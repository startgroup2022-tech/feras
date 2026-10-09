"""Phase 10 tests: the public website, its API and the internal lead handling.

The suite is organised around the guarantees that matter:

* the public submission endpoints accept good input and reject bad input,
* a submission is classified and routed server-side, never by the client,
* attribution is preserved,
* nothing confidential is ever exposed publicly,
* internal endpoints are permission gated,
* the website's SEO surface is complete and consistent.
"""

from __future__ import annotations

import json

import pytest

from backend.db.models.enums import (
    LeadStatus,
    Market,
    OpportunityType,
    PublicOpportunityStatus,
    WebsiteServiceType,
)
from backend.db.models.website import WebsiteLead, WebsiteOpportunity
from backend.services import website_lead_service

PUBLIC = "/api/v1/public"


def _base(market: str = "bahrain", **overrides) -> dict:
    payload = {
        "market": market,
        "locale": "ar",
        "full_name": "أحمد العلي",
        "email": "ahmed@example.com",
        "phone": "+9731234567",
        "consent": True,
    }
    payload.update(overrides)
    return payload


# --------------------------------------------------------------------------
# public submissions: happy paths
# --------------------------------------------------------------------------
def test_company_formation_bahrain_is_accepted_and_routed(client, db):
    payload = _base(
        "bahrain",
        desired_activity="تجارة عامة",
        number_of_partners=2,
        investor_type="company",
        nationality="بحريني",
    )
    response = client.post(f"{PUBLIC}/leads/company-formation", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["reference"].startswith("SAF-CF-")

    lead = db.query(WebsiteLead).one()
    assert lead.market == Market.BAHRAIN.value
    assert lead.service_type == WebsiteServiceType.COMPANY_FORMATION.value
    # The routing decision is the server's, derived from the market + service.
    assert lead.routed_team == "formation_bahrain"
    assert lead.status == LeadStatus.NEW.value


def test_company_formation_saudi_requires_residency_and_city(client):
    incomplete = _base("saudi", desired_activity="مقاولات")
    response = client.post(f"{PUBLIC}/leads/company-formation", json=incomplete)
    assert response.status_code == 422

    complete = _base(
        "saudi",
        desired_activity="مقاولات",
        investor_residency="foreign",
        target_city="الرياض",
    )
    response = client.post(f"{PUBLIC}/leads/company-formation", json=complete)
    assert response.status_code == 201
    assert response.json()["reference"].startswith("SAF-CF-")


def test_company_formation_bahrain_requires_partners(client):
    response = client.post(
        f"{PUBLIC}/leads/company-formation",
        json=_base("bahrain", desired_activity="تجارة"),
    )
    assert response.status_code == 422


def test_feasibility_submission_routes_to_market_team(client, db):
    response = client.post(
        f"{PUBLIC}/leads/feasibility",
        json=_base(
            "saudi",
            project_idea="مصنع تعبئة",
            sector="صناعة",
            project_stage="new",
            study_type="feasibility",
            target_city="جدة",
        ),
    )
    assert response.status_code == 201
    lead = db.query(WebsiteLead).one()
    assert lead.routed_team == "feasibility_saudi"


def test_contact_submission_creates_lead(client, db):
    response = client.post(
        f"{PUBLIC}/leads/contact",
        json=_base("bahrain", inquiry_type="general", message="استفسار"),
    )
    assert response.status_code == 201
    assert db.query(WebsiteLead).count() == 1


def test_investment_submission_routes_to_the_investment_desk(client, db):
    # A market-level investment interest has no opportunity_id and must still
    # be accepted and routed.
    response = client.post(
        f"{PUBLIC}/leads/investment",
        json=_base("saudi", investor_profile="Family office"),
    )
    assert response.status_code == 201, response.text
    assert response.json()["reference"].startswith("SAF-IN-")
    lead = db.query(WebsiteLead).one()
    assert lead.service_type == WebsiteServiceType.INVESTMENT.value
    assert lead.market == Market.SAUDI.value
    assert lead.routed_team == "investment_desk"


# --------------------------------------------------------------------------
# consent, honeypot, attribution
# --------------------------------------------------------------------------
def test_consent_is_required(client):
    payload = _base("bahrain", inquiry_type="general")
    payload["consent"] = False
    response = client.post(f"{PUBLIC}/leads/contact", json=payload)
    assert response.status_code == 422


def test_honeypot_accepts_but_stores_nothing(client, db):
    payload = _base("bahrain", inquiry_type="general", honeypot="i-am-a-bot")
    response = client.post(f"{PUBLIC}/leads/contact", json=payload)
    # Indistinguishable from success, but nothing is persisted.
    assert response.status_code == 201
    assert db.query(WebsiteLead).count() == 0


def test_attribution_is_preserved_verbatim(client, db):
    payload = _base(
        "bahrain",
        inquiry_type="general",
        attribution={
            "utm_source": "google",
            "utm_medium": "cpc",
            "utm_campaign": "launch-2027",
            "referrer": "https://example.org/ads",
            "landing_page": "/bahrain/company-formation?utm_source=google",
        },
    )
    client.post(f"{PUBLIC}/leads/contact", json=payload)
    lead = db.query(WebsiteLead).one()
    assert lead.utm_source == "google"
    assert lead.utm_campaign == "launch-2027"
    assert lead.referrer == "https://example.org/ads"


def test_unknown_market_is_rejected(client):
    response = client.post(
        f"{PUBLIC}/leads/contact",
        json=_base("qatar", inquiry_type="general"),
    )
    assert response.status_code == 422


def test_oversized_free_text_is_rejected(client):
    response = client.post(
        f"{PUBLIC}/leads/contact",
        json=_base("bahrain", inquiry_type="general", message="x" * 5000),
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------
# business listings and opportunities
# --------------------------------------------------------------------------
def _listing_payload(**overrides) -> dict:
    payload = _base(
        "bahrain",
        applicant_capacity="owner",
        opportunity_type="full_sale",
        description="شركة تجارية قائمة منذ سنوات.",
        sector="تجارة",
        currency="BHD",
    )
    payload.update(overrides)
    return payload


def test_business_listing_creates_a_private_opportunity(client, db):
    response = client.post(
        f"{PUBLIC}/leads/business-listing",
        data={"payload": json.dumps(_listing_payload())},
    )
    assert response.status_code == 201, response.text
    assert response.json()["reference"].startswith("SAF-BL-")

    opportunity = db.query(WebsiteOpportunity).one()
    # Never public until the Holding reviews it.
    assert opportunity.status == PublicOpportunityStatus.SUBMITTED.value
    assert opportunity.is_public is False


def test_listing_value_range_is_validated(client):
    response = client.post(
        f"{PUBLIC}/leads/business-listing",
        data={"payload": json.dumps(_listing_payload(value_min=1000, value_max=500))},
    )
    assert response.status_code == 422


def test_listing_payload_must_be_valid_json(client):
    response = client.post(
        f"{PUBLIC}/leads/business-listing",
        data={"payload": "{not-json"},
    )
    assert response.status_code == 422


def test_public_opportunity_list_is_empty_by_default(client):
    response = client.get(f"{PUBLIC}/opportunities")
    assert response.status_code == 200
    assert response.json() == []


def test_opportunity_interest_rejects_unpublished_listing(client, db):
    client.post(
        f"{PUBLIC}/leads/business-listing",
        data={"payload": json.dumps(_listing_payload())},
    )
    opportunity = db.query(WebsiteOpportunity).one()

    response = client.post(
        f"{PUBLIC}/leads/opportunity-interest",
        json=_base("bahrain", opportunity_id=opportunity.id),
    )
    # An unpublished listing is indistinguishable from a missing one.
    assert response.status_code == 404


def test_opportunity_interest_accepts_published_listing(client, db):
    client.post(
        f"{PUBLIC}/leads/business-listing",
        data={"payload": json.dumps(_listing_payload())},
    )
    opportunity = db.query(WebsiteOpportunity).one()
    opportunity.status = PublicOpportunityStatus.PUBLISHED.value
    opportunity.is_public = True
    opportunity.public_title_ar = "فرصة تجارية"
    db.commit()

    response = client.post(
        f"{PUBLIC}/leads/opportunity-interest",
        json=_base("bahrain", opportunity_id=opportunity.id),
    )
    assert response.status_code == 201


def test_public_opportunity_shape_never_leaks_confidential_fields(client, db):
    client.post(
        f"{PUBLIC}/leads/business-listing",
        data={"payload": json.dumps(_listing_payload(description="بيانات سرية"))},
    )
    opportunity = db.query(WebsiteOpportunity).one()
    opportunity.status = PublicOpportunityStatus.PUBLISHED.value
    opportunity.is_public = True
    opportunity.public_title_ar = "فرصة معلنة"
    opportunity.public_summary_ar = "ملخص عام"
    db.commit()

    rows = client.get(f"{PUBLIC}/opportunities").json()
    assert len(rows) == 1
    row = rows[0]
    # The confidential description and value range are absent from the shape.
    assert "description" not in row
    assert "value_min" not in row
    assert "value_max" not in row
    assert row["title_ar"] == "فرصة معلنة"


def test_public_opportunities_can_be_filtered_by_market(client, db):
    for market in ("bahrain", "saudi"):
        lead = WebsiteLead(
            reference=f"SAF-BL-{market}",
            source="website",
            market=market,
            service_type=WebsiteServiceType.BUSINESS_LISTING.value,
            locale="ar",
            full_name="x",
            email="x@example.com",
            consent_given=True,
            status=LeadStatus.NEW.value,
            priority="normal",
        )
        db.add(lead)
        db.flush()
        db.add(
            WebsiteOpportunity(
                lead_id=lead.id,
                market=market,
                applicant_capacity="owner",
                opportunity_type=OpportunityType.FULL_SALE.value,
                currency="BHD",
                status=PublicOpportunityStatus.PUBLISHED.value,
                is_public=True,
                public_title_ar="فرصة",
            )
        )
    db.commit()

    rows = client.get(f"{PUBLIC}/opportunities?market=saudi").json()
    assert len(rows) == 1
    assert rows[0]["market"] == "saudi"


# --------------------------------------------------------------------------
# internal endpoints: permissions
# --------------------------------------------------------------------------
def test_lead_list_requires_authentication(client):
    assert client.get("/api/v1/leads").status_code == 401


def test_company_manager_cannot_see_website_leads(client, world, login):
    # A company manager has no website_lead.read permission.
    headers = login("alpha@corp.sa")
    assert client.get("/api/v1/leads", headers=headers).status_code == 403
    assert client.get("/api/v1/leads/stats", headers=headers).status_code == 403


def test_business_development_can_read_and_manage_leads(client, world, login):
    headers = login("owner@corp.sa")  # holding_owner
    assert client.get("/api/v1/leads", headers=headers).status_code == 200
    assert client.get("/api/v1/leads/stats", headers=headers).status_code == 200


def test_lead_update_requires_manage_permission(client, db, world, login):
    # Create a lead as the public website would.
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("RATE_LIMIT_ENABLED", "false")
    client.post(
        f"{PUBLIC}/leads/contact",
        json=_base("bahrain", inquiry_type="general"),
    )
    lead = db.query(WebsiteLead).one()

    accountant = login("acc@corp.sa")  # accountant: no lead permissions
    assert client.get(f"/api/v1/leads/{lead.id}", headers=accountant).status_code == 403
    assert (
        client.patch(f"/api/v1/leads/{lead.id}", json={"status": "in_progress"}, headers=accountant).status_code
        == 403
    )

    owner = login("owner@corp.sa")
    response = client.patch(
        f"/api/v1/leads/{lead.id}", json={"status": "in_progress"}, headers=owner
    )
    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"


def test_lead_stats_reflect_real_rows(client, db, world, login):
    client.post(
        f"{PUBLIC}/leads/contact",
        json=_base("bahrain", inquiry_type="general"),
    )
    client.post(
        f"{PUBLIC}/leads/feasibility",
        json=_base(
            "saudi",
            project_idea="مشروع",
            sector="صناعة",
            project_stage="new",
            study_type="market",
            target_city="الدمام",
        ),
    )
    headers = login("owner@corp.sa")
    stats = client.get("/api/v1/leads/stats", headers=headers).json()
    assert stats["total"] == 2
    assert stats["by_market"]["bahrain"] == 1
    assert stats["by_market"]["saudi"] == 1


def test_opportunity_review_requires_publish_copy(client, db, world, login):
    client.post(
        f"{PUBLIC}/leads/business-listing",
        data={"payload": json.dumps(_listing_payload())},
    )
    opportunity = db.query(WebsiteOpportunity).one()
    headers = login("owner@corp.sa")

    # Publishing without public copy is refused.
    response = client.post(
        f"/api/v1/leads/opportunities/{opportunity.id}/review",
        json={"status": "published", "publish": True},
        headers=headers,
    )
    assert response.status_code == 422

    # With copy it succeeds and the listing becomes public.
    response = client.post(
        f"/api/v1/leads/opportunities/{opportunity.id}/review",
        json={
            "status": "published",
            "publish": True,
            "public_title_ar": "فرصة معلنة",
        },
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["is_public"] is True


# --------------------------------------------------------------------------
# notifications
# --------------------------------------------------------------------------
def test_new_lead_notifies_the_responsible_role(client, db, world, login):
    client.post(
        f"{PUBLIC}/leads/company-formation",
        json=_base(
            "bahrain",
            desired_activity="تجارة",
            number_of_partners=1,
            investor_type="individual",
        ),
    )
    # The holding owner is in the notify set for formation requests.
    headers = login("owner@corp.sa")
    items = client.get("/api/v1/notifications", headers=headers).json()["items"]
    assert any("SAF-CF" in (n["title_ar"] or "") or "SAF-CF" in (n["title_en"] or "") for n in items)


# --------------------------------------------------------------------------
# routing table integrity
# --------------------------------------------------------------------------
def test_every_service_market_pair_has_a_route():
    for service in WebsiteServiceType:
        for market in Market:
            assert website_lead_service.routed_team_for(service.value, market.value), (
                f"no route for {service.value}/{market.value}"
            )


def test_references_are_unique_across_many_submissions(client, db):
    for index in range(12):
        client.post(
            f"{PUBLIC}/leads/contact",
            json=_base("bahrain", inquiry_type="general", email=f"u{index}@example.com"),
        )
    refs = [lead.reference for lead in db.query(WebsiteLead).all()]
    assert len(refs) == len(set(refs)) == 12


# --------------------------------------------------------------------------
# handoff forms: group services (market-less) and careers (CV)
# --------------------------------------------------------------------------
def test_group_service_submission_is_market_less_and_routed_to_the_front_desk(client, db):
    payload = {
        "locale": "ar",
        "full_name": "أحمد العلي",
        "email": "ahmed@example.com",
        "phone": "+9731234567",
        "service": "legal",
        "country": "BH",
        "consent": True,
    }
    response = client.post(f"{PUBLIC}/leads/group-service", json=payload)
    assert response.status_code == 201, response.text
    assert response.json()["reference"].startswith("SAF-GS-")

    lead = db.query(WebsiteLead).one()
    # No false Bahrain/Saudi choice: the market-less form is recorded as gulf.
    assert lead.market == Market.GULF.value
    assert lead.service_type == WebsiteServiceType.GROUP_SERVICE.value
    assert lead.routed_team == "holding_front_desk"
    # The visitor's actual service and country are preserved in the payload.
    stored = json.loads(lead.payload_json)
    assert stored["service"] == "legal"
    assert stored["country"] == "BH"


def test_group_service_requires_the_service_and_country(client):
    incomplete = {
        "locale": "ar",
        "full_name": "أحمد",
        "email": "a@example.com",
        "phone": "+9731234567",
        "consent": True,
    }
    assert client.post(f"{PUBLIC}/leads/group-service", json=incomplete).status_code == 422


def test_careers_submission_accepts_a_cv_and_routes_to_the_people_team(client, db):
    payload = json.dumps(
        {
            "locale": "en",
            "full_name": "Sam Applicant",
            "email": "sam@example.com",
            "phone": "+9731234567",
            "residence_country": "BH",
            "job_title": "Engineer",
            "years_experience": "5",
            "consent": True,
        }
    )
    response = client.post(
        f"{PUBLIC}/leads/careers",
        data={"payload": payload},
        files={"cv": ("cv.pdf", b"%PDF-1.4 minimal", "application/pdf")},
    )
    assert response.status_code == 201, response.text
    assert response.json()["reference"].startswith("SAF-CV-")

    lead = db.query(WebsiteLead).one()
    assert lead.service_type == WebsiteServiceType.CAREERS.value
    assert lead.market == Market.GULF.value
    assert lead.routed_team == "people_team"
    stored = json.loads(lead.payload_json)
    assert stored["job_title"] == "Engineer"


def test_careers_payload_must_be_valid_json(client):
    response = client.post(
        f"{PUBLIC}/leads/careers",
        data={"payload": "not-json"},
        files={"cv": ("cv.pdf", b"x", "application/pdf")},
    )
    assert response.status_code == 422


def test_careers_marks_the_residence_country_as_open_text(client, db):
    # The handoff does not restrict career residence to the service-country
    # list, so an unlisted country is accepted as free text.
    payload = json.dumps(
        {
            "locale": "en",
            "full_name": "Dana",
            "email": "dana@example.com",
            "phone": "+444",
            "residence_country": "United Kingdom",
            "job_title": "Analyst",
            "years_experience": "2",
            "consent": True,
        }
    )
    response = client.post(
        f"{PUBLIC}/leads/careers",
        data={"payload": payload},
        files={"cv": ("cv.pdf", b"x", "application/pdf")},
    )
    assert response.status_code == 201, response.text
    assert json.loads(db.query(WebsiteLead).one().payload_json)["residence_country"] == "United Kingdom"


def test_careers_other_country_requires_a_name_and_stores_it(client, db):
    # Revision brief item 13: choosing "other country" must carry the actual
    # country name, not the literal value "other", and the server enforces it.
    missing = json.dumps(
        {
            "locale": "en",
            "full_name": "Nour",
            "email": "nour@example.com",
            "phone": "+962",
            "residence_country": "other",
            "job_title": "Designer",
            "years_experience": "0",
            "consent": True,
        }
    )
    rejected = client.post(
        f"{PUBLIC}/leads/careers",
        data={"payload": missing},
        files={"cv": ("cv.pdf", b"%PDF", "application/pdf")},
    )
    assert rejected.status_code == 422

    provided = json.loads(missing)
    provided["residence_country_other"] = "Jordan"
    accepted = client.post(
        f"{PUBLIC}/leads/careers",
        data={"payload": json.dumps(provided)},
        files={"cv": ("cv.pdf", b"%PDF", "application/pdf")},
    )
    assert accepted.status_code == 201, accepted.text
    stored = json.loads(db.query(WebsiteLead).one().payload_json)
    assert stored["residence_country"] == "Jordan"
