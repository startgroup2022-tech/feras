"""Phase 11 tests: the Website Management (CMS).

Covers the guarantees that make the CMS safe to bolt onto a live site:

* authorization: every write requires a ``website.*`` permission, and a role
  without it is refused (403) -- RBAC is enforced, not decorative,
* the public read boundary: only ``public`` media is streamed anonymously, and
  only ``published`` pages are rendered,
* additive rendering: an empty CMS leaves the V2 site byte-for-byte equivalent,
  and published CMS content appears on top,
* sanitization: menu URLs reject dangerous schemes; user copy is escaped,
* maintenance mode returns 503 without exposing internal detail,
* revision history records content changes.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from backend.core.config import settings
from backend.db.models.enums import ContentStatus
from backend.main import create_app
from backend.website import pages


@pytest.fixture
def public_client(monkeypatch):
    """A client for the production layout: the website owns the root."""
    monkeypatch.setattr(settings, "SPLIT_PUBLIC_SITE", True)
    with TestClient(create_app()) as client:
        yield client


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _create_page(client, auth, user, **overrides):
    payload = {
        "route_key": "home",
        "title_ar": "عنوان تجريبي",
        "title_en": "Test title",
        "content_ar": "محتوى تجريبي",
        "content_en": "Test content",
        "sections": [
            {
                "key": "intro",
                "kind": "text",
                "heading_ar": "قسم",
                "heading_en": "Section",
                "body_ar": "نص",
                "body_en": "Body",
                "display_order": 0,
                "is_visible": True,
            }
        ],
    }
    payload.update(overrides)
    return client.post("/api/v1/website/pages", json=payload, headers=auth(user))


# --------------------------------------------------------------------------
# authorization
# --------------------------------------------------------------------------
def test_marketing_can_read_but_employee_cannot_write(client, auth, make_user):
    marketing = make_user("mkt@corp.sa", "marketing")
    employee = make_user("emp@corp.sa", "employee")

    assert client.get("/api/v1/website/overview", headers=auth(marketing)).status_code == 200
    # An employee has no website.* permission: reading the CMS is refused.
    assert client.get("/api/v1/website/overview", headers=auth(employee)).status_code == 403
    assert _create_page(client, auth, employee).status_code == 403


def test_marketing_cannot_write_settings_but_owner_can(client, auth, make_user):
    marketing = make_user("mkt@corp.sa", "marketing")
    owner = make_user("owner@corp.sa", "holding_owner")

    refused = client.patch(
        "/api/v1/website/settings", json={"site_name_en": "Nope"}, headers=auth(marketing)
    )
    assert refused.status_code == 403

    ok = client.patch(
        "/api/v1/website/settings", json={"site_name_en": "Safir"}, headers=auth(owner)
    )
    assert ok.status_code == 200
    assert ok.json()["site_name_en"] == "Safir"


def test_marketing_can_create_draft_but_cannot_publish(client, auth, make_user):
    marketing = make_user("mkt@corp.sa", "marketing")
    created = _create_page(client, auth, marketing)
    assert created.status_code == 201
    page_id = created.json()["id"]
    assert created.json()["status"] == ContentStatus.DRAFT.value

    publish = client.post(f"/api/v1/website/pages/{page_id}/publish", headers=auth(marketing))
    assert publish.status_code == 403


# --------------------------------------------------------------------------
# CRUD + revisions
# --------------------------------------------------------------------------
def test_page_create_update_publish_records_revisions(client, auth, make_user, db):
    owner = make_user("owner@corp.sa", "holding_owner")
    page_id = _create_page(client, auth, owner).json()["id"]

    updated = client.patch(
        f"/api/v1/website/pages/{page_id}",
        json={"title_en": "Updated"},
        headers=auth(owner),
    )
    assert updated.status_code == 200
    assert updated.json()["title_en"] == "Updated"

    published = client.post(
        f"/api/v1/website/pages/{page_id}/publish", headers=auth(owner)
    )
    assert published.status_code == 200
    assert published.json()["status"] == ContentStatus.PUBLISHED.value

    revisions = client.get("/api/v1/website/revisions", headers=auth(owner)).json()
    actions = {r["action"] for r in revisions}
    assert {"create", "update", "published"} <= actions


def test_duplicate_route_key_is_rejected(client, auth, make_user):
    owner = make_user("owner@corp.sa", "holding_owner")
    assert _create_page(client, auth, owner).status_code == 201
    assert _create_page(client, auth, owner).status_code == 422


# --------------------------------------------------------------------------
# menu URL sanitization
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "url",
    ["javascript:alert(1)", "data:text/html;base64,PHNjcmlwdD4=", "vbscript:msgbox(1)", "//evil.example"],
)
def test_menu_rejects_dangerous_url_schemes(client, auth, make_user, url):
    owner = make_user("owner@corp.sa", "holding_owner")
    response = client.post(
        "/api/v1/website/menus",
        json={"location": "header", "label_en": "X", "url": url, "display_order": 0},
        headers=auth(owner),
    )
    assert response.status_code == 422


def test_menu_accepts_internal_and_https_paths(client, auth, make_user):
    owner = make_user("owner@corp.sa", "holding_owner")
    for url in ("/en/services", "https://sup-edu.com/about"):
        response = client.post(
            "/api/v1/website/menus",
            json={"location": "header", "label_en": "X", "url": url, "display_order": 0},
            headers=auth(owner),
        )
        assert response.status_code == 201, url


# --------------------------------------------------------------------------
# media visibility boundary
# --------------------------------------------------------------------------
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00"
    b"\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _upload(client, auth, user, visibility="public"):
    return client.post(
        "/api/v1/website/media",
        files={"file": ("logo.png", io.BytesIO(PNG), "image/png")},
        data={"visibility": visibility},
        headers=auth(user),
    )


def test_private_media_is_not_streamed_publicly(client, auth, make_user, public_client):
    owner = make_user("owner@corp.sa", "holding_owner")
    upload = _upload(client, auth, owner, visibility="private")
    assert upload.status_code == 201
    media_id = upload.json()["id"]

    # Authenticated owner can fetch the raw private asset...
    assert client.get(f"/api/v1/website/media/{media_id}/file", headers=auth(owner)).status_code == 200
    # ...but the anonymous public endpoint 404s it.
    assert public_client.get(f"/api/v1/public/website/media/{media_id}").status_code == 404


def test_public_media_is_streamed_publicly(client, auth, make_user, public_client):
    owner = make_user("owner@corp.sa", "holding_owner")
    upload = _upload(client, auth, owner, visibility="public")
    media_id = upload.json()["id"]
    assert public_client.get(f"/api/v1/public/website/media/{media_id}").status_code == 200


# --------------------------------------------------------------------------
# additive rendering
# --------------------------------------------------------------------------
def test_draft_page_is_not_visible_on_the_public_site(client, auth, make_user, public_client):
    owner = make_user("owner@corp.sa", "holding_owner")
    _create_page(client, auth, owner, title_en="DRAFTMARKER")
    html = public_client.get("/").text
    assert "DRAFTMARKER" not in html


def test_published_content_is_added_to_the_public_site(client, auth, make_user, public_client):
    owner = make_user("owner@corp.sa", "holding_owner")
    page_id = _create_page(client, auth, owner, title_en="PUBLISHEDMARKER").json()["id"]
    client.post(f"/api/v1/website/pages/{page_id}/publish", headers=auth(owner))

    html = public_client.get("/").text
    # The built-in V2 content is still present...
    assert "Why Safir Holding" in html
    # ...and the published CMS block is appended.
    assert "PUBLISHEDMARKER" in html


def test_published_cms_title_cannot_inject_markup(client, auth, make_user, public_client):
    owner = make_user("owner@corp.sa", "holding_owner")
    page_id = _create_page(
        client, auth, owner, title_en="<script>alert(1)</script>"
    ).json()["id"]
    client.post(f"/api/v1/website/pages/{page_id}/publish", headers=auth(owner))
    html = public_client.get("/").text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


# --------------------------------------------------------------------------
# maintenance mode
# --------------------------------------------------------------------------
def test_maintenance_mode_returns_503(client, auth, make_user, public_client):
    owner = make_user("owner@corp.sa", "holding_owner")
    client.patch(
        "/api/v1/website/settings",
        json={"maintenance_mode": True, "maintenance_message_en": "Back soon"},
        headers=auth(owner),
    )
    response = public_client.get("/en/about")
    assert response.status_code == 503
    assert "Back soon" in response.text
    assert response.headers.get("Retry-After") == "3600"

    # The Arabic site shows the Arabic maintenance message.
    arabic = public_client.get("/ar")
    assert arabic.status_code == 503
    assert "نعمل حاليًا" in arabic.text

    # The API is not gated by maintenance mode.
    assert client.get("/api/v1/website/overview", headers=auth(owner)).status_code == 200


# --------------------------------------------------------------------------
# companies seed
# --------------------------------------------------------------------------
def test_seed_companies_is_idempotent(client, auth, make_user):
    owner = make_user("owner@corp.sa", "holding_owner")
    first = client.post("/api/v1/website/companies/seed", headers=auth(owner))
    assert first.status_code == 200
    assert first.json()["created"] == 9
    second = client.post("/api/v1/website/companies/seed", headers=auth(owner))
    assert second.json()["created"] == 0
    listed = client.get("/api/v1/website/companies", headers=auth(owner)).json()
    assert len(listed) == 9
