"""Pydantic schemas for the notification centre, advanced analytics and
external integrations.

Kept separate from ``models.py`` (V1/Phase 2) and ``ops.py`` (Phase 3) so each
surface has one obvious home. As elsewhere, the schemas are closed-set: event
types and priorities are validated against enums so no payload can smuggle in
an unknown value.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from backend.db.models.enums import (
    NotificationPriority,
    WebhookStatus,
)
from backend.services.integration_service import SUPPORTED_EVENTS


# --------------------------------------------------------------------------
# notifications
# --------------------------------------------------------------------------
class NotificationOut(BaseModel):
    id: int
    type: str
    priority: str
    title_ar: str
    title_en: str
    message_ar: str
    message_en: str
    entity_type: str | None = None
    entity_id: int | None = None
    company_id: int | None = None
    is_read: bool
    read_at: datetime | None = None
    created_at: datetime


class NotificationSummaryOut(BaseModel):
    unread: int
    by_type: dict[str, int] = {}


# --------------------------------------------------------------------------
# analytics
# --------------------------------------------------------------------------
class AnalyticsPeriodOut(BaseModel):
    year: int
    month: int


class TrendPointOut(BaseModel):
    year: int
    month: int
    revenue: float
    expenses: float
    net_result: float
    companies_reporting: int


class SectorMixOut(BaseModel):
    sector: str
    companies: int
    revenue: float
    net_result: float


class ComplianceOut(BaseModel):
    companies_total: int
    companies_reported: int
    companies_reviewed: int
    companies_missing: int
    compliance_pct: float


class MoverOut(BaseModel):
    company_id: int
    revenue: float
    previous_revenue: float
    change_pct: float
    name_ar: str | None = None
    name_en: str | None = None
    code: str | None = None


class MoversOut(BaseModel):
    top: list[MoverOut] = []
    bottom: list[MoverOut] = []


class HealthBucketOut(BaseModel):
    health: str
    companies: int


class HoldingOverviewOut(BaseModel):
    period: AnalyticsPeriodOut
    trend: list[TrendPointOut] = []
    sectors: list[SectorMixOut] = []
    compliance: ComplianceOut
    movers: MoversOut
    health_distribution: list[HealthBucketOut] = []


class StatusCountOut(BaseModel):
    status: str
    count: int


class CompanyCountOut(BaseModel):
    company_id: int
    count: int
    name_ar: str | None = None
    name_en: str | None = None
    code: str | None = None


class BottleneckOut(BaseModel):
    step_id: int
    name_ar: str | None = None
    name_en: str | None = None
    pending: int


class CycleOut(BaseModel):
    completed: int
    average_hours: float | None = None
    fastest_hours: float | None = None
    slowest_hours: float | None = None


class SupportCategoryOut(BaseModel):
    category: str
    total: int
    open: int
    closed: int


class SupportThroughputOut(BaseModel):
    closed_requests: int
    average_hours: float | None = None


class OperationalReportOut(BaseModel):
    period: AnalyticsPeriodOut
    requests_by_status: list[StatusCountOut] = []
    requests_by_company: list[CompanyCountOut] = []
    approval_bottlenecks: list[BottleneckOut] = []
    approval_cycle: CycleOut
    support_by_category: list[SupportCategoryOut] = []
    support_throughput: SupportThroughputOut


class DocumentExposureOut(BaseModel):
    expired: int
    expiring_soon: int
    valid: int
    none: int
    total: int
    expiring_soon_days: int


class DocumentCategoryCountOut(BaseModel):
    name_ar: str
    name_en: str
    count: int


class FlaggedFinancialOut(BaseModel):
    company_id: int
    flagged_reviews: int
    name_ar: str | None = None
    name_en: str | None = None
    code: str | None = None


class ComplianceReportOut(BaseModel):
    period: AnalyticsPeriodOut
    documents: DocumentExposureOut
    documents_by_category: list[DocumentCategoryCountOut] = []
    reporting: ComplianceOut
    flagged_financials: list[FlaggedFinancialOut] = []


class InvestmentCompanyOut(BaseModel):
    company_id: int
    name_ar: str
    name_en: str
    code: str
    sector: str | None = None
    health: str
    revenue: float
    net_result: float
    margin_pct: float | None = None
    outstanding_receivables: float
    has_opportunity: bool
    has_new_customers: bool


class InvestmentReportOut(BaseModel):
    period: AnalyticsPeriodOut
    companies: list[InvestmentCompanyOut] = []
    opportunities_reported: int
    opportunity_companies: list[InvestmentCompanyOut] = []
    portfolio_net: float
    portfolio_revenue: float
    average_margin_pct: float | None = None


# --------------------------------------------------------------------------
# executive intelligence
# --------------------------------------------------------------------------
class BriefingItemOut(BaseModel):
    key: str
    tone: str | None = None
    text_ar: str
    text_en: str


class ActionItemOut(BaseModel):
    key: str
    text_ar: str
    text_en: str


class ExecutiveBriefingOut(BaseModel):
    period: AnalyticsPeriodOut
    provider: str
    degraded: bool
    generated_from: str
    summary_ar: str
    summary_en: str
    highlights: list[BriefingItemOut] = []
    risks: list[BriefingItemOut] = []
    opportunities: list[BriefingItemOut] = []
    recommended_actions: list[ActionItemOut] = []


# --------------------------------------------------------------------------
# integrations
# --------------------------------------------------------------------------
class WebhookEndpointOut(BaseModel):
    id: int
    name: str
    url: str
    status: str
    scope: str
    company_id: int | None = None
    subscribed_events: list[str] = []
    description: str | None = None
    last_delivery_at: datetime | None = None
    last_status: str | None = None
    delivery_count: int = 0
    created_at: datetime


class WebhookEndpointCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    url: str = Field(min_length=4, max_length=500)
    subscribed_events: list[str] = Field(min_length=1)
    scope: str = "holding"
    company_id: int | None = None
    description: str | None = Field(default=None, max_length=1000)

    @field_validator("subscribed_events")
    @classmethod
    def _known_events(cls, value: list[str]) -> list[str]:
        unknown = [e for e in value if e not in SUPPORTED_EVENTS]
        if unknown:
            raise ValueError("Unknown event type(s): " + ", ".join(unknown))
        return value


class WebhookEndpointUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    url: str | None = Field(default=None, min_length=4, max_length=500)
    subscribed_events: list[str] | None = None
    status: str | None = None
    description: str | None = Field(default=None, max_length=1000)

    @field_validator("status")
    @classmethod
    def _known_status(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if value not in (WebhookStatus.ACTIVE.value, WebhookStatus.INACTIVE.value):
            raise ValueError("Unknown webhook status.")
        return value


class WebhookSecretOut(BaseModel):
    """Returned exactly once, at creation or rotation."""

    endpoint: WebhookEndpointOut
    signing_secret: str


class WebhookDeliveryOut(BaseModel):
    id: int
    endpoint_id: int
    event_id: str
    event_type: str
    status: str
    attempt_count: int
    response_status: int | None = None
    error: str | None = None
    last_attempt_at: datetime | None = None
    created_at: datetime


class IntegrationEventOut(BaseModel):
    """The catalogue of subscribable events, for the admin UI."""

    events: list[str]
    email_provider: str
    webhooks_enabled: bool


class NotificationPriorityOut(BaseModel):
    values: list[str] = [p.value for p in NotificationPriority]


__all__ = [
    "ActionItemOut",
    "AnalyticsPeriodOut",
    "BottleneckOut",
    "BriefingItemOut",
    "CompanyCountOut",
    "ComplianceOut",
    "ComplianceReportOut",
    "CycleOut",
    "DocumentCategoryCountOut",
    "DocumentExposureOut",
    "ExecutiveBriefingOut",
    "FlaggedFinancialOut",
    "HealthBucketOut",
    "HoldingOverviewOut",
    "IntegrationEventOut",
    "InvestmentCompanyOut",
    "InvestmentReportOut",
    "MoverOut",
    "MoversOut",
    "NotificationOut",
    "NotificationPriorityOut",
    "NotificationSummaryOut",
    "OperationalReportOut",
    "SectorMixOut",
    "StatusCountOut",
    "SupportCategoryOut",
    "SupportThroughputOut",
    "TrendPointOut",
    "WebhookDeliveryOut",
    "WebhookEndpointCreateRequest",
    "WebhookEndpointOut",
    "WebhookEndpointUpdateRequest",
    "WebhookSecretOut",
]
