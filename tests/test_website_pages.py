"""Phase 10 tests: the server-rendered public website.

Covers the guarantees that make the site a real SEO asset rather than a
client-side shell:

* every page is a complete document with a unique title, description, canonical
  and hreflang pair,
* the sitemap and robots.txt are consistent with the route table,
* the two languages are separate URLs and the Arabic pages are RTL,
* the platform and the API are never indexable,
* user-supplied values cannot inject markup (a title containing ``<script>``
  stays inert),
* the site does not fabricate content.
"""

from __future__ import annotations

import base64
import re

import pytest
from fastapi.testclient import TestClient

from backend.core.config import settings
from backend.main import create_app
from backend.website import content as C
from backend.website import pages, renderer, seo


@pytest.fixture
def public_client(monkeypatch):
    """A client for the production layout: the website owns the root.

    In development (``SPLIT_PUBLIC_SITE=false``) the platform keeps the root so
    local workflows are unchanged; production splits the two. The public site
    must be exercised in the split layout, so this fixture builds an app with
    the split enabled -- exactly what is deployed.
    """
    monkeypatch.setattr(settings, "SPLIT_PUBLIC_SITE", True)
    with TestClient(create_app()) as client:
        yield client


# --------------------------------------------------------------------------
# route table
# --------------------------------------------------------------------------
def test_every_top_level_page_resolves_in_both_languages():
    for key, paths in C.PAGE_PATHS.items():
        for lang in ("en", "ar"):
            meta = pages.resolve_route(paths[lang])
            assert meta is not None, f"{key}/{lang} did not resolve"
            assert meta.route == key
            assert meta.lang == lang


def test_every_market_service_page_resolves_in_both_languages():
    for market, slug in C.all_market_service_pages():
        for lang in ("en", "ar"):
            path = C.market_service_path(market, slug, lang)
            meta = pages.resolve_route(path)
            assert meta is not None, f"{path} did not resolve"
            assert meta.lang == lang


def test_unknown_path_resolves_to_none():
    assert pages.resolve_route("/definitely-not-a-page") is None
    assert pages.resolve_route("/api/v1/companies") is None


def test_home_paths_are_language_specific():
    assert pages.resolve_route("/").lang == "en"
    assert pages.resolve_route("/ar").lang == "ar"


# --------------------------------------------------------------------------
# metadata
# --------------------------------------------------------------------------
def test_each_page_has_a_unique_title_and_description():
    titles = {}
    for key, paths in C.PAGE_PATHS.items():
        for lang in ("en", "ar"):
            meta = pages.resolve_route(paths[lang])
            assert meta.title.strip(), f"{key}/{lang} has no title"
            assert meta.description.strip(), f"{key}/{lang} has no description"
            titles.setdefault(meta.title, []).append(paths[lang])
    duplicates = {t: p for t, p in titles.items() if len(p) > 1}
    assert not duplicates, f"duplicate titles: {duplicates}"


def test_each_page_declares_both_language_alternates():
    for key, paths in C.PAGE_PATHS.items():
        for lang in ("en", "ar"):
            meta = pages.resolve_route(paths[lang])
            assert meta.alternates["en"] == paths["en"]
            assert meta.alternates["ar"] == paths["ar"]


def test_meta_tags_include_canonical_and_hreflang():
    meta = pages.resolve_route("/bahrain/company-formation")
    html = seo.render_meta_tags(meta)
    assert '<link rel="canonical"' in html
    assert 'hreflang="en"' in html
    assert 'hreflang="ar"' in html
    assert 'hreflang="x-default"' in html
    assert "<title>" in html
    assert 'name="description"' in html


def test_title_and_description_are_html_escaped():
    # A value with markup must not break out of the attribute or element.
    meta = pages.resolve_route("/")
    meta.title = 'Test <script>alert("x")</script>'
    meta.description = 'A "quoted" & <b>bold</b> description'
    html = seo.render_meta_tags(meta)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&quot;" in html


def test_jsonld_is_safe_and_factual():
    meta = pages.resolve_route("/ar")
    html = renderer.render(meta)
    assert 'application/ld+json' in html
    # Only the Organization + BreadcrumbList nodes; no fabricated rating/price.
    assert '"@type": "Organization"' in html
    assert "aggregateRating" not in html
    assert '"@type": "Review"' not in html


# --------------------------------------------------------------------------
# rendered documents
# --------------------------------------------------------------------------
@pytest.mark.parametrize("path", ["/", "/ar", "/services", "/ar/خدمات-الأعمال",
                                  "/bahrain/company-formation",
                                  "/ar/البحرين/تأسيس-شركة", "/list-your-business",
                                  "/group-companies", "/about", "/contact"])
def test_page_renders_a_complete_document(public_client, path):
    response = public_client.get(path)
    assert response.status_code == 200, response.text
    html = response.text
    assert html.startswith("<!DOCTYPE html>")
    assert "</html>" in html
    assert '<html lang="' in html
    assert '<main id="main"' in html


def test_arabic_pages_are_rtl_and_english_pages_are_ltr(public_client):
    arabic = public_client.get("/ar").text
    english = public_client.get("/").text
    assert 'dir="rtl"' in arabic
    assert 'lang="ar"' in arabic
    assert 'dir="ltr"' in english
    assert 'lang="en"' in english


def test_language_switch_links_to_the_mirror_page(public_client):
    html = public_client.get("/bahrain/company-formation").text
    # The switch points at the Arabic mirror of the same page.
    assert 'hreflang="ar"' in html
    assert "/ar/" in html


def test_unknown_page_returns_404_html(public_client):
    response = public_client.get("/no-such-page")
    assert response.status_code == 404
    assert "text/html" in response.headers["content-type"]
    # The 404 page is noindex.
    assert "noindex" in response.text


def test_noscript_fallback_is_present(public_client):
    assert "<noscript>" in public_client.get("/contact").text


# --------------------------------------------------------------------------
# header shell
# --------------------------------------------------------------------------
def test_header_has_a_single_brand_and_a_language_switch(public_client):
    html = public_client.get("/").text
    assert 'class="brand"' in html
    assert html.count('class="header-actions"') == 1
    assert 'class="lang-switch"' in html
    # The language switch offers both languages explicitly.
    assert 'class="lang-opt' in html
    assert ">العربية</a>" in html
    assert ">English</a>" in html


def test_header_uses_the_fallback_mark_when_no_logo_is_set(public_client):
    html = public_client.get("/").text
    assert "data-brand-fallback" in html
    assert "data-brand-logo" not in html


def test_header_renders_the_uploaded_logo(client, auth, make_user, tmp_path, monkeypatch):
    from backend.core.config import settings

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "SPLIT_PUBLIC_SITE", True)
    admin = make_user("header.admin@corp.sa", "super_admin")
    logo = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    )
    with TestClient(create_app()) as app_client:
        upload = app_client.post(
            "/api/v1/admin/branding/logo",
            headers=auth(admin),
            files={"file": ("logo.png", logo, "image/png")},
        )
        assert upload.status_code == 201, upload.text
        html = app_client.get("/").text
    assert "data-brand-logo" in html
    assert "data-brand-fallback" not in html
    assert "/api/v1/public/branding/logo?v=" in html


# --------------------------------------------------------------------------
# SEO files
# --------------------------------------------------------------------------
def test_robots_disallows_api_and_platform(client):
    body = client.get("/robots.txt").text
    assert "Disallow: /api/" in body
    assert "Disallow: /platform" in body


def test_sitemap_lists_every_page_in_both_languages(client):
    body = client.get("/sitemap.xml").text
    assert body.startswith("<?xml")
    # One <url> per language per page.
    expected = (len(C.PAGE_PATHS) + len(C.all_market_service_pages())) * 2
    assert body.count("<loc>") == expected
    assert "hreflang=\"ar\"" in body
    assert "hreflang=\"en\"" in body


def test_sitemap_is_valid_xml(client):
    import xml.etree.ElementTree as ET

    body = client.get("/sitemap.xml").text
    # Raises if the document is not well-formed.
    ET.fromstring(body)


def test_absolute_urls_are_used_when_a_base_url_is_configured(monkeypatch):
    from backend.core.config import settings

    monkeypatch.setattr(settings, "WEBSITE_BASE_URL", "https://safir.example")
    body = seo.sitemap_xml()
    assert "https://safir.example/" in body
    assert "https://safir.example/ar" in body


# --------------------------------------------------------------------------
# indexability of the internal surfaces
# --------------------------------------------------------------------------
def test_platform_is_marked_noindex(client):
    response = client.get("/platform/")
    assert response.status_code == 200
    assert response.headers.get("x-robots-tag") == "noindex, nofollow"


def test_api_is_marked_noindex(client):
    response = client.get("/api/v1")
    assert response.headers.get("x-robots-tag") == "noindex, nofollow"


def test_platform_shell_is_served_under_the_platform_path(client):
    html = client.get("/platform/").text
    # The unchanged internal application is served, not the website.
    assert "safir" in html.lower()


# --------------------------------------------------------------------------
# content integrity
# --------------------------------------------------------------------------
def test_group_company_entries_are_flagged_for_verification():
    # Nothing invented: every listed entity carries its verification state.
    for company in C.GROUP_COMPANIES:
        assert "verified" in company
        assert company["name_ar"] and company["name_en"]


def test_every_service_has_a_market_specific_page():
    for market, slug in C.all_market_service_pages():
        assert market in C.MARKETS
        assert slug in C.SERVICES


def test_no_placeholder_or_demo_markers_in_rendered_pages(public_client):
    forbidden = re.compile(r"lorem ipsum|placeholder text|demo data|TODO", re.I)
    for path in ("/", "/ar", "/services", "/about", "/contact"):
        assert not forbidden.search(public_client.get(path).text), path
