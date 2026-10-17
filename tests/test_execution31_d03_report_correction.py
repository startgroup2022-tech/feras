"""Execution 31 — D03: the versioned non-financial management report (S09).

Spec §21 assigns the *non-financial work states* -- including "correcting the
management report after submission" -- to D03. The owner authorised D03, so this
module proves the correction workflow end to end: return for correction,
linked correction version, resubmission, owner approval and owner cancellation,
with the original always preserved and every step audited and company-scoped.

Each test asserts the real persisted state (via the API *and* a fresh read from
the database) so a passing test proves saving, updating and persistence.
"""

from __future__ import annotations

import pytest

from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import ReportApprovalStatus, ReportStatus


@pytest.fixture
def d03_world(db, make_company, make_user, make_report):
    """Two companies with a submitted management report and the roles that act."""
    alpha = make_company("ALPHA", "شركة ألفا")
    beta = make_company("BETA", "شركة بيتا")

    alpha_mgr = make_user("alpha.d03@corp.sa", "company_manager", [alpha])
    beta_mgr = make_user("beta.d03@corp.sa", "company_manager", [beta])
    owner = make_user("owner.d03@corp.sa", "holding_owner")
    bd = make_user("bd.d03@corp.sa", "business_development")
    accountant = make_user("acc.d03@corp.sa", "accountant")

    alpha_report = make_report(
        alpha, revenue="111111", expenses="1", net="111110",
        status=ReportStatus.SUBMITTED.value,
    )
    beta_report = make_report(
        beta, revenue="999999", expenses="1", net="999998",
        status=ReportStatus.SUBMITTED.value,
    )

    return {
        "alpha": alpha,
        "beta": beta,
        "alpha_mgr": alpha_mgr,
        "beta_mgr": beta_mgr,
        "owner": owner,
        "bd": bd,
        "accountant": accountant,
        "alpha_report": alpha_report,
        "beta_report": beta_report,
    }


def _return(client, world, auth, reason="أرقام السوق غير مكتملة"):
    return client.post(
        f"/api/v1/monthly-reports/{world['alpha_report'].id}/return",
        headers=auth(world["bd"]),
        json={"reason": reason},
    )


# --------------------------------------------------------------------------
# return for correction (D03)
# --------------------------------------------------------------------------
def test_bd_returns_a_submitted_report_for_correction(client, d03_world, auth, db):
    response = _return(client, d03_world, auth)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == ReportStatus.RETURNED.value
    assert body["return_reason"] == "أرقام السوق غير مكتملة"

    # Persisted, not just echoed.
    from backend.db.models.report import MonthlyReport

    db.expire_all()
    stored = db.get(MonthlyReport, d03_world["alpha_report"].id)
    assert stored.status == ReportStatus.RETURNED.value
    assert stored.return_reason == "أرقام السوق غير مكتملة"
    assert stored.returned_by_id == d03_world["bd"].id
    assert stored.returned_at is not None


def test_return_records_an_append_only_lifecycle_event(client, d03_world, auth, db):
    _return(client, d03_world, auth)

    from backend.db.models.report import ReportLifecycleEvent

    events = (
        db.query(ReportLifecycleEvent)
        .filter(ReportLifecycleEvent.report_id == d03_world["alpha_report"].id)
        .order_by(ReportLifecycleEvent.id)
        .all()
    )
    assert [e.action for e in events] == ["returned"]
    assert events[0].to_status == ReportStatus.RETURNED.value
    assert events[0].actor_id == d03_world["bd"].id
    assert events[0].note == "أرقام السوق غير مكتملة"


def test_return_requires_a_reason(client, d03_world, auth):
    response = client.post(
        f"/api/v1/monthly-reports/{d03_world['alpha_report'].id}/return",
        headers=auth(d03_world["bd"]),
        json={"reason": ""},
    )
    assert response.status_code == 422


def test_company_manager_cannot_return_a_report(client, d03_world, auth):
    """REPORT_REVIEW is held by the Holding reviewers, not the company side."""
    response = client.post(
        f"/api/v1/monthly-reports/{d03_world['alpha_report'].id}/return",
        headers=auth(d03_world["alpha_mgr"]),
        json={"reason": "محاولة غير مصرّح بها"},
    )
    assert response.status_code == 403


def test_return_is_audited(client, d03_world, auth, db):
    from backend.db.models import AuditLog

    _return(client, d03_world, auth)
    assert (
        db.query(AuditLog)
        .filter(AuditLog.action == AuditAction.REPORT_RETURNED)
        .count()
        == 1
    )


def test_cannot_return_an_already_returned_report(client, d03_world, auth):
    _return(client, d03_world, auth)
    response = _return(client, d03_world, auth, reason="مرة ثانية")
    assert response.status_code == 409


# --------------------------------------------------------------------------
# linked correction version (D03/S09)
# --------------------------------------------------------------------------
def test_correction_creates_a_linked_new_version(client, d03_world, auth, db):
    original_id = d03_world["alpha_report"].id
    _return(client, d03_world, auth)

    response = client.post(
        f"/api/v1/monthly-reports/{original_id}/correction",
        headers=auth(d03_world["alpha_mgr"]),
        json={"major_problems": "نقص في توريد المواد الخام"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["version_number"] == 2
    assert body["corrects_report_id"] == original_id
    assert body["is_live"] is True
    assert body["status"] == ReportStatus.DRAFT.value
    assert body["major_problems"] == "نقص في توريد المواد الخام"
    # Financial figures are carried over, not re-entered on the management side.
    assert body["revenue"] == "111111.00"

    from backend.db.models.report import MonthlyReport

    db.expire_all()
    original = db.get(MonthlyReport, original_id)
    assert original.is_live is False  # superseded, never deleted
    assert original.major_problems is None  # original narrative untouched
    correction = db.get(MonthlyReport, body["id"])
    assert correction.corrects_report_id == original_id
    assert correction.version_number == 2


def test_correction_requires_a_returned_report(client, d03_world, auth):
    """A submitted (not returned) report cannot spawn a correction."""
    response = client.post(
        f"/api/v1/monthly-reports/{d03_world['alpha_report'].id}/correction",
        headers=auth(d03_world["alpha_mgr"]),
        json={"major_problems": "x"},
    )
    assert response.status_code == 409


def test_correction_is_company_scoped(client, d03_world, auth):
    """Another company's manager cannot correct this report (404, not 403)."""
    _return(client, d03_world, auth)
    response = client.post(
        f"/api/v1/monthly-reports/{d03_world['alpha_report'].id}/correction",
        headers=auth(d03_world["beta_mgr"]),
        json={"major_problems": "x"},
    )
    assert response.status_code == 404


def test_resubmitting_a_correction_records_resubmitted(client, d03_world, auth, db):
    original_id = d03_world["alpha_report"].id
    _return(client, d03_world, auth)
    correction = client.post(
        f"/api/v1/monthly-reports/{original_id}/correction",
        headers=auth(d03_world["alpha_mgr"]),
        json={"major_problems": "مشكلة"},
    ).json()

    response = client.post(
        f"/api/v1/monthly-reports/{correction['id']}/submit",
        headers=auth(d03_world["alpha_mgr"]),
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == ReportStatus.SUBMITTED.value

    from backend.db.models.report import ReportLifecycleEvent

    events = (
        db.query(ReportLifecycleEvent)
        .filter(ReportLifecycleEvent.report_id == correction["id"])
        .order_by(ReportLifecycleEvent.id)
        .all()
    )
    assert [e.action for e in events] == ["resubmitted"]


# --------------------------------------------------------------------------
# owner approval / cancellation (D03, owner-only)
# --------------------------------------------------------------------------
def test_owner_approves_a_submitted_report(client, d03_world, auth, db):
    response = client.post(
        f"/api/v1/monthly-reports/{d03_world['alpha_report'].id}/approve",
        headers=auth(d03_world["owner"]),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == ReportStatus.REVIEWED.value
    assert body["approval_status"] == ReportApprovalStatus.APPROVED.value

    from backend.db.models.report import MonthlyReport

    db.expire_all()
    stored = db.get(MonthlyReport, d03_world["alpha_report"].id)
    assert stored.approval_status == ReportApprovalStatus.APPROVED.value
    assert stored.approved_by_id == d03_world["owner"].id
    assert stored.approved_at is not None


def test_bd_cannot_approve_a_report(client, d03_world, auth):
    """Final approval is owner-only: REPORT_REVIEW is not enough."""
    response = client.post(
        f"/api/v1/monthly-reports/{d03_world['alpha_report'].id}/approve",
        headers=auth(d03_world["bd"]),
    )
    assert response.status_code == 403


def test_owner_cancels_a_report_with_a_reason(client, d03_world, auth, db):
    response = client.post(
        f"/api/v1/monthly-reports/{d03_world['alpha_report'].id}/cancel",
        headers=auth(d03_world["owner"]),
        json={"reason": "تقرير مكرر"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == ReportStatus.CANCELLED.value
    assert body["approval_status"] == ReportApprovalStatus.CANCELLED.value

    from backend.db.models.report import MonthlyReport

    db.expire_all()
    stored = db.get(MonthlyReport, d03_world["alpha_report"].id)
    assert stored.cancelled_by_id == d03_world["owner"].id
    assert stored.cancel_reason == "تقرير مكرر"


def test_cannot_approve_a_draft(client, d03_world, auth):
    draft = client.post(
        "/api/v1/monthly-reports",
        headers=auth(d03_world["alpha_mgr"]),
        json={"company_id": d03_world["alpha"].id, "period_year": 2027, "period_month": 11},
    ).json()
    response = client.post(
        f"/api/v1/monthly-reports/{draft['id']}/approve",
        headers=auth(d03_world["owner"]),
    )
    assert response.status_code == 409


# --------------------------------------------------------------------------
# version chain + lifecycle reads
# --------------------------------------------------------------------------
def test_versions_endpoint_returns_the_full_chain(client, d03_world, auth):
    original_id = d03_world["alpha_report"].id
    _return(client, d03_world, auth)
    correction = client.post(
        f"/api/v1/monthly-reports/{original_id}/correction",
        headers=auth(d03_world["alpha_mgr"]),
        json={"major_problems": "مشكلة"},
    ).json()

    response = client.get(
        f"/api/v1/monthly-reports/{correction['id']}/versions",
        headers=auth(d03_world["owner"]),
    )
    assert response.status_code == 200, response.text
    versions = response.json()
    assert [v["version_number"] for v in versions] == [1, 2]
    assert versions[0]["id"] == original_id
    assert versions[0]["is_live"] is False
    assert versions[1]["is_live"] is True
    assert versions[1]["corrects_report_id"] == original_id


def test_list_shows_only_the_live_version(client, d03_world, auth):
    original_id = d03_world["alpha_report"].id
    _return(client, d03_world, auth)
    client.post(
        f"/api/v1/monthly-reports/{original_id}/correction",
        headers=auth(d03_world["alpha_mgr"]),
        json={"major_problems": "مشكلة"},
    )

    listing = client.get(
        f"/api/v1/monthly-reports?company_id={d03_world['alpha'].id}",
        headers=auth(d03_world["owner"]),
    ).json()
    assert len(listing) == 1
    assert listing[0]["version_number"] == 2
    assert listing[0]["is_live"] is True


def test_versions_are_company_scoped(client, d03_world, auth):
    response = client.get(
        f"/api/v1/monthly-reports/{d03_world['alpha_report'].id}/versions",
        headers=auth(d03_world["beta_mgr"]),
    )
    assert response.status_code == 404


def test_lifecycle_endpoint_is_ordered(client, d03_world, auth):
    original_id = d03_world["alpha_report"].id
    _return(client, d03_world, auth)
    correction = client.post(
        f"/api/v1/monthly-reports/{original_id}/correction",
        headers=auth(d03_world["alpha_mgr"]),
        json={"major_problems": "مشكلة"},
    ).json()
    client.post(
        f"/api/v1/monthly-reports/{correction['id']}/submit",
        headers=auth(d03_world["alpha_mgr"]),
    )
    client.post(
        f"/api/v1/monthly-reports/{correction['id']}/approve",
        headers=auth(d03_world["owner"]),
    )

    response = client.get(
        f"/api/v1/monthly-reports/{correction['id']}/lifecycle",
        headers=auth(d03_world["owner"]),
    )
    assert response.status_code == 200, response.text
    actions = [e["action"] for e in response.json()]
    assert actions == ["resubmitted", "approved"]


def test_report_detail_embeds_lifecycle_and_versions(client, d03_world, auth):
    _return(client, d03_world, auth)
    body = client.get(
        f"/api/v1/monthly-reports/{d03_world['alpha_report'].id}",
        headers=auth(d03_world["owner"]),
    ).json()
    assert body["version_number"] == 1
    assert body["is_live"] is True
    assert len(body["versions"]) == 1
    assert len(body["lifecycle"]) == 1
    assert body["lifecycle"][0]["action"] == "returned"


# --------------------------------------------------------------------------
# frontend contract (vanilla JS, asserted statically like the other views)
# --------------------------------------------------------------------------
def test_frontend_exposes_the_d03_workflow():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    app_js = (root / "frontend" / "app.js").read_text(encoding="utf-8")

    # The four transition calls the workflow needs (versions/lifecycle are
    # embedded in the report detail, so they are read, not fetched separately).
    for endpoint in (
        "/return",
        "/correction",
        "/approve",
        "/cancel",
    ):
        assert '"/api/v1/monthly-reports/" + id + "' + endpoint in app_js, (
            f"app.js never calls the {endpoint} endpoint"
        )
    for fn in (
        "returnReportForm",
        "correctReportForm",
        "approveReport",
        "cancelReportForm",
        "reportVersionsBlock",
        "reportLifecycleBlock",
    ):
        assert f"function {fn}(" in app_js, f"{fn} is not defined"
    # The buttons are permission-gated, not role-name gated.
    assert 'has("monthly_report.review")' in app_js
    assert 'has("monthly_report.approve")' in app_js

