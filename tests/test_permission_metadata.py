"""Bilingual permission metadata and the admin catalogue endpoint.

The metadata is the presentation layer for the permission catalogue: it adds
Arabic/English names and descriptions, a category and an action kind, and a
"danger" hint. It must describe *every* permission and must never change
authorization, which still runs against the codes in ``backend.rbac.permissions``.
"""

from __future__ import annotations

from backend.rbac import permission_metadata as pm
from backend.rbac.permissions import ALL_PERMISSIONS


def test_every_permission_has_curated_metadata():
    assert pm.unknown_codes() == []


def test_catalogue_covers_every_permission_exactly_once():
    codes = [p["code"] for p in pm.catalogue()]
    assert sorted(codes) == sorted(ALL_PERMISSIONS)
    assert len(codes) == len(set(codes))


def test_every_entry_is_bilingual_and_non_empty():
    for entry in pm.catalogue():
        for field in (
            "name_ar",
            "name_en",
            "description_ar",
            "description_en",
        ):
            assert entry[field], f"{entry['code']} has an empty {field}"


def test_categories_and_actions_referenced_exist():
    cat_keys = {c["key"] for c in pm.CATEGORIES}
    act_keys = {a["key"] for a in pm.ACTIONS}
    for entry in pm.catalogue():
        assert entry["category"] in cat_keys, entry["code"]
        assert entry["action"] in act_keys, entry["code"]


def test_category_and_action_keys_are_unique():
    cat_keys = [c["key"] for c in pm.CATEGORIES]
    act_keys = [a["key"] for a in pm.ACTIONS]
    assert len(cat_keys) == len(set(cat_keys))
    assert len(act_keys) == len(set(act_keys))


def test_arabic_and_english_names_differ_for_curated_entries():
    """A curated entry must actually be translated, not just copied."""
    for entry in pm.catalogue():
        assert entry["name_ar"] != entry["name_en"], entry["code"]


def test_describe_unknown_code_falls_back_to_the_code():
    """A permission with no curated metadata is still described, not hidden."""
    entry = pm.describe("future.permission")
    assert entry["code"] == "future.permission"
    assert entry["name_en"] == "future.permission"
    assert entry["danger"] is False


def test_dangerous_permissions_are_marked():
    dangerous = {p["code"] for p in pm.catalogue() if p["danger"]}
    # Destructive / authority-granting codes must be flagged for the owner.
    assert "user.manage" in dangerous
    assert "permission.assign" in dangerous
    assert "role.manage" in dangerous
    # A read-only code must not be flagged.
    assert "company.read" not in dangerous


# --------------------------------------------------------------------------
# admin endpoint
# --------------------------------------------------------------------------


def test_owner_can_read_the_permission_catalogue(client, auth, make_user):
    owner = make_user("owner@corp.sa", "holding_owner")

    response = client.get("/api/v1/admin/permissions/catalogue", headers=auth(owner))

    assert response.status_code == 200
    body = response.json()
    assert {p["code"] for p in body["permissions"]} == set(ALL_PERMISSIONS)
    assert body["categories"] and body["actions"]
    sample = body["permissions"][0]
    for field in ("name_ar", "name_en", "description_ar", "description_en", "category", "action"):
        assert field in sample


def test_manager_cannot_read_the_permission_catalogue(client, auth, make_user):
    manager = make_user("mgr@corp.sa", "company_manager")

    response = client.get("/api/v1/admin/permissions/catalogue", headers=auth(manager))

    assert response.status_code == 403
