"""Company isolation -- the core security property of the platform.

A subsidiary must never be able to read another subsidiary's data, by any
route: list endpoints, direct id access (IDOR), query parameters that try to
widen scope, dashboards, or the AI context builder.
"""

from __future__ import annotations

import pytest

from backend.services import ai_service


# --------------------------------------------------------------------------
# company listing
# --------------------------------------------------------------------------
def test_manager_sees_only_its_own_company(client, world, auth):
    response = client.get("/api/v1/companies", headers=auth(world["alpha_mgr"]))

    assert response.status_code == 200
    assert [c["code"] for c in response.json()] == ["ALPHA"]


def test_owner_sees_every_company(client, world, auth):
    response = client.get("/api/v1/companies", headers=auth(world["owner"]))

    assert {c["code"] for c in response.json()} == {"ALPHA", "BETA"}


# --------------------------------------------------------------------------
# IDOR -- direct object access
# --------------------------------------------------------------------------
def test_manager_cannot_read_another_company_by_id(client, world, auth):
    response = client.get(f"/api/v1/companies/{world['beta'].id}", headers=auth(world["alpha_mgr"]))

    # 404 rather than 403: out-of-scope and non-existent are indistinguishable,
    # so an attacker cannot enumerate which ids exist.
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_manager_cannot_read_another_company_dashboard(client, world, auth):
    response = client.get(
        f"/api/v1/dashboard/company/{world['beta'].id}?year=2027&month=10",
        headers=auth(world["alpha_mgr"]),
    )

    assert response.status_code == 404


def test_manager_cannot_read_another_company_report(client, world, auth):
    response = client.get(
        f"/api/v1/monthly-reports/{world['beta_report'].id}", headers=auth(world["alpha_mgr"])
    )

    assert response.status_code == 404


def test_manager_cannot_read_another_company_support_request(client, world, auth):
    response = client.get(
        f"/api/v1/support-requests/{world['beta_req'].id}", headers=auth(world["alpha_mgr"])
    )

    assert response.status_code == 404


# --------------------------------------------------------------------------
# query parameters must never widen scope
# --------------------------------------------------------------------------
def test_company_id_query_param_cannot_widen_report_scope(client, world, auth):
    response = client.get(
        f"/api/v1/monthly-reports?company_id={world['beta'].id}",
        headers=auth(world["alpha_mgr"]),
    )

    assert response.status_code == 200
    assert response.json() == []


def test_company_id_query_param_cannot_widen_support_scope(client, world, auth):
    response = client.get(
        f"/api/v1/support-requests?company_id={world['beta'].id}",
        headers=auth(world["alpha_mgr"]),
    )

    assert response.status_code == 200
    assert response.json() == []


def test_report_list_is_scoped_to_own_company(client, world, auth):
    response = client.get("/api/v1/monthly-reports", headers=auth(world["alpha_mgr"]))

    assert response.status_code == 200
    assert [r["company_id"] for r in response.json()] == [world["alpha"].id]


# --------------------------------------------------------------------------
# holding dashboard is not available to company users
# --------------------------------------------------------------------------
def test_company_manager_cannot_open_holding_dashboard(client, world, auth):
    response = client.get(
        "/api/v1/dashboard/holding?year=2027&month=10", headers=auth(world["alpha_mgr"])
    )

    assert response.status_code == 403


def test_company_dashboard_totals_cover_only_that_company(client, world, auth):
    response = client.get(
        f"/api/v1/dashboard/company/{world['alpha'].id}?year=2027&month=10",
        headers=auth(world["alpha_mgr"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["kpis"]["companies_count"] == 1
    # Must reflect ALPHA's 111111, never the group total.
    assert body["kpis"]["total_revenue"] == "111111.00"


# --------------------------------------------------------------------------
# a user with no company grants sees nothing
# --------------------------------------------------------------------------
def test_manager_without_grants_sees_nothing(client, make_user, make_company, auth):
    make_company("GHOST", "شركة")
    orphan = make_user("orphan@corp.sa", "company_manager")

    assert client.get("/api/v1/companies", headers=auth(orphan)).json() == []
    assert client.get("/api/v1/monthly-reports", headers=auth(orphan)).json() == []


def test_write_access_requires_write_grant(client, world, db, make_user, auth):
    """A read-only grant must not permit submitting a report."""
    from backend.db.models.identity import UserCompanyAccess

    reader = make_user("reader@corp.sa", "company_manager", [world["alpha"]], can_write=False)
    response = client.post(
        "/api/v1/monthly-reports",
        headers=auth(reader),
        json={
            "company_id": world["alpha"].id,
            "period_year": 2027,
            "period_month": 11,
            "revenue": "1",
        },
    )

    assert response.status_code == 403


# --------------------------------------------------------------------------
# AI isolation -- context must be built from the caller's scope only
# --------------------------------------------------------------------------
def test_ai_company_context_excludes_other_companies(db, world):
    context = ai_service.build_company_context(
        db, world["alpha_mgr"], world["alpha"].id, 2027, 10
    )

    assert context["grounded_on_company_ids"] == [world["alpha"].id]
    assert [c["id"] for c in context["companies"]] == [world["alpha"].id]
    # The other company's figures must not appear anywhere in the payload.
    assert world["beta"].id not in context["grounded_on_company_ids"]
    assert "999999" not in str(context)


def test_ai_refuses_another_company_for_manager(db, world):
    from backend.core.errors import PermissionDeniedError

    with pytest.raises(PermissionDeniedError):
        ai_service.build_company_context(db, world["alpha_mgr"], world["beta"].id, 2027, 10)


def test_ai_company_endpoint_denies_cross_company_question(client, world, auth):
    response = client.post(
        "/api/v1/ai/company",
        headers=auth(world["alpha_mgr"]),
        json={"question": "ما هي نتائج الشركة الأخرى؟", "company_id": world["beta"].id},
    )

    assert response.status_code == 403


def test_ai_holding_answer_contains_only_real_scope(client, world, auth):
    response = client.post(
        "/api/v1/ai/holding?year=2027&month=10",
        headers=auth(world["owner"]),
        json={"question": "ملخص أداء المجموعة هذا الشهر"},
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body["grounded_on_company_ids"]) == {world["alpha"].id, world["beta"].id}
    # The group total is alpha + beta, which proves both were included.
    assert "1,111,110" in body["answer"]


def test_ai_company_answer_hides_the_group_total(client, world, auth):
    """A company-scoped answer must reflect only that company's figures."""
    response = client.post(
        "/api/v1/ai/company?year=2027&month=10",
        headers=auth(world["alpha_mgr"]),
        json={"question": "ملخص أدائنا", "company_id": world["alpha"].id},
    )

    assert response.status_code == 200
    answer = response.json()["answer"]
    assert "111,110" in answer  # alpha's net result
    assert "999,998" not in answer  # beta's net result must not appear


def test_ai_conversation_cannot_be_reused_across_companies(client, world, auth, db):
    """A conversation id from one scope must not be usable in another."""
    first = client.post(
        "/api/v1/ai/company",
        headers=auth(world["alpha_mgr"]),
        json={"question": "ملخص أدائنا", "company_id": world["alpha"].id},
    )
    assert first.status_code == 200
    conversation_id = first.json()["conversation_id"]

    # Same user, but now targeting a company they cannot access.
    response = client.post(
        "/api/v1/ai/company",
        headers=auth(world["alpha_mgr"]),
        json={
            "question": "وماذا عن الأخرى؟",
            "company_id": world["beta"].id,
            "conversation_id": conversation_id,
        },
    )

    assert response.status_code == 403
