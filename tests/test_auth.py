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
