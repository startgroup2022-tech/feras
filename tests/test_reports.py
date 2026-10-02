"""Monthly reports: lifecycle, financial review, and the verified-data rule."""

from __future__ import annotations

import pytest

from backend.db.models.enums import ReportStatus

YEAR, MONTH = 2027, 10


# --------------------------------------------------------------------------
# lifecycle
# --------------------------------------------------------------------------
def test_manager_creates_a_draft(client, world, auth):
    response = client.post(
        "/api/v1/monthly-reports",
        headers=auth(world["alpha_mgr"]),
        json={
            "company_id": world["alpha"].id,
            "period_year": 2027,
            "period_month": 11,
            "revenue": "500000",
            "expenses": "300000",
            "net_result": "200000",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == ReportStatus.DRAFT.value
    assert body["company_id"] == world["alpha"].id


def test_cannot_create_two_reports_for_the_same_month(client, world, auth):
    response = client.post(
        "/api/v1/monthly-reports",
        headers=auth(world["alpha_mgr"]),
        json={"company_id": world["alpha"].id, "period_year": YEAR, "period_month": MONTH},
    )

    # alpha already has a report for 2027-10 in the shared fixture.
    assert response.status_code == 409


def test_manager_cannot_file_a_report_for_another_company(client, world, auth):
    response = client.post(
        "/api/v1/monthly-reports",
        headers=auth(world["alpha_mgr"]),
        json={"company_id": world["beta"].id, "period_year": 2027, "period_month": 12},
    )

    assert response.status_code == 403


def test_draft_can_be_edited_then_submitted(client, world, auth):
    created = client.post(
        "/api/v1/monthly-reports",
        headers=auth(world["alpha_mgr"]),
        json={"company_id": world["alpha"].id, "period_year": 2027, "period_month": 11},
    ).json()
    report_id = created["id"]

    updated = client.patch(
        f"/api/v1/monthly-reports/{report_id}",
        headers=auth(world["alpha_mgr"]),
        json={"revenue": "750000", "expenses": "500000", "net_result": "250000"},
    )
    assert updated.status_code == 200
    assert updated.json()["revenue"] == "750000.00"

    submitted = client.post(
        f"/api/v1/monthly-reports/{report_id}/submit", headers=auth(world["alpha_mgr"])
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == ReportStatus.SUBMITTED.value
    assert submitted.json()["submitted_at"] is not None


def test_submitted_report_cannot_be_edited(client, world, auth):
    created = client.post(
        "/api/v1/monthly-reports",
        headers=auth(world["alpha_mgr"]),
        json={
            "company_id": world["alpha"].id,
            "period_year": 2027,
            "period_month": 11,
            "revenue": "100",
            "expenses": "50",
        },
    ).json()
    client.post(f"/api/v1/monthly-reports/{created['id']}/submit", headers=auth(world["alpha_mgr"]))

    response = client.patch(
        f"/api/v1/monthly-reports/{created['id']}",
        headers=auth(world["alpha_mgr"]),
        json={"revenue": "1"},
    )

    assert response.status_code == 409


def test_submitting_without_figures_is_rejected(client, world, auth):
    """Revenue and expenses are mandatory before a report reaches the Holding."""
    created = client.post(
        "/api/v1/monthly-reports",
        headers=auth(world["alpha_mgr"]),
        json={"company_id": world["alpha"].id, "period_year": 2027, "period_month": 11},
    ).json()

    response = client.post(
        f"/api/v1/monthly-reports/{created['id']}/submit", headers=auth(world["alpha_mgr"])
    )

    assert response.status_code == 422


def test_a_report_can_be_submitted_only_once(client, world, auth):
    created = client.post(
        "/api/v1/monthly-reports",
        headers=auth(world["alpha_mgr"]),
        json={
            "company_id": world["alpha"].id,
            "period_year": 2027,
            "period_month": 11,
            "revenue": "100",
            "expenses": "50",
        },
    ).json()
    headers = auth(world["alpha_mgr"])
    client.post(f"/api/v1/monthly-reports/{created['id']}/submit", headers=headers)

    again = client.post(f"/api/v1/monthly-reports/{created['id']}/submit", headers=headers)

    assert again.status_code == 409


# --------------------------------------------------------------------------
# financial review
# --------------------------------------------------------------------------
def test_accountant_approves_and_verified_figures_replace_submitted(client, world, auth):
    report = world["alpha_report"]

    response = client.post(
        f"/api/v1/monthly-reports/{report.id}/financial-review",
        headers=auth(world["accountant"]),
        json={
            "is_financially_accurate": True,
            "financial_notes": "تم التحقق",
            "verified_revenue": "222222",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    # Corrected revenue, but expenses fall back to the submitted value.
    assert body["verified_revenue"] == "222222.00"
    assert body["verified_expenses"] == "1.00"


def test_approved_review_updates_the_holding_dashboard(client, world, auth):
    before = client.get(
        "/api/v1/dashboard/holding?year=2027&month=10", headers=auth(world["accountant"])
    ).json()
    assert before["kpis"]["total_revenue"] == "1111110.00"

    client.post(
        f"/api/v1/monthly-reports/{world['alpha_report'].id}/financial-review",
        headers=auth(world["accountant"]),
        json={"is_financially_accurate": True, "verified_revenue": "500000"},
    )

    after = client.get(
        "/api/v1/dashboard/holding?year=2027&month=10", headers=auth(world["accountant"])
    ).json()
    # 500000 (verified alpha) + 999999 (beta submitted)
    assert after["kpis"]["total_revenue"] == "1499999.00"


def test_flagged_review_keeps_submitted_figures_in_the_dashboard(client, world, auth):
    """A rejected verification must not feed the dashboard."""
    client.post(
        f"/api/v1/monthly-reports/{world['alpha_report'].id}/financial-review",
        headers=auth(world["accountant"]),
        json={
            "is_financially_accurate": False,
            "flagged_reason": "أرقام غير مكتملة",
            "verified_revenue": "1",
        },
    )

    dashboard = client.get(
        "/api/v1/dashboard/holding?year=2027&month=10", headers=auth(world["accountant"])
    ).json()

    assert dashboard["kpis"]["total_revenue"] == "1111110.00"
    assert dashboard["kpis"]["pending_financial_reviews"] == 1


def test_flagging_without_a_reason_is_rejected(client, world, auth):
    response = client.post(
        f"/api/v1/monthly-reports/{world['alpha_report'].id}/financial-review",
        headers=auth(world["accountant"]),
        json={"is_financially_accurate": False},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_flagged_review_sets_report_under_review(client, world, auth, db):
    client.post(
        f"/api/v1/monthly-reports/{world['alpha_report'].id}/financial-review",
        headers=auth(world["accountant"]),
        json={"is_financially_accurate": False, "flagged_reason": "تحتاج توضيح"},
    )

    report = client.get(
        f"/api/v1/monthly-reports/{world['alpha_report'].id}", headers=auth(world["accountant"])
    ).json()
    assert report["status"] == ReportStatus.UNDER_REVIEW.value


def test_draft_cannot_be_financially_reviewed(client, world, auth):
    draft = client.post(
        "/api/v1/monthly-reports",
        headers=auth(world["alpha_mgr"]),
        json={"company_id": world["alpha"].id, "period_year": 2027, "period_month": 11},
    ).json()

    response = client.post(
        f"/api/v1/monthly-reports/{draft['id']}/financial-review",
        headers=auth(world["accountant"]),
        json={"is_financially_accurate": True},
    )

    assert response.status_code == 409


def test_review_is_audited(client, world, auth, db):
    from backend.db.models import AuditLog
    from backend.db.models.audit_actions import AuditAction

    client.post(
        f"/api/v1/monthly-reports/{world['alpha_report'].id}/financial-review",
        headers=auth(world["accountant"]),
        json={"is_financially_accurate": True},
    )

    assert (
        db.query(AuditLog)
        .filter(AuditLog.action == AuditAction.REPORT_FINANCIAL_REVIEWED)
        .count()
        == 1
    )


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------
@pytest.mark.parametrize("month", [0, 13])
def test_invalid_month_is_rejected(client, world, auth, month):
    response = client.post(
        "/api/v1/monthly-reports",
        headers=auth(world["alpha_mgr"]),
        json={"company_id": world["alpha"].id, "period_year": 2027, "period_month": month},
    )

    assert response.status_code == 422


def test_negative_revenue_is_rejected(client, world, auth):
    response = client.post(
        "/api/v1/monthly-reports",
        headers=auth(world["alpha_mgr"]),
        json={
            "company_id": world["alpha"].id,
            "period_year": 2027,
            "period_month": 11,
            "revenue": "-5",
        },
    )

    assert response.status_code == 422
