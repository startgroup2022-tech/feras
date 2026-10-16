"""Execution 02: subsidiary financial summaries, special items and corrections.

This module implements the approved financial workflow of spec section 14.1 and
the F-03 / F-04 / F-06 screens (S05, S06, S08). It is deliberately *additive*:
the existing :mod:`backend.db.models.report` module (the simple ``MonthlyReport``
and its accountant review) is untouched and keeps working, so no existing API,
dashboard query or migration is invalidated.

Model shape (spec Table 74):

    FinancialPeriod             one per (company, year, month); owns many versions
      └─ FinancialSummaryVersion    a versioned snapshot (draft..approved)
            ├─ FinancialSummaryItem        values, each snapshotting its definition
            └─ FinancialBankAttachment     the mandatory bank statement
      └─ FinancialReviewAction     the append-only decision history

Invariants enforced in the service layer (and by the schema here):

* at most one **effective** (approved) version per period;
* an approved version is never mutated -- a correction is a *new* version that
  links back to the original, and the original is retained;
* money is ``NUMERIC(18, 2)`` -- never floating point.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin
from backend.db.models.enums import (
    FinancialInclusionRule,
    FinancialItemCategory,
    FinancialItemKind,
    FinancialSummaryStatus,
)

if TYPE_CHECKING:
    from backend.db.models.identity import Company, User

# Exact money. Mirrors ``backend.db.models.report.MONEY``.
MONEY = Numeric(18, 2)


class FinancialPeriod(Base, TimestampMixin):
    """One financial period for one company.

    ``effective_version_id`` points at the single approved version that the
    reporting layer must use. It is ``NULL`` while no version has been approved
    yet. The period is the identity that links every version of the same
    (company, year, month) together (spec section 14.1: "هوية الفترة الواحدة
    تربط جميع نسخها").
    """

    __tablename__ = "financial_periods"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "period_year", "period_month", name="uq_financial_period"
        ),
        Index("ix_financial_periods_company_period", "company_id", "period_year", "period_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..12
    # The base currency of the company for this period, snapshotted so a later
    # currency change (D09) cannot retroactively reinterpret stored amounts.
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="SAR")

    effective_version_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )

    company: Mapped["Company"] = relationship(back_populates="financial_periods")
    versions: Mapped[list["FinancialSummaryVersion"]] = relationship(
        back_populates="period",
        cascade="all, delete-orphan",
        foreign_keys="FinancialSummaryVersion.period_id",
    )
    # Read-only convenience view over the plain-integer pointer. Kept viewonly so
    # persistence is driven solely by ``effective_version_id``.
    effective_version: Mapped["FinancialSummaryVersion | None"] = relationship(
        primaryjoin="FinancialPeriod.effective_version_id == FinancialSummaryVersion.id",
        foreign_keys="FinancialPeriod.effective_version_id",
        viewonly=True,
    )
    review_actions: Mapped[list["FinancialReviewAction"]] = relationship(
        back_populates="period", cascade="all, delete-orphan"
    )


class FinancialSummaryVersion(Base, TimestampMixin):
    """A single version of a company's monthly financial summary (F-03).

    ``version_number`` is 1 for the original, 2 for the first corrective
    version, and so on. ``corrects_version_id`` links a corrective version to
    the approved version it replaces; the original is never modified.
    """

    __tablename__ = "financial_summary_versions"
    __table_args__ = (
        UniqueConstraint("period_id", "version_number", name="uq_financial_version_number"),
        Index("ix_financial_versions_period_status", "period_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period_id: Mapped[int] = mapped_column(
        ForeignKey("financial_periods.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default=FinancialSummaryStatus.DRAFT.value,
        index=True,
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="SAR")

    # A corrective version points at the approved version it corrects. NULL for
    # the original version.
    corrects_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("financial_summary_versions.id", ondelete="SET NULL"), nullable=True
    )

    # ---- figures entered by the subsidiary manager ----
    submitted_revenue: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    submitted_expenses: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    # ---- effective (calculated) figures, recomputed on every change ----
    effective_revenue: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    effective_expenses: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    calculated_result: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    # ---- closing balances (period-end; independent of the result) ----
    closing_bank_balance: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    closing_cash_balance: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    calculated_total_cash: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    outstanding_debts: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    customer_receivables: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)

    manager_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # A free-text reference the manager records; the mandatory *file* is a
    # FinancialBankAttachment. Kept so a bank reference can be cited even before
    # the file is uploaded.
    bank_statement_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # The accountant's mandatory note when returning for correction.
    return_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    period: Mapped[FinancialPeriod] = relationship(
        back_populates="versions", foreign_keys=[period_id]
    )
    company: Mapped["Company"] = relationship()
    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_id])
    submitted_by: Mapped["User | None"] = relationship(foreign_keys=[submitted_by_id])
    reviewed_by: Mapped["User | None"] = relationship(foreign_keys=[reviewed_by_id])
    approved_by: Mapped["User | None"] = relationship(foreign_keys=[approved_by_id])
    corrects_version: Mapped["FinancialSummaryVersion | None"] = relationship(
        remote_side="FinancialSummaryVersion.id", foreign_keys=[corrects_version_id]
    )
    items: Mapped[list["FinancialSummaryItem"]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )
    bank_attachments: Mapped[list["FinancialBankAttachment"]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )


class FinancialItemDefinition(Base, TimestampMixin):
    """A stable, reusable special-item definition (F-04).

    The definition carries the *rules* (category, kind, inclusion). A summary
    item snapshots those rules at submission time, so editing a definition later
    never rewrites history.
    """

    __tablename__ = "financial_item_definitions"
    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_financial_item_definition_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    description_ar: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(
        String(24), nullable=False, default=FinancialItemCategory.OTHER.value
    )
    kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default=FinancialItemKind.OTHER.value
    )
    inclusion_rule: Mapped[str] = mapped_column(
        String(16), nullable=False, default=FinancialInclusionRule.INCLUDED.value
    )
    # Whether this definition may be picked by a company manager in the UI.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=false())
    # Approved owner-decision reference for service items (spec S06).
    decision_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)

    company: Mapped["Company"] = relationship()


class FinancialSummaryItem(Base, TimestampMixin):
    """One special-item value attached to a summary version.

    The definition's rules are snapshotted here (name/category/kind/inclusion)
    so the calculation and the audit trail stay faithful even if the definition
    is later edited or deactivated.
    """

    __tablename__ = "financial_summary_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("financial_summary_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    definition_id: Mapped[int | None] = mapped_column(
        ForeignKey("financial_item_definitions.id", ondelete="SET NULL"), nullable=True
    )
    # ---- definition snapshot ----
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    inclusion_rule: Mapped[str] = mapped_column(String(16), nullable=False)
    decision_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)

    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="SAR")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    version: Mapped[FinancialSummaryVersion] = relationship(back_populates="items")
    definition: Mapped["FinancialItemDefinition | None"] = relationship()


class FinancialBankAttachment(Base, TimestampMixin):
    """The mandatory bank statement attached to a summary version (F-03).

    Bytes live outside the database under an opaque ``storage_key`` (reuse of
    the existing private attachment architecture). A statement is served only
    through the authenticated, company-scoped download route -- never through a
    public website path.
    """

    __tablename__ = "financial_bank_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("financial_summary_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uploaded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    version: Mapped[FinancialSummaryVersion] = relationship(back_populates="bank_attachments")


class FinancialReviewAction(Base, TimestampMixin):
    """Append-only history of every workflow decision on a period.

    Records who did what, when, and -- for a return -- the mandatory note. This
    is what makes "the resend/approve of the same request does not create an
    independent version or a duplicate notice" auditable.
    """

    __tablename__ = "financial_review_actions"
    __table_args__ = (
        Index("ix_financial_review_actions_period", "period_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period_id: Mapped[int] = mapped_column(
        ForeignKey("financial_periods.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_id: Mapped[int | None] = mapped_column(
        ForeignKey("financial_summary_versions.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    period: Mapped[FinancialPeriod] = relationship(back_populates="review_actions")
    actor: Mapped["User | None"] = relationship()


__all__ = [
    "FinancialPeriod",
    "FinancialSummaryVersion",
    "FinancialItemDefinition",
    "FinancialSummaryItem",
    "FinancialBankAttachment",
    "FinancialReviewAction",
]
