"""Advanced reporting and analytics.

Everything here is derived from rows that already exist; nothing is stored or
pre-computed, so a report can never drift from the underlying data. The service
is the analytical layer over the same scoped queries the dashboard uses, which
means company isolation is inherited rather than re-implemented:

* :func:`_scope` applies ``accessible_company_ids`` to every statement, so a
  company-scoped user gets analytics for exactly their companies.
* Holding-wide users (Owner, Finance) get the group view.

Four report families are produced, each gated by its own permission so the
Holding can grant "operations analytics" without granting "group financials":

1. :func:`holding_overview` -- monthly trend, sector mix, compliance, movers.
2. :func:`operational_report` -- request/approval throughput and bottlenecks.
3. :func:`compliance_report` -- document expiry exposure and report compliance.
4. :func:`investment_report` -- the opportunity/return view the Holding uses.

All money is ``Decimal`` end to end; conversion to float happens only at the
JSON boundary, in the schema layer.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.models.documents import Document
from backend.db.models.enums import (
    DocumentStatus,
    FinancialReviewStatus,
    ReportStatus,
    SupportStatus,
    TaskStatus,
)
from backend.db.models.identity import Company, User
from backend.db.models.report import MonthlyReport, MonthlyReportFinancialReview
from backend.db.models.submissions import FormSubmission
from backend.db.models.support import SupportRequest
from backend.db.models.workflows import ApprovalEvent, ApprovalTask
from backend.rbac.authorization import accessible_company_ids, require_permission
from backend.rbac.permissions import Perm

# How many trailing months the trend report covers.
TREND_MONTHS = 12


def _scope(stmt, column, user: User):
    allowed = accessible_company_ids(user)
    if allowed is None:
        return stmt
    if not allowed:
        return stmt.where(False)
    return stmt.where(column.in_(allowed))


def _money(value) -> Decimal:
    return Decimal(str(value or 0))


# --------------------------------------------------------------------------
# 1. holding overview
# --------------------------------------------------------------------------
def holding_overview(db: Session, *, user: User, year: int, month: int) -> dict:
    """Group trend, sector mix, reporting compliance and month-over-month movers."""
    require_permission(user, Perm.ANALYTICS_HOLDING)

    return {
        "period": {"year": year, "month": month},
        "trend": _monthly_trend(db, user=user, year=year, month=month),
        "sectors": _sector_mix(db, user=user, year=year, month=month),
        "compliance": _reporting_compliance(db, user=user, year=year, month=month),
        "movers": _movers(db, user=user, year=year, month=month),
        "health_distribution": _health_distribution(db, user=user),
    }


def _monthly_trend(db: Session, *, user: User, year: int, month: int) -> list[dict]:
    """The trailing ``TREND_MONTHS`` months of revenue / expenses / net.

    Months with no data are returned as zero rather than omitted, so the chart
    has a continuous x-axis and a gap is visible as a gap.
    """
    start_key = year * 12 + month - (TREND_MONTHS - 1)
    start_year, start_month = divmod(start_key - 1, 12)
    start_month += 1

    revenue = func.coalesce(
        MonthlyReportFinancialReview.verified_revenue, MonthlyReport.revenue
    )
    expenses = func.coalesce(
        MonthlyReportFinancialReview.verified_expenses, MonthlyReport.expenses
    )
    net = func.coalesce(
        MonthlyReportFinancialReview.verified_net_result, MonthlyReport.net_result
    )
    stmt = (
        select(
            MonthlyReport.period_year,
            MonthlyReport.period_month,
            func.coalesce(func.sum(revenue), 0),
            func.coalesce(func.sum(expenses), 0),
            func.coalesce(func.sum(net), 0),
            func.count(func.distinct(MonthlyReport.company_id)),
        )
        .select_from(MonthlyReport)
        .outerjoin(
            MonthlyReportFinancialReview,
            (MonthlyReportFinancialReview.report_id == MonthlyReport.id)
            & (
                MonthlyReportFinancialReview.status
                == FinancialReviewStatus.APPROVED.value
            ),
        )
        .where(
            MonthlyReport.status != ReportStatus.DRAFT.value,
            (MonthlyReport.period_year > start_year)
            | (
                (MonthlyReport.period_year == start_year)
                & (MonthlyReport.period_month >= start_month)
            ),
        )
        .group_by(MonthlyReport.period_year, MonthlyReport.period_month)
    )
    stmt = _scope(stmt, MonthlyReport.company_id, user)
    rows = {
        (y, m): (rev, exp, net_result, companies)
        for y, m, rev, exp, net_result, companies in db.execute(stmt)
    }

    series = []
    for offset in range(TREND_MONTHS):
        key = start_key + offset
        y, m = divmod(key - 1, 12)
        m += 1
        rev, exp, net_result, companies = rows.get((y, m), (0, 0, 0, 0))
        series.append(
            {
                "year": y,
                "month": m,
                "revenue": float(_money(rev)),
                "expenses": float(_money(exp)),
                "net_result": float(_money(net_result)),
                "companies_reporting": int(companies),
            }
        )
    return series


def _sector_mix(db: Session, *, user: User, year: int, month: int) -> list[dict]:
    stmt = (
        select(
            Company.sector,
            func.count(func.distinct(Company.id)),
            func.coalesce(func.sum(MonthlyReport.revenue), 0),
            func.coalesce(func.sum(MonthlyReport.net_result), 0),
        )
        .select_from(Company)
        .outerjoin(
            MonthlyReport,
            (MonthlyReport.company_id == Company.id)
            & (MonthlyReport.period_year == year)
            & (MonthlyReport.period_month == month)
            & (MonthlyReport.status != ReportStatus.DRAFT.value),
        )
        .group_by(Company.sector)
        .order_by(func.coalesce(func.sum(MonthlyReport.revenue), 0).desc())
    )
    stmt = _scope(stmt, Company.id, user)
    return [
        {
            "sector": sector or "—",
            "companies": int(count),
            "revenue": float(_money(rev)),
            "net_result": float(_money(net)),
        }
        for sector, count, rev, net in db.execute(stmt)
    ]


def _reporting_compliance(db: Session, *, user: User, year: int, month: int) -> dict:
    total = int(
        db.execute(_scope(select(func.count(Company.id)), Company.id, user)).scalar_one()
    )
    reported = int(
        db.execute(
            _scope(
                select(func.count(func.distinct(MonthlyReport.company_id))).where(
                    MonthlyReport.period_year == year,
                    MonthlyReport.period_month == month,
                    MonthlyReport.status != ReportStatus.DRAFT.value,
                ),
                MonthlyReport.company_id,
                user,
            )
        ).scalar_one()
    )
    reviewed = int(
        db.execute(
            _scope(
                select(func.count(func.distinct(MonthlyReport.company_id))).where(
                    MonthlyReport.period_year == year,
                    MonthlyReport.period_month == month,
                    MonthlyReport.status == ReportStatus.REVIEWED.value,
                ),
                MonthlyReport.company_id,
                user,
            )
        ).scalar_one()
    )
    return {
        "companies_total": total,
        "companies_reported": reported,
        "companies_reviewed": reviewed,
        "companies_missing": max(total - reported, 0),
        "compliance_pct": round(reported / total * 100, 1) if total else 0.0,
    }


def _movers(db: Session, *, user: User, year: int, month: int) -> dict:
    """Best and worst month-over-month revenue movers, with a real baseline."""
    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    current = _company_revenue(db, user=user, year=year, month=month)
    previous = _company_revenue(db, user=user, year=prev_year, month=prev_month)

    movers = []
    for company_id, revenue in current.items():
        prior = previous.get(company_id)
        if prior is None or prior == 0:
            continue
        change = round(float((revenue - prior) / prior * 100), 1)
        movers.append(
            {
                "company_id": company_id,
                "revenue": float(revenue),
                "previous_revenue": float(prior),
                "change_pct": change,
            }
        )
    names = _company_names(db, user=user, ids=[m["company_id"] for m in movers])
    for mover in movers:
        mover.update(names.get(mover["company_id"], {}))
    movers.sort(key=lambda m: m["change_pct"], reverse=True)
    return {"top": movers[:5], "bottom": list(reversed(movers[-5:])) if movers else []}


def _company_revenue(db: Session, *, user: User, year: int, month: int) -> dict[int, Decimal]:
    stmt = (
        select(MonthlyReport.company_id, func.coalesce(func.sum(MonthlyReport.revenue), 0))
        .where(
            MonthlyReport.period_year == year,
            MonthlyReport.period_month == month,
            MonthlyReport.status != ReportStatus.DRAFT.value,
        )
        .group_by(MonthlyReport.company_id)
    )
    stmt = _scope(stmt, MonthlyReport.company_id, user)
    return {cid: _money(rev) for cid, rev in db.execute(stmt)}


def _company_names(db: Session, *, user: User, ids: list[int]) -> dict[int, dict]:
    if not ids:
        return {}
    stmt = select(Company.id, Company.name_ar, Company.name_en, Company.code).where(
        Company.id.in_(ids)
    )
    stmt = _scope(stmt, Company.id, user)
    return {
        cid: {"name_ar": ar, "name_en": en, "code": code}
        for cid, ar, en, code in db.execute(stmt)
    }


def _health_distribution(db: Session, *, user: User) -> list[dict]:
    stmt = (
        select(Company.health, func.count(Company.id))
        .group_by(Company.health)
    )
    stmt = _scope(stmt, Company.id, user)
    return [{"health": health, "companies": int(count)} for health, count in db.execute(stmt)]


# --------------------------------------------------------------------------
# 2. operational report
# --------------------------------------------------------------------------
def operational_report(db: Session, *, user: User, year: int, month: int) -> dict:
    require_permission(user, Perm.ANALYTICS_OPERATIONS)
    return {
        "period": {"year": year, "month": month},
        "requests_by_status": _submissions_by_status(db, user=user),
        "requests_by_company": _submissions_by_company(db, user=user),
        "approval_bottlenecks": _approval_bottlenecks(db, user=user),
        "approval_cycle": _approval_cycle(db, user=user, year=year, month=month),
        "support_by_category": _support_by_category(db, user=user),
        "support_throughput": _support_throughput(db, user=user),
    }


def _submissions_by_status(db: Session, *, user: User) -> list[dict]:
    stmt = select(FormSubmission.status, func.count(FormSubmission.id)).group_by(
        FormSubmission.status
    )
    stmt = _scope(stmt, FormSubmission.company_id, user)
    return [{"status": status, "count": int(count)} for status, count in db.execute(stmt)]


def _submissions_by_company(db: Session, *, user: User) -> list[dict]:
    stmt = (
        select(FormSubmission.company_id, func.count(FormSubmission.id))
        .group_by(FormSubmission.company_id)
    )
    stmt = _scope(stmt, FormSubmission.company_id, user)
    rows = list(db.execute(stmt))
    names = _company_names(db, user=user, ids=[cid for cid, _ in rows])
    return [
        {
            "company_id": cid,
            "count": int(count),
            **names.get(cid, {}),
        }
        for cid, count in rows
    ]


def _approval_bottlenecks(db: Session, *, user: User) -> list[dict]:
    """Pending approval tasks grouped by step -- where requests are waiting."""
    from backend.db.models.workflows import WorkflowInstance, WorkflowStep

    stmt = (
        select(
            ApprovalTask.step_id,
            WorkflowStep.name_ar,
            WorkflowStep.name_en,
            func.count(ApprovalTask.id),
        )
        .select_from(ApprovalTask)
        .join(WorkflowStep, WorkflowStep.id == ApprovalTask.step_id)
        .join(WorkflowInstance, WorkflowInstance.id == ApprovalTask.instance_id)
        .where(ApprovalTask.status == TaskStatus.PENDING.value)
        .group_by(ApprovalTask.step_id, WorkflowStep.name_ar, WorkflowStep.name_en)
        .order_by(func.count(ApprovalTask.id).desc())
    )
    # Scope by the instance's company so a scoped user only counts their own.
    stmt = _scope(stmt, WorkflowInstance.company_id, user)
    return [
        {"step_id": sid, "name_ar": ar, "name_en": en, "pending": int(count)}
        for sid, ar, en, count in db.execute(stmt)
    ]


def _approval_cycle(db: Session, *, user: User, year: int, month: int) -> dict:
    """Average time from submission to a terminal approval decision.

    Uses :class:`ApprovalEvent` timestamps; only events whose submission is in
    scope are considered.
    """
    from backend.db.models.workflows import WorkflowInstance

    allowed = accessible_company_ids(user)
    instances_stmt = select(WorkflowInstance)
    if allowed is not None:
        if not allowed:
            return {"completed": 0, "average_hours": None}
        instances_stmt = instances_stmt.where(WorkflowInstance.company_id.in_(allowed))
    instances = {i.id: i for i in db.execute(instances_stmt).scalars()}

    events = list(
        db.execute(
            select(ApprovalEvent)
            .where(ApprovalEvent.action == "completed")
            .order_by(ApprovalEvent.id)
        ).scalars()
    )
    durations: list[float] = []
    for event in events:
        instance = instances.get(event.instance_id)
        if instance is None or instance.started_at is None or event.created_at is None:
            continue
        durations.append(
            (event.created_at - instance.started_at).total_seconds() / 3600.0
        )
    if not durations:
        return {"completed": 0, "average_hours": None}
    return {
        "completed": len(durations),
        "average_hours": round(sum(durations) / len(durations), 1),
        "fastest_hours": round(min(durations), 1),
        "slowest_hours": round(max(durations), 1),
    }


def _support_by_category(db: Session, *, user: User) -> list[dict]:
    stmt = (
        select(SupportRequest.category, SupportRequest.status, func.count(SupportRequest.id))
        .group_by(SupportRequest.category, SupportRequest.status)
    )
    stmt = _scope(stmt, SupportRequest.company_id, user)
    buckets: dict[str, dict] = {}
    for category, status, count in db.execute(stmt):
        row = buckets.setdefault(category, {"category": category, "total": 0, "open": 0, "closed": 0})
        row["total"] += int(count)
        if status in (SupportStatus.NEW.value, SupportStatus.IN_PROGRESS.value):
            row["open"] += int(count)
        if status == SupportStatus.CLOSED.value:
            row["closed"] += int(count)
    return sorted(buckets.values(), key=lambda r: r["total"], reverse=True)


def _support_throughput(db: Session, *, user: User) -> dict:
    """Average hours to close a support request (closed_at - created_at)."""
    stmt = select(SupportRequest.created_at, SupportRequest.closed_at).where(
        SupportRequest.closed_at.isnot(None)
    )
    stmt = _scope(stmt, SupportRequest.company_id, user)
    durations = [
        (closed - created).total_seconds() / 3600.0
        for created, closed in db.execute(stmt)
        if created and closed
    ]
    if not durations:
        return {"closed_requests": 0, "average_hours": None}
    return {
        "closed_requests": len(durations),
        "average_hours": round(sum(durations) / len(durations), 1),
    }


# --------------------------------------------------------------------------
# 3. compliance report
# --------------------------------------------------------------------------
def compliance_report(db: Session, *, user: User, year: int, month: int) -> dict:
    require_permission(user, Perm.ANALYTICS_COMPLIANCE)
    return {
        "period": {"year": year, "month": month},
        "documents": _document_exposure(db, user=user),
        "documents_by_category": _documents_by_category(db, user=user),
        "reporting": _reporting_compliance(db, user=user, year=year, month=month),
        "flagged_financials": _flagged_financials(db, user=user, year=year, month=month),
    }


def _document_exposure(db: Session, *, user: User) -> dict:
    from backend.db.models.documents import EXPIRING_SOON_DAYS

    stmt = select(Document).where(Document.status == DocumentStatus.ACTIVE.value)
    stmt = _scope(stmt, Document.company_id, user)
    counts = {"expired": 0, "expiring_soon": 0, "valid": 0, "none": 0}
    for document in db.execute(stmt).scalars():
        counts[document.expiry_state] = counts.get(document.expiry_state, 0) + 1
    counts["expiring_soon_days"] = EXPIRING_SOON_DAYS
    counts["total"] = sum(
        counts[k] for k in ("expired", "expiring_soon", "valid", "none")
    )
    return counts


def _documents_by_category(db: Session, *, user: User) -> list[dict]:
    from backend.db.models.documents import DocumentCategory

    stmt = (
        select(
            DocumentCategory.name_ar,
            DocumentCategory.name_en,
            func.count(Document.id),
        )
        .select_from(Document)
        .join(DocumentCategory, DocumentCategory.id == Document.category_id)
        .where(Document.status == DocumentStatus.ACTIVE.value)
        .group_by(DocumentCategory.name_ar, DocumentCategory.name_en)
        .order_by(func.count(Document.id).desc())
    )
    stmt = _scope(stmt, Document.company_id, user)
    return [
        {"name_ar": ar, "name_en": en, "count": int(count)}
        for ar, en, count in db.execute(stmt)
    ]


def _flagged_financials(db: Session, *, user: User, year: int, month: int) -> list[dict]:
    stmt = (
        select(MonthlyReport.company_id, func.count(MonthlyReportFinancialReview.id))
        .select_from(MonthlyReportFinancialReview)
        .join(MonthlyReport, MonthlyReport.id == MonthlyReportFinancialReview.report_id)
        .where(
            MonthlyReport.period_year == year,
            MonthlyReport.period_month == month,
            MonthlyReportFinancialReview.status == FinancialReviewStatus.FLAGGED.value,
        )
        .group_by(MonthlyReport.company_id)
    )
    stmt = _scope(stmt, MonthlyReport.company_id, user)
    rows = list(db.execute(stmt))
    names = _company_names(db, user=user, ids=[cid for cid, _ in rows])
    return [
        {"company_id": cid, "flagged_reviews": int(count), **names.get(cid, {})}
        for cid, count in rows
    ]


# --------------------------------------------------------------------------
# 4. investment report
# --------------------------------------------------------------------------
def investment_report(db: Session, *, user: User, year: int, month: int) -> dict:
    """The investment lens: profitability, efficiency and reported opportunities."""
    require_permission(user, Perm.ANALYTICS_HOLDING)

    stmt = (
        select(
            Company.id,
            Company.name_ar,
            Company.name_en,
            Company.code,
            Company.sector,
            Company.health,
            MonthlyReport.revenue,
            MonthlyReport.expenses,
            MonthlyReport.net_result,
            MonthlyReport.outstanding_receivables,
            MonthlyReport.new_opportunities,
            MonthlyReport.new_customers,
        )
        .select_from(Company)
        .outerjoin(
            MonthlyReport,
            (MonthlyReport.company_id == Company.id)
            & (MonthlyReport.period_year == year)
            & (MonthlyReport.period_month == month)
            & (MonthlyReport.status != ReportStatus.DRAFT.value),
        )
        .order_by(Company.name_en)
    )
    stmt = _scope(stmt, Company.id, user)
    rows = list(db.execute(stmt))

    companies = []
    for (
        cid, ar, en, code, sector, health, revenue, expenses, net, receivables, opps, customers
    ) in rows:
        revenue = _money(revenue)
        net = _money(net)
        margin = round(float(net / revenue * 100), 1) if revenue else None
        companies.append(
            {
                "company_id": cid,
                "name_ar": ar,
                "name_en": en,
                "code": code,
                "sector": sector,
                "health": health,
                "revenue": float(revenue),
                "net_result": float(net),
                "margin_pct": margin,
                "outstanding_receivables": float(_money(receivables)),
                "has_opportunity": bool((opps or "").strip()),
                "has_new_customers": bool((customers or "").strip()),
            }
        )

    opportunities = [c for c in companies if c["has_opportunity"]]
    return {
        "period": {"year": year, "month": month},
        "companies": companies,
        "opportunities_reported": len(opportunities),
        "opportunity_companies": opportunities,
        "portfolio_net": float(sum(Decimal(str(c["net_result"])) for c in companies)),
        "portfolio_revenue": float(sum(Decimal(str(c["revenue"])) for c in companies)),
        "average_margin_pct": _average(
            [c["margin_pct"] for c in companies if c["margin_pct"] is not None]
        ),
    }


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 1)


__all__ = [
    "TREND_MONTHS",
    "compliance_report",
    "holding_overview",
    "investment_report",
    "operational_report",
]
