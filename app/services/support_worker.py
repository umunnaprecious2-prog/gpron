"""In-process background worker for the support agent, plus runtime wiring.

No external queue: due batches are found by polling support_conversations.due_at
(indexed) and woken early on new messages. Everything is persisted, so after a
restart the first poll picks up whatever was pending, and expired leases from
a crashed run are taken over. Safe to run on several instances at once; the
DB lease decides who processes each batch.
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Coroutine

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.services.ai_response_service import AIResponseService, OpenAIChatProvider
from app.services.speech_service import SpeechProvider, build_speech_provider
from app.services.support_batching_service import BatchProcessor
from app.utils.rate_limit import RateLimiter

logger = logging.getLogger(__name__)

PURGE_INTERVAL_SECONDS = 3600
MIN_SLEEP_SECONDS = 0.2


class SupportWorker:
    def __init__(self, processor: BatchProcessor, settings: Settings):
        self._processor = processor
        self._settings = settings
        self._wake = asyncio.Event()
        self._sem = asyncio.Semaphore(max(settings.support_worker_concurrency, 1))
        self._inflight: dict[uuid.UUID, asyncio.Task] = {}
        self._cancels: dict[uuid.UUID, int] = {}
        self._background: set[asyncio.Task] = set()
        self._loop_task: asyncio.Task | None = None
        self._last_purge = 0.0

    async def start(self) -> None:
        if self._loop_task is None:
            self._loop_task = asyncio.create_task(self._run(), name="support-worker")
            logger.info("support.worker_started")

    async def stop(self) -> None:
        tasks = [
            t
            for t in [self._loop_task, *self._inflight.values(), *self._background]
            if t
        ]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._loop_task = None

    def notify_new_message(self, conversation_id: uuid.UUID) -> None:
        """A customer message arrived: cancel an in-flight generation for the
        same conversation (its answer would be stale) and wake the loop.

        Cancellation is bounded by support_max_stale_regenerations, after
        which the generation is allowed to finish and deliver.
        """
        task = self._inflight.get(conversation_id)
        if task is not None and not task.done():
            count = self._cancels.get(conversation_id, 0)
            if count < self._settings.support_max_stale_regenerations:
                self._cancels[conversation_id] = count + 1
                task.cancel()
        self._wake.set()

    def submit(self, coro: Coroutine, wake_after: bool = True) -> None:
        """Run a background job (e.g. transcription) tied to the worker's lifetime."""

        async def runner() -> None:
            try:
                await coro
            finally:
                if wake_after:
                    self._wake.set()

        task = asyncio.create_task(runner())
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def run_once(self) -> float:
        """Start due batches. Returns seconds until the next known due time
        (capped at the idle poll interval, which is the restart/multi-instance
        safety net)."""
        scan = await self._processor.scan()
        for conv_id in scan.ids:
            if conv_id in self._inflight:
                continue
            task = asyncio.create_task(self._process(conv_id))
            self._inflight[conv_id] = task
        idle = self._settings.support_worker_poll_seconds
        if scan.next_due_at is None:
            return idle
        until_due = (scan.next_due_at - self._processor.clock()).total_seconds()
        return min(max(until_due, MIN_SLEEP_SECONDS), idle)

    async def _process(self, conv_id: uuid.UUID) -> None:
        try:
            async with self._sem:
                outcome = await self._processor.process(conv_id)
            if outcome in ("delivered", "fallback"):
                self._cancels.pop(conv_id, None)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("support.worker_task_error conv=%s", conv_id)
        finally:
            self._inflight.pop(conv_id, None)
            # Something may now be due (e.g. a stale batch that must re-run).
            self._wake.set()

    async def _maintenance(self) -> None:
        purged = await self._processor.purge_expired()
        orphaned = await self._processor.clear_orphaned_schedules()
        if purged or orphaned:
            logger.info(
                "support.maintenance purged=%s orphaned_schedules=%s", purged, orphaned
            )

    async def _run(self) -> None:
        error_backoff = 1.0
        while True:
            # Clear before scanning: a wake-up that arrives during the scan
            # must not be lost.
            self._wake.clear()
            try:
                sleep_for = await self.run_once()
                if time.monotonic() - self._last_purge > PURGE_INTERVAL_SECONDS:
                    self._last_purge = time.monotonic()
                    await self._maintenance()
                error_backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception:
                # DB briefly unavailable etc.: keep the loop alive, back off.
                logger.exception("support.worker_loop_error")
                error_backoff = min(error_backoff * 2, 30)
                sleep_for = error_backoff
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=sleep_for)
            except asyncio.TimeoutError:
                pass


@dataclass
class SupportLimiters:
    """Per-instance abuse limits. Keys are client IPs or conversation ids."""

    conversations_per_ip: RateLimiter = field(
        default_factory=lambda: RateLimiter(20, 3600)
    )
    messages_per_ip: RateLimiter = field(default_factory=lambda: RateLimiter(60, 60))
    messages_per_conversation: RateLimiter = field(
        default_factory=lambda: RateLimiter(20, 60)
    )
    voice_per_conversation: RateLimiter = field(
        default_factory=lambda: RateLimiter(8, 60)
    )
    tts_per_conversation: RateLimiter = field(
        default_factory=lambda: RateLimiter(15, 60)
    )
    escalations_per_ip: RateLimiter = field(
        default_factory=lambda: RateLimiter(5, 3600)
    )


@dataclass
class SupportRuntime:
    """Everything the support routes need, built once at startup."""

    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]
    processor: BatchProcessor
    speech: SpeechProvider | None
    worker: SupportWorker | None = None
    limiters: SupportLimiters = field(default_factory=SupportLimiters)

    @property
    def ai_available(self) -> bool:
        return bool(self.settings.openai_api_key)

    @property
    def voice_output_available(self) -> bool:
        return self.speech is not None and getattr(self.speech, "can_synthesize", False)


def build_support_runtime(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession]
) -> SupportRuntime:
    ai = AIResponseService(provider=OpenAIChatProvider(settings), settings=settings)
    processor = BatchProcessor(
        session_factory=session_factory, ai=ai, settings=settings
    )
    speech = build_speech_provider(settings)
    worker = (
        SupportWorker(processor, settings) if settings.support_worker_enabled else None
    )
    return SupportRuntime(
        settings=settings,
        session_factory=session_factory,
        processor=processor,
        speech=speech,
        worker=worker,
    )
