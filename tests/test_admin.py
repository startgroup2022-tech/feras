"""User and company administration (Holding Owner only)."""

from __future__ import annotations

import pytest

from backend.db.models.enums import CompanyHealth

USERS = "/api/v1/users"
COMPANIES = "/api/v1/companies"


# --------------------------------------------------------------------------
# users
# --------------------------------------------------------------------------
def test_owner_creates_a_user(client, auth, make_user):
    owner = make_user("owner@corp.sa", "holding_owner")

    response = client.post(
        USERS,
        headers=auth(owner),
        json={
            "email": "new.manager@corp.sa",
            "password": "StrongPass!2027",
            "full_name_ar": "مدير جديد",
            "role_code": "company_manager",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new.manager@corp.sa"
    assert body["role_code"] == "company_manager"
    assert "password" not in body and "password_hash" not in body


def test_created_user_can_log_in(client, auth, make_user):
    owner = make_user("owner@corp.sa", "holding_owner")
    client.post(
        USERS,
        headers=auth(owner),
        json={
            "email": "new.manager@corp.sa",
            "password": "StrongPass!2027",
            "full_name_ar": "مدير جديد",
            "role_code": "company_manager",
        },
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "new.manager@corp.sa", "password": "StrongPass!2027"},
    )

    assert response.status_code == 200


def test_duplicate_email_is_rejected(client, auth, make_user):
    owner = make_user("owner@corp.sa", "holding_owner")

    response = client.post(
        USERS,
        headers=auth(owner),
        json={
            "email": "owner@corp.sa",
            "password": "StrongPass!2027",
            "full_name_ar": "مكرر",
            "role_code": "company_manager",
        },
    )

    assert response.status_code == 409


def test_unknown_role_is_rejected(client, auth, make_user):
    owner = make_user("owner@corp.sa", "holding_owner")

    response = client.post(
        USERS,
        headers=auth(owner),
        json={
            "email": "x@corp.sa",
            "password": "StrongPass!2027",
            "full_name_ar": "مستخدم",
            "role_code": "does_not_exist",
        },
    )

    assert response.status_code in (400, 422)


@pytest.mark.parametrize("password", ["short", "1234567"])
def test_weak_password_is_rejected(client, auth, make_user, password):
    owner = make_user("owner@corp.sa", "holding_owner")

    response = client.post(
        USERS,
        headers=auth(owner),
        json={
            "email": "weak@corp.sa",
            "password": password,
            "full_name_ar": "مستخدم",
            "role_code": "company_manager",
        },
    )

    assert response.status_code == 422


def test_email_must_be_syntactically_valid(client, auth, make_user):
    owner = make_user("owner@corp.sa", "holding_owner")

    response = client.post(
        USERS,
        headers=auth(owner),
        json={
            "email": "not-an-email",
            "password": "StrongPass!2027",
            "full_name_ar": "مستخدم",
            "role_code": "company_manager",
        },
    )

    assert response.status_code == 422


def test_internal_domain_email_is_accepted(client, auth, make_user):
    """Internal addresses such as ``.local`` must not be rejected."""
    owner = make_user("owner@corp.sa", "holding_owner")

    response = client.post(
        USERS,
        headers=auth(owner),
        json={
            "email": "ops@safir.local",
            "password": "StrongPass!2027",
            "full_name_ar": "مستخدم داخلي",
            "role_code": "accountant",
        },
    )

    assert response.status_code == 201


def test_manager_cannot_list_users(client, auth, make_user):
    """User administration is not exposed to company users at all."""
    manager = make_user("mgr@corp.sa", "company_manager")

    assert client.get(USERS, headers=auth(manager)).status_code in (403, 404, 405)


def test_owner_can_read_own_effective_permissions(client, auth, make_user):
    owner = make_user("owner@corp.sa", "holding_owner")

    response = client.get("/api/v1/users/me/permissions", headers=auth(owner))

    assert response.status_code == 200
    assert response.json()["role_code"] == "holding_owner"


def test_deactivating_a_user_invalidates_existing_tokens(client, auth, make_user, db):
    make_user("owner@corp.sa", "holding_owner")
    target = make_user("mgr@corp.sa", "company_manager")
    headers = auth(target)

    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

    target.is_active = False
    db.add(target)
    db.commit()

    # The token is checked against the live user on every request.
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_user_creation_is_audited(client, auth, make_user, db):
    from backend.db.models import AuditLog
    from backend.db.models.audit_actions import AuditAction

    owner = make_user("owner@corp.sa", "holding_owner")
    client.post(
        USERS,
        headers=auth(owner),
        json={
            "email": "audited@corp.sa",
            "password": "StrongPass!2027",
            "full_name_ar": "مستخدم",
            "role_code": "company_manager",
        },
    )

    assert (
        db.query(AuditLog).filter(AuditLog.action == AuditAction.USER_CREATED).count() == 1
    )


# --------------------------------------------------------------------------
# companies
# --------------------------------------------------------------------------
def test_owner_creates_a_company(client, auth, make_user):
    owner = make_user("owner@corp.sa", "holding_owner")

    response = client.post(
        COMPANIES,
        headers=auth(owner),
        json={"code": "NEWCO", "name_ar": "شركة جديدة", "name_en": "New Co", "sector": "تقنية"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["code"] == "NEWCO"
    assert body["status"] == "active"


def test_company_code_is_normalised_to_upper_case(client, auth, make_user):
    owner = make_user("owner@corp.sa", "holding_owner")

    response = client.post(
        COMPANIES,
        headers=auth(owner),
        json={"code": "lower", "name_ar": "شركة", "name_en": "Co"},
    )

    assert response.status_code == 201
    assert response.json()["code"] == "LOWER"


def test_company_code_is_unique(client, auth, make_user):
    owner = make_user("owner@corp.sa", "holding_owner")
    payload = {"code": "NEWCO", "name_ar": "شركة", "name_en": "Co"}
    client.post(COMPANIES, headers=auth(owner), json=payload)

    duplicate = client.post(COMPANIES, headers=auth(owner), json=payload)

    assert duplicate.status_code == 409


def test_manager_can_read_a_company_it_has_access_to(client, world, auth):
    response = client.get(f"{COMPANIES}/{world['alpha'].id}", headers=auth(world["alpha_mgr"]))

    assert response.status_code == 200
    assert response.json()["code"] == "ALPHA"


def test_manager_cannot_read_a_company_it_lacks_access_to(client, world, auth):
    response = client.get(f"{COMPANIES}/{world['beta'].id}", headers=auth(world["alpha_mgr"]))

    assert response.status_code == 404


def test_manager_cannot_create_a_company(client, auth, make_user):
    manager = make_user("mgr@corp.sa", "company_manager")

    response = client.post(
        COMPANIES, headers=auth(manager), json={"code": "NOPE", "name_ar": "x", "name_en": "x"}
    )

    assert response.status_code == 403


# --------------------------------------------------------------------------
# RBAC catalogue sync
# --------------------------------------------------------------------------
def test_owner_can_sync_the_rbac_catalogue(client, auth, make_user):
    owner = make_user("owner@corp.sa", "holding_owner")

    response = client.post("/api/v1/rbac/sync", headers=auth(owner))

    assert response.status_code in (200, 204)


def test_manager_cannot_sync_the_rbac_catalogue(client, auth, make_user):
    manager = make_user("mgr@corp.sa", "company_manager")

    assert client.post("/api/v1/rbac/sync", headers=auth(manager)).status_code == 403


# --------------------------------------------------------------------------
# Phase 2: administration endpoints
# --------------------------------------------------------------------------
def test_owner_lists_users(client, world, auth):
    response = client.get("/api/v1/users", headers=auth(world["owner"]))
    assert response.status_code == 200
    assert len(response.json()) == 4


def test_update_user_role_and_names(client, world, auth):
    response = client.patch(
        f"/api/v1/users/{world['alpha_mgr'].id}",
        headers=auth(world["owner"]),
        json={"full_name_en": "Alpha Manager", "role_code": "marketing"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["role_code"] == "marketing"
    assert response.json()["full_name_en"] == "Alpha Manager"


def test_update_user_rejects_unknown_role(client, world, auth):
    response = client.patch(
        f"/api/v1/users/{world['alpha_mgr'].id}",
        headers=auth(world["owner"]),
        json={"role_code": "wizard"},
    )
    assert response.status_code == 422


def test_admin_cannot_deactivate_self(client, world, auth):
    response = client.patch(
        f"/api/v1/users/{world['owner'].id}",
        headers=auth(world["owner"]),
        json={"is_active": False},
    )
    assert response.status_code == 422


def test_grant_and_revoke_company_access(client, world, auth, make_company):
    gamma = make_company("GAMMA", "شركة جاما")
    target = world["alpha_mgr"]

    granted = client.post(
        f"/api/v1/users/{target.id}/company-access",
        headers=auth(world["owner"]),
        json={"company_id": gamma.id, "can_write": False},
    )
    assert granted.status_code == 200, granted.text
    assert gamma.id in granted.json()["company_ids"]

    revoked = client.delete(
        f"/api/v1/users/{target.id}/company-access/{gamma.id}",
        headers=auth(world["owner"]),
    )
    assert revoked.status_code == 200
    assert gamma.id not in revoked.json()["company_ids"]


def test_grant_access_is_idempotent(client, world, auth):
    target = world["alpha_mgr"]
    for _ in range(2):
        response = client.post(
            f"/api/v1/users/{target.id}/company-access",
            headers=auth(world["owner"]),
            json={"company_id": world["alpha"].id, "can_write": True},
        )
        assert response.status_code == 200
    assert response.json()["company_ids"].count(world["alpha"].id) == 1


def test_grant_access_requires_permission(client, world, auth):
    response = client.post(
        f"/api/v1/users/{world['alpha_mgr'].id}/company-access",
        headers=auth(world["alpha_mgr"]),
        json={"company_id": world["beta"].id},
    )
    assert response.status_code == 403


def test_update_company_health_and_sector(client, world, auth):
    response = client.patch(
        f"/api/v1/companies/{world['beta'].id}",
        headers=auth(world["owner"]),
        json={"health": CompanyHealth.ATTENTION.value, "sector": "Retail"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["health"] == CompanyHealth.ATTENTION.value
    assert response.json()["sector"] == "Retail"


def test_update_company_rejects_invalid_health(client, world, auth):
    response = client.patch(
        f"/api/v1/companies/{world['beta'].id}",
        headers=auth(world["owner"]),
        json={"health": "on-fire"},
    )
    assert response.status_code == 422


def test_update_company_requires_permission(client, world, auth):
    response = client.patch(
        f"/api/v1/companies/{world['beta'].id}",
        headers=auth(world["alpha_mgr"]),
        json={"sector": "Retail"},
    )
    assert response.status_code == 403


def test_user_update_is_audited(client, world, auth, db):
    from backend.db.models.ai import AuditLog

    client.patch(
        f"/api/v1/users/{world['alpha_mgr'].id}",
        headers=auth(world["owner"]),
        json={"full_name_en": "Renamed"},
    )
    assert "user.updated" in [row.action for row in db.query(AuditLog).all()]
