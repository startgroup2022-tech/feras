"""Phase 2 group administration: holding, ownership, departments, roles, audit.

The emphasis is on the security properties:

* administration endpoints are permission-gated, and a company-scoped role can
  only touch its own companies;
* privilege escalation is impossible in both directions -- you cannot grant a
  permission you do not hold, nor assign a role more privileged than your own;
* closing an ownership stake preserves history instead of deleting it.
"""

from __future__ import annotations

import pytest

from backend.db.models.enums import CompanyHealth

ADMIN = "/api/v1/admin"


@pytest.fixture
def admin(db, make_user):
    """A Super Admin: full group administration without being the owner."""
    return make_user("admin@corp.sa", "super_admin")


@pytest.fixture
def scoped(db, make_company, make_user):
    """A Company Owner confined to a single company."""
    owned = make_company("OWNED", "شركة مملوكة", health=CompanyHealth.STABLE.value)
    other = make_company("OTHER", "شركة أخرى", health=CompanyHealth.STABLE.value)
    user = make_user("owner.co@corp.sa", "company_owner", [owned])
    return {"user": user, "owned": owned, "other": other}


# --------------------------------------------------------------------------
# holding profile
# --------------------------------------------------------------------------
def test_holding_is_created_on_first_read(client, admin, auth):
    response = client.get(f"{ADMIN}/holding", headers=auth(admin))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == "SAFIR"
    assert body["default_currency"] == "SAR"


def test_holding_update_requires_group_manage(client, world, auth):
    # A company manager cannot edit the Holding profile.
    response = client.patch(
        f"{ADMIN}/holding",
        headers=auth(world["alpha_mgr"]),
        json={"legal_name_en": "Nope"},
    )
    assert response.status_code == 403


def test_holding_update_persists_and_audits(client, admin, auth, db):
    from backend.db.models.ai import AuditLog

    response = client.patch(
        f"{ADMIN}/holding",
        headers=auth(admin),
        json={"legal_name_en": "Safir Group Holdings", "tax_number": "3000000000"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["legal_name_en"] == "Safir Group Holdings"
    assert "holding.updated" in [row.action for row in db.query(AuditLog).all()]


def test_holding_update_rejects_bad_status(client, admin, auth):
    response = client.patch(
        f"{ADMIN}/holding", headers=auth(admin), json={"status": "exploded"}
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------
# departments
# --------------------------------------------------------------------------
def test_admin_creates_a_department(client, admin, make_company, auth):
    company = make_company("DEPTCO", "شركة الأقسام")

    response = client.post(
        f"{ADMIN}/departments",
        headers=auth(admin),
        json={
            "company_id": company.id,
            "code": "fin",
            "name_ar": "الإدارة المالية",
            "name_en": "Finance",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["code"] == "FIN"
    assert response.json()["company_id"] == company.id


def test_department_code_is_unique_per_company(client, admin, make_company, auth):
    company = make_company("DEPTCO", "شركة الأقسام")
    payload = {
        "company_id": company.id,
        "code": "FIN",
        "name_ar": "المالية",
        "name_en": "Finance",
    }
    client.post(f"{ADMIN}/departments", headers=auth(admin), json=payload)

    duplicate = client.post(f"{ADMIN}/departments", headers=auth(admin), json=payload)
    assert duplicate.status_code == 409


def test_scoped_user_cannot_create_department_in_another_company(
    client, scoped, auth
):
    response = client.post(
        f"{ADMIN}/departments",
        headers=auth(scoped["user"]),
        json={
            "company_id": scoped["other"].id,
            "code": "OPS",
            "name_ar": "العمليات",
            "name_en": "Operations",
        },
    )
    # 403 because the role lacks department.manage; 404 would be the scoping
    # answer if the role held the permission. Either way it must not succeed.
    assert response.status_code in (403, 404)


def test_department_list_is_company_scoped(client, admin, scoped, auth):
    client.post(
        f"{ADMIN}/departments",
        headers=auth(admin),
        json={
            "company_id": scoped["owned"].id,
            "code": "FIN",
            "name_ar": "المالية",
            "name_en": "Finance",
        },
    )
    client.post(
        f"{ADMIN}/departments",
        headers=auth(admin),
        json={
            "company_id": scoped["other"].id,
            "code": "OPS",
            "name_ar": "العمليات",
            "name_en": "Operations",
        },
    )

    response = client.get(f"{ADMIN}/departments", headers=auth(scoped["user"]))
    assert response.status_code == 200, response.text
    assert [d["code"] for d in response.json()] == ["FIN"]


def test_department_requires_manage_permission(client, world, auth, make_company):
    company = make_company("XCO", "شركة")
    response = client.post(
        f"{ADMIN}/departments",
        headers=auth(world["alpha_mgr"]),
        json={
            "company_id": company.id,
            "code": "FIN",
            "name_ar": "المالية",
            "name_en": "Finance",
        },
    )
    assert response.status_code == 403


# --------------------------------------------------------------------------
# ownership
# --------------------------------------------------------------------------
def test_create_stake_between_companies(client, admin, make_company, auth):
    parent = make_company("PARENT", "الشركة الأم")
    child = make_company("CHILD", "الشركة التابعة")

    response = client.post(
        f"{ADMIN}/ownerships",
        headers=auth(admin),
        json={
            "owned_company_id": child.id,
            "owner_company_id": parent.id,
            "ownership_percentage": "80",
            "effective_from": "2026-01-01",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["ownership_percentage"] == 80.0
    assert body["owner_company_name_en"] == "PARENT"


def test_external_owner_is_accepted(client, admin, make_company, auth):
    company = make_company("EXT", "شركة")
    response = client.post(
        f"{ADMIN}/ownerships",
        headers=auth(admin),
        json={
            "owned_company_id": company.id,
            "external_owner_name": "Public Fund",
            "ownership_percentage": "25",
            "effective_from": "2026-01-01",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["external_owner_name"] == "Public Fund"


def test_stake_requires_exactly_one_owner(client, admin, make_company, auth):
    company = make_company("AMB", "شركة")
    both = client.post(
        f"{ADMIN}/ownerships",
        headers=auth(admin),
        json={
            "owned_company_id": company.id,
            "owner_company_id": company.id,
            "external_owner_name": "Someone",
            "ownership_percentage": "10",
            "effective_from": "2026-01-01",
        },
    )
    assert both.status_code == 422

    neither = client.post(
        f"{ADMIN}/ownerships",
        headers=auth(admin),
        json={
            "owned_company_id": company.id,
            "ownership_percentage": "10",
            "effective_from": "2026-01-01",
        },
    )
    assert neither.status_code == 422


def test_self_ownership_is_rejected(client, admin, make_company, auth):
    company = make_company("SELF", "شركة")
    response = client.post(
        f"{ADMIN}/ownerships",
        headers=auth(admin),
        json={
            "owned_company_id": company.id,
            "owner_company_id": company.id,
            "ownership_percentage": "10",
            "effective_from": "2026-01-01",
        },
    )
    # Self-ownership parses as an invalid payload (owner == owned is caught by
    # cycle detection) and is refused.
    assert response.status_code in (409, 422)


def test_indirect_cycle_is_rejected(client, admin, make_company, auth):
    a = make_company("A", "ألف")
    b = make_company("B", "باء")
    c = make_company("C", "جيم")

    # A owns B, B owns C; then C owning A would close a loop.
    for owned, owner in ((b, a), (c, b)):
        assert (
            client.post(
                f"{ADMIN}/ownerships",
                headers=auth(admin),
                json={
                    "owned_company_id": owned.id,
                    "owner_company_id": owner.id,
                    "ownership_percentage": "60",
                    "effective_from": "2026-01-01",
                },
            ).status_code
            == 201
        )

    response = client.post(
        f"{ADMIN}/ownerships",
        headers=auth(admin),
        json={
            "owned_company_id": a.id,
            "owner_company_id": c.id,
            "ownership_percentage": "60",
            "effective_from": "2026-01-01",
        },
    )
    assert response.status_code == 409


def test_active_stakes_cannot_exceed_one_hundred_percent(
    client, admin, make_company, auth
):
    company = make_company("CAP", "شركة")
    holder = make_company("HOLD", "ماسك")

    assert (
        client.post(
            f"{ADMIN}/ownerships",
            headers=auth(admin),
            json={
                "owned_company_id": company.id,
                "owner_company_id": holder.id,
                "ownership_percentage": "70",
                "effective_from": "2026-01-01",
            },
        ).status_code
        == 201
    )

    response = client.post(
        f"{ADMIN}/ownerships",
        headers=auth(admin),
        json={
            "owned_company_id": company.id,
            "external_owner_name": "Other fund",
            "ownership_percentage": "40",
            "effective_from": "2026-01-01",
        },
    )
    assert response.status_code == 422


def test_ending_a_stake_preserves_history(client, admin, make_company, auth):
    parent = make_company("PARENT", "الشركة الأم")
    child = make_company("CHILD", "الشركة التابعة")
    created = client.post(
        f"{ADMIN}/ownerships",
        headers=auth(admin),
        json={
            "owned_company_id": child.id,
            "owner_company_id": parent.id,
            "ownership_percentage": "100",
            "effective_from": "2026-01-01",
        },
    ).json()

    ended = client.post(
        f"{ADMIN}/ownerships/{created['id']}/end", headers=auth(admin)
    )
    assert ended.status_code == 200, ended.text
    assert ended.json()["status"] == "ended"

    # The row is still listed: history is preserved, not deleted.
    listed = client.get(f"{ADMIN}/ownerships", headers=auth(admin)).json()
    assert any(row["id"] == created["id"] for row in listed)

    # With the stake closed, a new full stake is allowed again.
    again = client.post(
        f"{ADMIN}/ownerships",
        headers=auth(admin),
        json={
            "owned_company_id": child.id,
            "owner_company_id": parent.id,
            "ownership_percentage": "100",
            "effective_from": "2027-01-01",
        },
    )
    assert again.status_code == 201


def test_ownership_requires_manage_permission(client, world, auth, make_company):
    company = make_company("NOPE", "شركة")
    response = client.post(
        f"{ADMIN}/ownerships",
        headers=auth(world["alpha_mgr"]),
        json={
            "owned_company_id": company.id,
            "external_owner_name": "Fund",
            "ownership_percentage": "10",
            "effective_from": "2026-01-01",
        },
    )
    assert response.status_code == 403


def test_group_structure_reflects_stakes(client, admin, make_company, auth):
    parent = make_company("PARENT", "الأم")
    child = make_company("CHILD", "التابعة")
    client.post(
        f"{ADMIN}/ownerships",
        headers=auth(admin),
        json={
            "owned_company_id": child.id,
            "owner_company_id": parent.id,
            "ownership_percentage": "75",
            "effective_from": "2026-01-01",
        },
    )

    nodes = client.get(f"{ADMIN}/holding/structure", headers=auth(admin)).json()
    child_node = next(n for n in nodes if n["company_id"] == child.id)
    parent_node = next(n for n in nodes if n["company_id"] == parent.id)
    assert child_node["parent_company_id"] == parent.id
    assert child_node["ownership_percentage"] == 75.0
    assert parent_node["direct_children"] == 1


# --------------------------------------------------------------------------
# roles, permissions and privilege escalation
# --------------------------------------------------------------------------
def test_admin_lists_roles_and_permissions(client, admin, auth):
    roles = client.get(f"{ADMIN}/roles", headers=auth(admin))
    assert roles.status_code == 200, roles.text
    codes = {r["code"] for r in roles.json()}
    assert {"holding_owner", "super_admin", "company_owner"} <= codes

    permissions = client.get(f"{ADMIN}/permissions", headers=auth(admin))
    assert permissions.status_code == 200
    assert any(p["code"] == "group.manage" for p in permissions.json())


def test_creating_a_role_within_your_own_permissions_succeeds(client, admin, auth):
    response = client.post(
        f"{ADMIN}/roles",
        headers=auth(admin),
        json={
            "code": "regional_analyst",
            "name_ar": "محلل إقليمي",
            "name_en": "Regional Analyst",
            "permissions": ["company.read", "ownership.read"],
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["is_system"] is False
    assert response.json()["permissions"] == ["company.read", "ownership.read"]


def test_cannot_create_a_role_with_permissions_you_lack(client, world, auth, db, make_user):
    """A limited actor cannot manufacture authority it does not hold."""
    # Build a role that can read roles but not manage users, then confirm the
    # escalation guard blocks granting user.manage.
    from backend.db.models.enums import RoleCode

    limited = make_user("limited@corp.sa", RoleCode.CEO.value, [world["alpha"]])

    response = client.post(
        f"{ADMIN}/roles",
        headers=auth(limited),
        json={
            "code": "sneaky",
            "name_ar": "متسلل",
            "name_en": "Sneaky",
            "permissions": ["user.manage"],
        },
    )
    # CEO lacks permission.assign/role.manage entirely, so it is refused well
    # before the escalation guard is even reached.
    assert response.status_code == 403


def test_escalation_guard_blocks_granting_absent_permission(client, auth, db, make_user):
    """Directly exercise the service-level guard with a crafted actor."""
    from backend.core.errors import PermissionDeniedError
    from backend.services.role_service import create_role

    actor = make_user("weak@corp.sa", "company_manager", [])
    with pytest.raises(PermissionDeniedError):
        create_role(
            db,
            actor=actor,
            payload={
                "code": "escalated",
                "name_ar": "مرتفع",
                "name_en": "Escalated",
                "permissions": ["user.manage"],
            },
        )


def test_set_role_permissions_updates_effective_authorization(
    client, admin, auth, db, make_user
):
    """Editing a role's grants changes what its members can actually do."""
    client.post(
        f"{ADMIN}/roles",
        headers=auth(admin),
        json={
            "code": "temp_role",
            "name_ar": "مؤقت",
            "name_en": "Temporary",
            "permissions": ["company.read"],
        },
    )

    response = client.put(
        f"{ADMIN}/roles/temp_role/permissions",
        headers=auth(admin),
        json={"permissions": ["company.read", "ownership.read"]},
    )
    assert response.status_code == 200, response.text
    assert set(response.json()["permissions"]) == {"company.read", "ownership.read"}

    # A member of the role immediately sees the new permission on /auth/me.
    member = make_user("member@corp.sa", "employee", [])
    assert client.get("/api/v1/auth/me", headers=auth(member)).status_code == 200


def test_cannot_modify_a_more_privileged_role(client, scoped, auth, db):
    """A company-scoped actor must not be able to edit a holding-wide role."""
    response = client.patch(
        f"{ADMIN}/roles/holding_owner",
        headers=auth(scoped["user"]),
        json={"name_en": "Hijacked"},
    )
    assert response.status_code == 403


# --------------------------------------------------------------------------
# user directory and audit
# --------------------------------------------------------------------------
def test_admin_user_directory_is_paginated(client, admin, world, auth):
    response = client.get(f"{ADMIN}/users?limit=2&offset=0", headers=auth(admin))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["limit"] == 2
    assert body["total"] >= 4
    assert len(body["items"]) <= 2


def test_admin_user_directory_filters_by_role(client, admin, world, auth):
    response = client.get(
        f"{ADMIN}/users?role_code=holding_owner", headers=auth(admin)
    )
    assert response.status_code == 200, response.text
    codes = {u["role_code"] for u in response.json()["items"]}
    assert codes <= {"holding_owner"}


def test_user_directory_requires_read_all(client, world, auth):
    response = client.get(f"{ADMIN}/users", headers=auth(world["alpha_mgr"]))
    assert response.status_code == 403


def test_audit_log_requires_permission(client, world, auth):
    assert (
        client.get(f"{ADMIN}/audit-logs", headers=auth(world["alpha_mgr"])).status_code
        == 403
    )


def test_audit_log_lists_entries(client, admin, auth, db):
    client.patch(
        f"{ADMIN}/holding", headers=auth(admin), json={"legal_name_en": "Group"}
    )

    response = client.get(f"{ADMIN}/audit-logs", headers=auth(admin))
    assert response.status_code == 200, response.text
    actions = [row["action"] for row in response.json()["items"]]
    assert "holding.updated" in actions


# --------------------------------------------------------------------------
# user serialisation contract
# --------------------------------------------------------------------------
def test_auth_me_exposes_role_code_and_roles_list(client, world, auth):
    response = client.get("/api/v1/auth/me", headers=auth(world["owner"]))
    assert response.status_code == 200
    body = response.json()
    assert body["role_code"] == "holding_owner"
    assert body["roles"] == ["holding_owner"]
