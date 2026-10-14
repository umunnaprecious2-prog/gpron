from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Strips leading/trailing whitespace from every string field. Env var
    # dashboards (Render and others) commonly pick up a trailing newline
    # when a value is pasted in, which otherwise turns e.g. DATABASE_URL's
    # database name into "defaultdb\n" -- a real name that doesn't exist.
    model_config = SettingsConfigDict(env_file=".env", str_strip_whitespace=True)

    database_url: str
    secret_key: str
    email_service_key: str = ""
    openai_api_key: str = ""
    # No default: a hardcoded working value here would let any deployment
    # that forgets to set MANAGER_CODE silently accept a well-known code for
    # manager registration. Must come from .env / the real environment.
    manager_code: str
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours
    allowed_origins: str = (
        "*"  # comma-separated list, e.g. "https://gpron.onrender.com"
    )

    # --- AI support agent -------------------------------------------------
    openai_chat_model: str = "gpt-4.1-mini"
    ai_timeout_seconds: float = 20.0
    ai_max_retries: int = 2  # per provider call, for timeouts / 429 / 5xx
    ai_max_tool_rounds: int = 3
    ai_max_output_tokens: int = 450

    # Batching: reply once the customer pauses for support_inactivity_seconds,
    # or support_max_batch_seconds after the batch's first message at most.
    support_inactivity_seconds: float = 3.0
    support_max_batch_seconds: float = 10.0
    support_transcription_timeout_seconds: float = 30.0
    support_max_stale_regenerations: int = 2
    support_max_failed_attempts: int = 3
    support_claim_ttl_seconds: float = 60.0
    support_worker_enabled: bool = True
    # Longest the worker sleeps when idle. It is woken immediately by new
    # messages and otherwise sleeps until the next batch is due, so this is
    # only the safety net for restarts / other instances. Keeps DB load low.
    support_worker_poll_seconds: float = 15.0
    support_worker_concurrency: int = 4
    support_retention_days: int = 30
    support_history_messages: int = 20
    support_max_message_chars: int = 1000
    support_max_messages_per_conversation: int = 200

    # Speech: "auto" picks ElevenLabs when its key is set, else OpenAI when
    # its key is set, else voice is disabled. "none" turns voice off.
    speech_provider: str = "auto"
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    elevenlabs_stt_model: str = "scribe_v2"
    elevenlabs_tts_model: str = "eleven_multilingual_v2"
    openai_stt_model: str = "gpt-4o-mini-transcribe"
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "alloy"
    speech_timeout_seconds: float = 30.0
    voice_max_upload_bytes: int = 3_000_000
    voice_max_seconds: int = 60
    tts_max_chars: int = 1200

    # /metrics is only served when this is set (Prometheus sends it as a
    # bearer token), so it is never public by accident.
    metrics_token: str = ""


settings = Settings()
