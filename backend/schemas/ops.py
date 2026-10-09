"""Pydantic schemas for the Phase 3 dynamic operations platform.

Grouped here rather than in ``models.py`` to keep that module focused on the
V1/Phase 2 surface. Validation is declarative and closed-set: field types,
requirement types, assignment rules and statuses are all enums, so no payload
can introduce executable behaviour.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from backend.db.models.enums import (
    ApprovalDecision,
    AssignmentType,
    DocumentStatus,
    FieldType,
    FormScope,
    FormStatus,
    RequirementType,
    SubmissionStatus,
    WorkflowStatus,
)

_CODE = r"^[a-z][a-z0-9_]*$"
_KEY = r"^[a-z][a-z0-9_]*$"


# --------------------------------------------------------------------------
# forms
# --------------------------------------------------------------------------
class FormOut(BaseModel):
    id: int
    code: str
    name_ar: str
    name_en: str
    description_ar: str | None = None
    description_en: str | None = None
    category: str | None = None
    scope: str
    status: str
    created_by_id: int | None = None
    created_at: datetime
    updated_at: datetime
    company_ids: list[int] = []
    published_version_id: int | None = None
    latest_version_id: int | None = None
    latest_version_number: int | None = None
    published_version_number: int | None = None
    field_count: int = 0


class FormCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=60, pattern=_CODE)
    name_ar: str = Field(min_length=1, max_length=200)
    name_en: str = Field(min_length=1, max_length=200)
    description_ar: str | None = Field(default=None, max_length=2000)
    description_en: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, max_length=80)
    scope: FormScope = FormScope.COMPANY
    company_ids: list[int] = []


class FormUpdateRequest(BaseModel):
    name_ar: str | None = Field(default=None, min_length=1, max_length=200)
    name_en: str | None = Field(default=None, min_length=1, max_length=200)
    description_ar: str | None = Field(default=None, max_length=2000)
    description_en: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, max_length=80)
    scope: FormScope | None = None
    company_ids: list[int] | None = None


class FormFieldOut(BaseModel):
    id: int
    key: str
    field_type: str
    label_ar: str
    label_en: str
    placeholder_ar: str | None = None
    placeholder_en: str | None = None
    help_ar: str | None = None
    help_en: str | None = None
    is_required: bool
    is_active: bool
    display_order: int
    default_value: str | None = None
    config: dict | None = None


class FormFieldIn(BaseModel):
    key: str = Field(min_length=1, max_length=60, pattern=_KEY)
    field_type: FieldType
    label_ar: str = Field(min_length=1, max_length=200)
    label_en: str = Field(min_length=1, max_length=200)
    placeholder_ar: str | None = Field(default=None, max_length=200)
    placeholder_en: str | None = Field(default=None, max_length=200)
    help_ar: str | None = Field(default=None, max_length=2000)
    help_en: str | None = Field(default=None, max_length=2000)
    is_required: bool = False
    is_active: bool = True
    display_order: int = 0
    default_value: str | None = Field(default=None, max_length=4000)
    config: dict[str, Any] | None = None


class FormFieldUpdateRequest(BaseModel):
    label_ar: str | None = Field(default=None, min_length=1, max_length=200)
    label_en: str | None = Field(default=None, min_length=1, max_length=200)
    placeholder_ar: str | None = Field(default=None, max_length=200)
    placeholder_en: str | None = Field(default=None, max_length=200)
    help_ar: str | None = Field(default=None, max_length=2000)
    help_en: str | None = Field(default=None, max_length=2000)
    is_required: bool | None = None
    is_active: bool | None = None
    display_order: int | None = None
    default_value: str | None = Field(default=None, max_length=4000)
    config: dict[str, Any] | None = None


class ReorderRequest(BaseModel):
    """Ordered ids defining the new display order."""

    ordered_ids: list[int] = Field(min_length=1)


class FormVersionOut(BaseModel):
    id: int
    form_id: int
    version_number: int
    status: str
    created_at: datetime
    published_at: datetime | None = None
    fields: list[FormFieldOut] = []
    requirements: list["FormRequirementOut"] = []


# --------------------------------------------------------------------------
# requirements
# --------------------------------------------------------------------------
class FormRequirementOut(BaseModel):
    id: int
    key: str
    name_ar: str
    name_en: str
    description_ar: str | None = None
    description_en: str | None = None
    requirement_type: str
    is_mandatory: bool
    is_active: bool
    display_order: int
    config: dict | None = None


class RequirementIn(BaseModel):
    key: str = Field(min_length=1, max_length=60, pattern=_KEY)
    name_ar: str = Field(min_length=1, max_length=200)
    name_en: str = Field(min_length=1, max_length=200)
    description_ar: str | None = Field(default=None, max_length=2000)
    description_en: str | None = Field(default=None, max_length=2000)
    requirement_type: RequirementType = RequirementType.DOCUMENT
    is_mandatory: bool = True
    is_active: bool = True
    display_order: int = 0
    config: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _field_value_needs_key(self) -> "RequirementIn":
        if self.requirement_type == RequirementType.FIELD_VALUE:
            field_key = (self.config or {}).get("field_key")
            if not field_key:
                raise ValueError("A field-value requirement needs config.field_key.")
        return self


class RequirementUpdateRequest(BaseModel):
    name_ar: str | None = Field(default=None, min_length=1, max_length=200)
    name_en: str | None = Field(default=None, min_length=1, max_length=200)
    description_ar: str | None = Field(default=None, max_length=2000)
    description_en: str | None = Field(default=None, max_length=2000)
    is_mandatory: bool | None = None
    is_active: bool | None = None
    display_order: int | None = None
    config: dict[str, Any] | None = None


# --------------------------------------------------------------------------
# workflows
# --------------------------------------------------------------------------
class WorkflowStepOut(BaseModel):
    id: int
    key: str
    name_ar: str
    name_en: str
    display_order: int
    assignment_type: str
    assignment_config: dict | None = None
    required_permission: str | None = None
    allow_approve: bool
    allow_reject: bool
    allow_return: bool
    require_comment_on_reject: bool
    sla_hours: int | None = None


class WorkflowStepIn(BaseModel):
    key: str = Field(min_length=1, max_length=60, pattern=_KEY)
    name_ar: str = Field(min_length=1, max_length=200)
    name_en: str = Field(min_length=1, max_length=200)
    display_order: int = 0
    assignment_type: AssignmentType
    assignment_config: dict[str, Any] | None = None
    required_permission: str | None = Field(default=None, max_length=80)
    allow_approve: bool = True
    allow_reject: bool = True
    allow_return: bool = True
    require_comment_on_reject: bool = True
    sla_hours: int | None = Field(default=None, ge=0, le=8760)

    @model_validator(mode="after")
    def _assignment_needs_config(self) -> "WorkflowStepIn":
        cfg = self.assignment_config or {}
        if self.assignment_type == AssignmentType.USER and not cfg.get("user_id"):
            raise ValueError("A user step needs assignment_config.user_id.")
        if self.assignment_type == AssignmentType.ROLE and not cfg.get("role_code"):
            raise ValueError("A role step needs assignment_config.role_code.")
        return self


class WorkflowStepUpdateRequest(BaseModel):
    name_ar: str | None = Field(default=None, min_length=1, max_length=200)
    name_en: str | None = Field(default=None, min_length=1, max_length=200)
    display_order: int | None = None
    assignment_type: AssignmentType | None = None
    assignment_config: dict[str, Any] | None = None
    required_permission: str | None = Field(default=None, max_length=80)
    allow_approve: bool | None = None
    allow_reject: bool | None = None
    allow_return: bool | None = None
    require_comment_on_reject: bool | None = None
    sla_hours: int | None = Field(default=None, ge=0, le=8760)


class WorkflowVersionOut(BaseModel):
    id: int
    definition_id: int
    version_number: int
    status: str
    created_at: datetime
    published_at: datetime | None = None
    steps: list[WorkflowStepOut] = []


class WorkflowOut(BaseModel):
    id: int
    code: str
    name_ar: str
    name_en: str
    description_ar: str | None = None
    description_en: str | None = None
    form_id: int
    form_name_ar: str | None = None
    form_name_en: str | None = None
    scope: str
    status: str
    allow_requirement_override: bool
    created_by_id: int | None = None
    created_at: datetime
    updated_at: datetime
    published_version_id: int | None = None
    latest_version_id: int | None = None
    latest_version_number: int | None = None
    step_count: int | None = None


class WorkflowCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=60, pattern=_CODE)
    name_ar: str = Field(min_length=1, max_length=200)
    name_en: str = Field(min_length=1, max_length=200)
    description_ar: str | None = Field(default=None, max_length=2000)
    description_en: str | None = Field(default=None, max_length=2000)
    form_id: int
    scope: FormScope = FormScope.COMPANY
    allow_requirement_override: bool = False


class WorkflowUpdateRequest(BaseModel):
    name_ar: str | None = Field(default=None, min_length=1, max_length=200)
    name_en: str | None = Field(default=None, min_length=1, max_length=200)
    description_ar: str | None = Field(default=None, max_length=2000)
    description_en: str | None = Field(default=None, max_length=2000)
    allow_requirement_override: bool | None = None


# --------------------------------------------------------------------------
# submissions
# --------------------------------------------------------------------------
class SubmissionRequirementOut(BaseModel):
    id: int
    requirement_key: str
    name_ar: str
    name_en: str
    requirement_type: str
    is_mandatory: bool
    is_satisfied: bool
    overridden: bool
    override_reason: str | None = None
    satisfied_at: datetime | None = None
    document_ids: list[int] = []


class SubmissionOut(BaseModel):
    id: int
    reference: str
    form_id: int
    form_version_id: int
    form_name_ar: str | None = None
    form_name_en: str | None = None
    company_id: int
    company_name_ar: str | None = None
    company_name_en: str | None = None
    department_id: int | None = None
    submitted_by_id: int | None = None
    submitted_by_name_ar: str | None = None
    submitted_by_name_en: str | None = None
    status: str
    title: str | None = None
    values: dict | None = None
    submitted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    current_step_name_ar: str | None = None
    current_step_name_en: str | None = None
    current_step_order: int | None = None
    total_steps: int | None = None


class SubmissionCreateRequest(BaseModel):
    form_id: int
    company_id: int
    department_id: int | None = None
    title: str | None = Field(default=None, max_length=200)
    values: dict[str, Any] = {}


class SubmissionUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    values: dict[str, Any] | None = None
    department_id: int | None = None


class SubmissionSubmitRequest(BaseModel):
    """Submit a draft, optionally overriding unmet mandatory requirements.

    The override is honoured only when the workflow allows it *and* the actor
    holds ``approval.override``; otherwise the request is rejected as
    incomplete.
    """

    override_requirements: bool = False
    override_reason: str | None = Field(default=None, max_length=2000)


class RequirementOverrideRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class ApprovalActionRequest(BaseModel):
    decision: ApprovalDecision
    comment: str | None = Field(default=None, max_length=4000)


class ApprovalTaskOut(BaseModel):
    id: int
    instance_id: int
    submission_id: int | None = None
    step_id: int
    step_order: int
    step_name_ar: str | None = None
    step_name_en: str | None = None
    assignee_id: int | None = None
    assignee_name_ar: str | None = None
    assignee_name_en: str | None = None
    status: str
    acted_at: datetime | None = None
    comment: str | None = None


class ApprovalEventOut(BaseModel):
    id: int
    action: str
    actor_user_id: int | None = None
    actor_name_ar: str | None = None
    actor_name_en: str | None = None
    step_id: int | None = None
    step_name_ar: str | None = None
    step_name_en: str | None = None
    comment: str | None = None
    from_status: str | None = None
    to_status: str | None = None
    created_at: datetime


class WorkflowInstanceOut(BaseModel):
    id: int
    submission_id: int
    workflow_definition_id: int
    workflow_version_id: int
    company_id: int
    current_step_id: int | None = None
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    tasks: list[ApprovalTaskOut] = []
    events: list[ApprovalEventOut] = []


class SubmissionDetailOut(SubmissionOut):
    requirements: list[SubmissionRequirementOut] = []
    documents: list["DocumentOut"] = []
    workflow: WorkflowInstanceOut | None = None
    can_submit: bool = False
    can_act: bool = False
    can_override: bool = False


# --------------------------------------------------------------------------
# documents
# --------------------------------------------------------------------------
class DocumentCategoryOut(BaseModel):
    id: int
    code: str
    name_ar: str
    name_en: str
    description: str | None = None
    display_order: int
    is_active: bool


class DocumentCategoryCreateRequest(BaseModel):
    code: str = Field(min_length=2, max_length=60, pattern=_CODE)
    name_ar: str = Field(min_length=1, max_length=160)
    name_en: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    display_order: int = 0
    is_active: bool = True


class DocumentCategoryUpdateRequest(BaseModel):
    name_ar: str | None = Field(default=None, min_length=1, max_length=160)
    name_en: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    display_order: int | None = None
    is_active: bool | None = None


class DocumentOut(BaseModel):
    id: int
    company_id: int
    company_name_ar: str | None = None
    company_name_en: str | None = None
    category_id: int | None = None
    category_code: str | None = None
    title_ar: str | None = None
    title_en: str | None = None
    description: str | None = None
    related_entity_type: str | None = None
    related_entity_id: int | None = None
    submission_id: int | None = None
    submission_requirement_id: int | None = None
    uploaded_by_id: int | None = None
    original_filename: str
    content_type: str | None = None
    size_bytes: int | None = None
    issue_date: date | None = None
    expiry_date: date | None = None
    expiry_state: str
    status: str
    created_at: datetime
    updated_at: datetime


class DocumentUpdateRequest(BaseModel):
    title_ar: str | None = Field(default=None, max_length=200)
    title_en: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    category_id: int | None = None
    issue_date: date | None = None
    expiry_date: date | None = None


class DocumentListQuery(BaseModel):
    company_id: int | None = None
    category_id: int | None = None
    status: DocumentStatus | None = None
    expiry: str | None = None  # expired | expiring_soon | valid
    search: str | None = None


FormVersionOut.model_rebuild()
SubmissionDetailOut.model_rebuild()

__all__ = [
    "ApprovalActionRequest",
    "ApprovalEventOut",
    "ApprovalTaskOut",
    "DocumentCategoryCreateRequest",
    "DocumentCategoryOut",
    "DocumentCategoryUpdateRequest",
    "DocumentListQuery",
    "DocumentOut",
    "DocumentUpdateRequest",
    "FormCreateRequest",
    "FormFieldIn",
    "FormFieldOut",
    "FormFieldUpdateRequest",
    "FormOut",
    "FormRequirementOut",
    "FormUpdateRequest",
    "FormVersionOut",
    "ReorderRequest",
    "RequirementIn",
    "RequirementOverrideRequest",
    "RequirementUpdateRequest",
    "SubmissionCreateRequest",
    "SubmissionDetailOut",
    "SubmissionOut",
    "SubmissionRequirementOut",
    "SubmissionSubmitRequest",
    "SubmissionUpdateRequest",
    "WorkflowCreateRequest",
    "WorkflowInstanceOut",
    "WorkflowOut",
    "WorkflowStepIn",
    "WorkflowStepOut",
    "WorkflowStepUpdateRequest",
    "WorkflowUpdateRequest",
    "WorkflowVersionOut",
]
