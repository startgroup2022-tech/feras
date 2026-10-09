"""Website lead service.

This is where the public website meets the internal platform. A public form
submission becomes a durable, routed, attributed internal record here -- no
``localStorage``, no client-side fiction.

Responsibilities, in order of importance:

1. **Accept a public submission safely.** Rate limiting, a honeypot check and
   strict schema validation all run before anything is written. A bot that
   fills the honeypot receives the same success response as a human but no row
   is created, so probing the endpoint reveals nothing.
2. **Classify and route.** Market and service type come from the page context
   (server-side), never from a free-text field, so the record always knows which
   market generated the lead. A deterministic rule table picks the team and, in
   some cases, the subsidiary that will handle it.
3. **Preserve attribution.** UTM/referrer/landing are copied verbatim at
   submission time and never recomputed.
4. **Notify the responsible people.** The existing notification centre is used
   so a new lead shows up in the right inbox, and the existing webhook
   integration fires ``lead.created`` for external subscribers.

Nothing in the public path can read internal data: the only public read is
:func:`list_public_opportunities`, which filters on ``is_public`` and returns a
deliberately narrow shape.
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.core.config import settings
from backend.core.errors import NotFoundError, ValidationError
from backend.db.base import utcnow
from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import (
    ApplicantCapacity,
    LeadPriority,
    LeadStatus,
    Market,
    OpportunityType,
    PublicOpportunityStatus,
    WebsiteLeadSource,
    WebsiteServiceType,
)
from backend.db.models.identity import User
from backend.db.models.website import (
    WebsiteLead,
    WebsiteLeadAttachment,
    WebsiteOpportunity,
)
from backend.rbac.authorization import require_permission
from backend.rbac.permissions import Perm
from backend.schemas.website import (
    BusinessListingSubmission,
    CareersSubmission,
    CompanyFormationSubmission,
    ContactSubmission,
    FeasibilitySubmission,
    GroupServiceSubmission,
    OpportunityInterestSubmission,
)
from backend.services import audit_service

logger = logging.getLogger("safir.website")


# --------------------------------------------------------------------------
# routing rules
# --------------------------------------------------------------------------
# Which internal team owns each service, per market. This is the whole point of
# the gateway: the visitor picks a need and a market; SAFIR decides internally.
# The mapping is data, not logic, so it is easy to review and change.
# Market-less forms (the handoff's group-services and careers forms are not
# scoped to Bahrain/Saudi) are recorded under ``Market.GULF`` so the routing
# table stays total and the integrity test can assert every service/market pair
# is handled. The country the visitor actually chose lives in the service
# fields, not in the market column.
ROUTING_TABLE: dict[str, dict[str, str]] = {
    WebsiteServiceType.COMPANY_FORMATION.value: {
        Market.BAHRAIN.value: "formation_bahrain",
        Market.SAUDI.value: "formation_saudi",
        Market.GULF.value: "formation_bahrain",
    },
    WebsiteServiceType.FEASIBILITY_STUDY.value: {
        Market.BAHRAIN.value: "feasibility_bahrain",
        Market.SAUDI.value: "feasibility_saudi",
        Market.GULF.value: "feasibility_bahrain",
    },
    WebsiteServiceType.OPPORTUNITY_INTEREST.value: {
        Market.BAHRAIN.value: "investment_desk",
        Market.SAUDI.value: "investment_desk",
        Market.GULF.value: "investment_desk",
    },
    WebsiteServiceType.BUSINESS_LISTING.value: {
        Market.BAHRAIN.value: "investment_desk",
        Market.SAUDI.value: "investment_desk",
        Market.GULF.value: "investment_desk",
    },
    WebsiteServiceType.INVESTMENT.value: {
        Market.BAHRAIN.value: "investment_desk",
        Market.SAUDI.value: "investment_desk",
        Market.GULF.value: "investment_desk",
    },
    WebsiteServiceType.GENERAL_CONTACT.value: {
        Market.BAHRAIN.value: "holding_front_desk",
        Market.SAUDI.value: "holding_front_desk",
        Market.GULF.value: "holding_front_desk",
    },
    # Handoff §4: the visitor picks a service and a country; the Holding routes
    # it internally to the responsible group company.
    WebsiteServiceType.GROUP_SERVICE.value: {
        Market.BAHRAIN.value: "holding_front_desk",
        Market.SAUDI.value: "holding_front_desk",
        Market.GULF.value: "holding_front_desk",
    },
    # Handoff §3 الوظائف: CVs go to the people team, not a market desk.
    WebsiteServiceType.CAREERS.value: {
        Market.BAHRAIN.value: "people_team",
        Market.SAUDI.value: "people_team",
        Market.GULF.value: "people_team",
    },
}

# Service -> the role that should be notified. Business Development owns the
# lead pipeline; a formation/feasibility request additionally notifies the
# Holding Owner so nothing high-value sits unseen.
SERVICE_NOTIFY_ROLES: dict[str, list[str]] = {
    WebsiteServiceType.COMPANY_FORMATION.value: ["business_development", "holding_owner"],
    WebsiteServiceType.FEASIBILITY_STUDY.value: ["business_development", "holding_owner"],
    WebsiteServiceType.OPPORTUNITY_INTEREST.value: ["business_development", "holding_owner"],
    WebsiteServiceType.BUSINESS_LISTING.value: ["business_development", "holding_owner"],
    WebsiteServiceType.INVESTMENT.value: ["business_development", "holding_owner"],
    WebsiteServiceType.GENERAL_CONTACT.value: ["business_development"],
    WebsiteServiceType.GROUP_SERVICE.value: ["business_development", "holding_owner"],
    WebsiteServiceType.CAREERS.value: ["business_development", "holding_owner"],
}


def routed_team_for(service_type: str, market: str) -> str | None:
    return ROUTING_TABLE.get(service_type, {}).get(market)


def _new_reference(service_type: str) -> str:
    """A short, non-guessable public reference, e.g. ``SAF-WEB-7F3A91``.

    The random suffix means a visitor cannot enumerate other people's
    references, and the numeric id is never exposed.
    """
    prefix = {
        WebsiteServiceType.COMPANY_FORMATION.value: "SAF-CF",
        WebsiteServiceType.FEASIBILITY_STUDY.value: "SAF-FS",
        WebsiteServiceType.OPPORTUNITY_INTEREST.value: "SAF-OI",
        WebsiteServiceType.BUSINESS_LISTING.value: "SAF-BL",
        WebsiteServiceType.INVESTMENT.value: "SAF-IN",
        WebsiteServiceType.GENERAL_CONTACT.value: "SAF-CT",
        WebsiteServiceType.GROUP_SERVICE.value: "SAF-GS",
        WebsiteServiceType.CAREERS.value: "SAF-CV",
    }.get(service_type, "SAF-WEB")
    return f"{prefix}-{secrets.token_hex(3).upper()}"


# --------------------------------------------------------------------------
# public submission entry point
# --------------------------------------------------------------------------
def create_lead(
    db: Session,
    *,
    service_type: str,
    payload: (
        CompanyFormationSubmission
        | FeasibilitySubmission
        | OpportunityInterestSubmission
        | InvestmentSubmission
        | BusinessListingSubmission
        | ContactSubmission
        | GroupServiceSubmission
        | CareersSubmission
    ),
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> WebsiteLead:
    """Persist a public submission as an internal lead and route it.

    Returns the created lead. The caller (the public API) only ever exposes the
    reference and timestamp to the visitor.
    """
    # Honeypot: accept silently, store nothing. Returning a normal-looking
    # result avoids teaching a bot which submissions succeed.
    if (payload.honeypot or "").strip():
        logger.info("website submission dropped: honeypot filled")
        return WebsiteLead(
            reference=_new_reference(service_type),
            source=WebsiteLeadSource.WEBSITE.value,
            market=payload.market.value,
            service_type=service_type,
            locale=payload.locale,
            full_name="—",
            email="dropped@invalid",
            consent_given=True,
            status=LeadStatus.CLOSED.value,
            created_at=utcnow(),
            updated_at=utcnow(),
        )

    # Cross-check market/service: an opportunity-interest request must point at
    # a real, published listing in the same market. This prevents using the
    # endpoint to probe unpublished opportunities.
    opportunity: WebsiteOpportunity | None = None
    if service_type == WebsiteServiceType.OPPORTUNITY_INTEREST.value:
        opportunity = _resolve_public_opportunity(
            db, payload.opportunity_id, market=payload.market.value
        )

    service_fields = _service_fields(service_type, payload)
    team = routed_team_for(service_type, payload.market.value)

    lead = WebsiteLead(
        reference=_new_reference(service_type),
        source=WebsiteLeadSource.WEBSITE.value,
        market=payload.market.value,
        service_type=service_type,
        locale=payload.locale,
        full_name=payload.full_name.strip(),
        email=str(payload.email).strip().lower(),
        phone=(payload.phone or "").strip() or None,
        nationality=(payload.nationality or "").strip() or None,
        company_name=(payload.company_name or "").strip() or None,
        message=(payload.message or "").strip() or None,
        consent_given=payload.consent,
        payload_json=json.dumps(service_fields, ensure_ascii=False, default=str),
        status=LeadStatus.NEW.value,
        priority=_initial_priority(service_type),
        routed_team=team,
        **_attribution_columns(payload),
        ip_address=ip_address,
        user_agent=(user_agent or "")[:255] or None,
    )
    db.add(lead)
    db.flush()

    if service_type == WebsiteServiceType.BUSINESS_LISTING.value:
        _create_opportunity(db, lead=lead, payload=payload)

    db.commit()
    db.refresh(lead)

    audit_service.record(
        db,
        action=AuditAction.WEBSITE_LEAD_CREATED,
        entity_type="website_lead",
        entity_id=lead.id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={
            "reference": lead.reference,
            "market": lead.market,
            "service_type": lead.service_type,
            "routed_team": lead.routed_team,
            "opportunity_id": opportunity.id if opportunity else None,
        },
    )
    _notify_team(db, lead=lead)
    _emit_lead_created(db, lead=lead)
    return lead


def _attribution_columns(payload) -> dict:
    attr = payload.attribution
    if attr is None:
        return {
            "utm_source": None,
            "utm_medium": None,
            "utm_campaign": None,
            "utm_content": None,
            "utm_term": None,
            "referrer": None,
            "landing_page": None,
        }
    return {
        "utm_source": attr.utm_source,
        "utm_medium": attr.utm_medium,
        "utm_campaign": attr.utm_campaign,
        "utm_content": attr.utm_content,
        "utm_term": attr.utm_term,
        "referrer": attr.referrer,
        "landing_page": attr.landing_page,
    }


def _initial_priority(service_type: str) -> str:
    # Listings and investment interest are high-value by nature; the rest are
    # normal. Priority is an internal hint, not something the visitor sets.
    if service_type in {
        WebsiteServiceType.BUSINESS_LISTING.value,
        WebsiteServiceType.INVESTMENT.value,
        WebsiteServiceType.OPPORTUNITY_INTEREST.value,
        WebsiteServiceType.GROUP_SERVICE.value,
        WebsiteServiceType.CAREERS.value,
    }:
        return LeadPriority.HIGH.value
    return LeadPriority.NORMAL.value


def _service_fields(service_type: str, payload) -> dict:
    """The service-specific answers, minus the shared contact block.

    Kept as a dict so a new service can be added without a migration.
    """
    common = {"locale": payload.locale, "market": payload.market.value}
    if service_type == WebsiteServiceType.COMPANY_FORMATION.value:
        return {
            **common,
            "desired_activity": payload.desired_activity,
            "number_of_partners": payload.number_of_partners,
            "investor_type": payload.investor_type,
            "needs_office": payload.needs_office,
            "investor_residency": payload.investor_residency,
            "legal_entity": payload.legal_entity,
            "target_city": payload.target_city,
        }
    if service_type == WebsiteServiceType.FEASIBILITY_STUDY.value:
        return {
            **common,
            "project_idea": payload.project_idea,
            "sector": payload.sector,
            "project_location": payload.project_location,
            "target_city": payload.target_city,
            "approximate_capital": payload.approximate_capital,
            "project_stage": payload.project_stage,
            "study_type": payload.study_type,
        }
    if service_type == WebsiteServiceType.OPPORTUNITY_INTEREST.value:
        return {
            **common,
            "opportunity_id": payload.opportunity_id,
            "investor_profile": payload.investor_profile,
        }
    if service_type == WebsiteServiceType.INVESTMENT.value:
        return {
            **common,
            "investor_profile": payload.investor_profile,
        }
    if service_type == WebsiteServiceType.BUSINESS_LISTING.value:
        return {
            **common,
            "applicant_capacity": payload.applicant_capacity.value,
            "opportunity_type": payload.opportunity_type.value,
            "sector": payload.sector,
            "business_age_years": payload.business_age_years,
            "description": payload.description,
            "value_min": float(payload.value_min) if payload.value_min is not None else None,
            "value_max": float(payload.value_max) if payload.value_max is not None else None,
            "currency": payload.currency,
            "reason_for_listing": payload.reason_for_listing,
            "desired_outcome": payload.desired_outcome,
        }
    if service_type == WebsiteServiceType.GENERAL_CONTACT.value:
        return {**common, "inquiry_type": payload.inquiry_type, "subject": payload.subject}
    if service_type == WebsiteServiceType.GROUP_SERVICE.value:
        return {
            **common,
            "service": payload.service,
            "country": payload.country,
        }
    if service_type == WebsiteServiceType.CAREERS.value:
        # Item 13: when the visitor chose "other country", store the actual
        # name they typed instead of the literal value "other".
        residence = payload.residence_country
        if residence == "other" and (payload.residence_country_other or "").strip():
            residence = payload.residence_country_other.strip()
        return {
            **common,
            "residence_country": residence,
            "city": payload.city,
            "job_title": payload.job_title,
            "years_experience": payload.years_experience,
            "preferred_company": payload.preferred_company,
        }
    return common


def _resolve_public_opportunity(
    db: Session, opportunity_id: int, *, market: str
) -> WebsiteOpportunity:
    opportunity = db.execute(
        select(WebsiteOpportunity).where(
            WebsiteOpportunity.id == opportunity_id,
            WebsiteOpportunity.is_public.is_(True),
            WebsiteOpportunity.status == PublicOpportunityStatus.PUBLISHED.value,
            WebsiteOpportunity.market == market,
        )
    ).scalar_one_or_none()
    if opportunity is None:
        # Indistinguishable from "no such listing": a private opportunity must
        # not be probeable.
        raise NotFoundError("This opportunity is no longer available.")
    return opportunity


def _create_opportunity(
    db: Session, *, lead: WebsiteLead, payload: BusinessListingSubmission
) -> WebsiteOpportunity:
    opportunity = WebsiteOpportunity(
        lead_id=lead.id,
        market=lead.market,
        applicant_capacity=payload.applicant_capacity.value,
        opportunity_type=payload.opportunity_type.value,
        sector=payload.sector,
        business_age_years=payload.business_age_years,
        description=payload.description,
        value_min=payload.value_min,
        value_max=payload.value_max,
        currency=payload.currency,
        reason_for_listing=payload.reason_for_listing,
        desired_outcome=payload.desired_outcome,
        status=PublicOpportunityStatus.SUBMITTED.value,
        # Never public on submission. The Holding reviews and publishes.
        is_public=False,
    )
    db.add(opportunity)
    db.flush()
    audit_service.record(
        db,
        action=AuditAction.WEBSITE_OPPORTUNITY_SUBMITTED,
        entity_type="website_opportunity",
        entity_id=opportunity.id,
        metadata={"lead_id": lead.id, "market": lead.market},
        commit=False,
    )
    return opportunity


# --------------------------------------------------------------------------
# notifications / webhooks
# --------------------------------------------------------------------------
def _notify_team(db: Session, *, lead: WebsiteLead) -> None:
    """Put the new lead in the right internal inboxes. Best-effort."""
    try:
        from backend.db.models.identity import Role
        from backend.services import notification_service

        role_codes = SERVICE_NOTIFY_ROLES.get(lead.service_type, ["business_development"])
        role_ids = list(
            db.execute(select(Role.id).where(Role.code.in_(role_codes))).scalars()
        )
        if not role_ids:
            return
        recipients = list(
            db.execute(
                select(User.id).where(
                    User.role_id.in_(role_ids), User.is_active.is_(True)
                )
            ).scalars()
        )
        if not recipients:
            return
        notification_service.notify(
            db,
            recipient_ids=recipients,
            type="system",
            title_ar=f"طلب جديد من الموقع: {lead.reference}",
            title_en=f"New website request: {lead.reference}",
            message_ar=(
                f"وصل طلب جديد ({lead.service_type}) من سوق "
                f"{'البحرين' if lead.market == Market.BAHRAIN.value else 'السعودية'}."
            ),
            message_en=(
                f"A new {lead.service_type} request arrived from the "
                f"{'Bahrain' if lead.market == Market.BAHRAIN.value else 'Saudi'} market."
            ),
            priority=lead.priority,
            entity_type="website_lead",
            entity_id=lead.id,
            dedupe_key=f"lead:{lead.id}",
            emit_webhook=False,
        )
    except Exception:  # noqa: BLE001 - a notification must never fail a lead
        logger.exception("failed to notify team about lead %s", lead.reference)


def _emit_lead_created(db: Session, *, lead: WebsiteLead) -> None:
    try:
        from backend.services import integration_service

        integration_service.emit(
            db,
            event_type="lead.created",
            payload={
                "lead_id": lead.id,
                "reference": lead.reference,
                "market": lead.market,
                "service_type": lead.service_type,
                "routed_team": lead.routed_team,
                "utm_source": lead.utm_source,
                "utm_campaign": lead.utm_campaign,
            },
        )
    except Exception:  # noqa: BLE001 - best-effort
        logger.exception("lead webhook emit failed")


# --------------------------------------------------------------------------
# public read: published opportunities
# --------------------------------------------------------------------------
def list_public_opportunities(
    db: Session, *, market: str | None = None, opportunity_type: str | None = None
) -> list[dict]:
    """Published listings only, in the narrow public shape."""
    stmt = (
        select(WebsiteOpportunity)
        .options(
            selectinload(WebsiteOpportunity.lead).selectinload(WebsiteLead.attachments)
        )
        .where(
            WebsiteOpportunity.is_public.is_(True),
            WebsiteOpportunity.status == PublicOpportunityStatus.PUBLISHED.value,
        )
    )
    if market:
        stmt = stmt.where(WebsiteOpportunity.market == market)
    if opportunity_type:
        stmt = stmt.where(WebsiteOpportunity.opportunity_type == opportunity_type)
    stmt = stmt.order_by(WebsiteOpportunity.updated_at.desc())

    return [_public_opportunity_shape(row) for row in db.execute(stmt).scalars()]


def public_opportunity_photo(db: Session, *, opportunity_id: int, attachment_id: int):
    """A single public photo for a published listing, or ``None``.

    Returns ``(storage_key, content_type)`` only when the opportunity is
    published and the attachment belongs to its lead and is marked public. A
    proof document or CV on the same lead can therefore never be fetched
    through this path, and an unpublished listing reveals nothing.
    """
    row = db.execute(
        select(WebsiteOpportunity)
        .options(selectinload(WebsiteOpportunity.lead))
        .where(
            WebsiteOpportunity.id == opportunity_id,
            WebsiteOpportunity.is_public.is_(True),
            WebsiteOpportunity.status == PublicOpportunityStatus.PUBLISHED.value,
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    attachment = (
        db.query(WebsiteLeadAttachment)
        .filter(
            WebsiteLeadAttachment.id == attachment_id,
            WebsiteLeadAttachment.lead_id == row.lead_id,
            WebsiteLeadAttachment.is_public.is_(True),
        )
        .one_or_none()
    )
    if attachment is None:
        return None
    return attachment.storage_key, attachment.content_type


def _public_opportunity_shape(row: WebsiteOpportunity) -> dict:
    photos = []
    lead = row.lead
    if lead is not None:
        photos = [
            f"/api/v1/public/opportunities/{row.id}/photos/{a.id}"
            for a in lead.attachments
            if a.is_public
        ]
    return {
        "id": row.id,
        "market": row.market,
        "opportunity_type": row.opportunity_type,
        "sector": row.sector,
        "title_ar": row.public_title_ar,
        "title_en": row.public_title_en,
        "summary_ar": row.public_summary_ar,
        "summary_en": row.public_summary_en,
        "photo_urls": photos,
        "published_at": row.updated_at,
    }


# --------------------------------------------------------------------------
# internal read / write
# --------------------------------------------------------------------------
def serialise_lead(lead: WebsiteLead) -> dict:
    payload = None
    if lead.payload_json:
        try:
            payload = json.loads(lead.payload_json)
        except (TypeError, ValueError):
            payload = None

    attribution = {
        k: getattr(lead, k)
        for k in (
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_content",
            "utm_term",
            "referrer",
            "landing_page",
        )
    }
    if not any(attribution.values()):
        attribution = {}

    return {
        "id": lead.id,
        "reference": lead.reference,
        "source": lead.source,
        "market": lead.market,
        "service_type": lead.service_type,
        "locale": lead.locale,
        "full_name": lead.full_name,
        "email": lead.email,
        "phone": lead.phone,
        "nationality": lead.nationality,
        "company_name": lead.company_name,
        "message": lead.message,
        "payload": payload,
        "status": lead.status,
        "priority": lead.priority,
        "routed_team": lead.routed_team,
        "routed_company_id": lead.routed_company_id,
        "assigned_to_id": lead.assigned_to_id,
        "assigned_to_name_ar": lead.assigned_to.full_name_ar if lead.assigned_to else None,
        "assigned_to_name_en": lead.assigned_to.full_name_en if lead.assigned_to else None,
        "final_result": lead.final_result,
        "internal_notes": lead.internal_notes,
        "attribution": attribution or None,
        "created_at": lead.created_at,
        "updated_at": lead.updated_at,
        "closed_at": lead.closed_at,
        "attachments": [
            {
                "id": a.id,
                "original_filename": a.original_filename,
                "content_type": a.content_type,
                "size_bytes": a.size_bytes,
                "created_at": a.created_at,
            }
            for a in lead.attachments
        ],
    }


def get_lead(db: Session, *, user: User, lead_id: int) -> WebsiteLead:
    require_permission(user, Perm.LEAD_READ)
    lead = db.execute(
        select(WebsiteLead)
        .options(selectinload(WebsiteLead.attachments), selectinload(WebsiteLead.assigned_to))
        .where(WebsiteLead.id == lead_id)
    ).scalar_one_or_none()
    if lead is None:
        raise NotFoundError("Lead not found.")
    return lead


def list_leads(
    db: Session,
    *,
    user: User,
    market: str | None = None,
    service_type: str | None = None,
    status: str | None = None,
    assigned_to_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    require_permission(user, Perm.LEAD_READ)
    conditions = []
    if market:
        conditions.append(WebsiteLead.market == market)
    if service_type:
        conditions.append(WebsiteLead.service_type == service_type)
    if status:
        conditions.append(WebsiteLead.status == status)
    if assigned_to_id is not None:
        conditions.append(WebsiteLead.assigned_to_id == assigned_to_id)

    count_stmt = select(func.count(WebsiteLead.id))
    stmt = (
        select(WebsiteLead)
        .options(selectinload(WebsiteLead.attachments), selectinload(WebsiteLead.assigned_to))
        .order_by(WebsiteLead.created_at.desc(), WebsiteLead.id.desc())
    )
    for condition in conditions:
        count_stmt = count_stmt.where(condition)
        stmt = stmt.where(condition)

    total = int(db.execute(count_stmt).scalar_one())
    rows = list(db.execute(stmt.limit(limit).offset(offset)).scalars())
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [serialise_lead(row) for row in rows],
    }


def update_lead(
    db: Session,
    *,
    user: User,
    lead_id: int,
    changes: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> WebsiteLead:
    require_permission(user, Perm.LEAD_MANAGE)
    lead = get_lead(db, user=user, lead_id=lead_id)

    previous_status = lead.status
    for field, value in changes.items():
        if value is None:
            continue
        if field == "status" and value != previous_status:
            require_permission(user, Perm.LEAD_STATUS_CHANGE)
            lead.status = value
            if value in {LeadStatus.CLOSED.value, LeadStatus.CONVERTED.value}:
                lead.closed_at = utcnow()
        elif field == "status":
            continue
        else:
            setattr(lead, field, value)

    db.add(lead)
    db.commit()
    db.refresh(lead)

    audit_service.record(
        db,
        action=AuditAction.WEBSITE_LEAD_UPDATED,
        actor_user_id=user.id,
        entity_type="website_lead",
        entity_id=lead.id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"changes": {k: str(v) for k, v in changes.items() if v is not None}},
    )
    if lead.status != previous_status:
        _emit_lead_status(db, lead=lead, previous=previous_status)
    return lead


def _emit_lead_status(db: Session, *, lead: WebsiteLead, previous: str) -> None:
    try:
        from backend.services import integration_service

        integration_service.emit(
            db,
            event_type="lead.status_changed",
            payload={
                "lead_id": lead.id,
                "reference": lead.reference,
                "from": previous,
                "to": lead.status,
            },
        )
    except Exception:  # noqa: BLE001
        logger.exception("lead status webhook emit failed")


def review_opportunity(
    db: Session,
    *,
    user: User,
    opportunity_id: int,
    status: str,
    publish: bool,
    public_title_ar: str | None = None,
    public_title_en: str | None = None,
    public_summary_ar: str | None = None,
    public_summary_en: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> WebsiteOpportunity:
    require_permission(user, Perm.OPPORTUNITY_REVIEW)
    opportunity = db.execute(
        select(WebsiteOpportunity).where(WebsiteOpportunity.id == opportunity_id)
    ).scalar_one_or_none()
    if opportunity is None:
        raise NotFoundError("Opportunity not found.")

    if publish:
        require_permission(user, Perm.OPPORTUNITY_PUBLISH)
        if status != PublicOpportunityStatus.PUBLISHED.value:
            raise ValidationError("A listing must be marked published to be made public.")
        if not (public_title_ar or public_title_en):
            raise ValidationError("Public-facing copy is required before publishing.")

    opportunity.status = status
    opportunity.is_public = bool(publish)
    opportunity.public_title_ar = public_title_ar
    opportunity.public_title_en = public_title_en
    opportunity.public_summary_ar = public_summary_ar
    opportunity.public_summary_en = public_summary_en
    opportunity.reviewed_by_id = user.id
    opportunity.reviewed_at = utcnow()
    db.add(opportunity)
    db.commit()
    db.refresh(opportunity)

    audit_service.record(
        db,
        action=(
            AuditAction.WEBSITE_OPPORTUNITY_PUBLISHED
            if publish
            else AuditAction.WEBSITE_OPPORTUNITY_REVIEWED
        ),
        actor_user_id=user.id,
        entity_type="website_opportunity",
        entity_id=opportunity.id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"status": status, "published": publish},
    )
    return opportunity


def lead_stats(db: Session, *, user: User) -> dict:
    require_permission(user, Perm.LEAD_READ)

    def _grouped(column) -> dict[str, int]:
        rows = db.execute(select(column, func.count(WebsiteLead.id)).group_by(column)).all()
        return {str(key): int(count) for key, count in rows}

    total = int(db.execute(select(func.count(WebsiteLead.id))).scalar_one())
    opportunities_submitted = int(
        db.execute(select(func.count(WebsiteOpportunity.id))).scalar_one()
    )
    opportunities_published = int(
        db.execute(
            select(func.count(WebsiteOpportunity.id)).where(
                WebsiteOpportunity.is_public.is_(True)
            )
        ).scalar_one()
    )
    return {
        "total": total,
        "by_status": _grouped(WebsiteLead.status),
        "by_market": _grouped(WebsiteLead.market),
        "by_service": _grouped(WebsiteLead.service_type),
        "by_campaign": {
            k: v
            for k, v in _grouped(WebsiteLead.utm_campaign).items()
            if k not in {"None", ""}
        },
        "opportunities_submitted": opportunities_submitted,
        "opportunities_published": opportunities_published,
    }


def add_attachment(
    db: Session,
    *,
    lead: WebsiteLead,
    original_filename: str,
    storage_key: str,
    content_type: str | None,
    size_bytes: int,
    is_public: bool = False,
) -> WebsiteLeadAttachment:
    attachment = WebsiteLeadAttachment(
        lead_id=lead.id,
        original_filename=original_filename[:255],
        storage_key=storage_key,
        content_type=content_type,
        size_bytes=size_bytes,
        is_public=is_public,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return attachment


__all__ = [
    "create_lead",
    "list_leads",
    "get_lead",
    "update_lead",
    "review_opportunity",
    "lead_stats",
    "serialise_lead",
    "list_public_opportunities",
    "public_opportunity_photo",
    "add_attachment",
    "routed_team_for",
    "ROUTING_TABLE",
]
