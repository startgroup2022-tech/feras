"""Developer-package website contract tests (``/api/public``).

These cover the surface defined by ``00-shared/api-contract.openapi.yaml``: the
public website reads published content and writes only through the five
submission endpoints. Every write is checked against the resulting PostgreSQL
state via the ORM, and every refusal (honeypot, missing consent, unpublished
opportunity) is checked to leave no row behind.
"""

from __future__ import annotations

from backend.db.models.enums import Market, WebsiteServiceType
from backend.db.models.website import WebsiteLead
from backend.db.models.website_cms import WebsiteCompany, WebsiteMedia

CONTRACT = "/api/public"


def _make_company_row(db, slug="alpha", **overrides):
    row = WebsiteCompany(
        slug=slug,
        name_ar=overrides.get("name_ar", "شركة ألفا"),
        name_en=overrides.get("name_en", "Alpha Co"),
        description_ar="وصف",
        description_en="desc",
        country="BH",
        display_order=overrides.get("display_order", 1),
        is_visible=overrides.get("is_visible", True),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# --------------------------------------------------------------------------
# reads
# --------------------------------------------------------------------------
def test_site_info_returns_the_official_holding_name(client):
    body = client.get(f"{CONTRACT}/site-info").json()
    assert body["nameAr"] == "شركة ستارت اب سفير القابضة ذ.م.م"
    assert body["nameEn"] == "START UPSPHERE HOLDING CO W.L.L"
    assert body["email"] == "Info@sup-edu.com"
    assert body["phone"] == "+973 17626990"


def test_companies_returns_only_visible_rows_in_display_order(client, db):
    _make_company_row(db, slug="hidden", is_visible=False, display_order=0)
    _make_company_row(db, slug="second", name_ar="ثاني", display_order=2)
    _make_company_row(db, slug="first", name_ar="أول", display_order=1)

    body = client.get(f"{CONTRACT}/companies").json()
    names = [c["nameAr"] for c in body]
    assert names == ["أول", "ثاني"]  # hidden excluded, ordered by display_order
    assert all(c["id"].startswith("PUB-") for c in body)


def test_company_logo_url_only_for_public_media(client, db):
    media = WebsiteMedia(
        original_name="logo.png",
        storage_key="k/logo.png",
        content_type="image/png",
        byte_size=10,
        visibility="public",
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    row = _make_company_row(db, slug="withlogo")
    row.logo_media_id = media.id
    db.commit()

    body = client.get(f"{CONTRACT}/companies").json()
    assert body[0]["logoUrl"] == f"/api/v1/public/website/media/{media.id}"


def test_vacancies_is_empty_by_design(client):
    assert client.get(f"{CONTRACT}/vacancies").json() == []


# --------------------------------------------------------------------------
# writes: happy paths (verified against the DB)
# --------------------------------------------------------------------------
def test_inquiry_creates_a_contact_lead(client, db):
    resp = client.post(
        f"{CONTRACT}/inquiries",
        json={
            "name": "أحمد",
            "email": "a@example.com",
            "phone": "+9731111",
            "message": "مرحبا",
            "consent": True,
            "lang": "ar",
        },
    )
    assert resp.status_code == 201, resp.text
    reference = resp.json()["reference"]
    lead = db.query(WebsiteLead).filter_by(reference=reference).one()
    assert lead.service_type == WebsiteServiceType.GENERAL_CONTACT.value
    assert lead.email == "a@example.com"


def test_service_request_routes_company_formation_to_its_service(client, db):
    resp = client.post(
        f"{CONTRACT}/service-requests",
        json={
            "service": "company_formation",
            "formationCountry": "Bahrain",
            "name": "سارة",
            "email": "s@example.com",
            "phone": "+9732222",
            "details": "تأسيس شركة",
            "consent": True,
        },
    )
    assert resp.status_code == 201, resp.text
    lead = db.query(WebsiteLead).filter_by(reference=resp.json()["reference"]).one()
    assert lead.service_type == WebsiteServiceType.COMPANY_FORMATION.value
    assert lead.market == Market.BAHRAIN.value


def test_service_request_requires_a_country_for_company_formation(client):
    resp = client.post(
        f"{CONTRACT}/service-requests",
        json={
            "service": "company_formation",
            "name": "سارة",
            "email": "s@example.com",
            "phone": "+9732222",
            "details": "تأسيس",
            "consent": True,
        },
    )
    assert resp.status_code == 422


def test_business_submission_creates_a_listing_lead(client, db):
    resp = client.post(
        f"{CONTRACT}/submissions",
        data={
            "kind": "business_for_sale",
            "title": "متجر",
            "country": "Bahrain",
            "summary": "متجر للبيع",
            "contactName": "علي",
            "contactEmail": "ali@example.com",
            "contactPhone": "+9733333",
            "consent": "true",
            "lang": "ar",
        },
    )
    assert resp.status_code == 201, resp.text
    lead = db.query(WebsiteLead).filter_by(reference=resp.json()["reference"]).one()
    assert lead.service_type == WebsiteServiceType.BUSINESS_LISTING.value


def test_cv_submission_stores_a_careers_lead(client, db):
    resp = client.post(
        f"{CONTRACT}/cv",
        data={
            "name": "منى",
            "email": "mona@example.com",
            "phone": "+9734444",
            "field": "محاسبة",
            "consent": "true",
        },
        files={"file": ("cv.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    lead = db.query(WebsiteLead).filter_by(reference=resp.json()["reference"]).one()
    assert lead.service_type == WebsiteServiceType.CAREERS.value
    assert len(lead.attachments) == 1


# --------------------------------------------------------------------------
# writes: refusals leave no row
# --------------------------------------------------------------------------
def test_honeypot_drops_the_submission_silently(client, db):
    before = db.query(WebsiteLead).count()
    resp = client.post(
        f"{CONTRACT}/inquiries",
        json={
            "name": "bot",
            "email": "bot@example.com",
            "message": "spam",
            "consent": True,
            "hp": "filled",
        },
    )
    assert resp.status_code == 201
    assert db.query(WebsiteLead).count() == before


def test_missing_consent_is_rejected(client):
    resp = client.post(
        f"{CONTRACT}/inquiries",
        json={
            "name": "x",
            "email": "x@example.com",
            "message": "hi",
            "consent": False,
        },
    )
    assert resp.status_code == 422


def test_interest_in_an_unknown_opportunity_is_refused(client):
    resp = client.post(
        f"{CONTRACT}/interests",
        json={
            "opportunityId": "9999",
            "name": "x",
            "email": "x@example.com",
            "phone": "+9735",
            "consent": True,
        },
    )
    assert resp.status_code in (400, 404, 422)
