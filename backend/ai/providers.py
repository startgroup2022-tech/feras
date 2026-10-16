"""Concrete AI providers.

``NullProvider`` is deterministic and always available: it composes an Arabic
answer directly from the scoped context, so the platform is fully functional
(and testable) without any external model.

``OpenAICompatibleProvider`` targets any OpenAI-compatible ``/chat/completions``
endpoint. That covers hosted providers and, importantly for the Holding's
data-residency requirement, self-hosted open-weight models (vLLM, Ollama,
LM Studio, TGI) that expose the same API. The provider is only constructed when
``AI_PROVIDER`` selects it, so no network dependency exists in the default path.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal

from backend.ai.base import AIAnswer, ProviderError

logger = logging.getLogger("safir.ai")

_SYSTEM_PROMPT = (
    "أنت مساعد ذكاء أعمال واستثمار لمجموعة قابضة. تجيب بالعربية الفصحى بإيجاز "
    "تنفيذي. القاعدة المطلقة: لا تذكر أي رقم غير موجود في البيانات المرفقة. "
    "إذا لم تتوفر بيانات كافية، قل ذلك صراحةً بدل التخمين. "
    "You are a business & investment intelligence assistant for a holding "
    "company. Answer in concise executive Arabic. Never state a figure that is "
    "not present in the supplied data; say the data is unavailable instead."
)


def _money(value) -> str:
    return f"{Decimal(str(value or 0)):,.0f}"


class NullProvider:
    """Deterministic, fully-offline provider.

    Its answers are assembled from the context only, so they are grounded by
    construction. It is the default and the provider used by the test suite.
    """

    name = "none"

    def answer(self, *, question: str, context: dict) -> AIAnswer:
        return AIAnswer(text=self._compose(context), provider=self.name)

    # -- composition -------------------------------------------------------
    def _compose(self, context: dict) -> str:
        if context.get("scope") == "company":
            return self._company_answer(context)
        return self._holding_answer(context)

    def _company_answer(self, context: dict) -> str:
        kpis = context.get("kpis", {})
        companies = context.get("companies", [])
        period = context.get("period", {})
        name_ar = companies[0]["name_ar"] if companies else ""
        net = Decimal(str(kpis.get("total_net_result") or 0))

        lines = [
            f"ملخص أداء {name_ar} لشهر {period.get('month')}/{period.get('year')}:",
            (
                f"الإيرادات {_money(kpis.get('total_revenue'))}، "
                f"المصروفات {_money(kpis.get('total_expenses'))}، "
                f"صافي النتيجة {_money(net)}."
            ),
            "حالة التقرير الشهري: " + (context.get("report_status") or "لم يُرسل بعد") + ".",
        ]
        if context.get("major_problems"):
            lines.append(f"تحديات مذكورة في التقرير: {context['major_problems']}.")
        if context.get("support_required"):
            lines.append(f"الدعم المطلوب من المقر: {context['support_required']}.")
        lines.append(
            f"طلبات الدعم المفتوحة: {kpis.get('open_support_requests', 0)}."
        )
        lines.append("هذا ملخص مبني على البيانات المسجلة فعلياً في النظام.")
        return " ".join(lines)

    def _holding_answer(self, context: dict) -> str:
        kpis = context.get("kpis", {})
        missing = context.get("companies_missing_report", [])
        attention = context.get("companies_requiring_attention", [])
        period = context.get("period", {})
        change = context.get("change_vs_previous") or {}

        lines = [
            f"ملخص أداء المجموعة لشهر {period.get('month')}/{period.get('year')}:",
            (
                f"عدد الشركات {kpis.get('companies_count', 0)}، "
                f"واستلمنا تقارير {kpis.get('reports_submitted', 0)} شركة."
            ),
            (
                f"إجمالي الإيرادات {_money(kpis.get('total_revenue'))}، "
                f"وإجمالي المصروفات {_money(kpis.get('total_expenses'))}، "
                f"بصافي نتائج {_money(kpis.get('total_net_result'))}."
            ),
        ]
        if change.get("revenue_pct") is not None:
            direction = "ارتفاع" if change["revenue_pct"] >= 0 else "انخفاض"
            lines.append(
                f"{direction} الإيرادات بنسبة {abs(change['revenue_pct'])}٪ "
                "مقارنة بالشهر الماضي."
            )
        if missing:
            names = "، ".join(c["name_ar"] for c in missing)
            lines.append(f"شركات لم ترسل التقرير الشهري: {names}.")
        if attention:
            detail = "؛ ".join(
                f"{c['name_ar']} ({c['reason']})" for c in attention if c.get("reason")
            )
            if detail:
                lines.append(f"شركات تحتاج متابعة: {detail}.")
            else:
                lines.append(f"عدد الشركات التي تحتاج متابعة: {len(attention)}.")
        lines.append(
            f"طلبات الدعم المفتوحة لدى المقر: {kpis.get('open_support_requests', 0)}."
        )
        pending = kpis.get("pending_financial_reviews", 0)
        if pending:
            lines.append(f"هناك {pending} تقريراً بانتظار المراجعة المالية من المحاسب.")
        lines.append("جميع الأرقام أعلاه مستخرجة مباشرة من قاعدة بيانات النظام.")
        return " ".join(lines)


class OpenAICompatibleProvider:
    """Provider for any OpenAI-compatible chat-completions endpoint.

    Works with hosted APIs and self-hosted open-weight servers alike. Only the
    scoped context is sent, never raw database access, so the isolation boundary
    established before this call remains intact.
    """

    name = "openai"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 30.0,
    ) -> None:
        if not base_url or not model:
            raise ProviderError(
                "AI_BASE_URL and AI_MODEL must be set for the openai provider."
            )
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    def answer(self, *, question: str, context: dict) -> AIAnswer:
        # Imported lazily so the default (no-provider) path needs no HTTP client.
        import urllib.error
        import urllib.request

        payload = {
            "model": self._model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "بيانات النظام (مصدر الحقيقة الوحيد):\n"
                        + json.dumps(context, ensure_ascii=False, default=str)
                        + f"\n\nسؤال المستخدم: {question}"
                    ),
                },
            ],
        }
        request = urllib.request.Request(
            f"{self._base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            logger.warning("AI provider call failed: %s", exc)
            raise ProviderError("The AI provider is currently unavailable.") from exc

        try:
            text = body["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("The AI provider returned an unexpected response.") from exc

        usage = body.get("usage") or {}
        return AIAnswer(
            text=text,
            provider=self.name,
            tokens_used=usage.get("total_tokens"),
        )


class LocalProvider(OpenAICompatibleProvider):
    """Self-hosted open-weight model (vLLM / Ollama / LM Studio / TGI).

    Behaviourally identical to the hosted provider; named separately so the
    deployment mode is visible in configuration and audit records.
    """

    name = "local"
