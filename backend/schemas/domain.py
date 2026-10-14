"""Pydantic schemas for the Executions 04-14 holding-business domain.

Grouped in one module so the whole new surface is reviewable at once. As
elsewhere, the schemas are closed-set: enums are validated, so a payload cannot
smuggle in an unknown status. Response models mirror the service serialisers
exactly, so the API never exposes a field the service did not intend to expose
(for example, salary fields are absent from ``EmployeeOut`` unless the caller
holds the salary permission, which is why the endpoints return plain dicts for
that case).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from backend.db.models.enums import (
    AccountType,
    AssessmentType,
    CampaignStatus,
    EmployeeMovementType,
    EmployeeStatus,
    InvoiceDirection,
    JournalStatus,
    ManagementBriefUrgency,
    MovementStatus,
    OpeningBalanceKind,
    OwnerDecisionStatus,
    ProjectRecordType,
    TaskLifecycleStatus,
    TaskPriority,
)

_CODE = r"^[A-Za-z0-9._-]+$"


# --------------------------------------------------------------------------
# opening balances
# --------------------------------------------------------------------------
class OpeningBalanceCreateRequest(BaseModel):
    company_id: int
    period_year: int = Field(ge=2000, le=2100)
    period_month: int | None = Field(default=None, ge=1, le=12)
    kind: OpeningBalanceKind = OpeningBalanceKind.OPENING
    currency: str = Field(default="SAR", max_length=8)
    bank: Decimal | None = None
    cash: Decimal | None = None
    receivables: Decimal | None = None
    debts: Decimal | None = None
    source_summary_version_id: int | None = None
    notes: str | None = Field(default=None, max_length=2000)


class OpeningBalanceOut(BaseModel):
    id: int
    company_id: int
    period_year: int
    period_month: int | None
    kind: str
    status: str
    currency: str
    bank: Decimal | None
    cash: Decimal | None
    receivables: Decimal | None
    debts: Decimal | None
    source_summary_version_id: int | None
    notes: str | None
    approved_by_id: int | None
    approved_at: datetime | None
    created_at: datetime


# --------------------------------------------------------------------------
# employees & assessments
# --------------------------------------------------------------------------
class EmployeeCreateRequest(BaseModel):
    company_id: int
    full_name_ar: str = Field(min_length=1, max_length=180)
    full_name_en: str | None = Field(default=None, max_length=180)
    job_title: str | None = Field(default=None, max_length=120)
    department_id: int | None = None
    employee_code: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    hire_date: date | None = None
    currency: str = Field(default="SAR", max_length=8)
    base_salary: Decimal | None = None
    housing_allowance: Decimal | None = None
    transport_allowance: Decimal | None = None
    leave_balance_days: Decimal | None = None
    advance_balance: Decimal | None = None
    notes: str | None = Field(default=None, max_length=4000)


class EmployeeUpdateRequest(BaseModel):
    full_name_ar: str | None = Field(default=None, max_length=180)
    full_name_en: str | None = Field(default=None, max_length=180)
    job_title: str | None = Field(default=None, max_length=120)
    department_id: int | None = None
    status: EmployeeStatus | None = None
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    currency: str | None = Field(default=None, max_length=8)
    base_salary: Decimal | None = None
    housing_allowance: Decimal | None = None
    transport_allowance: Decimal | None = None
    leave_balance_days: Decimal | None = None
    advance_balance: Decimal | None = None
    notes: str | None = Field(default=None, max_length=4000)


class EmployeeMovementCreateRequest(BaseModel):
    movement_type: EmployeeMovementType
    effective_date: date | None = None
    days: Decimal | None = None
    amount: Decimal | None = None
    currency: str = Field(default="SAR", max_length=8)
    reason: str | None = Field(default=None, max_length=2000)


class EmployeeMovementDecisionRequest(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=2000)


class AssessmentCreateRequest(BaseModel):
    company_id: int
    period_label: str = Field(min_length=1, max_length=60)
    assessment_type: AssessmentType = AssessmentType.EMPLOYEE
    employee_id: int | None = None
    subject_user_id: int | None = None
    summary: str | None = Field(default=None, max_length=4000)


class AssessmentItemRequest(BaseModel):
    criterion_code: str = Field(min_length=1, max_length=60)
    criterion_name_ar: str = Field(min_length=1, max_length=200)
    criterion_name_en: str | None = Field(default=None, max_length=200)
    weight: Decimal = Decimal("1")
    score: Decimal | None = Field(default=None, ge=1, le=5)
    evidence_required: bool = False
    evidence_text: str | None = Field(default=None, max_length=4000)
    evidence_complete: bool = False
    comment: str | None = Field(default=None, max_length=2000)


# --------------------------------------------------------------------------
# tasks
# --------------------------------------------------------------------------
class TaskCreateRequest(BaseModel):
    company_id: int
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    assignee_id: int | None = None
    reviewer_id: int | None = None
    priority: TaskPriority = TaskPriority.NORMAL
    due_date: date | None = None


class TaskUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    assignee_id: int | None = None
    reviewer_id: int | None = None
    priority: TaskPriority | None = None
    progress_percent: int | None = Field(default=None, ge=0, le=100)
    due_date: date | None = None


class TaskStatusRequest(BaseModel):
    status: TaskLifecycleStatus
    note: str | None = Field(default=None, max_length=2000)


# --------------------------------------------------------------------------
# weekly reports
# --------------------------------------------------------------------------
class WeeklyQuestionCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=60, pattern=_CODE)
    text_ar: str = Field(min_length=1, max_length=400)
    text_en: str | None = Field(default=None, max_length=400)
    order_index: int = 0


class WeeklyAnswerIn(BaseModel):
    question_id: int | None = None
    question_code: str = Field(default="", max_length=60)
    answer: str | None = Field(default=None, max_length=4000)


class WeeklyReportCreateRequest(BaseModel):
    company_id: int
    period_year: int = Field(ge=2000, le=2100)
    period_week: int = Field(ge=1, le=53)
    answers: list[WeeklyAnswerIn] = Field(default_factory=list)
    summary: str | None = Field(default=None, max_length=4000)


# --------------------------------------------------------------------------
# campaigns
# --------------------------------------------------------------------------
class CampaignCreateRequest(BaseModel):
    company_id: int
    name: str = Field(min_length=1, max_length=200)
    platform: str | None = Field(default=None, max_length=80)
    goal: str | None = Field(default=None, max_length=2000)
    start_date: date | None = None
    end_date: date | None = None
    budget: Decimal | None = None
    currency: str = Field(default="SAR", max_length=8)


class CampaignUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    platform: str | None = Field(default=None, max_length=80)
    goal: str | None = Field(default=None, max_length=2000)
    start_date: date | None = None
    end_date: date | None = None
    budget: Decimal | None = None
    spend: Decimal | None = None
    lead_count: int | None = Field(default=None, ge=0)
    conversion_count: int | None = Field(default=None, ge=0)
    status: CampaignStatus | None = None
    manager_note: str | None = Field(default=None, max_length=4000)
    marketing_note: str | None = Field(default=None, max_length=4000)


# --------------------------------------------------------------------------
# complaints (confidential)
# --------------------------------------------------------------------------
class ComplaintCreateRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=8000)
    company_id: int | None = None
    is_anonymous: bool = False


class ComplaintDecisionRequest(BaseModel):
    status: str = Field(min_length=1, max_length=20)
    decision: str | None = Field(default=None, max_length=4000)
    routed_to_id: int | None = None


# --------------------------------------------------------------------------
# advisors
# --------------------------------------------------------------------------
class AdvisorAssignRequest(BaseModel):
    company_id: int
    advisor_user_id: int
    specialty: str | None = Field(default=None, max_length=120)


class AdvisorySessionCreateRequest(BaseModel):
    company_id: int
    advisor_user_id: int
    scheduled_at: datetime | None = None
    topic: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=8000)
    recommendations: str | None = Field(default=None, max_length=8000)
    status: str = Field(default="scheduled", max_length=20)


class AdvisorReportSaveRequest(BaseModel):
    company_id: int
    advisor_user_id: int
    period_year: int = Field(ge=2000, le=2100)
    period_month: int = Field(ge=1, le=12)
    development: str | None = Field(default=None, max_length=8000)
    challenges: str | None = Field(default=None, max_length=8000)
    recommendations: str | None = Field(default=None, max_length=8000)


# --------------------------------------------------------------------------
# owner decisions
# --------------------------------------------------------------------------
class OwnerDecisionCreateRequest(BaseModel):
    number: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=240)
    company_id: int | None = None
    body: str | None = Field(default=None, max_length=8000)
    executor_user_id: int | None = None
    due_date: date | None = None


class OwnerDecisionUpdateRequest(BaseModel):
    status: OwnerDecisionStatus | None = None
    follow_up_note: str | None = Field(default=None, max_length=4000)


# --------------------------------------------------------------------------
# projects & opportunities (S20)
# --------------------------------------------------------------------------
class ProjectRecordCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    record_type: ProjectRecordType = ProjectRecordType.OPPORTUNITY
    company_id: int | None = None
    description: str | None = Field(default=None, max_length=8000)
    objective: str | None = Field(default=None, max_length=8000)
    period_start: date | None = None
    period_end: date | None = None
    results: str | None = Field(default=None, max_length=8000)
    resource_estimate: str | None = Field(default=None, max_length=8000)
    estimated_value: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="SAR", max_length=8)
    status: str = Field(default="open", max_length=20)
    owner_decision_id: int | None = None


class ProjectRecordUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=240)
    record_type: ProjectRecordType | None = None
    company_id: int | None = None
    description: str | None = Field(default=None, max_length=8000)
    objective: str | None = Field(default=None, max_length=8000)
    period_start: date | None = None
    period_end: date | None = None
    results: str | None = Field(default=None, max_length=8000)
    resource_estimate: str | None = Field(default=None, max_length=8000)
    estimated_value: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=8)
    status: str | None = Field(default=None, max_length=20)
    owner_decision_id: int | None = None


# --------------------------------------------------------------------------
# management reports: the BD five-axis brief (S21)
# --------------------------------------------------------------------------
class ManagementBriefSaveRequest(BaseModel):
    """Draft payload for the BD brief. The five axes are free text (D02 gates
    only the indicator definitions, so no metric is computed here)."""

    period_year: int = Field(ge=2000, le=2100)
    period_month: int = Field(ge=1, le=12)
    executive_summary: str | None = Field(default=None, max_length=2000)
    axis_companies: str | None = Field(default=None, max_length=8000)
    axis_projects: str | None = Field(default=None, max_length=8000)
    axis_employees: str | None = Field(default=None, max_length=8000)
    axis_risks: str | None = Field(default=None, max_length=8000)
    axis_decisions: str | None = Field(default=None, max_length=8000)
    source_report_ids: list[int] | None = None
    urgency: ManagementBriefUrgency = ManagementBriefUrgency.MONTHLY


# --------------------------------------------------------------------------
# confidential access grants (D04)
# --------------------------------------------------------------------------
class ConfidentialGrantCreateRequest(BaseModel):
    subject_type: str = Field(min_length=1, max_length=40)
    subject_id: int
    grantee_user_id: int
    permission_code: str = Field(min_length=1, max_length=80)
    expires_at: datetime
    reason: str | None = Field(default=None, max_length=2000)


# --------------------------------------------------------------------------
# holding accounting
# --------------------------------------------------------------------------
class AccountCreateRequest(BaseModel):
    company_id: int
    code: str = Field(min_length=1, max_length=40)
    name_ar: str = Field(min_length=1, max_length=200)
    name_en: str | None = Field(default=None, max_length=200)
    account_type: AccountType
    parent_id: int | None = None
    currency: str = Field(default="SAR", max_length=8)
    description: str | None = Field(default=None, max_length=2000)


class JournalLineIn(BaseModel):
    account_id: int
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    description: str | None = Field(default=None, max_length=500)
    cost_centre: str | None = Field(default=None, max_length=80)


class JournalCreateRequest(BaseModel):
    company_id: int
    entry_date: date
    lines: list[JournalLineIn] = Field(default_factory=list)
    description: str | None = Field(default=None, max_length=2000)
    currency: str = Field(default="SAR", max_length=8)
    number: str | None = Field(default=None, max_length=40)


class JournalReverseRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class InvoiceLineIn(BaseModel):
    description: str = Field(min_length=1, max_length=300)
    quantity: Decimal = Decimal("1")
    unit_price: Decimal = Decimal("0")


class InvoiceCreateRequest(BaseModel):
    company_id: int
    number: str = Field(min_length=1, max_length=60)
    party_name: str = Field(min_length=1, max_length=200)
    direction: InvoiceDirection = InvoiceDirection.ISSUED
    party_id: int | None = None
    lines: list[InvoiceLineIn] = Field(default_factory=list)
    currency: str = Field(default="SAR", max_length=8)
    issue_date: date | None = None
    due_date: date | None = None
    tax_rate: Decimal = Decimal("0")
    notes: str | None = Field(default=None, max_length=2000)


class PartyCreateRequest(BaseModel):
    company_id: int
    name: str = Field(min_length=1, max_length=200)
    name_en: str | None = Field(default=None, max_length=200)
    party_type: str = Field(default="customer", max_length=20)
    currency: str = Field(default="SAR", max_length=8)
    contact: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)


class InterbalanceCreateRequest(BaseModel):
    company_id: int
    counterparty_company_id: int | None = None
    counterparty_name: str | None = Field(default=None, max_length=200)
    currency: str = Field(default="SAR", max_length=8)
    amount: Decimal
    reason: str | None = Field(default=None, max_length=2000)
    journal_reference: str | None = Field(default=None, max_length=120)


class SettlementCreateRequest(BaseModel):
    amount: Decimal
    settled_on: date | None = None
    reference: str | None = Field(default=None, max_length=120)


class AssetCreateRequest(BaseModel):
    company_id: int
    name: str = Field(min_length=1, max_length=200)
    cost: Decimal
    category: str | None = Field(default=None, max_length=80)
    acquisition_date: date | None = None
    currency: str = Field(default="SAR", max_length=8)
    depreciation_method: str | None = Field(default=None, max_length=40)
    depreciation_rate: Decimal | None = None
    notes: str | None = Field(default=None, max_length=2000)


class BudgetCreateRequest(BaseModel):
    company_id: int
    fiscal_year: int = Field(ge=2000, le=2100)
    total_amount: Decimal
    source: str | None = Field(default=None, max_length=200)
    currency: str = Field(default="SAR", max_length=8)
    notes: str | None = Field(default=None, max_length=2000)


class BudgetApproveRequest(BaseModel):
    source: str | None = Field(default=None, max_length=200)


class KpiCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=60, pattern=_CODE)
    name_ar: str = Field(min_length=1, max_length=200)
    data_source: str = Field(min_length=1, max_length=200)
    calculation_method: str = Field(min_length=1, max_length=4000)
    period_label: str = Field(min_length=1, max_length=60)
    company_id: int | None = None
    name_en: str | None = Field(default=None, max_length=200)
    unit: str | None = Field(default=None, max_length=40)
    target_value: Decimal | None = None
