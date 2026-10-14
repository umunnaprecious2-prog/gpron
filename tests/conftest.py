import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Awaitable, Callable
from urllib.parse import urlsplit

import pytest
import pytest_asyncio

from app.config import settings as app_settings
from app.database import Base, SessionLocal, engine

# Import registers the ORM models on Base.metadata, needed for create_all.
from app.models import db as db_models  # noqa: F401
from app.services.ai_response_service import (
    AIResponseService,
    AIUnavailableError,
    ChatCompletion,
    ToolCall,
)
from app.services.speech_service import SpeechError, SynthesizedAudio
from app.services.support_batching_service import BatchProcessor
from app.services.support_worker import SupportRuntime


def pytest_configure(config):
    """Refuse to run against a hosted database by accident.

    .env usually holds the production DATABASE_URL, and these tests create
    users, orders and chats. Point DATABASE_URL at a local/throwaway Postgres
    (see read.md), or set ALLOW_REMOTE_TEST_DB=1 if you really mean it.
    """
    host = urlsplit(app_settings.database_url).hostname or ""
    local = host in {"localhost", "127.0.0.1", "postgres", "::1"}
    if not local and os.environ.get("ALLOW_REMOTE_TEST_DB") != "1":
        pytest.exit(
            f"Refusing to run tests against non-local database host '{host}'. "
            "Set DATABASE_URL to a local test database.",
            returncode=2,
        )


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _create_tables():
    """Postgres needs tables to exist before tests run (Mongo collections
    were created implicitly). Runs once per test session against whatever
    DATABASE_URL is configured (local Docker Postgres by default)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


# --------------------------------------------------------------------------
# Support agent test doubles. No test ever calls a paid provider.
# --------------------------------------------------------------------------


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime.utcnow()

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> datetime:
        self.now += timedelta(seconds=seconds)
        return self.now


@dataclass
class FakeChatProvider:
    """Scriptable ChatProvider. Records every prompt it was sent."""

    replies: list = field(default_factory=list)  # ChatCompletion | Exception
    default_text: str = "Happy to help with that."
    calls: list[list[dict]] = field(default_factory=list)
    # Awaited inside complete(), e.g. to simulate slow generation or to insert
    # a customer message mid-generation.
    during_call: Callable[[int], Awaitable[None]] | None = None

    async def complete(self, messages: list[dict], tools: list[dict]) -> ChatCompletion:
        self.calls.append([dict(m) for m in messages])
        if self.during_call is not None:
            await self.during_call(len(self.calls))
        if self.replies:
            nxt = self.replies.pop(0)
            if isinstance(nxt, Exception):
                raise nxt
            return nxt
        return ChatCompletion(content=self.default_text, prompt_tokens=10)

    def last_user_message(self, call_index: int = -1) -> str:
        return [m for m in self.calls[call_index] if m["role"] == "user"][-1]["content"]


class FakeSpeechProvider:
    name = "fake"
    can_synthesize = True

    def __init__(self, transcript: str = "hello from a voice note") -> None:
        self.transcript = transcript
        self.fail_with: str | None = None
        self.gate: asyncio.Event | None = None

    async def transcribe(self, audio: bytes, extension: str, mime: str) -> str:
        if self.gate is not None:
            await self.gate.wait()
        if self.fail_with:
            raise SpeechError(self.fail_with)
        return self.transcript

    async def synthesize(self, text: str) -> SynthesizedAudio:
        return SynthesizedAudio(b"ID3fake-mp3", "audio/mpeg")


def make_test_settings(**overrides):
    base = {
        "support_worker_enabled": False,
        "support_inactivity_seconds": 3.0,
        "support_max_batch_seconds": 10.0,
        "support_max_stale_regenerations": 2,
        "support_max_failed_attempts": 3,
        "support_transcription_timeout_seconds": 30.0,
        "support_claim_ttl_seconds": 60.0,
        "openai_api_key": "test-key-not-real",
    }
    base.update(overrides)
    return app_settings.model_copy(update=base)


def make_processor(provider, clock, **overrides) -> BatchProcessor:
    s = make_test_settings(**overrides)
    return BatchProcessor(
        session_factory=SessionLocal,
        ai=AIResponseService(provider=provider, settings=s),
        settings=s,
        clock=clock,
    )


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def fake_provider() -> FakeChatProvider:
    return FakeChatProvider()


@pytest.fixture
def fake_speech() -> FakeSpeechProvider:
    return FakeSpeechProvider()


@pytest.fixture
def support_runtime(fake_provider, fake_speech, clock):
    """Installs a support runtime on the app with fakes and no background worker."""
    from app.main import app

    s = make_test_settings()
    runtime = SupportRuntime(
        settings=s,
        session_factory=SessionLocal,
        processor=make_processor(fake_provider, clock),
        speech=fake_speech,
        worker=None,
    )
    app.state.support = runtime
    yield runtime
    app.state.support = None


__all__ = [
    "AIUnavailableError",
    "ChatCompletion",
    "FakeChatProvider",
    "FakeClock",
    "FakeSpeechProvider",
    "ToolCall",
    "make_processor",
    "make_test_settings",
]
