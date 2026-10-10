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


# --------------------------------------------------------------------------
# Execution 02: subsidiary financial summary workflow (spec section 14.1)
# --------------------------------------------------------------------------
class FinancialSummaryStatus(str, enum.Enum):
    """Lifecycle of one financial summary *version* (spec Table 68).

    ``DRAFT``            -- the manager is still assembling it (no notice).
    ``SUBMITTED``        -- sent to the accountant for review (للمراجعة).
    ``CORRECTION_REQUIRED`` -- returned by the accountant with a mandatory note
                              (مطلوب تصحيح); the manager corrects and resubmits.
    ``APPROVED``         -- approved and closed; becomes effective for reporting.

    A *corrective* version is a fresh row that starts at ``DRAFT`` again and
    links back to the approved version it corrects; until it is approved the
    previous approved version stays the single effective one.
    """

    DRAFT = "draft"
    SUBMITTED = "submitted"
    CORRECTION_REQUIRED = "correction_required"
    APPROVED = "approved"


class FinancialItemCategory(str, enum.Enum):
    """Approved special-item categories (spec S06 / F-04)."""

    WITHDRAWAL = "withdrawal"  # مسحوبات
    TRANSFER = "transfer"  # تحويلات
    LOAN = "loan"  # قروض
    SETTLEMENT = "settlement"  # تسويات
    SERVICE = "service"  # بنود خدمية معتمدة بقرار مالك
    OTHER = "other"


class FinancialItemKind(str, enum.Enum):
    """How an item affects the period result (spec section 15.1).

    ``REVENUE`` / ``EXPENSE`` feed the effective totals when their inclusion
    rule is ``ADDED``. ``OTHER`` (e.g. a transfer, a withdrawal, a loan) never
    changes the result automatically -- a transfer to the Holding is *not*
    revenue.
    """

    REVENUE = "revenue"
    EXPENSE = "expense"
    OTHER = "other"


class FinancialInclusionRule(str, enum.Enum):
    """Whether an item is already inside the entered totals or added to them."""

    INCLUDED = "included"  # مشمول: already counted, must not be added twice
    ADDED = "added"  # مضاف: added on top of the entered totals


class FinancialReviewAction(str, enum.Enum):
    """The accountant's (or manager's) recorded decisions on a version."""

    SUBMITTED = "submitted"
    RETURNED = "returned"
    RESUBMITTED = "resubmitted"
    APPROVED = "approved"
    CORRECTION_CREATED = "correction_created"


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
    # Execution 02: subsidiary financial summary workflow
    FINANCIAL_SUMMARY_SUBMITTED = "financial_summary.submitted"
    FINANCIAL_SUMMARY_RETURNED = "financial_summary.returned"
    FINANCIAL_SUMMARY_RESUBMITTED = "financial_summary.resubmitted"
    FINANCIAL_SUMMARY_APPROVED = "financial_summary.approved"
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
    # Phase 10: public website leads
    LEAD_CREATED = "lead.created"
    LEAD_STATUS_CHANGED = "lead.status_changed"
    LEAD_ASSIGNED = "lead.assigned"


class DeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


# --------------------------------------------------------------------------
# Phase 10: public website leads and opportunities
# --------------------------------------------------------------------------
class Market(str, enum.Enum):
    """The two markets the public website serves.

    Stored on every website lead so the Holding can measure demand per market
    without parsing free text. Closed set: adding a market means a deliberate
    change here, in the routing rules and in the website content model.
    """

    BAHRAIN = "bahrain"
    SAUDI = "saudi"
    # The handoff's group-services form is not market-scoped: the visitor may
    # be outside the two operating markets (the form offers a Gulf country
    # list). "gulf" keeps the routing table total without pretending the lead
    # belongs to Bahrain or Saudi Arabia.
    GULF = "gulf"


class WebsiteServiceType(str, enum.Enum):
    """What the visitor asked for, independent of which subsidiary fulfils it.

    This is the public-facing service taxonomy from the V2 concept. It is what
    the visitor chooses; internal routing then maps it to a team. The visitor
    never needs to know which company executes the request.
    """

    OPPORTUNITY_INTEREST = "opportunity_interest"
    COMPANY_FORMATION = "company_formation"
    FEASIBILITY_STUDY = "feasibility_study"
    BUSINESS_LISTING = "business_listing"
    INVESTMENT = "investment"
    GENERAL_CONTACT = "general_contact"
    # Handoff §4 "كيف يمكننا مساعدتك؟" -- the single group-services form that
    # routes the visitor to the responsible group company.
    GROUP_SERVICE = "group_service"
    # Handoff §3 الوظائف -- the careers CV submission.
    CAREERS = "careers"


class LeadStatus(str, enum.Enum):
    """Internal lifecycle of a website lead.

    Deliberately short -- this is a lead pipeline, not a workflow engine. The
    existing approval engine remains the place for multi-step review.
    """

    NEW = "new"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    QUALIFIED = "qualified"
    ESCALATED = "escalated"
    CONVERTED = "converted"
    CLOSED = "closed"


class LeadPriority(str, enum.Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class OpportunityType(str, enum.Enum):
    """How a business or opportunity is being offered.

    Mirrors the V2 concept exactly. Stored as a short code so listings can be
    filtered by type without free-text matching.
    """

    FULL_SALE = "full_sale"
    PARTIAL_SALE = "partial_sale"
    STRATEGIC_PARTNER = "strategic_partner"
    INVESTMENT = "investment"
    ACQUISITION = "acquisition"


class ApplicantCapacity(str, enum.Enum):
    """The capacity in which a visitor lists a business.

    Determines who we are actually talking to -- owner, mandated
    representative, or an intermediary -- which changes how the opportunity is
    handled internally.
    """

    OWNER = "owner"
    REPRESENTATIVE = "representative"
    ADVISOR = "advisor"


class PublicOpportunityStatus(str, enum.Enum):
    """Lifecycle of a submitted opportunity listing.

    A listing is private to the Holding until it is reviewed and published, so
    nothing confidential is ever exposed on the public site by default.
    """

    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    PUBLISHED = "published"
    REJECTED = "rejected"
    CLOSED = "closed"


class WebsiteLeadSource(str, enum.Enum):
    """Where a lead came from. ``WEBSITE`` is the only value V1 produces."""

    WEBSITE = "website"
    PLATFORM = "platform"
    REFERRAL = "referral"
    OTHER = "other"


# --------------------------------------------------------------------------
# Phase 11: website CMS
# --------------------------------------------------------------------------
class ContentStatus(str, enum.Enum):
    """Draft/published lifecycle shared by pages, slides and service content.

    Nothing is rendered on the public site until ``PUBLISHED``; the editor can
    still preview a draft. This keeps an incomplete edit from leaking.
    """

    DRAFT = "draft"
    PUBLISHED = "published"


class MediaVisibility(str, enum.Enum):
    """Where an uploaded media asset may be served from.

    ``PUBLIC`` assets are streamed by the unauthenticated public endpoint;
    ``PRIVATE`` assets are only ever served to an authenticated session with
    the media permission. The separation is enforced server-side.
    """

    PUBLIC = "public"
    PRIVATE = "private"


class SectionKind(str, enum.Enum):
    """The kind of a homepage section.

    A closed set, so the renderer knows exactly how to render each one and an
    editor can never introduce arbitrary markup. Unknown kinds fall back to a
    plain text block.
    """

    HERO = "hero"
    CARDS = "cards"
    STATS = "stats"
    STEPS = "steps"
    CTA = "cta"
    TEXT = "text"

