"""Enumerations shared by models, schemas, RBAC and services.

Values are stored as short lowercase strings so that the schema stays readable
and migrations are trivial to review.
"""

from __future__ import annotations

import enum


class RoleCode(str, enum.Enum):
    """Platform roles.

    The original six V1 roles are extended in Phase 2 with group
    administration and company-governance roles. Roles only ever *group
    permissions*: no endpoint branches on a role name.
    """

    # V1 roles
    HOLDING_OWNER = "holding_owner"
    COMPANY_MANAGER = "company_manager"
    ACCOUNTANT = "accountant"
    BUSINESS_DEVELOPMENT = "business_development"
    MARKETING = "marketing"
    DESIGNER = "designer"

    # Phase 2 group-administration and governance roles
    SUPER_ADMIN = "super_admin"
    HOLDING_FINANCE = "holding_finance"
    COMPANY_OWNER = "company_owner"
    CEO = "ceo"
    FINANCE_MANAGER = "finance_manager"
    HR_MANAGER = "hr_manager"
    DEPARTMENT_MANAGER = "department_manager"
    EMPLOYEE = "employee"


class ReportStatus(str, enum.Enum):
    """Monthly report lifecycle. Deliberately short -- no complex workflow."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    REVIEWED = "reviewed"


class FinancialReviewStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    FLAGGED = "flagged"


class SupportCategory(str, enum.Enum):
    ACCOUNTING = "accounting"
    BUSINESS_DEVELOPMENT = "business_development"
    MARKETING = "marketing"
    DESIGN = "design"
    GENERAL = "general"


class SupportStatus(str, enum.Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CLOSED = "closed"


class AIScope(str, enum.Enum):
    """Two AI contexts: Holding-level and per-company."""

    HOLDING = "holding"
    COMPANY = "company"


class AIMessageRole(str, enum.Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class CompanyStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class CompanyType(str, enum.Enum):
    """Coarse classification of a subsidiary entity."""

    HOLDING = "holding"
    SUBSIDIARY = "subsidiary"
    JOINT_VENTURE = "joint_venture"
    AFFILIATE = "affiliate"


class OwnershipStatus(str, enum.Enum):
    """Lifecycle of an ownership stake.

    Rows are never deleted: a change closes the previous row (``ended``) and a
    new row is opened, so the ownership history is preserved and auditable.
    """

    ACTIVE = "active"
    ENDED = "ended"


class DepartmentStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class HoldingStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class CompanyHealth(str, enum.Enum):
    """Executive health indicator shown on the dashboard overview."""

    STRONG = "strong"
    STABLE = "stable"
    WATCH = "watch"
    ATTENTION = "attention"


# --------------------------------------------------------------------------
# Phase 3: dynamic operations platform
# --------------------------------------------------------------------------
class FormStatus(str, enum.Enum):
    """Lifecycle of a dynamic form definition."""

    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class FormScope(str, enum.Enum):
    """Who a form definition applies to.

    ``HOLDING`` templates are visible group-wide; ``COMPANY`` forms are
    restricted to the explicit rows in ``form_companies``.
    """

    HOLDING = "holding"
    COMPANY = "company"


class FieldType(str, enum.Enum):
    """Supported configurable field types.

    Deliberately a closed set: the frontend renders each type and the backend
    validates against it, so no arbitrary executable validation is possible.
    """

    SHORT_TEXT = "short_text"
    LONG_TEXT = "long_text"
    INTEGER = "integer"
    DECIMAL = "decimal"
    CURRENCY = "currency"
    DATE = "date"
    DATETIME = "datetime"
    CHECKBOX = "checkbox"
    SELECT = "select"
    MULTI_SELECT = "multi_select"
    EMAIL = "email"
    PHONE = "phone"
    URL = "url"
    FILE = "file"
    COMPANY = "company"
    DEPARTMENT = "department"
    USER = "user"


class RequirementType(str, enum.Enum):
    """What a requirement asks for.

    A closed set, extensible by adding a value plus a branch in the
    completeness evaluator.
    """

    DOCUMENT = "document"
    FIELD_VALUE = "field_value"
    ACKNOWLEDGEMENT = "acknowledgement"


class WorkflowStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class AssignmentType(str, enum.Enum):
    """How a workflow step resolves its approver(s).

    Explicit, safe rules only -- no scripting. The resolver lives in
    :mod:`backend.services.workflow_service`.
    """

    USER = "user"
    ROLE = "role"
    DEPARTMENT_MANAGER = "department_manager"
    COMPANY_MANAGER = "company_manager"
    SUBMITTER_MANAGER = "submitter_manager"


class SubmissionStatus(str, enum.Enum):
    """Lifecycle of a form submission / request.

    Transitions are validated in :mod:`backend.services.submission_service`;
    an impossible transition is rejected server-side.
    """

    DRAFT = "draft"
    INCOMPLETE = "incomplete"
    SUBMITTED = "submitted"
    IN_REVIEW = "in_review"
    RETURNED = "returned"
    REJECTED = "rejected"
    APPROVED = "approved"
    CANCELLED = "cancelled"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    RETURNED = "returned"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class ApprovalDecision(str, enum.Enum):
    """The actions an approver may take on a pending task."""

    APPROVE = "approve"
    REJECT = "reject"
    RETURN = "return"


class DocumentStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class DocumentEntityType(str, enum.Enum):
    """The entity a document is attached to, for generic linking."""

    COMPANY = "company"
    FORM_SUBMISSION = "form_submission"
    SUBMISSION_REQUIREMENT = "submission_requirement"
    REQUIREMENT = "requirement"
    OTHER = "other"


# --------------------------------------------------------------------------
# Phase 6: notification centre
# --------------------------------------------------------------------------
class NotificationType(str, enum.Enum):
    """What a notification is about.

    A closed set: the frontend maps each value to an icon and a target view, so
    an unknown type would silently fail to route. Adding a value means adding a
    branch in the UI as well.
    """

    APPROVAL_ASSIGNED = "approval.assigned"
    APPROVAL_APPROVED = "approval.approved"
    APPROVAL_REJECTED = "approval.rejected"
    APPROVAL_RETURNED = "approval.returned"
    SUBMISSION_INCOMPLETE = "submission.incomplete"
    DOCUMENT_EXPIRING = "document.expiring"
    DOCUMENT_EXPIRED = "document.expired"
    REPORT_SUBMITTED = "report.submitted"
    SUPPORT_ASSIGNED = "support.assigned"
    SUPPORT_STATUS_CHANGED = "support.status_changed"
    SYSTEM = "system"


class NotificationPriority(str, enum.Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


# --------------------------------------------------------------------------
# Phase 9: external integrations
# --------------------------------------------------------------------------
class WebhookStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class WebhookEventType(str, enum.Enum):
    """The business events an outbound webhook can subscribe to.

    Names are dotted and stable -- they are part of the integration contract, so
    a subscriber can match on them without reading SAFIR internals.
    """

    REQUEST_SUBMITTED = "request.submitted"
    REQUEST_APPROVED = "request.approved"
    REQUEST_REJECTED = "request.rejected"
    REQUEST_RETURNED = "request.returned"
    DOCUMENT_EXPIRING = "document.expiring"
    REPORT_SUBMITTED = "report.submitted"
    SUPPORT_CREATED = "support.created"
    SUPPORT_ASSIGNED = "support.assigned"
    NOTIFICATION_CREATED = "notification.created"


class DeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
