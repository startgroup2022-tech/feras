"""Group-level administration models: Holding, Ownership and Department.

These are the Phase 2 foundations. They are deliberately small and additive:

* :class:`Holding` is a singleton-style record describing Safir Holding itself
  (legal name, registration, default currency). It does not model multi-tenant
  SaaS -- there is one Holding, and companies belong to it implicitly -- but the
  table exists so group metadata is persisted rather than hardcoded.
* :class:`Ownership` records stakes between companies (and, optionally, an
  external owner). Rows form a *history*: a stake is closed by setting
  ``status``/``effective_to`` rather than being deleted.
* :class:`Department` is a company-scoped organisational unit. A department is
  always reachable only through its owning company.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin
from backend.db.models.enums import (
    DepartmentStatus,
    HoldingStatus,
    OwnershipStatus,
)

if TYPE_CHECKING:
    from backend.db.models.identity import Company


class Holding(Base, TimestampMixin):
    """Metadata about the Holding entity itself.

    A single active row is expected, but the table is a normal table (keyed by
    ``id``) so a future multi-group deployment would not need a rewrite.
    """

    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    legal_name_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    legal_name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name_ar: Mapped[str | None] = mapped_column(String(200), nullable=True)
    display_name_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    commercial_registration: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tax_number: Mapped[str | None] = mapped_column(String(80), nullable=True)
    default_currency: Mapped[str] = mapped_column(String(8), nullable=False, default="SAR")
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=HoldingStatus.ACTIVE.value, index=True
    )


class Ownership(Base, TimestampMixin):
    """A stake in ``owned_company`` held by a company or an external owner.

    Exactly one of ``owner_company_id`` / ``external_owner_name`` is set. The
    application validates percentages and cycles; the database enforces the
    hard invariants (percentage range, non-null owner) via a check constraint.
    """

    __tablename__ = "ownerships"
    __table_args__ = (
        Index("ix_ownerships_owned", "owned_company_id", "status"),
        Index("ix_ownerships_owner", "owner_company_id"),
        UniqueConstraint(
            "owned_company_id",
            "owner_company_id",
            "external_owner_name",
            "effective_from",
            name="uq_ownerships_stake_period",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owned_company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Internal owner (another company in the group). Nullable because a stake
    # may instead be held by an external party.
    owner_company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), nullable=True
    )
    external_owner_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ownership_percentage: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=OwnershipStatus.ACTIVE.value, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    owned_company: Mapped[Company] = relationship(
        foreign_keys=[owned_company_id], backref="ownership_in"
    )
    owner_company: Mapped[Company | None] = relationship(
        foreign_keys=[owner_company_id], backref="ownership_out"
    )


class Department(Base, TimestampMixin):
    """A company-scoped department (Finance, HR, Operations, ...)."""

    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_departments_company_code"),
        Index("ix_departments_company", "company_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(180), nullable=False)
    name_en: Mapped[str] = mapped_column(String(180), nullable=False)
    manager_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    parent_department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DepartmentStatus.ACTIVE.value, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    company: Mapped[Company] = relationship(backref="departments")
