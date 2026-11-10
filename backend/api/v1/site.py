"""Developer-package public website contract (``/api/public``).

The developer package (``00-shared/api-contract.openapi.yaml``) specifies the
exact public surface the marketing website consumes. It is served under its own
prefix (``settings.PUBLIC_SITE_API_PREFIX``) so it never collides with the
platform's ``/api/v1/public`` surface, which is the internal lead-capture API.

Everything here reuses the existing, hardened services: submissions become the
same routed :class:`WebsiteLead` rows, published companies come from the CMS,
and the honeypot + rate-limit + consent rules are unchanged. No new write path
is invented and no internal object is ever returned.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile, status
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select

from backend.api.deps import DbSession
from backend.core import storage
from backend.core.config import settings
from backend.core.errors import RateLimitError, ValidationError
from backend.core.rate_limit import RateLimiter
from backend.db.base import utcnow
from backend.db.models.enums import (
    ApplicantCapacity,
    Market,
    OpportunityType,
    WebsiteServiceType,
)
from backend.db.models.website import WebsiteOpportunity
from backend.db.models.website_cms import WebsiteCompany, WebsiteSettings
from backend.schemas.site_contract import (
    CompanyOut,
    ContractSubmissionResult,
    CvIn,
    InquiryIn,
    InterestIn,
    OpportunityContractOut,
    ServiceRequestIn,
    SiteInfoOut,
    SubmissionIn,
    VacancyOut,
)
from backend.schemas.website import (
    BusinessListingSubmission,
    CareersSubmission,
    CompanyFormationSubmission,
    ContactSubmission,
    GroupServiceSubmission,
    OpportunityInterestSubmission,
)
from backend.services import audit_service, website_cms_service, website_lead_service

logger = logging.getLogger("safir.website.contract")

router = APIRouter(prefix=settings.PUBLIC_SITE_API_PREFIX, tags=["public-site"])

# Contract request bodies are JSON (except submissions/cv which are multipart).
# Reuse the same shared limiter as the platform's public surface so a single
# abuser cannot exhaust either path.
_submission_limiter = RateLimiter(
    max_events=settings.PUBLIC_RATE_LIMIT,
    window_seconds=settings.PUBLIC_RATE_WINDOW_SECONDS,
)

_KIND_TO_OPPORTUNITY_TYPE = {
    "business_for_sale": OpportunityType.FULL_SALE.value,
    "partnership": OpportunityType.STRATEGIC_PARTNER.value,
    "promising_project": OpportunityType.INVESTMENT.value,
}


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = getattr(request, "client", None)
    return getattr(client, "host", None) or "unknown"


def _enforce_rate_limit(request: Request) -> None:
    if not settings.RATE_LIMIT_ENABLED:
        return
    if not _submission_limiter.check(f"public-site:{_client_ip(request)}"):
        raise RateLimitError(
            "Too many submissions from this address. Please try again later."
        )


def _result(lead) -> ContractSubmissionResult:
    return ContractSubmissionResult(
        reference=lead.reference, receivedAt=lead.created_at.isoformat()
    )


def _market_for_country(country: str | None) -> str:
    """Route a free-text country to the internal market bucket."""
    value = (country or "").strip().lower()
    if "saudi" in value or value in {"sa", "ksa", "السعودية"}:
        return Market.SAUDI.value
    if "bahrain" in value or value in {"bh", "البحرين"}:
        return Market.BAHRAIN.value
    return Market.GULF.value


# --------------------------------------------------------------------------
# reads
# --------------------------------------------------------------------------
@router.get("/site-info", response_model=SiteInfoOut)
def site_info(db: DbSession) -> SiteInfoOut:
    """Holding identity. Empty optional fields are returned as ``None``."""
    settings_row = db.get(WebsiteSettings, 1)
    social: dict[str, str] = {}
    if settings_row is not None and isinstance(settings_row.social_links, dict):
        social = {
            str(k): str(v) for k, v in settings_row.social_links.items() if v
        }
    return SiteInfoOut(
        nameAr=(
            (settings_row.site_name_ar if settings_row else None)
            or website_lead_service.HOLDING_NAME_AR
        ),
        nameEn=(
            (settings_row.site_name_en if settings_row else None)
            or website_lead_service.HOLDING_NAME_EN
        ),
        email=(
            (settings_row.contact_email if settings_row else None)
            or website_lead_service.HOLDING_EMAIL
        ),
        phone=(settings_row.contact_phone if settings_row else None)
        or website_lead_service.HOLDING_PHONE,
        address=website_lead_service.HOLDING_ADDRESS,
        hours=website_lead_service.HOLDING_HOURS,
        social=social,
    )


@router.get("/companies", response_model=list[CompanyOut])
def companies(db: DbSession) -> list[CompanyOut]:
    """Published group companies only (``is_visible``), in display order."""
    rows = db.scalars(
        select(WebsiteCompany)
        .where(WebsiteCompany.is_visible.is_(True))
        .order_by(WebsiteCompany.display_order, WebsiteCompany.id)
    ).all()
    return [
        CompanyOut(
            id=f"PUB-{row.id:03d}",
            nameAr=row.name_ar,
            nameEn=row.name_en or None,
            descAr=row.description_ar,
            descEn=row.description_en,
            country=row.country,
            logoUrl=website_cms_service.public_media_url(row.logo_media_id),
        )
        for row in rows
    ]


@router.get("/opportunities", response_model=list[OpportunityContractOut])
def opportunities(db: DbSession) -> list[OpportunityContractOut]:
    """Published opportunities only; no owner contact details are ever returned."""
    rows = website_lead_service.list_public_opportunities(db)
    out: list[OpportunityContractOut] = []
    for row in rows:
        out.append(
            OpportunityContractOut(
                id=str(row["id"]),
                title=row.get("title_ar") or row.get("title_en") or "",
                type=row.get("opportunity_type") or "",
                sector=row.get("sector"),
                country=row.get("market"),
                summary=row.get("summary_ar") or row.get("summary_en"),
            )
        )
    return out


@router.get("/vacancies", response_model=list[VacancyOut])
def vacancies() -> list[VacancyOut]:
    """Open positions. There is no vacancy model yet, so this is empty by design."""
    return []


# --------------------------------------------------------------------------
# writes
# --------------------------------------------------------------------------
@router.post(
    "/inquiries",
    response_model=ContractSubmissionResult,
    status_code=status.HTTP_201_CREATED,
)
def submit_inquiry(
    payload: InquiryIn, request: Request, db: DbSession
) -> ContractSubmissionResult:
    _enforce_rate_limit(request)
    ctx = audit_service.request_context(request)
    lead = website_lead_service.create_lead(
        db,
        service_type=WebsiteServiceType.GENERAL_CONTACT.value,
        payload=ContactSubmission(
            full_name=payload.name,
            email=payload.email,
            phone=payload.phone,
            subject=payload.subject,
            message=payload.message,
            inquiry_type="general",
            consent=payload.consent,
            honeypot=payload.hp,
            locale=payload.lang,
        ),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return _result(lead)


@router.post(
    "/service-requests",
    response_model=ContractSubmissionResult,
    status_code=status.HTTP_201_CREATED,
)
def submit_service_request(
    payload: ServiceRequestIn, request: Request, db: DbSession
) -> ContractSubmissionResult:
    """The contract's single service form, mapped onto the internal taxonomy.

    ``company_formation`` carries the country into the formation-specific
    fields; every other service code is a general group-service enquiry, so the
    lead is still routed to the right team without inventing a new schema.
    """
    _enforce_rate_limit(request)
    ctx = audit_service.request_context(request)
    market = _market_for_country(payload.formationCountry)
    if payload.service == "company_formation":
        submission = CompanyFormationSubmission(
            full_name=payload.name,
            email=payload.email,
            phone=payload.phone,
            desired_activity=payload.details[:200],
            consent=payload.consent,
            honeypot=payload.hp,
            locale=payload.lang,
            market=Market(market),
            # Supply the market-specific answers the internal schema requires so
            # the contract's single form satisfies either branch.
            number_of_partners=1 if market == Market.BAHRAIN.value else None,
            investor_type="company" if market == Market.BAHRAIN.value else None,
            investor_residency="foreign" if market != Market.BAHRAIN.value else None,
            target_city=(payload.formationCountry or "—")[:120],
        )
        service_type = WebsiteServiceType.COMPANY_FORMATION.value
    else:
        submission = GroupServiceSubmission(
            full_name=payload.name,
            email=payload.email,
            phone=payload.phone,
            service=payload.service,
            country=payload.formationCountry or "gulf",
            message=payload.details,
            consent=payload.consent,
            honeypot=payload.hp,
            locale=payload.lang,
            market=Market(market),
        )
        service_type = WebsiteServiceType.GROUP_SERVICE.value
    lead = website_lead_service.create_lead(
        db,
        service_type=service_type,
        payload=submission,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return _result(lead)


@router.post(
    "/submissions",
    response_model=ContractSubmissionResult,
    status_code=status.HTTP_201_CREATED,
)
async def submit_business(
    request: Request,
    db: DbSession,
    kind: Annotated[str, Form()],
    title: Annotated[str, Form()],
    country: Annotated[str, Form()],
    summary: Annotated[str, Form()],
    contactName: Annotated[str, Form()],
    contactEmail: Annotated[str, Form()],
    contactPhone: Annotated[str, Form()],
    consent: bool = Form(False),
    sector: str | None = Form(None),
    hp: str | None = Form(None),
    lang: str = Form("ar"),
    attachment: UploadFile | None = File(None),
) -> ContractSubmissionResult:
    """``multipart/form-data`` because it carries an optional PDF/Word study."""
    _enforce_rate_limit(request)
    try:
        data = SubmissionIn(
            kind=kind,  # type: ignore[arg-type]
            title=title,
            country=country,
            sector=sector,
            summary=summary,
            contactName=contactName,
            contactEmail=contactEmail,
            contactPhone=contactPhone,
            consent=consent,
            hp=hp,
            lang=lang,  # type: ignore[arg-type]
        )
    except PydanticValidationError as exc:
        raise ValidationError("; ".join(str(e["msg"]) for e in exc.errors())) from exc

    ctx = audit_service.request_context(request)
    lead = website_lead_service.create_lead(
        db,
        service_type=WebsiteServiceType.BUSINESS_LISTING.value,
        payload=BusinessListingSubmission(
            full_name=data.contactName,
            email=data.contactEmail,
            phone=data.contactPhone,
            applicant_capacity=ApplicantCapacity.OWNER,
            opportunity_type=OpportunityType(_KIND_TO_OPPORTUNITY_TYPE[data.kind]),
            sector=data.sector,
            description=f"{data.title} — {data.summary}",
            company_name=data.title,
            consent=data.consent,
            honeypot=data.hp,
            locale=data.lang,
            market=Market(_market_for_country(data.country)),
        ),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    files = [attachment] if attachment is not None and attachment.filename else []
    if files:
        await website_lead_service.persist_public_uploads(
            db, lead=lead, files=files
        )
    return _result(lead)


@router.post(
    "/interests",
    response_model=ContractSubmissionResult,
    status_code=status.HTTP_201_CREATED,
)
def submit_interest(
    payload: InterestIn, request: Request, db: DbSession
) -> ContractSubmissionResult:
    _enforce_rate_limit(request)
    # The opportunity id must be a published listing; an unknown or private id
    # is refused so the endpoint cannot probe unpublished opportunities.
    opportunity = db.get(WebsiteOpportunity, int(payload.opportunityId)) if payload.opportunityId.isdigit() else None
    if opportunity is None or not opportunity.is_public:
        raise ValidationError("The requested opportunity is not available.")
    ctx = audit_service.request_context(request)
    lead = website_lead_service.create_lead(
        db,
        service_type=WebsiteServiceType.OPPORTUNITY_INTEREST.value,
        payload=OpportunityInterestSubmission(
            full_name=payload.name,
            email=payload.email,
            phone=payload.phone,
            message=payload.message,
            opportunity_id=opportunity.id,
            market=Market(opportunity.market),
            consent=payload.consent,
            honeypot=payload.hp,
            locale=payload.lang,
        ),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return _result(lead)


@router.post(
    "/cv",
    response_model=ContractSubmissionResult,
    status_code=status.HTTP_201_CREATED,
)
async def submit_cv(
    request: Request,
    db: DbSession,
    name: Annotated[str, Form()],
    email: Annotated[str, Form()],
    phone: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    field: str | None = Form(None),
    consent: bool = Form(False),
    hp: str | None = Form(None),
    lang: str = Form("ar"),
) -> ContractSubmissionResult:
    """CV submission. The CV lives with the Holding for 6 months, then is deleted."""
    _enforce_rate_limit(request)
    try:
        data = CvIn(
            name=name,
            email=email,
            phone=phone,
            field=field,
            consent=consent,
            hp=hp,
            lang=lang,  # type: ignore[arg-type]
        )
    except PydanticValidationError as exc:
        raise ValidationError("; ".join(str(e["msg"]) for e in exc.errors())) from exc

    ctx = audit_service.request_context(request)
    lead = website_lead_service.create_lead(
        db,
        service_type=WebsiteServiceType.CAREERS.value,
        payload=CareersSubmission(
            full_name=data.name,
            email=data.email,
            phone=data.phone,
            residence_country="other",
            residence_country_other="not-provided",
            job_title=data.field or "—",
            years_experience="—",
            consent=data.consent,
            honeypot=data.hp,
            locale=data.lang,
        ),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    if file is not None and file.filename:
        await website_lead_service.persist_public_uploads(
            db, lead=lead, files=[file], validator=storage.validate_cv_upload
        )
    return _result(lead)
