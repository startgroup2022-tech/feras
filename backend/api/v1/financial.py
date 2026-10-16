"""Financial summary workflow endpoints (Execution 02, F-03/F-04/F-06).

Thin routers: every business rule lives in
:mod:`backend.services.financial_service`. All routes are permission-guarded and
company-scoped; an out-of-scope id is reported as not found (IDOR protection).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile, status
from fastapi.responses import FileResponse

from backend.api.deps import CurrentUser, DbSession, require
from backend.core import storage
from backend.core.errors import NotFoundError
from backend.db.models.financial import FinancialItemDefinition
from backend.rbac.authorization import require_any_permission, require_company_access, require_permission
from backend.rbac.permissions import Perm
from backend.repositories.scoped import (
    FinancialPeriodRepository,
    FinancialVersionRepository,
)
from backend.schemas.financial import (
    FinancialBankAttachmentOut,
    FinancialItemCreateRequest,
    FinancialItemDefinitionCreateRequest,
    FinancialItemDefinitionOut,
    FinancialItemOut,
    FinancialPeriodOut,
    FinancialReviewReturnRequest,
    FinancialSummaryCreateRequest,
    FinancialSummaryOut,
    FinancialSummaryUpdateRequest,
)
from backend.services import audit_service, financial_service
from backend.services import financial_reporting

router = APIRouter(prefix="/financial", tags=["financial-suite"])


def _summary_out(version) -> FinancialSummaryOut:
    return FinancialSummaryOut(**financial_service.serialise(version))


# --------------------------------------------------------------------------
# effective-version report (registered before the {version_id} routes)
# --------------------------------------------------------------------------
@router.get("/report")
def effective_report(
    user: CurrentUser, db: DbSession, year: int, month: int
) -> dict:
    """Per-company effective financial report for one month (spec S10).

    Reads only the effective (approved) version of each period, so two versions
    of the same month are never double-counted.
    """
    require_any_permission(
        user, Perm.FINANCIAL_SUMMARY_READ_OWN, Perm.FINANCIAL_SUMMARY_READ_ALL
    )
    return financial_reporting.effective_period_report(db, user=user, year=year, month=month)


# --------------------------------------------------------------------------
# accountant review queue (registered before the {version_id} routes)
# --------------------------------------------------------------------------
@router.get("/summaries/pending", response_model=list[FinancialSummaryOut])
def list_pending(user: CurrentUser, db: DbSession) -> list[FinancialSummaryOut]:
    """Submitted (and returned) summaries awaiting an accountant decision."""
    require_any_permission(user, Perm.FINANCIAL_REVIEW_ACT, Perm.FINANCIAL_REVIEW_READ)
    versions = FinancialVersionRepository(db).pending_for_user(user)
    return [_summary_out(v) for v in versions]


# --------------------------------------------------------------------------
# periods and summaries
# --------------------------------------------------------------------------
@router.get("/periods", response_model=list[FinancialPeriodOut])
def list_periods(
    user: CurrentUser,
    db: DbSession,
    company_id: int | None = None,
    year: int | None = None,
    status: str | None = None,
) -> list[FinancialPeriodOut]:
    require_any_permission(
        user, Perm.FINANCIAL_SUMMARY_READ_OWN, Perm.FINANCIAL_SUMMARY_READ_ALL
    )
    periods = FinancialPeriodRepository(db).list_for_user(
        user, company_id=company_id, year=year, status=status
    )
    return [FinancialPeriodOut(**financial_service.serialise_period(p)) for p in periods]


@router.get("/periods/{period_id}", response_model=FinancialPeriodOut)
def get_period(period_id: int, user: CurrentUser, db: DbSession) -> FinancialPeriodOut:
    require_any_permission(
        user, Perm.FINANCIAL_SUMMARY_READ_OWN, Perm.FINANCIAL_SUMMARY_READ_ALL
    )
    period = FinancialPeriodRepository(db).get_for_user(user, period_id)
    if period is None:
        raise NotFoundError("Financial period not found.")
    return FinancialPeriodOut(**financial_service.serialise_period(period))


@router.post(
    "/summaries", response_model=FinancialSummaryOut, status_code=status.HTTP_201_CREATED
)
def create_summary(
    payload: FinancialSummaryCreateRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> FinancialSummaryOut:
    ctx = audit_service.request_context(request)
    data = payload.model_dump(
        exclude={"company_id", "period_year", "period_month"}, exclude_unset=True
    )
    version = financial_service.create_summary(
        db,
        user=user,
        company_id=payload.company_id,
        period_year=payload.period_year,
        period_month=payload.period_month,
        payload=data,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return _summary_out(version)


@router.get("/summaries/{version_id}", response_model=FinancialSummaryOut)
def get_summary(version_id: int, user: CurrentUser, db: DbSession) -> FinancialSummaryOut:
    require_any_permission(
        user, Perm.FINANCIAL_SUMMARY_READ_OWN, Perm.FINANCIAL_SUMMARY_READ_ALL
    )
    version = FinancialVersionRepository(db).get_for_user(user, version_id)
    if version is None:
        raise NotFoundError("Financial summary not found.")
    return _summary_out(version)


@router.patch("/summaries/{version_id}", response_model=FinancialSummaryOut)
def update_summary(
    version_id: int,
    payload: FinancialSummaryUpdateRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> FinancialSummaryOut:
    ctx = audit_service.request_context(request)
    version = financial_service.update_draft(
        db,
        user=user,
        version_id=version_id,
        payload=payload.model_dump(exclude_unset=True),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return _summary_out(version)


# --------------------------------------------------------------------------
# special items
# --------------------------------------------------------------------------
@router.post(
    "/summaries/{version_id}/items",
    response_model=FinancialItemOut,
    status_code=status.HTTP_201_CREATED,
)
def add_item(
    version_id: int,
    payload: FinancialItemCreateRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> FinancialItemOut:
    ctx = audit_service.request_context(request)
    item = financial_service.add_item(
        db,
        user=user,
        version_id=version_id,
        payload=payload.model_dump(exclude_unset=True),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return FinancialItemOut.model_validate(item)


@router.delete(
    "/summaries/{version_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def remove_item(
    version_id: int,
    item_id: int,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> Response:
    ctx = audit_service.request_context(request)
    financial_service.remove_item(
        db,
        user=user,
        version_id=version_id,
        item_id=item_id,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------
# bank statement (private; never served via a public route)
# --------------------------------------------------------------------------
@router.post(
    "/summaries/{version_id}/bank-statement",
    response_model=FinancialBankAttachmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_bank_statement(
    version_id: int,
    request: Request,
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
) -> FinancialBankAttachmentOut:
    ctx = audit_service.request_context(request)
    data = await file.read()
    attachment = financial_service.add_bank_attachment(
        db,
        user=user,
        version_id=version_id,
        filename=file.filename or "",
        content_type=file.content_type,
        data=data,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return FinancialBankAttachmentOut.model_validate(attachment)


@router.get("/summaries/{version_id}/bank-statement/{attachment_id}")
def download_bank_statement(
    version_id: int,
    attachment_id: int,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> FileResponse:
    ctx = audit_service.request_context(request)
    attachment = financial_service.get_bank_attachment_for_download(
        db,
        user=user,
        version_id=version_id,
        attachment_id=attachment_id,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    path = storage.resolve_stored_path(attachment.storage_key)
    return FileResponse(
        path,
        media_type=attachment.content_type or "application/octet-stream",
        filename=attachment.original_filename,
    )


# --------------------------------------------------------------------------
# workflow transitions
# --------------------------------------------------------------------------
@router.post("/summaries/{version_id}/submit", response_model=FinancialSummaryOut)
def submit_summary(
    version_id: int, request: Request, user: CurrentUser, db: DbSession
) -> FinancialSummaryOut:
    ctx = audit_service.request_context(request)
    version = financial_service.submit_version(
        db,
        user=user,
        version_id=version_id,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return _summary_out(version)


@router.post("/summaries/{version_id}/return", response_model=FinancialSummaryOut)
def return_summary(
    version_id: int,
    payload: FinancialReviewReturnRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> FinancialSummaryOut:
    ctx = audit_service.request_context(request)
    version = financial_service.return_version(
        db,
        user=user,
        version_id=version_id,
        note=payload.note,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return _summary_out(version)


@router.post("/summaries/{version_id}/approve", response_model=FinancialSummaryOut)
def approve_summary(
    version_id: int, request: Request, user: CurrentUser, db: DbSession
) -> FinancialSummaryOut:
    ctx = audit_service.request_context(request)
    version = financial_service.approve_version(
        db,
        user=user,
        version_id=version_id,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return _summary_out(version)


@router.post(
    "/periods/{period_id}/corrections",
    response_model=FinancialSummaryOut,
    status_code=status.HTTP_201_CREATED,
)
def create_correction(
    period_id: int, request: Request, user: CurrentUser, db: DbSession
) -> FinancialSummaryOut:
    ctx = audit_service.request_context(request)
    version = financial_service.create_correction(
        db,
        user=user,
        period_id=period_id,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return _summary_out(version)


# --------------------------------------------------------------------------
# special-item definitions (F-04 configuration)
# --------------------------------------------------------------------------
@router.get("/item-definitions", response_model=list[FinancialItemDefinitionOut])
def list_item_definitions(
    user: CurrentUser, db: DbSession, company_id: int | None = None
) -> list[FinancialItemDefinitionOut]:
    require_any_permission(
        user, Perm.FINANCIAL_SUMMARY_READ_OWN, Perm.FINANCIAL_SUMMARY_READ_ALL
    )
    from backend.rbac.authorization import accessible_company_ids

    stmt = db.query(FinancialItemDefinition)
    allowed = accessible_company_ids(user)
    if allowed is not None:
        stmt = stmt.filter(FinancialItemDefinition.company_id.in_(allowed or [-1]))
    if company_id is not None:
        stmt = stmt.filter(FinancialItemDefinition.company_id == company_id)
    rows = stmt.order_by(
        FinancialItemDefinition.company_id, FinancialItemDefinition.name_en
    ).all()
    return [FinancialItemDefinitionOut.model_validate(r) for r in rows]


@router.post(
    "/item-definitions",
    response_model=FinancialItemDefinitionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_item_definition(
    payload: FinancialItemDefinitionCreateRequest,
    company_id: int,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> FinancialItemDefinitionOut:
    require_permission(user, Perm.FINANCIAL_ITEM_MANAGE)
    require_company_access(user, company_id, write=True)

    existing = (
        db.query(FinancialItemDefinition)
        .filter(
            FinancialItemDefinition.company_id == company_id,
            FinancialItemDefinition.code == payload.code,
        )
        .one_or_none()
    )
    if existing is not None:
        from backend.core.errors import ConflictError

        raise ConflictError("An item definition with this code already exists.")

    definition = FinancialItemDefinition(
        company_id=company_id,
        **payload.model_dump(),
    )
    db.add(definition)
    db.commit()
    db.refresh(definition)
    return FinancialItemDefinitionOut.model_validate(definition)


__all__ = ["router"]
