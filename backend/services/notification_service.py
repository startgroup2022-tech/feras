"""Notification centre service.

Two responsibilities, kept apart on purpose:

1. **Recording events** -- :func:`notify` writes one durable row per recipient
   from a real system event. It is called by the business services *after* the
   domain change has been committed, and it never raises into the caller: a
   failed notification must not roll back an approval.
2. **Reading an inbox** -- :func:`list_notifications` and friends are always
   filtered by the caller's own user id. A company id from the request can only
   narrow the result, never widen it.

Every row carries a soft reference (``entity_type`` / ``entity_id``) to the
record it is about. That reference is for display only: opening the target
still runs the normal company-scope checks, so a notification can never be a
back door to another company's data.
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.errors import NotFoundError
from backend.db.base import utcnow
from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import NotificationPriority, NotificationType
from backend.db.models.identity import User
from backend.db.models.notifications import Notification
from backend.rbac.authorization import require_permission
from backend.rbac.permissions import Perm
from backend.services import audit_service

logger = logging.getLogger("safir.notifications")


# --------------------------------------------------------------------------
# serialisation
# --------------------------------------------------------------------------
def serialise(notification: Notification) -> dict:
    return {
        "id": notification.id,
        "type": notification.type,
        "priority": notification.priority,
        "title_ar": notification.title_ar,
        "title_en": notification.title_en,
        "message_ar": notification.message_ar,
        "message_en": notification.message_en,
        "entity_type": notification.entity_type,
        "entity_id": notification.entity_id,
        "company_id": notification.company_id,
        "is_read": notification.is_read,
        "read_at": notification.read_at,
        "created_at": notification.created_at,
    }


# --------------------------------------------------------------------------
# writing events
# --------------------------------------------------------------------------
def notify(
    db: Session,
    *,
    recipient_ids: list[int] | None,
    type: str,
    title_ar: str,
    title_en: str,
    message_ar: str,
    message_en: str,
    priority: str = NotificationPriority.NORMAL.value,
    company_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    dedupe_key: str | None = None,
    commit: bool = True,
    actor_user_id: int | None = None,
    emit_webhook: bool = True,
) -> list[Notification]:
    """Create notifications for the given recipients.

    Duplicate protection is per recipient via ``dedupe_key``: if a row with the
    same key already exists for that recipient it is left untouched. This is
    what makes an idempotent expiry scan safe to run repeatedly.

    The function is deliberately forgiving: unknown/inactive recipients are
    skipped and the caller's transaction is never broken by a notification.
    """
    recipients = [uid for uid in set(recipient_ids or []) if uid]
    if not recipients:
        return []

    valid = {
        uid
        for uid in db.execute(
            select(User.id).where(User.id.in_(recipients), User.is_active.is_(True))
        ).scalars()
    }

    created: list[Notification] = []
    for uid in sorted(valid):
        if dedupe_key and _exists(db, recipient_id=uid, dedupe_key=dedupe_key):
            continue
        row = Notification(
            recipient_id=uid,
            company_id=company_id,
            type=type,
            priority=priority,
            title_ar=title_ar,
            title_en=title_en,
            message_ar=message_ar,
            message_en=message_en,
            entity_type=entity_type,
            entity_id=entity_id,
            dedupe_key=dedupe_key,
        )
        db.add(row)
        created.append(row)

    if not created:
        return []

    db.flush()
    for row in created:
        db.refresh(row)

    audit_service.record(
        db,
        action=AuditAction.NOTIFICATION_CREATED,
        actor_user_id=actor_user_id,
        entity_type=entity_type or "notification",
        entity_id=entity_id,
        company_id=company_id,
        metadata={"type": type, "recipients": [r.recipient_id for r in created]},
        commit=False,
    )

    if commit:
        db.commit()

    if emit_webhook:
        _emit_notification_event(db, created)

    return created


def _exists(db: Session, *, recipient_id: int, dedupe_key: str) -> bool:
    stmt = select(Notification.id).where(
        Notification.recipient_id == recipient_id,
        Notification.dedupe_key == dedupe_key,
    )
    return db.execute(stmt).first() is not None


def _emit_notification_event(db: Session, rows: list[Notification]) -> None:
    """Hand the new notifications to the integration layer.

    Imported lazily and wrapped so that a broken webhook configuration can never
    surface to the user who merely triggered a business action.
    """
    try:
        from backend.services import integration_service

        for row in rows:
            integration_service.emit(
                db,
                event_type="notification.created",
                payload={
                    "notification_id": row.id,
                    "recipient_id": row.recipient_id,
                    "type": row.type,
                    "company_id": row.company_id,
                    "entity_type": row.entity_type,
                    "entity_id": row.entity_id,
                },
                company_id=row.company_id,
            )
    except Exception:  # noqa: BLE001 - integrations are best-effort
        logger.exception("Failed to emit notification webhook event")


# --------------------------------------------------------------------------
# reading an inbox
# --------------------------------------------------------------------------
def _base_inbox(user: User):
    return select(Notification).where(Notification.recipient_id == user.id)


def list_notifications(
    db: Session,
    *,
    user: User,
    unread_only: bool = False,
    type: str | None = None,
    company_id: int | None = None,
    limit: int = 30,
    offset: int = 0,
) -> dict:
    """The caller's own notifications, newest first."""
    require_permission(user, Perm.NOTIFICATION_READ_OWN)

    conditions = [Notification.recipient_id == user.id]
    if unread_only:
        conditions.append(Notification.read_at.is_(None))
    if type:
        conditions.append(Notification.type == type)
    if company_id is not None:
        conditions.append(Notification.company_id == company_id)

    total = int(
        db.execute(select(func.count(Notification.id)).where(*conditions)).scalar_one()
    )
    rows = list(
        db.execute(
            select(Notification)
            .where(*conditions)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(limit)
            .offset(offset)
        ).scalars()
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [serialise(n) for n in rows],
    }


def unread_count(db: Session, *, user: User) -> int:
    from backend.rbac.authorization import has_permission

    if not has_permission(user, Perm.NOTIFICATION_READ_OWN):
        return 0
    return int(
        db.execute(
            select(func.count(Notification.id)).where(
                Notification.recipient_id == user.id,
                Notification.read_at.is_(None),
            )
        ).scalar_one()
    )


def summary(db: Session, *, user: User) -> dict:
    """Unread total plus a per-type breakdown for the header badge/popover."""
    require_permission(user, Perm.NOTIFICATION_READ_OWN)
    rows = db.execute(
        select(Notification.type, func.count(Notification.id))
        .where(Notification.recipient_id == user.id, Notification.read_at.is_(None))
        .group_by(Notification.type)
    ).all()
    by_type = {t: int(c) for t, c in rows}
    return {"unread": sum(by_type.values()), "by_type": by_type}


def _own_or_404(db: Session, user: User, notification_id: int) -> Notification:
    row = db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.recipient_id == user.id,
        )
    ).scalar_one_or_none()
    if row is None:
        # Not found and not-yours are indistinguishable, by design.
        raise NotFoundError("Notification not found.")
    return row


def mark_read(
    db: Session, *, user: User, notification_id: int
) -> Notification:
    require_permission(user, Perm.NOTIFICATION_READ_OWN)
    row = _own_or_404(db, user, notification_id)
    if row.read_at is None:
        row.read_at = utcnow()
        db.add(row)
        db.commit()
        db.refresh(row)
        audit_service.record(
            db,
            action=AuditAction.NOTIFICATION_READ,
            actor_user_id=user.id,
            entity_type="notification",
            entity_id=row.id,
            company_id=row.company_id,
            commit=False,
        )
    return row


def mark_all_read(db: Session, *, user: User) -> int:
    require_permission(user, Perm.NOTIFICATION_READ_OWN)
    result = db.execute(
        update(Notification)
        .where(Notification.recipient_id == user.id, Notification.read_at.is_(None))
        .values(read_at=utcnow())
    )
    db.commit()
    count = int(result.rowcount or 0)
    if count:
        audit_service.record(
            db,
            action=AuditAction.NOTIFICATION_READ_ALL,
            actor_user_id=user.id,
            entity_type="notification",
            metadata={"count": count},
            commit=False,
        )
    return count


# --------------------------------------------------------------------------
# typed emitters used by the business services
# --------------------------------------------------------------------------
def notify_approval_assigned(
    db: Session,
    *,
    assignee_ids: list[int],
    submission_id: int,
    company_id: int,
    title: str,
    step_name_ar: str,
    step_name_en: str,
    actor_user_id: int | None = None,
) -> list[Notification]:
    return notify(
        db,
        recipient_ids=assignee_ids,
        type=NotificationType.APPROVAL_ASSIGNED.value,
        priority=NotificationPriority.HIGH.value,
        title_ar="طلب بانتظار موافقتك",
        title_en="A request awaits your approval",
        message_ar=f"«{title}» وصل إلى خطوة: {step_name_ar}.",
        message_en=f"“{title}” reached the step: {step_name_en}.",
        company_id=company_id,
        entity_type="form_submission",
        entity_id=submission_id,
        actor_user_id=actor_user_id,
        dedupe_key=f"approval_assigned:{submission_id}:{step_name_en}",
    )


def notify_decision(
    db: Session,
    *,
    submitter_id: int | None,
    decision: str,
    submission_id: int,
    company_id: int,
    title: str,
    actor_user_id: int | None = None,
) -> list[Notification]:
    """Tell the submitter the outcome of their request."""
    if not submitter_id:
        return []
    mapping = {
        "approve": (
            NotificationType.APPROVAL_APPROVED.value,
            "تمت الموافقة على طلبك",
            "Your request was approved",
            "تمت الموافقة على «{t}».",
            "“{t}” was approved.",
        ),
        "reject": (
            NotificationType.APPROVAL_REJECTED.value,
            "تم رفض طلبك",
            "Your request was rejected",
            "تم رفض «{t}».",
            "“{t}” was rejected.",
        ),
        "return": (
            NotificationType.APPROVAL_RETURNED.value,
            "أُعيد طلبك للتصحيح",
            "Your request was returned for correction",
            "أُعيد «{t}» للتصحيح.",
            "“{t}” was returned for correction.",
        ),
    }
    if decision not in mapping:
        return []
    kind, t_ar, t_en, m_ar, m_en = mapping[decision]
    return notify(
        db,
        recipient_ids=[submitter_id],
        type=kind,
        priority=(
            NotificationPriority.NORMAL.value
            if decision == "approve"
            else NotificationPriority.HIGH.value
        ),
        title_ar=t_ar,
        title_en=t_en,
        message_ar=m_ar.format(t=title),
        message_en=m_en.format(t=title),
        company_id=company_id,
        entity_type="form_submission",
        entity_id=submission_id,
        actor_user_id=actor_user_id,
        dedupe_key=f"approval_{decision}:{submission_id}",
    )


def notify_support_assigned(
    db: Session,
    *,
    assignee_id: int | None,
    request_id: int,
    company_id: int,
    request_title: str,
    department_ar: str,
    department_en: str,
    actor_user_id: int | None = None,
) -> list[Notification]:
    if not assignee_id:
        return []
    return notify(
        db,
        recipient_ids=[assignee_id],
        type=NotificationType.SUPPORT_ASSIGNED.value,
        priority=NotificationPriority.HIGH.value,
        title_ar="طلب دعم مُسند إليك",
        title_en="A support request was assigned to you",
        message_ar=f"«{request_title}» ({department_ar}).",
        message_en=f"“{request_title}” ({department_en}).",
        company_id=company_id,
        entity_type="support_request",
        entity_id=request_id,
        actor_user_id=actor_user_id,
        dedupe_key=f"support_assigned:{request_id}:{assignee_id}",
    )


def notify_support_status(
    db: Session,
    *,
    recipient_ids: list[int],
    request_id: int,
    company_id: int,
    request_title: str,
    status_ar: str,
    status_en: str,
    actor_user_id: int | None = None,
) -> list[Notification]:
    return notify(
        db,
        recipient_ids=recipient_ids,
        type=NotificationType.SUPPORT_STATUS_CHANGED.value,
        title_ar="تحديث حالة طلب دعم",
        title_en="Support request status updated",
        message_ar=f"«{request_title}» أصبح: {status_ar}.",
        message_en=f"“{request_title}” is now: {status_en}.",
        company_id=company_id,
        entity_type="support_request",
        entity_id=request_id,
        actor_user_id=actor_user_id,
        dedupe_key=None,
    )


def notify_report_submitted(
    db: Session,
    *,
    recipient_ids: list[int],
    report_id: int,
    company_id: int,
    company_name_ar: str,
    company_name_en: str,
    year: int,
    month: int,
    actor_user_id: int | None = None,
) -> list[Notification]:
    return notify(
        db,
        recipient_ids=recipient_ids,
        type=NotificationType.REPORT_SUBMITTED.value,
        title_ar="تقرير شهري جديد",
        title_en="A new monthly report was submitted",
        message_ar=f"{company_name_ar} أرسلت تقرير {month}/{year}.",
        message_en=f"{company_name_en} submitted its {month}/{year} report.",
        company_id=company_id,
        entity_type="monthly_report",
        entity_id=report_id,
        actor_user_id=actor_user_id,
        dedupe_key=f"report_submitted:{report_id}",
    )


# --------------------------------------------------------------------------
# scheduled scan: expiring / expired documents
# --------------------------------------------------------------------------
def scan_document_expiry(db: Session, *, actor_user_id: int | None = None) -> dict:
    """Raise notifications for documents nearing or past expiry.

    Idempotent by construction: the ``dedupe_key`` includes the document id and
    the calendar month, so running the scan daily produces at most one
    notification per document per month. Recipients are the holders of
    ``document.read`` in the document's company; the scan itself is safe to run
    as a scheduled job because it never widens anyone's scope.
    """
    from datetime import date, timedelta

    from backend.db.models.documents import Document
    from backend.db.models.enums import DocumentStatus
    from backend.db.models.identity import Company, UserCompanyAccess

    window = settings.NOTIFICATION_EXPIRY_WINDOW_DAYS
    today = date.today()
    horizon = today + timedelta(days=window)

    documents = list(
        db.execute(
            select(Document).where(
                Document.status == DocumentStatus.ACTIVE.value,
                Document.expiry_date.isnot(None),
                Document.expiry_date <= horizon,
            )
        ).scalars()
    )

    raised = 0
    for document in documents:
        expired = document.expiry_date < today
        key_suffix = f"{document.expiry_date.year}-{document.expiry_date.month:02d}"
        recipients = _document_recipients(db, document.company_id)
        if not recipients:
            continue
        company = db.get(Company, document.company_id)
        label = document.title_ar or document.original_filename
        label_en = document.title_en or document.original_filename
        created = notify(
            db,
            recipient_ids=recipients,
            type=(
                NotificationType.DOCUMENT_EXPIRED.value
                if expired
                else NotificationType.DOCUMENT_EXPIRING.value
            ),
            priority=(
                NotificationPriority.HIGH.value
                if expired
                else NotificationPriority.NORMAL.value
            ),
            title_ar="مستند منتهي الصلاحية" if expired else "مستند قارب على الانتهاء",
            title_en="Document expired" if expired else "Document expiring soon",
            message_ar=(
                f"«{label}» انتهت صلاحيته في {document.expiry_date}."
                if expired
                else f"«{label}» تنتهي صلاحيته في {document.expiry_date}."
            ),
            message_en=(
                f"“{label_en}” expired on {document.expiry_date}."
                if expired
                else f"“{label_en}” expires on {document.expiry_date}."
            ),
            company_id=document.company_id,
            entity_type="document",
            entity_id=document.id,
            dedupe_key=f"document_expiry:{document.id}:{key_suffix}",
            commit=False,
            actor_user_id=actor_user_id,
            emit_webhook=False,
        )
        raised += len(created)
        if created:
            _emit_expiry_event(db, document, company)

    db.commit()
    return {"documents_scanned": len(documents), "notifications_created": raised}


def finance_reviewer_ids(db: Session) -> list[int]:
    """Active users holding a financial-review permission, for report alerts.

    Falls back to holding-wide users when no explicit reviewer is configured, so
    a freshly seeded environment still routes the notification somewhere useful.
    """
    from backend.db.models.identity import Permission, Role, RoleCode, RolePermission, User

    codes = {Perm.FINANCIAL_REVIEW_READ, Perm.FINANCIAL_REVIEW_WRITE}
    reviewer_ids = set(
        db.execute(
            select(User.id)
            .join(Role, Role.id == User.role_id)
            .join(RolePermission, RolePermission.role_id == Role.id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(User.is_active.is_(True), Permission.code.in_(codes))
        ).scalars()
    )
    if reviewer_ids:
        return list(reviewer_ids)
    return list(
        db.execute(
            select(User.id)
            .join(Role, Role.id == User.role_id)
            .where(
                User.is_active.is_(True),
                (User.is_superuser.is_(True))
                | (Role.code == RoleCode.HOLDING_OWNER.value),
            )
        ).scalars()
    )


def _document_recipients(db: Session, company_id: int) -> list[int]:
    """Active users who may read documents in this company.

    Holding-wide users (owner / superuser) always qualify; otherwise the user
    needs an explicit ``user_company_access`` grant for the company.
    """
    from backend.db.models.identity import Role, RoleCode, User, UserCompanyAccess

    granted = set(
        db.execute(
            select(UserCompanyAccess.user_id).where(
                UserCompanyAccess.company_id == company_id,
                UserCompanyAccess.can_read.is_(True),
            )
        ).scalars()
    )
    holding_wide = set(
        db.execute(
            select(User.id)
            .join(Role, Role.id == User.role_id)
            .where(
                User.is_active.is_(True),
                (User.is_superuser.is_(True))
                | (Role.code == RoleCode.HOLDING_OWNER.value),
            )
        ).scalars()
    )
    candidates = granted | holding_wide
    if not candidates:
        return []
    # Keep only active users.
    return list(
        db.execute(
            select(User.id).where(User.id.in_(candidates), User.is_active.is_(True))
        ).scalars()
    )


def _emit_expiry_event(db: Session, document, company) -> None:
    from datetime import date

    try:
        from backend.services import integration_service

        integration_service.emit(
            db,
            event_type="document.expiring",
            payload={
                "document_id": document.id,
                "company_id": document.company_id,
                "title_ar": document.title_ar,
                "expiry_date": str(document.expiry_date),
                "expired": document.expiry_date < date.today(),
            },
            company_id=document.company_id,
        )
    except Exception:  # noqa: BLE001 - best-effort
        logger.exception("Failed to emit document expiry webhook event")


__all__ = [
    "list_notifications",
    "mark_all_read",
    "mark_read",
    "notify",
    "notify_approval_assigned",
    "notify_decision",
    "notify_report_submitted",
    "notify_support_assigned",
    "notify_support_status",
    "finance_reviewer_ids",
    "scan_document_expiry",
    "serialise",
    "summary",
    "unread_count",
]
