"""S24 organisational positions and S01 motivational sentence library.

Both are additive admin catalogues built on the existing RBAC and company-scope
machinery: reads need ``position.read`` / ``motivation.read`` (granted through
the shared read sets), writes need ``position.manage`` / ``motivation.manage``
(holding owner and HR manager only). The dashboard surfaces one sentence from
the library, chosen deterministically for the caller's role.
"""

from __future__ import annotations

from backend.db.models.operations import MotivationText


def _position_payload(company_id: int, code="CTO", **over):
    data = {
        "company_id": company_id,
        "code": code,
        "title_ar": "المدير التنفيذي للتقنية",
        "title_en": "Chief Technology Officer",
    }
    data.update(over)
    return data


# --------------------------------------------------------------------------
# S24 positions
# --------------------------------------------------------------------------
def test_owner_creates_and_lists_a_position(client, world, auth, make_user):
    owner = make_user("owner_pos@corp.sa", "holding_owner", [world["alpha"]])
    created = client.post(
        "/api/v1/admin/positions",
        json=_position_payload(world["alpha"].id),
        headers=auth(owner),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["code"] == "CTO"
    assert body["title_en"] == "Chief Technology Officer"
    assert body["company_name_en"] == world["alpha"].name_en

    listed = client.get("/api/v1/admin/positions", headers=auth(owner))
    assert listed.status_code == 200, listed.text
    assert [p["code"] for p in listed.json()] == ["CTO"]


def test_duplicate_position_code_is_rejected_per_company(client, world, auth, make_user):
    owner = make_user("owner_pos2@corp.sa", "holding_owner", [world["alpha"], world["beta"]])
    assert client.post(
        "/api/v1/admin/positions",
        json=_position_payload(world["alpha"].id),
        headers=auth(owner),
    ).status_code == 201
    dup = client.post(
        "/api/v1/admin/positions",
        json=_position_payload(world["alpha"].id, title_ar="أخرى"),
        headers=auth(owner),
    )
    assert dup.status_code == 409, dup.text
    # The same code in a different company is fine -- codes are company-scoped.
    other = client.post(
        "/api/v1/admin/positions",
        json=_position_payload(world["beta"].id),
        headers=auth(owner),
    )
    assert other.status_code == 201, other.text


def test_company_manager_cannot_manage_positions(client, world, auth):
    # Company Manager has position.read via the shared company read set, but
    # not position.manage: the org chart is company administration.
    denied = client.post(
        "/api/v1/admin/positions",
        json=_position_payload(world["alpha"].id),
        headers=auth(world["alpha_mgr"]),
    )
    assert denied.status_code == 403, denied.text

    allowed = client.get("/api/v1/admin/positions", headers=auth(world["alpha_mgr"]))
    assert allowed.status_code == 200, allowed.text


def test_position_company_scope_hides_other_companies(client, world, auth, make_user):
    owner = make_user("owner_pos3@corp.sa", "holding_owner", [world["alpha"], world["beta"]])
    client.post(
        "/api/v1/admin/positions",
        json=_position_payload(world["alpha"].id, code="A1"),
        headers=auth(owner),
    )
    client.post(
        "/api/v1/admin/positions",
        json=_position_payload(world["beta"].id, code="B1"),
        headers=auth(owner),
    )
    only_alpha = client.get(
        f"/api/v1/admin/positions?company_id={world['alpha'].id}", headers=auth(owner)
    )
    assert only_alpha.status_code == 200
    assert [p["code"] for p in only_alpha.json()] == ["A1"]

    # A manager scoped to beta never sees alpha's position.
    beta_only = client.get("/api/v1/admin/positions", headers=auth(world["beta_mgr"]))
    assert [p["code"] for p in beta_only.json()] == ["B1"]


def test_reporting_line_and_department_must_stay_in_company(client, world, auth, make_user):
    owner = make_user("owner_pos4@corp.sa", "holding_owner", [world["alpha"], world["beta"]])
    alpha_root = client.post(
        "/api/v1/admin/positions",
        json=_position_payload(world["alpha"].id, code="ROOT"),
        headers=auth(owner),
    ).json()
    beta_root = client.post(
        "/api/v1/admin/positions",
        json=_position_payload(world["beta"].id, code="ROOT"),
        headers=auth(owner),
    ).json()

    cross = client.post(
        "/api/v1/admin/positions",
        json=_position_payload(
            world["alpha"].id, code="CHILD", reports_to_position_id=beta_root["id"]
        ),
        headers=auth(owner),
    )
    assert cross.status_code == 422, cross.text

    same = client.post(
        "/api/v1/admin/positions",
        json=_position_payload(
            world["alpha"].id, code="CHILD", reports_to_position_id=alpha_root["id"]
        ),
        headers=auth(owner),
    )
    assert same.status_code == 201, same.text
    assert same.json()["reports_to_title_en"] == alpha_root["title_en"]


def test_position_cannot_report_to_itself(client, world, auth, make_user):
    owner = make_user("owner_pos5@corp.sa", "holding_owner", [world["alpha"]])
    pid = client.post(
        "/api/v1/admin/positions",
        json=_position_payload(world["alpha"].id),
        headers=auth(owner),
    ).json()["id"]
    bad = client.patch(
        f"/api/v1/admin/positions/{pid}",
        json={"reports_to_position_id": pid},
        headers=auth(owner),
    )
    assert bad.status_code == 422, bad.text


def test_company_manager_never_reports_to_business_development(client, world, auth, make_user):
    """AC-24: BD coordinates; it does not command a subsidiary manager."""
    owner = make_user("owner_pos6@corp.sa", "holding_owner", [world["alpha"]])
    bd = make_user("bd_pos@corp.sa", "business_development", [world["alpha"]])
    mgr = make_user("mgr_pos@corp.sa", "company_manager", [world["alpha"]])

    bd_position = client.post(
        "/api/v1/admin/positions",
        json=_position_payload(world["alpha"].id, code="BD-LEAD", holder_user_id=bd.id),
        headers=auth(owner),
    ).json()

    bad = client.post(
        "/api/v1/admin/positions",
        json=_position_payload(
            world["alpha"].id,
            code="MGR",
            holder_user_id=mgr.id,
            reports_to_position_id=bd_position["id"],
        ),
        headers=auth(owner),
    )
    assert bad.status_code == 422, bad.text

    # The owner is a valid parent: both roles report to the owner.
    owner_position = client.post(
        "/api/v1/admin/positions",
        json=_position_payload(world["alpha"].id, code="OWNER-SEAT", holder_user_id=owner.id),
        headers=auth(owner),
    ).json()
    good = client.post(
        "/api/v1/admin/positions",
        json=_position_payload(
            world["alpha"].id,
            code="MGR2",
            holder_user_id=mgr.id,
            reports_to_position_id=owner_position["id"],
        ),
        headers=auth(owner),
    )
    assert good.status_code == 201, good.text


# --------------------------------------------------------------------------
# S01 motivational sentence library
# --------------------------------------------------------------------------
def _motivation_payload(**over):
    data = {"text_ar": "نحو أداء متميز", "text_en": "Towards excellence"}
    data.update(over)
    return data


def test_owner_manages_motivation_library(client, world, auth, make_user):
    owner = make_user("owner_mot@corp.sa", "holding_owner", [world["alpha"]])
    created = client.post(
        "/api/v1/admin/motivation-texts", json=_motivation_payload(), headers=auth(owner)
    )
    assert created.status_code == 201, created.text
    assert created.json()["is_active"] is True

    updated = client.patch(
        f"/api/v1/admin/motivation-texts/{created.json()['id']}",
        json={"is_active": False},
        headers=auth(owner),
    )
    assert updated.status_code == 200
    assert updated.json()["is_active"] is False

    # Retired rows disappear from the default listing but stay retrievable.
    active = client.get("/api/v1/admin/motivation-texts", headers=auth(owner))
    assert active.json() == []
    full = client.get(
        "/api/v1/admin/motivation-texts?include_inactive=true", headers=auth(owner)
    )
    assert len(full.json()) == 1


def test_company_manager_reads_but_cannot_manage_motivation(client, world, auth, make_user):
    owner = make_user("owner_mot2@corp.sa", "holding_owner", [world["alpha"]])
    client.post(
        "/api/v1/admin/motivation-texts", json=_motivation_payload(), headers=auth(owner)
    )
    denied = client.post(
        "/api/v1/admin/motivation-texts",
        json=_motivation_payload(text_en="nope"),
        headers=auth(world["alpha_mgr"]),
    )
    assert denied.status_code == 403, denied.text

    allowed = client.get(
        "/api/v1/admin/motivation-texts", headers=auth(world["alpha_mgr"])
    )
    assert allowed.status_code == 200, allowed.text


def test_dashboard_surfaces_the_role_sentence(client, world, auth, make_user, db):
    owner = make_user("owner_mot3@corp.sa", "holding_owner", [world["alpha"]])
    client.post(
        "/api/v1/admin/motivation-texts",
        json=_motivation_payload(
            text_ar="جملة عامة", text_en="Generic", audience_role=None
        ),
        headers=auth(owner),
    )
    client.post(
        "/api/v1/admin/motivation-texts",
        json=_motivation_payload(
            text_ar="جملة للتنمية", text_en="For BD", audience_role="business_development"
        ),
        headers=auth(owner),
    )

    # The owner (holding) sees the generic sentence, not the BD-targeted one.
    holding = client.get("/api/v1/dashboard/holding", headers=auth(owner))
    assert holding.status_code == 200, holding.text
    assert holding.json()["motivation"]["text_en"] == "Generic"

    bd = make_user("bd_mot@corp.sa", "business_development", [world["alpha"]])
    company = client.get(
        f"/api/v1/dashboard/company/{world['alpha'].id}", headers=auth(bd)
    )
    assert company.status_code == 200, company.text
    assert company.json()["motivation"]["text_en"] == "For BD"


def test_dashboard_motivation_is_none_when_library_empty(client, world, auth):
    holding = client.get("/api/v1/dashboard/holding", headers=auth(world["owner"]))
    assert holding.status_code == 200, holding.text
    assert holding.json()["motivation"] is None
