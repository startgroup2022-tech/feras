"""Persistent in-app notifications.

A notification is a durable record of something that actually happened in the
system (an approval landed in someone's queue, a document is expiring, a
support request was assigned). It is never generated decoratively: every row
is written by :mod:`backend.services.notification_service` from a real event.

Security note
-------------
A notification row is *not* an authorization grant. It stores a soft reference
(``entity_type`` / ``entity_id``) to the record it is about, but opening that
record always re-runs the normal company-scope checks. A notification that
points at another company's data therefore cannot leak it -- the target
endpoint still returns 404 for a caller who may not see it.

``recipient_id`` is the only person who may read a row; listing is always
filtered by the caller's own id, never by a company id from the request.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
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
from backend.db.models.enums import NotificationPriority, NotificationType

if TYPE_CHECKING:
    from backend.db.models.identity import Company, User


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"
    __table_args__ = (
        # Reading a user's unread inbox is the hottest query; this covers it.
        Index(
            "ix_notifications_recipient_read",
            "recipient_id",
            "read_at",
            "created_at",
        ),
        Index("ix_notifications_company", "company_id"),
        # Dedupe guard: a given recipient can only receive one row per dedupe
        # key, which is what stops an expiry scan from notifying twice for the
        # same document within the same window.
        UniqueConstraint(
            "recipient_id", "dedupe_key", name="uq_notifications_recipient_dedupe"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipient_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Soft company scope for display/grouping. NULL for holding-wide events.
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )

    type: Mapped[str] = mapped_column(
        String(40), nullable=False, default=NotificationType.SYSTEM.value, index=True
    )
    priority: Mapped[str] = mapped_column(
        String(20), nullable=False, default=NotificationPriority.NORMAL.value
    )

    title_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    title_en: Mapped[str] = mapped_column(String(200), nullable=False)
    message_ar: Mapped[str] = mapped_column(Text, nullable=False)
    message_en: Mapped[str] = mapped_column(Text, nullable=False)

    # Soft reference to the record this notification is about.
    entity_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Stable key used to prevent duplicate notifications for the same event
    # (e.g. ``document_expiring:{id}:2027-11``). NULL keys are never deduped.
    dedupe_key: Mapped[str | None] = mapped_column(String(120), nullable=True)

    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Set when an email copy was dispatched, so the adapter is not called twice.
    emailed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    recipient: Mapped["User"] = relationship(foreign_keys=[recipient_id])
    company: Mapped["Company | None"] = relationship()

    @property
    def is_read(self) -> bool:
        return self.read_at is not None


__all__ = ["Notification"]
