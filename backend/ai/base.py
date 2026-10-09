"""AI provider abstraction.

The application never talks to a model directly. It builds a *scoped* context
payload (see :mod:`backend.services.ai_service`), then hands it to a provider
that implements :class:`AIProvider`. Swapping the deterministic provider for a
real model -- hosted or open-weight served locally -- is a configuration change
(``AI_PROVIDER``), not a code change.

Two guarantees hold for every provider:

1. The provider only ever receives the context payload. Because that payload was
   assembled after company isolation was enforced, a provider cannot leak
   another company's data even if the question asks for it.
2. Answers are checked for grounding: every numeric figure in the answer must
   appear in the context (see :mod:`backend.ai.grounding`). A model that invents
   a number is caught rather than trusted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


class ProviderError(RuntimeError):
    """Raised when a provider is misconfigured or the upstream call fails."""


@dataclass(slots=True)
class AIAnswer:
    """A provider's answer plus the provenance the API exposes to the client."""

    text: str
    provider: str
    # Numeric tokens in ``text`` that could not be traced back to the context.
    ungrounded_numbers: list[str] = field(default_factory=list)
    # Optional token accounting when the provider reports it.
    tokens_used: int | None = None

    @property
    def grounded(self) -> bool:
        return not self.ungrounded_numbers


@runtime_checkable
class AIProvider(Protocol):
    """Interface every AI backend implements."""

    name: str

    def answer(self, *, question: str, context: dict) -> AIAnswer: ...
