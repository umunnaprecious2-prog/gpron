"""Voice note intake: upload validation and transcription into the message row."""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.exceptions.errors import (
    PayloadTooLargeError,
    UnsupportedMediaError,
    ValidationFailedError,
)
from app.models.db import SupportMessage
from app.services.speech_service import (
    ALLOWED_AUDIO_TYPES,
    SpeechError,
    SpeechProvider,
    normalize_mime,
    sniff_audio,
)
from app.utils import metrics

logger = logging.getLogger(__name__)

MIN_AUDIO_BYTES = 1_000  # anything smaller is not a usable recording


@dataclass(frozen=True)
class ValidatedAudio:
    data: bytes
    mime: str
    extension: str


def validate_audio_upload(
    data: bytes, content_type: str | None, settings: Settings
) -> ValidatedAudio:
    if len(data) > settings.voice_max_upload_bytes:
        raise PayloadTooLargeError(
            f"Voice notes can be at most {settings.voice_max_seconds} seconds long."
        )
    if len(data) < MIN_AUDIO_BYTES:
        raise ValidationFailedError("That recording was too short. Please try again.")

    mime = normalize_mime(content_type)
    if mime not in ALLOWED_AUDIO_TYPES:
        raise UnsupportedMediaError("Unsupported audio format.")
    sniffed = sniff_audio(data)
    # Bytes must look like real audio; mp4 vs m4a style mismatches between
    # declared type and container are fine, a non-audio file is not.
    if sniffed is None:
        raise UnsupportedMediaError("That file doesn't look like an audio recording.")
    return ValidatedAudio(data=data, mime=mime, extension=sniffed)


async def transcribe_and_store(
    session_factory: async_sessionmaker[AsyncSession],
    speech: SpeechProvider,
    message_id: uuid.UUID,
    audio: ValidatedAudio,
    settings: Settings,
) -> str:
    """Transcribe in memory and write the result. Returns an outcome code."""
    started = time.monotonic()
    text = ""
    error_code: str | None = None
    try:
        text = await asyncio.wait_for(
            speech.transcribe(audio.data, audio.extension, audio.mime),
            # Provider calls retry within this budget; small margin on top.
            timeout=settings.speech_timeout_seconds + 2,
        )
        if not text.strip():
            error_code = "empty_transcript"
    except asyncio.TimeoutError:
        error_code = "timeout"
    except SpeechError as exc:
        error_code = exc.reason
    except Exception:
        logger.exception("support.transcription_error msg=%s", message_id)
        error_code = "internal"

    metrics.support_transcription_latency_seconds.observe(time.monotonic() - started)
    outcome = "ok" if error_code is None else error_code
    metrics.support_transcriptions_total.labels(outcome=outcome).inc()

    async with session_factory() as db:
        # Only fill a message still waiting; if the batch already timed it out,
        # a late transcript must not rewrite history the AI has answered.
        await db.execute(
            update(SupportMessage)
            .where(
                SupportMessage.id == message_id,
                SupportMessage.status == "transcribing",
            )
            .values(
                content=(
                    text.strip()[: settings.support_max_message_chars]
                    if error_code is None
                    else ""
                ),
                status="ready" if error_code is None else "failed",
                error_code=error_code,
            )
        )
        await db.commit()
    return outcome
