"""Website branding: the configurable Holding logo.

The logo is uploaded from the administration area and rendered by the public
website header. These tests pin the security and behaviour properties:

* only ``group.manage`` may change it, and every change is audited;
* only raster images are accepted, the size is capped, and the client filename
  never reaches the filesystem;
* a missing asset degrades to the built-in fallback instead of a broken image;
* the public endpoints expose only the versioned URL, never the storage key.
"""

from __future__ import annotations

import base64
import uuid

import pytest

from backend.core import branding_storage
from backend.core.config import settings
from backend.db.models.ai import AuditLog

ADMIN = "/api/v1/admin"
PUBLIC = "/api/v1/public"

# A 1x1 transparent PNG, enough to satisfy the raster allow-list.
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


@pytest.fixture
def branding_dir(tmp_path, monkeypatch):
    """Redirect the branding root into a per-test directory."""
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    root = branding_storage.branding_root()
    yield root


@pytest.fixture
def admin(db, make_user):
    return make_user("branding.admin@corp.sa", "super_admin")


@pytest.fixture
def manager(db, make_company, make_user):
    company = make_company("BRANDCO", "شركة الشعار")
    return make_user("branding.mgr@corp.sa", "company_manager", [company])


def _upload(client, auth, user, content=PNG_BYTES, filename="logo.png",
            content_type="image/png"):
    return client.post(
        f"{ADMIN}/branding/logo",
        headers=auth(user),
        files={"file": (filename, content, content_type)},
    )


# --------------------------------------------------------------------------
# authorization
# --------------------------------------------------------------------------
def test_upload_requires_group_manage(client, auth, manager, branding_dir):
    response = _upload(client, auth, manager)
    assert response.status_code == 403


def test_remove_requires_group_manage(client, auth, manager, branding_dir):
    response = client.delete(f"{ADMIN}/branding/logo", headers=auth(manager))
    assert response.status_code == 403


def test_upload_requires_authentication(client, branding_dir):
    response = client.post(
        f"{ADMIN}/branding/logo",
        files={"file": ("logo.png", PNG_BYTES, "image/png")},
    )
    assert response.status_code in (401, 403)


# --------------------------------------------------------------------------
# happy path
# --------------------------------------------------------------------------
def test_upload_stores_and_returns_versioned_url(client, auth, admin, branding_dir):
    response = _upload(client, auth, admin)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["logo_url"].startswith(f"{PUBLIC}/branding/logo?v=")
    assert body["logo_updated_at"] is not None


def test_upload_audits_the_change(client, auth, admin, branding_dir, db):
    _upload(client, auth, admin)
    assert "branding.logo_updated" in [row.action for row in db.query(AuditLog).all()]


def test_uploaded_file_is_served_publicly(client, auth, admin, branding_dir):
    _upload(client, auth, admin)
    response = client.get(f"{PUBLIC}/branding/logo")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert response.content == PNG_BYTES


def test_public_branding_payload_hides_the_storage_key(client, auth, admin, branding_dir):
    _upload(client, auth, admin)
    body = client.get(f"{PUBLIC}/branding").json()
    assert "storage" not in body
    assert "logo_storage_key" not in body
    assert set(body) == {"logo_url", "logo_updated_at"}


def test_client_filename_never_reaches_the_filesystem(client, auth, admin, branding_dir):
    _upload(client, auth, admin, filename="../../etc/passwd.png")
    stored = list(branding_dir.iterdir())
    assert len(stored) == 1
    # The stored name is an opaque UUID plus a server-derived extension.
    assert stored[0].name.endswith(".png")
    assert "passwd" not in stored[0].name
    assert "/" not in stored[0].name


def test_reupload_replaces_the_previous_file(client, auth, admin, branding_dir):
    _upload(client, auth, admin)
    first = {p.name for p in branding_dir.iterdir()}
    _upload(client, auth, admin)
    remaining = {p.name for p in branding_dir.iterdir()}
    assert len(remaining) == 1
    assert first != remaining


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "content_type",
    ["text/plain", "image/svg+xml", "application/pdf", "image/bmp", ""],
)
def test_non_raster_types_are_rejected(client, auth, admin, branding_dir, content_type):
    response = _upload(client, auth, admin, content_type=content_type)
    assert response.status_code == 422


def test_oversized_upload_is_rejected(client, auth, admin, branding_dir):
    big = b"x" * (branding_storage.MAX_BRANDING_BYTES + 1)
    response = _upload(client, auth, admin, content=big)
    assert response.status_code == 422


def test_empty_upload_is_rejected(client, auth, admin, branding_dir):
    response = _upload(client, auth, admin, content=b"")
    assert response.status_code == 422


# --------------------------------------------------------------------------
# removal and graceful degradation
# --------------------------------------------------------------------------
def test_remove_clears_the_logo_and_audits(client, auth, admin, branding_dir, db):
    _upload(client, auth, admin)
    response = client.delete(f"{ADMIN}/branding/logo", headers=auth(admin))
    assert response.status_code == 200
    assert response.json()["logo_url"] is None
    assert "branding.logo_removed" in [row.action for row in db.query(AuditLog).all()]


def test_remove_without_a_logo_is_a_validation_error(client, auth, admin, branding_dir):
    response = client.delete(f"{ADMIN}/branding/logo", headers=auth(admin))
    assert response.status_code == 422


def test_missing_asset_degrades_to_the_fallback(client, auth, admin, branding_dir):
    _upload(client, auth, admin)
    # Simulate a lost file behind a still-set key.
    for path in branding_dir.iterdir():
        path.unlink()
    assert client.get(f"{PUBLIC}/branding").json()["logo_url"] is None
    assert client.get(f"{PUBLIC}/branding/logo").status_code == 404


def test_no_logo_configured_returns_404(client, branding_dir):
    assert client.get(f"{PUBLIC}/branding").json()["logo_url"] is None
    assert client.get(f"{PUBLIC}/branding/logo").status_code == 404


# --------------------------------------------------------------------------
# storage guards
# --------------------------------------------------------------------------
def test_resolve_refuses_traversal(branding_dir):
    from backend.core.errors import ValidationError

    with pytest.raises(ValidationError):
        branding_storage.resolve_branding_path("../../etc/passwd")


def test_store_rejects_a_bad_extension(branding_dir):
    # The extension is always server-derived, but the guard must still refuse
    # a key that would escape the root.
    from backend.core.errors import ValidationError

    with pytest.raises(ValidationError):
        branding_storage.store_branding_bytes(data=b"x", extension="/../../evil")


def test_stored_keys_are_unique(branding_dir):
    a = branding_storage.store_branding_bytes(data=b"a", extension=".png")
    b = branding_storage.store_branding_bytes(data=b"b", extension=".png")
    assert a != b
    assert uuid.UUID(a.split(".")[0])  # opaque, not client-derived
