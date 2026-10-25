"""D11: notification channel preferences and the delivery log.

The owner decision D11 makes the in-platform notification centre the base, with
email *optional per event type and user preference*, and requires that a
sensitive notification never leaks confidential detail in its subject or body.
This module records both halves:

* :class:`NotificationPreference` -- a per-user, per-event-type channel choice.
  The default is in-app only; email is opt-in and remains inert until the owner
  configures a provider (no provider is invented here).
* :class:`NotificationDeliveryLog` -- one row per attempted channel delivery,
  carrying status, attempt count and a *minimised* subject/body. A failure is
  recorded rather than swallowed, so retry and failure handling is observable.

Neither table is an authorization grant. A preference can only be read or
written by its own user, and the delivery log is likewise user-scoped.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from backend.db.models.identity import User


class NotificationPreference(Base, TimestampMixin):
    """A user's channel choice for one event type (D11).

    ``event_type`` is a ``NotificationType`` value, or ``"*"`` for the user's
    default. The unique constraint makes the pair a single switch, so a lookup
    is deterministic and there is never a duplicate preference row.
    """

    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "event_type", name="uq_notification_preferences_user_event"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # A NotificationType value, or "*" for the user-wide default.
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)

    # In-app is the base channel and cannot be turned off by a preference row;
    # it is stored so the effective channel set is explicit and auditable.
    in_app: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    # Email is optional and inert until a provider is configured (D11).
    email: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    # A user may mute a category entirely (it is then not created at all).
    muted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    user: Mapped["User"] = relationship(foreign_keys=[user_id])


class NotificationDeliveryLog(Base, TimestampMixin):
    """One attempted delivery of a notification over one channel (D11).

    ``payload_excerpt`` is deliberately a *minimised* copy: for a sensitive
    notification it holds only a neutral marker, never the confidential text,
    so the log itself cannot become a leak. ``attempts`` supports retry and
    failure handling without a second delivery happening silently.
    """

    __tablename__ = "notification_delivery_log"
    __table_args__ = (
        Index("ix_notification_delivery_user_channel", "user_id", "channel"),
        Index("ix_notification_delivery_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    notification_id: Mapped[int | None] = mapped_column(
        ForeignKey("notifications.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Minimised excerpt only; a sensitive notification stores a neutral marker.
    payload_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


__all__ = ["NotificationPreference", "NotificationDeliveryLog"]
