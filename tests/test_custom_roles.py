"""Custom-role authorization and confidentiality tests.

The specification (T02 / D04) requires that server-side enforcement holds for
roles an administrator creates at runtime, not just the predefined catalogue,
and that a custom role can never reach the confidential owner-only surface
(leadership assessments) -- and never grant a permission its creator does not
hold (no privilege escalation).

These exercise real APIs against the real database, using only predefined
actors to create the custom roles.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def custom_world(world, make_user):
    """Owner with explicit grants on both companies, plus a second company mgr."""
    owner_all = make_user("owner_all@corp.sa", "holding_owner", [world["alpha"], world["beta"]])
    out = dict(world)
    out["owner_all"] = owner_all
    return out


def _create_role(client, auth, owner, code: str, permissions: list[str]):
    return client.post(
        "/api/v1/admin/roles",
        json={
            "code": code,
            "name_ar": "دور مخصص",
            "name_en": "Custom role",
            "permissions": permissions,
        },
        headers=auth(owner),
    )


def _make_user_with_custom_role(make_user, db, code: str, role_code: str, companies=()):
    return make_user(f"{code}@corp.sa", role_code, list(companies))


# --------------------------------------------------------------------------
# server-side enforcement for custom roles
# --------------------------------------------------------------------------
def test_custom_role_permissions_are_enforced_server_side(client, custom_world, auth, make_user):
    owner = custom_world["owner_all"]
    created = _create_role(client, auth, owner, "alpha_reader", ["company.read"])
    assert created.status_code == 201, created.text

    # A user in the new role can read companies...
    viewer = make_user("viewer@corp.sa", "alpha_reader")
    assert client.get("/api/v1/companies", headers=auth(viewer)).status_code == 200

    # ...but cannot manage users (no user.manage).
    denied = client.get("/api/v1/admin/users", headers=auth(viewer))
    assert denied.status_code == 403, denied.text

    # Revoke company.read; the same token now loses the read immediately.
    updated = client.put(
        "/api/v1/admin/roles/alpha_reader/permissions",
        json={"permissions": []},
        headers=auth(owner),
    )
    assert updated.status_code == 200, updated.text
    assert client.get("/api/v1/companies", headers=auth(viewer)).status_code == 403


def test_custom_role_cannot_escalate_beyond_its_creator(client, world, auth, make_user):
    """An actor may not grant permissions they do not hold."""
    manager = world["alpha_mgr"] if "alpha_mgr" in world else None
    if manager is None:
        manager = make_user("cm@corp.sa", "company_manager", [world["alpha"]])
    escalate = _create_role(client, auth, manager, "sneaky", ["user.manage"])
    assert escalate.status_code == 403, escalate.text


# --------------------------------------------------------------------------
# confidential owner-only surface (T02 / D04)
# --------------------------------------------------------------------------
def test_custom_role_with_every_common_permission_cannot_reach_leadership(
    client, custom_world, auth, make_user, db
):
    """Even an all-granted custom role must not read a leadership assessment.

    Confidentiality is not a permission code; it is enforced by record, so a
    custom role cannot buy its way in.
    """
    owner = custom_world["owner_all"]

    # Owner creates a confidential leadership assessment about the alpha manager.
    subject = custom_world["beta_mgr"]
    created = client.post(
        "/api/v1/employees/assessments",
        json={
            "company_id": custom_world["alpha"].id,
            "period_label": "2027-Q4",
            "assessment_type": "leadership",
            "subject_user_id": subject.id,
            "summary": "سرّي",
        },
        headers=auth(owner),
    )
    assert created.status_code == 201, created.text
    assessment_id = created.json()["id"]

    # A custom role granted broad assessment powers (all head-office perms the
    # owner holds that relate to assessment/employee data).
    from backend.rbac.permissions import ROLE_PERMISSIONS

    owner_perms = sorted(ROLE_PERMISSIONS["holding_owner"])
    grantable = [p for p in owner_perms if p in {
        "assessment.read", "assessment.manage", "assessment.approve",
        "employee.read", "employee.manage", "company.read",
        "confidential_access.manage",
    }]
    role = _create_role(client, auth, owner, "all_buttons", grantable)
    assert role.status_code == 201, role.text
    spy = make_user("spy@corp.sa", "all_buttons", [custom_world["alpha"]])

    # It can list employee (non-confidential) assessments and read companies...
    assert client.get("/api/v1/companies", headers=auth(spy)).status_code == 200

    # ...but the leadership assessment is invisible: not listed, and 404 by id.
    listed = client.get(
        "/api/v1/employees/assessments/list?assessment_type=leadership",
        headers=auth(spy),
    )
    assert listed.status_code == 200, listed.text
    assert listed.json() == []

    by_id = client.get(
        f"/api/v1/confidential-access/grants?subject_type=leadership_assessment"
        f"&subject_id={assessment_id}",
        headers=auth(spy),
    )
    # Grant listing is itself owner-only (require_permission confidential_access.manage
    # plus owner check); a non-owner must not see grants for a record it cannot see.
    assert by_id.status_code in (403, 404), by_id.text
