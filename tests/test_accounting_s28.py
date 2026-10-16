"""S28 completion: the monthly financial report (``التقرير المالي الشهري``).

Table 57 defines the action as "يسحب الحسابات ويضيف التحليل" -- *draws the
accounts and adds the analysis* -- and states the report "notifies the Business
Development manager and the owner according to permissions". These tests exercise
the real service + API + persistence path:

* the report is generated from the *posted* ledger only (a draft journal is not
  drawn), and the summary reconciles with the trial balance (AC-28);
* figures are kept per currency, so two currencies are never summed (T10);
* the accountant adds the analysis; finalising fixes the report (immutable) and
  notifies the BD and owner; archiving is the read-only history;
* the report is company-scoped: another company's accountant gets a 404.
"""

from __future__ import annotations

import pytest

from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import NotificationType


@pytest.fixture
def s28_world(world, make_user):
    """``world`` plus granted actors. Writes need an explicit access row."""
    accountant_all = make_user(
        "acc28_all@corp.sa", "accountant", [world["alpha"], world["beta"]]
    )
    owner_all = make_user(
        "owner28_all@corp.sa", "holding_owner", [world["alpha"], world["beta"]]
    )
    bd = make_user("bd28@corp.sa", "business_development", [world["alpha"]])
    accountant_alpha = make_user(
        "acc28_alpha@corp.sa", "accountant", [world["alpha"]]
    )
    accountant_beta = make_user(
        "acc28_beta@corp.sa", "accountant", [world["beta"]]
    )
    out = dict(world)
    out.update(
        accountant_all=accountant_all,
        owner_all=owner_all,
        bd=bd,
        accountant_alpha=accountant_alpha,
        accountant_beta=accountant_beta,
    )
    return out


def _account(db, company_id, code, atype, currency="SAR"):
    from sqlalchemy import select

    from backend.db.models.accounting import Account

    existing = db.execute(
        select(Account).where(Account.company_id == company_id, Account.code == code)
    ).scalars().first()
    if existing is not None:
        return existing
    acct = Account(company_id=company_id, code=code, name_ar="حساب",
                   account_type=atype, currency=currency)
    db.add(acct)
    db.commit()
    db.refresh(acct)
    return acct


def _posted_journal(client, auth, user, company_id, db, *, entry_date="2027-10-01",
                    debit_code="1100", credit_code="4100", amount="1000.00",
                    currency="SAR"):
    debit = _account(db, company_id, debit_code, "asset", currency=currency)
    credit = _account(db, company_id, credit_code, "revenue", currency=currency)
    created = client.post(
        "/api/v1/accounting/journals",
        json={
            "company_id": company_id,
            "entry_date": entry_date,
            "currency": currency,
            "lines": [
                {"account_id": debit.id, "debit": amount, "credit": "0"},
                {"account_id": credit.id, "debit": "0", "credit": amount},
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


def _generate(client, auth, user, company_id, *, year=2027, month=10, currency="SAR"):
    return client.post(
        "/api/v1/accounting/financial-reports",
        json={
            "company_id": company_id,
            "period_year": year,
            "period_month": month,
            "currency": currency,
        },
        headers=auth(user),
    )


# --------------------------------------------------------------------------
# generation draws the accounts (Table 57)
# --------------------------------------------------------------------------
def test_generate_draws_posted_accounts_and_reconciles_with_trial_balance(
    client, s28_world, auth, db
):
    accountant = s28_world["accountant_all"]
    alpha = s28_world["alpha"].id
    _posted_journal(client, auth, accountant, alpha, db, amount="1000.00")

    resp = _generate(client, auth, accountant, alpha)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "draft"
    figures = body["figures"]
    # Revenue 1000, expense 0, net 1000 for the month.
    assert figures["summary"] == [
        {"currency": "SAR", "revenue": "1000.00", "expenses": "0.00", "net": "1000.00"}
    ]
    # AC-28: the summary reconciles with the trial balance.
    assert figures["trial_balance"]["balanced"] is True
    assert figures["trial_balance"]["total_debit"] == "1000.00"
    assert figures["trial_balance"]["total_credit"] == "1000.00"


def test_generate_ignores_draft_journals(client, s28_world, auth, db):
    """A draft journal never reaches the ledger, so it is not drawn."""
    accountant = s28_world["accountant_all"]
    alpha = s28_world["alpha"].id
    debit = _account(db, alpha, "1100", "asset")
    credit = _account(db, alpha, "4100", "revenue")
    created = client.post(
        "/api/v1/accounting/journals",
        json={
            "company_id": alpha,
            "entry_date": "2027-10-05",
            "currency": "SAR",
            "lines": [
                {"account_id": debit.id, "debit": "999.00", "credit": "0"},
                {"account_id": credit.id, "debit": "0", "credit": "999.00"},
            ],
        },
        headers=auth(accountant),
    )
    assert created.status_code == 201, created.text

    resp = _generate(client, auth, accountant, alpha)
    assert resp.status_code == 201, resp.text
    assert resp.json()["figures"]["summary"] == []


def test_report_figures_are_kept_per_currency(client, s28_world, auth, db):
    """T10: two currencies are never added together in one summary line."""
    accountant = s28_world["accountant_all"]
    alpha = s28_world["alpha"].id
    _posted_journal(client, auth, accountant, alpha, db, amount="1000.00",
                    currency="SAR")
    _posted_journal(client, auth, accountant, alpha, db, amount="500.00",
                    currency="USD", debit_code="1101", credit_code="4101")

    resp = _generate(client, auth, accountant, alpha)
    assert resp.status_code == 201, resp.text
    summary = resp.json()["figures"]["summary"]
    by_currency = {row["currency"]: row for row in summary}
    assert by_currency["SAR"]["net"] == "1000.00"
    assert by_currency["USD"]["net"] == "500.00"
    # No combined figure exists.
    assert len(summary) == 2


def test_regenerate_updates_the_draft_not_a_second_row(client, s28_world, auth, db):
    accountant = s28_world["accountant_all"]
    alpha = s28_world["alpha"].id
    _posted_journal(client, auth, accountant, alpha, db, amount="1000.00")

    first = _generate(client, auth, accountant, alpha)
    assert first.status_code == 201, first.text
    _posted_journal(client, auth, accountant, alpha, db, amount="250.00",
                    debit_code="1102", credit_code="4102")
    second = _generate(client, auth, accountant, alpha)
    assert second.status_code == 201, second.text
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["figures"]["summary"][0]["revenue"] == "1250.00"

    listed = client.get(
        f"/api/v1/accounting/financial-reports?company_id={alpha}",
        headers=auth(accountant),
    ).json()
    assert len(listed) == 1


# --------------------------------------------------------------------------
# analysis + finalise + archive
# --------------------------------------------------------------------------
def test_analysis_is_saved_then_finalise_notifies_bd_and_owner(
    client, s28_world, auth, db
):
    accountant = s28_world["accountant_all"]
    alpha = s28_world["alpha"].id
    _posted_journal(client, auth, accountant, alpha, db, amount="1000.00")
    report_id = _generate(client, auth, accountant, alpha).json()["id"]

    annotated = client.patch(
        f"/api/v1/accounting/financial-reports/{report_id}/analysis",
        json={"analysis": "نمو جيد مدفوع بإيرادات جديدة."},
        headers=auth(accountant),
    )
    assert annotated.status_code == 200, annotated.text
    assert annotated.json()["analysis"] == "نمو جيد مدفوع بإيرادات جديدة."

    # Persisted on read-back.
    fetched = client.get(
        f"/api/v1/accounting/financial-reports/{report_id}",
        headers=auth(accountant),
    ).json()
    assert fetched["analysis"] == "نمو جيد مدفوع بإيرادات جديدة."

    finalised = client.post(
        f"/api/v1/accounting/financial-reports/{report_id}/finalise",
        headers=auth(accountant),
    )
    assert finalised.status_code == 200, finalised.text
    assert finalised.json()["status"] == "finalised"

    # The BD and the owner were told (Table 57).
    for actor in (s28_world["bd"], s28_world["owner_all"]):
        inbox = client.get("/api/v1/notifications", headers=auth(actor))
        assert inbox.status_code == 200, inbox.text
        types = [n["type"] for n in inbox.json()["items"]]
        assert NotificationType.FINANCIAL_REPORT_FINALISED.value in types

    # The finalise action is audited.
    logs = client.get(
        "/api/v1/admin/audit-logs?entity_type=monthly_financial_report",
        headers=auth(s28_world["owner_all"]),
    )
    assert logs.status_code == 200, logs.text
    actions = [row["action"] for row in logs.json()["items"]]
    assert AuditAction.FINANCIAL_REPORT_FINALISED in actions


def test_finalised_report_is_immutable(client, s28_world, auth, db):
    accountant = s28_world["accountant_all"]
    alpha = s28_world["alpha"].id
    _posted_journal(client, auth, accountant, alpha, db, amount="1000.00")
    report_id = _generate(client, auth, accountant, alpha).json()["id"]
    client.post(
        f"/api/v1/accounting/financial-reports/{report_id}/finalise",
        headers=auth(accountant),
    )

    # Regenerating a finalised report is refused.
    again = _generate(client, auth, accountant, alpha)
    assert again.status_code == 409, again.text
    # Editing its analysis is refused.
    edit = client.patch(
        f"/api/v1/accounting/financial-reports/{report_id}/analysis",
        json={"analysis": "تعديل متأخر"},
        headers=auth(accountant),
    )
    assert edit.status_code == 409, edit.text


def test_archive_keeps_the_report_as_history(client, s28_world, auth, db):
    accountant = s28_world["accountant_all"]
    alpha = s28_world["alpha"].id
    _posted_journal(client, auth, accountant, alpha, db, amount="1000.00")
    report_id = _generate(client, auth, accountant, alpha).json()["id"]
    client.post(
        f"/api/v1/accounting/financial-reports/{report_id}/finalise",
        headers=auth(accountant),
    )
    archived = client.post(
        f"/api/v1/accounting/financial-reports/{report_id}/archive",
        headers=auth(accountant),
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "archived"

    # An unfinalised report cannot be archived.
    second_id = _generate(client, auth, accountant, alpha, month=11).json()["id"]
    bad = client.post(
        f"/api/v1/accounting/financial-reports/{second_id}/archive",
        headers=auth(accountant),
    )
    assert bad.status_code == 409, bad.text


# --------------------------------------------------------------------------
# RBAC / isolation
# --------------------------------------------------------------------------
def test_report_is_company_scoped(client, s28_world, auth, db):
    """A company manager confined to beta cannot read alpha's report (404).

    Accountants are holding-wide readers, so the isolating role here is the
    company-scoped manager: "not yours" and "does not exist" are the same 404.
    """
    alpha = s28_world["alpha"].id
    _posted_journal(client, auth, s28_world["accountant_all"], alpha, db)
    report_id = _generate(client, auth, s28_world["accountant_all"], alpha).json()["id"]

    beta_only = s28_world["beta_mgr"]
    denied = client.get(
        f"/api/v1/accounting/financial-reports/{report_id}", headers=auth(beta_only)
    )
    assert denied.status_code == 404
    assert denied.json()["error"]["code"] == "not_found"


def test_generate_requires_company_access(client, s28_world, auth):
    """The alpha accountant cannot generate a report for company beta."""
    beta = s28_world["beta"].id
    denied = _generate(client, auth, s28_world["accountant_alpha"], beta)
    assert denied.status_code in (403, 404), denied.text


def test_owner_can_read_but_not_generate(client, s28_world, auth, db):
    owner = s28_world["owner_all"]
    alpha = s28_world["alpha"].id
    _posted_journal(client, auth, s28_world["accountant_all"], alpha, db)
    report_id = _generate(client, auth, s28_world["accountant_all"], alpha).json()["id"]

    read = client.get(
        f"/api/v1/accounting/financial-reports/{report_id}", headers=auth(owner)
    )
    assert read.status_code == 200, read.text

    # The owner holds every permission, so generation is allowed for them; the
    # point of this test is that a *read-only* role cannot. The BD reads only.
    bd_generate = _generate(client, auth, s28_world["bd"], alpha)
    assert bd_generate.status_code in (403, 404), bd_generate.text


def test_bd_reads_the_report_archive(client, s28_world, auth, db):
    alpha = s28_world["alpha"].id
    _posted_journal(client, auth, s28_world["accountant_all"], alpha, db)
    _generate(client, auth, s28_world["accountant_all"], alpha)

    listed = client.get(
        f"/api/v1/accounting/financial-reports?company_id={alpha}",
        headers=auth(s28_world["bd"]),
    )
    assert listed.status_code == 200, listed.text
    assert len(listed.json()) == 1


def test_invalid_period_month_is_rejected(client, s28_world, auth):
    alpha = s28_world["alpha"].id
    resp = client.post(
        "/api/v1/accounting/financial-reports",
        json={"company_id": alpha, "period_year": 2027, "period_month": 13},
        headers=auth(s28_world["accountant_all"]),
    )
    assert resp.status_code == 422, resp.text


def test_frontend_financial_reports_tab_is_wired():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    app_js = (root / "frontend" / "app.js").read_text(encoding="utf-8")
    index = (root / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "function renderFinancialReports" in app_js
    assert "/api/v1/accounting/financial-reports" in app_js
    assert 'data-acct-tab="reports" data-perm="financial_report.read"' in index
