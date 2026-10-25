"""S03 -- the managed sector catalogue.

Companies carry a free-text ``sector`` string; this is the controlled,
bilingual catalogue behind it. Reads need ``sector.read``, writes need
``sector.manage``. The company payload is unchanged, so these tests only touch
the new admin endpoints.
"""

from __future__ import annotations


def _payload(code="TECH", **over):
    data = {
        "code": code,
        "name_ar": "التقنية",
        "name_en": "Technology",
        "sort_order": 10,
    }
    data.update(over)
    return data


def test_owner_creates_and_lists_a_sector(client, world, auth, make_user):
    owner = make_user("owner_sec@corp.sa", "holding_owner", [world["alpha"]])
    created = client.post("/api/v1/admin/sectors", json=_payload(), headers=auth(owner))
    assert created.status_code == 201, created.text
    assert created.json()["code"] == "TECH"

    listed = client.get("/api/v1/admin/sectors", headers=auth(owner))
    assert listed.status_code == 200, listed.text
    assert [s["code"] for s in listed.json()] == ["TECH"]


def test_duplicate_sector_code_is_rejected(client, world, auth, make_user):
    owner = make_user("owner_sec2@corp.sa", "holding_owner", [world["alpha"]])
    assert client.post("/api/v1/admin/sectors", json=_payload(), headers=auth(owner)).status_code == 201
    dup = client.post("/api/v1/admin/sectors", json=_payload(name_ar="أخرى"), headers=auth(owner))
    assert dup.status_code == 409, dup.text


def test_update_sector_is_bilingual_and_persisted(client, world, auth, make_user):
    owner = make_user("owner_sec3@corp.sa", "holding_owner", [world["alpha"]])
    sid = client.post("/api/v1/admin/sectors", json=_payload(), headers=auth(owner)).json()["id"]
    updated = client.patch(
        f"/api/v1/admin/sectors/{sid}",
        json={"name_en": "Technology & Digital", "status": "inactive"},
        headers=auth(owner),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name_en"] == "Technology & Digital"
    assert updated.json()["status"] == "inactive"


def test_company_manager_cannot_manage_sectors(client, world, auth):
    # Company Manager has sector.read via the shared company read set, but not
    # sector.manage: the catalogue is group administration.
    denied = client.post(
        "/api/v1/admin/sectors", json=_payload(), headers=auth(world["alpha_mgr"])
    )
    assert denied.status_code == 403, denied.text

    allowed = client.get("/api/v1/admin/sectors", headers=auth(world["alpha_mgr"]))
    assert allowed.status_code == 200, allowed.text


def test_hr_manager_can_manage_sectors(client, world, auth, make_user):
    hr = make_user("hr_sec@corp.sa", "hr_manager", [world["alpha"]])
    created = client.post("/api/v1/admin/sectors", json=_payload("HRD"), headers=auth(hr))
    assert created.status_code == 201, created.text
