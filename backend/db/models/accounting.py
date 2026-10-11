"""Executions 04 & 12: opening balances, holding accounting, budgets, KPIs.

Implements the safe, independently-specified parts of the owner decisions and
leaves the policy-dependent parts as configuration:

* **D08** -- an opening balance is entered by an authorised user, optionally
  guided by the last approved financial summary, and is **not** auto-carried
  from December before the new opening balance is reviewed and approved. Both
  "opening" and "carry-forward" rows are *balances*, never revenue.
* **D01** -- a double-entry ledger. An approved (posted) entry is never edited
  in place; a correction is a reversal or a documented adjustment. There is
  **no** bank-transfer endpoint and **no** automatic posting from other modules.
  Tax, fiscal-year, invoice and asset *policy* are not hard-coded: they are
  configuration rows/columns that wait for accountant-approved values.
* **D07** -- budgets preserve their source and version; an approved budget is
  superseded, never silently overwritten.
* **D02** -- KPI definitions carry their data source, calculation method and
  period so a metric is always reproducible.
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
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin
from backend.db.models.enums import (
    AccountType,
    BudgetStatus,
    InvoiceStatus,
    JournalStatus,
    OpeningBalanceKind,
    OpeningBalanceStatus,
)

if TYPE_CHECKING:
    from backend.db.models.identity import Company, User

MONEY = Numeric(18, 2)


class OpeningBalance(Base, TimestampMixin):
    """An opening or carry-forward balance for a company and period (D08)."""

    __tablename__ = "opening_balances"
    __table_args__ = (
        Index("ix_opening_balances_company_period", "company_id", "period_year", "period_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(
        String(20), nullable=False, default=OpeningBalanceKind.OPENING.value
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=OpeningBalanceStatus.DRAFT.value, index=True
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="SAR")
    bank: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    cash: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    receivables: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    debts: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    # Optional guidance: the approved financial summary this was drawn from.
    source_summary_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("financial_summary_versions.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped["Company"] = relationship()


class Account(Base, TimestampMixin):
    """A chart-of-accounts entry (D01)."""

    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_account_company_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    name_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    account_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="SAR")
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    company: Mapped["Company"] = relationship()


class Journal(Base, TimestampMixin):
    """A double-entry journal (D01).

    A journal is never edited once posted. ``reversal_of_id`` links a reversal
    to the entry it corrects.
    """

    __tablename__ = "journals"
    __table_args__ = (
        Index("ix_journals_company_date", "company_id", "entry_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    fiscal_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fiscal_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=JournalStatus.DRAFT.value, index=True
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="SAR")
    reversal_of_id: Mapped[int | None] = mapped_column(
        ForeignKey("journals.id", ondelete="SET NULL"), nullable=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    posted_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped["Company"] = relationship()
    lines: Mapped[list["JournalLine"]] = relationship(
        back_populates="journal", cascade="all, delete-orphan"
    )


class JournalLine(Base, TimestampMixin):
    """One debit or credit line of a journal. Exactly one of debit/credit is set."""

    __tablename__ = "journal_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    journal_id: Mapped[int] = mapped_column(
        ForeignKey("journals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    debit: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    credit: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_centre: Mapped[str | None] = mapped_column(String(80), nullable=True)

    journal: Mapped[Journal] = relationship(back_populates="lines")


class FiscalPeriod(Base, TimestampMixin):
    """A fiscal period for the holding ledger (D01)."""

    __tablename__ = "fiscal_periods"
    __table_args__ = (
        UniqueConstraint("company_id", "year", "month", name="uq_fiscal_period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    is_closed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    closed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Invoice(Base, TimestampMixin):
    """An invoice (S27). Policy fields are data, not hard-coded rules (D01)."""

    __tablename__ = "invoices"
    __table_args__ = (
        Index("ix_invoices_company_status", "company_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    party_name: Mapped[str] = mapped_column(String(200), nullable=False)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="SAR")
    total: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    settled_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    # Tax rate is *configuration* (accountant-approved); default 0, never assumed.
    tax_rate: Mapped[Decimal] = mapped_column(
        Numeric(6, 3), nullable=False, default=Decimal("0"), server_default="0"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=InvoiceStatus.DRAFT.value, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    company: Mapped["Company"] = relationship()
    lines: Mapped[list["InvoiceLine"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )
    settlements: Mapped[list["Settlement"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )


class InvoiceLine(Base, TimestampMixin):
    __tablename__ = "invoice_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("1"))
    unit_price: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))

    invoice: Mapped[Invoice] = relationship(back_populates="lines")


class Settlement(Base, TimestampMixin):
    """A recorded payment against an invoice (S27)."""

    __tablename__ = "settlements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="SAR")
    settled_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    recorded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    invoice: Mapped[Invoice] = relationship(back_populates="settlements")


class Asset(Base, TimestampMixin):
    """A fixed asset (S28). Depreciation policy is configuration (D01)."""

    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    acquisition_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    cost: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="SAR")
    # Depreciation method/rate are accountant-approved configuration, not code.
    depreciation_method: Mapped[str | None] = mapped_column(String(40), nullable=True)
    depreciation_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    company: Mapped["Company"] = relationship()


class Budget(Base, TimestampMixin):
    """A budget with preserved source and version (D07)."""

    __tablename__ = "budgets"
    __table_args__ = (
        Index("ix_budgets_company_year", "company_id", "fiscal_year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="SAR")
    total_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=BudgetStatus.DRAFT.value, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    supersedes_id: Mapped[int | None] = mapped_column(
        ForeignKey("budgets.id", ondelete="SET NULL"), nullable=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped["Company"] = relationship()


class KpiDefinition(Base, TimestampMixin):
    """A manageable KPI definition with source, method and period (D02)."""

    __tablename__ = "kpi_definitions"
    __table_args__ = (
        Index("ix_kpi_definitions_company", "company_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    code: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    name_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    data_source: Mapped[str] = mapped_column(String(200), nullable=False)
    calculation_method: Mapped[str] = mapped_column(Text, nullable=False)
    period_label: Mapped[str] = mapped_column(String(60), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    target_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
