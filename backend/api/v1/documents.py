"""Document management endpoints under ``/api/v1/documents``.

Storage internals (the key and path) are never returned. Downloads enforce the
caller's company scope, so a document id from another company is indistinguishable
from a missing one.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import FileResponse

from backend.api.deps import CurrentUser, DbSession, require
from backend.rbac.permissions import Perm
from backend.db.models.audit_actions import AuditAction
from backend.schemas import (
    DocumentCategoryCreateRequest,
    DocumentCategoryOut,
    DocumentCategoryUpdateRequest,
    DocumentOut,
    DocumentUpdateRequest,
    PageOut,
)
from backend.services import audit_service, document_service

router = APIRouter(prefix="/documents", tags=["documents"])


# --------------------------------------------------------------------------
# categories
# --------------------------------------------------------------------------
@router.get("/categories", response_model=list[DocumentCategoryOut])
def list_categories(
    db: DbSession, user: CurrentUser, include_inactive: bool = Query(default=False)
) -> list[DocumentCategoryOut]:
    return [
        DocumentCategoryOut(**row)
        for row in document_service.list_categories(
            db, user=user, include_inactive=include_inactive
        )
    ]


@router.post(
    "/categories", response_model=DocumentCategoryOut, status_code=status.HTTP_201_CREATED
)
def create_category(
    payload: DocumentCategoryCreateRequest,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.DOCUMENT_CATEGORY_MANAGE)),
) -> DocumentCategoryOut:
    ctx = audit_service.request_context(request)
    row = document_service.create_category(
        db,
        actor=actor,
        payload=payload.model_dump(),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return DocumentCategoryOut(**row)


@router.patch("/categories/{category_id}", response_model=DocumentCategoryOut)
def update_category(
    category_id: int,
    payload: DocumentCategoryUpdateRequest,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.DOCUMENT_CATEGORY_MANAGE)),
) -> DocumentCategoryOut:
    ctx = audit_service.request_context(request)
    row = document_service.update_category(
        db,
        actor=actor,
        category_id=category_id,
        payload=payload.model_dump(exclude_unset=True),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return DocumentCategoryOut(**row)


# --------------------------------------------------------------------------
# documents
# --------------------------------------------------------------------------
@router.get("", response_model=PageOut)
def list_documents(
    db: DbSession,
    user: CurrentUser,
    company_id: int | None = Query(default=None),
    category_id: int | None = Query(default=None),
    document_status: str | None = Query(default=None, alias="status"),
    expiry: str | None = Query(default=None, pattern="^(expired|expiring_soon|valid)$"),
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PageOut:
    return PageOut(
        **document_service.list_documents(
            db,
            user=user,
            company_id=company_id,
            category_id=category_id,
            status=document_status,
            expiry=expiry,
            search=search,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/expiry-summary", response_model=dict)
def expiry_summary(db: DbSession, user: CurrentUser) -> dict:
    """Foundation for a future notification centre -- counts only."""
    return document_service.expiring_summary(db, user=user)


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.DOCUMENT_UPLOAD)),
    file: UploadFile = File(...),
    company_id: int = Form(...),
    category_id: int | None = Form(default=None),
    title_ar: str | None = Form(default=None),
    title_en: str | None = Form(default=None),
    description: str | None = Form(default=None),
    issue_date: str | None = Form(default=None),
    expiry_date: str | None = Form(default=None),
) -> DocumentOut:
    from datetime import date

    ctx = audit_service.request_context(request)
    data = await file.read()

    def _parse(value: str | None):
        if not value:
            return None
        return date.fromisoformat(value[:10])

    document = document_service.upload_document(
        db,
        actor=actor,
        company_id=company_id,
        filename=file.filename or "",
        content_type=file.content_type,
        data=data,
        category_id=category_id,
        title_ar=title_ar,
        title_en=title_en,
        description=description,
        issue_date=_parse(issue_date),
        expiry_date=_parse(expiry_date),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return DocumentOut(**document_service.serialise_document(db, document))


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: int, db: DbSession, user: CurrentUser) -> DocumentOut:
    document = document_service.get_document_scoped(db, user, document_id)
    return DocumentOut(**document_service.serialise_document(db, document))


@router.patch("/{document_id}", response_model=DocumentOut)
def update_document(
    document_id: int,
    payload: DocumentUpdateRequest,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.DOCUMENT_UPDATE)),
) -> DocumentOut:
    ctx = audit_service.request_context(request)
    row = document_service.update_document(
        db,
        actor=actor,
        document_id=document_id,
        payload=payload.model_dump(exclude_unset=True),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return DocumentOut(**row)


@router.post("/{document_id}/archive", response_model=DocumentOut)
def archive_document(
    document_id: int,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.DOCUMENT_ARCHIVE)),
) -> DocumentOut:
    ctx = audit_service.request_context(request)
    row = document_service.archive_document(
        db,
        actor=actor,
        document_id=document_id,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return DocumentOut(**row)


@router.get("/{document_id}/download")
def download_document(
    document_id: int, request: Request, db: DbSession, user: CurrentUser
) -> FileResponse:
    """Stream a document's bytes after re-checking the caller's scope."""
    ctx = audit_service.request_context(request)
    document, path = document_service.open_document_for_download(
        db, actor=user, document_id=document_id
    )
    audit_service.record(
        db,
        action=AuditAction.DOCUMENT_DOWNLOADED,
        actor_user_id=user.id,
        entity_type="document",
        entity_id=document.id,
        company_id=document.company_id,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return FileResponse(
        path,
        media_type=document.content_type or "application/octet-stream",
        filename=document.original_filename,
    )
