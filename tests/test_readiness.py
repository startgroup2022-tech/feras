"""Readiness endpoint: dependency checks and information-leak safety.

``/health`` is a liveness probe and must stay trivial. ``/ready`` additionally
verifies database connectivity and upload-directory writability, and must never
leak credentials, filesystem paths or exception detail.
"""

from __future__ import annotations

import json

import pytest

from backend.core.config import settings


# --------------------------------------------------------------------------
# liveness
# --------------------------------------------------------------------------
def test_health_is_liveness_only(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "safir-holding-2027"}


# --------------------------------------------------------------------------
# readiness - happy path
# --------------------------------------------------------------------------
def test_ready_reports_healthy_dependencies(client):
    response = client.get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["database"] is True
    assert body["uploads_writable"] is True


def test_ready_does_not_leak_configuration(client):
    """The body must be coarse booleans only -- no URLs, paths or secrets."""
    raw = json.dumps(client.get("/ready").json())

    for forbidden in ("sqlite", "postgres", "password", "secret", "://", "/tmp", "/var"):
        assert forbidden.lower() not in raw.lower()
    assert set(client.get("/ready").json()) == {"status", "database", "uploads_writable"}


# --------------------------------------------------------------------------
# readiness - failure paths
# --------------------------------------------------------------------------
def test_ready_returns_503_when_database_is_down(client, monkeypatch):
    def _boom():
        raise RuntimeError("simulated database outage with secret detail")

    monkeypatch.setattr("backend.main.SessionLocal", _boom)

    response = client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["database"] is False
    # The internal error text must not surface in the response.
    assert "secret detail" not in json.dumps(body)


def test_ready_returns_503_when_uploads_are_not_writable(client, monkeypatch):
    # A path that cannot be created because its parent is a file.
    monkeypatch.setattr(settings, "UPLOAD_DIR", "/dev/null/not-a-dir", raising=False)

    response = client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["uploads_writable"] is False
    assert body["status"] == "not_ready"


@pytest.mark.parametrize("probe", ["/health", "/ready"])
def test_probes_never_require_authentication(client, probe):
    """Probes must be reachable without a token (load balancers have none)."""
    assert client.get(probe).status_code in (200, 503)
