"""Batching, staleness, concurrency and recovery for the support agent.

Each test drives a real Postgres database with a fake AI provider and a fake
clock, so the 3s / 10s windows are exercised exactly without sleeping.
"""

import asyncio
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models.db import SupportConversation, SupportMessage
from app.services import support_conversation_service as conversations
from app.services.ai_response_service import (
    AIUnavailableError,
    ChatCompletion,
    OpenAIChatProvider,
)
from app.services.support_batching_service import (
    FALLBACK_NOT_CONFIGURED,
    DueScan,
    FALLBACK_TEMPORARY,
)
from app.services.support_voice_service import ValidatedAudio, transcribe_and_store
from tests.conftest import (
    FakeChatProvider,
    FakeSpeechProvider,
    make_processor,
    make_test_settings,
)

SETTINGS = make_test_settings()


async def new_conversation(clock) -> uuid.UUID:
    async with SessionLocal() as db:
        conv, _ = await conversations.create_conversation(db, None, clock())
        return conv.id


async def say(conv_id, clock, text, kind="text", status="ready") -> SupportMessage:
    async with SessionLocal() as db:
        conv = await db.get(SupportConversation, conv_id)
        result = await conversations.add_customer_message(
            db,
            conv,
            kind=kind,
            content=text,
            status=status,
            client_msg_id=uuid.uuid4().hex,
            now=clock(),
            settings=SETTINGS,
        )
        return result.message


async def replies(conv_id) -> list[SupportMessage]:
    async with SessionLocal() as db:
        result = await db.execute(
            select(SupportMessage)
            .where(
                SupportMessage.conversation_id == conv_id,
                SupportMessage.role == "assistant",
            )
            .order_by(SupportMessage.seq)
        )
        return list(result.scalars().all())


async def conversation(conv_id) -> SupportConversation:
    async with SessionLocal() as db:
        return await db.get(SupportConversation, conv_id)


# 1 ---------------------------------------------------------------------------
async def test_single_message_gets_one_reply(clock, fake_provider):
    proc = make_processor(fake_provider, clock)
    conv_id = await new_conversation(clock)
    await say(conv_id, clock, "What services do you offer?")

    assert await proc.process(conv_id) == "not_claimed"  # still inside 3s window
    clock.advance(3.1)
    assert await proc.process(conv_id) == "delivered"

    out = await replies(conv_id)
    assert [r.content for r in out] == ["Happy to help with that."]
    assert len(fake_provider.calls) == 1
    assert fake_provider.last_user_message() == "What services do you offer?"
    conv = await conversation(conv_id)
    assert conv.replied_through_seq == conv.customer_seq
    assert conv.due_at is None and conv.claim_id is None


# 2 ---------------------------------------------------------------------------
async def test_four_rapid_messages_combined_into_one_reply(clock, fake_provider):
    proc = make_processor(fake_provider, clock)
    conv_id = await new_conversation(clock)
    texts = [
        "Hello.",
        "I brought my clothes yesterday.",
        "I need them for tomorrow.",
        "Can I upgrade to express service?",
    ]
    for text in texts:
        await say(conv_id, clock, text)
        clock.advance(1.0)
        assert await proc.process(conv_id) == "not_claimed"

    clock.advance(2.5)
    assert await proc.process(conv_id) == "delivered"
    assert await proc.process(conv_id) == "not_claimed"

    assert len(await replies(conv_id)) == 1
    assert len(fake_provider.calls) == 1
    prompt = fake_provider.last_user_message()
    positions = [prompt.index(t) for t in texts]
    assert positions == sorted(positions), "messages must keep their order"
    assert "in a row" in prompt


# 3 ---------------------------------------------------------------------------
async def test_pause_longer_than_inactivity_triggers_processing(clock, fake_provider):
    proc = make_processor(fake_provider, clock)
    conv_id = await new_conversation(clock)
    await say(conv_id, clock, "How much is express?")
    clock.advance(2.9)
    assert await proc.process(conv_id) == "not_claimed"
    clock.advance(0.2)
    assert await proc.process(conv_id) == "delivered"

    # A later message after the reply starts a fresh batch and gets its own reply.
    clock.advance(20)
    await say(conv_id, clock, "And normal service?")
    clock.advance(3.1)
    assert await proc.process(conv_id) == "delivered"
    assert len(await replies(conv_id)) == 2
    assert fake_provider.last_user_message() == "And normal service?"


# 4 ---------------------------------------------------------------------------
async def test_max_window_prevents_indefinite_waiting(clock, fake_provider):
    proc = make_processor(fake_provider, clock)
    conv_id = await new_conversation(clock)
    # A message every 2s never lets the 3s inactivity window close.
    for i in range(5):  # sends at t=0,2,4,6,8; checks at t=1.9,...,9.9
        await say(conv_id, clock, f"part {i}")
        clock.advance(1.9)
        assert await proc.process(conv_id) == "not_claimed"
        clock.advance(0.1)
    # t=10s since the first message: the max window forces processing even
    # though the customer just sent another message.
    await say(conv_id, clock, "part 5")
    assert await proc.process(conv_id) == "delivered"
    assert "part 0" in fake_provider.last_user_message()
    assert "part 5" in fake_provider.last_user_message()


# 5 ---------------------------------------------------------------------------
async def test_text_and_voice_transcripts_combined(clock, fake_provider):
    proc = make_processor(fake_provider, clock)
    speech = FakeSpeechProvider("I dropped my clothes this morning.")
    conv_id = await new_conversation(clock)

    voice = await say(conv_id, clock, "", kind="voice", status="transcribing")
    await transcribe_and_store(
        SessionLocal,
        speech,
        voice.id,
        ValidatedAudio(b"x", "audio/webm", "webm"),
        SETTINGS,
    )
    clock.advance(1)
    await say(conv_id, clock, "My order number is GPRON-2026-0001.")
    clock.advance(1)
    voice2 = await say(conv_id, clock, "", kind="voice", status="transcribing")
    speech.transcript = "Can I get everything before Friday?"
    await transcribe_and_store(
        SessionLocal,
        speech,
        voice2.id,
        ValidatedAudio(b"x", "audio/webm", "webm"),
        SETTINGS,
    )

    clock.advance(3.1)
    assert await proc.process(conv_id) == "delivered"
    prompt = fake_provider.last_user_message()
    assert "1. [voice note, transcribed] I dropped my clothes this morning." in prompt
    assert "2. My order number is GPRON-2026-0001." in prompt
    assert "3. [voice note, transcribed] Can I get everything before Friday?" in prompt


# 6 ---------------------------------------------------------------------------
async def test_delayed_transcription_is_waited_for_not_dropped(clock, fake_provider):
    proc = make_processor(fake_provider, clock)
    speech = FakeSpeechProvider("please deliver on Saturday")
    conv_id = await new_conversation(clock)
    await say(conv_id, clock, "About my order")
    voice = await say(conv_id, clock, "", kind="voice", status="transcribing")

    clock.advance(5)  # batch is due, but the voice note is still transcribing
    assert await proc.process(conv_id) == "waiting_transcription"
    assert fake_provider.calls == []

    await transcribe_and_store(
        SessionLocal,
        speech,
        voice.id,
        ValidatedAudio(b"x", "audio/ogg", "ogg"),
        SETTINGS,
    )
    clock.advance(1.1)
    assert await proc.process(conv_id) == "delivered"
    assert "please deliver on Saturday" in fake_provider.last_user_message()


async def test_transcription_timeout_marks_failed_and_asks_to_repeat(
    clock, fake_provider
):
    proc = make_processor(fake_provider, clock)
    conv_id = await new_conversation(clock)
    voice = await say(conv_id, clock, "", kind="voice", status="transcribing")

    clock.advance(31)  # past support_transcription_timeout_seconds
    assert await proc.process(conv_id) == "delivered"
    assert "could not be transcribed" in fake_provider.last_user_message()
    async with SessionLocal() as db:
        msg = await db.get(SupportMessage, voice.id)
    assert msg.status == "failed" and msg.error_code == "transcription_timeout"

    # A transcript that arrives after the timeout must not rewrite history.
    await transcribe_and_store(
        SessionLocal,
        FakeSpeechProvider("late"),
        voice.id,
        ValidatedAudio(b"x", "audio/ogg", "ogg"),
        SETTINGS,
    )
    async with SessionLocal() as db:
        msg = await db.get(SupportMessage, voice.id)
    assert msg.status == "failed" and msg.content == ""


async def test_empty_transcript_is_failed_not_invented(clock, fake_provider):
    conv_id = await new_conversation(clock)
    voice = await say(conv_id, clock, "", kind="voice", status="transcribing")
    outcome = await transcribe_and_store(
        SessionLocal,
        FakeSpeechProvider("   "),
        voice.id,
        ValidatedAudio(b"x", "audio/ogg", "ogg"),
        SETTINGS,
    )
    assert outcome == "empty_transcript"
    async with SessionLocal() as db:
        assert (await db.get(SupportMessage, voice.id)).status == "failed"


# 7 ---------------------------------------------------------------------------
async def test_message_during_generation_suppresses_stale_reply(clock):
    conv_id = await new_conversation(clock)

    async def customer_adds_clarification(call_no: int) -> None:
        if call_no == 1:
            await say(conv_id, clock, "Actually, make it express.")

    provider = FakeChatProvider(during_call=customer_adds_clarification)
    proc = make_processor(provider, clock)
    await say(conv_id, clock, "I want to order 3 shirts.")
    clock.advance(3.1)

    assert await proc.process(conv_id) == "stale"
    assert await replies(conv_id) == []  # stale answer never delivered

    clock.advance(3.1)
    assert await proc.process(conv_id) == "delivered"
    out = await replies(conv_id)
    assert len(out) == 1
    second_prompt = provider.last_user_message()
    assert "3 shirts" in second_prompt and "make it express" in second_prompt
    conv = await conversation(conv_id)
    assert out[0].reply_to_seq == conv.customer_seq
    assert conv.stale_count == 0


async def test_stale_regeneration_is_bounded(clock):
    """A customer typing during every generation can't starve the chat."""
    conv_id = await new_conversation(clock)

    async def always_interrupt(call_no: int) -> None:
        await say(conv_id, clock, f"one more thing #{call_no}")

    provider = FakeChatProvider(during_call=always_interrupt)
    proc = make_processor(provider, clock, support_max_stale_regenerations=2)
    await say(conv_id, clock, "first question")

    outcomes = []
    for _ in range(4):
        clock.advance(11)
        outcomes.append(await proc.process(conv_id))
        if outcomes[-1] == "delivered":
            break
    assert outcomes == ["stale", "stale", "delivered"]
    out = await replies(conv_id)
    assert len(out) == 1
    conv = await conversation(conv_id)
    # The message that arrived during the forced delivery opens the next batch.
    assert conv.customer_seq > conv.replied_through_seq
    assert conv.due_at is not None


async def test_worker_cancels_in_flight_generation_on_new_message(clock):
    from app.services.support_worker import SupportWorker

    conv_id = await new_conversation(clock)
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow(call_no: int) -> None:
        started.set()
        await release.wait()

    provider = FakeChatProvider(during_call=slow)
    proc = make_processor(provider, clock)

    async def only_this_conversation(limit: int = 20):
        # The shared test DB holds other tests' pending chats; keep this
        # worker focused on the one under test.
        return DueScan(ids=[conv_id], next_due_at=None)

    proc.scan = only_this_conversation
    worker = SupportWorker(proc, proc.settings)
    await say(conv_id, clock, "first")
    clock.advance(3.1)

    try:
        await _cancel_scenario(worker, proc, provider, clock, conv_id, started, release)
    finally:
        await worker.stop()


async def _cancel_scenario(worker, proc, provider, clock, conv_id, started, release):
    await worker.run_once()
    await asyncio.wait_for(started.wait(), 5)
    await say(conv_id, clock, "second")
    in_flight = list(worker._inflight.values())
    assert len(in_flight) == 1
    worker.notify_new_message(conv_id)  # cancels the in-flight generation
    await asyncio.wait(in_flight, timeout=10)  # cancellation + lease release
    release.set()
    assert await replies(conv_id) == []
    conv = await conversation(conv_id)
    assert (conv.claim_id, conv.stale_count, conv.failed_attempts) == (None, 1, 0)

    provider.during_call = None
    clock.advance(3.1)
    assert await proc.process(conv_id) == "delivered"
    assert "second" in provider.last_user_message()


# 8 ---------------------------------------------------------------------------
async def test_two_concurrent_workers_cannot_answer_same_batch(clock):
    conv_id = await new_conversation(clock)
    gate = asyncio.Event()

    async def hold(call_no: int) -> None:
        await gate.wait()

    provider = FakeChatProvider(during_call=hold)
    worker_a = make_processor(provider, clock)
    worker_b = make_processor(provider, clock)
    await say(conv_id, clock, "Where is my order?")
    clock.advance(3.1)

    task_a = asyncio.create_task(worker_a.process(conv_id))
    task_b = asyncio.create_task(worker_b.process(conv_id))
    await asyncio.sleep(0.3)
    gate.set()
    outcomes = sorted(await asyncio.gather(task_a, task_b))

    assert outcomes == ["delivered", "not_claimed"]
    assert len(provider.calls) == 1
    assert len(await replies(conv_id)) == 1


async def test_parallel_sends_get_unique_ordered_seqs(clock):
    conv_id = await new_conversation(clock)
    msgs = await asyncio.gather(*(say(conv_id, clock, f"m{i}") for i in range(8)))
    seqs = sorted(m.seq for m in msgs)
    assert seqs == list(range(1, 9))
    conv = await conversation(conv_id)
    assert conv.customer_seq == 8 and conv.last_seq == 8


# 9 ---------------------------------------------------------------------------
async def test_retried_message_is_not_duplicated(clock):
    conv_id = await new_conversation(clock)
    async with SessionLocal() as db:
        conv = await db.get(SupportConversation, conv_id)
        first = await conversations.add_customer_message(
            db,
            conv,
            kind="text",
            content="hi",
            status="ready",
            client_msg_id="retry-key-123",
            now=clock(),
            settings=SETTINGS,
        )
    async with SessionLocal() as db:
        conv = await db.get(SupportConversation, conv_id)
        second = await conversations.add_customer_message(
            db,
            conv,
            kind="text",
            content="hi",
            status="ready",
            client_msg_id="retry-key-123",
            now=clock(),
            settings=SETTINGS,
        )
    assert first.created and not second.created
    assert first.message.id == second.message.id
    async with SessionLocal() as db:
        count = await db.scalar(
            select(func.count()).where(SupportMessage.conversation_id == conv_id)
        )
    assert count == 1


async def test_database_blocks_second_reply_to_same_batch(clock, fake_provider):
    proc = make_processor(fake_provider, clock)
    conv_id = await new_conversation(clock)
    await say(conv_id, clock, "hello")
    clock.advance(3.1)
    assert await proc.process(conv_id) == "delivered"
    first = (await replies(conv_id))[0]

    async with SessionLocal() as db:
        db.add(
            SupportMessage(
                conversation_id=conv_id,
                seq=999,
                role="assistant",
                content="dup",
                reply_to_seq=first.reply_to_seq,
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()


# 10 --------------------------------------------------------------------------
async def test_pending_messages_survive_restart(clock, fake_provider):
    conv_id = await new_conversation(clock)
    await say(conv_id, clock, "Are you open on Sunday?")
    clock.advance(3.1)

    # "Restart": a brand-new processor with no in-memory state finds the work.
    fresh = make_processor(fake_provider, clock)
    assert conv_id in (await fresh.scan(limit=1000)).ids
    assert await fresh.process(conv_id) == "delivered"


async def test_crashed_worker_lease_is_taken_over(clock, fake_provider):
    conv_id = await new_conversation(clock)
    await say(conv_id, clock, "Hi there")
    clock.advance(3.1)

    crashed = make_processor(fake_provider, clock)
    assert await crashed.claim(conv_id) is not None  # claims, then "dies"

    survivor = make_processor(fake_provider, clock)
    assert await survivor.process(conv_id) == "not_claimed"  # lease still valid
    clock.advance(61)  # past support_claim_ttl_seconds
    assert await survivor.process(conv_id) == "delivered"
    assert len(await replies(conv_id)) == 1


# 11 --------------------------------------------------------------------------
async def test_missing_ai_credentials_give_clear_recoverable_fallback(clock):
    no_key = make_test_settings(openai_api_key="")
    proc = make_processor(OpenAIChatProvider(no_key), clock)
    conv_id = await new_conversation(clock)
    await say(conv_id, clock, "hello?")
    clock.advance(3.1)

    assert await proc.process(conv_id) == "fallback"
    out = await replies(conv_id)
    assert out[0].content == FALLBACK_NOT_CONFIGURED and out[0].status == "fallback"

    # Once credentials work again, the same conversation recovers.
    healthy = make_processor(FakeChatProvider(default_text="Back online."), clock)
    await say(conv_id, clock, "still there?")
    clock.advance(3.1)
    assert await healthy.process(conv_id) == "delivered"
    assert (await replies(conv_id))[-1].content == "Back online."


async def test_transient_ai_failure_retries_with_backoff_then_succeeds(clock):
    provider = FakeChatProvider(
        replies=[AIUnavailableError("timeout"), ChatCompletion(content="Got it.")]
    )
    proc = make_processor(provider, clock)
    conv_id = await new_conversation(clock)
    await say(conv_id, clock, "hello")
    clock.advance(3.1)

    assert await proc.process(conv_id) == "retry_scheduled"
    assert await proc.process(conv_id) == "not_claimed"  # backoff not elapsed
    clock.advance(2.1)
    assert await proc.process(conv_id) == "delivered"
    assert (await replies(conv_id))[0].content == "Got it."


async def test_repeated_ai_failures_never_block_conversation(clock):
    provider = FakeChatProvider(replies=[AIUnavailableError("provider_5xx")] * 5)
    proc = make_processor(provider, clock, support_max_failed_attempts=3)
    conv_id = await new_conversation(clock)
    await say(conv_id, clock, "hello")

    outcomes = []
    for _ in range(5):
        clock.advance(10)
        outcomes.append(await proc.process(conv_id))
        if outcomes[-1] == "fallback":
            break
    assert outcomes == ["retry_scheduled", "retry_scheduled", "fallback"]
    assert (await replies(conv_id))[0].content == FALLBACK_TEMPORARY


async def test_retention_purge_removes_old_conversations(clock, fake_provider):
    proc = make_processor(fake_provider, clock, support_retention_days=30)
    conv_id = await new_conversation(clock)
    await say(conv_id, clock, "old chat")
    clock.advance(31 * 24 * 3600)
    assert await proc.purge_expired() >= 1
    assert await conversation(conv_id) is None


async def test_worker_sleeps_until_next_due_batch_instead_of_polling(
    clock, fake_provider
):
    """Idle DB load matters on metered databases: the worker must sleep until
    the next known due time, not wake on a short fixed interval."""
    from app.services.support_worker import SupportWorker

    proc = make_processor(fake_provider, clock, support_worker_poll_seconds=15.0)
    conv_id = await new_conversation(clock)

    async def scoped_scan(limit: int = 20):
        full = await type(proc).scan(proc, limit)
        mine = await conversation(conv_id)
        due = mine.due_at if mine.due_at and mine.due_at > clock() else None
        return DueScan(ids=[i for i in full.ids if i == conv_id], next_due_at=due)

    proc.scan = scoped_scan
    worker = SupportWorker(proc, proc.settings)
    try:
        assert await worker.run_once() == 15.0  # nothing pending: idle cap
        await say(conv_id, clock, "hello")
        assert 2.9 <= await worker.run_once() <= 3.0  # sleeps until due, not 0.5s
    finally:
        await worker.stop()
