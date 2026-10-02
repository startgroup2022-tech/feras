"""AI provider architecture and answer-grounding tests.

Covers the Phase 2 provider abstraction: the deterministic provider stays the
default, an OpenAI-compatible provider can be selected purely through
configuration, and -- critically -- the grounding check rejects any figure that
the scoped context cannot justify.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.ai import find_ungrounded, get_provider
from backend.ai.base import AIAnswer, ProviderError
from backend.ai.providers import LocalProvider, NullProvider, OpenAICompatibleProvider
from backend.core.config import settings


# --------------------------------------------------------------------------
# provider selection (configuration only)
# --------------------------------------------------------------------------
def test_default_provider_is_deterministic(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "none")
    assert isinstance(get_provider(), NullProvider)


def test_openai_provider_requires_key(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "openai")
    monkeypatch.setattr(settings, "AI_API_KEY", "")
    # No key configured -> degrade to the deterministic provider, never crash.
    assert isinstance(get_provider(), NullProvider)


def test_openai_provider_selected_with_config(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "openai")
    monkeypatch.setattr(settings, "AI_API_KEY", "sk-test")
    monkeypatch.setattr(settings, "AI_MODEL", "gpt-test")
    monkeypatch.setattr(settings, "AI_BASE_URL", "https://api.example.com/v1")
    provider = get_provider()
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.name == "openai"


def test_local_provider_selected_for_open_weight(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "local")
    monkeypatch.setattr(settings, "AI_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setattr(settings, "AI_MODEL", "qwen2")
    provider = get_provider()
    assert isinstance(provider, LocalProvider)
    assert provider.name == "local"


def test_openai_provider_requires_base_url_and_model():
    with pytest.raises(ProviderError):
        OpenAICompatibleProvider(base_url="", api_key="x", model="y")


def test_unknown_provider_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "does-not-exist")
    assert isinstance(get_provider(), NullProvider)


# --------------------------------------------------------------------------
# grounding
# --------------------------------------------------------------------------
CONTEXT = {
    "scope": "holding",
    "period": {"year": 2027, "month": 10},
    "kpis": {
        "companies_count": 6,
        "reports_submitted": 5,
        "total_revenue": 14130000.0,
        "total_expenses": 10400000.0,
        "total_net_result": 3730000.0,
        "open_support_requests": 4,
    },
}


def test_grounded_answer_passes():
    answer = "إجمالي الإيرادات 14,130,000 وصافي النتائج 3,730,000."
    assert find_ungrounded(answer, CONTEXT) == []


def test_invented_figure_is_flagged():
    answer = "إجمالي الإيرادات 99,999,999."
    assert "99,999,999" in find_ungrounded(answer, CONTEXT)


def test_arabic_indic_numerals_are_grounded():
    # ١٤٬١٣٠٬٠٠٠ == 14,130,000 which is in context.
    answer = "الإيرادات ١٤,١٣٠,٠٠٠"
    assert find_ungrounded(answer, CONTEXT) == []


def test_small_structural_numbers_allowed():
    # "4 companies" style prose should not be flagged when 4 is a real value.
    assert find_ungrounded("طلبات الدعم المفتوحة: 4", CONTEXT) == []


def test_null_provider_answer_is_grounded():
    provider = NullProvider()
    result = provider.answer(question="ملخص", context=CONTEXT)
    assert isinstance(result, AIAnswer)
    assert result.grounded
    assert find_ungrounded(result.text, CONTEXT) == []


def test_null_provider_never_invents_numbers():
    """A sparse context must still yield an answer with no stray figures."""
    sparse = {"scope": "holding", "period": {"year": 2027, "month": 10}, "kpis": {}}
    result = NullProvider().answer(question="?", context=sparse)
    assert find_ungrounded(result.text, sparse) == []


def test_grounding_reads_nested_context():
    ctx = {"companies": [{"id": 1, "revenue": Decimal(555000)}]}
    assert find_ungrounded("الإيرادات 555,000", ctx) == []
    assert find_ungrounded("الإيرادات 556,000", ctx) != []
