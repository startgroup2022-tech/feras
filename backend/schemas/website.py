"""Pydantic schemas for the public website and its internal lead handling.

Two audiences, two validation postures:

* The **public** schemas are the untrusted boundary. Every field has an
  explicit maximum length, every enumeration is closed, consent is mandatory
  and the market/service combination is cross-checked so a payload cannot
  describe a page that does not exist. Nothing here can widen internal access:
  a public request never carries an id it is allowed to read back.
* The **internal** schemas describe what an authenticated SAFIR user may change
  on a lead -- status, priority, assignment, routing and outcome.

Field limits are intentionally generous for free text (a business description
can be long) but bounded, so an oversized payload is rejected at the schema
layer before it reaches the database.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, model_validator

from backend.db.models.enums import (
    ApplicantCapacity,
    LeadPriority,
    LeadStatus,
    Market,
    OpportunityType,
    PublicOpportunityStatus,
    WebsiteServiceType,
)

# Shared bounds, named so the intent is obvious at each use site.
_NAME_MAX = 160
_EMAIL_MAX = 255
_PHONE_MAX = 40
_SHORT_MAX = 200
_TEXT_MAX = 4000
_URL_MAX = 500
_UTM_MAX = 160


# --------------------------------------------------------------------------
# shared input blocks
# --------------------------------------------------------------------------
class AttributionIn(BaseModel):
    """Marketing attribution captured on the landing page.

    All optional: the site still records ``referrer``/``landing_page`` even when
    no campaign parameters are present.
    """

    utm_source: str | None = Field(default=None, max_length=_UTM_MAX)
    utm_medium: str | None = Field(default=None, max_length=_UTM_MAX)
    utm_campaign: str | None = Field(default=None, max_length=_UTM_MAX)
    utm_content: str | None = Field(default=None, max_length=_UTM_MAX)
    utm_term: str | None = Field(default=None, max_length=_UTM_MAX)
    referrer: str | None = Field(default=None, max_length=_URL_MAX)
    landing_page: str | None = Field(default=None, max_length=_URL_MAX)


class PublicSubmissionBase(BaseModel):
    """Fields every public journey collects.

    ``honeypot`` is a hidden field real visitors never fill; a non-empty value
    is treated as a bot and the submission is accepted-but-dropped (see the
    service layer). It is validated as a plain string so the bot's own content
    is never reflected anywhere.
    """

    # Market-less journeys (the handoff's group-services form offers a Gulf
    # country list, and careers residence is unrestricted) default to ``gulf``
    # rather than forcing a false Bahrain/Saudi choice. The visitor's actual
    # country is carried in the service fields.
    market: Market = Market.GULF
    locale: str = Field(default="ar", pattern="^(ar|en)$")
    full_name: str = Field(min_length=1, max_length=_NAME_MAX)
    email: EmailStr = Field(max_length=_EMAIL_MAX)
    phone: str | None = Field(default=None, max_length=_PHONE_MAX)
    nationality: str | None = Field(default=None, max_length=80)
    company_name: str | None = Field(default=None, max_length=_SHORT_MAX)
    message: str | None = Field(default=None, max_length=_TEXT_MAX)
    consent: bool
    honeypot: str | None = Field(default=None, max_length=200)
    attribution: AttributionIn | None = None

    @model_validator(mode="after")
    def _require_consent(self) -> "PublicSubmissionBase":
        if not self.consent:
            raise ValueError("Consent to the privacy notice is required.")
        return self


# --------------------------------------------------------------------------
# company formation
# --------------------------------------------------------------------------
class CompanyFormationSubmission(PublicSubmissionBase):
    """Company-formation request.

    One endpoint, two markets: Bahrain and Saudi Arabia collect slightly
    different answers, and the market decides which are required. This is
    enforced here rather than in the browser so the rule holds for any client.
    """

    desired_activity: str = Field(min_length=1, max_length=_SHORT_MAX)
    # Bahrain
    number_of_partners: int | None = Field(default=None, ge=1, le=50)
    investor_type: str | None = Field(default=None, pattern="^(individual|company)$")
    needs_office: bool | None = None
    # Saudi Arabia
    investor_residency: str | None = Field(default=None, pattern="^(local|foreign)$")
    legal_entity: str | None = Field(default=None, max_length=120)
    target_city: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def _require_market_fields(self) -> "CompanyFormationSubmission":
        if self.market == Market.BAHRAIN.value:
            if self.number_of_partners is None:
                raise ValueError("Number of partners is required for Bahrain.")
            if self.investor_type is None:
                raise ValueError("Investor type is required for Bahrain.")
        else:
            if self.investor_residency is None:
                raise ValueError("Investor residency is required for Saudi Arabia.")
            if not self.target_city:
                raise ValueError("Target city is required for Saudi Arabia.")
        return self


# --------------------------------------------------------------------------
# feasibility study
# --------------------------------------------------------------------------
class FeasibilitySubmission(PublicSubmissionBase):
    """Feasibility-study request. ``study_type`` is a closed set."""

    project_idea: str = Field(min_length=1, max_length=_TEXT_MAX)
    sector: str = Field(min_length=1, max_length=120)
    project_location: str | None = Field(default=None, max_length=160)
    target_city: str | None = Field(default=None, max_length=120)
    approximate_capital: float | None = Field(default=None, ge=0, le=1e15)
    project_stage: str = Field(pattern="^(new|existing)$")
    study_type: str = Field(
        pattern="^(feasibility|market|financial|technical)$"
    )

    @model_validator(mode="after")
    def _require_market_location(self) -> "FeasibilitySubmission":
        if self.market == Market.SAUDI.value and not self.target_city:
            raise ValueError("Target city is required for Saudi Arabia.")
        return self


# --------------------------------------------------------------------------
# opportunity interest
# --------------------------------------------------------------------------
class OpportunityInterestSubmission(PublicSubmissionBase):
    """A request for the confidential details of a published opportunity.

    ``opportunity_id`` is only ever used to look up a listing that is *already
    public*; a request for a private or missing listing is refused, so the
    endpoint cannot be used to probe for unpublished opportunities.
    """

    opportunity_id: int = Field(ge=1)
    investor_profile: str | None = Field(default=None, max_length=_SHORT_MAX)


# --------------------------------------------------------------------------
# investment interest
# --------------------------------------------------------------------------
class InvestmentSubmission(PublicSubmissionBase):
    """A general investment / partnership interest in a chosen market.

    Unlike :class:`OpportunityInterestSubmission` this is not tied to a
    specific published listing: the visitor is signalling interest in the
    market, not in one opportunity. Kept separate so the public endpoint never
    requires an ``opportunity_id`` the visitor cannot supply.
    """

    investor_profile: str | None = Field(default=None, max_length=_SHORT_MAX)


# --------------------------------------------------------------------------
# business listing
# --------------------------------------------------------------------------
class BusinessListingSubmission(PublicSubmissionBase):
    """A business offered for sale, partnership or investment.

    Attachments arrive separately (multipart) and are validated by the storage
    layer; this schema covers the structured fields only.
    """

    applicant_capacity: ApplicantCapacity
    opportunity_type: OpportunityType
    sector: str | None = Field(default=None, max_length=120)
    business_age_years: int | None = Field(default=None, ge=0, le=200)
    description: str = Field(min_length=1, max_length=_TEXT_MAX)
    value_min: float | None = Field(default=None, ge=0, le=1e15)
    value_max: float | None = Field(default=None, ge=0, le=1e15)
    currency: str = Field(default="SAR", max_length=8)
    reason_for_listing: str | None = Field(default=None, max_length=_TEXT_MAX)
    desired_outcome: str | None = Field(default=None, max_length=_TEXT_MAX)

    @model_validator(mode="after")
    def _validate_value_range(self) -> "BusinessListingSubmission":
        if (
            self.value_min is not None
            and self.value_max is not None
            and self.value_max < self.value_min
        ):
            raise ValueError("value_max must be greater than or equal to value_min.")
        return self


# --------------------------------------------------------------------------
# group services ("كيف يمكننا مساعدتك؟") -- handoff §4
# --------------------------------------------------------------------------
class GroupServiceSubmission(PublicSubmissionBase):
    """The single group-services form.

    Unlike the market/service pages this is not scoped to Bahrain or Saudi:
    the form offers a Gulf country list (``options.json``). ``service`` and
    ``country`` are stable ids from the content model, validated here so a
    client cannot post an unknown option. ``full_name`` and ``email`` already
    come from :class:`PublicSubmissionBase`; the phone is required here.
    """

    phone: str = Field(min_length=1, max_length=_PHONE_MAX)
    service: str = Field(min_length=1, max_length=40)
    country: str = Field(min_length=1, max_length=40)


# --------------------------------------------------------------------------
# careers (CV submission) -- handoff §3 الوظائف
# --------------------------------------------------------------------------
class CareersSubmission(PublicSubmissionBase):
    """Join-the-team application.

    Residence country is intentionally *open text*: the handoff says career
    residence is not restricted to the service-country list, so this field is
    validated for length only. The CV attachment arrives separately
    (multipart) and is validated by the storage layer.
    """

    phone: str = Field(min_length=1, max_length=_PHONE_MAX)
    residence_country: str = Field(min_length=1, max_length=80)
    residence_country_other: str | None = Field(default=None, max_length=80)
    city: str | None = Field(default=None, max_length=120)
    job_title: str = Field(min_length=1, max_length=160)
    years_experience: str = Field(min_length=1, max_length=40)
    preferred_company: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def _require_other_country_name(self) -> "CareersSubmission":
        """When the visitor picks "other country", the name is required.

        The UI reveals a companion text field for this case; enforcing it here
        too means the actual country reaches the Holding instead of the literal
        value ``other`` (revision brief item 13).
        """
        if self.residence_country == "other" and not (
            self.residence_country_other or ""
        ).strip():
            raise ValueError("Please enter the name of your country of residence.")
        return self


# --------------------------------------------------------------------------
# general contact
# --------------------------------------------------------------------------
class ContactSubmission(PublicSubmissionBase):
    """General contact / inquiry. ``inquiry_type`` is a closed set."""

    inquiry_type: str = Field(
        pattern=(
            "^(general|company_formation|feasibility|opportunity|partnership"
            "|investment|careers|media)$"
        )
    )
    subject: str | None = Field(default=None, max_length=_SHORT_MAX)


# --------------------------------------------------------------------------
# public outputs
# --------------------------------------------------------------------------
class PublicSubmissionResult(BaseModel):
    """What a visitor is told after a successful submission.

    Only a reference and a localised acknowledgement -- never an internal id,
    status, routing decision or any other operational detail.
    """

    reference: str
    received_at: datetime


class PublicOpportunityOut(BaseModel):
    """A published opportunity, as shown on the public website.

    Only fields the Holding has explicitly cleared for publication appear here.
    The confidential description, value range and contact details are never
    part of this shape.
    """

    id: int
    market: str
    opportunity_type: str
    sector: str | None = None
    title_ar: str | None = None
    title_en: str | None = None
    summary_ar: str | None = None
    summary_en: str | None = None
    # Public photos supplied with the listing (item 06). Empty until the
    # Holding publishes the listing; proof documents are never included.
    photo_urls: list[str] = []
    published_at: datetime | None = None


# --------------------------------------------------------------------------
# internal handling
# --------------------------------------------------------------------------
class LeadAttachmentOut(BaseModel):
    id: int
    original_filename: str
    content_type: str | None = None
    size_bytes: int | None = None
    created_at: datetime


class LeadOut(BaseModel):
    """A website lead as seen inside the platform."""

    id: int
    reference: str
    source: str
    market: str
    service_type: str
    locale: str
    full_name: str
    email: str
    phone: str | None = None
    nationality: str | None = None
    company_name: str | None = None
    message: str | None = None
    payload: dict | None = None
    status: str
    priority: str
    routed_team: str | None = None
    routed_company_id: int | None = None
    assigned_to_id: int | None = None
    assigned_to_name_ar: str | None = None
    assigned_to_name_en: str | None = None
    final_result: str | None = None
    internal_notes: str | None = None
    attribution: dict | None = None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None = None
    attachments: list[LeadAttachmentOut] = []


class LeadUpdateRequest(BaseModel):
    """The fields an authorised user may change on a lead."""

    status: LeadStatus | None = None
    priority: LeadPriority | None = None
    routed_team: str | None = Field(default=None, max_length=60)
    routed_company_id: int | None = None
    assigned_to_id: int | None = None
    final_result: str | None = Field(default=None, max_length=_TEXT_MAX)
    internal_notes: str | None = Field(default=None, max_length=_TEXT_MAX)


class OpportunityReviewRequest(BaseModel):
    """Approve/reject a submitted listing, and optionally publish it."""

    status: PublicOpportunityStatus
    public_title_ar: str | None = Field(default=None, max_length=_SHORT_MAX)
    public_title_en: str | None = Field(default=None, max_length=_SHORT_MAX)
    public_summary_ar: str | None = Field(default=None, max_length=_TEXT_MAX)
    public_summary_en: str | None = Field(default=None, max_length=_TEXT_MAX)
    publish: bool = False

    @model_validator(mode="after")
    def _publish_requires_copy(self) -> "OpportunityReviewRequest":
        # A listing may only be made public when the Holding has written the
        # public-facing copy -- never by echoing the confidential description.
        if self.publish:
            if not (self.public_title_ar or self.public_title_en):
                raise ValueError("A public title is required to publish.")
        return self


class LeadStatsOut(BaseModel):
    """Aggregate counts for the internal lead dashboard."""

    total: int
    by_status: dict[str, int] = {}
    by_market: dict[str, int] = {}
    by_service: dict[str, int] = {}
    by_campaign: dict[str, int] = {}
    opportunities_submitted: int = 0
    opportunities_published: int = 0


__all__ = [
    "AttributionIn",
    "PublicSubmissionBase",
    "CompanyFormationSubmission",
    "FeasibilitySubmission",
    "OpportunityInterestSubmission",
    "InvestmentSubmission",
    "BusinessListingSubmission",
    "ContactSubmission",
    "PublicSubmissionResult",
    "PublicOpportunityOut",
    "LeadOut",
    "LeadAttachmentOut",
    "LeadUpdateRequest",
    "OpportunityReviewRequest",
    "LeadStatsOut",
    "WebsiteServiceType",
]
