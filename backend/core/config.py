"""Environment-based application configuration.

All settings are read from environment variables (optionally via a ``.env``
file). No secret is ever hardcoded; ``SECRET_KEY`` and ``DATABASE_URL`` have
no usable default in production and are validated at startup.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---- application ----
    APP_NAME: str = "Safir Holding 2027"
    APP_ENV: str = Field(default="development")  # development | test | production
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # Swagger/OpenAPI. Enabled by default for development; staging/production
    # tiers may disable it or restrict it at the reverse proxy (see
    # ``deploy/nginx/``). Disabled outright when APP_ENV=production.
    DOCS_ENABLED: bool = True

    # ---- database ----
    # Defaults to a local SQLite file for development only. Production must
    # provide a PostgreSQL URL (postgresql+psycopg://...).
    DATABASE_URL: str = "sqlite:///./safir_dev.db"
    DB_ECHO: bool = False

    # ---- security ----
    SECRET_KEY: str = "dev-only-insecure-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ---- CORS ----
    # Comma separated list of allowed origins for the static frontend.
    CORS_ORIGINS: str = "http://localhost:12000,http://localhost:12001"

    # ---- rate limiting ----
    RATE_LIMIT_ENABLED: bool = True
    LOGIN_RATE_LIMIT: int = 10  # attempts
    LOGIN_RATE_WINDOW_SECONDS: int = 300

    # ---- attachments ----
    UPLOAD_DIR: str = "./uploads"

    # ---- AI ----
    # none | openai | azure | local
    #   none   -> deterministic, offline provider (default, used by tests)
    #   openai -> any OpenAI-compatible endpoint (AI_BASE_URL, AI_API_KEY)
    #   local  -> self-hosted open-weight server (vLLM / Ollama / LM Studio)
    AI_PROVIDER: str = "none"
    AI_MODEL: str = ""
    AI_API_KEY: str = ""
    AI_BASE_URL: str = ""  # e.g. https://api.openai.com/v1 or http://localhost:11434/v1
    AI_TIMEOUT_SECONDS: float = 30.0

    # ---- notification centre ----
    # Days before a document's expiry date that an "expiring soon" notification
    # is raised. Mirrors EXPIRING_SOON_DAYS but is configurable per deployment.
    NOTIFICATION_EXPIRY_WINDOW_DAYS: int = 30
    # When true, a notification also queues an email delivery (adapter chosen by
    # EMAIL_PROVIDER). Off by default so no outbound call happens unless asked.
    NOTIFICATION_EMAIL_ENABLED: bool = False

    # ---- external integrations ----
    # none | console | smtp. "console" logs the message (safe in dev/staging);
    # "smtp" performs a real send using the SMTP_* settings below.
    EMAIL_PROVIDER: str = "none"
    EMAIL_FROM: str = "no-reply@safir.local"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    # Outbound webhooks. When false, events are recorded but not delivered, so
    # the feature can be demonstrated without egress.
    WEBHOOKS_ENABLED: bool = False
    WEBHOOK_TIMEOUT_SECONDS: float = 10.0
    WEBHOOK_MAX_ATTEMPTS: int = 3

    @field_validator("SECRET_KEY")
    @classmethod
    def _guard_secret(cls, v: str, info) -> str:
        env = info.data.get("APP_ENV", "development")
        if env == "production" and v == "dev-only-insecure-change-me":
            raise ValueError(
                "SECRET_KEY must be set to a strong unique value in production."
            )
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
