"""Public website API under ``/api/v1/public``.

This is the only unauthenticated, write-capable surface in the application, so
it is written defensively:

* **No internal object is ever returned.** A successful submission yields a
  reference and a timestamp; the public opportunity list returns a narrow,
  explicitly-published shape. There is no endpoint here that takes an id and
  returns a record.
* **Strict, closed-set validation.** Every payload is validated by a dedicated
  schema with bounded field lengths and enum-constrained choices, so a malformed
  or oversized request is rejected before it reaches the database.
* **Abuse controls.** A per-IP sliding-window limiter throttles submissions, a
  honeypot field drops bots silently, and uploads are capped by count, type and
  size using the same storage discipline as internal documents.
* **No stack traces, no privilege escalation.** Errors flow through the shared
  handlers, and the endpoint never accepts an actor, role or company id.

The public endpoints deliberately do not share code with the authenticated CRUD
APIs: keeping them separate means a change to an internal endpoint can never
accidentally widen the public surface.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from pydantic import ValidationError as PydanticValidationError

from backend.api.deps import DbSession
from backend.core.config import settings
from backend.core.errors import NotFoundError, RateLimitError, ValidationError
from backend.core.rate_limit import RateLimiter
from backend.core import storage
from backend.schemas import (
    BrandingOut,
    BusinessListingSubmission,
    CareersSubmission,
    CompanyFormationSubmission,
    ContactSubmission,
    FeasibilitySubmission,
    GroupServiceSubmission,
    InvestmentSubmission,
    OpportunityInterestSubmission,
    PublicOpportunityOut,
    PublicSubmissionResult,
)
from backend.db.models.enums import WebsiteServiceType
from backend.services import audit_service, branding_service, website_lead_service
from backend.services import website_cms_service

logger = logging.getLogger("safir.website")

router = APIRouter(prefix="/public", tags=["public-website"])

# One limiter for the whole public form surface, keyed by client IP. Separate
# from the login limiter so marketing traffic cannot lock out sign-in.
_submission_limiter = RateLimiter(
    max_events=settings.PUBLIC_RATE_LIMIT,
    window_seconds=settings.PUBLIC_RATE_WINDOW_SECONDS,
)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = getattr(request, "client", None)
    return getattr(client, "host", None) or "unknown"


def _enforce_rate_limit(request: Request) -> None:
    if not settings.RATE_LIMIT_ENABLED:
        return
    key = f"public:{_client_ip(request)}"
    if not _submission_limiter.check(key):
        raise RateLimitError(
            "Too many submissions from this address. Please try again later."
        )


def _result(lead) -> PublicSubmissionResult:
    return PublicSubmissionResult(reference=lead.reference, received_at=lead.created_at)


def _format_pydantic_errors(exc: PydanticValidationError) -> str:
    """Turn a Pydantic error into one human-readable sentence.

    The multipart listing endpoint validates its JSON part by hand, so its
    errors do not pass through FastAPI's formatter. Summarising here keeps the
    public error response the same shape as every other endpoint.
    """
    messages = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ()) if part != "__root__")
        message = error.get("msg", "Invalid value")
        messages.append(f"{location}: {message}" if location else message)
    return "; ".join(messages) or "The submission is not valid."


# --------------------------------------------------------------------------
# submissions
# --------------------------------------------------------------------------
@router.post(
    "/leads/company-formation",
    response_model=PublicSubmissionResult,
    status_code=status.HTTP_201_CREATED,
)
def submit_company_formation(
    payload: CompanyFormationSubmission, request: Request, db: DbSession
) -> PublicSubmissionResult:
    _enforce_rate_limit(request)
    ctx = audit_service.request_context(request)
    lead = website_lead_service.create_lead(
        db,
        service_type=WebsiteServiceType.COMPANY_FORMATION.value,
        payload=payload,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return _result(lead)


@router.post(
    "/leads/feasibility",
    response_model=PublicSubmissionResult,
    status_code=status.HTTP_201_CREATED,
)
def submit_feasibility(
    payload: FeasibilitySubmission, request: Request, db: DbSession
) -> PublicSubmissionResult:
    _enforce_rate_limit(request)
    ctx = audit_service.request_context(request)
    lead = website_lead_service.create_lead(
        db,
        service_type=WebsiteServiceType.FEASIBILITY_STUDY.value,
        payload=payload,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return _result(lead)


@router.post(
    "/leads/opportunity-interest",
    response_model=PublicSubmissionResult,
    status_code=status.HTTP_201_CREATED,
)
def submit_opportunity_interest(
    payload: OpportunityInterestSubmission, request: Request, db: DbSession
) -> PublicSubmissionResult:
    _enforce_rate_limit(request)
    ctx = audit_service.request_context(request)
    lead = website_lead_service.create_lead(
        db,
        service_type=WebsiteServiceType.OPPORTUNITY_INTEREST.value,
        payload=payload,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return _result(lead)


@router.post(
    "/leads/investment",
    response_model=PublicSubmissionResult,
    status_code=status.HTTP_201_CREATED,
)
def submit_investment(
    payload: InvestmentSubmission, request: Request, db: DbSession
) -> PublicSubmissionResult:
    _enforce_rate_limit(request)
    ctx = audit_service.request_context(request)
    lead = website_lead_service.create_lead(
        db,
        service_type=WebsiteServiceType.INVESTMENT.value,
        payload=payload,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return _result(lead)


@router.post(
    "/leads/contact",
    response_model=PublicSubmissionResult,
    status_code=status.HTTP_201_CREATED,
)
def submit_contact(
    payload: ContactSubmission, request: Request, db: DbSession
) -> PublicSubmissionResult:
    _enforce_rate_limit(request)
    ctx = audit_service.request_context(request)
    lead = website_lead_service.create_lead(
        db,
        service_type=WebsiteServiceType.GENERAL_CONTACT.value,
        payload=payload,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return _result(lead)


@router.post(
    "/leads/group-service",
    response_model=PublicSubmissionResult,
    status_code=status.HTTP_201_CREATED,
)
def submit_group_service(
    payload: GroupServiceSubmission, request: Request, db: DbSession
) -> PublicSubmissionResult:
    """The handoff's single group-services form ("كيف يمكننا مساعدتك؟")."""
    _enforce_rate_limit(request)
    ctx = audit_service.request_context(request)
    lead = website_lead_service.create_lead(
        db,
        service_type=WebsiteServiceType.GROUP_SERVICE.value,
        payload=payload,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return _result(lead)


@router.post(
    "/leads/business-listing",
    response_model=PublicSubmissionResult,
    status_code=status.HTTP_201_CREATED,
)
async def submit_business_listing(
    request: Request,
    db: DbSession,
    payload: Annotated[str, Form()],
    files: Annotated[list[UploadFile], File()] = [],
) -> PublicSubmissionResult:
    """Business/opportunity listing.

    Sent as ``multipart/form-data`` because it may carry attachments: the
    structured fields arrive as a JSON string in ``payload`` and the files in
    ``files``. The JSON is parsed into the same schema used elsewhere, so the
    validation rules cannot diverge between transports.
    """
    _enforce_rate_limit(request)

    try:
        data = json.loads(payload)
    except (TypeError, ValueError) as exc:
        raise ValidationError("The submission payload is not valid JSON.") from exc
    if not isinstance(data, dict):
        raise ValidationError("The submission payload must be a JSON object.")

    try:
        submission = BusinessListingSubmission.model_validate(data)
    except PydanticValidationError as exc:
        # Re-raise through the shared ValidationError so the response shape is
        # identical to the JSON-body endpoints (which FastAPI validates itself).
        raise ValidationError(_format_pydantic_errors(exc)) from exc

    if len(files) > settings.PUBLIC_MAX_ATTACHMENTS:
        raise ValidationError(
            f"At most {settings.PUBLIC_MAX_ATTACHMENTS} attachments are allowed."
        )

    ctx = audit_service.request_context(request)
    lead = website_lead_service.create_lead(
        db,
        service_type=WebsiteServiceType.BUSINESS_LISTING.value,
        payload=submission,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )

    # Only persist files for a genuine submission (a honeypot drop returns a
    # synthetic lead whose status is closed and whose id is not persisted).
    await _persist_uploads(db, lead=lead, files=files)

    return _result(lead)


async def _persist_uploads(
    db: DbSession, *, lead, files: list[UploadFile]
) -> None:
    """Validate and store public attachments for a persisted lead.

    Shared by the business-listing and careers endpoints so the upload
    discipline (count cap, content-type allow-list, opaque storage key) cannot
    diverge between forms. A honeypot-dropped lead has no id and stores
    nothing.
    """
    if lead.id is None:
        return
    for upload in files:
        if not upload.filename:
            continue
        content = await upload.read()
        extension = storage.validate_upload(
            filename=upload.filename,
            content_type=upload.content_type,
            size=len(content),
        )
        key = storage.store_bytes(data=content, extension=extension)
        website_lead_service.add_attachment(
            db,
            lead=lead,
            original_filename=upload.filename,
            storage_key=key,
            content_type=upload.content_type,
            size_bytes=len(content),
        )


@router.post(
    "/leads/careers",
    response_model=PublicSubmissionResult,
    status_code=status.HTTP_201_CREATED,
)
async def submit_careers(
    request: Request,
    db: DbSession,
    payload: Annotated[str, Form()],
    files: Annotated[list[UploadFile], File()] = [],
) -> PublicSubmissionResult:
    """Careers application (handoff §3 الوظائف).

    Multipart because it carries a CV. The structured fields arrive as a JSON
    string in ``payload`` exactly like the business-listing endpoint, so the
    same strict schema validates the data regardless of transport.
    """
    _enforce_rate_limit(request)

    try:
        data = json.loads(payload)
    except (TypeError, ValueError) as exc:
        raise ValidationError("The submission payload is not valid JSON.") from exc
    if not isinstance(data, dict):
        raise ValidationError("The submission payload must be a JSON object.")

    try:
        submission = CareersSubmission.model_validate(data)
    except PydanticValidationError as exc:
        raise ValidationError(_format_pydantic_errors(exc)) from exc

    if len(files) > settings.PUBLIC_MAX_ATTACHMENTS:
        raise ValidationError(
            f"At most {settings.PUBLIC_MAX_ATTACHMENTS} attachments are allowed."
        )

    ctx = audit_service.request_context(request)
    lead = website_lead_service.create_lead(
        db,
        service_type=WebsiteServiceType.CAREERS.value,
        payload=submission,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    await _persist_uploads(db, lead=lead, files=files)
    return _result(lead)


# --------------------------------------------------------------------------
# published opportunities (public read)
# --------------------------------------------------------------------------
@router.get("/opportunities", response_model=list[PublicOpportunityOut])
def public_opportunities(
    db: DbSession,
    market: str | None = None,
    type: str | None = None,
) -> list[PublicOpportunityOut]:
    """Published listings only. Nothing confidential is ever returned."""
    rows = website_lead_service.list_public_opportunities(
        db, market=market, opportunity_type=type
    )
    return [PublicOpportunityOut(**row) for row in rows]


# --------------------------------------------------------------------------
# branding (public read)
# --------------------------------------------------------------------------
@router.get("/branding", response_model=BrandingOut)
def public_branding(db: DbSession) -> BrandingOut:
    """Public branding values (the logo URL). No internal data is exposed."""
    return BrandingOut(**branding_service.branding_payload(db))


@router.get("/branding/logo", include_in_schema=False)
def public_branding_logo(db: DbSession) -> Response:
    """Stream the uploaded logo, or 404 when none is set.

    Unauthenticated by design: the logo is public marketing material. Only a
    file that exists under the branding root is ever served; the storage key
    is never revealed in a URL.
    """
    path, content_type = branding_service.resolve_logo(db)
    if path is None:
        raise NotFoundError("No logo is configured.")
    return FileResponse(
        str(path),
        media_type=content_type or "application/octet-stream",
        headers={"Cache-Control": "public, max-age=86400"},
    )


# --------------------------------------------------------------------------
# website CMS media (public read)
# --------------------------------------------------------------------------
@router.get("/website/media/{media_id}", include_in_schema=False)
def public_website_media(media_id: int, db: DbSession) -> Response:
    """Stream a *public* CMS media asset, or 404 otherwise.

    Unauthenticated by design, so the boundary matters: the service only
    resolves assets whose ``visibility`` is ``public``. A private asset (or an
    id that does not exist) is indistinguishable from a missing file.
    """
    path, content_type = website_cms_service.resolve_media_for_public(db, media_id)
    return FileResponse(
        str(path),
        media_type=content_type or "application/octet-stream",
        headers={"Cache-Control": "public, max-age=86400"},
    )
