"""Data-driven AI Insights.

Four executive observations, each computed from the database rather than
authored. When the underlying data is insufficient the service returns an
explicit "no insight available yet" entry instead of inventing one -- a Holding
platform must never present a fabricated observation as fact.

The four required insights:

1. Revenue change versus the previous month.
2. A company requiring management attention.
3. A potential business opportunity (from companies reporting new opportunities).
4. Financial data requiring review (pending accountant verification / missing
   reports / flagged reviews).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models.enums import FinancialReviewStatus
from backend.db.models.identity import Company, User
from backend.db.models.report import MonthlyReport, MonthlyReportFinancialReview
from backend.rbac.authorization import accessible_company_ids
from backend.services import dashboard_service

NO_INSIGHT_AR = "لا توجد رؤية متاحة بعد."


def _scoped(stmt, column, user: User):
    allowed = accessible_company_ids(user)
    if allowed is None:
        return stmt
    if not allowed:
        return stmt.where(False)
    return stmt.where(column.in_(allowed))


def _insight(
    *, key: str, kind: str, title_ar: str, title_en: str, detail_ar: str, detail_en: str,
    tone: str, metric: str | None = None,
) -> dict:
    return {
        "key": key,
        "kind": kind,
        "title_ar": title_ar,
        "title_en": title_en,
        "detail_ar": detail_ar,
        "detail_en": detail_en,
        "tone": tone,
        "metric": metric,
    }


def _revenue_change_insight(change: dict, year: int, month: int) -> dict:
    pct = change.get("revenue_pct")
    if pct is None:
        return _insight(
            key="revenue_change",
            kind="revenue",
            title_ar="تغيّر الإيرادات مقارنةً بالشهر الماضي",
            title_en="Revenue change vs. last month",
            detail_ar=NO_INSIGHT_AR,
            detail_en="No insight available yet.",
            tone="neutral",
        )
    up = pct >= 0
    return _insight(
        key="revenue_change",
        kind="revenue",
        title_ar=("ارتفاع الإيرادات مقارنةً بالشهر الماضي"
                  if up else "انخفاض الإيرادات مقارنةً بالشهر الماضي"),
        title_en=("Revenue increased vs. last month"
                  if up else "Revenue decreased vs. last month"),
        detail_ar=f"إجمالي إيرادات المجموعة {'+' if up else '−'}{abs(pct)}٪ "
                  f"لشهر {month}/{year}.",
        detail_en=f"Group revenue {'+' if up else '−'}{abs(pct)}% "
                  f"for {month}/{year}.",
        tone="up" if up else "down",
        metric=f"{'+' if up else '−'}{abs(pct)}%",
    )


def _attention_insight(attention: list[dict]) -> dict:
    if not attention:
        return _insight(
            key="attention",
            kind="attention",
            title_ar="شركات تحتاج إلى اهتمام إداري",
            title_en="Companies needing management attention",
            detail_ar="لا توجد شركات تحتاج متابعة هذا الشهر.",
            detail_en="No companies require attention this month.",
            tone="neutral",
        )
    first = attention[0]
    detail_ar = first.get("reason") or "مؤشر الأداء يحتاج مراجعة."
    detail_en = "Performance indicator needs review."
    if len(attention) > 1:
        detail_ar += f" (و{len(attention) - 1} شركة أخرى)"
        detail_en += f" (and {len(attention) - 1} more)"
    return _insight(
        key="attention",
        kind="attention",
        title_ar="شركة تحتاج إلى اهتمام إداري",
        title_en="One company needs management attention",
        detail_ar=f"{first['name_ar']}: {detail_ar}",
        detail_en=f"{first.get('name_en') or first['name_ar']}: {detail_en}",
        tone="warn",
        metric=str(len(attention)),
    )


def _opportunity_insight(db: Session, user: User, year: int, month: int) -> dict:
    """Companies that explicitly reported a new opportunity this period."""
    stmt = (
        select(Company, MonthlyReport)
        .select_from(MonthlyReport)
        .join(Company, Company.id == MonthlyReport.company_id)
        .where(
            MonthlyReport.period_year == year,
            MonthlyReport.period_month == month,
            MonthlyReport.new_opportunities.isnot(None),
        )
        .order_by(Company.name_en)
    )
    stmt = _scoped(stmt, MonthlyReport.company_id, user)
    rows = list(db.execute(stmt).all())
    rows = [(c, r) for c, r in rows if (r.new_opportunities or "").strip()]

    if not rows:
        return _insight(
            key="opportunity",
            kind="opportunity",
            title_ar="فرص أعمال محتملة",
            title_en="Potential business opportunities",
            detail_ar=NO_INSIGHT_AR,
            detail_en="No insight available yet.",
            tone="neutral",
        )
    company, report = rows[0]
    extra = f" (+{len(rows) - 1})" if len(rows) > 1 else ""
    return _insight(
        key="opportunity",
        kind="opportunity",
        title_ar="تم رصد فرصة أعمال محتملة",
        title_en="A potential business opportunity was detected",
        detail_ar=f"{company.name_ar}: {report.new_opportunities.strip()}{extra}",
        detail_en=f"{company.name_en or company.name_ar} reported a new opportunity.",
        tone="gold",
        metric=str(len(rows)),
    )


def _financial_review_insight(
    db: Session, user: User, year: int, month: int, kpis: dict
) -> dict:
    """Anything the Holding should verify: pending reviews, flags, missing data."""
    reasons_ar: list[str] = []
    reasons_en: list[str] = []

    pending = kpis.get("pending_financial_reviews", 0)
    if pending:
        reasons_ar.append(f"{pending} تقريراً بانتظار المراجعة المالية")
        reasons_en.append(f"{pending} report(s) awaiting financial review")

    flagged_stmt = (
        select(MonthlyReportFinancialReview)
        .join(MonthlyReport, MonthlyReport.id == MonthlyReportFinancialReview.report_id)
        .where(
            MonthlyReport.period_year == year,
            MonthlyReport.period_month == month,
            MonthlyReportFinancialReview.status == FinancialReviewStatus.FLAGGED.value,
        )
    )
    flagged_stmt = _scoped(flagged_stmt, MonthlyReport.company_id, user)
    flagged = list(db.execute(flagged_stmt).scalars())
    if flagged:
        reasons_ar.append(f"{len(flagged)} تقريراً تم وسم بياناته المالية")
        reasons_en.append(f"{len(flagged)} report(s) flagged")

    missing = kpis.get("reports_missing", 0)
    if missing:
        reasons_ar.append(f"{missing} شركة لم ترسل التقرير الشهري")
        reasons_en.append(f"{missing} company(ies) missing a report")

    if not reasons_ar:
        return _insight(
            key="financial_review",
            kind="financial",
            title_ar="البيانات المالية تحتاج إلى مراجعة",
            title_en="Financial data needs review",
            detail_ar="لا توجد بيانات مالية بانتظار المراجعة.",
            detail_en="No financial data is awaiting review.",
            tone="neutral",
        )
    return _insight(
        key="financial_review",
        kind="financial",
        title_ar="البيانات المالية تحتاج إلى مراجعة",
        title_en="Financial data needs review",
        detail_ar="؛ ".join(reasons_ar) + ".",
        detail_en="; ".join(reasons_en) + ".",
        tone="risk",
        metric=str(pending + len(flagged) + missing),
    )


def build_insights(db: Session, *, user: User, year: int, month: int) -> list[dict]:
    """The four executive insights for the period, computed from real data."""
    data = dashboard_service.build_dashboard(db, user=user, year=year, month=month)
    if data.get("__not_found__"):
        return []
    kpis = data["kpis"]
    return [
        _revenue_change_insight(data["change_vs_previous"], year, month),
        _attention_insight(data["companies_requiring_attention"]),
        _opportunity_insight(db, user, year, month),
        _financial_review_insight(db, user, year, month, kpis),
    ]
