"""S27 completion: receivables/payables, the party directory and inter-company
balances.

These tests exercise the real service + API + persistence path (not mocks):

* an issued invoice is a receivable ("مستحق لنا") and a received invoice is a
  payable ("مستحق علينا"); a partial settlement reduces the outstanding amount
  exactly once (AC-27: no double count);
* currencies are never added together (T10);
* the party directory is company-scoped and a party from another company cannot
  be attached to an invoice;
* an inter-company balance records its currency and reason, is never treated as
  revenue, and cannot be written for another company (AC-27, spec §15);
* a non-accountant cannot read or write the ledger.
"""

from __future__ import annotations

import pytest

from backend.db.models.accounting import Invoice, Party
from backend.db.models.enums import InvoiceDirection, InvoiceStatus


@pytest.fixture
def s27_world(world, make_user):
    """``world`` plus granted actors (writes need an explicit access row)."""
    owner_all = make_user(
        "owner_all@corp.sa", "holding_owner", [world["alpha"], world["beta"]]
    )
    accountant_all = make_user(
        "acc_all@corp.sa", "accountant", [world["alpha"], world["beta"]]
    )
    world = dict(world)
    world["owner_all"] = owner_all
    world["accountant_all"] = accountant_all
    return world


def _invoice(client, auth, user, company_id, *, number, direction="issued",
             party_name="طرف", amount="1000.00", currency="SAR"):
    return client.post(
        "/api/v1/accounting/invoices",
        json={
            "company_id": company_id,
            "number": number,
            "party_name": party_name,
            "direction": direction,
            "currency": currency,
            "lines": [{"description": "بند", "quantity": "1", "unit_price": amount}],
        },
        headers=auth(user),
    )


# --------------------------------------------------------------------------
# receivables / payables (AC-27, T10)
# --------------------------------------------------------------------------
def test_issued_invoice_is_a_receivable_and_received_is_a_payable(
    client, s27_world, auth
):
    owner = s27_world["owner_all"]
    alpha = s27_world["alpha"].id

    issued = _invoice(client, auth, owner, alpha, number="INV-1", direction="issued",
                      amount="1000.00")
    assert issued.status_code == 201, issued.text
    assert issued.json()["direction"] == "issued"

    received = _invoice(client, auth, owner, alpha, number="INV-2", direction="received",
                        amount="400.00")
    assert received.status_code == 201, received.text
    assert received.json()["direction"] == "received"

    summary = client.get(
        f"/api/v1/accounting/receivables?company_id={alpha}", headers=auth(owner)
    )
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert body["receivables"] == [{"currency": "SAR", "amount": "1000.00"}]
    assert body["payables"] == [{"currency": "SAR", "amount": "400.00"}]


def test_partial_settlement_reduces_outstanding_once(client, s27_world, auth, db):
    owner = s27_world["owner_all"]
    alpha = s27_world["alpha"].id
    invoice_id = _invoice(client, auth, owner, alpha, number="INV-3",
                          amount="1000.00").json()["id"]

    first = client.post(
        f"/api/v1/accounting/invoices/{invoice_id}/settlements",
        json={"amount": "300.00"},
        headers=auth(owner),
    )
    assert first.status_code == 201, first.text

    second = client.post(
        f"/api/v1/accounting/invoices/{invoice_id}/settlements",
        json={"amount": "200.00"},
        headers=auth(owner),
    )
    assert second.status_code == 201, second.text

    summary = client.get(
        f"/api/v1/accounting/receivables?company_id={alpha}", headers=auth(owner)
    ).json()
    # 1000 - 300 - 200 = 500, counted once.
    assert summary["receivables"] == [{"currency": "SAR", "amount": "500.00"}]

    inv = db.get(Invoice, invoice_id)
    db.refresh(inv)
    assert inv.status == InvoiceStatus.PARTIALLY_SETTLED.value


def test_settling_beyond_the_outstanding_is_rejected(client, s27_world, auth):
    owner = s27_world["owner_all"]
    alpha = s27_world["alpha"].id
    invoice_id = _invoice(client, auth, owner, alpha, number="INV-4",
                          amount="100.00").json()["id"]
    over = client.post(
        f"/api/v1/accounting/invoices/{invoice_id}/settlements",
        json={"amount": "150.00"},
        headers=auth(owner),
    )
    assert over.status_code == 422


def test_currencies_are_never_added_together(client, s27_world, auth):
    owner = s27_world["owner_all"]
    alpha = s27_world["alpha"].id
    _invoice(client, auth, owner, alpha, number="INV-SAR", amount="1000.00",
             currency="SAR")
    _invoice(client, auth, owner, alpha, number="INV-BHD", amount="200.00",
             currency="BHD")
    summary = client.get(
        f"/api/v1/accounting/receivables?company_id={alpha}", headers=auth(owner)
    ).json()
    assert summary["receivables"] == [
        {"currency": "BHD", "amount": "200.00"},
        {"currency": "SAR", "amount": "1000.00"},
    ]


# --------------------------------------------------------------------------
# party directory (S27)
# --------------------------------------------------------------------------
def test_party_directory_is_company_scoped(client, s27_world, auth):
    owner = s27_world["owner_all"]
    alpha = s27_world["alpha"].id
    beta = s27_world["beta"].id

    created = client.post(
        "/api/v1/accounting/parties",
        json={"company_id": alpha, "name": "عميل ألفا"},
        headers=auth(owner),
    )
    assert created.status_code == 201, created.text

    alpha_list = client.get(
        f"/api/v1/accounting/parties?company_id={alpha}", headers=auth(owner)
    ).json()
    beta_list = client.get(
        f"/api/v1/accounting/parties?company_id={beta}", headers=auth(owner)
    ).json()
    assert [p["name"] for p in alpha_list] == ["عميل ألفا"]
    assert beta_list == []


def test_duplicate_party_name_is_rejected(client, s27_world, auth):
    owner = s27_world["owner_all"]
    alpha = s27_world["alpha"].id
    payload = {"company_id": alpha, "name": "مورد مشترك"}
    assert client.post("/api/v1/accounting/parties", json=payload,
                       headers=auth(owner)).status_code == 201
    again = client.post("/api/v1/accounting/parties", json=payload, headers=auth(owner))
    assert again.status_code == 409


def test_invoice_cannot_reference_another_company_party(client, s27_world, auth, db):
    owner = s27_world["owner_all"]
    alpha = s27_world["alpha"].id
    beta = s27_world["beta"].id
    # A party belonging to beta.
    beta_party = Party(company_id=beta, name="طرف بيتا")
    db.add(beta_party)
    db.commit()
    db.refresh(beta_party)

    rejected = client.post(
        "/api/v1/accounting/invoices",
        json={
            "company_id": alpha,
            "number": "INV-X",
            "party_name": "طرف بيتا",
            "party_id": beta_party.id,
            "lines": [{"description": "بند", "quantity": "1", "unit_price": "10"}],
        },
        headers=auth(owner),
    )
    assert rejected.status_code == 422


# --------------------------------------------------------------------------
# inter-company balances (S27, spec §15)
# --------------------------------------------------------------------------
def test_interbalance_records_currency_and_reason(client, s27_world, auth, db):
    owner = s27_world["owner_all"]
    alpha = s27_world["alpha"].id
    beta = s27_world["beta"].id

    created = client.post(
        "/api/v1/accounting/interbalances",
        json={
            "company_id": alpha,
            "counterparty_company_id": beta,
            "currency": "BHD",
            "amount": "5000.00",
            "reason": "تحويل تشغيلي",
        },
        headers=auth(owner),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["currency"] == "BHD"
    assert body["amount"] == "5000.00"
    assert body["reason"] == "تحويل تشغيلي"

    listed = client.get(
        f"/api/v1/accounting/interbalances?company_id={alpha}", headers=auth(owner)
    ).json()
    assert len(listed) == 1
    assert listed[0]["counterparty_company_id"] == beta


def test_interbalance_never_creates_revenue(client, s27_world, auth, db):
    """A recorded balance must not appear as revenue in the trial balance."""
    from backend.db.models.accounting import Account

    owner = s27_world["owner_all"]
    alpha = s27_world["alpha"].id
    beta = s27_world["beta"].id
    account = Account(company_id=alpha, code="4000", name_ar="إيراد",
                      account_type="revenue")
    db.add(account)
    db.commit()

    client.post(
        "/api/v1/accounting/interbalances",
        json={"company_id": alpha, "counterparty_company_id": beta,
              "currency": "SAR", "amount": "9999.00", "reason": "تحويل"},
        headers=auth(owner),
    )
    tb = client.get(
        f"/api/v1/accounting/trial-balance?company_id={alpha}", headers=auth(owner)
    ).json()
    assert tb["rows"] == []
    assert tb["total_debit"] == "0"


def test_interbalance_unknown_counterparty_is_rejected(client, s27_world, auth):
    owner = s27_world["owner_all"]
    alpha = s27_world["alpha"].id
    bad = client.post(
        "/api/v1/accounting/interbalances",
        json={"company_id": alpha, "counterparty_company_id": 999999,
              "currency": "SAR", "amount": "10.00"},
        headers=auth(owner),
    )
    assert bad.status_code == 422


# --------------------------------------------------------------------------
# RBAC: the ledger is not open to everyone
# --------------------------------------------------------------------------
def test_marketer_cannot_read_the_ledger(client, s27_world, auth):
    marketer = s27_world["marketer"] if "marketer" in s27_world else None
    if marketer is None:
        marketer = s27_world["alpha_mgr"]
    denied = client.get("/api/v1/accounting/receivables", headers=auth(marketer))
    assert denied.status_code == 403


def test_invoice_direction_defaults_to_issued(client, s27_world, auth):
    owner = s27_world["owner_all"]
    alpha = s27_world["alpha"].id
    created = client.post(
        "/api/v1/accounting/invoices",
        json={
            "company_id": alpha,
            "number": "INV-DEF",
            "party_name": "طرف",
            "lines": [{"description": "بند", "quantity": "1", "unit_price": "10"}],
        },
        headers=auth(owner),
    )
    assert created.status_code == 201, created.text
    assert created.json()["direction"] == InvoiceDirection.ISSUED.value


# --------------------------------------------------------------------------
# S28: financial statements (income statement + balance sheet)
# --------------------------------------------------------------------------
def _seed_ledger(db, company_id):
    """A posted journal: cash 1000 (asset), revenue 1000 (credit)."""
    from decimal import Decimal

    from backend.db.models.accounting import Account, Journal, JournalLine
    from datetime import date

    cash = Account(company_id=company_id, code="1000", name_ar="نقد", name_en="Cash",
                   account_type="asset", currency="SAR")
    revenue = Account(company_id=company_id, code="4000", name_ar="إيراد",
                      name_en="Revenue", account_type="revenue", currency="SAR")
    expense = Account(company_id=company_id, code="5000", name_ar="مصروف",
                      name_en="Expense", account_type="expense", currency="SAR")
    db.add_all([cash, revenue, expense])
    db.commit()
    db.refresh(cash)
    db.refresh(revenue)
    db.refresh(expense)

    journal = Journal(company_id=company_id, number="J-1", entry_date=date(2026, 3, 1),
                      fiscal_year=2026, fiscal_month=3, status="posted")
    db.add(journal)
    db.flush()
    db.add_all([
        JournalLine(journal_id=journal.id, account_id=cash.id, debit=Decimal("1000"),
                    credit=Decimal("0")),
        JournalLine(journal_id=journal.id, account_id=revenue.id, debit=Decimal("0"),
                    credit=Decimal("1000")),
    ])
    db.commit()
    return cash, revenue, expense


def test_financial_statements_report_income_and_balance(client, s27_world, auth, db):
    owner = s27_world["owner_all"]
    alpha = s27_world["alpha"].id
    _seed_ledger(db, alpha)

    fs = client.get(
        f"/api/v1/accounting/financial-statements?company_id={alpha}&fiscal_year=2026&fiscal_month=3",
        headers=auth(owner),
    )
    assert fs.status_code == 200, fs.text
    body = fs.json()
    is_ = body["income_statement"]
    bs = body["balance_sheet"]
    assert is_["total_revenue"] == [{"currency": "SAR", "amount": "1000.00"}]
    assert is_["total_expenses"] == []
    assert is_["net"] == [{"currency": "SAR", "amount": "1000.00"}]
    assert bs["total_assets"] == [{"currency": "SAR", "amount": "1000.00"}]
    assert bs["balanced"] == [{"currency": "SAR", "balanced": False}]


def test_financial_statements_ignore_draft_journals(client, s27_world, auth, db):
    from decimal import Decimal

    from datetime import date

    from backend.db.models.accounting import Account, Journal, JournalLine

    owner = s27_world["owner_all"]
    alpha = s27_world["alpha"].id
    cash = Account(company_id=alpha, code="1000", name_ar="نقد", account_type="asset",
                   currency="SAR")
    db.add(cash)
    db.commit()
    db.refresh(cash)
    journal = Journal(company_id=alpha, number="J-DRAFT", entry_date=date(2026, 3, 1),
                      fiscal_year=2026, fiscal_month=3, status="draft")
    db.add(journal)
    db.flush()
    db.add(JournalLine(journal_id=journal.id, account_id=cash.id,
                       debit=Decimal("500"), credit=Decimal("0")))
    db.commit()

    fs = client.get(
        f"/api/v1/accounting/financial-statements?company_id={alpha}&fiscal_year=2026&fiscal_month=3",
        headers=auth(owner),
    ).json()
    assert fs["balance_sheet"]["assets"] == []
    assert fs["balance_sheet"]["total_assets"] == []


def test_financial_statements_compare_previous_period(client, s27_world, auth, db):
    owner = s27_world["owner_all"]
    alpha = s27_world["alpha"].id
    _seed_ledger(db, alpha)
    fs = client.get(
        f"/api/v1/accounting/financial-statements?company_id={alpha}"
        "&fiscal_year=2026&fiscal_month=3&compare_previous=true",
        headers=auth(owner),
    ).json()
    assert "previous" in fs
    assert fs["previous"]["fiscal_year"] == 2026
    assert fs["previous"]["fiscal_month"] == 2


def test_financial_statements_are_company_scoped(client, s27_world, auth, db, make_user):
    """A finance manager scoped to alpha cannot read beta's statements.

    Out-of-scope and non-existent must be indistinguishable (both 403 with the
    same body), so the caller cannot probe which company ids exist.
    """
    alpha = s27_world["alpha"]
    scoped = make_user("fin_alpha@corp.sa", "finance_manager", [alpha])
    beta = s27_world["beta"].id
    out_of_scope = client.get(
        f"/api/v1/accounting/financial-statements?company_id={beta}",
        headers=auth(scoped),
    )
    missing = client.get(
        "/api/v1/accounting/financial-statements?company_id=999999",
        headers=auth(scoped),
    )
    assert out_of_scope.status_code == 403, out_of_scope.text
    assert missing.status_code == 403
    assert out_of_scope.json() == missing.json()
    # And the same user can read their own company.
    allowed = client.get(
        f"/api/v1/accounting/financial-statements?company_id={alpha.id}",
        headers=auth(scoped),
    )
    assert allowed.status_code == 200, allowed.text


def test_frontend_exposes_the_statements_tab():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    app_js = (root / "frontend" / "app.js").read_text(encoding="utf-8")
    index = (root / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "function renderStatements" in app_js
    assert "financial-statements" in app_js
    assert 'data-acct-tab="statements" data-perm="journal.read"' in index


def test_frontend_exposes_the_new_s27_tabs_and_renderers():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    app_js = (root / "frontend" / "app.js").read_text(encoding="utf-8")
    index = (root / "frontend" / "index.html").read_text(encoding="utf-8")

    assert '"parties"' in app_js and '"interbalances"' in app_js
    assert "function renderParties" in app_js
    assert "function renderInterbalances" in app_js
    assert "function renderInvoices" in app_js
    assert "moneyBlock(" in app_js  # receivables/payables totals

    # The tab buttons are permission-gated and bilingual.
    assert 'data-acct-tab="parties" data-perm="party.read"' in index
    assert 'data-acct-tab="interbalances" data-perm="interbalance.read"' in index


# --------------------------------------------------------------------------
# S26 Table 53: viewing revenue/expense shows the source lines, no new record
# --------------------------------------------------------------------------
def test_ledger_activity_shows_source_lines_and_adds_no_record(client, s27_world, auth, db):
    owner = s27_world["owner_all"]
    alpha = s27_world["alpha"].id
    _seed_ledger(db, alpha)

    from backend.db.models.accounting import Journal

    before = db.query(Journal).filter(Journal.company_id == alpha).count()

    res = client.get(
        f"/api/v1/accounting/ledger-activity?company_id={alpha}"
        "&fiscal_year=2026&fiscal_month=3",
        headers=auth(owner),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    # Only revenue/expense lines are shown, each pointing at its journal.
    assert {line["account_type"] for line in body["lines"]} == {"revenue"}
    line = body["lines"][0]
    assert line["journal_number"] == "J-1"
    assert line["entry_date"] == "2026-03-01"
    assert line["amount"] == "1000.00"
    assert line["currency"] == "SAR"
    # Viewing adds no record (Table 53: no extra posting).
    assert db.query(Journal).filter(Journal.company_id == alpha).count() == before


def test_ledger_activity_totals_reconcile_with_the_statement(client, s27_world, auth, db):
    owner = s27_world["owner_all"]
    alpha = s27_world["alpha"].id
    _seed_ledger(db, alpha)

    activity = client.get(
        f"/api/v1/accounting/ledger-activity?company_id={alpha}"
        "&fiscal_year=2026&fiscal_month=3",
        headers=auth(owner),
    ).json()
    fs = client.get(
        f"/api/v1/accounting/financial-statements?company_id={alpha}"
        "&fiscal_year=2026&fiscal_month=3",
        headers=auth(owner),
    ).json()

    by_type = {t["account_type"]: t for t in activity["totals"]}
    assert by_type["revenue"]["amount"] == fs["income_statement"]["total_revenue"][0]["amount"]


def test_ledger_activity_is_company_scoped(client, s27_world, auth, db, make_user):
    alpha = s27_world["alpha"]
    beta = s27_world["beta"].id
    _seed_ledger(db, alpha.id)

    # A finance manager holds journal.read but is confined to the granted company;
    # out-of-scope and non-existent are indistinguishable (same 403 body).
    scoped = make_user("fm.alpha@corp.sa", "finance_manager", [alpha])
    out_of_scope = client.get(
        f"/api/v1/accounting/ledger-activity?company_id={beta}", headers=auth(scoped)
    )
    missing = client.get(
        "/api/v1/accounting/ledger-activity?company_id=999999", headers=auth(scoped)
    )
    assert out_of_scope.status_code == 403, out_of_scope.text
    assert out_of_scope.json() == missing.json()
    assert client.get(
        f"/api/v1/accounting/ledger-activity?company_id={alpha.id}", headers=auth(scoped)
    ).status_code == 200


def test_ledger_activity_rejects_an_unknown_account_type(client, s27_world, auth):
    res = client.get(
        f"/api/v1/accounting/ledger-activity?company_id={s27_world['alpha'].id}"
        "&account_type=cash",
        headers=auth(s27_world["owner_all"]),
    )
    assert res.status_code == 422, res.text


def test_ledger_activity_requires_the_ledger_permission(client, s27_world, auth):
    alpha = s27_world["alpha"].id
    manager = s27_world["alpha_mgr"]
    res = client.get(
        f"/api/v1/accounting/ledger-activity?company_id={alpha}", headers=auth(manager)
    )
    assert res.status_code == 403, res.text


def test_frontend_exposes_the_ledger_activity_tab():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    app_js = (root / "frontend" / "app.js").read_text(encoding="utf-8")
    index = (root / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "function renderLedgerActivity" in app_js
    assert "ledger-activity" in app_js
    assert 'data-acct-tab="ledger" data-perm="journal.read"' in index


# --------------------------------------------------------------------------
# AC-27: the invoice and its ledger entry keep *one* reference
# --------------------------------------------------------------------------
def _account(db, company_id, code, atype):
    from sqlalchemy import select

    from backend.db.models.accounting import Account

    existing = db.execute(
        select(Account).where(Account.company_id == company_id, Account.code == code)
    ).scalars().first()
    if existing is not None:
        return existing
    acct = Account(company_id=company_id, code=code, name_ar="حساب", account_type=atype)
    db.add(acct)
    db.commit()
    db.refresh(acct)
    return acct


def _posted_journal(client, auth, user, company_id, db, *, currency="SAR"):
    debit = _account(db, company_id, "1100", "asset")
    credit = _account(db, company_id, "4100", "revenue")
    created = client.post(
        "/api/v1/accounting/journals",
        json={
            "company_id": company_id,
            "entry_date": "2027-10-01",
            "currency": currency,
            "lines": [
                {"account_id": debit.id, "debit": "1000.00", "credit": "0"},
                {"account_id": credit.id, "debit": "0", "credit": "1000.00"},
            ],
        },
        headers=auth(user),
    )
    assert created.status_code == 201, created.text
    journal_id = created.json()["id"]
    posted = client.post(
        f"/api/v1/accounting/journals/{journal_id}/post", headers=auth(user)
    )
    assert posted.status_code == 200, posted.text
    return journal_id


def test_invoice_and_journal_keep_one_reference(client, s27_world, auth, db):
    """AC-27: linking stores the entry id on the invoice; the entry is not re-created."""
    alpha = s27_world["alpha"].id
    inv = _invoice(client, auth, s27_world["accountant_all"], alpha, number="INV-L1")
    assert inv.status_code == 201, inv.text
    invoice_id = inv.json()["id"]
    assert inv.json()["journal_id"] is None

    journal_id = _posted_journal(client, auth, s27_world["accountant_all"], alpha, db)
    linked = client.post(
        f"/api/v1/accounting/invoices/{invoice_id}/journal",
        json={"journal_id": journal_id},
        headers=auth(s27_world["accountant_all"]),
    )
    assert linked.status_code == 200, linked.text
    assert linked.json()["journal_id"] == journal_id

    # Reading the invoice back returns the same single reference (persisted).
    listed = client.get(
        f"/api/v1/accounting/invoices?company_id={alpha}",
        headers=auth(s27_world["accountant_all"]),
    ).json()
    row = next(r for r in listed if r["id"] == invoice_id)
    assert row["journal_id"] == journal_id

    # The ledger still holds exactly one journal -- the link created no copy.
    journals = client.get(
        f"/api/v1/accounting/journals?company_id={alpha}",
        headers=auth(s27_world["accountant_all"]),
    ).json()
    assert [j["id"] for j in journals] == [journal_id]


def test_a_journal_cannot_be_linked_to_two_invoices(client, s27_world, auth, db):
    """AC-27: one entry, one reference -- a second invoice cannot reuse it."""
    alpha = s27_world["alpha"].id
    first = _invoice(client, auth, s27_world["accountant_all"], alpha, number="INV-L2")
    second = _invoice(client, auth, s27_world["accountant_all"], alpha, number="INV-L3")
    journal_id = _posted_journal(client, auth, s27_world["accountant_all"], alpha, db)

    ok = client.post(
        f"/api/v1/accounting/invoices/{first.json()['id']}/journal",
        json={"journal_id": journal_id},
        headers=auth(s27_world["accountant_all"]),
    )
    assert ok.status_code == 200, ok.text

    clash = client.post(
        f"/api/v1/accounting/invoices/{second.json()['id']}/journal",
        json={"journal_id": journal_id},
        headers=auth(s27_world["accountant_all"]),
    )
    assert clash.status_code == 409, clash.text


def test_an_invoice_cannot_carry_two_entries(client, s27_world, auth, db):
    alpha = s27_world["alpha"].id
    inv = _invoice(client, auth, s27_world["accountant_all"], alpha, number="INV-L4")
    first = _posted_journal(client, auth, s27_world["accountant_all"], alpha, db)
    second = _posted_journal(client, auth, s27_world["accountant_all"], alpha, db)

    assert client.post(
        f"/api/v1/accounting/invoices/{inv.json()['id']}/journal",
        json={"journal_id": first}, headers=auth(s27_world["accountant_all"]),
    ).status_code == 200
    again = client.post(
        f"/api/v1/accounting/invoices/{inv.json()['id']}/journal",
        json={"journal_id": second}, headers=auth(s27_world["accountant_all"]),
    )
    assert again.status_code == 409, again.text


def test_link_requires_a_posted_journal_of_the_same_company(client, s27_world, auth, db):
    alpha = s27_world["alpha"].id
    inv = _invoice(client, auth, s27_world["accountant_all"], alpha, number="INV-L5")

    # A draft entry is not an effect.
    debit = _account(db, alpha, "1101", "asset")
    credit = _account(db, alpha, "4101", "revenue")
    draft = client.post(
        "/api/v1/accounting/journals",
        json={
            "company_id": alpha, "entry_date": "2027-10-02",
            "lines": [
                {"account_id": debit.id, "debit": "5.00", "credit": "0"},
                {"account_id": credit.id, "debit": "0", "credit": "5.00"},
            ],
        },
        headers=auth(s27_world["accountant_all"]),
    ).json()
    not_posted = client.post(
        f"/api/v1/accounting/invoices/{inv.json()['id']}/journal",
        json={"journal_id": draft["id"]}, headers=auth(s27_world["accountant_all"]),
    )
    assert not_posted.status_code == 409, not_posted.text

    # A journal of another company is a 404, never a leak.
    beta = s27_world["beta"].id
    foreign = _posted_journal(client, auth, s27_world["accountant_all"], beta, db)
    cross = client.post(
        f"/api/v1/accounting/invoices/{inv.json()['id']}/journal",
        json={"journal_id": foreign}, headers=auth(s27_world["accountant_all"]),
    )
    assert cross.status_code == 404, cross.text


def test_link_refuses_a_currency_mismatch(client, s27_world, auth, db):
    """T10: the link can never bridge two currencies."""
    alpha = s27_world["alpha"].id
    inv = _invoice(
        client, auth, s27_world["accountant_all"], alpha, number="INV-L6", currency="SAR"
    )
    journal_id = _posted_journal(
        client, auth, s27_world["accountant_all"], alpha, db, currency="USD"
    )
    res = client.post(
        f"/api/v1/accounting/invoices/{inv.json()['id']}/journal",
        json={"journal_id": journal_id}, headers=auth(s27_world["accountant_all"]),
    )
    assert res.status_code == 422, res.text


def test_link_is_audited_and_permission_gated(client, s27_world, auth, db):
    from backend.db.models.ai import AuditLog

    alpha = s27_world["alpha"].id
    inv = _invoice(client, auth, s27_world["accountant_all"], alpha, number="INV-L7")
    journal_id = _posted_journal(client, auth, s27_world["accountant_all"], alpha, db)

    # A manager without the invoice permission cannot link.
    denied = client.post(
        f"/api/v1/accounting/invoices/{inv.json()['id']}/journal",
        json={"journal_id": journal_id}, headers=auth(s27_world["alpha_mgr"]),
    )
    assert denied.status_code == 403, denied.text

    client.post(
        f"/api/v1/accounting/invoices/{inv.json()['id']}/journal",
        json={"journal_id": journal_id}, headers=auth(s27_world["accountant_all"]),
    )
    actions = [row.action for row in db.query(AuditLog).all()]
    assert "invoice.journal_linked" in actions
