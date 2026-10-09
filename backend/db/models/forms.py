"""Dynamic forms and their requirements.

The builder has to satisfy two competing needs: an administrator must be able
to keep editing a form, while a submission made six months ago must still render
exactly as it was submitted. They are reconciled by *versioning*:

* :class:`DynamicForm` is the stable identity of a form (code, names, scope,
  category). It is what appears in listings.
* :class:`FormVersion` is an immutable snapshot of the structure. A draft
  version may be edited freely; once published it is frozen. Changing a
  published form means creating a new draft version that copies the previous
  one -- never mutating history.
* :class:`FormField` and :class:`FormRequirement` hang off a *version*, so a
  submission that references ``form_version_id`` always resolves the exact
  field set it was filled against.

Company scope lives on the definition (``form_companies``) so that "a form
belongs to one company / selected companies / the whole holding" is a property
of the form, not of one version.
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
from backend.db.models.enums import FormScope, FormStatus, RequirementType

if TYPE_CHECKING:
    from backend.db.models.identity import Company


class DynamicForm(Base, TimestampMixin):
    """The stable identity of a configurable form definition."""

    __tablename__ = "dynamic_forms"
    __table_args__ = (Index("ix_dynamic_forms_scope_status", "scope", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    name_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    description_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    scope: Mapped[str] = mapped_column(
        String(20), nullable=False, default=FormScope.COMPANY.value, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=FormStatus.DRAFT.value, index=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    versions: Mapped[list["FormVersion"]] = relationship(
        back_populates="form",
        cascade="all, delete-orphan",
        order_by="FormVersion.version_number",
    )
    companies: Mapped[list["FormCompany"]] = relationship(
        back_populates="form", cascade="all, delete-orphan"
    )

    @property
    def published_version(self) -> "FormVersion | None":
        for version in self.versions:
            if version.status == FormStatus.PUBLISHED.value:
                return version
        return None

    @property
    def latest_version(self) -> "FormVersion | None":
        if not self.versions:
            return None
        return max(self.versions, key=lambda v: v.version_number)


class FormVersion(Base, TimestampMixin):
    """An immutable-once-published structural snapshot of a form."""

    __tablename__ = "form_versions"
    __table_args__ = (
        UniqueConstraint("form_id", "version_number", name="uq_form_versions_number"),
        Index("ix_form_versions_form_status", "form_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    form_id: Mapped[int] = mapped_column(
        ForeignKey("dynamic_forms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=FormStatus.DRAFT.value, index=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    form: Mapped[DynamicForm] = relationship(back_populates="versions")
    fields: Mapped[list["FormField"]] = relationship(
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="FormField.display_order",
    )
    requirements: Mapped[list["FormRequirement"]] = relationship(
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="FormRequirement.display_order",
    )


class FormCompany(Base):
    """Explicit company scope for a ``company``-scoped form."""

    __tablename__ = "form_companies"
    __table_args__ = (
        UniqueConstraint("form_id", "company_id", name="uq_form_companies_pair"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    form_id: Mapped[int] = mapped_column(
        ForeignKey("dynamic_forms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )

    form: Mapped[DynamicForm] = relationship(back_populates="companies")
    company: Mapped["Company"] = relationship()


class FormField(Base, TimestampMixin):
    """A configurable field on a form version.

    Validation is declarative (min/max/pattern/max length/options) and never
    executable, so a malicious administrator cannot smuggle code through the
    builder.
    """

    __tablename__ = "form_fields"
    __table_args__ = (
        UniqueConstraint("form_version_id", "key", name="uq_form_fields_version_key"),
        Index("ix_form_fields_version_order", "form_version_id", "display_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    form_version_id: Mapped[int] = mapped_column(
        ForeignKey("form_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(60), nullable=False)
    field_type: Mapped[str] = mapped_column(String(30), nullable=False)
    label_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    label_en: Mapped[str] = mapped_column(String(200), nullable=False)
    placeholder_ar: Mapped[str | None] = mapped_column(String(200), nullable=True)
    placeholder_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    help_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    help_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    default_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Declarative configuration: options, min, max, max_length, pattern,
    # visibility rules. Kept as JSON so new (still declarative) knobs can be
    # added without a schema change.
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    version: Mapped[FormVersion] = relationship(back_populates="fields")


class FormRequirement(Base, TimestampMixin):
    """A configurable requirement attached to a form version."""

    __tablename__ = "form_requirements"
    __table_args__ = (
        UniqueConstraint(
            "form_version_id", "key", name="uq_form_requirements_version_key"
        ),
        Index("ix_form_requirements_version_order", "form_version_id", "display_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    form_version_id: Mapped[int] = mapped_column(
        ForeignKey("form_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(60), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    description_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    requirement_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default=RequirementType.DOCUMENT.value
    )
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # For FIELD_VALUE requirements: which field key must be present/satisfied,
    # plus optional expected value. For DOCUMENT: allowed MIME/extension hints.
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    version: Mapped[FormVersion] = relationship(back_populates="requirements")


__all__ = [
    "DynamicForm",
    "FormVersion",
    "FormCompany",
    "FormField",
    "FormRequirement",
]
