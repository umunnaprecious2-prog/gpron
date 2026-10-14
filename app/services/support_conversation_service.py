"""Support conversations: creation, access control, message intake, history."""

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import case, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.exceptions.errors import NotFoundError, TooManyRequestsError
from app.models.db import SupportConversation, SupportMessage, User
from app.utils import metrics


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_conversation(
    db: AsyncSession, user: User | None, now: datetime
) -> tuple[SupportConversation, str]:
    """Returns the conversation and its access token (shown once, stored hashed)."""
    token = secrets.token_urlsafe(32)
    conv = SupportConversation(
        token_hash=hash_token(token),
        user_id=user.id if user else None,
        created_at=now,
        updated_at=now,
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv, token


async def get_authorized_conversation(
    db: AsyncSession, conversation_id: str, token: str | None
) -> SupportConversation:
    """Load a conversation only if the caller holds its token.

    Wrong id, wrong token and malformed input all return the same 404, so the
    endpoint can't be used to discover which conversation ids exist.
    """
    not_found = NotFoundError("Conversation not found")
    if not token:
        raise not_found
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except ValueError:
        raise not_found
    conv = await db.get(SupportConversation, conv_uuid)
    if conv is None or not hmac.compare_digest(conv.token_hash, hash_token(token)):
        raise not_found
    return conv


@dataclass(frozen=True)
class IntakeResult:
    message: SupportMessage
    created: bool  # False when a retry matched an existing client_msg_id


async def _find_by_client_id(
    db: AsyncSession, conv_id: uuid.UUID, client_msg_id: str
) -> SupportMessage | None:
    result = await db.execute(
        select(SupportMessage).where(
            SupportMessage.conversation_id == conv_id,
            SupportMessage.client_msg_id == client_msg_id,
        )
    )
    return result.scalar_one_or_none()


async def add_customer_message(
    db: AsyncSession,
    conv: SupportConversation,
    *,
    kind: str,
    content: str,
    status: str,
    client_msg_id: str,
    now: datetime,
    settings: Settings,
) -> IntakeResult:
    """Persist a customer message and (re)schedule the conversation's batch.

    The conversation row UPDATE assigns the seq and takes a row lock, so
    concurrent sends to one conversation are serialized and never share a seq.
    """
    existing = await _find_by_client_id(db, conv.id, client_msg_id)
    if existing is not None:
        metrics.support_duplicates_prevented_total.labels(source="message_retry").inc()
        return IntakeResult(existing, created=False)

    if conv.last_seq >= settings.support_max_messages_per_conversation:
        raise TooManyRequestsError(
            "This conversation has reached its message limit. Please start a new chat."
        )

    pending = SupportConversation.customer_seq > SupportConversation.replied_through_seq
    row = (
        await db.execute(
            update(SupportConversation)
            .where(SupportConversation.id == conv.id)
            .values(
                last_seq=SupportConversation.last_seq + 1,
                customer_seq=SupportConversation.last_seq + 1,
                last_customer_at=now,
                # Keep the running batch's start time if one is open; the max
                # collection window is measured from the batch's first message.
                batch_started_at=_case_keep_batch_start(pending, now),
                updated_at=now,
            )
            .returning(
                SupportConversation.last_seq, SupportConversation.batch_started_at
            )
        )
    ).one()
    seq, batch_started_at = row
    due_at = min(
        now + timedelta(seconds=settings.support_inactivity_seconds),
        batch_started_at + timedelta(seconds=settings.support_max_batch_seconds),
    )
    await db.execute(
        update(SupportConversation)
        .where(SupportConversation.id == conv.id)
        .values(due_at=due_at)
    )

    msg = SupportMessage(
        conversation_id=conv.id,
        seq=seq,
        role="customer",
        kind=kind,
        status=status,
        content=content,
        client_msg_id=client_msg_id,
        created_at=now,
    )
    db.add(msg)
    try:
        await db.commit()
    except IntegrityError:
        # Same client_msg_id raced in on a parallel request: that one won.
        await db.rollback()
        existing = await _find_by_client_id(db, conv.id, client_msg_id)
        if existing is None:
            raise
        metrics.support_duplicates_prevented_total.labels(source="message_race").inc()
        return IntakeResult(existing, created=False)

    await db.refresh(msg)
    metrics.support_messages_total.labels(kind=kind).inc()
    return IntakeResult(msg, created=True)


def _case_keep_batch_start(pending, now: datetime):
    return case(
        (
            pending & SupportConversation.batch_started_at.is_not(None),
            SupportConversation.batch_started_at,
        ),
        else_=now,
    )


async def add_system_message(
    db: AsyncSession, conv_id: uuid.UUID, content: str, now: datetime
) -> SupportMessage:
    """Append a non-customer note (e.g. a recorded support request).

    Does not touch customer_seq, so it never opens or extends a batch.
    """
    seq = (
        await db.execute(
            update(SupportConversation)
            .where(SupportConversation.id == conv_id)
            .values(last_seq=SupportConversation.last_seq + 1, updated_at=now)
            .returning(SupportConversation.last_seq)
        )
    ).scalar_one()
    msg = SupportMessage(
        conversation_id=conv_id,
        seq=seq,
        role="system",
        kind="text",
        status="ready",
        content=content,
        created_at=now,
    )
    db.add(msg)
    return msg


async def list_messages(
    db: AsyncSession, conv_id: uuid.UUID, after_seq: int, limit: int = 100
) -> list[SupportMessage]:
    result = await db.execute(
        select(SupportMessage)
        .where(
            SupportMessage.conversation_id == conv_id,
            SupportMessage.seq > after_seq,
        )
        .order_by(SupportMessage.seq)
        .limit(limit)
    )
    return list(result.scalars().all())


async def conversation_stage(
    db: AsyncSession, conv: SupportConversation, now: datetime
) -> str | None:
    """What the customer should see while waiting: None when nothing is pending.

    collecting    still within the batching window ("I'm following along...")
    transcribing  a voice note in the batch is still being transcribed
    thinking      a worker holds the batch and is generating
    """
    if conv.customer_seq <= conv.replied_through_seq:
        return None
    transcribing = await db.execute(
        select(SupportMessage.id)
        .where(
            SupportMessage.conversation_id == conv.id,
            SupportMessage.seq > conv.replied_through_seq,
            SupportMessage.status == "transcribing",
        )
        .limit(1)
    )
    if transcribing.first() is not None:
        return "transcribing"
    if conv.claim_id and conv.claim_expires_at and conv.claim_expires_at > now:
        return "thinking"
    return "collecting"


async def get_message(
    db: AsyncSession, conv_id: uuid.UUID, message_id: str
) -> SupportMessage:
    try:
        msg_uuid = uuid.UUID(message_id)
    except ValueError:
        raise NotFoundError("Message not found")
    msg = await db.get(SupportMessage, msg_uuid)
    if msg is None or msg.conversation_id != conv_id:
        raise NotFoundError("Message not found")
    return msg
