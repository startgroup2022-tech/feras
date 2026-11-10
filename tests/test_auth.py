"""Authentication: login, tokens, rate limiting, logout."""

from __future__ import annotations

import pytest

from backend.core.security import create_access_token
from backend.db.models.identity import User

LOGIN = "/api/v1/auth/login"


def test_login_returns_token_pair(client, make_user):
    make_user("owner@holding.sa", "holding_owner")

    response = client.post(LOGIN, json={"email": "owner@holding.sa", "password": "TestPass!2027"})

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]
    assert body["expires_in"] > 0


def test_login_rejects_wrong_password(client, make_user):
    make_user("owner@holding.sa", "holding_owner")

    response = client.post(LOGIN, json={"email": "owner@holding.sa", "password": "nope"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_login_does_not_reveal_whether_account_exists(client, make_user):
    """Unknown account and wrong password must be indistinguishable."""
    make_user("owner@holding.sa", "holding_owner")

    unknown = client.post(LOGIN, json={"email": "ghost@holding.sa", "password": "whatever"})
    wrong = client.post(LOGIN, json={"email": "owner@holding.sa", "password": "whatever"})

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]


def test_login_rejects_inactive_account(client, db, make_user):
    user = make_user("owner@holding.sa", "holding_owner")
    user.is_active = False
    db.add(user)
    db.commit()

    response = client.post(LOGIN, json={"email": "owner@holding.sa", "password": "TestPass!2027"})

    assert response.status_code == 401


def test_deactivating_an_account_blocks_subsequent_requests(client, db, auth, make_user):
    """AC-25: disabling an account prevents later requests, not just new logins."""
    user = make_user("owner@holding.sa", "holding_owner")
    headers = auth(user)
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

    user.is_active = False
    db.add(user)
    db.commit()

    blocked = client.get("/api/v1/auth/me", headers=headers)
    assert blocked.status_code == 401


def test_login_validates_email_syntax(client):
    response = client.post(LOGIN, json={"email": "not-an-email", "password": "TestPass!2027"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_login_is_rate_limited(client, make_user, monkeypatch):
    """Brute force protection is enforced when enabled."""
    from backend.core import rate_limit

    make_user("owner@holding.sa", "holding_owner")
    limiter = rate_limit.RateLimiter(max_events=3, window_seconds=60)

    from backend.api.v1 import auth as auth_module

    monkeypatch.setattr(auth_module, "_login_limiter", limiter)
    monkeypatch.setattr(auth_module.settings, "RATE_LIMIT_ENABLED", True)

    codes = [
        client.post(LOGIN, json={"email": "owner@holding.sa", "password": "bad"}).status_code
        for _ in range(5)
    ]

    assert 429 in codes, f"expected a 429 among {codes}"


def test_refresh_issues_new_tokens(client, make_user):
    make_user("owner@holding.sa", "holding_owner")
    tokens = client.post(
        LOGIN, json={"email": "owner@holding.sa", "password": "TestPass!2027"}
    ).json()

    response = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})

    assert response.status_code == 200
    assert response.json()["access_token"]


def test_access_token_is_rejected_as_refresh_token(client, make_user):
    user = make_user("owner@holding.sa", "holding_owner")
    access = create_access_token(user.id)

    response = client.post("/api/v1/auth/refresh", json={"refresh_token": access})

    assert response.status_code == 401


def test_me_returns_effective_permissions(client, login, make_user):
    make_user("owner@holding.sa", "holding_owner")

    response = client.get("/api/v1/auth/me", headers=login("owner@holding.sa"))

    assert response.status_code == 200
    body = response.json()
    assert body["role_code"] == "holding_owner"
    assert "dashboard.holding" in body["permissions"]


@pytest.mark.parametrize("path", ["/api/v1/auth/me", "/api/v1/companies", "/api/v1/dashboard/holding"])
def test_protected_endpoints_require_a_token(client, path):
    assert client.get(path).status_code == 401


def test_malformed_token_is_rejected(client):
    response = client.get("/api/v1/companies", headers={"Authorization": "Bearer not.a.token"})

    assert response.status_code == 401


def test_token_of_deleted_user_is_rejected(client, db, make_user):
    user = make_user("owner@holding.sa", "holding_owner")
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}

    db.query(User).filter(User.id == user.id).delete()
    db.commit()

    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_logout_is_recorded_and_returns_no_body(client, db, make_user, login):
    from backend.db.models.audit_actions import AuditAction
    from backend.db.models import AuditLog

    user = make_user("owner@holding.sa", "holding_owner")
    headers = login("owner@holding.sa")

    response = client.post("/api/v1/auth/logout", headers=headers)

    assert response.status_code == 204
    assert response.content == b""
    logged = (
        db.query(AuditLog)
        .filter(AuditLog.actor_user_id == user.id, AuditLog.action == AuditAction.LOGOUT)
        .count()
    )
    assert logged == 1


def test_login_is_audited(client, db, make_user):
    from backend.db.models.audit_actions import AuditAction
    from backend.db.models import AuditLog

    user = make_user("owner@holding.sa", "holding_owner")
    client.post(LOGIN, json={"email": "owner@holding.sa", "password": "TestPass!2027"})

    actions = [row.action for row in db.query(AuditLog).filter(AuditLog.actor_user_id == user.id)]
    assert AuditAction.LOGIN in actions


# --------------------------------------------------------------------------
# self-service password change (D11 account access)
# --------------------------------------------------------------------------
CHANGE = "/api/v1/auth/change-password"


def test_change_password_rotates_the_credential(client, login, make_user):
    make_user("owner@holding.sa", "holding_owner")
    headers = login("owner@holding.sa")

    response = client.post(
        CHANGE,
        headers=headers,
        json={"current_password": "TestPass!2027", "new_password": "NewSecret!2028"},
    )
    assert response.status_code == 204

    old = client.post(LOGIN, json={"email": "owner@holding.sa", "password": "TestPass!2027"})
    new = client.post(LOGIN, json={"email": "owner@holding.sa", "password": "NewSecret!2028"})
    assert old.status_code == 401
    assert new.status_code == 200


def test_change_password_requires_the_current_password(client, login, make_user):
    make_user("owner@holding.sa", "holding_owner")
    headers = login("owner@holding.sa")

    response = client.post(
        CHANGE,
        headers=headers,
        json={"current_password": "wrong-password", "new_password": "NewSecret!2028"},
    )
    assert response.status_code == 401
    # The credential is untouched.
    assert client.post(LOGIN, json={"email": "owner@holding.sa", "password": "TestPass!2027"}).status_code == 200


def test_change_password_rejects_short_and_identical(client, login, make_user):
    make_user("owner@holding.sa", "holding_owner")
    headers = login("owner@holding.sa")

    short = client.post(
        CHANGE,
        headers=headers,
        json={"current_password": "TestPass!2027", "new_password": "short"},
    )
    assert short.status_code == 422  # schema minimum

    same = client.post(
        CHANGE,
        headers=headers,
        json={"current_password": "TestPass!2027", "new_password": "TestPass!2027"},
    )
    assert same.status_code == 422


def test_change_password_requires_authentication(client):
    response = client.post(
        CHANGE,
        json={"current_password": "x", "new_password": "NewSecret!2028"},
    )
    assert response.status_code == 401


def test_change_password_is_audited(client, db, login, make_user):
    from backend.db.models.audit_actions import AuditAction
    from backend.db.models import AuditLog

    user = make_user("owner@holding.sa", "holding_owner")
    headers = login("owner@holding.sa")
    client.post(
        CHANGE,
        headers=headers,
        json={"current_password": "TestPass!2027", "new_password": "NewSecret!2028"},
    )

    assert (
        db.query(AuditLog)
        .filter(
            AuditLog.actor_user_id == user.id,
            AuditLog.action == AuditAction.PASSWORD_CHANGED,
        )
        .count()
        == 1
    )


def test_admin_can_set_a_temporary_password(client, db, auth, make_user):
    from backend.db.models.audit_actions import AuditAction
    from backend.db.models import AuditLog

    owner = make_user("owner@holding.sa", "holding_owner")
    target = make_user("manager@holding.sa", "company_manager")

    response = client.post(
        f"/api/v1/users/{target.id}/password",
        headers=auth(owner),
        json={"new_password": "TempReset!2027"},
    )
    assert response.status_code == 204

    assert client.post(LOGIN, json={"email": "manager@holding.sa", "password": "TempReset!2027"}).status_code == 200
    assert (
        db.query(AuditLog)
        .filter(
            AuditLog.actor_user_id == owner.id,
            AuditLog.action == AuditAction.PASSWORD_RESET,
        )
        .count()
        == 1
    )


def test_set_password_requires_user_manage(client, auth, make_user):
    manager = make_user("manager@holding.sa", "company_manager")
    target = make_user("other@holding.sa", "company_manager")

    response = client.post(
        f"/api/v1/users/{target.id}/password",
        headers=auth(manager),
        json={"new_password": "TempReset!2027"},
    )
    assert response.status_code == 403


# --------------------------------------------------------------------------
# Server-side session revocation (logout + refresh rotation)
# --------------------------------------------------------------------------
def _tokens(client, email: str, password: str = "TestPass!2027") -> dict:
    response = client.post(LOGIN, json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def test_logout_revokes_the_access_token(client, make_user):
    """A logged-out access token must not reach a protected endpoint."""
    make_user("owner@holding.sa", "holding_owner")
    tokens = _tokens(client, "owner@holding.sa")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    # Same token, now revoked server-side.
    revoked = client.get("/api/v1/auth/me", headers=headers)
    assert revoked.status_code == 401
    assert revoked.json()["error"]["code"] == "unauthenticated"


def test_logout_revokes_the_refresh_token(client, make_user):
    """A logged-out refresh token must not mint a new access token."""
    make_user("owner@holding.sa", "holding_owner")
    tokens = _tokens(client, "owner@holding.sa")
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204

    response = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert response.status_code == 401


def test_refresh_rotates_the_refresh_token(client, make_user):
    """Each refresh returns a new refresh token; the new one keeps working."""
    make_user("owner@holding.sa", "holding_owner")
    tokens = _tokens(client, "owner@holding.sa")

    rotated = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert rotated.status_code == 200
    new_refresh = rotated.json()["refresh_token"]
    assert new_refresh and new_refresh != tokens["refresh_token"]

    # The rotated token is itself valid for the next exchange.
    again = client.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh})
    assert again.status_code == 200


def test_change_password_revokes_previous_access_token(client, login, make_user):
    """A stolen token must stop working once the password is changed."""
    make_user("owner@holding.sa", "holding_owner")
    headers = login("owner@holding.sa")

    changed = client.post(
        CHANGE,
        headers=headers,
        json={"current_password": "TestPass!2027", "new_password": "NewSecret!2028"},
    )
    assert changed.status_code == 204

    # The token minted before the change is now refused.
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    # The new credential mints a working token.
    fresh = _tokens(client, "owner@holding.sa", "NewSecret!2028")
    assert (
        client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {fresh['access_token']}"},
        ).status_code
        == 200
    )


def test_admin_reset_revokes_the_targets_sessions(client, auth, make_user):
    """An administrator password reset cuts off the target's live session."""
    owner = make_user("owner@holding.sa", "holding_owner")
    target = make_user("manager@holding.sa", "company_manager")
    target_tokens = _tokens(client, "manager@holding.sa")
    target_headers = {"Authorization": f"Bearer {target_tokens['access_token']}"}

    assert client.get("/api/v1/auth/me", headers=target_headers).status_code == 200
    reset = client.post(
        f"/api/v1/users/{target.id}/password",
        headers=auth(owner),
        json={"new_password": "TempReset!2027"},
    )
    assert reset.status_code == 204

    assert client.get("/api/v1/auth/me", headers=target_headers).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": target_tokens["refresh_token"]}
        ).status_code
        == 401
    )


def test_legacy_token_without_tv_is_rejected_once_revoked(client, db, make_user):
    """Tokens minted before ``tv`` existed keep working until a revocation."""
    user = make_user("owner@holding.sa", "holding_owner")
    # A token with no ``tv`` claim (as minted before this feature).
    legacy = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {legacy}"}

    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

    user.token_version = 1
    db.add(user)
    db.commit()

    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
