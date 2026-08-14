from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

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


settings = Settings()
