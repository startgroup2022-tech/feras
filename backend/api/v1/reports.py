"""Monthly report endpoints, including the accountant review sub-resource."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile, status

from backend.api.deps import CurrentUser, DbSession, require
from backend.core.errors import NotFoundError, ValidationError
from backend.db.models.identity import User
from backend.rbac.authorization import require_any_permission
from backend.rbac.permissions import Perm
from backend.repositories.scoped import MonthlyReportRepository
from backend.schemas import (
    AttachmentOut,
    FinancialReviewOut,
    FinancialReviewRequest,
    MonthlyReportCreateRequest,
    MonthlyReportOut,
    MonthlyReportUpdateRequest,
    ReportClarificationRequest,
)
from backend.services import audit_service, report_service

router = APIRouter(prefix="/monthly-reports", tags=["monthly-reports"])


def _to_out(report, db=None, user=None) -> MonthlyReportOut:
    financial_part = None
    if db is not None and user is not None:
        financial_part = report_service.financial_part_status(db, report=report, user=user)
    return MonthlyReportOut(**report_service.serialise(report, financial_part=financial_part))


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
    return [_to_out(r, db, user) for r in reports]


@router.get("/{report_id}", response_model=MonthlyReportOut)
def get_report(report_id: int, user: CurrentUser, db: DbSession) -> MonthlyReportOut:
    require_any_permission(user, Perm.REPORT_READ_OWN, Perm.REPORT_READ_ALL)
    report = MonthlyReportRepository(db).get_for_user(user, report_id)
    if report is None:
        from backend.core.errors import NotFoundError

        raise NotFoundError("Report not found.")
    return _to_out(report, db, user)


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
    return _to_out(report, db, user)


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
    return _to_out(report, db, user)


@router.post("/{report_id}/organize-narrative")
def organize_report_narrative(
    report_id: int, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    """S09: return an AI organization *proposal* for the report's narrative.

    The suggestion is advisory: the stored report is never modified by this
    call, so the original text always survives (spec: "يعرض اقتراح تنظيم مع بقاء
    الأصل"). The manager applies any accepted change through the normal PATCH.
    """
    ctx = audit_service.request_context(request)
    return report_service.organize_report_narrative(
        db,
        user=user,
        report_id=report_id,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )


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
    return _to_out(report, db, user)


@router.post(
    "/{report_id}/attachments",
    response_model=AttachmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    report_id: int,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
) -> AttachmentOut:
    """Attach a file to a report. Type and size are validated server-side."""
    ctx = audit_service.request_context(request)
    data = await file.read()
    attachment = report_service.add_attachment(
        db,
        user=user,
        report_id=report_id,
        filename=file.filename or "",
        content_type=file.content_type,
        data=data,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return AttachmentOut.model_validate(attachment)


@router.delete(
    "/{report_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_attachment(
    report_id: int,
    attachment_id: int,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> Response:
    ctx = audit_service.request_context(request)
    report_service.remove_attachment(
        db,
        user=user,
        report_id=report_id,
        attachment_id=attachment_id,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------
# clarification thread (S02/S09) -- linked to the original, never edits it
# --------------------------------------------------------------------------
@router.get("/{report_id}/clarifications")
def list_clarifications(report_id: int, user: CurrentUser, db: DbSession) -> list[dict]:
    require_any_permission(user, Perm.REPORT_READ_OWN, Perm.REPORT_READ_ALL)
    rows = report_service.list_clarifications(db, user=user, report_id=report_id)
    return [report_service.serialise_clarification(c) for c in rows]


@router.post(
    "/{report_id}/clarifications",
    status_code=status.HTTP_201_CREATED,
)
def add_clarification(
    report_id: int,
    payload: ReportClarificationRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> dict:
    ctx = audit_service.request_context(request)
    clarification = report_service.add_clarification(
        db,
        user=user,
        report_id=report_id,
        body=payload.body,
        kind=payload.kind.value,
        parent_id=payload.parent_id,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return report_service.serialise_clarification(clarification)


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
