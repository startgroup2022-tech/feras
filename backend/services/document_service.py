"""Document management service.

Company-scoped, like every other business module. The scope is applied as part
of the SQL query (never as a post-hoc check), so a document id belonging to
another company simply does not match -- knowing the id does not bypass
authorization.

Only metadata is returned by the API; the stored key and physical path are
never exposed. Downloads resolve the key server-side and re-check scope.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core import document_storage
from backend.core.errors import ConflictError, NotFoundError, ValidationError
from backend.db.models.audit_actions import AuditAction
from backend.db.models.documents import (
    EXPIRING_SOON_DAYS,
    Document,
    DocumentCategory,
)
from backend.db.models.enums import DocumentEntityType, DocumentStatus
from backend.db.models.identity import Company, User
from backend.rbac.authorization import (
    accessible_company_ids,
    require_company_access,
    require_permission,
)
from backend.rbac.permissions import Perm
from backend.services import audit_service


DEFAULT_CATEGORIES = [
    ("commercial_registration", "السجل التجاري", "Commercial Registration", 1),
    ("license", "رخصة", "License", 2),
    ("contract", "عقد", "Contract", 3),
    ("insurance", "تأمين", "Insurance", 4),
    ("employee_document", "مستند موظف", "Employee Document", 5),
    ("financial_document", "مستند مالي", "Financial Document", 6),
    ("legal_document", "مستند قانوني", "Legal Document", 7),
    ("quotation", "عرض سعر", "Quotation", 8),
    ("project_document", "مستند مشروع", "Project Document", 9),
    ("other", "أخرى", "Other", 10),
]


def seed_default_categories(db: Session) -> None:
    """Idempotently ensure the baseline categories exist."""
    existing = {c.code for c in db.execute(select(DocumentCategory)).scalars()}
    added = False
    for code, name_ar, name_en, order in DEFAULT_CATEGORIES:
        if code not in existing:
            db.add(
                DocumentCategory(
                    code=code,
                    name_ar=name_ar,
                    name_en=name_en,
                    display_order=order,
                    is_active=True,
                )
            )
            added = True
    if added:
        db.commit()


def _apply_document_scope(stmt, user: User):
    allowed = accessible_company_ids(user)
    if allowed is None:
        return stmt
    if not allowed:
        return stmt.where(False)
    return stmt.where(Document.company_id.in_(allowed))


def serialise_document(db: Session, document: Document) -> dict:
    company = db.get(Company, document.company_id)
    category = (
        db.get(DocumentCategory, document.category_id) if document.category_id else None
    )
    return {
        "id": document.id,
        "company_id": document.company_id,
        "company_name_ar": company.name_ar if company else None,
        "company_name_en": company.name_en if company else None,
        "category_id": document.category_id,
        "category_code": category.code if category else None,
        "title_ar": document.title_ar,
        "title_en": document.title_en,
        "description": document.description,
        "related_entity_type": document.related_entity_type,
        "related_entity_id": document.related_entity_id,
        "submission_id": document.submission_id,
        "submission_requirement_id": document.submission_requirement_id,
        "uploaded_by_id": document.uploaded_by_id,
        "original_filename": document.original_filename,
        "content_type": document.content_type,
        "size_bytes": document.size_bytes,
        "issue_date": document.issue_date,
        "expiry_date": document.expiry_date,
        "expiry_state": document.expiry_state,
        "status": document.status,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
    }


# --------------------------------------------------------------------------
# categories
# --------------------------------------------------------------------------
def list_categories(db: Session, *, user: User, include_inactive: bool = False) -> list[dict]:
    require_permission(user, Perm.DOCUMENT_READ)
    stmt = select(DocumentCategory).order_by(
        DocumentCategory.display_order, DocumentCategory.id
    )
    if not include_inactive:
        stmt = stmt.where(DocumentCategory.is_active.is_(True))
    return [
        {
            "id": c.id,
            "code": c.code,
            "name_ar": c.name_ar,
            "name_en": c.name_en,
            "description": c.description,
            "display_order": c.display_order,
            "is_active": c.is_active,
        }
        for c in db.execute(stmt).scalars()
    ]


def create_category(
    db: Session,
    *,
    actor: User,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    require_permission(actor, Perm.DOCUMENT_CATEGORY_MANAGE)
    code = payload["code"].strip().lower()
    if db.execute(
        select(DocumentCategory).where(DocumentCategory.code == code)
    ).scalar_one_or_none():
        raise ConflictError("A category with this code already exists.")
    category = DocumentCategory(
        code=code,
        name_ar=payload["name_ar"].strip(),
        name_en=payload["name_en"].strip(),
        description=payload.get("description"),
        display_order=payload.get("display_order", 0),
        is_active=bool(payload.get("is_active", True)),
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    audit_service.record(
        db,
        action=AuditAction.DOCUMENT_CATEGORY_CREATED,
        actor_user_id=actor.id,
        entity_type="document_category",
        entity_id=category.id,
        metadata={"code": code},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return {
        "id": category.id,
        "code": category.code,
        "name_ar": category.name_ar,
        "name_en": category.name_en,
        "description": category.description,
        "display_order": category.display_order,
        "is_active": category.is_active,
    }


def update_category(
    db: Session,
    *,
    actor: User,
    category_id: int,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    require_permission(actor, Perm.DOCUMENT_CATEGORY_MANAGE)
    category = db.get(DocumentCategory, category_id)
    if category is None:
        raise NotFoundError("Category not found.")
    for attr in ("name_ar", "name_en", "description", "display_order", "is_active"):
        if attr in payload and payload[attr] is not None:
            setattr(category, attr, payload[attr])
    db.add(category)
    db.commit()
    db.refresh(category)
    audit_service.record(
        db,
        action=AuditAction.DOCUMENT_CATEGORY_UPDATED,
        actor_user_id=actor.id,
        entity_type="document_category",
        entity_id=category.id,
        metadata={"fields": sorted(payload.keys())},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return {
        "id": category.id,
        "code": category.code,
        "name_ar": category.name_ar,
        "name_en": category.name_en,
        "description": category.description,
        "display_order": category.display_order,
        "is_active": category.is_active,
    }


# --------------------------------------------------------------------------
# documents
# --------------------------------------------------------------------------
def list_documents(
    db: Session,
    *,
    user: User,
    company_id: int | None = None,
    category_id: int | None = None,
    status: str | None = None,
    expiry: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    require_permission(user, Perm.DOCUMENT_READ)
    stmt = select(Document)
    stmt = _apply_document_scope(stmt, user)
    if company_id is not None:
        stmt = stmt.where(Document.company_id == company_id)
    if category_id is not None:
        stmt = stmt.where(Document.category_id == category_id)
    if status is not None:
        stmt = stmt.where(Document.status == status)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            Document.original_filename.ilike(like)
            | Document.title_ar.ilike(like)
            | Document.title_en.ilike(like)
        )

    rows = list(db.execute(stmt.order_by(Document.created_at.desc())).scalars())

    # Expiry filter is computed in Python (the state is date-relative).
    if expiry:
        rows = [d for d in rows if d.expiry_state == expiry]

    total = len(rows)
    page = rows[offset : offset + limit]
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [serialise_document(db, d) for d in page],
    }


def get_document_scoped(db: Session, user: User, document_id: int) -> Document:
    require_permission(user, Perm.DOCUMENT_READ)
    stmt = _apply_document_scope(select(Document).where(Document.id == document_id), user)
    document = db.execute(stmt).scalar_one_or_none()
    if document is None:
        raise NotFoundError("Document not found.")
    return document


def get_document_or_404(db: Session, document_id: int) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise NotFoundError("Document not found.")
    return document


def upload_document(
    db: Session,
    *,
    actor: User,
    company_id: int,
    filename: str,
    content_type: str | None,
    data: bytes,
    category_id: int | None = None,
    title_ar: str | None = None,
    title_en: str | None = None,
    description: str | None = None,
    issue_date: date | None = None,
    expiry_date: date | None = None,
    related_entity_type: str | None = None,
    related_entity_id: int | None = None,
    submission_id: int | None = None,
    submission_requirement_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Document:
    require_permission(actor, Perm.DOCUMENT_UPLOAD)
    require_company_access(actor, company_id, write=True)

    if category_id is not None and db.get(DocumentCategory, category_id) is None:
        raise ValidationError("The selected category does not exist.")
    if issue_date is not None and expiry_date is not None and expiry_date < issue_date:
        raise ValidationError("The expiry date cannot precede the issue date.")

    extension = document_storage.validate_document(
        filename=filename, content_type=content_type, size=len(data)
    )
    storage_key = document_storage.store_document_bytes(data=data, extension=extension)

    document = Document(
        company_id=company_id,
        category_id=category_id,
        title_ar=title_ar,
        title_en=title_en,
        description=description,
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
        submission_id=submission_id,
        submission_requirement_id=submission_requirement_id,
        uploaded_by_id=actor.id,
        original_filename=filename.strip()[:255],
        storage_key=storage_key,
        content_type=content_type,
        size_bytes=len(data),
        issue_date=issue_date,
        expiry_date=expiry_date,
        status=DocumentStatus.ACTIVE.value,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    audit_service.record(
        db,
        action=AuditAction.DOCUMENT_UPLOADED,
        actor_user_id=actor.id,
        entity_type="document",
        entity_id=document.id,
        company_id=company_id,
        metadata={
            "filename": document.original_filename,
            "content_type": content_type,
            "size": len(data),
            "category_id": category_id,
        },
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return document


def update_document(
    db: Session,
    *,
    actor: User,
    document_id: int,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    require_permission(actor, Perm.DOCUMENT_UPDATE)
    document = get_document_scoped(db, actor, document_id)
    require_company_access(actor, document.company_id, write=True)

    if payload.get("category_id") is not None and db.get(
        DocumentCategory, payload["category_id"]
    ) is None:
        raise ValidationError("The selected category does not exist.")

    for attr in ("title_ar", "title_en", "description", "category_id", "issue_date", "expiry_date"):
        if attr in payload:
            setattr(document, attr, payload[attr])

    if (
        document.issue_date is not None
        and document.expiry_date is not None
        and document.expiry_date < document.issue_date
    ):
        raise ValidationError("The expiry date cannot precede the issue date.")

    db.add(document)
    db.commit()
    db.refresh(document)

    audit_service.record(
        db,
        action=AuditAction.DOCUMENT_UPDATED,
        actor_user_id=actor.id,
        entity_type="document",
        entity_id=document.id,
        company_id=document.company_id,
        metadata={"fields": sorted(payload.keys())},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return serialise_document(db, document)


def archive_document(
    db: Session,
    *,
    actor: User,
    document_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    """Archive (never hard-delete) a document."""
    require_permission(actor, Perm.DOCUMENT_ARCHIVE)
    document = get_document_scoped(db, actor, document_id)
    require_company_access(actor, document.company_id, write=True)
    document.status = DocumentStatus.ARCHIVED.value
    db.add(document)
    db.commit()
    db.refresh(document)
    audit_service.record(
        db,
        action=AuditAction.DOCUMENT_ARCHIVED,
        actor_user_id=actor.id,
        entity_type="document",
        entity_id=document.id,
        company_id=document.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return serialise_document(db, document)


def open_document_for_download(
    db: Session, *, actor: User, document_id: int
) -> tuple[Document, Path]:
    """Resolve a document for download, enforcing scope and existence.

    The authorization is done by the scoped query, so a Company B document id
    used by a Company A user raises the same not-found error as a nonexistent
    id -- existence is not leaked.
    """
    document = get_document_scoped(db, actor, document_id)
    path = document_storage.resolve_document_path(document.storage_key)
    return document, path


def expiring_summary(db: Session, *, user: User) -> dict:
    """Counts for the expiry foundation (expired / expiring soon / valid)."""
    require_permission(user, Perm.DOCUMENT_READ)
    stmt = _apply_document_scope(
        select(Document).where(Document.status == DocumentStatus.ACTIVE.value), user
    )
    counts = {"expired": 0, "expiring_soon": 0, "valid": 0, "none": 0}
    for document in db.execute(stmt).scalars():
        counts[document.expiry_state] = counts.get(document.expiry_state, 0) + 1
    counts["expiring_soon_days"] = EXPIRING_SOON_DAYS
    return counts


__all__ = [
    "archive_document",
    "create_category",
    "expiring_summary",
    "get_document_or_404",
    "get_document_scoped",
    "list_categories",
    "list_documents",
    "open_document_for_download",
    "seed_default_categories",
    "serialise_document",
    "update_category",
    "update_document",
    "upload_document",
]
