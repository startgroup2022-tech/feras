"""RBAC: role/permission catalogue and endpoint enforcement."""

from __future__ import annotations

import pytest

from backend.rbac.authorization import (
    accessible_company_ids,
    has_permission,
    is_holding_wide,
    role_permissions,
)
from backend.rbac.permissions import HOLDING_WIDE_ROLES, ROLE_PERMISSIONS, Perm

ALL_ROLES = list(ROLE_PERMISSIONS)


def test_every_role_has_a_permission_set():
    for role in ALL_ROLES:
        assert ROLE_PERMISSIONS[role], f"{role} has no permissions"


def test_holding_owner_holds_the_widest_set():
    owner = ROLE_PERMISSIONS["holding_owner"]
    for role in ALL_ROLES:
        if role == "holding_owner":
            continue
        assert ROLE_PERMISSIONS[role] <= owner, f"{role} has permissions the owner lacks"


def test_company_manager_cannot_manage_users_or_companies():
    perms = ROLE_PERMISSIONS["company_manager"]

    assert Perm.USER_MANAGE not in perms
    assert Perm.COMPANY_MANAGE not in perms
    assert Perm.DASHBOARD_HOLDING not in perms


def test_company_manager_can_submit_its_own_report():
    perms = ROLE_PERMISSIONS["company_manager"]

    assert Perm.REPORT_CREATE in perms
    assert Perm.REPORT_SUBMIT in perms
    assert Perm.REPORT_READ_OWN in perms


def test_accountant_holds_review_but_not_company_management():
    perms = ROLE_PERMISSIONS["accountant"]

    assert Perm.FINANCIAL_REVIEW_WRITE in perms
    assert Perm.REPORT_READ_ALL in perms
    assert Perm.COMPANY_MANAGE not in perms


@pytest.mark.parametrize("role", ["business_development", "marketing", "designer"])
def test_support_departments_can_handle_but_not_create_requests(role):
    perms = ROLE_PERMISSIONS[role]

    assert Perm.SUPPORT_READ_ALL in perms
    assert Perm.SUPPORT_STATUS_CHANGE in perms
    # Support departments respond to requests; they do not raise them.
    assert Perm.SUPPORT_CREATE not in perms


def test_holding_wide_roles_match_the_catalogue():
    assert set(HOLDING_WIDE_ROLES) == {
        "holding_owner",
        "accountant",
        "business_development",
        "marketing",
        "designer",
    }


# --------------------------------------------------------------------------
# runtime authorization behaviour
# --------------------------------------------------------------------------
def test_holding_wide_users_are_not_confined(db, make_user):
    owner = make_user("owner@corp.sa", "holding_owner")
    accountant = make_user("acc@corp.sa", "accountant")
    manager = make_user("mgr@corp.sa", "company_manager")

    assert is_holding_wide(owner) is True
    assert is_holding_wide(accountant) is True
    assert is_holding_wide(manager) is False


def test_holding_wide_user_has_unrestricted_scope(db, make_user):
    accountant = make_user("acc@corp.sa", "accountant")

    # ``None`` means "no company filter", i.e. all companies.
    assert accessible_company_ids(accountant) is None


def test_company_manager_scope_is_its_grants(db, make_company, make_user):
    alpha = make_company("ALPHA", "ألفا")
    make_company("BETA", "بيتا")
    manager = make_user("mgr@corp.sa", "company_manager", [alpha])

    assert accessible_company_ids(manager) == [alpha.id]


def test_manager_without_grants_has_empty_scope(db, make_user):
    manager = make_user("mgr@corp.sa", "company_manager")

    assert accessible_company_ids(manager) == []


def test_superuser_bypasses_scope(db, make_user):
    user = make_user("root@corp.sa", "company_manager")
    user.is_superuser = True

    assert accessible_company_ids(user) is None


def test_has_permission_reflects_role(db, make_user):
    manager = make_user("mgr@corp.sa", "company_manager")

    assert has_permission(manager, Perm.REPORT_CREATE) is True
    assert has_permission(manager, Perm.USER_MANAGE) is False


def test_user_without_a_role_has_no_permissions(db, make_user):
    """A user whose role row is missing must fail closed, not open."""
    user = make_user("x@corp.sa", "company_manager")
    user.role = None

    assert role_permissions(user) == frozenset()
    assert is_holding_wide(user) is False


# --------------------------------------------------------------------------
# endpoint enforcement
# --------------------------------------------------------------------------
def test_only_owner_can_create_users(client, auth, make_user):
    owner = make_user("owner@corp.sa", "holding_owner")
    manager = make_user("mgr@corp.sa", "company_manager")
    payload = {
        "email": "new@corp.sa",
        "password": "StrongPass!2027",
        "full_name_ar": "مستخدم جديد",
        "role_code": "company_manager",
    }

    assert client.post("/api/v1/users", headers=auth(manager), json=payload).status_code == 403
    assert client.post("/api/v1/users", headers=auth(owner), json=payload).status_code == 201


def test_only_owner_can_create_companies(client, auth, make_user):
    owner = make_user("owner@corp.sa", "holding_owner")
    accountant = make_user("acc@corp.sa", "accountant")
    payload = {"code": "NEWCO", "name_ar": "شركة جديدة", "name_en": "New Co"}

    assert client.post("/api/v1/companies", headers=auth(accountant), json=payload).status_code == 403
    assert client.post("/api/v1/companies", headers=auth(owner), json=payload).status_code == 201


def test_duplicate_company_code_is_rejected(client, auth, make_user, make_company):
    owner = make_user("owner@corp.sa", "holding_owner")
    make_company("DUP", "شركة")

    response = client.post(
        "/api/v1/companies",
        headers=auth(owner),
        json={"code": "DUP", "name_ar": "أخرى", "name_en": "Other"},
    )

    assert response.status_code == 409


def test_manager_cannot_review_finances(client, world, auth):
    response = client.post(
        f"/api/v1/monthly-reports/{world['alpha_report'].id}/financial-review",
        headers=auth(world["alpha_mgr"]),
        json={"is_financially_accurate": True},
    )

    assert response.status_code == 403


def test_roles_endpoint_lists_the_catalogue(client, auth, make_user):
    owner = make_user("owner@corp.sa", "holding_owner")

    response = client.get("/api/v1/rbac/roles", headers=auth(owner))

    assert response.status_code == 200
    codes = {r["code"] for r in response.json()}
    assert codes == set(ALL_ROLES)


def test_manager_cannot_list_roles(client, auth, make_user):
    manager = make_user("mgr@corp.sa", "company_manager")

    assert client.get("/api/v1/rbac/roles", headers=auth(manager)).status_code == 403
