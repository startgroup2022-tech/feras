"""AI package: provider abstraction, grounding verification and factory."""

from __future__ import annotations

from backend.ai.base import AIAnswer, AIProvider, ProviderError
from backend.ai.grounding import find_ungrounded
from backend.ai.providers import LocalProvider, NullProvider, OpenAICompatibleProvider
from backend.core.config import settings

__all__ = [
    "AIAnswer",
    "AIProvider",
    "LocalProvider",
    "NullProvider",
    "OpenAICompatibleProvider",
    "ProviderError",
    "find_ungrounded",
    "get_provider",
]


def get_provider() -> AIProvider:
    """Select the configured provider.

    Unknown or unavailable providers fall back to :class:`NullProvider` so the
    platform degrades to a grounded deterministic answer instead of failing.
    """
    choice = (settings.AI_PROVIDER or "none").strip().lower()

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
