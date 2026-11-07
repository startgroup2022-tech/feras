"""AI package: provider abstraction, grounding verification and factory.

``get_provider`` is the single place a provider is chosen. Selection is a
configuration change, never a code change, and the default (``none``) is the
deterministic provider so the platform is fully functional and testable without
any external model.
"""

from __future__ import annotations

from backend.ai.base import AIAnswer, AIProvider, PaidModelError, ProviderError
from backend.ai.grounding import find_ungrounded
from backend.ai.openrouter import (
    FREE_ROUTER_ID,
    FreeModel,
    OpenRouterClient,
    OpenRouterProvider,
    pricing_is_zero,
)
from backend.ai.providers import LocalProvider, NullProvider, OpenAICompatibleProvider
from backend.core.config import settings

__all__ = [
    "AIAnswer",
    "AIProvider",
    "FREE_ROUTER_ID",
    "FreeModel",
    "LocalProvider",
    "NullProvider",
    "OpenAICompatibleProvider",
    "OpenRouterClient",
    "OpenRouterProvider",
    "PaidModelError",
    "ProviderError",
    "find_ungrounded",
    "get_provider",
    "pricing_is_zero",
]


def _split_models(raw: str) -> list[str]:
    return [m.strip() for m in (raw or "").split(",") if m.strip()]


def get_provider() -> AIProvider:
    """Select the configured provider.

    Unknown or unavailable providers fall back to :class:`NullProvider` so the
    platform degrades to a grounded deterministic answer instead of failing. The
    OpenRouter provider is only selected when a key is present; without one it
    degrades too, rather than raising at import time.
    """
    choice = (settings.AI_PROVIDER or "none").strip().lower()

    if choice == "openrouter":
        if not settings.OPENROUTER_API_KEY:
            return NullProvider()
        return OpenRouterProvider(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            model=settings.OPENROUTER_MODEL or FREE_ROUTER_ID,
            fallback_models=_split_models(settings.OPENROUTER_FALLBACK_MODELS),
            timeout=settings.AI_TIMEOUT_SECONDS,
            max_cost_usd=settings.OPENROUTER_MAX_COST_USD,
            site_url=settings.OPENROUTER_SITE_URL,
            app_title=settings.OPENROUTER_APP_TITLE,
        )

    if choice in ("openai", "azure"):
        if not settings.AI_API_KEY:
            return NullProvider()
        return OpenAICompatibleProvider(
            base_url=settings.AI_BASE_URL or "https://api.openai.com/v1",
            api_key=settings.AI_API_KEY,
            model=settings.AI_MODEL,
        )

    if choice == "local":
        # A local server needs no key; a base URL is still required.
        if not settings.AI_BASE_URL:
            return NullProvider()
        return LocalProvider(
            base_url=settings.AI_BASE_URL,
            api_key=settings.AI_API_KEY or "not-needed",
            model=settings.AI_MODEL or "local-model",
        )

    return NullProvider()
