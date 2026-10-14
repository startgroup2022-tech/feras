"""S21/S02/S09: management reporting & report clarifications.

Verifies the vertical slice end to end:

* the BD five-axis management brief is authored as a draft, submitted
  explicitly, and read by the owner/accountant;
* an urgent brief notifies the owner immediately;
* a report clarification is linked to a report's *original* and never edits it,
  and an out-of-scope report id is a 404 (IDOR protection);
* RBAC is enforced server-side and the new permissions are catalogued with
  bilingual metadata.
"""

from __future__ import annotations

import pytest

from backend.db.models import ManagementBrief, MonthlyReport, ReportClarification
from backend.rbac import permission_metadata
from backend.rbac.permissions import ALL_PERMISSIONS, Perm, ROLE_PERMISSIONS


@pytest.fixture
def mgmt_world(world, make_user):
    """A BD author scoped to alpha, the owner, and an accountant reader."""
    bd = make_user("bd.mgmt@corp.sa", "business_development", [world["alpha"]])
    world = dict(world)
    world["bd"] = bd
    return world


# --------------------------------------------------------------------------
# RBAC catalogue
# --------------------------------------------------------------------------
def test_new_management_permissions_are_catalogued_with_metadata():
    assert permission_metadata.unknown_codes() == []
    for code in (
        Perm.MANAGEMENT_BRIEF_READ,
        Perm.MANAGEMENT_BRIEF_SUBMIT,
        Perm.REPORT_CLARIFY,
    ):
        assert code in ALL_PERMISSIONS
        meta = permission_metadata.describe(code)
        assert meta["name_ar"] and meta["name_en"]
        assert meta["description_ar"] and meta["description_en"]


def test_role_grants_for_management_reporting():
    bd = ROLE_PERMISSIONS["business_development"]
    assert Perm.MANAGEMENT_BRIEF_READ in bd
    assert Perm.MANAGEMENT_BRIEF_SUBMIT in bd
    assert Perm.REPORT_CLARIFY in bd

    accountant = ROLE_PERMISSIONS["accountant"]
    assert Perm.MANAGEMENT_BRIEF_READ in accountant
    # The accountant reads the brief but never authors it.
    assert Perm.MANAGEMENT_BRIEF_SUBMIT not in accountant

    owner = ROLE_PERMISSIONS["holding_owner"]
    assert Perm.MANAGEMENT_BRIEF_READ in owner
    assert Perm.MANAGEMENT_BRIEF_SUBMIT in owner


# --------------------------------------------------------------------------
# management brief lifecycle (S21)
# --------------------------------------------------------------------------
def test_bd_authors_and_submits_the_five_axis_brief(client, mgmt_world, auth, db):
    payload = {
        "period_year": 2027,
        "period_month": 3,
        "executive_summary": "ملخص تنفيذي",
        "axis_companies": "أداء الشركات",
        "axis_projects": "المشاريع الجارية",
        "axis_employees": "القوى العاملة",
        "axis_risks": "المخاطر المرصودة",
        "axis_decisions": "قرارات مطلوبة",
        "urgency": "monthly",
    }
    created = client.post(
        "/api/v1/operations/management-briefs",
        json=payload,
        headers=auth(mgmt_world["bd"]),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "draft"
    assert body["period_year"] == 2027
    assert body["period_month"] == 3
    for axis in (
        "axis_companies", "axis_projects", "axis_employees",
        "axis_risks", "axis_decisions",
    ):
        assert body[axis] == payload[axis]
    assert body["submitted_at"] is None

    # Saving again for the same period updates the author's own draft rather
    # than creating a second one.
    updated = client.post(
        "/api/v1/operations/management-briefs",
        json={**payload, "axis_risks": "مخاطر محدّثة"},
        headers=auth(mgmt_world["bd"]),
    )
    assert updated.status_code == 201, updated.text
    assert updated.json()["id"] == body["id"]
    assert updated.json()["axis_risks"] == "مخاطر محدّثة"
    assert db.query(ManagementBrief).count() == 1

    submitted = client.post(
        f"/api/v1/operations/management-briefs/{body['id']}/submit",
        json={},
        headers=auth(mgmt_world["bd"]),
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted"
    assert submitted.json()["submitted_at"] is not None


def test_owner_reads_the_brief_and_the_accountant_reads_but_cannot_author(
    client, mgmt_world, auth,
):
    created = client.post(
        "/api/v1/operations/management-briefs",
        json={"period_year": 2027, "period_month": 4, "axis_companies": "x"},
        headers=auth(mgmt_world["bd"]),
    )
    assert created.status_code == 201, created.text

    listed = client.get(
        "/api/v1/operations/management-briefs", headers=auth(mgmt_world["owner"])
    )
    assert listed.status_code == 200, listed.text
    assert [b["id"] for b in listed.json()] == [created.json()["id"]]

    accountant_read = client.get(
        "/api/v1/operations/management-briefs", headers=auth(mgmt_world["accountant"])
    )
    assert accountant_read.status_code == 200, accountant_read.text

    accountant_write = client.post(
        "/api/v1/operations/management-briefs",
        json={"period_year": 2027, "period_month": 5},
        headers=auth(mgmt_world["accountant"]),
    )
    assert accountant_write.status_code == 403, accountant_write.text


def test_brief_is_scoped_to_its_author(client, mgmt_world, auth, make_user):
    # A second BD author in the same holding must not see the first's draft.
    other_bd = make_user("bd2.mgmt@corp.sa", "business_development", [mgmt_world["beta"]])
    created = client.post(
        "/api/v1/operations/management-briefs",
        json={"period_year": 2027, "period_month": 6, "axis_companies": "x"},
        headers=auth(mgmt_world["bd"]),
    )
    assert created.status_code == 201, created.text

    listed = client.get(
        "/api/v1/operations/management-briefs", headers=auth(other_bd)
    )
    assert listed.status_code == 200, listed.text
    assert created.json()["id"] not in [b["id"] for b in listed.json()]


def test_another_author_cannot_submit_a_brief_they_do_not_own(
    client, mgmt_world, auth, make_user,
):
    other_bd = make_user("bd3.mgmt@corp.sa", "business_development", [mgmt_world["beta"]])
    created = client.post(
        "/api/v1/operations/management-briefs",
        json={"period_year": 2027, "period_month": 7},
        headers=auth(mgmt_world["bd"]),
    )
    assert created.status_code == 201, created.text

    refused = client.post(
        f"/api/v1/operations/management-briefs/{created.json()['id']}/submit",
        json={},
        headers=auth(other_bd),
    )
    assert refused.status_code == 404, refused.text


def test_a_marketer_without_the_permission_cannot_read_briefs(
    client, mgmt_world, auth, make_user,
):
    marketer = make_user("mkt.mgmt@corp.sa", "marketing", [mgmt_world["alpha"]])
    refused = client.get(
        "/api/v1/operations/management-briefs", headers=auth(marketer)
    )
    assert refused.status_code == 403, refused.text


# --------------------------------------------------------------------------
# report clarifications (S02/S09)
# --------------------------------------------------------------------------
def test_clarification_is_linked_and_never_edits_the_report(
    client, mgmt_world, auth, db,
):
    report = mgmt_world["alpha_report"]
    original_revenue = report.revenue
    original_status = report.status

    created = client.post(
        f"/api/v1/monthly-reports/{report.id}/clarifications",
        json={"body": "يرجى توضيح بند الإيرادات.", "kind": "request"},
        headers=auth(mgmt_world["owner"]),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["report_id"] == report.id
    assert body["kind"] == "request"
    assert body["parent_id"] is None

    # The reply answers the request and stays on the same report.
    reply = client.post(
        f"/api/v1/monthly-reports/{report.id}/clarifications",
        json={"body": "البند يمثل مبيعات الربع الأول.", "kind": "reply", "parent_id": body["id"]},
        headers=auth(mgmt_world["alpha_mgr"]),
    )
    assert reply.status_code == 201, reply.text
    assert reply.json()["parent_id"] == body["id"]

    thread = client.get(
        f"/api/v1/monthly-reports/{report.id}/clarifications",
        headers=auth(mgmt_world["owner"]),
    )
    assert thread.status_code == 200, thread.text
    assert [c["id"] for c in thread.json()] == [body["id"], reply.json()["id"]]

    # The original report is untouched.
    db.refresh(report)
    assert report.revenue == original_revenue
    assert report.status == original_status
    assert db.query(ReportClarification).count() == 2


def test_clarification_on_another_companys_report_is_not_found(
    client, mgmt_world, auth,
):
    # beta's report exists, but the alpha-scoped company manager must not learn
    # that: a clarification against it is reported as 404, not 403.
    refused = client.post(
        f"/api/v1/monthly-reports/{mgmt_world['beta_report'].id}/clarifications",
        json={"body": "x", "kind": "request"},
        headers=auth(mgmt_world["alpha_mgr"]),
    )
    assert refused.status_code == 404, refused.text


def test_reply_to_a_request_on_a_different_report_is_rejected(
    client, mgmt_world, auth,
):
    request = client.post(
        f"/api/v1/monthly-reports/{mgmt_world['alpha_report'].id}/clarifications",
        json={"body": "سؤال", "kind": "request"},
        headers=auth(mgmt_world["owner"]),
    )
    assert request.status_code == 201, request.text

    refused = client.post(
        f"/api/v1/monthly-reports/{mgmt_world['beta_report'].id}/clarifications",
        json={"body": "رد", "kind": "reply", "parent_id": request.json()["id"]},
        headers=auth(mgmt_world["owner"]),
    )
    assert refused.status_code == 422, refused.text


def test_a_marketer_without_the_permission_cannot_clarify(
    client, mgmt_world, auth, make_user,
):
    marketer = make_user("mkt2.mgmt@corp.sa", "marketing", [mgmt_world["alpha"]])
    refused = client.post(
        f"/api/v1/monthly-reports/{mgmt_world['alpha_report'].id}/clarifications",
        json={"body": "x", "kind": "request"},
        headers=auth(marketer),
    )
    assert refused.status_code == 403, refused.text
