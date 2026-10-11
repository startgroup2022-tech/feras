"""Executions 05: employees, movements and assessments (S11, S12).

Implements the *safe, independent* parts of the owner decisions and leaves the
policy-dependent parts configurable rather than hard-coded:

* **D06 (v1)** -- balances and movements are entered by authorised users with a
  movement log and an approval. There is deliberately **no** automatic payroll
  link and **no** accounting entry generation: those wait for an approved
  linking policy, and are represented only by configuration flags.
* **D05** -- a 1..5 score per criterion with an approvable weight, and a rule
  that an assessment missing a mandatory-evidence item cannot be approved. The
  scale bounds are stored as configuration constants so an approved change is a
  single edit, not a schema change.
* **D04** -- a leadership assessment is confidential; its visibility is decided
  by the confidential-access grant table, not by this module.

All money is ``NUMERIC(18, 2)`` -- never floating point.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin
from backend.db.models.enums import (
    AssessmentStatus,
    AssessmentType,
    EmployeeStatus,
    MovementStatus,
)

if TYPE_CHECKING:
    from backend.db.models.identity import Company, User

MONEY = Numeric(18, 2)

# D05: the proposed assessment scale. Held as configuration, not scattered
# literals, so approving a different range is one deliberate change.
ASSESSMENT_SCORE_MIN = 1
ASSESSMENT_SCORE_MAX = 5


class Employee(Base, TimestampMixin):
    """An employee of a subsidiary (S11).

    Salary fields are marked sensitive: they are only serialised when the caller
    holds ``employee.salary.read``.
    """

    __tablename__ = "employees"
    __table_args__ = (
        Index("ix_employees_company_status", "company_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    full_name_ar: Mapped[str] = mapped_column(String(180), nullable=False)
    full_name_en: Mapped[str | None] = mapped_column(String(180), nullable=True)
    national_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    manager_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    hire_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=EmployeeStatus.ACTIVE.value, index=True
    )
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # ---- sensitive compensation (employee.salary.read) ----
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="SAR")
    base_salary: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    housing_allowance: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    transport_allowance: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)

    # ---- manual balances (D06 v1: entered, not auto-linked) ----
    leave_balance_days: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    advance_balance: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )

    company: Mapped["Company"] = relationship()
    movements: Mapped[list["EmployeeMovement"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )
    assessments: Mapped[list["Assessment"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )


class EmployeeMovement(Base, TimestampMixin):
    """A manual leave/advance/adjustment movement (D06 v1).

    Movement rows are append-only in spirit: a decision is recorded on the row
    and never silently rewritten; corrections are new adjustment movements.
    """

    __tablename__ = "employee_movements"
    __table_args__ = (
        Index("ix_employee_movements_employee_type", "employee_id", "movement_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    movement_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    days: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="SAR")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=MovementStatus.PENDING.value, index=True
    )
    requested_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    employee: Mapped[Employee] = relationship(back_populates="movements")


class Assessment(Base, TimestampMixin):
    """An employee (S12) or confidential leadership (S23) assessment.

    For a leadership assessment ``employee_id`` is ``NULL`` and
    ``subject_user_id`` identifies the assessed leader; visibility is governed
    by the confidential-access grants (D04).
    """

    __tablename__ = "assessments"
    __table_args__ = (
        Index("ix_assessments_company_type", "company_id", "assessment_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=True, index=True
    )
    subject_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assessment_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AssessmentType.EMPLOYEE.value, index=True
    )
    period_label: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AssessmentStatus.DRAFT.value, index=True
    )
    overall_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    employee: Mapped[Employee | None] = relationship(back_populates="assessments")
    items: Mapped[list["AssessmentItem"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan"
    )

    @property
    def has_evidence_gap(self) -> bool:
        """True while any mandatory-evidence item is still incomplete (D05)."""
        return any(
            item.evidence_required and not item.evidence_complete for item in self.items
        )


class AssessmentItem(Base, TimestampMixin):
    """One criterion line of an assessment (D05).

    ``weight`` is stored per line so an approved weighting is data, and a later
    approved change is a new assessment rather than an in-place edit of history.
    """

    __tablename__ = "assessment_items"
    __table_args__ = (
        Index("ix_assessment_items_assessment", "assessment_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    criterion_code: Mapped[str] = mapped_column(String(60), nullable=False)
    criterion_name_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    criterion_name_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    weight: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False, default=Decimal("1"))
    score: Mapped[Decimal | None] = mapped_column(Numeric(4, 2), nullable=True)
    evidence_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_complete: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    assessment: Mapped[Assessment] = relationship(back_populates="items")
