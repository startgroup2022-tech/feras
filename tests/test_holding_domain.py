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
    assert len(ALL_PERMISSIONS) == 149


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
