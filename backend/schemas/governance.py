"""Schemas for the Execution 30 owner-decision governance surface.

Kept in its own module so the D01/D03/D04/D09/D11 request shapes are reviewable
together. All enums are closed-set strings validated with a pattern, so a payload
cannot smuggle in an unknown status or kind.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


# --------------------------------------------------------------------------
# D01: accounting-policy proposals (accountant proposes, owner approves)
# --------------------------------------------------------------------------
class PolicyProposalCreateRequest(BaseModel):
    """A draft policy version plus the mandatory proposal reason."""

    kind: str = Field(pattern="^(tax|fiscal_year|invoice|asset|currency)$")
    reason: str = Field(min_length=3, max_length=2000)
    company_id: int | None = None
    value: Decimal | None = None
    value_text: str | None = Field(default=None, max_length=300)
    currency: str | None = Field(default=None, max_length=8)
    description: str | None = Field(default=None, max_length=2000)
    effective_from: date | None = None

    @model_validator(mode="after")
    def _require_a_value(self) -> "PolicyProposalCreateRequest":
        if self.value is None and not self.value_text:
            raise ValueError("A proposal must carry a value or a value_text.")
        return self


class PolicyProposalDecisionRequest(BaseModel):
    """Owner approval or rejection of a proposal."""

    approve: bool
    note: str | None = Field(default=None, max_length=2000)


class PolicyProposalOut(BaseModel):
    id: int
    policy_id: int | None
    company_id: int | None
    kind: str
    reason: str
    previous_value: str | None
    proposed_value: str | None
    proposed_value_text: str | None
    proposed_currency: str | None
    proposed_effective_from: date | None
    status: str
    submitted_by_id: int | None
    decided_by_id: int | None
    decided_at: datetime | None
    decision_note: str | None
    created_at: datetime


# --------------------------------------------------------------------------
# D03/D04: lead assignment events and history
# --------------------------------------------------------------------------
class LeadAssignRequest(BaseModel):
    """Assign or reassign a lead. A reason is required on reassignment."""

    assignee_id: int | None = None
    company_id: int | None = None
    reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _require_a_target(self) -> "LeadAssignRequest":
        if self.assignee_id is None and self.company_id is None:
            raise ValueError("Provide an assignee, a company, or both.")
        return self


class LeadAssignmentOut(BaseModel):
    id: int
    lead_id: int
    action: str
    previous_assignee_id: int | None
    previous_assignee_name_ar: str | None
    new_assignee_id: int | None
    new_assignee_name_ar: str | None
    previous_company_id: int | None
    new_company_id: int | None
    reason: str | None
    actor_id: int | None
    actor_name_ar: str | None
    created_at: datetime


# --------------------------------------------------------------------------
# D09: base-currency change workflow
# --------------------------------------------------------------------------
class CurrencyChangeRequestCreate(BaseModel):
    company_id: int
    requested_currency: str = Field(min_length=2, max_length=8)
    justification: str = Field(min_length=3, max_length=4000)


class CurrencyChangeReviewRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class CurrencyChangeDecisionRequest(BaseModel):
    approve: bool
    effective_year: int | None = Field(default=None, ge=2000, le=2200)
    effective_month: int | None = Field(default=None, ge=1, le=12)
    note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _require_period_on_approval(self) -> "CurrencyChangeDecisionRequest":
        if self.approve and (self.effective_year is None or self.effective_month is None):
            raise ValueError(
                "An effective financial period is required when approving a "
                "currency change."
            )
        return self


class CurrencyChangeOut(BaseModel):
    id: int
    company_id: int
    current_currency: str
    requested_currency: str
    justification: str
    status: str
    effective_year: int | None
    effective_month: int | None
    requested_by_id: int | None
    reviewed_by_id: int | None
    reviewed_at: datetime | None
    review_note: str | None
    decided_by_id: int | None
    decided_at: datetime | None
    decision_note: str | None
    applied_at: datetime | None
    created_at: datetime


# --------------------------------------------------------------------------
# D11: two-factor authentication
# --------------------------------------------------------------------------
class TwoFactorConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=20)


class TwoFactorDisableRequest(BaseModel):
    code: str = Field(min_length=6, max_length=20)


class TwoFactorEnrolOut(BaseModel):
    secret: str
    otpauth_uri: str


class TwoFactorConfirmOut(BaseModel):
    recovery_codes: list[str]


class TwoFactorStatusOut(BaseModel):
    enabled: bool


class TwoFactorLoginVerifyRequest(BaseModel):
    email: str
    password: str
    code: str = Field(min_length=6, max_length=20)


__all__ = [
    "CurrencyChangeDecisionRequest",
    "CurrencyChangeOut",
    "CurrencyChangeRequestCreate",
    "CurrencyChangeReviewRequest",
    "LeadAssignRequest",
    "LeadAssignmentOut",
    "PolicyProposalCreateRequest",
    "PolicyProposalDecisionRequest",
    "PolicyProposalOut",
    "TwoFactorConfirmOut",
    "TwoFactorConfirmRequest",
    "TwoFactorDisableRequest",
    "TwoFactorEnrolOut",
    "TwoFactorLoginVerifyRequest",
    "TwoFactorStatusOut",
]
