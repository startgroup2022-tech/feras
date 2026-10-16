"""Opening balances, holding accounting, budgets and KPIs (D01/D07/D08/D02).

Policy-dependent behaviour is deliberately absent:

* an opening balance is **not** auto-carried from December; a carry-forward is
  created only on an explicit, approved instruction (D08);
* a posted journal is immutable -- correction is by a reversal entry, never an
  in-place edit (D01);
* there is **no** bank-transfer endpoint and no cross-module automatic posting;
* tax rate, depreciation method/rate and invoice policy are *data* that default
  to neutral values and wait for accountant-approved configuration (D01);
* an approved budget is superseded by a new version, never overwritten (D07).
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.errors import ConflictError, NotFoundError, ValidationError
from backend.db.base import utcnow
from backend.db.models.audit_actions import AuditAction
from backend.db.models.accounting import (
    Account,
    AccountingPolicy,
    Asset,
    Budget,
    CompanyInterbalance,
    FiscalPeriod,
    Invoice,
    InvoiceLine,
    Journal,
    JournalLine,
    KpiDefinition,
    MonthlyFinancialReport,
    OpeningBalance,
    Party,
    Settlement,
)
from backend.db.models.enums import (
    AccountType,
    BudgetStatus,
    PolicyKind,
    PolicyStatus,
    InvoiceDirection,
    InvoiceStatus,
    JournalStatus,
    KpiDirection,
    MonthlyFinancialReportStatus,
    NotificationType,
    OpeningBalanceStatus,
)
from backend.db.models.financial import FinancialPeriod, FinancialSummaryVersion
from backend.db.models.identity import User
from backend.rbac.authorization import (
    accessible_company_ids,
    require_company_access,
    require_permission,
)
from backend.rbac.permissions import Perm
from backend.services import audit_service, kpi_service, notification_service

ZERO = Decimal("0")


# --------------------------------------------------------------------------
# opening balances (D08)
# --------------------------------------------------------------------------
def create_opening_balance(
    db: Session, *, user: User, company_id: int, period_year: int,
    kind: str = "opening", period_month: int | None = None, currency: str = "SAR",
    bank=None, cash=None, receivables=None, debts=None,
    source_summary_version_id: int | None = None, notes: str | None = None,
    ip_address: str | None = None, user_agent: str | None = None,
) -> OpeningBalance:
    require_permission(user, Perm.OPENING_BALANCE_MANAGE)
    require_company_access(user, company_id, write=True)
    ob = OpeningBalance(
        company_id=company_id, period_year=period_year, period_month=period_month,
        kind=kind, status=OpeningBalanceStatus.DRAFT.value, currency=currency,
        bank=bank, cash=cash, receivables=receivables, debts=debts,
        source_summary_version_id=source_summary_version_id, notes=notes,
        created_by_id=user.id,
    )
    db.add(ob)
    db.commit()
    db.refresh(ob)
    audit_service.record(db, action=AuditAction.OPENING_BALANCE_CREATED, actor_user_id=user.id,
                         entity_type="opening_balance", entity_id=ob.id, company_id=company_id,
                         ip_address=ip_address, user_agent=user_agent)
    return ob


def submit_opening_balance(
    db: Session, *, user: User, opening_balance_id: int,
    ip_address: str | None = None, user_agent: str | None = None,
) -> OpeningBalance:
    require_permission(user, Perm.OPENING_BALANCE_MANAGE)
    ob = _get_opening_balance(db, user=user, opening_balance_id=opening_balance_id)
    require_company_access(user, ob.company_id, write=True)
    if ob.status == OpeningBalanceStatus.APPROVED.value:
        raise ConflictError("An approved opening balance is immutable.")
    ob.status = OpeningBalanceStatus.SUBMITTED.value
    db.add(ob)
    db.commit()
    db.refresh(ob)
    audit_service.record(db, action=AuditAction.OPENING_BALANCE_SUBMITTED, actor_user_id=user.id,
                         entity_type="opening_balance", entity_id=ob.id, company_id=ob.company_id,
                         ip_address=ip_address, user_agent=user_agent)
    return ob


def approve_opening_balance(
    db: Session, *, user: User, opening_balance_id: int,
    ip_address: str | None = None, user_agent: str | None = None,
) -> OpeningBalance:
    require_permission(user, Perm.OPENING_BALANCE_APPROVE)
    ob = _get_opening_balance(db, user=user, opening_balance_id=opening_balance_id)
    require_company_access(user, ob.company_id, write=True)
    if ob.status != OpeningBalanceStatus.SUBMITTED.value:
        raise ConflictError("Only a submitted opening balance can be approved.")
    ob.status = OpeningBalanceStatus.APPROVED.value
    ob.approved_by_id = user.id
    ob.approved_at = utcnow()
    db.add(ob)
    db.commit()
    db.refresh(ob)
    audit_service.record(db, action=AuditAction.OPENING_BALANCE_APPROVED, actor_user_id=user.id,
                         entity_type="opening_balance", entity_id=ob.id, company_id=ob.company_id,
                         ip_address=ip_address, user_agent=user_agent)
    # D08: approval makes the balance effective. It is NOT carried forward
    # automatically -- a carry-forward row must be created explicitly.
    return ob


def _get_opening_balance(db: Session, *, user: User, opening_balance_id: int) -> OpeningBalance:
    ob = db.get(OpeningBalance, opening_balance_id)
    if ob is None:
        raise NotFoundError("Opening balance not found.")
    require_company_access(user, ob.company_id)
    return ob


def list_opening_balances(db: Session, *, user: User, company_id: int | None = None) -> list[OpeningBalance]:
    require_permission(user, Perm.OPENING_BALANCE_READ)
    stmt = select(OpeningBalance).order_by(OpeningBalance.period_year.desc())
    allowed = accessible_company_ids(user)
    if allowed is not None:
        stmt = stmt.where(OpeningBalance.company_id.in_(allowed)) if allowed else stmt.where(False)
    if company_id is not None:
        stmt = stmt.where(OpeningBalance.company_id == company_id)
    return list(db.execute(stmt).scalars())


def serialise_opening_balance(ob: OpeningBalance) -> dict:
    return {
        "id": ob.id, "company_id": ob.company_id, "period_year": ob.period_year,
        "period_month": ob.period_month, "kind": ob.kind, "status": ob.status,
        "currency": ob.currency, "bank": ob.bank, "cash": ob.cash,
        "receivables": ob.receivables, "debts": ob.debts,
        "total_cash": ob.total_cash,
        "source_summary_version_id": ob.source_summary_version_id, "notes": ob.notes,
        "approved_by_id": ob.approved_by_id, "approved_at": ob.approved_at,
        "created_at": ob.created_at,
    }


# --------------------------------------------------------------------------
# chart of accounts (D01)
# --------------------------------------------------------------------------
def create_account(db: Session, *, user: User, company_id: int, code: str, name_ar: str,
                   account_type: str, name_en: str | None = None, parent_id: int | None = None,
                   currency: str = "SAR", description: str | None = None,
                   ip_address: str | None = None, user_agent: str | None = None) -> Account:
    require_permission(user, Perm.ACCOUNT_MANAGE)
    require_company_access(user, company_id, write=True)
    existing = db.execute(
        select(Account).where(Account.company_id == company_id, Account.code == code)
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("An account with this code already exists for the company.")
    account = Account(company_id=company_id, code=code, name_ar=name_ar, name_en=name_en,
                      account_type=account_type, parent_id=parent_id, currency=currency,
                      description=description, is_active=True)
    db.add(account)
    db.commit()
    db.refresh(account)
    audit_service.record(db, action=AuditAction.ACCOUNT_CREATED, actor_user_id=user.id,
                         entity_type="account", entity_id=account.id, company_id=company_id,
                         ip_address=ip_address, user_agent=user_agent)
    return account


def list_accounts(db: Session, *, user: User, company_id: int | None = None) -> list[Account]:
    require_permission(user, Perm.ACCOUNT_READ)
    stmt = select(Account).order_by(Account.code)
    allowed = accessible_company_ids(user)
    if allowed is not None:
        stmt = stmt.where(Account.company_id.in_(allowed)) if allowed else stmt.where(False)
    if company_id is not None:
        stmt = stmt.where(Account.company_id == company_id)
    return list(db.execute(stmt).scalars())


def serialise_account(a: Account) -> dict:
    return {
        "id": a.id, "company_id": a.company_id, "code": a.code, "name_ar": a.name_ar,
        "name_en": a.name_en, "account_type": a.account_type, "parent_id": a.parent_id,
        "currency": a.currency, "is_active": a.is_active, "description": a.description,
    }


# --------------------------------------------------------------------------
# journals (D01: double-entry, immutable once posted)
# --------------------------------------------------------------------------
def create_journal(
    db: Session, *, user: User, company_id: int, entry_date, lines: list[dict],
    description: str | None = None, currency: str = "SAR", number: str | None = None,
    ip_address: str | None = None, user_agent: str | None = None,
) -> Journal:
    require_permission(user, Perm.JOURNAL_CREATE)
    require_company_access(user, company_id, write=True)
    if not lines:
        raise ValidationError("A journal requires at least one line.")

    journal = Journal(company_id=company_id, entry_date=entry_date, number=number,
                      description=description, currency=currency,
                      status=JournalStatus.DRAFT.value, created_by_id=user.id,
                      fiscal_year=entry_date.year if entry_date else None,
                      fiscal_month=entry_date.month if entry_date else None)
    db.add(journal)
    db.flush()
    for line in lines:
        account_id = line.get("account_id")
        account = db.get(Account, account_id) if account_id else None
        if account is None or account.company_id != company_id:
            raise ValidationError("Every journal line must reference an account of the company.")
        db.add(JournalLine(
            journal_id=journal.id, account_id=account_id,
            debit=line.get("debit", ZERO) or ZERO, credit=line.get("credit", ZERO) or ZERO,
            description=line.get("description"), cost_centre=line.get("cost_centre"),
        ))
    db.commit()
    db.refresh(journal)
    audit_service.record(db, action=AuditAction.JOURNAL_CREATED, actor_user_id=user.id,
                         entity_type="journal", entity_id=journal.id, company_id=company_id,
                         ip_address=ip_address, user_agent=user_agent)
    return journal


def post_journal(db: Session, *, user: User, journal_id: int,
                 ip_address: str | None = None, user_agent: str | None = None) -> Journal:
    """Post a journal after validating it balances (D01: double-entry)."""
    require_permission(user, Perm.JOURNAL_POST)
    journal = _get_journal(db, user=user, journal_id=journal_id)
    require_company_access(user, journal.company_id, write=True)
    if journal.status != JournalStatus.DRAFT.value:
        raise ConflictError("Only a draft journal can be posted.")

    total_debit = sum((line.debit or ZERO) for line in journal.lines)
    total_credit = sum((line.credit or ZERO) for line in journal.lines)
    if total_debit != total_credit:
        raise ValidationError("The journal does not balance (debits must equal credits).")
    if total_debit == ZERO:
        raise ValidationError("The journal has no value.")

    journal.status = JournalStatus.POSTED.value
    journal.posted_by_id = user.id
    journal.posted_at = utcnow()
    db.add(journal)
    db.commit()
    db.refresh(journal)
    audit_service.record(db, action=AuditAction.JOURNAL_POSTED, actor_user_id=user.id,
                         entity_type="journal", entity_id=journal.id, company_id=journal.company_id,
                         ip_address=ip_address, user_agent=user_agent)
    return journal


def reverse_journal(db: Session, *, user: User, journal_id: int, reason: str | None = None,
                    ip_address: str | None = None, user_agent: str | None = None) -> Journal:
    """Reverse a posted journal by creating a mirror entry (D01: never edit)."""
    require_permission(user, Perm.JOURNAL_REVERSE)
    journal = _get_journal(db, user=user, journal_id=journal_id)
    require_company_access(user, journal.company_id, write=True)
    if journal.status != JournalStatus.POSTED.value:
        raise ConflictError("Only a posted journal can be reversed.")

    reversal = Journal(
        company_id=journal.company_id, entry_date=journal.entry_date,
        fiscal_year=journal.fiscal_year, fiscal_month=journal.fiscal_month,
        description=f"Reversal of journal {journal.id}" + (f": {reason}" if reason else ""),
        status=JournalStatus.POSTED.value, currency=journal.currency,
        reversal_of_id=journal.id, created_by_id=user.id,
        posted_by_id=user.id, posted_at=utcnow(),
    )
    db.add(reversal)
    db.flush()
    for line in journal.lines:
        db.add(JournalLine(journal_id=reversal.id, account_id=line.account_id,
                           debit=line.credit or ZERO, credit=line.debit or ZERO,
                           description=line.description, cost_centre=line.cost_centre))
    journal.status = JournalStatus.REVERSED.value
    db.add(journal)
    db.commit()
    db.refresh(reversal)
    audit_service.record(db, action=AuditAction.JOURNAL_REVERSED, actor_user_id=user.id,
                         entity_type="journal", entity_id=journal.id, company_id=journal.company_id,
                         ip_address=ip_address, user_agent=user_agent,
                         metadata={"reversal_id": reversal.id})
    return reversal


def _get_journal(db: Session, *, user: User, journal_id: int) -> Journal:
    journal = db.get(Journal, journal_id)
    if journal is None:
        raise NotFoundError("Journal not found.")
    require_company_access(user, journal.company_id)
    return journal


def list_journals(db: Session, *, user: User, company_id: int | None = None) -> list[Journal]:
    require_permission(user, Perm.JOURNAL_READ)
    stmt = select(Journal).order_by(Journal.entry_date.desc(), Journal.id.desc())
    allowed = accessible_company_ids(user)
    if allowed is not None:
        stmt = stmt.where(Journal.company_id.in_(allowed)) if allowed else stmt.where(False)
    if company_id is not None:
        stmt = stmt.where(Journal.company_id == company_id)
    return list(db.execute(stmt).scalars())


def serialise_journal(j: Journal) -> dict:
    return {
        "id": j.id, "company_id": j.company_id, "number": j.number,
        "entry_date": j.entry_date, "description": j.description, "status": j.status,
        "currency": j.currency, "reversal_of_id": j.reversal_of_id,
        "posted_at": j.posted_at, "created_at": j.created_at,
        "total_debit": str(sum((l.debit or ZERO) for l in j.lines)),
        "total_credit": str(sum((l.credit or ZERO) for l in j.lines)),
        "lines": [
            {"id": l.id, "account_id": l.account_id, "debit": l.debit, "credit": l.credit,
             "description": l.description, "cost_centre": l.cost_centre}
            for l in j.lines
        ],
    }


def trial_balance(
    db: Session, *, user: User, company_id: int,
    fiscal_year: int | None = None, fiscal_month: int | None = None,
) -> dict:
    """The trial balance for one company's *posted* journals (S26/S28, AC-26/AC-28).

    Only ``POSTED`` journals count -- drafts never affect the ledger. Each line is
    grouped by account; ``balance`` is debit minus credit. The totals must agree
    (a posting that did not balance could never have been posted), so any
    discrepancy is surfaced rather than hidden.
    """
    require_permission(user, Perm.JOURNAL_READ)
    require_company_access(user, company_id)

    stmt = (
        select(
            JournalLine.account_id,
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0),
        )
        .join(Journal, Journal.id == JournalLine.journal_id)
        .where(
            Journal.company_id == company_id,
            Journal.status == JournalStatus.POSTED.value,
        )
        .group_by(JournalLine.account_id)
    )
    if fiscal_year is not None:
        stmt = stmt.where(Journal.fiscal_year == fiscal_year)
    if fiscal_month is not None:
        stmt = stmt.where(Journal.fiscal_month == fiscal_month)

    accounts = {a.id: a for a in db.execute(
        select(Account).where(Account.company_id == company_id)
    ).scalars()}

    rows: list[dict] = []
    total_debit = ZERO
    total_credit = ZERO
    for account_id, debit, credit in db.execute(stmt):
        account = accounts.get(account_id)
        if account is None:
            continue
        debit = Decimal(debit or 0)
        credit = Decimal(credit or 0)
        total_debit += debit
        total_credit += credit
        rows.append({
            "account_id": account_id,
            "code": account.code,
            "name_ar": account.name_ar,
            "name_en": account.name_en,
            "account_type": account.account_type,
            "currency": account.currency,
            "debit": str(debit),
            "credit": str(credit),
            "balance": str(debit - credit),
        })
    rows.sort(key=lambda r: r["code"])
    return {
        "company_id": company_id,
        "fiscal_year": fiscal_year,
        "fiscal_month": fiscal_month,
        "rows": rows,
        "total_debit": str(total_debit),
        "total_credit": str(total_credit),
        "balanced": total_debit == total_credit,
    }


# --------------------------------------------------------------------------
# financial statements (S28, spec §15)
# --------------------------------------------------------------------------
def _totals_by_currency(rows: list[dict]) -> list[dict]:
    totals: dict[str, Decimal] = {}
    for row in rows:
        cur = row["currency"]
        totals[cur] = totals.get(cur, ZERO) + row["amount"]
    return [{"currency": c, "amount": str(a)} for c, a in sorted(totals.items())]


def _statement_rows(db: Session, *, company_id: int, account_type: str,
                    fiscal_year: int | None, fiscal_month: int | None) -> list[dict]:
    stmt = (
        select(
            JournalLine.account_id,
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0),
        )
        .join(Journal, Journal.id == JournalLine.journal_id)
        .join(Account, Account.id == JournalLine.account_id)
        .where(
            Journal.company_id == company_id,
            Journal.status == JournalStatus.POSTED.value,
            Account.account_type == account_type,
        )
        .group_by(JournalLine.account_id)
    )
    if fiscal_year is not None:
        stmt = stmt.where(Journal.fiscal_year == fiscal_year)
    if fiscal_month is not None:
        stmt = stmt.where(Journal.fiscal_month == fiscal_month)

    accounts = {a.id: a for a in db.execute(
        select(Account).where(Account.company_id == company_id)
    ).scalars()}

    rows: list[dict] = []
    for account_id, debit, credit in db.execute(stmt):
        account = accounts.get(account_id)
        if account is None:
            continue
        debit = Decimal(debit or 0)
        credit = Decimal(credit or 0)
        # Assets/expenses are debit-normal; liabilities/equity/revenue are
        # credit-normal. The sign is derived, never stored, so a loss is simply
        # a negative net (spec §15 allows negative figures).
        if account_type in {AccountType.ASSET.value, AccountType.EXPENSE.value}:
            amount = debit - credit
        else:
            amount = credit - debit
        rows.append({
            "account_id": account_id,
            "code": account.code,
            "name_ar": account.name_ar,
            "name_en": account.name_en,
            "currency": account.currency,
            "amount": amount,
        })
    rows.sort(key=lambda r: r["code"])
    return rows


def _statements_for_period(db: Session, *, company_id: int,
                           fiscal_year: int | None, fiscal_month: int | None) -> dict:
    revenue = _statement_rows(db, company_id=company_id,
                              account_type=AccountType.REVENUE.value,
                              fiscal_year=fiscal_year, fiscal_month=fiscal_month)
    expenses = _statement_rows(db, company_id=company_id,
                               account_type=AccountType.EXPENSE.value,
                               fiscal_year=fiscal_year, fiscal_month=fiscal_month)
    assets = _statement_rows(db, company_id=company_id,
                             account_type=AccountType.ASSET.value,
                             fiscal_year=fiscal_year, fiscal_month=fiscal_month)
    liabilities = _statement_rows(db, company_id=company_id,
                                  account_type=AccountType.LIABILITY.value,
                                  fiscal_year=fiscal_year, fiscal_month=fiscal_month)
    equity = _statement_rows(db, company_id=company_id,
                             account_type=AccountType.EQUITY.value,
                             fiscal_year=fiscal_year, fiscal_month=fiscal_month)

    total_revenue = _totals_by_currency(revenue)
    total_expenses = _totals_by_currency(expenses)
    net: dict[str, Decimal] = {r["currency"]: r["amount"] for r in revenue}
    for e in expenses:
        net[e["currency"]] = net.get(e["currency"], ZERO) - e["amount"]
    net_rows = [{"currency": c, "amount": str(a)} for c, a in sorted(net.items())]

    total_assets = _totals_by_currency(assets)
    total_liabilities = _totals_by_currency(liabilities)
    total_equity = _totals_by_currency(equity)

    # Assets must equal liabilities + equity, per currency. A currency that
    # appears on only one side is a real imbalance and is reported, not hidden.
    balanced: dict[str, bool] = {}
    for row in total_assets:
        balanced[row["currency"]] = (
            Decimal(row["amount"])
            == Decimal(next((l["amount"] for l in total_liabilities
                             if l["currency"] == row["currency"]), "0"))
            + Decimal(next((e["amount"] for e in total_equity
                            if e["currency"] == row["currency"]), "0"))
        )

    def _fmt(rows: list[dict]) -> list[dict]:
        return [{**r, "amount": str(r["amount"])} for r in rows]

    return {
        "fiscal_year": fiscal_year,
        "fiscal_month": fiscal_month,
        "income_statement": {
            "revenue": _fmt(revenue),
            "expenses": _fmt(expenses),
            "total_revenue": total_revenue,
            "total_expenses": total_expenses,
            "net": net_rows,
        },
        "balance_sheet": {
            "assets": _fmt(assets),
            "liabilities": _fmt(liabilities),
            "equity": _fmt(equity),
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "total_equity": total_equity,
            "balanced": [
                {"currency": c, "balanced": b} for c, b in sorted(balanced.items())
            ],
        },
    }


def ledger_activity(
    db: Session, *, user: User, company_id: int, account_type: str | None = None,
    fiscal_year: int | None = None, fiscal_month: int | None = None,
) -> dict:
    """The source lines behind revenue/expense, as one view (S26 Table 53).

    Table 53: "عرض الإيرادات أو المصروفات | يعرض سطور المصدر لا تسجيلًا إضافيًا"
    -- viewing revenue or expenses shows the source lines and adds **no** extra
    record. So this reads the posted journal lines (with their journal header)
    and never writes. Only ``POSTED`` journals count, matching the trial balance
    and the financial statements, so the totals reconcile (AC-28).
    """
    require_permission(user, Perm.JOURNAL_READ)
    require_company_access(user, company_id)

    if account_type is not None and account_type not in {
        AccountType.REVENUE.value, AccountType.EXPENSE.value
    }:
        raise ValidationError("account_type must be 'revenue' or 'expense'.")

    stmt = (
        select(
            JournalLine.id,
            JournalLine.journal_id,
            JournalLine.account_id,
            JournalLine.debit,
            JournalLine.credit,
            JournalLine.description,
            Journal.number,
            Journal.entry_date,
            Journal.description,
            Account.code,
            Account.name_ar,
            Account.name_en,
            Account.account_type,
            Account.currency,
        )
        .join(Journal, Journal.id == JournalLine.journal_id)
        .join(Account, Account.id == JournalLine.account_id)
        .where(
            Journal.company_id == company_id,
            Journal.status == JournalStatus.POSTED.value,
        )
        .order_by(Journal.entry_date, JournalLine.id)
    )
    if account_type is not None:
        stmt = stmt.where(Account.account_type == account_type)
    else:
        stmt = stmt.where(
            Account.account_type.in_(
                [AccountType.REVENUE.value, AccountType.EXPENSE.value]
            )
        )
    if fiscal_year is not None:
        stmt = stmt.where(Journal.fiscal_year == fiscal_year)
    if fiscal_month is not None:
        stmt = stmt.where(Journal.fiscal_month == fiscal_month)

    lines: list[dict] = []
    totals: dict[tuple[str, str], Decimal] = {}
    for (line_id, journal_id, account_id, debit, credit, line_desc, number,
         entry_date, journal_desc, code, name_ar, name_en, a_type, currency) in db.execute(stmt):
        debit = Decimal(debit or 0)
        credit = Decimal(credit or 0)
        # Revenue is credit-normal, expense debit-normal; the sign is derived so
        # the sum of the lines equals the statement figure for that account.
        amount = (credit - debit) if a_type == AccountType.REVENUE.value else (debit - credit)
        lines.append({
            "line_id": line_id,
            "journal_id": journal_id,
            "journal_number": number,
            "entry_date": entry_date.isoformat() if entry_date else None,
            "account_id": account_id,
            "code": code,
            "name_ar": name_ar,
            "name_en": name_en,
            "account_type": a_type,
            "currency": currency,
            "debit": str(debit),
            "credit": str(credit),
            "amount": str(amount),
            "description": line_desc or journal_desc,
        })
        key = (a_type, currency)
        totals[key] = totals.get(key, ZERO) + amount

    totals_rows = [
        {"account_type": t, "currency": c, "amount": str(a)}
        for (t, c), a in sorted(totals.items())
    ]
    return {
        "company_id": company_id,
        "fiscal_year": fiscal_year,
        "fiscal_month": fiscal_month,
        "account_type": account_type,
        "lines": lines,
        "totals": totals_rows,
    }


def _previous_period(fiscal_year: int | None, fiscal_month: int | None):
    if fiscal_year is None:
        return None, None
    if fiscal_month is None:
        return fiscal_year - 1, None
    if fiscal_month <= 1:
        return fiscal_year - 1, 12
    return fiscal_year, fiscal_month - 1


def financial_statements(
    db: Session, *, user: User, company_id: int,
    fiscal_year: int | None = None, fiscal_month: int | None = None,
    compare_previous: bool = False,
) -> dict:
    """Income statement and balance sheet from *posted* journals (S28, AC-28).

    Only ``POSTED`` journals count. Figures are grouped per currency so two
    currencies are never added together (T10). When ``compare_previous`` is set
    the immediately preceding month (or year, when no month is given) is
    returned alongside for comparison.
    """
    require_permission(user, Perm.JOURNAL_READ)
    require_company_access(user, company_id)

    current = _statements_for_period(db, company_id=company_id,
                                     fiscal_year=fiscal_year, fiscal_month=fiscal_month)
    result = {"company_id": company_id, **current}
    if compare_previous:
        py, pm = _previous_period(fiscal_year, fiscal_month)
        result["previous"] = _statements_for_period(
            db, company_id=company_id, fiscal_year=py, fiscal_month=pm
        )
    return result


# --------------------------------------------------------------------------
# invoices & settlements (D01/D09: policy as data)
# --------------------------------------------------------------------------
def create_invoice(
    db: Session, *, user: User, company_id: int, number: str, party_name: str,
    lines: list[dict], currency: str = "SAR", issue_date=None, due_date=None,
    tax_rate: Decimal = ZERO, notes: str | None = None,
    direction: str = InvoiceDirection.ISSUED.value, party_id: int | None = None,
    ip_address: str | None = None, user_agent: str | None = None,
) -> Invoice:
    require_permission(user, Perm.INVOICE_MANAGE)
    require_company_access(user, company_id, write=True)
    if not lines:
        raise ValidationError("An invoice requires at least one line.")
    if direction not in {d.value for d in InvoiceDirection}:
        raise ValidationError("Unknown invoice direction.")
    if party_id is not None:
        party = db.get(Party, party_id)
        if party is None or party.company_id != company_id:
            raise ValidationError("The invoice party must belong to the company.")
    invoice = Invoice(company_id=company_id, number=number, party_name=party_name,
                      issue_date=issue_date, due_date=due_date, currency=currency,
                      tax_rate=tax_rate, notes=notes, status=InvoiceStatus.DRAFT.value,
                      direction=direction, party_id=party_id, created_by_id=user.id)
    db.add(invoice)
    db.flush()
    total = ZERO
    for line in lines:
        qty = line.get("quantity", Decimal("1")) or Decimal("1")
        unit = line.get("unit_price", ZERO) or ZERO
        amount = (qty * unit).quantize(Decimal("0.01"))
        total += amount
        db.add(InvoiceLine(invoice_id=invoice.id, description=line.get("description", ""),
                           quantity=qty, unit_price=unit, amount=amount))
    invoice.total = total
    db.commit()
    db.refresh(invoice)
    audit_service.record(db, action=AuditAction.INVOICE_CREATED, actor_user_id=user.id,
                         entity_type="invoice", entity_id=invoice.id, company_id=company_id,
                         ip_address=ip_address, user_agent=user_agent)
    return invoice


def record_settlement(db: Session, *, user: User, invoice_id: int, amount: Decimal,
                      settled_on=None, reference: str | None = None,
                      ip_address: str | None = None, user_agent: str | None = None) -> Settlement:
    require_permission(user, Perm.SETTLEMENT_MANAGE)
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise NotFoundError("Invoice not found.")
    require_company_access(user, invoice.company_id, write=True)
    if amount <= ZERO:
        raise ValidationError("A settlement amount must be positive.")
    remaining = (invoice.total or ZERO) - (invoice.settled_amount or ZERO)
    if amount > remaining:
        raise ValidationError("The settlement exceeds the outstanding amount.")

    settlement = Settlement(invoice_id=invoice.id, amount=amount, currency=invoice.currency,
                            settled_on=settled_on, reference=reference, recorded_by_id=user.id)
    db.add(settlement)
    invoice.settled_amount = (invoice.settled_amount or ZERO) + amount
    invoice.status = (
        InvoiceStatus.SETTLED.value
        if invoice.settled_amount >= (invoice.total or ZERO)
        else InvoiceStatus.PARTIALLY_SETTLED.value
    )
    db.add(invoice)
    db.commit()
    db.refresh(settlement)
    audit_service.record(db, action=AuditAction.SETTLEMENT_RECORDED, actor_user_id=user.id,
                         entity_type="settlement", entity_id=settlement.id,
                         company_id=invoice.company_id, ip_address=ip_address,
                         user_agent=user_agent)
    return settlement


def link_invoice_to_journal(
    db: Session, *, user: User, invoice_id: int, journal_id: int,
    ip_address: str | None = None, user_agent: str | None = None,
) -> Invoice:
    """Link an invoice to the single ledger entry that records it (S27/AC-27).

    AC-27: "the invoice and the entry keep one reference". The link is set once
    and is unique in both directions -- an invoice cannot carry two entries and
    two invoices cannot share one entry -- so the same operation is never posted
    twice. Both records must belong to the same company and share a currency, so
    the link can never bridge two companies or mix currencies (T10). The entry
    must already be *posted*: a draft is not an effect.
    """
    require_permission(user, Perm.INVOICE_MANAGE)
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise NotFoundError("Invoice not found.")
    require_company_access(user, invoice.company_id, write=True)

    journal = db.get(Journal, journal_id)
    if journal is None or journal.company_id != invoice.company_id:
        # "not yours" and "does not exist" are indistinguishable (isolation).
        raise NotFoundError("Journal not found.")
    if journal.status != JournalStatus.POSTED.value:
        raise ConflictError("Only a posted journal can be linked to an invoice.")
    if journal.currency != invoice.currency:
        raise ValidationError("The invoice and the journal must share a currency.")
    if invoice.journal_id == journal.id:
        raise ConflictError("The invoice is already linked to this journal.")
    if invoice.journal_id is not None:
        raise ConflictError("The invoice is already linked to a journal.")
    existing = db.execute(
        select(Invoice.id).where(
            Invoice.journal_id == journal.id, Invoice.id != invoice.id
        )
    ).scalar()
    if existing is not None:
        raise ConflictError("This journal is already linked to another invoice.")

    invoice.journal_id = journal.id
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    audit_service.record(db, action=AuditAction.INVOICE_JOURNAL_LINKED, actor_user_id=user.id,
                         entity_type="invoice", entity_id=invoice.id, company_id=invoice.company_id,
                         ip_address=ip_address, user_agent=user_agent,
                         metadata={"journal_id": journal.id})
    return invoice


def list_invoices(db: Session, *, user: User, company_id: int | None = None) -> list[Invoice]:
    require_permission(user, Perm.INVOICE_READ)
    stmt = select(Invoice).order_by(Invoice.created_at.desc())
    allowed = accessible_company_ids(user)
    if allowed is not None:
        stmt = stmt.where(Invoice.company_id.in_(allowed)) if allowed else stmt.where(False)
    if company_id is not None:
        stmt = stmt.where(Invoice.company_id == company_id)
    return list(db.execute(stmt).scalars())


def serialise_invoice(inv: Invoice) -> dict:
    return {
        "id": inv.id, "company_id": inv.company_id, "number": inv.number,
        "party_name": inv.party_name, "party_id": inv.party_id,
        "direction": inv.direction,
        "journal_id": inv.journal_id,
        "issue_date": inv.issue_date, "due_date": inv.due_date,
        "currency": inv.currency, "total": inv.total, "settled_amount": inv.settled_amount,
        "outstanding": (inv.total or ZERO) - (inv.settled_amount or ZERO),
        "tax_rate": inv.tax_rate, "status": inv.status, "notes": inv.notes,
        "created_at": inv.created_at,
        "lines": [
            {"id": l.id, "description": l.description, "quantity": l.quantity,
             "unit_price": l.unit_price, "amount": l.amount}
            for l in inv.lines
        ],
    }


def receivables_summary(db: Session, *, user: User, company_id: int | None = None) -> dict:
    """Outstanding receivables and payables, kept separate and per currency (S27).

    A partial settlement reduces the outstanding amount exactly once, and the
    totals are grouped by currency so two currencies are never added together
    (spec §15, T10).
    """
    require_permission(user, Perm.INVOICE_READ)
    if company_id is not None:
        require_company_access(user, company_id)

    stmt = select(Invoice)
    allowed = accessible_company_ids(user)
    if allowed is not None:
        stmt = stmt.where(Invoice.company_id.in_(allowed)) if allowed else stmt.where(False)
    if company_id is not None:
        stmt = stmt.where(Invoice.company_id == company_id)

    receivables: dict[str, Decimal] = {}
    payables: dict[str, Decimal] = {}
    for inv in db.execute(stmt).scalars():
        outstanding = (inv.total or ZERO) - (inv.settled_amount or ZERO)
        if outstanding == ZERO:
            continue
        bucket = receivables if inv.direction == InvoiceDirection.ISSUED.value else payables
        bucket[inv.currency] = bucket.get(inv.currency, ZERO) + outstanding

    def _rows(bucket: dict[str, Decimal]) -> list[dict]:
        return [
            {"currency": cur, "amount": str(amt)}
            for cur, amt in sorted(bucket.items())
        ]

    return {
        "company_id": company_id,
        "receivables": _rows(receivables),
        "payables": _rows(payables),
    }


# --------------------------------------------------------------------------
# parties (S27)
# --------------------------------------------------------------------------
def create_party(db: Session, *, user: User, company_id: int, name: str,
                 name_en: str | None = None, party_type: str = "customer",
                 currency: str = "SAR", contact: str | None = None,
                 notes: str | None = None,
                 ip_address: str | None = None, user_agent: str | None = None) -> Party:
    require_permission(user, Perm.PARTY_MANAGE)
    require_company_access(user, company_id, write=True)
    existing = db.execute(
        select(Party).where(Party.company_id == company_id, Party.name == name)
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("A party with this name already exists for the company.")
    party = Party(company_id=company_id, name=name, name_en=name_en,
                  party_type=party_type, currency=currency, contact=contact,
                  notes=notes, created_by_id=user.id)
    db.add(party)
    db.commit()
    db.refresh(party)
    audit_service.record(db, action=AuditAction.PARTY_CREATED, actor_user_id=user.id,
                         entity_type="party", entity_id=party.id, company_id=company_id,
                         ip_address=ip_address, user_agent=user_agent)
    return party


def list_parties(db: Session, *, user: User, company_id: int | None = None) -> list[Party]:
    require_permission(user, Perm.PARTY_READ)
    stmt = select(Party).order_by(Party.name)
    allowed = accessible_company_ids(user)
    if allowed is not None:
        stmt = stmt.where(Party.company_id.in_(allowed)) if allowed else stmt.where(False)
    if company_id is not None:
        stmt = stmt.where(Party.company_id == company_id)
    return list(db.execute(stmt).scalars())


def serialise_party(p: Party) -> dict:
    return {
        "id": p.id, "company_id": p.company_id, "name": p.name, "name_en": p.name_en,
        "party_type": p.party_type, "currency": p.currency, "contact": p.contact,
        "is_active": p.is_active, "notes": p.notes,
    }


# --------------------------------------------------------------------------
# inter-company balances (S27, spec §15)
# --------------------------------------------------------------------------
def record_interbalance(db: Session, *, user: User, company_id: int,
                        amount: Decimal, counterparty_company_id: int | None = None,
                        counterparty_name: str | None = None, currency: str = "SAR",
                        reason: str | None = None, journal_reference: str | None = None,
                        ip_address: str | None = None, user_agent: str | None = None) -> CompanyInterbalance:
    require_permission(user, Perm.INTERBALANCE_MANAGE)
    require_company_access(user, company_id, write=True)
    if counterparty_company_id is not None:
        # The counterparty company must exist (scope is not required: a holding
        # balance may reference a company the recorder cannot otherwise write).
        from backend.db.models.identity import Company as _Company
        if db.get(_Company, counterparty_company_id) is None:
            raise ValidationError("The counterparty company does not exist.")
    # A balance is a balance, never revenue: no posting, no service fee.
    balance = CompanyInterbalance(
        company_id=company_id, counterparty_company_id=counterparty_company_id,
        counterparty_name=counterparty_name, currency=currency, amount=amount,
        reason=reason, journal_reference=journal_reference, recorded_by_id=user.id,
    )
    db.add(balance)
    db.commit()
    db.refresh(balance)
    audit_service.record(db, action=AuditAction.INTERBALANCE_RECORDED, actor_user_id=user.id,
                         entity_type="company_interbalance", entity_id=balance.id,
                         company_id=company_id, ip_address=ip_address, user_agent=user_agent)
    return balance


def list_interbalances(db: Session, *, user: User, company_id: int | None = None) -> list[CompanyInterbalance]:
    require_permission(user, Perm.INTERBALANCE_READ)
    stmt = select(CompanyInterbalance).order_by(CompanyInterbalance.created_at.desc())
    allowed = accessible_company_ids(user)
    if allowed is not None:
        stmt = stmt.where(
            CompanyInterbalance.company_id.in_(allowed)
        ) if allowed else stmt.where(False)
    if company_id is not None:
        stmt = stmt.where(CompanyInterbalance.company_id == company_id)
    return list(db.execute(stmt).scalars())


def serialise_interbalance(b: CompanyInterbalance) -> dict:
    return {
        "id": b.id, "company_id": b.company_id,
        "counterparty_company_id": b.counterparty_company_id,
        "counterparty_name": b.counterparty_name, "currency": b.currency,
        "amount": b.amount, "reason": b.reason, "journal_reference": b.journal_reference,
        "created_at": b.created_at,
    }


# --------------------------------------------------------------------------
# assets (D01)
# --------------------------------------------------------------------------
def create_asset(db: Session, *, user: User, company_id: int, name: str, cost: Decimal,
                 category: str | None = None, acquisition_date=None, currency: str = "SAR",
                 depreciation_method: str | None = None, depreciation_rate: Decimal | None = None,
                 notes: str | None = None, ip_address: str | None = None,
                 user_agent: str | None = None) -> Asset:
    require_permission(user, Perm.ASSET_MANAGE)
    require_company_access(user, company_id, write=True)
    asset = Asset(company_id=company_id, name=name, category=category,
                  acquisition_date=acquisition_date, cost=cost, currency=currency,
                  depreciation_method=depreciation_method, depreciation_rate=depreciation_rate,
                  notes=notes, is_active=True)
    db.add(asset)
    db.commit()
    db.refresh(asset)
    audit_service.record(db, action=AuditAction.ASSET_CREATED, actor_user_id=user.id,
                         entity_type="asset", entity_id=asset.id, company_id=company_id,
                         ip_address=ip_address, user_agent=user_agent)
    return asset


def list_assets(db: Session, *, user: User, company_id: int | None = None) -> list[Asset]:
    require_permission(user, Perm.ASSET_READ)
    stmt = select(Asset).order_by(Asset.created_at.desc())
    allowed = accessible_company_ids(user)
    if allowed is not None:
        stmt = stmt.where(Asset.company_id.in_(allowed)) if allowed else stmt.where(False)
    if company_id is not None:
        stmt = stmt.where(Asset.company_id == company_id)
    return list(db.execute(stmt).scalars())


def serialise_asset(a: Asset) -> dict:
    return {
        "id": a.id, "company_id": a.company_id, "name": a.name, "category": a.category,
        "acquisition_date": a.acquisition_date, "cost": a.cost, "currency": a.currency,
        "depreciation_method": a.depreciation_method, "depreciation_rate": a.depreciation_rate,
        "is_active": a.is_active, "notes": a.notes,
    }


# --------------------------------------------------------------------------
# budgets (D07: source + version preserved; approved is superseded not edited)
# --------------------------------------------------------------------------
def create_budget(db: Session, *, user: User, company_id: int, fiscal_year: int,
                  total_amount: Decimal, source: str | None = None, currency: str = "SAR",
                  notes: str | None = None, ip_address: str | None = None,
                  user_agent: str | None = None) -> Budget:
    require_permission(user, Perm.BUDGET_MANAGE)
    require_company_access(user, company_id, write=True)
    budget = Budget(company_id=company_id, fiscal_year=fiscal_year, version=1,
                    currency=currency, total_amount=total_amount, source=source,
                    notes=notes, status=BudgetStatus.DRAFT.value, created_by_id=user.id)
    db.add(budget)
    db.commit()
    db.refresh(budget)
    audit_service.record(db, action=AuditAction.BUDGET_CREATED, actor_user_id=user.id,
                         entity_type="budget", entity_id=budget.id, company_id=company_id,
                         ip_address=ip_address, user_agent=user_agent)
    return budget


def approve_budget(db: Session, *, user: User, budget_id: int, source: str | None = None,
                   ip_address: str | None = None, user_agent: str | None = None) -> Budget:
    require_permission(user, Perm.BUDGET_APPROVE)
    budget = db.get(Budget, budget_id)
    if budget is None:
        raise NotFoundError("Budget not found.")
    require_company_access(user, budget.company_id, write=True)

    # D07: an approved budget is superseded by a new version, not overwritten.
    prior = db.execute(
        select(Budget).where(
            Budget.company_id == budget.company_id,
            Budget.fiscal_year == budget.fiscal_year,
            Budget.status == BudgetStatus.APPROVED.value,
        )
    ).scalars().first()
    if prior is not None:
        budget.version = prior.version + 1
        budget.supersedes_id = prior.id
        prior.status = BudgetStatus.SUPERSEDED.value
        db.add(prior)

    budget.status = BudgetStatus.APPROVED.value
    if source is not None:
        budget.source = source
    budget.approved_by_id = user.id
    budget.approved_at = utcnow()
    db.add(budget)
    db.commit()
    db.refresh(budget)
    audit_service.record(db, action=AuditAction.BUDGET_APPROVED, actor_user_id=user.id,
                         entity_type="budget", entity_id=budget.id, company_id=budget.company_id,
                         ip_address=ip_address, user_agent=user_agent)
    return budget


def list_budgets(db: Session, *, user: User, company_id: int | None = None) -> list[Budget]:
    require_permission(user, Perm.BUDGET_READ)
    stmt = select(Budget).order_by(Budget.fiscal_year.desc(), Budget.version.desc())
    allowed = accessible_company_ids(user)
    if allowed is not None:
        stmt = stmt.where(Budget.company_id.in_(allowed)) if allowed else stmt.where(False)
    if company_id is not None:
        stmt = stmt.where(Budget.company_id == company_id)
    return list(db.execute(stmt).scalars())


def serialise_budget(b: Budget) -> dict:
    return {
        "id": b.id, "company_id": b.company_id, "fiscal_year": b.fiscal_year,
        "version": b.version, "currency": b.currency, "total_amount": b.total_amount,
        "source": b.source, "status": b.status, "notes": b.notes,
        "supersedes_id": b.supersedes_id, "approved_by_id": b.approved_by_id,
        "approved_at": b.approved_at, "created_at": b.created_at,
    }


def budget_utilisation(
    db: Session, *, user: User, company_id: int, fiscal_year: int,
    fiscal_month: int | None = None,
) -> dict:
    """Budget-versus-actual for a year (Table 56 "يفتح المصدر والفروق").

    The actual is the sum of *posted* expenses for the year (optionally up to a
    month); the budget is the approved version for that year. The variance and an
    ``over_budget`` flag are reported, but over-budget never creates a spending
    approval -- the flag is informational and the caller must escalate
    explicitly (AC-28: "ميزانية متجاوزة لا تنشئ موافقة صرف تلقائية").
    """
    require_permission(user, Perm.BUDGET_READ)
    require_company_access(user, company_id)

    budget = db.execute(
        select(Budget)
        .where(
            Budget.company_id == company_id,
            Budget.fiscal_year == fiscal_year,
            Budget.status == BudgetStatus.APPROVED.value,
        )
        .order_by(Budget.version.desc())
    ).scalars().first()

    expense_rows = _statement_rows(
        db, company_id=company_id, account_type=AccountType.EXPENSE.value,
        fiscal_year=fiscal_year, fiscal_month=fiscal_month,
    )
    actual_by_currency: dict[str, Decimal] = {}
    for row in expense_rows:
        actual_by_currency[row["currency"]] = (
            actual_by_currency.get(row["currency"], ZERO) + row["amount"]
        )

    currency = budget.currency if budget is not None else "SAR"
    budget_amount = Decimal(budget.total_amount) if budget is not None else ZERO
    actual = actual_by_currency.get(currency, ZERO)
    variance = budget_amount - actual
    over_budget = budget is not None and actual > budget_amount
    return {
        "company_id": company_id,
        "fiscal_year": fiscal_year,
        "fiscal_month": fiscal_month,
        "currency": currency,
        "budget_id": budget.id if budget is not None else None,
        "budget_version": budget.version if budget is not None else None,
        "budget_source": budget.source if budget is not None else None,
        "budget_total": str(budget_amount),
        "actual_expenses": str(actual),
        "variance": str(variance),
        "over_budget": over_budget,
        # AC-28: an over-budget flag is never an automatic payment approval.
        "auto_payment_approval": False,
    }


# --------------------------------------------------------------------------
# KPIs (D02)
# --------------------------------------------------------------------------
def create_kpi(db: Session, *, user: User, code: str, name_ar: str, data_source: str,
               calculation_method: str, period_label: str, company_id: int | None = None,
               name_en: str | None = None, unit: str | None = None,
               target_value: Decimal | None = None, metric_key: str | None = None,
               direction: str | None = None, ip_address: str | None = None,
               user_agent: str | None = None) -> KpiDefinition:
    require_permission(user, Perm.KPI_MANAGE)
    if company_id is not None:
        require_company_access(user, company_id, write=True)
    if metric_key is not None and metric_key not in kpi_service.METRIC_KEYS:
        raise ValidationError(f"Unknown metric_key: {metric_key}")
    kpi = KpiDefinition(company_id=company_id, code=code, name_ar=name_ar, name_en=name_en,
                        data_source=data_source, calculation_method=calculation_method,
                        period_label=period_label, unit=unit, target_value=target_value,
                        metric_key=metric_key,
                        direction=(direction or KpiDirection.UP.value),
                        # A new definition is inert until an authorised approval
                        # activates it (D02) — configuration is never approval.
                        is_active=False, created_by_id=user.id)
    db.add(kpi)
    db.commit()
    db.refresh(kpi)
    audit_service.record(db, action=AuditAction.KPI_CREATED, actor_user_id=user.id,
                         entity_type="kpi_definition", entity_id=kpi.id, company_id=company_id,
                         ip_address=ip_address, user_agent=user_agent)
    return kpi


def list_kpis(db: Session, *, user: User, company_id: int | None = None) -> list[KpiDefinition]:
    require_permission(user, Perm.KPI_READ)
    stmt = select(KpiDefinition).order_by(KpiDefinition.code)
    allowed = accessible_company_ids(user)
    if allowed is not None:
        stmt = stmt.where(
            (KpiDefinition.company_id.is_(None)) | (KpiDefinition.company_id.in_(allowed))
        )
    if company_id is not None:
        stmt = stmt.where(KpiDefinition.company_id == company_id)
    return list(db.execute(stmt).scalars())


def serialise_kpi(k: KpiDefinition) -> dict:
    return {
        "id": k.id, "company_id": k.company_id, "code": k.code, "name_ar": k.name_ar,
        "name_en": k.name_en, "data_source": k.data_source,
        "calculation_method": k.calculation_method, "period_label": k.period_label,
        "unit": k.unit, "target_value": k.target_value, "is_active": k.is_active,
        "metric_key": k.metric_key, "direction": k.direction,
        "approved_at": k.approved_at,
    }


# --------------------------------------------------------------------------
# accounting policy registry (D01)
# --------------------------------------------------------------------------
def create_policy(db: Session, *, user: User, kind: str, company_id: int | None = None,
                  value: Decimal | None = None, value_text: str | None = None,
                  currency: str | None = None, description: str | None = None,
                  effective_from: date | None = None, ip_address: str | None = None,
                  user_agent: str | None = None) -> AccountingPolicy:
    """Record a *draft* accounting policy. Draft is inert (D01).

    A policy only becomes effective when an accountant approves it; a draft can
    never influence a calculation. The next version number is derived from the
    existing rows for the same (company, kind).
    """
    require_permission(user, Perm.POLICY_MANAGE)
    if company_id is not None:
        require_company_access(user, company_id, write=True)
    if kind not in {k.value for k in PolicyKind}:
        raise ValidationError(f"Unknown policy kind: {kind}")

    latest = db.execute(
        select(func.max(AccountingPolicy.version)).where(
            AccountingPolicy.company_id.is_(company_id) if company_id is None
            else AccountingPolicy.company_id == company_id,
            AccountingPolicy.kind == kind,
        )
    ).scalar()
    version = int(latest or 0) + 1

    policy = AccountingPolicy(
        company_id=company_id, kind=kind, version=version, value=value,
        value_text=value_text, currency=currency, description=description,
        status=PolicyStatus.DRAFT.value, effective_from=effective_from,
        created_by_id=user.id,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    audit_service.record(db, action=AuditAction.POLICY_CREATED, actor_user_id=user.id,
                         entity_type="accounting_policy", entity_id=policy.id,
                         company_id=company_id, ip_address=ip_address, user_agent=user_agent)
    return policy


def approve_policy(db: Session, *, user: User, policy_id: int,
                   ip_address: str | None = None, user_agent: str | None = None,
                   ) -> AccountingPolicy:
    """Approve a policy so it becomes effective; supersede the prior version.

    D01: approval is an explicit accountant act. The previously approved row for
    the same (company, kind) is marked ``superseded`` but kept, never edited, so
    the policy history survives. A holding-wide row (company_id is NULL) and a
    company row are separate chains.
    """
    require_permission(user, Perm.POLICY_APPROVE)
    policy = db.get(AccountingPolicy, policy_id)
    if policy is None:
        raise NotFoundError("Policy not found.")
    if policy.company_id is not None:
        require_company_access(user, policy.company_id, write=True)
    if policy.status == PolicyStatus.APPROVED.value:
        raise ConflictError("This policy is already approved.")

    prior = db.execute(
        select(AccountingPolicy).where(
            AccountingPolicy.kind == policy.kind,
            AccountingPolicy.company_id.is_(None) if policy.company_id is None
            else AccountingPolicy.company_id == policy.company_id,
            AccountingPolicy.status == PolicyStatus.APPROVED.value,
        )
    ).scalars().first()
    if prior is not None:
        prior.status = PolicyStatus.SUPERSEDED.value
        db.add(prior)
        policy.supersedes_id = prior.id

    policy.status = PolicyStatus.APPROVED.value
    policy.approved_by_id = user.id
    policy.approved_at = utcnow()
    db.add(policy)
    db.commit()
    db.refresh(policy)
    audit_service.record(db, action=AuditAction.POLICY_APPROVED, actor_user_id=user.id,
                         entity_type="accounting_policy", entity_id=policy.id,
                         company_id=policy.company_id, ip_address=ip_address,
                         user_agent=user_agent)
    return policy


def list_policies(db: Session, *, user: User, company_id: int | None = None,
                  kind: str | None = None, approved_only: bool = False,
                  ) -> list[AccountingPolicy]:
    require_permission(user, Perm.POLICY_READ)
    stmt = select(AccountingPolicy).order_by(
        AccountingPolicy.kind, AccountingPolicy.version.desc()
    )
    allowed = accessible_company_ids(user)
    if allowed is not None:
        stmt = stmt.where(
            (AccountingPolicy.company_id.is_(None))
            | (AccountingPolicy.company_id.in_(allowed))
        )
    if company_id is not None:
        stmt = stmt.where(AccountingPolicy.company_id == company_id)
    if kind is not None:
        stmt = stmt.where(AccountingPolicy.kind == kind)
    if approved_only:
        stmt = stmt.where(AccountingPolicy.status == PolicyStatus.APPROVED.value)
    return list(db.execute(stmt).scalars())


def effective_policy(db: Session, *, company_id: int, kind: str,
                     on_date: date | None = None) -> AccountingPolicy | None:
    """The approved policy that applies to a company on a date.

    Resolution order: a company-specific approved row wins; otherwise the
    holding-wide (``company_id is NULL``) approved row. A draft is never
    returned — a caller that needs a value gets ``None`` rather than an
    unapproved assumption (D01).
    """
    stmt = select(AccountingPolicy).where(
        AccountingPolicy.kind == kind,
        AccountingPolicy.status == PolicyStatus.APPROVED.value,
        AccountingPolicy.company_id.in_([company_id]) | AccountingPolicy.company_id.is_(None),
    )
    if on_date is not None:
        stmt = stmt.where(
            (AccountingPolicy.effective_from.is_(None))
            | (AccountingPolicy.effective_from <= on_date)
        )
    rows = list(db.execute(stmt).scalars())
    company_row = next((r for r in rows if r.company_id == company_id), None)
    if company_row is not None:
        return company_row
    return next((r for r in rows if r.company_id is None), None)


def serialise_policy(p: AccountingPolicy) -> dict:
    return {
        "id": p.id, "company_id": p.company_id, "kind": p.kind, "version": p.version,
        "value": p.value, "value_text": p.value_text, "currency": p.currency,
        "description": p.description, "status": p.status,
        "approved_by_id": p.approved_by_id, "approved_at": p.approved_at,
        "effective_from": p.effective_from, "supersedes_id": p.supersedes_id,
        "created_at": p.created_at,
    }


# --------------------------------------------------------------------------
# S28: monthly financial report (Table 57 -- draw the accounts, add analysis)
# --------------------------------------------------------------------------
def _current_source_version_id(db: Session, *, company_id: int, year: int, month: int):
    """The approved financial summary version current for a company/month, if any.

    Used as the report's provenance: the group report must distinguish the
    holding's own accounts from the subsidiary summaries (S28 scope).
    """
    period = db.execute(
        select(FinancialPeriod).where(
            FinancialPeriod.company_id == company_id,
            FinancialPeriod.period_year == year,
            FinancialPeriod.period_month == month,
        )
    ).scalars().first()
    if period is None or period.effective_version_id is None:
        return None
    version = db.get(FinancialSummaryVersion, period.effective_version_id)
    if version is None or version.company_id != company_id:
        return None
    return version.id


def _report_figures(db: Session, *, company_id: int, year: int, month: int) -> dict:
    """Draw the accounts for the month: statements + trial balance + summary.

    Reads only *posted* journals, so the summary reconciles with the trial
    balance (AC-28) and two currencies are never added together (T10).
    """
    statements = _statements_for_period(
        db, company_id=company_id, fiscal_year=year, fiscal_month=month
    )
    trial = _trial_balance_unchecked(db, company_id=company_id, year=year, month=month)

    # A concise, per-currency summary so the group view can read one line per
    # currency without summing across currencies.
    def _money(value: Decimal) -> str:
        return str(value.quantize(Decimal("0.01")))

    summary: list[dict] = []
    revenue_by_currency = {r["currency"]: Decimal(r["amount"])
                           for r in statements["income_statement"]["total_revenue"]}
    expenses_by_currency = {r["currency"]: Decimal(r["amount"])
                            for r in statements["income_statement"]["total_expenses"]}
    for currency in sorted(set(revenue_by_currency) | set(expenses_by_currency)):
        revenue = revenue_by_currency.get(currency, ZERO)
        expenses = expenses_by_currency.get(currency, ZERO)
        summary.append({
            "currency": currency,
            "revenue": _money(revenue),
            "expenses": _money(expenses),
            "net": _money(revenue - expenses),
        })

    return {
        "period_year": year,
        "period_month": month,
        "summary": summary,
        "income_statement": statements["income_statement"],
        "balance_sheet": statements["balance_sheet"],
        "trial_balance": {
            "balanced": trial["balanced"],
            "total_debit": trial["total_debit"],
            "total_credit": trial["total_credit"],
        },
    }


def _trial_balance_unchecked(db: Session, *, company_id: int, year: int, month: int) -> dict:
    """The trial balance without an RBAC check, for internal report generation.

    ``trial_balance`` gates on ``journal.read`` and company access; the report
    caller has already passed ``financial_report.*`` and company access, so the
    extra gate would be redundant (and the accountant does hold ``journal.read``
    anyway).
    """
    stmt = (
        select(
            JournalLine.account_id,
            func.coalesce(func.sum(JournalLine.debit), 0),
            func.coalesce(func.sum(JournalLine.credit), 0),
        )
        .join(Journal, Journal.id == JournalLine.journal_id)
        .where(
            Journal.company_id == company_id,
            Journal.status == JournalStatus.POSTED.value,
            Journal.fiscal_year == year,
            Journal.fiscal_month == month,
        )
        .group_by(JournalLine.account_id)
    )
    total_debit = ZERO
    total_credit = ZERO
    for _account_id, debit, credit in db.execute(stmt):
        total_debit += Decimal(debit or 0)
        total_credit += Decimal(credit or 0)
    return {
        "total_debit": str(total_debit),
        "total_credit": str(total_credit),
        "balanced": total_debit == total_credit,
    }


def generate_monthly_financial_report(
    db: Session, *, user: User, company_id: int, period_year: int, period_month: int,
    currency: str = "SAR", ip_address: str | None = None, user_agent: str | None = None,
) -> MonthlyFinancialReport:
    """Generate (or regenerate the draft of) a company's monthly financial report.

    Table 57: "إعداد التقرير المالي الشهري | يسحب الحسابات ويضيف التحليل" -- the
    action draws the accounts and adds the analysis. The drawn figures are the
    posted-journal statements for the month; the analysis is added separately
    (``update_report_analysis``). A finalised report is immutable.
    """
    require_permission(user, Perm.FINANCIAL_REPORT_MANAGE)
    require_company_access(user, company_id, write=True)
    if period_month < 1 or period_month > 12:
        raise ValidationError("period_month must be between 1 and 12.")

    existing = db.execute(
        select(MonthlyFinancialReport).where(
            MonthlyFinancialReport.company_id == company_id,
            MonthlyFinancialReport.period_year == period_year,
            MonthlyFinancialReport.period_month == period_month,
        )
    ).scalars().first()
    if existing is not None and existing.status != MonthlyFinancialReportStatus.DRAFT.value:
        raise ConflictError(
            "A finalised or archived report cannot be regenerated; a correction "
            "is a new report."
        )

    figures = _report_figures(db, company_id=company_id,
                              year=period_year, month=period_month)
    source_version_id = _current_source_version_id(
        db, company_id=company_id, year=period_year, month=period_month
    )

    if existing is None:
        report = MonthlyFinancialReport(
            company_id=company_id, period_year=period_year, period_month=period_month,
            status=MonthlyFinancialReportStatus.DRAFT.value, currency=currency,
            figures=json.dumps(figures, ensure_ascii=False),
            source_version_id=source_version_id, generated_at=utcnow(),
            generated_by_id=user.id,
        )
        db.add(report)
    else:
        report = existing
        report.figures = json.dumps(figures, ensure_ascii=False)
        report.currency = currency
        report.source_version_id = source_version_id
        report.generated_at = utcnow()
        report.generated_by_id = user.id
        db.add(report)

    db.commit()
    db.refresh(report)
    audit_service.record(
        db, action=AuditAction.FINANCIAL_REPORT_GENERATED, actor_user_id=user.id,
        entity_type="monthly_financial_report", entity_id=report.id, company_id=company_id,
        metadata={"period_year": period_year, "period_month": period_month},
        ip_address=ip_address, user_agent=user_agent,
    )
    return report


def _scoped_report(db: Session, *, user: User, report_id: int) -> MonthlyFinancialReport:
    """Fetch a report the caller may see, else raise NotFound (never 403).

    "Not yours" and "does not exist" must be indistinguishable, so an
    out-of-scope report is reported as missing rather than forbidden.
    """
    report = db.get(MonthlyFinancialReport, report_id)
    allowed = accessible_company_ids(user)
    if report is None or (allowed is not None and report.company_id not in set(allowed)):
        raise NotFoundError("Financial report not found.")
    return report


def update_report_analysis(
    db: Session, *, user: User, report_id: int, analysis: str | None,
    ip_address: str | None = None, user_agent: str | None = None,
) -> MonthlyFinancialReport:
    """Set the accountant's added analysis on a draft report (Table 57)."""
    require_permission(user, Perm.FINANCIAL_REPORT_MANAGE)
    report = _scoped_report(db, user=user, report_id=report_id)
    require_company_access(user, report.company_id, write=True)
    if report.status != MonthlyFinancialReportStatus.DRAFT.value:
        raise ConflictError("Only a draft report's analysis can be edited.")
    report.analysis = analysis
    db.add(report)
    db.commit()
    db.refresh(report)
    audit_service.record(
        db, action=AuditAction.FINANCIAL_REPORT_ANALYSIS_UPDATED, actor_user_id=user.id,
        entity_type="monthly_financial_report", entity_id=report.id,
        company_id=report.company_id, ip_address=ip_address, user_agent=user_agent,
    )
    return report


def finalise_monthly_financial_report(
    db: Session, *, user: User, report_id: int,
    ip_address: str | None = None, user_agent: str | None = None,
) -> MonthlyFinancialReport:
    """Finalise a draft report: it becomes immutable and the BD + owner are told.

    Table 57: the report "notifies the Business Development manager and the owner
    according to permissions". Finalising is the explicit accountant act that
    fixes the report; a later correction is a new report.
    """
    require_permission(user, Perm.FINANCIAL_REPORT_FINALISE)
    report = _scoped_report(db, user=user, report_id=report_id)
    require_company_access(user, report.company_id, write=True)
    if report.status != MonthlyFinancialReportStatus.DRAFT.value:
        raise ConflictError("Only a draft report can be finalised.")
    if report.figures is None:
        raise ConflictError("Generate the report before finalising it.")

    report.status = MonthlyFinancialReportStatus.FINALISED.value
    report.finalised_at = utcnow()
    report.finalised_by_id = user.id
    db.add(report)
    db.commit()
    db.refresh(report)
    audit_service.record(
        db, action=AuditAction.FINANCIAL_REPORT_FINALISED, actor_user_id=user.id,
        entity_type="monthly_financial_report", entity_id=report.id,
        company_id=report.company_id, ip_address=ip_address, user_agent=user_agent,
    )

    # Table 57: notify BD and owner (per permissions). Sensitive figures never
    # appear in the notification body (D11).
    from backend.db.models.identity import RoleCode

    recipients = set(notification_service.users_with_role(
        db, role_code=RoleCode.BUSINESS_DEVELOPMENT.value
    ))
    recipients |= set(notification_service.users_with_role(
        db, role_code=RoleCode.HOLDING_OWNER.value
    ))
    recipients.discard(user.id)
    notification_service.notify(
        db,
        recipient_ids=sorted(recipients),
        type=NotificationType.FINANCIAL_REPORT_FINALISED.value,
        title_ar="اعتماد التقرير المالي الشهري",
        title_en="Monthly financial report finalised",
        message_ar=(
            f"تم اعتماد التقرير المالي الشهري للفترة "
            f"{report.period_month}/{report.period_year}."
        ),
        message_en=(
            f"The monthly financial report for {report.period_month}/{report.period_year} "
            "was finalised."
        ),
        company_id=report.company_id,
        entity_type="monthly_financial_report",
        entity_id=report.id,
        dedupe_key=f"fin_report_finalised:{report.id}",
        actor_user_id=user.id,
    )
    return report


def archive_monthly_financial_report(
    db: Session, *, user: User, report_id: int,
    ip_address: str | None = None, user_agent: str | None = None,
) -> MonthlyFinancialReport:
    """Archive a finalised report (read-only history)."""
    require_permission(user, Perm.FINANCIAL_REPORT_FINALISE)
    report = _scoped_report(db, user=user, report_id=report_id)
    require_company_access(user, report.company_id, write=True)
    if report.status != MonthlyFinancialReportStatus.FINALISED.value:
        raise ConflictError("Only a finalised report can be archived.")
    report.status = MonthlyFinancialReportStatus.ARCHIVED.value
    db.add(report)
    db.commit()
    db.refresh(report)
    audit_service.record(
        db, action=AuditAction.FINANCIAL_REPORT_ARCHIVED, actor_user_id=user.id,
        entity_type="monthly_financial_report", entity_id=report.id,
        company_id=report.company_id, ip_address=ip_address, user_agent=user_agent,
    )
    return report


def list_monthly_financial_reports(
    db: Session, *, user: User, company_id: int | None = None,
    period_year: int | None = None, period_month: int | None = None,
) -> list[MonthlyFinancialReport]:
    """List financial reports in the caller's scope (the archive, S28)."""
    require_permission(user, Perm.FINANCIAL_REPORT_READ)
    stmt = select(MonthlyFinancialReport).order_by(
        MonthlyFinancialReport.period_year.desc(),
        MonthlyFinancialReport.period_month.desc(),
    )
    allowed = accessible_company_ids(user)
    if allowed is not None:
        stmt = stmt.where(MonthlyFinancialReport.company_id.in_(allowed)) if allowed \
            else stmt.where(False)
    if company_id is not None:
        stmt = stmt.where(MonthlyFinancialReport.company_id == company_id)
    if period_year is not None:
        stmt = stmt.where(MonthlyFinancialReport.period_year == period_year)
    if period_month is not None:
        stmt = stmt.where(MonthlyFinancialReport.period_month == period_month)
    return list(db.execute(stmt).scalars())


def get_monthly_financial_report(db: Session, *, user: User, report_id: int) -> MonthlyFinancialReport:
    require_permission(user, Perm.FINANCIAL_REPORT_READ)
    return _scoped_report(db, user=user, report_id=report_id)


def serialise_financial_report(r: MonthlyFinancialReport) -> dict:
    return {
        "id": r.id,
        "company_id": r.company_id,
        "period_year": r.period_year,
        "period_month": r.period_month,
        "status": r.status,
        "currency": r.currency,
        "figures": json.loads(r.figures) if r.figures else None,
        "analysis": r.analysis,
        "source_version_id": r.source_version_id,
        "generated_at": r.generated_at,
        "generated_by_id": r.generated_by_id,
        "finalised_at": r.finalised_at,
        "finalised_by_id": r.finalised_by_id,
        "created_at": r.created_at,
    }
