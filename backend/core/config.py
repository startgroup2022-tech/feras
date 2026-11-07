"""Environment-based application configuration.

All settings are read from environment variables (optionally via a ``.env``
file). No secret is ever hardcoded; ``SECRET_KEY`` and ``DATABASE_URL`` have
no usable default in production and are validated at startup.
"""

from __future__ import annotations

from functools import lru_cache
from typing import ClassVar

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
    # Public website form submissions. Per-IP, sliding window. Kept separate
    # from the login limiter so a busy marketing page cannot lock out sign-in.
    PUBLIC_RATE_LIMIT: int = 20
    PUBLIC_RATE_WINDOW_SECONDS: int = 600
    # Maximum attachments accepted on one public submission.
    PUBLIC_MAX_ATTACHMENTS: int = 5
    # Maximum project photos accepted on one business listing (item 06). The
    # brief's proposed limit is ten photos per listing.
    PUBLIC_MAX_LISTING_PHOTOS: int = 10

    # ---- public website ----
    # Absolute origin used to build canonical URLs, hreflang alternates and the
    # sitemap. Left blank in development, where relative URLs are emitted.
    WEBSITE_BASE_URL: str = ""
    # When true (production), the internal platform is served under PLATFORM_PATH
    # and marked noindex; the public website owns the root. When false
    # (development), the platform keeps the root so local workflows are
    # unchanged.
    SPLIT_PUBLIC_SITE: bool = False
    PLATFORM_PATH: str = "/platform"

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

    # ---- OpenRouter (primary provider) ----
    # The key lives only in the server environment; it is never sent to the
    # browser and never logged. ``AI_PROVIDER=openrouter`` selects this path.
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    # Default model. ``openrouter/free`` is a router that only ever selects
    # zero-cost models, so it is a safe default; the provider still verifies the
    # effective price of whatever it routes to and refuses anything billable.
    OPENROUTER_MODEL: str = "openrouter/free"
    # Ordered fallbacks, all verified free at request time. An empty list means
    # "no fallback" -- the provider never silently escalates to a paid model.
    OPENROUTER_FALLBACK_MODELS: str = ""
    # Models shown as verified-free in the admin panel. Refresh is a live call;
    # this is only the seed list used when the panel is opened offline.
    OPENROUTER_FREE_MODELS: str = "openrouter/free"
    # Attribution headers OpenRouter recommends; optional and non-secret.
    OPENROUTER_SITE_URL: str = ""
    OPENROUTER_APP_TITLE: str = "Safir Holding 2027"
    # Refuse a completion whose *reported* cost exceeds this (USD). Zero means
    # "any nonzero cost is rejected". This is a second line of defence after the
    # pricing check: if a router returned a paid model, the reported cost trips
    # the breaker and the answer is discarded.
    OPENROUTER_MAX_COST_USD: float = 0.0

    # ---- AI request limits and usage monitoring ----
    # Per-user, per-window application-level limits (independent of the
    # provider's own rate limits) so one account cannot exhaust the group's
    # free quota or hammer an upstream.
    AI_RATE_LIMIT_ENABLED: bool = True
    AI_RATE_LIMIT_REQUESTS: int = 30
    AI_RATE_LIMIT_WINDOW_SECONDS: int = 3600
    # Group-wide daily ceiling on metered provider calls. Reaching it degrades
    # to the deterministic provider rather than failing the request.
    AI_DAILY_REQUEST_LIMIT: int = 2000
    # How many knowledge chunks to retrieve as context for one answer.
    AI_KNOWLEDGE_TOP_K: int = 6
    # Chunk size (characters) for knowledge indexing. Overlap keeps a sentence
    # that straddles a boundary retrievable from either side.
    AI_KNOWLEDGE_CHUNK_CHARS: int = 900
    AI_KNOWLEDGE_CHUNK_OVERLAP: int = 150

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

    # A production secret must be long enough that it is not guessable and must
    # not be any of the values that ship in the repo (the dev default, the test
    # fixture, or a short placeholder). Length alone is the checkable property;
    # a real deployment generates this with ``secrets.token_urlsafe(64)``.
    MIN_PRODUCTION_SECRET_LEN: ClassVar[int] = 32
    _REJECTED_SECRETS: ClassVar[frozenset[str]] = frozenset({
        "dev-only-insecure-change-me",
        "test-secret-key-not-used-in-production",
        "changeme", "change-me", "secret", "password", "safir",
    })

    @field_validator("SECRET_KEY")
    @classmethod
    def _guard_secret(cls, v: str, info) -> str:
        env = info.data.get("APP_ENV", "development")
        if env != "production":
            return v
        if v in cls._REJECTED_SECRETS or len(v) < cls.MIN_PRODUCTION_SECRET_LEN:
            raise ValueError(
                "SECRET_KEY must be set to a strong unique value in production "
                f"(at least {cls.MIN_PRODUCTION_SECRET_LEN} characters, and not "
                "a placeholder). Generate one with "
                "`python -c \"import secrets; print(secrets.token_urlsafe(64))\"`."
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
