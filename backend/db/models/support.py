"""Support request models.

A subsidiary raises a simple request to the Holding; the Holding assigns it to
a department (derived from the category) and moves it through four statuses.
No approval matrix, no SLA engine -- those are future modules.
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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin
from backend.db.models.enums import SupportCategory, SupportStatus

if TYPE_CHECKING:
    from backend.db.models.identity import Company, User

# Which role owns a request of each category. Used to derive the responsible
# department without inventing a workflow table.
CATEGORY_OWNER_ROLE = {
    SupportCategory.ACCOUNTING.value: "accountant",
    SupportCategory.BUSINESS_DEVELOPMENT.value: "business_development",
    SupportCategory.MARKETING.value: "marketing",
    SupportCategory.DESIGN.value: "designer",
    SupportCategory.GENERAL.value: "holding_owner",
}


class SupportRequest(Base, TimestampMixin):
    __tablename__ = "support_requests"
    __table_args__ = (
        Index("ix_support_requests_company_status", "company_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(
        String(30), nullable=False, default=SupportCategory.GENERAL.value, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SupportStatus.NEW.value, index=True
    )
    requested_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_to_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped["Company"] = relationship(back_populates="support_requests")
    requested_by: Mapped["User | None"] = relationship(foreign_keys=[requested_by_id])
    assigned_to: Mapped["User | None"] = relationship(foreign_keys=[assigned_to_id])
    comments: Mapped[list["SupportRequestComment"]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )
    attachments: Mapped[list["SupportRequestAttachment"]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )

    @property
    def responsible_department(self) -> str:
        return CATEGORY_OWNER_ROLE.get(self.category, "holding_owner")


class SupportRequestComment(Base, TimestampMixin):
    __tablename__ = "support_request_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("support_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(nullable=False, default=False)

    request: Mapped[SupportRequest] = relationship(back_populates="comments")
    author: Mapped["User | None"] = relationship()


class SupportRequestAttachment(Base, TimestampMixin):
    __tablename__ = "support_request_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("support_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    request: Mapped[SupportRequest] = relationship(back_populates="attachments")
