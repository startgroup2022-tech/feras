"""AI text organization (S09 -- "تنظيم النص بالذكاء الاصطناعي").

The subsidiary monthly report carries free-text narrative (achievements,
challenges, proposals, ...). The spec gives the manager an AI action that
*organises* that text and shows a suggestion **while the original stays
untouched** ("يعرض اقتراح تنظيم مع بقاء الأصل").

Two properties follow from the spec and are enforced here:

1. **The original is never modified.** This module returns a proposal; the
   caller decides whether to keep it. There is no code path that writes the
   organised text back to the report.
2. **The AI never invents facts.** Organization is structural: the deterministic
   fallback re-groups and tidies the manager's own sentences and never adds a
   number. When a hosted provider is configured, its output is passed through
   the same numeric-grounding check used for Holding AI, and any invented figure
   is reported so the manager can see it is not trustworthy.
"""

from __future__ import annotations

import re

from backend.ai import find_ungrounded, get_provider
from backend.ai.base import ProviderError
from backend.ai.providers import NullProvider

# The narrative fields of the monthly report that a manager may organise.
ORGANIZABLE_FIELDS: tuple[str, ...] = (
    "important_developments",
    "new_customers",
    "new_opportunities",
    "major_problems",
    "support_required",
    "marketing_status",
    "business_development_status",
    "management_notes",
)

# Arabic sentence terminators plus the ASCII full stop and question mark.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?؟।\n])\s+|\n+")


def _tidy_sentence(sentence: str) -> str:
    """Collapse whitespace and normalise the terminating punctuation."""
    cleaned = re.sub(r"\s+", " ", sentence).strip()
    if not cleaned:
        return ""
    if cleaned[-1] not in ".!?؟।":
        cleaned += "."
    return cleaned


def organize_text(text: str) -> str:
    """Deterministic structural organisation of ``text``.

    Sentences are trimmed, de-duplicated (case-insensitively) and re-emitted as
    a tidy list. No word is added and no figure is introduced, so the result is
    grounded by construction.
    """
    if text is None:
        return ""
    raw = [s for s in _SENTENCE_SPLIT.split(text) if s and s.strip()]
    seen: set[str] = set()
    sentences: list[str] = []
    for candidate in raw:
        tidy = _tidy_sentence(candidate)
        if not tidy:
            continue
        key = tidy.casefold()
        if key in seen:
            continue
        seen.add(key)
        sentences.append(tidy)
    if not sentences:
        return ""
    if len(sentences) == 1:
        return sentences[0]
    return "\n".join(f"{i}. {s}" for i, s in enumerate(sentences, start=1))


def _organize_with_provider(text: str) -> tuple[str, str, list[str], bool]:
    """Organise via the configured provider, verifying numeric grounding.

    Returns ``(organised, provider_name, ungrounded_numbers, grounded)``. A
    provider failure or an ungrounded answer falls back to the deterministic
    organisation, so the manager always gets a trustworthy suggestion.
    """
    provider = get_provider()
    if isinstance(provider, NullProvider):
        organised = organize_text(text)
        return organised, provider.name, [], True

    context = {"text": text}
    try:
        answer = provider.answer(question=text, context=context)
    except ProviderError:
        organised = organize_text(text)
        return organised, "none", [], True

    ungrounded = find_ungrounded(answer.text, context)
    if ungrounded:
        # The model introduced a figure the source text cannot justify; the
        # suggestion must not be trusted, so fall back to the safe version.
        organised = organize_text(text)
        return organised, "none", ungrounded, True
    return answer.text.strip(), answer.provider, [], True


def organize_narrative(fields: dict[str, str | None]) -> dict:
    """Build an organization proposal for a set of narrative fields.

    ``fields`` maps a report field name to its current value. The response lists
    only the fields that carry text, each with the ``original`` (echoed back
    unchanged) and the ``organized`` suggestion. Nothing is persisted.
    """
    proposals: list[dict] = []
    for name in ORGANIZABLE_FIELDS:
        original = fields.get(name)
        if not original or not original.strip():
            continue
        organised, provider, ungrounded, grounded = _organize_with_provider(original)
        proposals.append(
            {
                "field": name,
                "original": original,
                "organized": organised,
                "provider": provider,
                "grounded": grounded,
                "ungrounded_numbers": ungrounded,
                "changed": organised != original,
            }
        )
    return {"proposals": proposals, "fields_considered": len(proposals)}
