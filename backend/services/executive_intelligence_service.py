"""Executive intelligence: scoped context assembly and a narrative briefing.

This sits above :mod:`backend.services.ai_service` and
:mod:`backend.services.analytics_service`. It answers a different question:
not "what are the numbers" but "what should management take from them".

Two ideas make it safe and useful:

**Permission-shaped context.** The context handed to a provider is assembled
section by section, and a section is only included when the caller holds the
permission that governs it. A company manager therefore never has group
financial analytics in the prompt -- not because the prompt asks the model to
ignore it, but because the data is never placed there.

**Grounded, degrade-never-fail briefing.** The narrative is produced by the
configured provider when one is available. If the provider is missing,
unreachable, or returns figures that cannot be traced back to the context, the
service falls back to a deterministic briefing composed from the same data and
marks the result ``degraded``. The executive always gets an answer, and the
answer is always grounded.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from decimal import Decimal

from backend.ai import AIAnswer, ProviderError, find_ungrounded, get_provider
from backend.db.models.identity import User
from backend.rbac.authorization import has_permission
from backend.rbac.permissions import Perm
from backend.services import analytics_service, dashboard_service, insights_service

logger = logging.getLogger("safir.executive")


# --------------------------------------------------------------------------
# context assembly (permission-shaped)
# --------------------------------------------------------------------------
def build_executive_context(db: Session, *, user: User, year: int, month: int) -> dict:
    """Assemble the executive context, including only sections the user may see."""
    data = dashboard_service.build_dashboard(db, user=user, year=year, month=month)
    if data.get("__not_found__"):
        return {"__not_found__": True}

    kpis = data["kpis"]
    context: dict = {
        "scope": "executive",
        "period": {"year": year, "month": month},
        "kpis": {
            key: (float(value) if isinstance(value, Decimal) else value)
            for key, value in kpis.items()
        },
        "companies": [
            {
                "id": c.id,
                "code": c.code,
                "name_ar": c.name_ar,
                "name_en": c.name_en,
                "sector": c.sector,
                "health": c.health,
            }
            for c in data["companies"]
        ],
        "companies_missing_report": [
            {"id": c.id, "name_ar": c.name_ar, "name_en": c.name_en}
            for c in data["companies_missing_report"]
        ],
        "companies_requiring_attention": data["companies_requiring_attention"],
        "change_vs_previous": {
            key: (float(value) if isinstance(value, Decimal) else value)
            for key, value in data["change_vs_previous"].items()
        },
    }

    # Group analytics only enter the context for a user who may read them.
    if has_permission(user, Perm.ANALYTICS_HOLDING):
        try:
            overview = analytics_service.holding_overview(db, user=user, year=year, month=month)
            context["trend"] = overview["trend"]
            context["sectors"] = overview["sectors"]
            context["compliance"] = overview["compliance"]
            context["movers"] = overview["movers"]
            context["health_distribution"] = overview["health_distribution"]
        except Exception:  # noqa: BLE001 - analytics is optional enrichment
            logger.exception("holding overview unavailable for executive context")

    if has_permission(user, Perm.ANALYTICS_OPERATIONS):
        try:
            context["operations"] = analytics_service.operational_report(
                db, user=user, year=year, month=month
            )
        except Exception:  # noqa: BLE001
            logger.exception("operational report unavailable for executive context")

    if has_permission(user, Perm.ANALYTICS_COMPLIANCE):
        try:
            context["compliance_report"] = analytics_service.compliance_report(
                db, user=user, year=year, month=month
            )
        except Exception:  # noqa: BLE001
            logger.exception("compliance report unavailable for executive context")

    # The four data-driven insights are always in scope for a dashboard user.
    context["insights"] = insights_service.build_insights(
        db, user=user, year=year, month=month
    )
    return context


# --------------------------------------------------------------------------
# deterministic briefing (the fallback, and the shape contract)
# --------------------------------------------------------------------------
def _pct(value) -> str:
    if value is None:
        return "—"
    return f"{'+' if value >= 0 else '−'}{abs(value)}%"


def _briefing_from_context(context: dict) -> dict:
    """Compose a briefing purely from the context. Grounded by construction."""
    kpis = context.get("kpis", {})
    change = context.get("change_vs_previous", {})
    missing = context.get("companies_missing_report", [])
    attention = context.get("companies_requiring_attention", [])
    compliance = context.get("compliance", {})
    period = context.get("period", {})

    summary_ar = (
        f"لشهر {period.get('month')}/{period.get('year')}، بلغت إيرادات المجموعة "
        f"{kpis.get('total_revenue', 0):,.0f} ر.س، بصافي نتائج "
        f"{kpis.get('total_net_result', 0):,.0f} ر.س، واستلمنا تقارير "
        f"{kpis.get('reports_submitted', 0)} شركة من أصل "
        f"{kpis.get('companies_count', 0)}."
    )
    summary_en = (
        f"For {period.get('month')}/{period.get('year')}, group revenue reached "
        f"{kpis.get('total_revenue', 0):,.0f} SAR with a net result of "
        f"{kpis.get('total_net_result', 0):,.0f} SAR; "
        f"{kpis.get('reports_submitted', 0)} of {kpis.get('companies_count', 0)} "
        f"companies reported."
    )

    highlights: list[dict] = []
    if change.get("revenue_pct") is not None:
        up = change["revenue_pct"] >= 0
        highlights.append(
            {
                "key": "revenue_change",
                "tone": "up" if up else "down",
                "text_ar": f"الإيرادات {'ارتفعت' if up else 'انخفضت'} بنسبة {_pct(change['revenue_pct'])} مقارنةً بالشهر الماضي.",
                "text_en": f"Revenue {'grew' if up else 'fell'} {_pct(change['revenue_pct'])} versus last month.",
            }
        )
    if compliance:
        highlights.append(
            {
                "key": "compliance",
                "tone": "gold" if compliance.get("compliance_pct", 0) >= 80 else "warn",
                "text_ar": f"نسبة الالتزام بإرسال التقارير {compliance.get('compliance_pct', 0)}٪.",
                "text_en": f"Reporting compliance is {compliance.get('compliance_pct', 0)}%.",
            }
        )

    risks: list[dict] = []
    if attention:
        names = "، ".join(c.get("name_ar", "") for c in attention[:3])
        risks.append(
            {
                "key": "attention",
                "tone": "warn",
                "text_ar": f"{len(attention)} شركة تحتاج متابعة إدارية ({names}).",
                "text_en": f"{len(attention)} compan(ies) need management attention ({names}).",
            }
        )
    if missing:
        risks.append(
            {
                "key": "missing_reports",
                "tone": "risk",
                "text_ar": f"{len(missing)} شركة لم ترسل التقرير الشهري.",
                "text_en": f"{len(missing)} compan(ies) have not submitted their monthly report.",
            }
        )
    flagged = context.get("compliance_report", {}).get("flagged_financials", [])
    if flagged:
        risks.append(
            {
                "key": "flagged_financials",
                "tone": "risk",
                "text_ar": f"{len(flagged)} شركة لديها بيانات مالية موسومة تحتاج مراجعة.",
                "text_en": f"{len(flagged)} compan(ies) have flagged financial data to review.",
            }
        )

    opportunities = [
        {
            "key": insight.get("key"),
            "tone": insight.get("tone"),
            "text_ar": insight.get("detail_ar"),
            "text_en": insight.get("detail_en"),
        }
        for insight in context.get("insights", [])
        if insight.get("kind") == "opportunity" and insight.get("tone") == "gold"
    ]

    actions: list[dict] = []
    if missing:
        actions.append(
            {
                "key": "chase_reports",
                "text_ar": "متابعة الشركات المتأخرة عن إرسال التقارير الشهرية.",
                "text_en": "Follow up with companies that have not submitted their monthly reports.",
            }
        )
    if attention:
        actions.append(
            {
                "key": "review_attention",
                "text_ar": "جدولة مراجعة إدارية للشركات التي تحتاج متابعة.",
                "text_en": "Schedule a management review for the companies needing attention.",
            }
        )
    if flagged:
        actions.append(
            {
                "key": "review_financials",
                "text_ar": "إحالة البيانات المالية الموسومة إلى المحاسب.",
                "text_en": "Refer the flagged financial data to the accountant.",
            }
        )
    if not actions:
        actions.append(
            {
                "key": "steady_state",
                "text_ar": "لا توجد إجراءات عاجلة؛ استمرار المتابعة الدورية.",
                "text_en": "No urgent action; continue routine monitoring.",
            }
        )

    return {
        "summary_ar": summary_ar,
        "summary_en": summary_en,
        "highlights": highlights,
        "risks": risks,
        "opportunities": opportunities,
        "recommended_actions": actions,
    }


# --------------------------------------------------------------------------
# public entry point
# --------------------------------------------------------------------------
def executive_briefing(db: Session, *, user: User, year: int, month: int) -> dict:
    """A grounded executive briefing, degrading to a deterministic one."""
    context = build_executive_context(db, user=user, year=year, month=month)
    if context.get("__not_found__"):
        return {"__not_found__": True}

    base = _briefing_from_context(context)
    provider_name = "none"
    degraded = True

    try:
        provider = get_provider()
        provider_name = getattr(provider, "name", "none")
        if provider_name != "none":
            prompt = (
                "اكتب ملخصاً تنفيذياً موجزاً بالعربية بناءً على البيانات التالية فقط. "
                "لا تذكر أي رقم غير موجود فيها. "
                "Summarise the following data in concise executive Arabic; never "
                "state a figure that is not present.\n\n"
                "المطلوب: ملخص، أبرز النقاط، المخاطر، الفرص، والإجراءات المقترحة."
            )
            answer: AIAnswer = provider.answer(question=prompt, context=context)
            ungrounded = find_ungrounded(answer.text, context)
            if not ungrounded and answer.text.strip():
                base["summary_ar"] = answer.text.strip()
                base["summary_en"] = answer.text.strip()
                degraded = False
    except ProviderError:
        logger.warning("Executive briefing provider unavailable; using deterministic briefing.")
    except Exception:  # noqa: BLE001 - a provider must never break the page
        logger.exception("Executive briefing provider failed; using deterministic briefing.")

    return {
        "period": {"year": year, "month": month},
        "provider": provider_name,
        "degraded": degraded,
        "generated_from": "live_data",
        **base,
    }


__all__ = ["build_executive_context", "executive_briefing"]
