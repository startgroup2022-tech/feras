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

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.errors import ConflictError, NotFoundError, ValidationError
from backend.db.base import utcnow
from backend.db.models.audit_actions import AuditAction
from backend.db.models.accounting import (
    Account,
    Asset,
    Budget,
    CompanyInterbalance,
    FiscalPeriod,
    Invoice,
    InvoiceLine,
    Journal,
    JournalLine,
    KpiDefinition,
    OpeningBalance,
    Party,
    Settlement,
)
from backend.db.models.enums import (
    AccountType,
    BudgetStatus,
    InvoiceDirection,
    InvoiceStatus,
    JournalStatus,
    OpeningBalanceStatus,
)
from backend.db.models.identity import User
from backend.rbac.authorization import (
    accessible_company_ids,
    require_company_access,
    require_permission,
)
from backend.rbac.permissions import Perm
from backend.services import audit_service

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


# --------------------------------------------------------------------------
# KPIs (D02)
# --------------------------------------------------------------------------
def create_kpi(db: Session, *, user: User, code: str, name_ar: str, data_source: str,
               calculation_method: str, period_label: str, company_id: int | None = None,
               name_en: str | None = None, unit: str | None = None,
               target_value: Decimal | None = None, ip_address: str | None = None,
               user_agent: str | None = None) -> KpiDefinition:
    require_permission(user, Perm.KPI_MANAGE)
    if company_id is not None:
        require_company_access(user, company_id, write=True)
    kpi = KpiDefinition(company_id=company_id, code=code, name_ar=name_ar, name_en=name_en,
                        data_source=data_source, calculation_method=calculation_method,
                        period_label=period_label, unit=unit, target_value=target_value,
                        is_active=True, created_by_id=user.id)
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
    }
