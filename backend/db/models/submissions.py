"""Form submissions.

A submission is one filled-in instance of a *published form version*. It pins
``form_version_id`` so the exact field set it was filled against is always
recoverable, even after the form is edited or a new version is published.

Requirement completion is tracked per submission in
:class:`SubmissionRequirement` rows (a snapshot of the requirement plus its
current satisfaction state). Documents uploaded against a requirement are linked
through :class:`Document`'s generic ``related_entity_*`` columns; the
``submission_requirement_id`` here is the stable join key.
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
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin
from backend.db.models.enums import RequirementType, SubmissionStatus

if TYPE_CHECKING:
    from backend.db.models.identity import Company, User


class FormSubmission(Base, TimestampMixin):
    __tablename__ = "form_submissions"
    __table_args__ = (
        Index("ix_form_submissions_company_status", "company_id", "status"),
        Index("ix_form_submissions_form", "form_id"),
        Index("ix_form_submissions_submitter", "submitted_by_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    form_id: Mapped[int] = mapped_column(
        ForeignKey("dynamic_forms.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    form_version_id: Mapped[int] = mapped_column(
        ForeignKey("form_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    submitted_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=SubmissionStatus.DRAFT.value, index=True
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    values: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    requirements: Mapped[list["SubmissionRequirement"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan"
    )

    @property
    def company(self) -> "Company | None":
        from sqlalchemy.orm import object_session

        session = object_session(self)
        if session is None or self.company_id is None:
            return None
        from backend.db.models.identity import Company as _Company

        return session.get(_Company, self.company_id)


class SubmissionRequirement(Base, TimestampMixin):
    """Snapshot of one requirement and whether this submission satisfies it."""

    __tablename__ = "submission_requirements"
    __table_args__ = (
        UniqueConstraint(
            "submission_id", "requirement_key", name="uq_submission_requirements_key"
        ),
        Index("ix_submission_requirements_submission", "submission_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("form_submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    form_requirement_id: Mapped[int | None] = mapped_column(
        ForeignKey("form_requirements.id", ondelete="SET NULL"), nullable=True
    )
    requirement_key: Mapped[str] = mapped_column(String(60), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    requirement_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default=RequirementType.DOCUMENT.value
    )
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_satisfied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    satisfied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    satisfied_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # A recorded override of a mandatory requirement (permission-gated).
    overridden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    submission: Mapped[FormSubmission] = relationship(back_populates="requirements")


__all__ = ["FormSubmission", "SubmissionRequirement"]
