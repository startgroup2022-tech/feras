"""Document management.

A document is company-owned metadata plus a pointer to bytes stored outside the
database. It can be linked generically to any entity (``related_entity_type`` /
``related_entity_id``), which is how a document uploaded against a form
requirement is tied to both the requirement and the submission.

Security properties, all enforced in :mod:`backend.services.document_service`
and :mod:`backend.core.document_storage`:

* the stored key is server-generated and opaque -- the client filename is never
  used to build a path, so traversal is impossible;
* file type and size are validated against an allow-list;
* every download re-checks the caller's company scope;
* nothing is permanently deleted -- documents are archived.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin
from backend.db.models.enums import DocumentStatus

if TYPE_CHECKING:
    from backend.db.models.identity import Company, User

# A document is "expiring soon" within this many days of its expiry date. The
# value is a foundation for a future notification centre; no notification is
# sent yet.
EXPIRING_SOON_DAYS = 30


class DocumentCategory(Base, TimestampMixin):
    """A configurable document category (Contract, Licence, Quotation, ...)."""

    __tablename__ = "document_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    name_ar: Mapped[str] = mapped_column(String(160), nullable=False)
    name_en: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)


class Document(Base, TimestampMixin):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("storage_key", name="uq_documents_storage_key"),
        Index("ix_documents_company_status", "company_id", "status"),
        Index("ix_documents_category", "category_id"),
        Index("ix_documents_expiry", "expiry_date"),
        Index("ix_documents_related", "related_entity_type", "related_entity_id"),
        Index("ix_documents_submission", "submission_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("document_categories.id", ondelete="SET NULL"), nullable=True
    )
    title_ar: Mapped[str | None] = mapped_column(String(200), nullable=True)
    title_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Generic link to whatever the document belongs to.
    related_entity_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    related_entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Explicit convenience links for the form-requirement flow.
    submission_id: Mapped[int | None] = mapped_column(
        ForeignKey("form_submissions.id", ondelete="CASCADE"), nullable=True
    )
    submission_requirement_id: Mapped[int | None] = mapped_column(
        ForeignKey("submission_requirements.id", ondelete="CASCADE"), nullable=True
    )

    uploaded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DocumentStatus.ACTIVE.value, index=True
    )

    category: Mapped["DocumentCategory | None"] = relationship()

    @property
    def expiry_state(self) -> str:
        """``expired`` / ``expiring_soon`` / ``valid`` / ``none``.

        Pure data foundation: computed on read so no background job is needed.
        """
        if self.expiry_date is None:
            return "none"
        today = date.today()
        if self.expiry_date < today:
            return "expired"
        if (self.expiry_date - today).days <= EXPIRING_SOON_DAYS:
            return "expiring_soon"
        return "valid"


__all__ = ["Document", "DocumentCategory", "EXPIRING_SOON_DAYS"]
