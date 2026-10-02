"""Dashboard aggregation service.

Every KPI is computed from the database through company-scoped queries. There
are no hardcoded or demo figures in this path: if the database is empty, the
dashboard returns zeros, which is the correct answer for an empty Holding.

Financial totals prefer the accountant's *verified* figures when a review
exists, and fall back to the submitted figures otherwise. This is what makes
"verified financial data feeds the Holding dashboard" true rather than a claim.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.models.enums import CompanyHealth, FinancialReviewStatus, ReportStatus
from backend.db.models.identity import Company, User
from backend.db.models.report import MonthlyReport, MonthlyReportFinancialReview
from backend.rbac.authorization import accessible_company_ids
from backend.repositories.scoped import (
    CompanyRepository,
    FinancialReviewRepository,
    MonthlyReportRepository,
    SupportRequestRepository,
)


def _scoped(stmt, column, user: User):
    allowed = accessible_company_ids(user)
    if allowed is None:
        return stmt
    if not allowed:
        return stmt.where(False)
    return stmt.where(column.in_(allowed))


def _financial_totals(db: Session, user: User, year: int, month: int) -> tuple[Decimal, Decimal, Decimal]:
    """Sum revenue/expenses/net result for the period, preferring verified data.

    Only an *approved* verification overrides the submitted figures. A flagged
    review means the numbers were not accepted, so the submitted values stand
    (which is also what the dashboard would show with no review at all).
    """
    revenue_expr = func.coalesce(
        MonthlyReportFinancialReview.verified_revenue, MonthlyReport.revenue
    )
    expenses_expr = func.coalesce(
        MonthlyReportFinancialReview.verified_expenses, MonthlyReport.expenses
    )
    net_expr = func.coalesce(
        MonthlyReportFinancialReview.verified_net_result, MonthlyReport.net_result
    )

    stmt = (
        select(
            func.coalesce(func.sum(revenue_expr), 0),
            func.coalesce(func.sum(expenses_expr), 0),
            func.coalesce(func.sum(net_expr), 0),
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
            MonthlyReport.period_year == year,
            MonthlyReport.period_month == month,
            # Drafts are not part of group performance until submitted.
            MonthlyReport.status != ReportStatus.DRAFT.value,
        )
    )
    stmt = _scoped(stmt, MonthlyReport.company_id, user)
    row = db.execute(stmt).one()
    return (
        Decimal(row[0] or 0),
        Decimal(row[1] or 0),
        Decimal(row[2] or 0),
    )


def _attention_rows(db: Session, user: User, year: int, month: int):
    """Companies flagged on health, or that reported major problems this period.

    Returns the underlying rows rather than just a count, so the dashboard and
    the AI can name the companies instead of only counting them.
    """
    stmt = (
        select(Company, MonthlyReport)
        .select_from(Company)
        .outerjoin(
            MonthlyReport,
            (MonthlyReport.company_id == Company.id)
            & (MonthlyReport.period_year == year)
            & (MonthlyReport.period_month == month),
        )
        .where(
            (Company.health.in_([CompanyHealth.ATTENTION.value, CompanyHealth.WATCH.value]))
            | (MonthlyReport.major_problems.isnot(None))
        )
    )
    stmt = _scoped(stmt, Company.id, user)
    return list(db.execute(stmt).all())


def attention_payload(db: Session, user: User, year: int, month: int) -> list[dict]:
    """Companies needing management attention, with the stated reason."""
    rows = _attention_rows(db, user, year, month)
    payload = []
    for company, report in rows:
        reason = None
        if report is not None and report.major_problems:
            reason = report.major_problems
        elif company.health == CompanyHealth.ATTENTION.value:
            reason = "مؤشر صحة الشركة منخفض"
        elif company.health == CompanyHealth.WATCH.value:
            reason = "الشركة تحت المراقبة"
        payload.append(
            {
                "id": company.id,
                "code": company.code,
                "name_ar": company.name_ar,
                "name_en": company.name_en,
                "health": company.health,
                "reason": reason,
                "support_required": report.support_required if report else None,
            }
        )
    return payload


def build_dashboard(
    db: Session,
    *,
    user: User,
    year: int,
    month: int,
    company_id: int | None = None,
) -> dict:
    """Assemble the dashboard payload for the caller's permitted scope."""
    companies_repo = CompanyRepository(db)
    reports_repo = MonthlyReportRepository(db)
    support_repo = SupportRequestRepository(db)
    review_repo = FinancialReviewRepository(db)

    if company_id is not None:
        # Company scope: the repository silently returns None when the caller
        # is not allowed to see it, which the caller turns into a 404.
        company = companies_repo.get_for_user(user, company_id)
        if company is None:
            return {"__not_found__": True}

    total_revenue, total_expenses, total_net = _financial_totals(db, user, year, month)

    submitted = reports_repo.status_counts(user, year, month)
    reports_submitted = sum(
        count
        for status, count in submitted.items()
        if status != ReportStatus.DRAFT.value
    )

    if company_id is not None:
        companies = [companies_repo.get_for_user(user, company_id)]
        companies = [c for c in companies if c is not None]
    else:
        companies = companies_repo.list_for_user(user)

    missing = reports_repo.companies_missing_report(user, year, month)
    attention = attention_payload(db, user, year, month)

    kpis = {
        "companies_count": companies_repo.count_for_user(user) if company_id is None else 1,
        "reports_submitted": reports_submitted,
        "reports_missing": len(missing),
        "total_revenue": total_revenue,
        "total_expenses": total_expenses,
        "total_net_result": total_net,
        "companies_requiring_attention": len(attention),
        "open_support_requests": support_repo.open_count(user),
        "pending_financial_reviews": review_repo.pending_count(user),
    }

    return {
        "scope": "company" if company_id is not None else "holding",
        "company_id": company_id,
        "period_year": year,
        "period_month": month,
        "kpis": kpis,
        "companies": companies,
        "companies_missing_report": missing,
        "companies_requiring_attention": attention,
    }
