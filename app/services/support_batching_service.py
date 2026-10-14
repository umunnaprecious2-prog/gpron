"""Decides when a customer batch is ready and turns it into exactly one reply.

Lifecycle of one batch (all state lives in support_conversations):

  1. Intake sets due_at = min(last message + inactivity, batch start + max window).
  2. claim():   compare-and-set lease. Only one worker can hold it; an expired
                lease (crashed worker) can be taken over.
  3. If a voice note in the batch is still transcribing, release and retry
     shortly, up to the transcription timeout, then treat it as failed.
  4. Generate the reply with no DB transaction open.
  5. deliver(): a second compare-and-set that only succeeds if we still hold
     the lease AND no newer customer message arrived (customer_seq unchanged).
     Otherwise the reply is stale: drop it and let the batch run again with
     the new message included. After support_max_stale_regenerations drops,
     deliver anyway (covering the older messages) so a customer who keeps
     typing can't starve the conversation.
  6. The reply row has a unique (conversation_id, reply_to_seq), so even a
     lease bug could not store two replies to the same batch.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.models.db import SupportConversation, SupportMessage
from app.services.ai_response_service import (
    AIResponseService,
    AIUnavailableError,
    ContextMessage,
    SupportTools,
)
from app.services.business_info_service import CONTACT
from app.utils import metrics

logger = logging.getLogger(__name__)

FALLBACK_NOT_CONFIGURED = (
    'Sorry, I can\'t answer automatically right now. Tap "Talk to a person" and '
    f"the Gpron team will get back to you, or call {CONTACT['phone']} during "
    "opening hours."
)
FALLBACK_TEMPORARY = (
    "Sorry, I'm having trouble answering right now. Please try again in a "
    'moment, or tap "Talk to a person" to reach the Gpron team.'
)


@dataclass(frozen=True)
class Claim:
    conversation_id: uuid.UUID
    claim_id: str
    target_seq: int
    replied_through_seq: int
    batch_started_at: datetime | None
    user_id: uuid.UUID | None
    failed_attempts: int


@dataclass(frozen=True)
class DueScan:
    ids: list[uuid.UUID]
    next_due_at: datetime | None  # earliest future due_at, if any


def _utcnow() -> datetime:
    return datetime.utcnow()


@dataclass
class BatchProcessor:
    session_factory: async_sessionmaker[AsyncSession]
    ai: AIResponseService
    settings: Settings
    clock: Callable[[], datetime] = _utcnow

    # ------------------------------------------------------------------ query

    async def scan(self, limit: int = 20) -> DueScan:
        """Due conversations now, plus when the next one becomes due.

        Two cheap indexed reads. The worker sleeps until next_due_at instead
        of polling on a short fixed interval, which matters on metered
        databases (CockroachDB Serverless bills per request).
        """
        now = self.clock()
        async with self.session_factory() as db:
            result = await db.execute(
                select(SupportConversation.id)
                .where(
                    SupportConversation.due_at <= now,
                    _lease_free(now),
                )
                .order_by(SupportConversation.due_at)
                .limit(limit)
            )
            ids = list(result.scalars().all())
            waiting, next_due_at = (
                await db.execute(
                    select(func.count(), func.min(SupportConversation.due_at)).where(
                        SupportConversation.due_at > now
                    )
                )
            ).one()
        metrics.support_pending_conversations.set(len(ids) + (waiting or 0))
        return DueScan(ids=ids, next_due_at=next_due_at)

    async def clear_orphaned_schedules(self) -> int:
        """Maintenance: a due_at with nothing pending is leftover state."""
        async with self.session_factory() as db:
            result = await db.execute(
                update(SupportConversation)
                .where(
                    SupportConversation.due_at.is_not(None),
                    SupportConversation.customer_seq
                    <= SupportConversation.replied_through_seq,
                )
                .values(due_at=None)
            )
            await db.commit()
        return result.rowcount or 0

    # ---------------------------------------------------------------- process

    async def process(self, conversation_id: uuid.UUID) -> str:
        """Run one batch if it's due. Returns an outcome code (for logs/tests)."""
        claim = await self.claim(conversation_id)
        if claim is None:
            return "not_claimed"

        try:
            batch, history = await self._load_batch(claim)
            if batch is None:
                return "waiting_transcription"

            started = self.clock()
            if claim.batch_started_at:
                metrics.support_batch_wait_seconds.observe(
                    (started - claim.batch_started_at).total_seconds()
                )
            metrics.support_batch_size.observe(len(batch))

            tools = SupportTools(self.session_factory, claim.user_id)
            try:
                reply = await asyncio.wait_for(
                    self.ai.generate_reply(
                        history, batch, tools, signed_in=claim.user_id is not None
                    ),
                    # Finish well inside the lease so nobody else takes it over.
                    timeout=max(self.settings.support_claim_ttl_seconds - 5, 5),
                )
            except asyncio.TimeoutError:
                return await self._handle_failure(claim, AIUnavailableError("timeout"))
            except AIUnavailableError as exc:
                return await self._handle_failure(claim, exc)
            except Exception:
                logger.exception(
                    "support.generation_error conv=%s", claim.conversation_id
                )
                return await self._handle_failure(claim, AIUnavailableError("internal"))

            return await self.deliver(claim, reply.text, status="ready")
        except asyncio.CancelledError:
            # A newer customer message cancelled this generation (see
            # SupportWorker). Counts toward the stale limit, then hands back.
            await self.release(claim, stale=True)
            raise
        except Exception:
            # Never leave a lease dangling on an unexpected error; it would
            # only clear after the TTL.
            logger.exception("support.process_error conv=%s", claim.conversation_id)
            await self.release(claim, stale=False, retry_in=2.0)
            return "error"

    async def claim(self, conversation_id: uuid.UUID) -> Claim | None:
        now = self.clock()
        claim_id = str(uuid.uuid4())
        async with self.session_factory() as db:
            row = (
                await db.execute(
                    update(SupportConversation)
                    .where(
                        SupportConversation.id == conversation_id,
                        SupportConversation.due_at <= now,
                        SupportConversation.customer_seq
                        > SupportConversation.replied_through_seq,
                        _lease_free(now),
                    )
                    .values(
                        claim_id=claim_id,
                        claim_expires_at=now
                        + timedelta(seconds=self.settings.support_claim_ttl_seconds),
                    )
                    .returning(
                        SupportConversation.customer_seq,
                        SupportConversation.replied_through_seq,
                        SupportConversation.batch_started_at,
                        SupportConversation.user_id,
                        SupportConversation.failed_attempts,
                    )
                )
            ).one_or_none()
            await db.commit()
        if row is None:
            return None
        return Claim(conversation_id, claim_id, *row)

    async def _load_batch(
        self, claim: Claim
    ) -> tuple[list[ContextMessage] | None, list[ContextMessage]]:
        """Returns (batch, history); batch is None if we must wait for STT."""
        now = self.clock()
        timeout = timedelta(seconds=self.settings.support_transcription_timeout_seconds)
        async with self.session_factory() as db:
            rows = await self._batch_rows(db, claim)
            transcribing = [m for m in rows if m.status == "transcribing"]
            if transcribing:
                if all(now - m.created_at < timeout for m in transcribing):
                    await db.rollback()
                    await self.release(claim, stale=False, retry_in=1.0)
                    return None, []
                # Too slow: give up on those so they can't block the batch.
                await db.execute(
                    update(SupportMessage)
                    .where(
                        SupportMessage.id.in_([m.id for m in transcribing]),
                        SupportMessage.status == "transcribing",
                    )
                    .values(status="failed", error_code="transcription_timeout")
                )
                await db.commit()
                metrics.support_transcriptions_total.labels(outcome="timeout").inc(
                    len(transcribing)
                )
                rows = await self._batch_rows(db, claim)

            first_seq = rows[0].seq if rows else claim.target_seq + 1
            history_rows = (
                (
                    await db.execute(
                        select(SupportMessage)
                        .where(
                            SupportMessage.conversation_id == claim.conversation_id,
                            SupportMessage.seq < first_seq,
                        )
                        .order_by(SupportMessage.seq.desc())
                        .limit(self.settings.support_history_messages)
                    )
                )
                .scalars()
                .all()
            )

        batch = [_to_context(m) for m in rows]
        history = [_to_context(m) for m in reversed(history_rows)]
        return batch, history

    async def _batch_rows(self, db: AsyncSession, claim: Claim) -> list[SupportMessage]:
        result = await db.execute(
            select(SupportMessage)
            .where(
                SupportMessage.conversation_id == claim.conversation_id,
                SupportMessage.role == "customer",
                SupportMessage.seq > claim.replied_through_seq,
                SupportMessage.seq <= claim.target_seq,
            )
            .order_by(SupportMessage.seq)
            .execution_options(populate_existing=True)
        )
        return list(result.scalars().all())

    # --------------------------------------------------------------- outcomes

    async def deliver(self, claim: Claim, text: str, status: str) -> str:
        now = self.clock()
        more_pending = SupportConversation.customer_seq > claim.target_seq
        async with self.session_factory() as db:
            seq = (
                await db.execute(
                    update(SupportConversation)
                    .where(
                        SupportConversation.id == claim.conversation_id,
                        SupportConversation.claim_id == claim.claim_id,
                        (SupportConversation.customer_seq == claim.target_seq)
                        | (
                            SupportConversation.stale_count
                            >= self.settings.support_max_stale_regenerations
                        ),
                    )
                    .values(
                        last_seq=SupportConversation.last_seq + 1,
                        replied_through_seq=claim.target_seq,
                        claim_id=None,
                        claim_expires_at=None,
                        stale_count=0,
                        failed_attempts=0,
                        # Messages that arrived during a forced delivery start a
                        # fresh batch right away.
                        due_at=case(
                            (
                                more_pending,
                                now
                                + timedelta(
                                    seconds=self.settings.support_inactivity_seconds
                                ),
                            ),
                            else_=None,
                        ),
                        batch_started_at=case((more_pending, now), else_=None),
                        updated_at=now,
                    )
                    .returning(SupportConversation.last_seq)
                )
            ).scalar_one_or_none()

            if seq is None:
                await db.rollback()
                return await self._release_stale(claim)

            db.add(
                SupportMessage(
                    conversation_id=claim.conversation_id,
                    seq=seq,
                    role="assistant",
                    kind="text",
                    status=status,
                    content=text,
                    reply_to_seq=claim.target_seq,
                    created_at=now,
                )
            )
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                metrics.support_duplicates_prevented_total.labels(source="reply").inc()
                logger.warning(
                    "support.duplicate_reply_blocked conv=%s", claim.conversation_id
                )
                return "duplicate_prevented"

        outcome = "delivered" if status == "ready" else "fallback"
        metrics.support_replies_total.labels(outcome=outcome).inc()
        logger.info(
            "support.reply_%s conv=%s through_seq=%s",
            outcome,
            claim.conversation_id,
            claim.target_seq,
        )
        return outcome

    async def _release_stale(self, claim: Claim) -> str:
        async with self.session_factory() as db:
            released = (
                await db.execute(
                    update(SupportConversation)
                    .where(
                        SupportConversation.id == claim.conversation_id,
                        SupportConversation.claim_id == claim.claim_id,
                    )
                    .values(
                        claim_id=None,
                        claim_expires_at=None,
                        stale_count=SupportConversation.stale_count + 1,
                    )
                    .returning(SupportConversation.id)
                )
            ).scalar_one_or_none()
            await db.commit()
        if released is None:
            logger.warning("support.claim_lost conv=%s", claim.conversation_id)
            return "claim_lost"
        metrics.support_stale_suppressed_total.inc()
        logger.info("support.stale_reply_dropped conv=%s", claim.conversation_id)
        return "stale"

    async def release(
        self, claim: Claim, stale: bool, retry_in: float | None = None
    ) -> None:
        values: dict = {"claim_id": None, "claim_expires_at": None}
        if stale:
            values["stale_count"] = SupportConversation.stale_count + 1
        if retry_in is not None:
            values["due_at"] = self.clock() + timedelta(seconds=retry_in)
        async with self.session_factory() as db:
            await db.execute(
                update(SupportConversation)
                .where(
                    SupportConversation.id == claim.conversation_id,
                    SupportConversation.claim_id == claim.claim_id,
                )
                .values(**values)
            )
            await db.commit()

    async def _handle_failure(self, claim: Claim, exc: AIUnavailableError) -> str:
        metrics.support_ai_errors_total.labels(reason=f"batch_{exc.reason}").inc()
        attempts = claim.failed_attempts + 1
        logger.warning(
            "support.generation_failed conv=%s reason=%s attempt=%s",
            claim.conversation_id,
            exc.reason,
            attempts,
        )
        if exc.reason == "not_configured":
            return await self.deliver(claim, FALLBACK_NOT_CONFIGURED, status="fallback")
        if attempts >= self.settings.support_max_failed_attempts:
            return await self.deliver(claim, FALLBACK_TEMPORARY, status="fallback")

        metrics.support_generation_retries_total.inc()
        async with self.session_factory() as db:
            await db.execute(
                update(SupportConversation)
                .where(
                    SupportConversation.id == claim.conversation_id,
                    SupportConversation.claim_id == claim.claim_id,
                )
                .values(
                    claim_id=None,
                    claim_expires_at=None,
                    failed_attempts=attempts,
                    due_at=self.clock() + timedelta(seconds=2**attempts),
                )
            )
            await db.commit()
        return "retry_scheduled"

    # -------------------------------------------------------------- retention

    async def purge_expired(self) -> int:
        cutoff = self.clock() - timedelta(days=self.settings.support_retention_days)
        async with self.session_factory() as db:
            result = await db.execute(
                delete(SupportConversation).where(
                    SupportConversation.updated_at < cutoff
                )
            )
            await db.commit()
        return result.rowcount or 0


def _lease_free(now: datetime):
    return SupportConversation.claim_id.is_(None) | (
        SupportConversation.claim_expires_at < now
    )


def _to_context(msg: SupportMessage) -> ContextMessage:
    return ContextMessage(
        role=msg.role, kind=msg.kind, status=msg.status, content=msg.content
    )
