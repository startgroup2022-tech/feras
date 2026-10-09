"""Support request endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from backend.api.deps import CurrentUser, DbSession
from backend.core.errors import NotFoundError
from backend.rbac.authorization import require_any_permission
from backend.rbac.permissions import Perm
from backend.repositories.scoped import SupportRequestRepository
from backend.schemas import (
    SupportAssignRequest,
    SupportCommentOut,
    SupportCommentRequest,
    SupportRequestCreateRequest,
    SupportRequestOut,
    SupportRequestStatusRequest,
)
from backend.services import audit_service, support_service

router = APIRouter(prefix="/support-requests", tags=["support-requests"])


@router.get("", response_model=list[SupportRequestOut])
def list_requests(
    user: CurrentUser,
    db: DbSession,
    company_id: int | None = None,
    status_filter: str | None = None,
    category: str | None = None,
) -> list[SupportRequestOut]:
    """Requests within the caller's company scope."""
    require_any_permission(user, Perm.SUPPORT_READ_OWN, Perm.SUPPORT_READ_ALL)
    requests = SupportRequestRepository(db).list_for_user(
        user, company_id=company_id, status=status_filter, category=category
    )
    return [SupportRequestOut(**support_service.serialise(r)) for r in requests]


@router.get("/{request_id}", response_model=SupportRequestOut)
def get_request(
    request_id: int, user: CurrentUser, db: DbSession
) -> SupportRequestOut:
    require_any_permission(user, Perm.SUPPORT_READ_OWN, Perm.SUPPORT_READ_ALL)
    request = SupportRequestRepository(db).get_for_user(user, request_id)
    if request is None:
        raise NotFoundError("Support request not found.")
    return SupportRequestOut(**support_service.serialise(request))


@router.post("", response_model=SupportRequestOut, status_code=status.HTTP_201_CREATED)
def create_request(
    payload: SupportRequestCreateRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> SupportRequestOut:
    ctx = audit_service.request_context(request)
    created = support_service.create_request(
        db,
        user=user,
        company_id=payload.company_id,
        title=payload.title,
        description=payload.description,
        category=payload.category.value,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return SupportRequestOut(**support_service.serialise(created))


@router.patch("/{request_id}/status", response_model=SupportRequestOut)
def change_status(
    request_id: int,
    payload: SupportRequestStatusRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> SupportRequestOut:
    ctx = audit_service.request_context(request)
    updated = support_service.change_status(
        db,
        user=user,
        request_id=request_id,
        new_status=payload.status.value,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return SupportRequestOut(**support_service.serialise(updated))


@router.patch("/{request_id}/assign", response_model=SupportRequestOut)
def assign_request(
    request_id: int,
    payload: SupportAssignRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> SupportRequestOut:
    ctx = audit_service.request_context(request)
    updated = support_service.assign_request(
        db,
        user=user,
        request_id=request_id,
        assigned_to_id=payload.assigned_to_id,
        responsible_department=payload.responsible_department,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return SupportRequestOut(**support_service.serialise(updated))


@router.get("/{request_id}/comments", response_model=list[SupportCommentOut])
def list_comments(
    request_id: int,
    user: CurrentUser,
    db: DbSession,
) -> list[dict]:
    return support_service.list_comments(db, user=user, request_id=request_id)


@router.post(
    "/{request_id}/comments",
    response_model=SupportCommentOut,
    status_code=status.HTTP_201_CREATED,
)
def add_comment(
    request_id: int,
    payload: SupportCommentRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> dict:
    ctx = audit_service.request_context(request)
    comment = support_service.add_comment(
        db,
        user=user,
        request_id=request_id,
        body=payload.body,
        is_internal=payload.is_internal,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return support_service.serialise_comment(comment)
