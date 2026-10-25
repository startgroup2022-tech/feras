"""Phase 9: external integrations.

The security properties get the most attention: SSRF rejection before any
socket is opened, a signing secret that is returned once and never again, and
company-scoped subscriptions that never receive another company's events.
"""

from __future__ import annotations

import socket

import pytest

from backend.core.config import settings
from backend.integrations.webhooks import (
    UnsafeUrlError,
    build_signature,
    validate_outbound_url,
)
from backend.services import integration_service

BASE = "/api/v1/integrations"


@pytest.fixture(autouse=True)
def _resolvable_public_host(monkeypatch):
    """Give the test host a stable public address.

    The SSRF check resolves every hostname; the sandbox has no DNS, so we answer
    for the one name the tests use and delegate everything else (numeric
    addresses such as 127.0.0.1 resolve locally and must stay real).
    """
    real = socket.getaddrinfo

    def _fake(host, port, *args, **kwargs):
        if host in ("hooks.example.com", "example.com"):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 443))]
        return real(host, port, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", _fake)


# --------------------------------------------------------------------------
# SSRF protection
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/hook",
        "http://127.0.0.1/hook",
        "http://[::1]/hook",
        "http://10.0.0.5/hook",
        "http://192.168.1.10/hook",
        "http://169.254.169.254/latest/meta-data",
        "ftp://example.com/hook",
        "https://user:pass@example.com/hook",
    ],
)
def test_unsafe_urls_are_rejected(url):
    with pytest.raises(UnsafeUrlError):
        validate_outbound_url(url)


def test_signature_is_deterministic():
    body = b'{"a":1}'
    one = build_signature("secret", body, timestamp="123")
    two = build_signature("secret", body, timestamp="123")
    assert one == two
    assert one != build_signature("other", body, timestamp="123")


# --------------------------------------------------------------------------
# endpoint administration
# --------------------------------------------------------------------------
def _create(client, auth, user, **overrides):
    payload = {
        "name": "CRM Sync",
        "url": "https://hooks.example.com/safir",
        "subscribed_events": ["report.submitted"],
        "scope": "holding",
    }
    payload.update(overrides)
    return client.post(BASE, headers=auth(user), json=payload)


def test_create_returns_the_secret_once(client, world, auth):
    response = _create(client, auth, world["owner"])
    assert response.status_code == 201
    body = response.json()
    assert body["signing_secret"]
    assert body["endpoint"]["id"]

    listed = client.get(BASE, headers=auth(world["owner"])).json()
    assert len(listed) == 1
    # The secret must not appear anywhere in the read path.
    assert "signing_secret" not in listed[0]


def test_create_rejects_a_private_url(client, world, auth):
    response = _create(client, auth, world["owner"], url="http://127.0.0.1/hook")
    # Rejected by the SSRF guard as an unprocessable destination.
    assert response.status_code == 422


def test_create_rejects_unknown_events(client, world, auth):
    response = _create(
        client, auth, world["owner"], subscribed_events=["not.a.real.event"]
    )
    assert response.status_code == 422


def test_rotate_secret_changes_the_value(client, world, auth):
    first = _create(client, auth, world["owner"]).json()
    endpoint_id = first["endpoint"]["id"]

    rotated = client.post(
        f"{BASE}/{endpoint_id}/rotate-secret", headers=auth(world["owner"])
    ).json()
    assert rotated["signing_secret"] != first["signing_secret"]


def test_manage_permission_is_required_to_create(client, world, auth):
    # A company manager holds integration.read (via analytics.company? no) --
    # assert the manage gate explicitly.
    denied = _create(client, auth, world["alpha_mgr"])
    assert denied.status_code == 403


def test_list_requires_read_permission(client, world, auth):
    denied = client.get(BASE, headers=auth(world["alpha_mgr"]))
    assert denied.status_code == 403
    allowed = client.get(BASE, headers=auth(world["owner"]))
    assert allowed.status_code == 200


# --------------------------------------------------------------------------
# scope matching
# --------------------------------------------------------------------------
def test_company_scoped_endpoint_does_not_receive_other_events(client, world, auth):
    created = _create(
        client,
        auth,
        world["owner"],
        scope="company",
        company_id=world["alpha"].id,
    ).json()
    endpoint_id = created["endpoint"]["id"]

    from backend.db.models.integrations import WebhookEndpoint
    from backend.db.session import SessionLocal

    with SessionLocal() as db:
        endpoint = db.get(WebhookEndpoint, endpoint_id)
        # An event for Beta must not match an Alpha-scoped endpoint.
        matched = integration_service.matching_endpoints(
            db, event_type="report.submitted", company_id=world["beta"].id
        )
        assert matched == []
        matched_alpha = integration_service.matching_endpoints(
            db, event_type="report.submitted", company_id=world["alpha"].id
        )
        assert [e.id for e in matched_alpha] == [endpoint.id]


def test_event_type_filtering(client, world, auth):
    _create(client, auth, world["owner"], subscribed_events=["report.submitted"])

    from backend.db.session import SessionLocal

    with SessionLocal() as db:
        assert (
            integration_service.matching_endpoints(
                db, event_type="support.created", company_id=world["alpha"].id
            )
            == []
        )


# --------------------------------------------------------------------------
# emission
# --------------------------------------------------------------------------
def test_emit_records_a_pending_delivery_when_disabled(client, world, auth, monkeypatch):
    monkeypatch.setattr(settings, "WEBHOOKS_ENABLED", False)
    _create(client, auth, world["owner"], subscribed_events=["report.submitted"])

    from backend.db.session import SessionLocal

    with SessionLocal() as db:
        results = integration_service.emit(
            db,
            event_type="report.submitted",
            payload={"report_id": 1},
            company_id=world["alpha"].id,
        )
        assert len(results) == 1
        assert results[0]["ok"] is False
        deliveries = integration_service.list_deliveries(db, user=world["owner"])
        assert deliveries[0]["status"] == "pending"
        assert deliveries[0]["event_type"] == "report.submitted"


def test_delivery_log_exposed_to_readers(client, world, auth, monkeypatch):
    monkeypatch.setattr(settings, "WEBHOOKS_ENABLED", False)
    _create(client, auth, world["owner"], subscribed_events=["support.created"])

    from backend.db.session import SessionLocal

    with SessionLocal() as db:
        integration_service.emit(
            db, event_type="support.created", payload={"x": 1}, company_id=world["alpha"].id
        )

    body = client.get(f"{BASE}/deliveries", headers=auth(world["owner"])).json()
    assert len(body) == 1
    assert body[0]["event_type"] == "support.created"


# --------------------------------------------------------------------------
# email
# --------------------------------------------------------------------------
def test_email_noop_provider_reports_not_sent():
    from backend.db.session import SessionLocal

    with SessionLocal() as db:
        result = integration_service.send_email(
            db, to=["x@example.com"], subject="hi", body="body"
        )
    assert result["sent"] is False
    assert result["provider"] == "none"


def test_email_without_recipients_is_a_noop():
    from backend.db.session import SessionLocal

    with SessionLocal() as db:
        result = integration_service.send_email(db, to=[], subject="s", body="b")
    assert result["sent"] is False
