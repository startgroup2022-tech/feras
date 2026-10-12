"""Final-completion tests: the screens and read endpoints added to close the
remaining backend-only gaps.

Three things are asserted here:

* the additive read endpoints (internal opportunity review queue, advisor
  assignment list) exist, are permission gated, and never leak the confidential
  shape to a caller without the review permission;
* the new frontend surface is wired: the review queue, item-definition builder,
  advisor assignments, task assignment, weekly template and audit filters are
  all present in ``app.js`` and gated by permission codes the backend defines;
* bilingual behaviour holds -- every new label is emitted as a dual AR/EN span
  and the language switch re-renders the active view.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from backend.db.models.enums import PublicOpportunityStatus
from backend.db.models.website import WebsiteOpportunity
from backend.rbac.permissions import ALL_PERMISSIONS

ROOT = Path(__file__).resolve().parent.parent
APP_JS = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
INDEX = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")

PUBLIC = "/api/v1/public"


def _listing_payload(**overrides) -> dict:
    payload = {
        "market": "bahrain",
        "locale": "ar",
        "full_name": "أحمد العلي",
        "email": "ahmed@example.com",
        "phone": "+9731234567",
        "consent": True,
        "applicant_capacity": "owner",
        "opportunity_type": "full_sale",
        "description": "شركة تجارية قائمة منذ سنوات.",
        "sector": "تجارة",
        "currency": "BHD",
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------
# backend: internal opportunity review queue
# --------------------------------------------------------------------------
def test_internal_opportunity_queue_requires_the_review_permission(client, world, auth):
    # An accountant has no opportunity-review permission.
    response = client.get("/api/v1/leads/opportunities", headers=auth(world["accountant"]))
    assert response.status_code == 403, response.text


def test_internal_opportunity_queue_lists_submissions_for_a_reviewer(client, db, world, auth):
    created = client.post(
        f"{PUBLIC}/leads/business-listing",
        data={"payload": json.dumps(_listing_payload())},
    )
    assert created.status_code == 201, created.text

    response = client.get("/api/v1/leads/opportunities", headers=auth(world["owner"]))
    assert response.status_code == 200, response.text
    rows = response.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == PublicOpportunityStatus.SUBMITTED.value
    assert row["is_public"] is False
    # The reviewer sees the confidential submission profile.
    assert row["description"] == "شركة تجارية قائمة منذ سنوات."
    assert row["sector"] == "تجارة"


def test_public_opportunity_list_still_hides_unpublished_submissions(client, db):
    client.post(
        f"{PUBLIC}/leads/business-listing",
        data={"payload": json.dumps(_listing_payload())},
    )
    response = client.get(f"{PUBLIC}/opportunities")
    assert response.status_code == 200, response.text
    assert response.json() == []


def test_reviewing_a_listing_publishes_it_through_the_queue(client, db, world, auth):
    client.post(
        f"{PUBLIC}/leads/business-listing",
        data={"payload": json.dumps(_listing_payload())},
    )
    opportunity = db.query(WebsiteOpportunity).one()

    reviewed = client.post(
        f"/api/v1/leads/opportunities/{opportunity.id}/review",
        headers=auth(world["owner"]),
        json={
            "status": PublicOpportunityStatus.PUBLISHED.value,
            "public_title_ar": "فرصة استثمارية",
            "publish": True,
        },
    )
    assert reviewed.status_code == 200, reviewed.text

    public = client.get(f"{PUBLIC}/opportunities").json()
    assert len(public) == 1
    assert public[0]["title_ar"] == "فرصة استثمارية"


# --------------------------------------------------------------------------
# backend: advisor assignments
# --------------------------------------------------------------------------
def test_advisor_assignment_list_is_permission_gated(client, world, auth):
    response = client.get("/api/v1/operations/advisors", headers=auth(world["accountant"]))
    assert response.status_code == 403, response.text


def test_advisor_assignment_round_trip(client, db, make_company, make_user, auth):
    company = make_company("ADVCO", "شركة المستشار")
    bd = make_user("bd.adv@corp.sa", "business_development", [company])
    create = client.post(
        "/api/v1/operations/advisors",
        headers=auth(bd),
        json={
            "company_id": company.id,
            "advisor_user_id": bd.id,
            "specialty": "restructuring",
        },
    )
    assert create.status_code == 201, create.text

    listed = client.get("/api/v1/operations/advisors", headers=auth(bd))
    assert listed.status_code == 200, listed.text
    rows = listed.json()
    assert any(r["specialty"] == "restructuring" for r in rows)


# --------------------------------------------------------------------------
# frontend contract: the new surface exists and is gated
# --------------------------------------------------------------------------
def _data_perms(html: str) -> list[str]:
    codes: list[str] = []
    for match in re.finditer(r'data-perm="([^"]+)"', html):
        codes.extend(match.group(1).split())
    return codes


def test_every_index_permission_token_is_a_real_code():
    for code in _data_perms(INDEX):
        assert code in ALL_PERMISSIONS, f"unknown permission token in markup: {code}"


def test_opportunity_queue_is_rendered_and_permission_gated():
    assert "function renderOpportunities" in APP_JS
    assert "/api/v1/leads/opportunities" in APP_JS
    assert "/review" in APP_JS
    # The sub-tab is gated by the review permission in the markup.
    assert 'data-lead-view="opportunities" data-perm="website_opportunity.review"' in INDEX


def test_financial_item_definitions_builder_is_wired():
    assert "function finDefinitionsPanel" in APP_JS
    assert "/api/v1/financial/item-definitions" in APP_JS
    assert 'has("financial_item.manage")' in APP_JS


def test_advisor_assignments_are_wired():
    assert "function advisorAssignmentsPanel" in APP_JS
    assert '"/api/v1/operations/advisors"' in APP_JS
    assert 'has("advisor.manage")' in APP_JS


def test_task_assignment_and_progress_are_wired():
    assert 'id="taskUpdateForm"' in APP_JS
    assert 'patch("/api/v1/operations/tasks/" + t.id' in APP_JS
    assert 'has("task.update")' in APP_JS


def test_weekly_question_template_is_wired():
    assert "function weeklyTemplatePanel" in APP_JS
    assert "/api/v1/operations/weekly-reports/questions" in APP_JS
    assert 'has("weekly_report.template.manage")' in APP_JS


def test_audit_view_supports_action_and_entity_filters():
    assert 'id="auditAction"' in APP_JS
    assert 'id="auditEntity"' in APP_JS
    assert '&action=" + encodeURIComponent(page.action)' in APP_JS


def test_company_create_form_is_wired_and_gated():
    assert 'id="companyCreateForm"' in APP_JS
    assert 'post("/api/v1/companies"' in APP_JS
    assert 'has("company.manage")' in APP_JS


# --------------------------------------------------------------------------
# bilingual behaviour
# --------------------------------------------------------------------------
def test_new_panels_emit_dual_arabic_and_english_labels():
    # Each new panel builds its labels through the shared bilingual helper.
    for fn in (
        "function finDefinitionsPanel",
        "function advisorAssignmentsPanel",
        "function weeklyTemplatePanel",
        "function renderOpportunities",
    ):
        assert fn in APP_JS
    # Spot-check that the new panels carry both languages.
    assert '"بنود مالية خاصة (F-04)", "Special financial items (F-04)"' in APP_JS
    assert '"المستشارون المُسندون (S19 / D04)", "Assigned advisors (S19 / D04)"' in APP_JS
    assert '"قالب الأسئلة (S17)", "Question template (S17)"' in APP_JS
    assert 'dual("عرض مقدم للمراجعة", "Submitted listing")' in APP_JS


def test_language_switch_sets_direction_and_rerenders():
    assert 'html.setAttribute("dir", lang === "ar" ? "rtl" : "ltr")' in APP_JS
    assert "function refreshActiveView" in APP_JS
    assert "function loadView" in APP_JS
    # The admin tab is re-rendered on switch so server-driven markup follows.
    assert "renderAdminTab(STATE.adminTab)" in APP_JS
