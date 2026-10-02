"""Support request service.

A subsidiary raises a request; the Holding department that owns the category
picks it up. Status transitions are validated so that a request cannot jump
from ``closed`` back to ``new`` without an explicit reopen, keeping the
foundation simple but not sloppy.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.core.errors import ConflictError, NotFoundError, ValidationError
from backend.db.base import utcnow
from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import SupportStatus
from backend.db.models.identity import User
from backend.db.models.support import SupportRequest, SupportRequestComment
from backend.rbac.authorization import require_company_access, require_permission
from backend.rbac.permissions import Perm
from backend.repositories.scoped import SupportRequestRepository
from backend.services import audit_service

# Allowed transitions. Deliberately linear and short.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    SupportStatus.NEW.value: {SupportStatus.IN_PROGRESS.value, SupportStatus.CLOSED.value},
    SupportStatus.IN_PROGRESS.value: {
        SupportStatus.COMPLETED.value,
        SupportStatus.CLOSED.value,
    },
    SupportStatus.COMPLETED.value: {SupportStatus.CLOSED.value, SupportStatus.IN_PROGRESS.value},
    SupportStatus.CLOSED.value: {SupportStatus.IN_PROGRESS.value},  # reopen
}


def create_request(
    db: Session,
    *,
    user: User,
    company_id: int,
    title: str,
    description: str | None,
    category: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> SupportRequest:
    require_permission(user, Perm.SUPPORT_CREATE)
    require_company_access(user, company_id, write=True)

    request = SupportRequest(
        company_id=company_id,
        title=title.strip(),
        description=description,
        category=category,
        status=SupportStatus.NEW.value,
        requested_by_id=user.id,
    )
    db.add(request)
    db.commit()
    db.refresh(request)

    audit_service.record(
        db,
        action=AuditAction.SUPPORT_REQUEST_CREATED,
        actor_user_id=user.id,
        entity_type="support_request",
        entity_id=request.id,
        company_id=company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"category": category},
    )
    return request


def change_status(
    db: Session,
    *,
    user: User,
    request_id: int,
    new_status: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> SupportRequest:
    require_permission(user, Perm.SUPPORT_STATUS_CHANGE)
    request = _get_scoped_or_404(db, user, request_id)

    if new_status == request.status:
        raise ConflictError("The request already has this status.")
    if new_status not in ALLOWED_TRANSITIONS.get(request.status, set()):
        raise ValidationError(
            f"Cannot move a request from '{request.status}' to '{new_status}'."
        )

    previous = request.status
    request.status = new_status
    request.closed_at = utcnow() if new_status == SupportStatus.CLOSED.value else None
    db.add(request)
    db.commit()
    db.refresh(request)

    audit_service.record(
        db,
        action=AuditAction.SUPPORT_REQUEST_STATUS_CHANGED,
        actor_user_id=user.id,
        entity_type="support_request",
        entity_id=request.id,
        company_id=request.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"from": previous, "to": new_status},
    )
    return request


def assign_request(
    db: Session,
    *,
    user: User,
    request_id: int,
    assigned_to_id: int | None,
    responsible_department: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> SupportRequest:
    """Assign a request to a staff member and/or a department.

    Only the ``assigned_to_id`` and department label are stored; there is no
    routing engine. The department is normally derived from the category, but a
    manager may override it.
    """
    require_permission(user, Perm.SUPPORT_ASSIGN)
    request = _get_scoped_or_404(db, user, request_id)

    if assigned_to_id is not None:
        assignee = db.get(User, assigned_to_id)
        if assignee is None or not assignee.is_active:
            raise ValidationError("Assignee not found or inactive.")

    request.assigned_to_id = assigned_to_id
    db.add(request)
    db.commit()
    db.refresh(request)

    audit_service.record(
        db,
        action=AuditAction.SUPPORT_REQUEST_ASSIGNED,
        actor_user_id=user.id,
        entity_type="support_request",
        entity_id=request.id,
        company_id=request.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"assigned_to": assigned_to_id, "department": responsible_department},
    )
    return request


def add_comment(
    db: Session,
    *,
    user: User,
    request_id: int,
    body: str,
    is_internal: bool = False,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> SupportRequestComment:
    require_permission(user, Perm.SUPPORT_COMMENT)
    request = _get_scoped_or_404(db, user, request_id)

    # Internal notes are for Holding staff only, never visible to the company.
    if is_internal and not _is_holding_staff(user):
        raise ValidationError("Internal notes are restricted to Holding staff.")

    comment = SupportRequestComment(
        request_id=request.id,
        author_id=user.id,
        body=body.strip(),
        is_internal=is_internal,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)

    audit_service.record(
        db,
        action=AuditAction.SUPPORT_REQUEST_COMMENTED,
        actor_user_id=user.id,
        entity_type="support_request",
        entity_id=request.id,
        company_id=request.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"internal": is_internal},
    )
    return comment


def list_comments(db: Session, *, user: User, request_id: int) -> list[dict]:
    """Comments on a request, with internal notes hidden from the company.

    The subsidiary that raised the request sees the public conversation only;
    Holding staff see everything. Scoping happens through the request itself,
    so a caller cannot read comments on a request they cannot see.
    """
    request = _get_scoped_or_404(db, user, request_id)
    query = (
        db.query(SupportRequestComment)
        .filter(SupportRequestComment.request_id == request.id)
        .order_by(SupportRequestComment.created_at.asc(), SupportRequestComment.id.asc())
    )
    if not _is_holding_staff(user):
        query = query.filter(SupportRequestComment.is_internal.is_(False))

    return [serialise_comment(comment) for comment in query.all()]


def serialise_comment(comment: SupportRequestComment) -> dict:
    return {
        "id": comment.id,
        "request_id": comment.request_id,
        "author_id": comment.author_id,
        "author_name_ar": comment.author.full_name_ar if comment.author else None,
        "body": comment.body,
        "is_internal": comment.is_internal,
        "created_at": comment.created_at,
    }


def _is_holding_staff(user: User) -> bool:
    from backend.rbac.authorization import is_holding_wide

    return is_holding_wide(user) or user.role_code == "accountant"


def _get_scoped_or_404(db: Session, user: User, request_id: int) -> SupportRequest:
    request = SupportRequestRepository(db).get_for_user(user, request_id)
    if request is None:
        raise NotFoundError("Support request not found.")
    return request


def serialise(request: SupportRequest) -> dict:
    return {
        "id": request.id,
        "company_id": request.company_id,
        "company_name_ar": request.company.name_ar if request.company else None,
        "company_name_en": request.company.name_en if request.company else None,
        "title": request.title,
        "description": request.description,
        "category": request.category,
        "status": request.status,
        "responsible_department": request.responsible_department,
        "requested_by_id": request.requested_by_id,
        "assigned_to_id": request.assigned_to_id,
        "created_at": request.created_at,
        "updated_at": request.updated_at,
        "closed_at": request.closed_at,
    }
