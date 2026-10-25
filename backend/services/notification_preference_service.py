"""D11: notification channel preferences and delivery logging.

Preferences decide *whether* a channel is used for an event type; the delivery
log records what actually happened. Both are user-scoped: a caller can only
read or change their own preferences, and the log is filtered by ``user_id``.

Design rules carried from D11:

* In-app is the base channel and is always on; a preference can only add email
  or mute the event entirely.
* Email is opt-in *and* inert while ``EMAIL_PROVIDER`` is ``none``: the
  preference is recorded, but no send is attempted and the log records a
  ``skipped`` row rather than a fabricated success.
* A sensitive notification is never written to the delivery log verbatim.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.errors import ValidationError
from backend.db.models.enums import NotificationType
from backend.db.models.identity import User
from backend.db.models.notification_preferences import (
    NotificationDeliveryLog,
    NotificationPreference,
)
from backend.db.models.notifications import Notification

DEFAULT_EVENT = "*"
VALID_CHANNELS = ("in_app", "email")
VALID_EVENT_TYPES = {t.value for t in NotificationType} | {DEFAULT_EVENT}

# Notification types whose detail must not be copied into a delivery log. The
# list is a whitelist of *safe* types: anything not named here is treated as
# sensitive and its log excerpt is a neutral marker (D11).
NON_SENSITIVE_TYPES = {
    NotificationType.SYSTEM.value,
    NotificationType.REPORT_SUBMITTED.value,
    NotificationType.SUPPORT_ASSIGNED.value,
    NotificationType.SUPPORT_STATUS_CHANGED.value,
}
SENSITIVE_EXCERPT = "[redacted]"


def serialise_preference(pref: NotificationPreference) -> dict:
    return {
        "id": pref.id,
        "event_type": pref.event_type,
        "in_app": pref.in_app,
        "email": pref.email,
        "muted": pref.muted,
    }


def list_preferences(db: Session, *, user: User) -> list[NotificationPreference]:
    stmt = (
        select(NotificationPreference)
        .where(NotificationPreference.user_id == user.id)
        .order_by(NotificationPreference.event_type)
    )
    return list(db.execute(stmt).scalars())


def effective_preference(db: Session, *, user_id: int, event_type: str) -> dict:
    """The channel set for one event, resolving the user-wide ``*`` default.

    Returns a plain dict so callers (the notify pipeline, tests) never depend on
    a row existing: an unconfigured user gets the D11 default — in-app on,
    email off, not muted.
    """
    stmt = select(NotificationPreference).where(
        NotificationPreference.user_id == user_id,
        NotificationPreference.event_type.in_([event_type, DEFAULT_EVENT]),
    )
    rows = {r.event_type: r for r in db.execute(stmt).scalars()}
    specific = rows.get(event_type)
    fallback = rows.get(DEFAULT_EVENT)
    chosen = specific or fallback
    if chosen is None:
        return {"in_app": True, "email": False, "muted": False}
    return {"in_app": chosen.in_app, "email": chosen.email, "muted": chosen.muted}


def set_preference(
    db: Session,
    *,
    user: User,
    event_type: str,
    in_app: bool | None = None,
    email: bool | None = None,
    muted: bool | None = None,
) -> NotificationPreference:
    if event_type not in VALID_EVENT_TYPES:
        raise ValidationError(f"Unknown notification event type: {event_type}")

    pref = db.execute(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user.id,
            NotificationPreference.event_type == event_type,
        )
    ).scalar_one_or_none()
    if pref is None:
        pref = NotificationPreference(user_id=user.id, event_type=event_type)
        db.add(pref)
    if in_app is not None:
        pref.in_app = in_app
    if email is not None:
        pref.email = email
    if muted is not None:
        pref.muted = muted
    # A muted event has no channel; keeping the columns coherent avoids a
    # contradictory row.
    if pref.muted:
        pref.in_app = False
        pref.email = False
    elif not pref.in_app and not pref.email:
        pref.in_app = True  # in-app is the base channel (D11)
    db.commit()
    db.refresh(pref)
    return pref


def record_delivery(
    db: Session,
    *,
    notification: Notification,
    channel: str,
    status: str,
    provider: str | None = None,
    error: str | None = None,
    excerpt: str | None = None,
    commit: bool = True,
) -> NotificationDeliveryLog:
    """Append a delivery-log row for one channel attempt.

    The excerpt is minimised for a sensitive notification so the log cannot leak
    the confidential body (D11).
    """
    if channel not in VALID_CHANNELS:
        raise ValidationError(f"Unknown delivery channel: {channel}")

    if excerpt is None and notification.type in NON_SENSITIVE_TYPES:
        excerpt = notification.title_ar
    elif excerpt is None:
        excerpt = SENSITIVE_EXCERPT

    row = NotificationDeliveryLog(
        notification_id=notification.id,
        user_id=notification.recipient_id,
        channel=channel,
        status=status,
        provider=provider,
        payload_excerpt=excerpt,
        error=(error or None),
        delivered_at=datetime.now(timezone.utc) if status == "delivered" else None,
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row


def dispatch_email(
    db: Session,
    *,
    notification: Notification,
    recipient_email: str | None,
) -> NotificationDeliveryLog:
    """Attempt an email copy of a notification, recording the outcome.

    Email is only attempted when the recipient's preference enables it *and* a
    provider is configured. Otherwise a ``skipped`` row is written — the platform
    never reports an email as delivered when no send happened.
    """
    pref = effective_preference(
        db, user_id=notification.recipient_id, event_type=notification.type
    )
    if not pref["email"]:
        return record_delivery(
            db, notification=notification, channel="email", status="skipped",
            provider=settings.EMAIL_PROVIDER, error="preference_disabled",
        )
    if (settings.EMAIL_PROVIDER or "none").strip().lower() == "none":
        return record_delivery(
            db, notification=notification, channel="email", status="skipped",
            provider="none", error="provider_not_configured",
        )
    if not recipient_email or "@" not in recipient_email:
        return record_delivery(
            db, notification=notification, channel="email", status="failed",
            provider=settings.EMAIL_PROVIDER, error="no_recipient_address",
        )

    from backend.services import integration_service

    result = integration_service.send_email(
        db,
        to=[recipient_email],
        subject=notification.title_ar,
        body=notification.message_ar,
    )
    status = "delivered" if result.get("sent") else "failed"
    return record_delivery(
        db, notification=notification, channel="email", status=status,
        provider=result.get("provider"), error=None if result.get("sent") else result.get("detail"),
    )


def list_delivery_log(
    db: Session, *, user: User, limit: int = 50, offset: int = 0
) -> dict:
    base = select(NotificationDeliveryLog).where(
        NotificationDeliveryLog.user_id == user.id
    )
    total = len(list(db.execute(base).scalars()))
    stmt = (
        base.order_by(NotificationDeliveryLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = [
        {
            "id": r.id,
            "notification_id": r.notification_id,
            "channel": r.channel,
            "status": r.status,
            "attempts": r.attempts,
            "provider": r.provider,
            "payload_excerpt": r.payload_excerpt,
            "error": r.error,
            "delivered_at": r.delivered_at,
            "created_at": r.created_at,
        }
        for r in db.execute(stmt).scalars()
    ]
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


__all__ = [
    "DEFAULT_EVENT",
    "VALID_CHANNELS",
    "VALID_EVENT_TYPES",
    "effective_preference",
    "list_preferences",
    "list_delivery_log",
    "record_delivery",
    "dispatch_email",
    "serialise_preference",
    "set_preference",
]
