"""Pydantic request/response schemas.

Central validation lives here: every payload entering the API is parsed by one
of these models, so validation rules are declared once and cannot drift between
endpoints. Field constraints double as the first line of defence against
malformed or hostile input.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from backend.db.models.enums import (
    CompanyHealth,
    CompanyStatus,
    CompanyType,
    DepartmentStatus,
    HoldingStatus,
    OwnershipStatus,
    PositionStatus,
    ReportClarificationKind,
    SupportCategory,
    SupportStatus,
)

# Deliberately syntax-only. Public email validators reject reserved/internal
# TLDs (``.local``, private zones) outright, which would make it impossible to
# register the Holding's own staff. This platform never sends mail itself, so
# deliverability is not this layer's concern; strict syntax is.
_LOCAL_PART = re.compile(r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+$")
_LABEL = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")

MAX_EMAIL_LENGTH = 254


def _validate_internal_email(value: str) -> str:
    """Validate and normalise an email address's syntax."""
    value = (value or "").strip()
    if not value or len(value) > MAX_EMAIL_LENGTH:
        raise ValueError("Not a valid email address.")
    if value.count("@") != 1:
        raise ValueError("Not a valid email address.")
    local, _, domain = value.partition("@")
    if not local or len(local) > 64:
        raise ValueError("Not a valid email address.")
    if local.startswith(".") or local.endswith(".") or ".." in local:
        raise ValueError("Not a valid email address.")
    if not _LOCAL_PART.match(local):
        raise ValueError("Not a valid email address.")
    labels = domain.split(".")
    if len(labels) < 2 or any(not _LABEL.match(label) for label in labels):
        raise ValueError("Not a valid email address.")
    return f"{local}@{domain}".lower()


# Email type used across the API: syntax-checked, internal-domain friendly.
InternalEmail = Annotated[str, AfterValidator(_validate_internal_email)]


# --------------------------------------------------------------------------
# auth
# --------------------------------------------------------------------------
class LoginRequest(BaseModel):
    email: InternalEmail
    password: str = Field(min_length=1, max_length=72)
    # D11: the second factor, required when the account has 2FA enabled. Kept
    # optional so the schema is backwards compatible; the service enforces it.
    code: str | None = Field(default=None, min_length=6, max_length=20)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class ChangePasswordRequest(BaseModel):
    """Self-service password change (D11 account access).

    The current password is required so a stolen access token alone cannot be
    used to take over the account.
    """

    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=8, max_length=72)


class AdminSetPasswordRequest(BaseModel):
    """Owner/administrator sets a temporary password for another account."""

    new_password: str = Field(min_length=8, max_length=72)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: InternalEmail
    full_name_ar: str
    full_name_en: str | None
    is_active: bool
    # ``role_code`` is the primary role and is always populated for a user that
    # has a role row. ``roles`` mirrors it as a list so a future many-to-many
    # role model can be exposed without breaking this contract.
    role_code: str
    role_name_ar: str | None = None
    role_name_en: str | None = None
    roles: list[str] = []
    permissions: list[str] = []
    company_ids: list[int] = []
    department_id: int | None = None
    last_login_at: datetime | None = None


class CreateUserRequest(BaseModel):
    email: InternalEmail
    password: str = Field(min_length=8, max_length=72)
    full_name_ar: str = Field(min_length=1, max_length=180)
    full_name_en: str | None = Field(default=None, max_length=180)
    role_code: str = Field(min_length=2, max_length=40)
    company_ids: list[int] = Field(default_factory=list)


class UpdateUserRequest(BaseModel):
    """Partial update. Every field is optional; omitted fields are untouched."""

    full_name_ar: str | None = Field(default=None, min_length=1, max_length=180)
    full_name_en: str | None = Field(default=None, max_length=180)
    role_code: str | None = Field(default=None, min_length=2, max_length=40)
    is_active: bool | None = None
    department_id: int | None = None


class CompanyAccessRequest(BaseModel):
    company_id: int
    can_read: bool = True
    can_write: bool = True
    is_primary: bool = False


# --------------------------------------------------------------------------
# companies
# --------------------------------------------------------------------------
class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name_ar: str
    name_en: str | None = None
    sector: str | None
    status: str
    health: str
    contact_email: str | None
    legal_name_ar: str | None = None
    legal_name_en: str | None = None
    company_type: str = CompanyType.SUBSIDIARY.value
    country: str | None = None
    commercial_registration: str | None = None
    currency: str = "SAR"
    address: str | None = None
    phone: str | None = None
    founded_on: date | None = None
    tracking_start_date: date | None = None
    # ---- company setup wizard (deck slides 50-52) ----
    trade_name_ar: str | None = None
    trade_name_en: str | None = None
    activity: str | None = None
    capital_amount: Decimal | None = None
    fiscal_year_start_month: int | None = None
    fiscal_year_end_month: int | None = None
    default_language: str = "ar"
    template_effective_from: date | None = None
    access_scope: str | None = None
    # Localization setup (deck slides 105/106): the per-entity target and the
    # calculation-rule edition. Null means unset -> the board shows غير مُعدّ.
    localization_target_pct: Decimal | None = None
    localization_rule_version: str | None = None
    localization_rule_effective_from: date | None = None
    # The deck's portfolio list (slide 134) filters by "مدير"; the manager is
    # derived from the company's granted company-manager user, so the picker can
    # show a name rather than a bare id. Null when the company has no manager.
    manager_user_id: int | None = None
    manager_name_ar: str | None = None
    manager_name_en: str | None = None


class CompanyCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    name_ar: str = Field(min_length=1, max_length=180)
    name_en: str | None = Field(default=None, max_length=180)
    # F-01 / AC-03: the sector is mandatory; a company may not be registered
    # without one.
    sector: str = Field(min_length=1, max_length=120)
    contact_email: InternalEmail | None = None
    legal_name_ar: str | None = Field(default=None, max_length=200)
    legal_name_en: str | None = Field(default=None, max_length=200)
    company_type: str = Field(default=CompanyType.SUBSIDIARY.value, max_length=30)
    country: str | None = Field(default=None, max_length=80)
    commercial_registration: str | None = Field(default=None, max_length=80)
    currency: str = Field(default="SAR", min_length=3, max_length=8)
    address: str | None = Field(default=None, max_length=1000)
    phone: str | None = Field(default=None, max_length=40)
    # AC-03: the founding date and the monitoring-start date are distinct.
    founded_on: date | None = None
    tracking_start_date: date | None = None
    # The wizard's step 2 records the company's status (S03: نشطة/معلقة/مؤرشفة).
    status: str = Field(default=CompanyStatus.ACTIVE.value, max_length=20)
    # ---- company setup wizard (deck slides 50-52) ----
    trade_name_ar: str | None = Field(default=None, max_length=180)
    trade_name_en: str | None = Field(default=None, max_length=180)
    activity: str | None = Field(default=None, max_length=300)
    capital_amount: Decimal | None = Field(default=None, ge=0)
    fiscal_year_start_month: int | None = Field(default=None, ge=1, le=12)
    fiscal_year_end_month: int | None = Field(default=None, ge=1, le=12)
    default_language: str = Field(default="ar", max_length=8)
    template_effective_from: date | None = None
    access_scope: str | None = Field(default=None, max_length=40)
    # Localization setup (deck slides 105/106).
    localization_target_pct: Decimal | None = Field(default=None, ge=0, le=100)
    localization_rule_version: str | None = Field(default=None, max_length=120)
    localization_rule_effective_from: date | None = None

    @field_validator("status")
    @classmethod
    def _valid_create_status(cls, value: str) -> str:
        allowed = {s.value for s in CompanyStatus}
        if value not in allowed:
            raise ValueError(f"status must be one of {sorted(allowed)}")
        return value

    @field_validator("default_language")
    @classmethod
    def _valid_default_language(cls, value: str) -> str:
        allowed = {"ar", "en", "both"}
        if value not in allowed:
            raise ValueError(f"default_language must be one of {sorted(allowed)}")
        return value

    @field_validator("company_type")
    @classmethod
    def _valid_company_type(cls, value: str) -> str:
        allowed = {t.value for t in CompanyType}
        if value not in allowed:
            raise ValueError(f"company_type must be one of {sorted(allowed)}")
        return value


class CompanyUpdateRequest(BaseModel):
    """Partial update of a subsidiary's descriptive fields."""

    name_ar: str | None = Field(default=None, min_length=1, max_length=180)
    name_en: str | None = Field(default=None, min_length=1, max_length=180)
    sector: str | None = Field(default=None, min_length=1, max_length=120)
    health: str | None = Field(default=None, max_length=20)
    status: str | None = Field(default=None, max_length=20)
    contact_email: InternalEmail | None = None
    legal_name_ar: str | None = Field(default=None, max_length=200)
    legal_name_en: str | None = Field(default=None, max_length=200)
    company_type: str | None = Field(default=None, max_length=30)
    country: str | None = Field(default=None, max_length=80)
    commercial_registration: str | None = Field(default=None, max_length=80)
    currency: str | None = Field(default=None, min_length=3, max_length=8)
    address: str | None = Field(default=None, max_length=1000)
    phone: str | None = Field(default=None, max_length=40)
    founded_on: date | None = None
    tracking_start_date: date | None = None
    # ---- company setup wizard (deck slides 50-52) ----
    trade_name_ar: str | None = Field(default=None, max_length=180)
    trade_name_en: str | None = Field(default=None, max_length=180)
    activity: str | None = Field(default=None, max_length=300)
    capital_amount: Decimal | None = Field(default=None, ge=0)
    fiscal_year_start_month: int | None = Field(default=None, ge=1, le=12)
    fiscal_year_end_month: int | None = Field(default=None, ge=1, le=12)
    default_language: str | None = Field(default=None, max_length=8)
    template_effective_from: date | None = None
    access_scope: str | None = Field(default=None, max_length=40)
    # Localization setup (deck slides 105/106).
    localization_target_pct: Decimal | None = Field(default=None, ge=0, le=100)
    localization_rule_version: str | None = Field(default=None, max_length=120)
    localization_rule_effective_from: date | None = None

    @field_validator("default_language")
    @classmethod
    def _valid_default_language(cls, value: str | None) -> str | None:
        if value is None:
            return None
        allowed = {"ar", "en", "both"}
        if value not in allowed:
            raise ValueError(f"default_language must be one of {sorted(allowed)}")
        return value

    @field_validator("health")
    @classmethod
    def _valid_health(cls, value: str | None) -> str | None:
        if value is None:
            return None
        allowed = {h.value for h in CompanyHealth}
        if value not in allowed:
            raise ValueError(f"health must be one of {sorted(allowed)}")
        return value

    @field_validator("status")
    @classmethod
    def _valid_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        allowed = {s.value for s in CompanyStatus}
        if value not in allowed:
            raise ValueError(f"status must be one of {sorted(allowed)}")
        return value

    @field_validator("company_type")
    @classmethod
    def _valid_company_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        allowed = {t.value for t in CompanyType}
        if value not in allowed:
            raise ValueError(f"company_type must be one of {sorted(allowed)}")
        return value


# --------------------------------------------------------------------------
# monthly reports
# --------------------------------------------------------------------------
class MonthlyReportCreateRequest(BaseModel):
    company_id: int
    period_year: int = Field(ge=2000, le=2100)
    period_month: int = Field(ge=1, le=12)

    revenue: Decimal | None = Field(default=None, ge=0)
    expenses: Decimal | None = Field(default=None, ge=0)
    net_result: Decimal | None = None
    outstanding_receivables: Decimal | None = Field(default=None, ge=0)

    important_developments: str | None = Field(default=None, max_length=5000)
    new_customers: str | None = Field(default=None, max_length=5000)
    new_opportunities: str | None = Field(default=None, max_length=5000)
    major_problems: str | None = Field(default=None, max_length=5000)
    support_required: str | None = Field(default=None, max_length=5000)
    marketing_status: str | None = Field(default=None, max_length=5000)
    business_development_status: str | None = Field(default=None, max_length=5000)
    management_notes: str | None = Field(default=None, max_length=5000)


class MonthlyReportUpdateRequest(BaseModel):
    """All fields optional; only drafts may be updated."""

    revenue: Decimal | None = Field(default=None, ge=0)
    expenses: Decimal | None = Field(default=None, ge=0)
    net_result: Decimal | None = None
    outstanding_receivables: Decimal | None = Field(default=None, ge=0)
    important_developments: str | None = Field(default=None, max_length=5000)
    new_customers: str | None = Field(default=None, max_length=5000)
    new_opportunities: str | None = Field(default=None, max_length=5000)
    major_problems: str | None = Field(default=None, max_length=5000)
    support_required: str | None = Field(default=None, max_length=5000)
    marketing_status: str | None = Field(default=None, max_length=5000)
    business_development_status: str | None = Field(default=None, max_length=5000)
    management_notes: str | None = Field(default=None, max_length=5000)


class ReportReturnRequest(BaseModel):
    """D03: Business Development returns a submitted report for correction.

    The reason is mandatory -- a return with no explanation would leave the
    company manager with nothing to act on.
    """

    reason: str = Field(min_length=3, max_length=2000)


class ReportCorrectionCreateRequest(BaseModel):
    """D03: create a *linked* correction version of a submitted report (S09).

    Only the narrative fields are re-entered; the correction is a new version
    (``version_number`` increments) that points at the version it corrects. The
    original is preserved, never overwritten.
    """

    important_developments: str | None = Field(default=None, max_length=5000)
    new_customers: str | None = Field(default=None, max_length=5000)
    new_opportunities: str | None = Field(default=None, max_length=5000)
    major_problems: str | None = Field(default=None, max_length=5000)
    support_required: str | None = Field(default=None, max_length=5000)
    marketing_status: str | None = Field(default=None, max_length=5000)
    business_development_status: str | None = Field(default=None, max_length=5000)
    management_notes: str | None = Field(default=None, max_length=5000)


class ReportCancelRequest(BaseModel):
    """D03: owner-only cancellation of a report version."""

    reason: str = Field(min_length=3, max_length=2000)


class ReportLifecycleEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    from_status: str | None
    to_status: str
    actor_id: int | None
    actor_name_ar: str | None = None
    note: str | None
    created_at: datetime


class ReportVersionOut(BaseModel):
    """One version in a management report's correction chain (D03/S09)."""

    id: int
    version_number: int
    status: str
    approval_status: str
    is_live: bool
    corrects_report_id: int | None
    submitted_at: datetime | None
    returned_at: datetime | None
    return_reason: str | None
    approved_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime


class FinancialReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    report_id: int
    reviewer_id: int
    # Display names for the reviewer, so a list can offer the deck's "مراجع"
    # filter (slide 134) without resolving a bare id client-side.
    reviewer_name_ar: str | None = None
    reviewer_name_en: str | None = None
    status: str
    verified_revenue: Decimal | None
    verified_expenses: Decimal | None
    verified_net_result: Decimal | None
    verified_outstanding_receivables: Decimal | None
    financial_notes: str | None
    is_financially_accurate: bool | None
    flagged_reason: str | None
    reviewed_at: datetime | None


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_filename: str
    content_type: str | None
    size_bytes: int | None
    created_at: datetime


class FinancialPartVersionOut(BaseModel):
    id: int
    version_number: int
    status: str


class FinancialPartOut(BaseModel):
    """The linked F-03 financial part of a monthly report (spec Table 42).

    ``status`` is ``no_data`` when the company has not started a financial
    summary for the period, so the report shows the absence honestly.
    """

    status: str
    effective_version: FinancialPartVersionOut | None = None
    current_version: FinancialPartVersionOut | None = None


class MonthlyReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    company_name_ar: str | None = None
    company_name_en: str | None = None
    period_year: int
    period_month: int
    status: str
    version_number: int = 1
    corrects_report_id: int | None = None
    is_live: bool = True
    approval_status: str = "pending"
    return_reason: str | None = None
    returned_at: datetime | None = None
    approved_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancel_reason: str | None = None
    revenue: Decimal | None
    expenses: Decimal | None
    net_result: Decimal | None
    outstanding_receivables: Decimal | None
    important_developments: str | None = None
    new_customers: str | None = None
    new_opportunities: str | None = None
    major_problems: str | None = None
    support_required: str | None = None
    marketing_status: str | None = None
    business_development_status: str | None = None
    management_notes: str | None = None
    submitted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    financial_review: FinancialReviewOut | None = None
    attachments: list[AttachmentOut] = []
    financial_part: FinancialPartOut | None = None
    # D03: the ordered workflow trail and the full version chain (S09 history).
    lifecycle: list[ReportLifecycleEventOut] = []
    versions: list[ReportVersionOut] = []


class FinancialReviewRequest(BaseModel):
    """Accountant verification payload."""

    verified_revenue: Decimal | None = Field(default=None, ge=0)
    verified_expenses: Decimal | None = Field(default=None, ge=0)
    verified_net_result: Decimal | None = None
    verified_outstanding_receivables: Decimal | None = Field(default=None, ge=0)
    financial_notes: str | None = Field(default=None, max_length=5000)
    is_financially_accurate: bool
    flagged_reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _require_reason_when_inaccurate(self) -> FinancialReviewRequest:
        # A model validator is required here, not a field validator: Pydantic v2
        # skips field validators for fields left at their default, so a check
        # on ``flagged_reason`` would never run when the client omits it --
        # exactly the case it exists to catch.
        if not self.is_financially_accurate and not (
            self.flagged_reason and self.flagged_reason.strip()
        ):
            raise ValueError("A reason is required when financial data is not accurate.")
        return self


class ReportClarificationRequest(BaseModel):
    """A clarification request/reply linked to a report's original (S02/S09)."""

    body: str = Field(min_length=1, max_length=4000)
    kind: ReportClarificationKind = ReportClarificationKind.REQUEST
    parent_id: int | None = None


# --------------------------------------------------------------------------
# support requests
# --------------------------------------------------------------------------
class SupportRequestCreateRequest(BaseModel):
    company_id: int
    title: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    category: SupportCategory = SupportCategory.GENERAL
    platform: str | None = Field(default=None, max_length=80)
    dimensions: str | None = Field(default=None, max_length=120)
    reference_link: str | None = Field(default=None, max_length=500)


class SupportRequestStatusRequest(BaseModel):
    status: SupportStatus


class SupportDeliveryRequest(BaseModel):
    delivery_link: str = Field(min_length=1, max_length=500)


class SupportAssignRequest(BaseModel):
    assigned_to_id: int | None = None
    responsible_department: str | None = Field(default=None, max_length=120)


class SupportCommentRequest(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    is_internal: bool = False


class SupportCommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: int
    author_id: int | None
    author_name_ar: str | None = None
    body: str
    is_internal: bool
    created_at: datetime


class SupportRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    company_name_ar: str | None = None
    company_name_en: str | None = None
    title: str
    description: str | None
    category: str
    status: str
    responsible_department: str
    requested_by_id: int | None
    assigned_to_id: int | None
    # Display names for the assignee, so the list view can offer the deck's
    # "مسؤول" filter without resolving a bare id client-side.
    assigned_to_name_ar: str | None = None
    assigned_to_name_en: str | None = None
    platform: str | None = None
    dimensions: str | None = None
    reference_link: str | None = None
    delivery_link: str | None = None
    delivered_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None


# --------------------------------------------------------------------------
# dashboard
# --------------------------------------------------------------------------
class DashboardKpis(BaseModel):
    companies_count: int
    reports_submitted: int
    reports_missing: int
    total_revenue: Decimal
    total_expenses: Decimal
    total_net_result: Decimal
    companies_requiring_attention: int
    open_support_requests: int
    pending_financial_reviews: int


class AttentionCompanyOut(BaseModel):
    """A company the Holding should look at, with the reason why."""

    id: int
    code: str
    name_ar: str
    name_en: str | None = None
    health: str
    reason: str | None = None
    support_required: str | None = None


class PriorityOut(BaseModel):
    """S01 ``الأولويات``: a link to a record that needs the caller's action.

    ``kind`` names the record type so the UI can route to the right view; only
    sources the caller may read are emitted.
    """

    kind: str  # "owner_decision" | "support_request" | "company"
    record_id: int
    label_ar: str
    label_en: str | None = None
    status: str | None = None
    due_date: date | None = None
    overdue: bool = False
    reason: str | None = None


class IndicatorSourceOut(BaseModel):
    """A record that produced an indicator's number (S01 AC-01 drill-down)."""

    kind: str  # "monthly_report" | "company" | "support_request"
    record_id: int
    company_id: int | None = None
    label_ar: str


class IndicatorSourcesOut(BaseModel):
    """The source records behind one dashboard indicator."""

    indicator: str
    period_year: int
    period_month: int
    records: list[IndicatorSourceOut] = []


class GoalOut(BaseModel):
    """A company goal: an approved, company-scoped KPI with a target (S02/S10)."""

    id: int
    company_id: int | None = None
    code: str
    name_ar: str
    name_en: str | None = None
    unit: str | None = None
    period_label: str | None = None
    period_year: int
    period_month: int
    metric_key: str | None = None
    direction: str
    target_value: Decimal | None = None
    actual_value: Decimal | None = None
    variance: Decimal | None = None
    variance_pct: float | None = None
    favourable: bool | None = None
    is_active: bool
    approved_at: datetime | None = None
    status: str


class CompanyPerformanceOut(BaseModel):
    """Per-company figures for the dashboard report/overview cards."""

    id: int
    code: str
    name_ar: str
    name_en: str | None = None
    sector: str | None = None
    health: str
    report_status: str | None = None
    has_report: bool
    revenue: Decimal | None = None
    expenses: Decimal | None = None
    net_result: Decimal | None = None
    outstanding_receivables: Decimal | None = None
    revenue_pct: float | None = None
    last_update: datetime | None = None
    goals: list[GoalOut] = []
    # S10 Table 44 ``اكتمال البيانات``: no_data / under_review / complete.
    data_completeness: str = "no_data"


class DataCompletenessCompanyOut(BaseModel):
    id: int
    code: str
    status: str


class DataCompletenessOut(BaseModel):
    """S10 ``اكتمال البيانات`` -- lets the UI say "no data" instead of zero."""

    overall: str
    has_data: bool
    companies: list[DataCompletenessCompanyOut] = []


class PeriodChangeOut(BaseModel):
    """Month-over-month change for the group totals."""

    previous_year: int
    previous_month: int
    revenue_previous: Decimal
    expenses_previous: Decimal
    net_previous: Decimal
    revenue_pct: float | None = None
    expenses_pct: float | None = None
    net_pct: float | None = None


class RoleKpiOut(BaseModel):
    """One tile on a role dashboard (deck slides 7-11)."""

    key: str
    label_ar: str
    label_en: str
    value: str
    unit: str | None = None
    delta: str | None = None
    delta_dir: str | None = None  # "up" | "down" | None
    tone: str = "navy"


class RoleShortcutOut(BaseModel):
    """One role-dashboard shortcut tile (deck slides 7-11)."""

    label_ar: str
    label_en: str
    view: str


class RoleSummaryOut(BaseModel):
    """The caller's role dashboard: a titled, role-specific KPI strip.

    ``None`` on the dashboard when the role has no dedicated summary, in which
    case the holding strip is the correct presentation.
    """

    title_ar: str
    title_en: str
    # Deck slide 46 keys the manager's smart brief on the caller's role, so the
    # role code travels with the summary rather than being guessed client-side.
    role_code: str = ""
    greeting_ar: str = ""
    greeting_en: str = ""
    # Deck slides 7-11: the follow-up section heading ("قرارات بانتظار الاعتماد",
    # "مهامي المسندة إليّ", ...), the [عرض الكل] target and the role's shortcut
    # grid. The service has always computed the section wording; it was being
    # dropped here, so the client could not paint it.
    section_ar: str = ""
    section_en: str = ""
    view_all: str | None = None
    shortcuts: list["RoleShortcutOut"] = []
    kpis: list[RoleKpiOut] = []


class DashboardResponse(BaseModel):
    scope: str  # "holding" | "company"
    company_id: int | None
    period_year: int
    period_month: int
    kpis: DashboardKpis
    companies: list[CompanyOut] = []
    companies_performance: list[CompanyPerformanceOut] = []
    data_completeness: DataCompletenessOut | None = None
    change_vs_previous: PeriodChangeOut | None = None
    companies_missing_report: list[CompanyOut] = []
    companies_requiring_attention: list[AttentionCompanyOut] = []
    priorities: list[PriorityOut] = []
    motivation: "MotivationTextOut | None" = None
    role_summary: "RoleSummaryOut | None" = None


# --------------------------------------------------------------------------
# AI
# --------------------------------------------------------------------------
class AIKnowledgeSourceOut(BaseModel):
    """One retrieved knowledge chunk cited in a knowledge-scope answer."""

    document_id: int
    version_id: int
    title_ar: str
    title_en: str | None = None
    company_id: int | None = None
    sensitivity: str
    chunk_id: int
    score: float
    source: str
    excerpt: str


class AIAskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    conversation_id: int | None = None
    company_id: int | None = None  # required for company-scoped AI

    @field_validator("question")
    @classmethod
    def _question_must_have_content(cls, value: str) -> str:
        # ``min_length`` alone accepts a run of spaces, which is not a question.
        stripped = value.strip()
        if len(stripped) < 2:
            raise ValueError("The question must contain at least 2 visible characters.")
        return stripped


class AIMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    created_at: datetime


class AIAskResponse(BaseModel):
    conversation_id: int
    scope: str
    company_id: int | None
    answer: str
    grounded_on_company_ids: list[int]
    provider: str
    grounded: bool = True
    ungrounded_numbers: list[str] = []
    message: AIMessageOut
    # True when the deterministic provider answered because the configured one
    # was unavailable, refused a non-free model, or the daily ceiling was hit.
    degraded: bool = False
    # Retrieved knowledge sources (knowledge scope only), for citation display.
    sources: list["AIKnowledgeSourceOut"] = []


class AIInsightOut(BaseModel):
    key: str
    kind: str
    title_ar: str
    title_en: str
    detail_ar: str
    detail_en: str
    tone: str
    metric: str | None = None


class AIOrganizeFieldOut(BaseModel):
    """One narrative field's organization suggestion (S09)."""

    field: str
    original: str
    organized: str
    provider: str
    grounded: bool = True
    ungrounded_numbers: list[str] = []
    changed: bool = False


class AIOrganizeResponse(BaseModel):
    proposals: list[AIOrganizeFieldOut]
    fields_considered: int


# --------------------------------------------------------------------------
# AI knowledge base (Phase 3)
# --------------------------------------------------------------------------
class KnowledgeCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name_ar: str
    name_en: str
    description: str | None = None
    display_order: int = 0
    is_active: bool = True


class KnowledgeCategoryCreate(BaseModel):
    code: str = Field(min_length=2, max_length=60)
    name_ar: str = Field(min_length=2, max_length=160)
    name_en: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    display_order: int = 0


class KnowledgeVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    version_number: int
    body_ar: str
    body_en: str | None = None
    status: str
    review_note: str | None = None
    source_reference: str | None = None
    created_at: datetime
    approved_by_id: int | None = None


class KnowledgeDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title_ar: str
    title_en: str | None = None
    summary_ar: str | None = None
    summary_en: str | None = None
    category_id: int | None = None
    company_id: int | None = None
    sensitivity: str
    status: str
    language: str
    current_version_id: int | None = None
    created_at: datetime
    updated_at: datetime


class KnowledgeDocumentCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=160)
    title_ar: str = Field(min_length=2, max_length=240)
    title_en: str | None = Field(default=None, max_length=240)
    body_ar: str = Field(min_length=2, max_length=200000)
    body_en: str | None = Field(default=None, max_length=200000)
    summary_ar: str | None = Field(default=None, max_length=4000)
    summary_en: str | None = Field(default=None, max_length=4000)
    category_id: int | None = None
    company_id: int | None = None
    sensitivity: str = "holding"
    source_reference: str | None = Field(default=None, max_length=400)


class KnowledgeVersionCreate(BaseModel):
    body_ar: str = Field(min_length=2, max_length=200000)
    body_en: str | None = Field(default=None, max_length=200000)
    source_reference: str | None = Field(default=None, max_length=400)


class KnowledgeApproveRequest(BaseModel):
    review_note: str | None = Field(default=None, max_length=2000)


class KnowledgeProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int | None = None
    kind: str
    title: str
    proposed_body: str
    rationale: str | None = None
    status: str
    resolution_note: str | None = None
    applied_version_id: int | None = None
    created_at: datetime


class KnowledgeProposalCreate(BaseModel):
    title: str = Field(min_length=2, max_length=240)
    proposed_body: str = Field(min_length=2, max_length=200000)
    document_id: int | None = None
    kind: str = "correction"
    rationale: str | None = Field(default=None, max_length=4000)


class KnowledgeProposalResolve(BaseModel):
    approve: bool
    resolution_note: str | None = Field(default=None, max_length=2000)


class KnowledgeSearchHitOut(BaseModel):
    document_id: int
    version_id: int
    title_ar: str
    title_en: str | None = None
    company_id: int | None = None
    sensitivity: str
    chunk_id: int
    score: float
    source: str
    excerpt: str


class AIProviderStatusOut(BaseModel):
    """The AI provider's configuration and live free-model inventory."""

    provider: str
    model: str
    fallbacks: list[str]
    configured: bool
    api_key_present: bool
    base_url: str
    max_cost_usd: float
    verified_free: bool
    free_models: list[dict] = []
    discovery_error: str | None = None
    rate_limit: dict = {}
    daily_limit: int = 0
    daily_used: int = 0
    usage: dict = {}


# --------------------------------------------------------------------------
# Phase 2: group administration
# --------------------------------------------------------------------------
class HoldingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    legal_name_ar: str
    legal_name_en: str
    display_name_ar: str | None = None
    display_name_en: str | None = None
    country: str | None = None
    commercial_registration: str | None = None
    tax_number: str | None = None
    default_currency: str = "SAR"
    contact_email: str | None = None
    phone: str | None = None
    address: str | None = None
    status: str = HoldingStatus.ACTIVE.value
    # Public website branding. ``logo_url`` is the versioned URL of the
    # uploaded logo, or null when the site should show its built-in fallback.
    logo_url: str | None = None
    logo_updated_at: datetime | None = None


class BrandingOut(BaseModel):
    """Public branding values the website shell needs.

    Deliberately minimal: the public site only learns whether a logo exists
    and where to fetch it. Nothing about the uploader or the raw storage key
    is exposed.
    """

    logo_url: str | None = None
    logo_updated_at: datetime | None = None


class HoldingUpdateRequest(BaseModel):
    """Partial update of the Holding's group metadata."""

    legal_name_ar: str | None = Field(default=None, min_length=1, max_length=200)
    legal_name_en: str | None = Field(default=None, min_length=1, max_length=200)
    display_name_ar: str | None = Field(default=None, max_length=200)
    display_name_en: str | None = Field(default=None, max_length=200)
    country: str | None = Field(default=None, max_length=80)
    commercial_registration: str | None = Field(default=None, max_length=80)
    tax_number: str | None = Field(default=None, max_length=80)
    default_currency: str | None = Field(default=None, min_length=3, max_length=8)
    contact_email: InternalEmail | None = None
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=1000)
    status: str | None = Field(default=None, max_length=20)

    @field_validator("status")
    @classmethod
    def _valid_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        allowed = {s.value for s in HoldingStatus}
        if value not in allowed:
            raise ValueError(f"status must be one of {sorted(allowed)}")
        return value


class OwnershipCreateRequest(BaseModel):
    owned_company_id: int
    owner_company_id: int | None = None
    external_owner_name: str | None = Field(default=None, max_length=200)
    ownership_percentage: Decimal = Field(gt=0, le=100, max_digits=6, decimal_places=3)
    effective_from: date
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _exactly_one_owner(self) -> "OwnershipCreateRequest":
        has_company = self.owner_company_id is not None
        has_external = bool(self.external_owner_name and self.external_owner_name.strip())
        if has_company == has_external:
            raise ValueError(
                "Provide exactly one of owner_company_id or external_owner_name."
            )
        return self


class OwnershipUpdateRequest(BaseModel):
    """Change a stake. Closing a stake sets ``status`` to ``ended``."""

    ownership_percentage: Decimal | None = Field(
        default=None, gt=0, le=100, max_digits=6, decimal_places=3
    )
    effective_to: date | None = None
    status: str | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("status")
    @classmethod
    def _valid_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        allowed = {s.value for s in OwnershipStatus}
        if value not in allowed:
            raise ValueError(f"status must be one of {sorted(allowed)}")
        return value


class OwnershipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owned_company_id: int
    owner_company_id: int | None
    external_owner_name: str | None
    ownership_percentage: float
    effective_from: date
    effective_to: date | None
    status: str
    notes: str | None = None
    # Denormalised labels so the frontend does not need a second lookup.
    owned_company_name_ar: str | None = None
    owned_company_name_en: str | None = None
    owner_company_name_ar: str | None = None
    owner_company_name_en: str | None = None


class GroupStructureNode(BaseModel):
    """One edge of the group structure: parent -> subsidiary at ``percentage``."""

    company_id: int
    code: str
    name_ar: str
    # English name is optional (spec S03: الاسم الإنجليزي optional), so a
    # company created without one must not break the structure tree.
    name_en: str | None = None
    sector: str | None
    status: str
    parent_company_id: int | None
    parent_name_ar: str | None
    parent_name_en: str | None
    ownership_percentage: float | None
    direct_children: int = 0


class InvestmentValuationUpdateRequest(BaseModel):
    """The documented valuation summary for one owned company (deck 107-109).

    The book value is entered as approved by the accountant, not computed by
    summing contributions/financing/distributions. The valuation is a yes/no
    choice: with ``has_valuation`` false the record stores no zero, so the
    amount/date/source/reference must be blank; with it true all four are
    required (a cross-field rule, hence ``model_validator``).
    """

    currency: str | None = Field(default=None, min_length=3, max_length=8)
    investment_date: date | None = None
    original_value: Decimal | None = None
    subsequent_contributions: Decimal | None = None
    financing: Decimal | None = None
    distributions: Decimal | None = None
    book_value: Decimal | None = None
    book_value_date: date | None = None
    book_value_source: str | None = Field(default=None, max_length=200)
    has_valuation: bool | None = None
    valuation_amount: Decimal | None = None
    valuation_date: date | None = None
    valuation_source: str | None = Field(default=None, max_length=200)
    valuation_reference: str | None = Field(default=None, max_length=200)
    decision_reference: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _valuation_yes_no(self) -> "InvestmentValuationUpdateRequest":
        if self.has_valuation is True:
            missing = [
                name
                for name, value in (
                    ("valuation_amount", self.valuation_amount),
                    ("valuation_date", self.valuation_date),
                    ("valuation_source", self.valuation_source),
                    ("valuation_reference", self.valuation_reference),
                )
                if value in (None, "")
            ]
            if missing:
                raise ValueError(
                    "has_valuation=true requires " + ", ".join(missing)
                )
        if self.has_valuation is False:
            stray = [
                name
                for name, value in (
                    ("valuation_amount", self.valuation_amount),
                    ("valuation_date", self.valuation_date),
                    ("valuation_source", self.valuation_source),
                    ("valuation_reference", self.valuation_reference),
                )
                if value not in (None, "")
            ]
            if stray:
                raise ValueError(
                    "has_valuation=false must not set " + ", ".join(stray)
                    + " (the system never stores a zero as a valuation)"
                )
        return self


class InvestmentValuationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # ``id`` is None for a company with no recorded summary yet: the detail view
    # shows "غير مُعدّ" rather than an invented zero (deck slide 109).
    id: int | None = None
    owned_company_id: int
    owned_company_name_ar: str | None = None
    owned_company_name_en: str | None = None
    currency: str
    investment_date: date | None = None
    original_value: Decimal | None = None
    subsequent_contributions: Decimal | None = None
    financing: Decimal | None = None
    distributions: Decimal | None = None
    book_value: Decimal | None = None
    book_value_date: date | None = None
    book_value_source: str | None = None
    has_valuation: bool = False
    valuation_amount: Decimal | None = None
    valuation_date: date | None = None
    valuation_source: str | None = None
    valuation_reference: str | None = None
    decision_reference: str | None = None
    notes: str | None = None


class DepartmentCreateRequest(BaseModel):
    company_id: int
    code: str = Field(min_length=1, max_length=40)
    name_ar: str = Field(min_length=1, max_length=180)
    name_en: str = Field(min_length=1, max_length=180)
    manager_user_id: int | None = None
    parent_department_id: int | None = None
    notes: str | None = Field(default=None, max_length=1000)


class DepartmentUpdateRequest(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=40)
    name_ar: str | None = Field(default=None, min_length=1, max_length=180)
    name_en: str | None = Field(default=None, min_length=1, max_length=180)
    manager_user_id: int | None = None
    parent_department_id: int | None = None
    status: str | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("status")
    @classmethod
    def _valid_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        allowed = {s.value for s in DepartmentStatus}
        if value not in allowed:
            raise ValueError(f"status must be one of {sorted(allowed)}")
        return value


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    code: str
    name_ar: str
    name_en: str
    manager_user_id: int | None
    parent_department_id: int | None
    status: str
    notes: str | None = None
    company_name_ar: str | None = None
    company_name_en: str | None = None
    manager_name_ar: str | None = None
    manager_name_en: str | None = None


class SectorCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name_ar: str = Field(min_length=1, max_length=180)
    name_en: str = Field(min_length=1, max_length=180)
    status: str | None = Field(default=None, max_length=20)
    sort_order: int | None = None
    notes: str | None = Field(default=None, max_length=1000)


class SectorUpdateRequest(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=40)
    name_ar: str | None = Field(default=None, min_length=1, max_length=180)
    name_en: str | None = Field(default=None, min_length=1, max_length=180)
    status: str | None = Field(default=None, max_length=20)
    sort_order: int | None = None
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("status")
    @classmethod
    def _valid_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        allowed = {s.value for s in DepartmentStatus}
        if value not in allowed:
            raise ValueError(f"status must be one of {sorted(allowed)}")
        return value


class SectorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name_ar: str
    name_en: str
    status: str
    sort_order: int
    notes: str | None = None


class PositionCreateRequest(BaseModel):
    company_id: int
    department_id: int | None = None
    code: str = Field(min_length=1, max_length=40)
    title_ar: str = Field(min_length=1, max_length=180)
    title_en: str = Field(min_length=1, max_length=180)
    holder_user_id: int | None = None
    holder_employee_id: int | None = None
    reports_to_position_id: int | None = None
    status: str | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("status")
    @classmethod
    def _valid_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        allowed = {s.value for s in PositionStatus}
        if value not in allowed:
            raise ValueError(f"status must be one of {sorted(allowed)}")
        return value


class PositionUpdateRequest(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=40)
    title_ar: str | None = Field(default=None, min_length=1, max_length=180)
    title_en: str | None = Field(default=None, min_length=1, max_length=180)
    department_id: int | None = None
    holder_user_id: int | None = None
    holder_employee_id: int | None = None
    reports_to_position_id: int | None = None
    status: str | None = Field(default=None, max_length=20)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("status")
    @classmethod
    def _valid_status(cls, value: str | None) -> str | None:
        if value is None:
            return None
        allowed = {s.value for s in PositionStatus}
        if value not in allowed:
            raise ValueError(f"status must be one of {sorted(allowed)}")
        return value


class PositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    department_id: int | None
    code: str
    title_ar: str
    title_en: str
    holder_user_id: int | None
    holder_employee_id: int | None
    reports_to_position_id: int | None
    status: str
    notes: str | None = None
    company_name_ar: str | None = None
    company_name_en: str | None = None
    department_name_ar: str | None = None
    department_name_en: str | None = None
    holder_name_ar: str | None = None
    holder_name_en: str | None = None
    reports_to_title_ar: str | None = None
    reports_to_title_en: str | None = None


class MotivationTextCreateRequest(BaseModel):
    text_ar: str = Field(min_length=1, max_length=500)
    text_en: str = Field(min_length=1, max_length=500)
    audience_role: str | None = Field(default=None, max_length=60)
    sort_order: int | None = None
    is_active: bool = True


class MotivationTextUpdateRequest(BaseModel):
    text_ar: str | None = Field(default=None, min_length=1, max_length=500)
    text_en: str | None = Field(default=None, min_length=1, max_length=500)
    audience_role: str | None = Field(default=None, max_length=60)
    sort_order: int | None = None
    is_active: bool | None = None


class MotivationTextOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text_ar: str
    text_en: str
    audience_role: str | None = None
    sort_order: int
    is_active: bool


class RoleOut(BaseModel):
    code: str
    name_ar: str
    name_en: str
    description: str | None = None
    description_ar: str | None = None
    permissions: list[str] = []
    is_system: bool = True


class RoleCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=40, pattern=r"^[a-z][a-z0-9_]*$")
    name_ar: str = Field(min_length=1, max_length=120)
    name_en: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    description_ar: str | None = Field(default=None, max_length=500)
    permissions: list[str] = []


class RoleUpdateRequest(BaseModel):
    name_ar: str | None = Field(default=None, min_length=1, max_length=120)
    name_en: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    description_ar: str | None = Field(default=None, max_length=500)


class RolePermissionsRequest(BaseModel):
    permissions: list[str]


class PermissionOut(BaseModel):
    code: str
    description: str | None = None


class PermissionCategoryOut(BaseModel):
    key: str
    name_ar: str
    name_en: str
    order: int


class PermissionActionOut(BaseModel):
    key: str
    name_ar: str
    name_en: str
    order: int


class PermissionDetailOut(BaseModel):
    """Human-readable presentation of a permission for the admin UI."""

    code: str
    category: str
    action: str
    name_ar: str
    name_en: str
    description_ar: str
    description_en: str
    danger: bool = False


class PermissionCatalogueOut(BaseModel):
    categories: list[PermissionCategoryOut]
    actions: list[PermissionActionOut]
    permissions: list[PermissionDetailOut]


class AuditLogOut(BaseModel):
    id: int
    actor_user_id: int | None
    actor_name_ar: str | None = None
    actor_name_en: str | None = None
    action: str
    entity_type: str | None
    entity_id: str | None
    company_id: int | None
    ip_address: str | None
    meta: dict | None = None
    created_at: datetime


class PageOut(BaseModel):
    """Generic paginated envelope."""

    total: int
    limit: int
    offset: int
    items: list[dict]
