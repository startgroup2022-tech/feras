"""Monthly report and accountant-review services.

Business rules enforced here (not in the UI):

* A report belongs to exactly one company and one month.
* Only a draft can be edited or deleted; once submitted it is locked.
* Submitting moves ``draft`` -> ``submitted`` and stamps ``submitted_at``.
* The accountant records verified figures in a separate review row and moves
  the report to ``under_review`` or ``reviewed``. The originally submitted
  numbers are never overwritten, so an audit always shows both.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from backend.core.errors import ConflictError, NotFoundError, ValidationError
from backend.db.base import utcnow
from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import FinancialReviewStatus, ReportStatus
from backend.db.models.identity import User
from backend.db.models.report import MonthlyReport, MonthlyReportFinancialReview
from backend.rbac.authorization import require_company_access, require_permission
from backend.rbac.permissions import Perm
from backend.repositories.scoped import MonthlyReportRepository
from backend.services import audit_service


def create_report(
    db: Session,
    *,
    user: User,
    company_id: int,
    period_year: int,
    period_month: int,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> MonthlyReport:
    require_permission(user, Perm.REPORT_CREATE)
    # Company isolation: the caller must be able to *write* this company.
    require_company_access(user, company_id, write=True)

    repo = MonthlyReportRepository(db)
    if repo.get_by_company_period(company_id, period_year, period_month) is not None:
        raise ConflictError("A report already exists for this company and month.")

    report = MonthlyReport(
        company_id=company_id,
        period_year=period_year,
        period_month=period_month,
        status=ReportStatus.DRAFT.value,
        **payload,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    audit_service.record(
        db,
        action=AuditAction.REPORT_CREATED,
        actor_user_id=user.id,
        entity_type="monthly_report",
        entity_id=report.id,
        company_id=company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"period": f"{period_year}-{period_month:02d}"},
    )
    return report


def update_report(
    db: Session,
    *,
    user: User,
    report_id: int,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> MonthlyReport:
    require_permission(user, Perm.REPORT_UPDATE)
    report = _get_scoped_or_404(db, user, report_id)
    require_company_access(user, report.company_id, write=True)

    if report.status != ReportStatus.DRAFT.value:
        raise ConflictError("Only draft reports can be edited.")

    for key, value in payload.items():
        setattr(report, key, value)
    db.add(report)
    db.commit()
    db.refresh(report)

    audit_service.record(
        db,
        action=AuditAction.REPORT_UPDATED,
        actor_user_id=user.id,
        entity_type="monthly_report",
        entity_id=report.id,
        company_id=report.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"fields": sorted(payload.keys())},
    )
    return report


def submit_report(
    db: Session,
    *,
    user: User,
    report_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> MonthlyReport:
    require_permission(user, Perm.REPORT_SUBMIT)
    report = _get_scoped_or_404(db, user, report_id)
    require_company_access(user, report.company_id, write=True)

    if report.status != ReportStatus.DRAFT.value:
        raise ConflictError("Only a draft report can be submitted.")
    if report.revenue is None or report.expenses is None:
        raise ValidationError("Revenue and expenses are required before submitting.")

    report.status = ReportStatus.SUBMITTED.value
    report.submitted_at = utcnow()
    report.submitted_by_id = user.id
    db.add(report)
    db.commit()
    db.refresh(report)

    audit_service.record(
        db,
        action=AuditAction.REPORT_SUBMITTED,
        actor_user_id=user.id,
        entity_type="monthly_report",
        entity_id=report.id,
        company_id=report.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"period": f"{report.period_year}-{report.period_month:02d}"},
    )
    return report


def review_financially(
    db: Session,
    *,
    user: User,
    report_id: int,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> MonthlyReportFinancialReview:
    """Accountant verification of a submitted report."""
    require_permission(user, Perm.FINANCIAL_REVIEW_WRITE)
    report = _get_scoped_or_404(db, user, report_id)
    require_company_access(user, report.company_id)

    if report.status == ReportStatus.DRAFT.value:
        raise ConflictError("A draft report cannot be financially reviewed.")

    accurate = bool(payload.get("is_financially_accurate"))
    review = db.query(MonthlyReportFinancialReview).filter(
        MonthlyReportFinancialReview.report_id == report.id
    ).one_or_none()

    if review is None:
        review = MonthlyReportFinancialReview(
            report_id=report.id, reviewer_id=user.id
        )

    review.reviewer_id = user.id
    review.status = (
        FinancialReviewStatus.APPROVED.value
        if accurate
        else FinancialReviewStatus.FLAGGED.value
    )
    review.is_financially_accurate = accurate
    review.financial_notes = payload.get("financial_notes")
    review.flagged_reason = payload.get("flagged_reason")

    # Default verified figures to the submitted ones unless corrected.
    review.verified_revenue = _coalesce(payload.get("verified_revenue"), report.revenue)
    review.verified_expenses = _coalesce(payload.get("verified_expenses"), report.expenses)
    review.verified_net_result = _coalesce(payload.get("verified_net_result"), report.net_result)
    review.verified_outstanding_receivables = _coalesce(
        payload.get("verified_outstanding_receivables"), report.outstanding_receivables
    )
    review.reviewed_at = utcnow()

    # Accurate data closes the loop; flagged data stays under review.
    report.status = (
        ReportStatus.REVIEWED.value
        if accurate
        else ReportStatus.UNDER_REVIEW.value
    )

    db.add(review)
    db.add(report)
    db.commit()
    db.refresh(review)

    audit_service.record(
        db,
        action=AuditAction.REPORT_FINANCIAL_REVIEWED,
        actor_user_id=user.id,
        entity_type="monthly_report",
        entity_id=report.id,
        company_id=report.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"accurate": accurate, "status": review.status},
    )
    return review


def _coalesce(new_value, existing):
    return new_value if new_value is not None else existing


def _get_scoped_or_404(db: Session, user: User, report_id: int) -> MonthlyReport:
    """Fetch a report inside the caller's company scope.

    An out-of-scope id is reported as *not found* rather than *forbidden*, so a
    caller cannot use the error to discover that another company's report
    exists (IDOR protection).
    """
    report = MonthlyReportRepository(db).get_for_user(user, report_id)
    if report is None:
        raise NotFoundError("Report not found.")
    return report


def serialise(report: MonthlyReport) -> dict:
    """Attach company display names for the API response."""
    data = {
        "id": report.id,
        "company_id": report.company_id,
        "company_name_ar": report.company.name_ar if report.company else None,
        "company_name_en": report.company.name_en if report.company else None,
        "period_year": report.period_year,
        "period_month": report.period_month,
        "status": report.status,
        "revenue": report.revenue,
        "expenses": report.expenses,
        "net_result": report.net_result,
        "outstanding_receivables": report.outstanding_receivables,
        "important_developments": report.important_developments,
        "new_customers": report.new_customers,
        "new_opportunities": report.new_opportunities,
        "major_problems": report.major_problems,
        "support_required": report.support_required,
        "marketing_status": report.marketing_status,
        "business_development_status": report.business_development_status,
        "management_notes": report.management_notes,
        "submitted_at": report.submitted_at,
        "created_at": report.created_at,
        "updated_at": report.updated_at,
        "financial_review": report.financial_review,
    }
    return data


__all__ = [
    "create_report",
    "update_report",
    "submit_report",
    "review_financially",
    "serialise",
    "MonthlyReport",
    "Decimal",
]
