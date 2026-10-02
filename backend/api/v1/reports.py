"""Monthly report endpoints, including the accountant review sub-resource."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from backend.api.deps import CurrentUser, DbSession, require
from backend.db.models.identity import User
from backend.rbac.authorization import require_any_permission
from backend.rbac.permissions import Perm
from backend.repositories.scoped import MonthlyReportRepository
from backend.schemas import (
    FinancialReviewOut,
    FinancialReviewRequest,
    MonthlyReportCreateRequest,
    MonthlyReportOut,
    MonthlyReportUpdateRequest,
)
from backend.services import audit_service, report_service

router = APIRouter(prefix="/monthly-reports", tags=["monthly-reports"])


def _to_out(report) -> MonthlyReportOut:
    return MonthlyReportOut(**report_service.serialise(report))


@router.get("", response_model=list[MonthlyReportOut])
def list_reports(
    user: CurrentUser,
    db: DbSession,
    company_id: int | None = None,
    year: int | None = None,
) -> list[MonthlyReportOut]:
    """Reports within the caller's company scope.

    ``company_id`` narrows the result; it can never widen it, because the scope
    filter is applied by the repository regardless of the query parameter.
    """
    require_any_permission(user, Perm.REPORT_READ_OWN, Perm.REPORT_READ_ALL)
    reports = MonthlyReportRepository(db).list_for_user(
        user, company_id=company_id, year=year
    )
    return [_to_out(r) for r in reports]


@router.get("/{report_id}", response_model=MonthlyReportOut)
def get_report(report_id: int, user: CurrentUser, db: DbSession) -> MonthlyReportOut:
    require_any_permission(user, Perm.REPORT_READ_OWN, Perm.REPORT_READ_ALL)
    report = MonthlyReportRepository(db).get_for_user(user, report_id)
    if report is None:
        from backend.core.errors import NotFoundError

        raise NotFoundError("Report not found.")
    return _to_out(report)


@router.post("", response_model=MonthlyReportOut, status_code=status.HTTP_201_CREATED)
def create_report(
    payload: MonthlyReportCreateRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> MonthlyReportOut:
    ctx = audit_service.request_context(request)
    data = payload.model_dump(exclude={"company_id", "period_year", "period_month"})
    report = report_service.create_report(
        db,
        user=user,
        company_id=payload.company_id,
        period_year=payload.period_year,
        period_month=payload.period_month,
        payload=data,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return _to_out(report)


@router.patch("/{report_id}", response_model=MonthlyReportOut)
def update_report(
    report_id: int,
    payload: MonthlyReportUpdateRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> MonthlyReportOut:
    ctx = audit_service.request_context(request)
    report = report_service.update_report(
        db,
        user=user,
        report_id=report_id,
        payload=payload.model_dump(exclude_unset=True),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return _to_out(report)


@router.post("/{report_id}/submit", response_model=MonthlyReportOut)
def submit_report(
    report_id: int, request: Request, user: CurrentUser, db: DbSession
) -> MonthlyReportOut:
    ctx = audit_service.request_context(request)
    report = report_service.submit_report(
        db,
        user=user,
        report_id=report_id,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return _to_out(report)


# --------------------------------------------------------------------------
# accountant review
# --------------------------------------------------------------------------
@router.post("/{report_id}/financial-review", response_model=FinancialReviewOut)
def financial_review(
    report_id: int,
    payload: FinancialReviewRequest,
    request: Request,
    db: DbSession,
    actor: User = Depends(require(Perm.FINANCIAL_REVIEW_WRITE)),
) -> FinancialReviewOut:
    """Accountant verification. Verified figures feed the Holding dashboard."""
    ctx = audit_service.request_context(request)
    review = report_service.review_financially(
        db,
        user=actor,
        report_id=report_id,
        payload=payload.model_dump(),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return FinancialReviewOut.model_validate(review)
