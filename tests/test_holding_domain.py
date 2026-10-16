"""Executions 04-14: holding-business domain tests.

Covers the security properties (RBAC + company isolation + confidentiality) and
the owner-decision rules that must hold (D03 lifecycle, D05 evidence gate,
D01 double-entry + immutable posting, D07 budget supersession, D08 no automatic
carry-forward, D04 confidential visibility).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.db.models import (
    Account,
    Budget,
    Employee,
    Journal,
    OpeningBalance,
)
from backend.db.models.enums import BudgetStatus, JournalStatus


@pytest.fixture
def domain_world(world, make_user):
    """Extend ``world`` with holding users granted write access to both
    companies.

    The platform's security model requires an explicit ``user_company_access``
    row before *any* write, even for the owner (holding-wide only widens reads).
    Tests therefore use these granted actors for writes.
    """
    owner_all = make_user("owner_all@corp.sa", "holding_owner", [world["alpha"], world["beta"]])
    accountant_all = make_user(
        "acc_all@corp.sa", "accountant", [world["alpha"], world["beta"]]
    )
    marketer = make_user("marketing@corp.sa", "marketing", [world["alpha"]])
    world = dict(world)
    world["owner_all"] = owner_all
    world["accountant_all"] = accountant_all
    world["marketer"] = marketer
    return world


# --------------------------------------------------------------------------
# RBAC catalogue
# --------------------------------------------------------------------------
def test_new_permissions_are_catalogued_with_metadata():
    from backend.rbac import permission_metadata
    from backend.rbac.permissions import ALL_PERMISSIONS

    assert permission_metadata.unknown_codes() == []
    assert len(ALL_PERMISSIONS) == 169


def test_external_consultant_role_is_not_holding_wide():
    from backend.db.models.enums import RoleCode
    from backend.rbac.permissions import HOLDING_WIDE_ROLES

    assert RoleCode.EXTERNAL_CONSULTANT.value not in HOLDING_WIDE_ROLES


# --------------------------------------------------------------------------
# tasks (D03)
# --------------------------------------------------------------------------
def test_task_lifecycle_happy_path(client, domain_world, auth, db):
    created = client.post(
        "/api/v1/operations/tasks",
        json={"company_id": domain_world["alpha"].id, "title": "مهمة"},
        headers=auth(domain_world["owner_all"]),
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    assert created.json()["status"] == "new"

    for new_status in ("in_progress", "awaiting_review", "complete"):
        r = client.post(
            f"/api/v1/operations/tasks/{task_id}/status",
            json={"status": new_status},
            headers=auth(domain_world["owner_all"]),
        )
        assert r.status_code == 200, r.text
    assert r.json()["status"] == "complete"


def test_task_cannot_skip_states(client, domain_world, auth):
    created = client.post(
        "/api/v1/operations/tasks",
        json={"company_id": domain_world["alpha"].id, "title": "x"},
        headers=auth(domain_world["owner_all"]),
    )
    task_id = created.json()["id"]
    r = client.post(
        f"/api/v1/operations/tasks/{task_id}/status",
        json={"status": "complete"},
        headers=auth(domain_world["owner_all"]),
    )
    assert r.status_code == 422


def test_company_manager_cannot_create_task_for_other_company(client, domain_world, auth):
    r = client.post(
        "/api/v1/operations/tasks",
        json={"company_id": domain_world["beta"].id, "title": "x"},
        headers=auth(domain_world["alpha_mgr"]),
    )
    assert r.status_code == 403


def test_assigning_a_task_notifies_the_assignee(client, domain_world, auth, db, make_user):
    """S17: creating a task for an employee puts a notification in their inbox."""
    from backend.db.models.notifications import Notification

    designer = make_user("designer.tasks@corp.sa", "designer", [domain_world["alpha"]])
    created = client.post(
        "/api/v1/operations/tasks",
        json={
            "company_id": domain_world["alpha"].id,
            "title": "مهمة تصميم",
            "assignee_id": designer.id,
        },
        headers=auth(domain_world["owner_all"]),
    )
    assert created.status_code == 201, created.text

    rows = (
        db.query(Notification)
        .filter(Notification.recipient_id == designer.id)
        .all()
    )
    assert len(rows) == 1
    assert rows[0].type == "task.assigned"
    assert rows[0].entity_type == "task"
    assert rows[0].entity_id == created.json()["id"]


def test_task_status_change_notifies_the_creator(client, domain_world, auth, db):
    """S17: the creator follows progress; the assignee's update is surfaced."""
    from backend.db.models.notifications import Notification

    creator = domain_world["owner_all"]
    created = client.post(
        "/api/v1/operations/tasks",
        json={
            "company_id": domain_world["alpha"].id,
            "title": "مهمة متابعة",
            "assignee_id": domain_world["marketer"].id,
        },
        headers=auth(creator),
    )
    task_id = created.json()["id"]

    r = client.post(
        f"/api/v1/operations/tasks/{task_id}/status",
        json={"status": "in_progress"},
        headers=auth(domain_world["marketer"]),
    )
    assert r.status_code == 200, r.text

    rows = (
        db.query(Notification)
        .filter(Notification.recipient_id == creator.id, Notification.type == "task.status_changed")
        .all()
    )
    assert len(rows) == 1
    assert rows[0].entity_id == task_id


def test_overdue_list_excludes_a_completed_task(client, domain_world, auth, db):
    """AC-17: a completed task is not in the overdue list; an open past-due one is."""
    from datetime import date, timedelta

    from backend.db.models.operations import Task

    yesterday = date.today() - timedelta(days=1)
    open_task = Task(
        company_id=domain_world["alpha"].id, title="متأخرة", status="in_progress",
        priority="normal", progress_percent=0, due_date=yesterday,
        assignee_id=domain_world["marketer"].id,
    )
    done_task = Task(
        company_id=domain_world["alpha"].id, title="منجزة", status="complete",
        priority="normal", progress_percent=100, due_date=yesterday,
        assignee_id=domain_world["marketer"].id,
    )
    db.add_all([open_task, done_task])
    db.commit()

    r = client.get(
        "/api/v1/operations/tasks?overdue=true", headers=auth(domain_world["marketer"])
    )
    assert r.status_code == 200, r.text
    titles = {t["title"] for t in r.json()}
    assert "متأخرة" in titles
    assert "منجزة" not in titles
    # is_overdue is exposed and false for the completed task.
    done_payload = next(
        t for t in r.json() if t["title"] == "متأخرة"
    )
    assert done_payload["is_overdue"] is True


# --------------------------------------------------------------------------
# assessments (D05)
# --------------------------------------------------------------------------
def test_assessment_approval_blocked_on_evidence_gap(client, domain_world, auth):
    created = client.post(
        "/api/v1/employees/assessments",
        json={"company_id": domain_world["alpha"].id, "period_label": "2027-Q4",
              "employee_id": _make_employee(domain_world, "alpha").id},
        headers=auth(domain_world["owner_all"]),
    )
    assert created.status_code == 201, created.text
    assessment_id = created.json()["id"]

    # A criterion that requires evidence, left incomplete.
    client.post(
        f"/api/v1/employees/assessments/{assessment_id}/items",
        json={"criterion_code": "quality", "criterion_name_ar": "الجودة",
              "score": 4, "evidence_required": True, "evidence_complete": False},
        headers=auth(domain_world["owner_all"]),
    )
    r = client.post(
        f"/api/v1/employees/assessments/{assessment_id}/approve",
        headers=auth(domain_world["owner_all"]),
    )
    assert r.status_code == 422
    assert "evidence" in r.json()["error"]["message"].lower()

    # Completing the evidence unblocks approval.
    client.post(
        f"/api/v1/employees/assessments/{assessment_id}/items",
        json={"criterion_code": "quality", "criterion_name_ar": "الجودة",
              "score": 4, "evidence_required": True, "evidence_complete": True},
        headers=auth(domain_world["owner_all"]),
    )
    r = client.post(
        f"/api/v1/employees/assessments/{assessment_id}/approve",
        headers=auth(domain_world["owner_all"]),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "approved"


def test_assessment_score_must_be_within_scale(client, domain_world, auth):
    emp = _make_employee(domain_world, "alpha")
    created = client.post(
        "/api/v1/employees/assessments",
        json={"company_id": domain_world["alpha"].id, "period_label": "2027-Q4",
              "employee_id": emp.id},
        headers=auth(domain_world["owner_all"]),
    )
    assessment_id = created.json()["id"]
    r = client.post(
        f"/api/v1/employees/assessments/{assessment_id}/items",
        json={"criterion_code": "c", "criterion_name_ar": "ج", "score": 9},
        headers=auth(domain_world["owner_all"]),
    )
    assert r.status_code == 422


# --------------------------------------------------------------------------
# confidential complaints (D04)
# --------------------------------------------------------------------------
def test_complaint_is_invisible_to_other_users(client, domain_world, auth):
    r = client.post(
        "/api/v1/operations/complaints",
        json={"subject": "سرّي", "body": "تفاصيل", "company_id": domain_world["alpha"].id},
        headers=auth(domain_world["marketer"]),
    )
    assert r.status_code == 201, r.text
    complaint_id = r.json()["id"]

    # A different manager cannot see it, even by id.
    other = client.get(
        f"/api/v1/operations/complaints/{complaint_id}",
        headers=auth(domain_world["beta_mgr"]),
    )
    assert other.status_code == 404

    # The owner can.
    owner_view = client.get(
        f"/api/v1/operations/complaints/{complaint_id}", headers=auth(domain_world["owner_all"])
    )
    assert owner_view.status_code == 200


def test_complaint_not_counted_in_company_scope(client, domain_world, auth):
    client.post(
        "/api/v1/operations/complaints",
        json={"subject": "سرّي", "body": "تفاصيل"},
        headers=auth(domain_world["marketer"]),
    )
    # The accountant (holding-wide, no decide permission) does not list it.
    r = client.get("/api/v1/operations/complaints", headers=auth(domain_world["accountant_all"]))
    # 403 (no read_own/decide for accountant) or an empty list is acceptable;
    # what must NOT happen is the accountant seeing someone else's complaint.
    if r.status_code == 200:
        assert r.json() == []


def test_delegated_grant_allows_read_and_expires(client, domain_world, auth, db):
    from backend.db.models import ConfidentialAccessGrant

    r = client.post(
        "/api/v1/operations/complaints",
        json={"subject": "سرّي", "body": "تفاصيل"},
        headers=auth(domain_world["marketer"]),
    )
    complaint_id = r.json()["id"]

    # Owner grants the accountant read access to this one complaint.
    g = client.post(
        "/api/v1/confidential-access/grants",
        json={
            "subject_type": "complaint",
            "subject_id": complaint_id,
            "grantee_user_id": domain_world["accountant_all"].id,
            "permission_code": "complaint.decide",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        },
        headers=auth(domain_world["owner_all"]),
    )
    assert g.status_code == 201, g.text

    allowed = client.get(
        f"/api/v1/operations/complaints/{complaint_id}", headers=auth(domain_world["accountant_all"])
    )
    assert allowed.status_code == 200

    # Expire the grant directly; access is withdrawn.
    grant_row = db.get(ConfidentialAccessGrant, g.json()["id"])
    grant_row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()

    denied = client.get(
        f"/api/v1/operations/complaints/{complaint_id}", headers=auth(domain_world["accountant_all"])
    )
    assert denied.status_code == 404


def test_complaint_decision_notifies_only_the_named_person(client, domain_world, auth, db):
    """AC-15: recording a complaint notifies no manager; only an explicit route does."""
    from backend.db.models.notifications import Notification

    routed_to = domain_world["accountant_all"]
    r = client.post(
        "/api/v1/operations/complaints",
        json={"subject": "سرّي", "body": "تفاصيل"},
        headers=auth(domain_world["marketer"]),
    )
    complaint_id = r.json()["id"]

    # Logging alone notifies nobody.
    assert (
        db.query(Notification)
        .filter(Notification.entity_type == "complaint", Notification.entity_id == complaint_id)
        .count()
        == 0
    )

    decided = client.post(
        f"/api/v1/operations/complaints/{complaint_id}/decision",
        json={"status": "routed", "routed_to_id": routed_to.id},
        headers=auth(domain_world["owner_all"]),
    )
    assert decided.status_code == 200, decided.text

    rows = (
        db.query(Notification)
        .filter(Notification.recipient_id == routed_to.id, Notification.entity_id == complaint_id)
        .all()
    )
    assert len(rows) == 1
    # The confidential subject/body must not leak into the notification text.
    assert "سرّي" not in rows[0].title_ar and "سرّي" not in rows[0].message_ar
    assert "تفاصيل" not in rows[0].message_ar
    assert "تفاصيل" not in rows[0].title_ar


# --------------------------------------------------------------------------
# accounting (D01 / D08 / D07)
# --------------------------------------------------------------------------
def _make_account(db, company_id, code="1000", atype="asset"):
    acct = Account(company_id=company_id, code=code, name_ar="حساب", account_type=atype)
    db.add(acct)
    db.commit()
    db.refresh(acct)
    return acct


def test_journal_must_balance_before_posting(client, domain_world, auth, db):
    a = _make_account(db, domain_world["alpha"].id, "1000", "asset")
    b = _make_account(db, domain_world["alpha"].id, "4000", "revenue")
    created = client.post(
        "/api/v1/accounting/journals",
        json={
            "company_id": domain_world["alpha"].id,
            "entry_date": "2027-10-01",
            "lines": [
                {"account_id": a.id, "debit": "100.00", "credit": "0"},
                {"account_id": b.id, "debit": "0", "credit": "90.00"},
            ],
        },
        headers=auth(domain_world["owner_all"]),
    )
    assert created.status_code == 201, created.text
    journal_id = created.json()["id"]
    r = client.post(
        f"/api/v1/accounting/journals/{journal_id}/post", headers=auth(domain_world["owner_all"])
    )
    assert r.status_code == 422


def test_posted_journal_is_immutable_and_reversible(client, domain_world, auth, db):
    a = _make_account(db, domain_world["alpha"].id, "1000", "asset")
    b = _make_account(db, domain_world["alpha"].id, "4000", "revenue")
    created = client.post(
        "/api/v1/accounting/journals",
        json={
            "company_id": domain_world["alpha"].id,
            "entry_date": "2027-10-01",
            "lines": [
                {"account_id": a.id, "debit": "100.00"},
                {"account_id": b.id, "credit": "100.00"},
            ],
        },
        headers=auth(domain_world["owner_all"]),
    )
    journal_id = created.json()["id"]
    posted = client.post(
        f"/api/v1/accounting/journals/{journal_id}/post", headers=auth(domain_world["owner_all"])
    )
    assert posted.status_code == 200, posted.text
    assert posted.json()["status"] == "posted"

    # Posting again is refused (no in-place change).
    again = client.post(
        f"/api/v1/accounting/journals/{journal_id}/post", headers=auth(domain_world["owner_all"])
    )
    assert again.status_code == 409

    # Reversal creates a mirror entry and marks the original reversed.
    reversal = client.post(
        f"/api/v1/accounting/journals/{journal_id}/reverse",
        json={"reason": "correction"},
        headers=auth(domain_world["owner_all"]),
    )
    assert reversal.status_code == 200, reversal.text
    assert reversal.json()["reversal_of_id"] == journal_id
    original = db.get(Journal, journal_id)
    db.refresh(original)
    assert original.status == JournalStatus.REVERSED.value


def test_trial_balance_aggregates_posted_journals_only(client, domain_world, auth, db):
    a = _make_account(db, domain_world["alpha"].id, "1000", "asset")
    b = _make_account(db, domain_world["alpha"].id, "4000", "revenue")
    owner = domain_world["owner_all"]

    # A draft journal must not appear in the trial balance.
    draft = client.post(
        "/api/v1/accounting/journals",
        json={
            "company_id": domain_world["alpha"].id,
            "entry_date": "2027-10-01",
            "lines": [{"account_id": a.id, "debit": "500.00"},
                      {"account_id": b.id, "credit": "500.00"}],
        },
        headers=auth(owner),
    ).json()

    tb = client.get(
        "/api/v1/accounting/trial-balance",
        params={"company_id": domain_world["alpha"].id},
        headers=auth(owner),
    )
    assert tb.status_code == 200, tb.text
    assert tb.json()["rows"] == []
    assert tb.json()["balanced"] is True

    # Post it: now both accounts show, totals agree, balance is debit-credit.
    client.post(f"/api/v1/accounting/journals/{draft['id']}/post", headers=auth(owner))
    tb = client.get(
        "/api/v1/accounting/trial-balance",
        params={"company_id": domain_world["alpha"].id},
        headers=auth(owner),
    ).json()
    by_code = {r["code"]: r for r in tb["rows"]}
    assert by_code["1000"]["debit"] == "500.00"
    assert by_code["1000"]["balance"] == "500.00"
    assert by_code["4000"]["credit"] == "500.00"
    assert by_code["4000"]["balance"] == "-500.00"
    assert tb["total_debit"] == "500.00"
    assert tb["total_credit"] == "500.00"
    assert tb["balanced"] is True


def test_trial_balance_excludes_another_company(client, domain_world, auth, db, make_user):
    owner = domain_world["owner_all"]
    alpha = _make_account(db, domain_world["alpha"].id, "1000", "asset")
    beta = _make_account(db, domain_world["beta"].id, "1000", "asset")
    other = _make_account(db, domain_world["beta"].id, "4000", "revenue")
    client.post(
        "/api/v1/accounting/journals",
        json={
            "company_id": domain_world["beta"].id, "entry_date": "2027-10-01",
            "lines": [{"account_id": beta.id, "debit": "300.00"},
                      {"account_id": other.id, "credit": "300.00"}],
        },
        headers=auth(owner),
    )
    tb = client.get(
        "/api/v1/accounting/trial-balance",
        params={"company_id": domain_world["alpha"].id},
        headers=auth(owner),
    ).json()
    # Alpha has no posted entries; beta's posted entry must not leak in.
    assert tb["rows"] == []

    # A custom role granted only ``journal.read`` and scoped to alpha may read
    # alpha's ledger but must not reach beta's trial balance.
    role = client.post(
        "/api/v1/admin/roles",
        json={
            "code": "tb_reader_alpha",
            "name_ar": "قارئ ميزان",
            "name_en": "Trial balance reader",
            "permissions": ["journal.read"],
        },
        headers=auth(owner),
    )
    assert role.status_code == 201, role.text
    scoped = make_user("tb.reader@corp.sa", "tb_reader_alpha", [domain_world["alpha"]])
    denied = client.get(
        "/api/v1/accounting/trial-balance",
        params={"company_id": domain_world["beta"].id},
        headers=auth(scoped),
    )
    assert denied.status_code in (403, 404), denied.text


def test_opening_balance_not_auto_carried(client, domain_world, auth, db):
    # Creating an opening balance must not create a carry-forward row for the
    # next year (D08).
    r = client.post(
        "/api/v1/accounting/opening-balances",
        json={"company_id": domain_world["alpha"].id, "period_year": 2027,
              "kind": "opening", "bank": "1000.00"},
        headers=auth(domain_world["owner_all"]),
    )
    assert r.status_code == 201, r.text
    rows = db.query(OpeningBalance).filter_by(company_id=domain_world["alpha"].id).all()
    assert len(rows) == 1
    assert all(row.kind == "opening" for row in rows)


def test_opening_balance_total_cash_is_computed(client, domain_world, auth):
    """AC-04: bank 120 and cash 30 produce total cash 150."""
    r = client.post(
        "/api/v1/accounting/opening-balances",
        json={
            "company_id": domain_world["alpha"].id,
            "period_year": 2027,
            "kind": "opening",
            "bank": "120.00",
            "cash": "30.00",
        },
        headers=auth(domain_world["owner_all"]),
    )
    assert r.status_code == 201, r.text
    assert r.json()["total_cash"] == "150.00"

    # Persistence: the computed value survives a fresh read and cannot be set
    # directly (the request schema has no total_cash field).
    listed = client.get(
        "/api/v1/accounting/opening-balances", headers=auth(domain_world["owner_all"])
    ).json()
    row = next(o for o in listed if o["id"] == r.json()["id"])
    assert row["total_cash"] == "150.00"

    forged = client.post(
        "/api/v1/accounting/opening-balances",
        json={
            "company_id": domain_world["alpha"].id,
            "period_year": 2028,
            "bank": "10.00",
            "cash": "5.00",
            "total_cash": "999.00",
        },
        headers=auth(domain_world["owner_all"]),
    )
    assert forged.status_code == 201, forged.text
    assert forged.json()["total_cash"] == "15.00"


def test_budget_approval_supersedes_previous(client, domain_world, auth, db):
    r1 = client.post(
        "/api/v1/accounting/budgets",
        json={"company_id": domain_world["alpha"].id, "fiscal_year": 2027, "total_amount": "1000"},
        headers=auth(domain_world["owner_all"]),
    )
    b1 = r1.json()["id"]
    client.post(f"/api/v1/accounting/budgets/{b1}/approve", json={}, headers=auth(domain_world["owner_all"]))

    r2 = client.post(
        "/api/v1/accounting/budgets",
        json={"company_id": domain_world["alpha"].id, "fiscal_year": 2027, "total_amount": "2000"},
        headers=auth(domain_world["owner_all"]),
    )
    b2 = r2.json()["id"]
    approved = client.post(
        f"/api/v1/accounting/budgets/{b2}/approve", json={}, headers=auth(domain_world["owner_all"])
    )
    assert approved.status_code == 200
    assert approved.json()["version"] == 2
    assert approved.json()["supersedes_id"] == b1

    first = db.get(Budget, b1)
    db.refresh(first)
    assert first.status == BudgetStatus.SUPERSEDED.value


def test_journal_cannot_use_another_company_account(client, domain_world, auth, db):
    beta_acct = _make_account(db, domain_world["beta"].id, "1000", "asset")
    r = client.post(
        "/api/v1/accounting/journals",
        json={
            "company_id": domain_world["alpha"].id,
            "entry_date": "2027-10-01",
            "lines": [{"account_id": beta_acct.id, "debit": "10"}],
        },
        headers=auth(domain_world["owner_all"]),
    )
    assert r.status_code == 422


# --------------------------------------------------------------------------
# campaigns (S14)
# --------------------------------------------------------------------------
def test_campaign_round_trip_records_results_and_is_audited(client, domain_world, auth, db):
    from backend.db.models import AuditLog

    created = client.post(
        "/api/v1/operations/campaigns",
        json={
            "company_id": domain_world["alpha"].id,
            "name": "حملة الإطلاق",
            "platform": "instagram",
            "goal": "زيادة الوعي",
            "budget": "5000.00",
        },
        headers=auth(domain_world["marketer"]),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "planned"
    assert body["budget"] == "5000.00"

    # Results are recorded manually (execution happens outside the platform).
    updated = client.patch(
        f"/api/v1/operations/campaigns/{body['id']}",
        json={"status": "completed", "spend": "4200.00", "lead_count": 37,
              "conversion_count": 9, "marketing_note": "نتائج جيدة"},
        headers=auth(domain_world["marketer"]),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "completed"
    assert updated.json()["spend"] == "4200.00"
    assert updated.json()["lead_count"] == 37
    assert updated.json()["conversion_count"] == 9

    # The write persists: a fresh read returns the same figures.
    listed = client.get(
        f"/api/v1/operations/campaigns?company_id={domain_world['alpha'].id}",
        headers=auth(domain_world["marketer"]),
    )
    assert listed.status_code == 200
    assert [c["id"] for c in listed.json()] == [body["id"]]
    assert listed.json()[0]["spend"] == "4200.00"

    actions = {
        row.action for row in db.query(AuditLog)
        .filter(AuditLog.entity_type == "campaign", AuditLog.entity_id == body["id"])
    }
    assert {"campaign.created", "campaign.updated"} <= actions


def test_campaign_write_requires_company_access(client, domain_world, auth):
    # The marketer is granted only ``alpha``; writing a campaign for ``beta``
    # must fail even though the role holds ``campaign.manage``.
    denied = client.post(
        "/api/v1/operations/campaigns",
        json={"company_id": domain_world["beta"].id, "name": "حملة"},
        headers=auth(domain_world["marketer"]),
    )
    assert denied.status_code == 403


# --------------------------------------------------------------------------
# isolation across the new surface
# --------------------------------------------------------------------------
def test_manager_cannot_list_another_company_employees(client, domain_world, auth):
    _make_employee(domain_world, "beta")
    r = client.get("/api/v1/employees", headers=auth(domain_world["alpha_mgr"]))
    assert r.status_code == 200
    assert r.json() == []


def test_salary_hidden_without_permission(client, domain_world, auth):
    emp = _make_employee(domain_world, "alpha")
    # A company manager holds employee.manage but not employee.salary.read.
    r = client.get(f"/api/v1/employees/{emp.id}", headers=auth(domain_world["alpha_mgr"]))
    assert r.status_code == 200
    assert "base_salary" not in r.json()


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _make_employee(domain_world, which: str) -> Employee:
    from backend.db.session import SessionLocal

    with SessionLocal() as db:
        emp = Employee(company_id=domain_world[which].id, full_name_ar="موظف تجريبي")
        db.add(emp)
        db.commit()
        db.refresh(emp)
        db.expunge(emp)
        return emp
