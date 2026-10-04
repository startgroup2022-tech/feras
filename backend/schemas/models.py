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


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


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
    name_en: str
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


class CompanyCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    name_ar: str = Field(min_length=1, max_length=180)
    name_en: str = Field(min_length=1, max_length=180)
    sector: str | None = Field(default=None, max_length=120)
    contact_email: InternalEmail | None = None
    legal_name_ar: str | None = Field(default=None, max_length=200)
    legal_name_en: str | None = Field(default=None, max_length=200)
    company_type: str = Field(default=CompanyType.SUBSIDIARY.value, max_length=30)
    country: str | None = Field(default=None, max_length=80)
    commercial_registration: str | None = Field(default=None, max_length=80)
    currency: str = Field(default="SAR", min_length=3, max_length=8)
    address: str | None = Field(default=None, max_length=1000)
    phone: str | None = Field(default=None, max_length=40)

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
    sector: str | None = Field(default=None, max_length=120)
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


class FinancialReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    report_id: int
    reviewer_id: int
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


class MonthlyReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    company_name_ar: str | None = None
    company_name_en: str | None = None
    period_year: int
    period_month: int
    status: str
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


# --------------------------------------------------------------------------
# support requests
# --------------------------------------------------------------------------
class SupportRequestCreateRequest(BaseModel):
    company_id: int
    title: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    category: SupportCategory = SupportCategory.GENERAL


class SupportRequestStatusRequest(BaseModel):
    status: SupportStatus


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


class DashboardResponse(BaseModel):
    scope: str  # "holding" | "company"
    company_id: int | None
    period_year: int
    period_month: int
    kpis: DashboardKpis
    companies: list[CompanyOut] = []
    companies_performance: list[CompanyPerformanceOut] = []
    change_vs_previous: PeriodChangeOut | None = None
    companies_missing_report: list[CompanyOut] = []
    companies_requiring_attention: list[AttentionCompanyOut] = []


# --------------------------------------------------------------------------
# AI
# --------------------------------------------------------------------------
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


class AIInsightOut(BaseModel):
    key: str
    kind: str
    title_ar: str
    title_en: str
    detail_ar: str
    detail_en: str
    tone: str
    metric: str | None = None


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
    name_en: str
    sector: str | None
    status: str
    parent_company_id: int | None
    parent_name_ar: str | None
    parent_name_en: str | None
    ownership_percentage: float | None
    direct_children: int = 0


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


class RoleOut(BaseModel):
    code: str
    name_ar: str
    name_en: str
    description: str | None = None
    permissions: list[str] = []
    is_system: bool = True


class RoleCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=40, pattern=r"^[a-z][a-z0-9_]*$")
    name_ar: str = Field(min_length=1, max_length=120)
    name_en: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    permissions: list[str] = []


class RoleUpdateRequest(BaseModel):
    name_ar: str | None = Field(default=None, min_length=1, max_length=120)
    name_en: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)


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
