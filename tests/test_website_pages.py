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
from datetime import datetime, timezone
from pathlib import Path

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


def test_header_uses_the_original_shipped_logo_when_no_cms_logo_is_set(public_client):
    """The owner-supplied logo ships as a static asset (handoff §1).

    Regression against the old behaviour: the header used to fall back to a
    generated hexagon mark when no logo was uploaded through the CMS. The
    approved design requires the *original* owner mark, never a substitute, so
    the shipped asset is the default and the generated mark is gone.
    """
    html = public_client.get("/").text
    assert "data-brand-fallback" not in html
    assert "data-brand-logo" in html
    assert "/website/assets/holding-logo.png" in html


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


def test_bare_platform_path_redirects_to_the_slashed_url(client):
    # Regression: at ``/platform`` (no trailing slash) the shell's relative
    # asset references resolved against the root and 404'd, breaking login.
    response = client.get("/platform", follow_redirects=False)
    assert response.status_code in (307, 308)
    assert response.headers["location"].endswith("/platform/")
    # And the assets must be reachable under the canonical prefix.
    assert client.get("/platform/auth.js").status_code == 200


def test_platform_shell_is_the_live_app_not_a_fixed_design_board(client):
    """The authenticated platform must load the live application.

    Regression: the platform entry point must be the real ``frontend/`` app --
    auth gate plus the live data scripts -- and not a fixed 1920x1080 design
    board scaled to fit the viewport (which reads as a static "screenshot").
    """
    html = client.get("/platform/").text
    # The live application hooks.
    assert 'id="loginForm"' in html
    assert "auth.js" in html
    assert "app.js" in html
    # The dashboard board must be the live board, populated from the API.
    assert 'id="board"' in html
    assert 'data-kpi="companies_count"' in html


def test_platform_no_longer_scales_the_board_to_fit(client):
    """The live view is fluid; only export mode uses the fixed canvas.

    Regression: the old inline script resized ``#stage`` with
    ``transform: scale(...)`` so the app looked like a baked board. The live
    entry point must not scale the stage, and must reserve the 1:1 canvas for
    ``?export=1``.
    """
    html = client.get("/platform/").text
    assert "scale(" not in html.replace(" ", "")
    assert "export" in html
    # The fixed canvas dimensions are preserved for export mode only.
    css = client.get("/platform/styles.css").text
    assert "--stage-w:1920px" in css
    assert "--stage-h:1080px" in css
    assert "body.export .stage" in css


def test_platform_header_keeps_every_control_reachable_on_phones(client):
    """The platform header must not overflow or clip a control on small screens.

    Regression: the action cluster (language, search, notifications, messages,
    profile, sign-out) was wider than a phone viewport, so at <=480px
    ``#logoutBtn`` was pushed past the right edge and became unreachable. The
    header must collapse the profile text and the sign-out label so every
    control stays on screen without horizontal overflow, in both directions.
    """
    css = client.get("/platform/styles.css").text
    # A <=480px reflow exists and collapses the wide header pieces.
    assert "@media (max-width:480px)" in css
    block = css.split("@media (max-width:480px)", 1)[1]
    assert ".p-meta{display:none;}" in block
    assert ".logout-btn{padding:8px;}" in block
    assert ".logout-btn span{display:none;}" in block
    # The controls themselves are still present in the markup (only the
    # decorative label is hidden, so Sign out stays operable via its icon/title).
    html = client.get("/platform/").text
    for control in ("id=\"logoutBtn\"", "id=\"searchBtn\"", "id=\"notifBtn\"",
                    "id=\"msgBtn\"", "class=\"profile\"", "class=\"lang-switch\""):
        assert control in html


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


# --------------------------------------------------------------------------
# V2 visitor journey: per market+service pages
# --------------------------------------------------------------------------
def test_every_market_service_page_has_its_own_title_and_description():
    seen_titles: dict[str, str] = {}
    seen_descriptions: dict[str, str] = {}
    for market, slug in C.all_market_service_pages():
        for lang in ("en", "ar"):
            meta = pages.resolve_route(C.market_service_path(market, slug, lang))
            assert meta is not None
            assert meta.title.strip()
            assert meta.description.strip()
            # Each page must be genuinely distinct, not a country label swap.
            key_t = f"{market}/{slug}/{lang}"
            assert meta.title not in seen_titles, f"{key_t} duplicates {seen_titles[meta.title]}"
            assert meta.description not in seen_descriptions, (
                f"{key_t} duplicates {seen_descriptions[meta.description]}"
            )
            seen_titles[meta.title] = key_t
            seen_descriptions[meta.description] = key_t


def test_every_market_service_page_has_rich_local_content():
    for market, slug in C.all_market_service_pages():
        content = C.service_market_content(slug, market)
        assert content is not None, f"{market}/{slug} has no content"
        for lang in ("en", "ar"):
            assert content["meta"][lang]["title"]
            assert content["meta"][lang]["description"]
            assert content["intro"][lang]
            assert content["highlights"][lang]
            assert content["deliverables"][lang]
            assert content["steps"][lang]
            assert content["faq"][lang]
            # FAQ entries must be (question, answer) pairs with real text.
            for question, answer in content["faq"][lang]:
                assert question.strip() and answer.strip()


def test_market_service_pages_differ_between_markets():
    # The V2 rule: the same service in Bahrain and Saudi must not share copy.
    for slug in C.SERVICES:
        bh = C.service_market_content(slug, "bahrain")
        sa = C.service_market_content(slug, "saudi")
        assert bh and sa
        for lang in ("en", "ar"):
            assert bh["intro"][lang] != sa["intro"][lang]
            assert bh["meta"][lang]["description"] != sa["meta"][lang]["description"]


def test_market_service_page_emits_service_and_faq_structured_data(public_client):
    html = public_client.get("/bahrain/company-formation").text
    assert '"@type": "Service"' in html
    assert '"@type": "FAQPage"' in html
    assert '"@type": "BreadcrumbList"' in html


def test_market_service_page_renders_faq_and_steps(public_client):
    html = public_client.get("/saudi/feasibility-study").text
    assert 'class="faq"' in html
    assert 'class="faq-item"' in html
    assert 'class="steps"' in html
    assert 'class="check-list"' in html


def test_investment_page_uses_the_investment_form(public_client):
    # Regression: the investment page used to post to the opportunity-interest
    # form, which requires an opportunity_id the visitor could not supply.
    html = public_client.get("/saudi/investment").text
    assert 'data-form="investment"' in html
    assert "/api/v1/public/leads/investment" in html
    assert "opportunity_id" not in html


def test_listing_wizard_has_all_its_field_labels(public_client):
    # Regression: three wizard fields had no label and rendered their raw key.
    html = public_client.get("/list-your-business").text
    assert "Business description" in html
    assert "Reason for listing" in html
    assert "Desired outcome" in html
    assert ">description<" not in html
    assert ">reason_for_listing<" not in html
    assert ">desired_outcome<" not in html


def test_footer_links_to_services_by_market(public_client):
    html = public_client.get("/").text
    assert "/bahrain/company-formation" in html
    assert "/saudi/company-formation" in html


# --------------------------------------------------------------------------
# group companies (handoff: interactive selector + mobile accordion)
# --------------------------------------------------------------------------
def test_group_companies_dataset_matches_the_handoff():
    # The canonical dataset is the approved nine, in order, with both legal
    # names supplied. Nothing is invented and nothing is dropped.
    from backend.website import group_companies as G

    companies = G.ordered()
    assert [c["order"] for c in companies] == list(range(1, 10))
    assert [c["id"] for c in companies] == [
        "alreyada", "damac-business", "damac-trading", "bait-al-rayhan",
        "digital-rocket", "najmat-business", "wealth-first",
        "najmat-contracting", "allamasat",
    ]
    for c in companies:
        assert c["name_ar"].strip()
        assert c["country"] in ("bahrain", "saudi")
        assert c["card_ar"] and c["about_ar"] and c["services_ar"]


def test_group_selector_renders_all_nine_with_first_selected(public_client):
    for path in ("/", "/group-companies"):
        html = public_client.get(path).text
        assert html.count("data-company-choice") == 9, path
        assert html.count("data-company-panel") == 9, path
        # The first company is expanded by default; the other eight start
        # collapsed (the header nav toggle is another aria-expanded="false").
        assert html.count('aria-expanded="true"') == 1, path
        assert html.count('aria-expanded="false"') == 9, path
        assert "data-company-detail" in html


def test_group_companies_render_in_both_languages(public_client):
    import html as html_mod

    from backend.website import group_companies as G
    import backend.website.renderer as R

    for path, lang in (("/group-companies", "en"), ("/ar/شركات-المجموعة", "ar")):
        html = public_client.get(path).text
        for c in G.ordered():
            name = html_mod.escape(R._localized_name(c, lang))
            assert name in html, (path, c["id"])


def test_group_company_actions_only_render_when_a_value_exists(public_client):
    html = public_client.get("/group-companies").text
    # Provided contact details become real links (the selected first company)...
    assert "tel:+97317595522" in html          # alreyada phone
    assert "mailto:info@alreyada-law.com" in html
    # ...and every tel:/mailto: that does appear is a real value: either one of
    # the provided company numbers or the Holding's own published number
    # (footer/contact). Never an empty or fabricated one.
    provided_tel = {
        "+97317595522", "+97317826990", "+97337088373", "+97317001555",
        "+97339848990", "+97339808990", "+966505688912", "+97317626990",
    }
    found_tel = set(re.findall(r'href="tel:([^"]+)"', html))
    assert found_tel <= provided_tel
    # A null field must not surface as the string "None" anywhere.
    assert ">None<" not in html


def test_mobile_group_accordion_css_is_present():
    css = (Path(renderer.__file__).resolve().parent.parent.parent
           / "website" / "assets" / "styles.css").read_text(encoding="utf-8")
    block = css.split("@media (max-width: 600px)", 1)[1]
    assert ".company-list { display: block; }" in block
    assert ".desktop-detail { display: none; }" in block
    assert ".inline-detail[hidden] { display: none; }" in block


# --------------------------------------------------------------------------
# original approved design: assets, new pages and the home journey
# --------------------------------------------------------------------------
def test_shipped_original_assets_are_served(public_client):
    # The owner-supplied logo and hero image are real static assets.
    for asset in ("holding-logo.png", "bahrain-bay.jpg"):
        response = public_client.get(f"/website/assets/{asset}")
        assert response.status_code == 200, asset
        assert response.content, asset


def test_home_uses_the_original_logo_and_hero_image(public_client):
    html = public_client.get("/").text
    assert "/website/assets/holding-logo.png" in html
    assert "/website/assets/bahrain-bay.jpg" in html


def test_home_follows_the_approved_section_order(public_client):
    html = public_client.get("/").text
    # Hero → About Us → Group Companies → Business Opportunities → Help.
    # Section-specific markers, so the header nav labels are not matched.
    order = [
        'class="hero hero-home"',
        'class="section about-teaser"',
        "data-company-selector",
        'id="opportunities"',
        'id="help"',
    ]
    positions = [html.find(marker) for marker in order]
    assert all(p != -1 for p in positions), positions
    assert positions == sorted(positions), positions


def test_home_hero_carries_the_holding_name_and_definition(public_client):
    html = public_client.get("/").text
    assert "START UPSPHERE HOLDING CO W.L.L" in html
    assert "Based in Bahrain" in html


def test_home_group_services_form_is_present_in_both_languages(public_client):
    en = public_client.get("/").text
    ar = public_client.get("/ar").text
    assert 'data-form="group-service"' in en
    assert "/api/v1/public/leads/group-service" in en
    assert 'data-form="group-service"' in ar
    # The six services and seven countries are offered as real options.
    for service in C.SERVICE_OPTIONS:
        assert service["en"] in en
    for country in C.SERVICE_COUNTRIES:
        assert country["ar"] in ar


def test_home_offers_the_two_group_cta_actions(public_client):
    html = public_client.get("/").text
    assert "View All Opportunities" in html
    assert "Submit Your Business" in html


def test_careers_page_has_a_cv_form_no_vacancies_list(public_client):
    en = public_client.get("/careers").text
    ar = public_client.get("/ar/الوظائف").text
    assert 'data-form="careers"' in en
    assert 'enctype="multipart/form-data"' in en
    assert 'data-multipart="1"' in en
    assert 'type="file"' in en
    assert "/api/v1/public/leads/careers" in en
    assert "Join the Startup Safeer Team" in en
    assert "انضم إلى فريق ستارت أب سفير" in ar


def test_terms_and_privacy_pages_render_their_approved_sections(public_client):
    terms = public_client.get("/terms").text
    assert "About This Website" in terms
    assert "Business Listings" in terms
    privacy = public_client.get("/ar/سياسة-الخصوصية").text
    assert "البيانات التي نجمعها واستخدامها" in privacy
    assert "مشاركة البيانات" in privacy
    # The internal review note from the handoff draft is never published.
    assert "ملاحظة داخلية" not in privacy
    assert "Owner note" not in privacy


def test_contact_page_has_the_holding_details_and_no_form(public_client):
    html = public_client.get("/contact").text
    assert "START UPSPHERE HOLDING CO W.L.L" in html
    assert "Info@sup-edu.com" in html
    assert "tel:+97317626990" in html
    # The handoff specifies contact details with no enquiry form.
    assert 'class="site-form"' not in html
    # Revision brief item 12: the placeholder map is hidden until the owner
    # provides the real location link, so no stand-in location is shown.
    assert 'class="map-placeholder"' not in html
    assert "Head office location" not in html


def test_about_page_reflects_the_approved_copy(public_client):
    html = public_client.get("/about").text
    assert "Our Role Within the Group" in html
    assert "Our Current Portfolio" in html
    assert "How We Grow" in html
    ar = public_client.get("/ar/عن-القابضة").text
    assert "دورنا داخل المجموعة" in ar
    assert "محفظتنا الحالية" in ar
    assert "كيف ننمو" in ar


def test_new_pages_declare_rtl_in_arabic_and_ltr_in_english(public_client):
    for ar_path, en_path in (
        ("/ar/الوظائف", "/careers"),
        ("/ar/الشروط-والأحكام", "/terms"),
        ("/ar/سياسة-الخصوصية", "/privacy"),
    ):
        assert 'dir="rtl"' in public_client.get(ar_path).text
        assert 'dir="ltr"' in public_client.get(en_path).text


# --------------------------------------------------------------------------
# Revision brief (Safeer_Website_Revision_Brief.docx)
# --------------------------------------------------------------------------
def test_revision_brief_footer_shows_the_real_year_not_a_placeholder(public_client):
    for path in ("/", "/ar"):
        html = public_client.get(path).text
        assert "السنة الحالية" not in html
        assert "Current year" not in html
        assert f"&copy; {datetime.now(timezone.utc).year}" in html


def test_revision_brief_submit_cta_reaches_the_form_in_one_click(public_client):
    # Item 01: the home "Submit Your Business" button must go straight to the
    # listing form page; the dead #submit-project anchor is gone site-wide.
    home_en = public_client.get("/").text
    home_ar = public_client.get("/ar").text
    assert 'href="/list-your-business"' in home_en
    assert 'href="/ar/اعرض-شركتك"' in home_ar
    assert "#submit-project" not in home_en
    assert "#submit-project" not in home_ar


def test_revision_brief_opportunities_use_approved_copy(public_client):
    en = public_client.get("/opportunities").text
    ar = public_client.get("/ar/الفرص-التجارية").text
    # Approved heading + intro (item 04).
    assert "Submit Your Business" in en
    assert "اعرض مشروعك" in ar
    assert "after review and approval" in en
    assert "بعد المراجعة والموافقة" in ar
    # Planning phrases are removed (item 04).
    assert "investor starts here" not in en
    assert "يدخل المستثمر أولًا" not in ar

    # Non-warranty notice appears in the listing context (item 07), i.e. on a
    # market's published-opportunities page.
    listing_en = public_client.get("/bahrain/opportunities").text
    listing_ar = public_client.get("/ar/البحرين/الفرص-والمشاريع").text
    assert "not a guarantee or an investment recommendation" in listing_en
    assert "لا يمثل ضمانًا أو توصية استثمارية" in listing_ar


def test_revision_brief_contact_hides_the_placeholder_map_in_both_languages(public_client):
    for path in ("/contact", "/ar/تواصل"):
        html = public_client.get(path).text
        assert "map-placeholder" not in html
        # The textual address, phone, email and WhatsApp stay.
        assert "Info@sup-edu.com" in html
        assert "tel:+97317626990" in html


def test_revision_brief_careers_heading_is_not_duplicated_and_has_other_country(public_client):
    en = public_client.get("/careers").text
    ar = public_client.get("/ar/الوظائف").text
    # Item 17: one clear section heading; the form gets a functional heading.
    # (The phrase also appears in <title>/JSON-LD, so count the rendered <h1>.)
    assert en.count("Join the Startup Safeer Team</h1>") == 1
    assert ar.count("انضم إلى فريق ستارت أب سفير</h1>") == 1
    assert "Application details" in en
    assert "بيانات التقديم" in ar
    # Item 13: an "other country" choice reveals a required country-name field.
    assert 'data-other-for="residence_country"' in en
    assert "Other country" in en
    assert "دولة أخرى" in ar


def test_revision_brief_no_internal_market_note_is_published(public_client):
    # Item 15: the internal "recorded under the gulf market" note is removed.
    for path in ("/", "/ar", "/contact", "/ar/تواصل"):
        html = public_client.get(path).text
        assert "automatically be recorded under" not in html
        assert "سيُسجَّل هذا الطلب تلقائيًا" not in html


def test_revision_brief_hero_keeps_a_dark_scrim_for_readability(public_client):
    # Item 18: the hero text sits on a gradient scrim over the approved image.
    html = public_client.get("/").text
    assert "linear-gradient(100deg, rgba(10,23,48,.94)" in html
    assert "bahrain-bay.jpg" in html
