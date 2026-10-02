"""User and company administration (Holding Owner only)."""

from __future__ import annotations

import pytest

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
