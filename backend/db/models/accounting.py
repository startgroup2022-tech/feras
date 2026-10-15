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
    InvoiceDirection,
    InvoiceStatus,
    JournalStatus,
    KpiDirection,
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

    @property
    def total_cash(self) -> Decimal | None:
        """Bank + cash (AC-04). Computed, never accepted from the client.

        Returns ``None`` only when both components are absent, so a genuine zero
        balance is still distinguishable from "not entered".
        """
        if self.bank is None and self.cash is None:
            return None
        return (self.bank or Decimal("0")) + (self.cash or Decimal("0"))


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
    # S27: issued (receivable "مستحق لنا") or received (payable "مستحق علينا").
    direction: Mapped[str] = mapped_column(
        String(20), nullable=False, default=InvoiceDirection.ISSUED.value,
        server_default=InvoiceDirection.ISSUED.value, index=True,
    )
    party_id: Mapped[int | None] = mapped_column(
        ForeignKey("parties.id", ondelete="SET NULL"), nullable=True
    )
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
    # S27/AC-27: the invoice and its ledger entry keep *one* reference. The
    # link is set once, explicitly, by the accountant (invoice-posting timing is
    # D01-gated); it is unique, so a second invoice cannot point at the same
    # entry and re-linking the same pair is refused rather than duplicated.
    journal_id: Mapped[int | None] = mapped_column(
        ForeignKey("journals.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    company: Mapped["Company"] = relationship()
    journal: Mapped["Journal | None"] = relationship(foreign_keys=[journal_id])
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




class AccountingPolicy(Base, TimestampMixin):
    """An accountant-approved accounting policy (D01).

    Tax, fiscal-year, invoice and asset policy are *configuration*, never
    hard-coded assumptions. A policy is inert until an accountant approves it:
    ``approved_at``/``approved_by_id`` are the only way a value becomes
    effective, and the effective-date pair distinguishes *when a rule starts*
    from *when it was approved*. A newer approved version supersedes the
    previous one; the previous row is retained, never edited, so history is
    preserved (D01).
    """

    __tablename__ = "accounting_policies"
    __table_args__ = (
        # One approved version per (company, kind) at a time; historical rows
        # keep their own number.
        UniqueConstraint(
            "company_id", "kind", "version", name="uq_accounting_policy_version"
        ),
        Index("ix_accounting_policies_company_kind", "company_id", "kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # NULL company_id means a holding-wide default; a company row overrides it.
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # A PolicyKind value (tax, fiscal_year, invoice, asset, currency).
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    # Policy payload is data so a new rule needs no migration.
    value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    value_text: Mapped[str | None] = mapped_column(String(300), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Draft until approved; approval is an explicit accountant act (D01).
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default="draft", index=True
    )
    approved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    supersedes_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounting_policies.id", ondelete="SET NULL"), nullable=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    company: Mapped["Company | None"] = relationship(foreign_keys=[company_id])


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
    # ---- D02 target-vs-actual (configurable, inactive until approved) ----
    # ``metric_key`` names the dashboard metric that supplies the actual value
    # (see ``METRIC_RESOLVERS``). NULL means "definition only, no live actual",
    # so an unconfigured KPI never invents a number.
    metric_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # ``up`` = a larger actual is better; ``down`` = smaller is better. Drives
    # the variance sign so "positive" always means "favourable".
    direction: Mapped[str] = mapped_column(
        String(10), nullable=False, default=KpiDirection.UP.value, server_default="up"
    )
    # A definition is never *active* until an authorised approval flips this.
    # ``target_value``/``metric_key`` may be configured while still inert, so
    # the whole workflow can be prepared without inventing a business approval.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    approved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class Party(Base, TimestampMixin):
    """A customer or supplier the holding deals with (S27).

    One party directory backs both issued and received invoices, so a receivable
    and a payable for the same counterparty stay on one record instead of being
    duplicated (spec §15, D01).
    """

    __tablename__ = "parties"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_party_company_name"),
        Index("ix_parties_company_type", "company_id", "party_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    party_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="customer", server_default="customer"
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="SAR")
    contact: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    company: Mapped["Company"] = relationship()


class CompanyInterbalance(Base, TimestampMixin):
    """A recorded inter-company balance (S27, spec §15, D01).

    Records the *reason* and the *currency* of a balance between the holding and
    a company. It never imposes a service fee and never treats a transfer as
    revenue -- the balance is a balance, and the currency is preserved so two
    currencies are never silently combined.
    """

    __tablename__ = "company_interbalances"
    __table_args__ = (
        Index("ix_interbalances_company", "company_id", "counterparty_company_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    counterparty_company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    counterparty_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="SAR")
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    journal_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    recorded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    company: Mapped["Company"] = relationship(foreign_keys=[company_id])
