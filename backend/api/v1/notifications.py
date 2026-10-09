"""Notification centre endpoints under ``/api/v1/notifications``.

The inbox is always the caller's own: listing and mutation are filtered by
``recipient_id = current_user.id`` in the service, never by a query parameter.
The one administrative action -- running the document-expiry scan -- requires
``notification.manage`` and is idempotent.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.api.deps import CurrentUser, DbSession, require
from backend.rbac.permissions import Perm
from backend.schemas import (
    NotificationOut,
    NotificationSummaryOut,
    PageOut,
)
from backend.services import notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=PageOut)
def list_notifications(
    db: DbSession,
    user: CurrentUser,
    unread_only: bool = Query(default=False),
    type: str | None = Query(default=None),
    company_id: int | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PageOut:
    return PageOut(
        **notification_service.list_notifications(
            db,
            user=user,
            unread_only=unread_only,
            type=type,
            company_id=company_id,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/summary", response_model=NotificationSummaryOut)
def summary(db: DbSession, user: CurrentUser) -> NotificationSummaryOut:
    return NotificationSummaryOut(**notification_service.summary(db, user=user))


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(
    notification_id: int, db: DbSession, user: CurrentUser
) -> NotificationOut:
    row = notification_service.mark_read(db, user=user, notification_id=notification_id)
    return NotificationOut(**notification_service.serialise(row))


@router.post("/read-all", response_model=NotificationSummaryOut)
def mark_all_read(db: DbSession, user: CurrentUser) -> NotificationSummaryOut:
    notification_service.mark_all_read(db, user=user)
    return NotificationSummaryOut(**notification_service.summary(db, user=user))


@router.post("/scan-documents", response_model=dict)
def scan_documents(
    db: DbSession,
    actor=Depends(require(Perm.NOTIFICATION_MANAGE)),
) -> dict:
    """Run the document-expiry scan now. Idempotent per document per month.

    Exposed as an explicit endpoint so the scan can be scheduled (cron, systemd
    timer) or triggered by an administrator without a background worker.
    """
    return notification_service.scan_document_expiry(db, actor_user_id=actor.id)
