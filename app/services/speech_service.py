"""Speech-to-text and text-to-speech behind one small, swappable interface.

Providers: ElevenLabs (preferred) and OpenAI (fallback, reuses OPENAI_API_KEY).
Audio is only ever held in memory: nothing is written to disk, so there are
no temporary files to clean up and no raw recordings are retained.
"""

import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"
OPENAI_BASE = "https://api.openai.com/v1"

# Browser MediaRecorder output (webm/ogg opus, Safari mp4/aac) plus common
# uploads. Maps the declared MIME type to the filename extension providers need.
ALLOWED_AUDIO_TYPES: dict[str, str] = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/aac": "m4a",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
}


class SpeechError(Exception):
    """Speech provider failure. `reason` is a short, metric-safe code."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def normalize_mime(content_type: str | None) -> str:
    # "audio/webm;codecs=opus" -> "audio/webm"
    return (content_type or "").split(";")[0].strip().lower()


def sniff_audio(data: bytes) -> str | None:
    """Identify the container from magic bytes; None if it isn't known audio.

    The declared Content-Type is client-controlled, so the actual bytes must
    agree before anything is sent to a provider.
    """
    head = data[:16]
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm"
    if head.startswith(b"OggS"):
        return "ogg"
    if head[4:8] == b"ftyp":
        return "m4a"
    if head.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return "wav"
    if head.startswith(b"ID3") or (
        len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0
    ):
        return "mp3"
    return None


@dataclass(frozen=True)
class SynthesizedAudio:
    data: bytes
    media_type: str


class SpeechProvider(Protocol):
    name: str

    async def transcribe(self, audio: bytes, extension: str, mime: str) -> str: ...

    async def synthesize(self, text: str) -> SynthesizedAudio: ...


SPEECH_ATTEMPTS = 2
CONNECT_TIMEOUT_SECONDS = 5.0


async def _post(url: str, timeout: float, **kwargs) -> httpx.Response:
    """POST with one retry on a hung or dropped connection.

    `timeout` is the total budget; it is split across attempts so a stalled
    first connection doesn't use the whole budget before the retry.
    """
    per_attempt = httpx.Timeout(
        timeout / SPEECH_ATTEMPTS, connect=min(CONNECT_TIMEOUT_SECONDS, timeout)
    )
    reason = "network"
    for _ in range(SPEECH_ATTEMPTS):
        try:
            async with httpx.AsyncClient(timeout=per_attempt) as client:
                res = await client.post(url, **kwargs)
            break
        except httpx.TimeoutException:
            reason = "timeout"
        except httpx.HTTPError:
            reason = "network"
    else:
        raise SpeechError(reason)
    if res.status_code in (401, 403):
        raise SpeechError("not_configured")
    if res.status_code == 429:
        raise SpeechError("rate_limited")
    if res.status_code >= 400:
        raise SpeechError(f"http_{res.status_code}")
    return res


class ElevenLabsSpeechProvider:
    name = "elevenlabs"

    def __init__(self, settings: Settings):
        self._s = settings

    @property
    def can_synthesize(self) -> bool:
        return bool(self._s.elevenlabs_voice_id)

    async def transcribe(self, audio: bytes, extension: str, mime: str) -> str:
        res = await _post(
            f"{ELEVENLABS_BASE}/speech-to-text",
            self._s.speech_timeout_seconds,
            headers={"xi-api-key": self._s.elevenlabs_api_key},
            data={
                "model_id": self._s.elevenlabs_stt_model,
                "tag_audio_events": "false",
            },
            files={"file": (f"voice.{extension}", audio, mime)},
        )
        return str(res.json().get("text", "")).strip()

    async def synthesize(self, text: str) -> SynthesizedAudio:
        if not self._s.elevenlabs_voice_id:
            raise SpeechError("not_configured")
        res = await _post(
            f"{ELEVENLABS_BASE}/text-to-speech/{self._s.elevenlabs_voice_id}",
            self._s.speech_timeout_seconds,
            params={"output_format": "mp3_44100_64"},
            headers={"xi-api-key": self._s.elevenlabs_api_key},
            json={"text": text, "model_id": self._s.elevenlabs_tts_model},
        )
        return SynthesizedAudio(res.content, "audio/mpeg")


class OpenAISpeechProvider:
    name = "openai"

    def __init__(self, settings: Settings):
        self._s = settings

    @property
    def can_synthesize(self) -> bool:
        return True

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._s.openai_api_key}"}

    async def transcribe(self, audio: bytes, extension: str, mime: str) -> str:
        res = await _post(
            f"{OPENAI_BASE}/audio/transcriptions",
            self._s.speech_timeout_seconds,
            headers=self._headers(),
            data={"model": self._s.openai_stt_model},
            files={"file": (f"voice.{extension}", audio, mime)},
        )
        return str(res.json().get("text", "")).strip()

    async def synthesize(self, text: str) -> SynthesizedAudio:
        res = await _post(
            f"{OPENAI_BASE}/audio/speech",
            self._s.speech_timeout_seconds,
            headers=self._headers(),
            json={
                "model": self._s.openai_tts_model,
                "voice": self._s.openai_tts_voice,
                "input": text,
                "response_format": "mp3",
            },
        )
        return SynthesizedAudio(res.content, "audio/mpeg")


def build_speech_provider(settings: Settings) -> SpeechProvider | None:
    """Pick the configured provider, or None when voice is unavailable."""
    choice = settings.speech_provider.lower()
    if choice == "none":
        return None
    if choice in ("auto", "elevenlabs") and settings.elevenlabs_api_key:
        return ElevenLabsSpeechProvider(settings)
    if choice in ("auto", "openai") and settings.openai_api_key:
        return OpenAISpeechProvider(settings)
    if choice not in ("auto", "elevenlabs", "openai"):
        logger.warning("Unknown SPEECH_PROVIDER %r; voice disabled", choice)
    return None
