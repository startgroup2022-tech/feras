"""Developer-package website contract schemas.

These mirror ``00-shared/api-contract.openapi.yaml`` verbatim: the public
website (https://sup-edu.com/) reads the published fields below and writes only
through the five submission endpoints. Nothing internal is exposed, and no
contact detail of an opportunity owner is ever returned.

The shapes are deliberately narrow -- the same discipline as
:mod:`backend.schemas.website` -- so a change to an internal model can never
widen the public surface by accident.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator

_NAME_MAX = 200
_EMAIL_MAX = 200
_PHONE_MAX = 40
_SHORT_MAX = 200
_TEXT_MAX = 2000

ServiceCode = Literal[
    "company_formation",
    "legal_consultation",
    "feasibility_study",
    "product_distribution",
    "other",
]
SubmissionKind = Literal["business_for_sale", "partnership", "promising_project"]


class SiteInfoOut(BaseModel):
    """Holding contact facts for the site footer/contact page.

    Empty fields are omitted by the website; the API returns them as ``None``
    so the client can decide what to hide.
    """

    nameAr: str
    nameEn: str
    email: str
    phone: str | None = None
    address: str | None = None
    hours: str
    social: dict[str, str] = Field(default_factory=dict)


class CompanyOut(BaseModel):
    """A published group company (``published=true`` only)."""

    id: str
    nameAr: str
    nameEn: str | None = None
    descAr: str | None = None
    descEn: str | None = None
    country: str | None = None
    logoUrl: str | None = None


class OpportunityContractOut(BaseModel):
    """A published opportunity, with no owner contact details."""

    id: str
    title: str
    type: str
    sector: str | None = None
    country: str | None = None
    summary: str | None = None


class VacancyOut(BaseModel):
    """An open position (may be empty)."""

    id: str
    title: str
    location: str | None = None
    department: str | None = None
    summary: str | None = None


class _ContractSubmissionBase(BaseModel):
    """Shared honeypot + consent handling for the contract submissions."""

    consent: bool
    hp: str | None = Field(default=None, max_length=200)
    lang: Literal["ar", "en"] = "ar"

    @model_validator(mode="after")
    def _require_consent(self) -> "_ContractSubmissionBase":
        if not self.consent:
            raise ValueError("Consent to the privacy notice is required.")
        return self


class InquiryIn(_ContractSubmissionBase):
    name: str = Field(min_length=1, max_length=_NAME_MAX)
    email: EmailStr = Field(max_length=_EMAIL_MAX)
    phone: str | None = Field(default=None, max_length=_PHONE_MAX)
    subject: str | None = Field(default=None, max_length=_SHORT_MAX)
    message: str = Field(min_length=1, max_length=_TEXT_MAX)


class ServiceRequestIn(_ContractSubmissionBase):
    service: ServiceCode
    formationCountry: str | None = Field(default=None, max_length=80)
    name: str = Field(min_length=1, max_length=_NAME_MAX)
    email: EmailStr = Field(max_length=_EMAIL_MAX)
    phone: str = Field(min_length=1, max_length=_PHONE_MAX)
    details: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def _require_country_for_formation(self) -> "ServiceRequestIn":
        if self.service == "company_formation" and not (
            self.formationCountry or ""
        ).strip():
            raise ValueError("A country of formation is required.")
        return self


class SubmissionIn(_ContractSubmissionBase):
    kind: SubmissionKind
    title: str = Field(min_length=1, max_length=_SHORT_MAX)
    country: str = Field(min_length=1, max_length=80)
    sector: str | None = Field(default=None, max_length=120)
    summary: str = Field(min_length=1, max_length=_TEXT_MAX)
    contactName: str = Field(min_length=1, max_length=_NAME_MAX)
    contactEmail: EmailStr = Field(max_length=_EMAIL_MAX)
    contactPhone: str = Field(min_length=1, max_length=_PHONE_MAX)


class InterestIn(_ContractSubmissionBase):
    opportunityId: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=_NAME_MAX)
    email: EmailStr = Field(max_length=_EMAIL_MAX)
    phone: str = Field(min_length=1, max_length=_PHONE_MAX)
    message: str | None = Field(default=None, max_length=_TEXT_MAX)


class CvIn(_ContractSubmissionBase):
    name: str = Field(min_length=1, max_length=_NAME_MAX)
    email: EmailStr = Field(max_length=_EMAIL_MAX)
    phone: str = Field(min_length=1, max_length=_PHONE_MAX)
    field: str | None = Field(default=None, max_length=_SHORT_MAX)


class ContractSubmissionResult(BaseModel):
    """The only thing a visitor is told: a reference and a timestamp."""

    reference: str
    receivedAt: str
