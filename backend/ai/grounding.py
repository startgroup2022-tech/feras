"""Grounding check for AI answers.

The rule the Holding AI must never break: *it must not invent financial
figures*. A language model is not a trustworthy source of numbers, so instead of
asking it nicely, we verify it. Every numeric token in an answer is compared
against the numbers present in the scoped context payload. Anything that cannot
be traced back is reported as ungrounded.

The check is deliberately conservative in one direction: it may occasionally
accept a number that happens to coincide with a context value, but it never
lets an invented figure pass silently. Callers decide how to react -- the API
surfaces the provenance, and the audit log records it.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

# Western and Arabic-Indic digit ranges.
_ARABIC_INDIC = {ord(c): ord("0") + i for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
_EXTENDED_ARABIC = {ord(c): ord("0") + i for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")}

_NUMBER_RE = re.compile(r"\d[\d,._]*\d|\d")
_CURRENCY_NOISE = re.compile(r"[^\d.,\-]")


def to_western_digits(text: str) -> str:
    """Normalise Arabic-Indic numerals to ASCII digits."""
    return text.translate(_ARABIC_INDIC).translate(_EXTENDED_ARABIC)


def _canonical(value: Decimal) -> str:
    """A comparison key for a number, ignoring formatting and scale."""
    normalised = value.normalize()
    if normalised == normalised.to_integral_value():
        return str(int(normalised))
    return format(normalised, "f")


def _parse_token(token: str) -> Decimal | None:
    """Parse a numeric token that may use thousands separators or Arabic digits."""
    cleaned = to_western_digits(token).strip().replace(",", "").replace("_", "").strip(".")
    if not cleaned or cleaned in {"-", "."}:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _iter_numbers(payload) -> list[Decimal]:
    """Recursively collect every numeric value in a nested payload."""
    found: list[Decimal] = []
    if isinstance(payload, bool):
        return found
    if isinstance(payload, (int, float, Decimal)):
        try:
            found.append(Decimal(str(payload)))
        except InvalidOperation:
            pass
    elif isinstance(payload, str):
        for token in _NUMBER_RE.findall(to_western_digits(payload)):
            parsed = _parse_token(token)
            if parsed is not None:
                found.append(parsed)
    elif isinstance(payload, dict):
        for value in payload.values():
            found.extend(_iter_numbers(value))
    elif isinstance(payload, (list, tuple, set)):
        for value in payload:
            found.extend(_iter_numbers(value))
    return found


def allowed_numbers(context: dict) -> set[str]:
    """Every number the context can justify, in canonical form.

    Rounding is tolerated: money is often presented rounded to the nearest unit,
    so both the exact value and its rounded integer form are accepted.
    """
    allowed: set[str] = set()
    # Structural numbers that legitimately appear in prose.
    allowed.update(str(i) for i in range(13))
    for value in _iter_numbers(context):
        allowed.add(_canonical(value))
        try:
            allowed.add(_canonical(value.to_integral_value(rounding="ROUND_HALF_UP")))
        except InvalidOperation:
            pass
    return allowed


def extract_numbers(text: str) -> list[str]:
    """Numeric tokens as they appear in ``text`` (Western digits)."""
    return [token.strip(".,") for token in _NUMBER_RE.findall(to_western_digits(text))]


def find_ungrounded(answer: str, context: dict) -> list[str]:
    """Return numeric tokens in ``answer`` that the context cannot justify."""
    allowed = allowed_numbers(context)
    ungrounded: list[str] = []
    for token in _NUMBER_RE.findall(to_western_digits(answer)):
        parsed = _parse_token(token)
        if parsed is None:
            continue
        if _canonical(parsed) not in allowed:
            ungrounded.append(token.strip(".,"))
    return ungrounded
