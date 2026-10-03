"""Canonical audit action codes.

Kept as plain string constants rather than an Enum column so that new actions
can be added in future modules without a database migration.
"""


class AuditAction:
    # authentication
    LOGIN = "auth.login"
    LOGIN_FAILED = "auth.login_failed"
    LOGOUT = "auth.logout"
    TOKEN_REFRESH = "auth.token_refresh"

    # administration
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_ROLE_CHANGED = "user.role_changed"
    COMPANY_CREATED = "company.created"
    COMPANY_UPDATED = "company.updated"
    COMPANY_STATUS_CHANGED = "company.status_changed"
    COMPANY_ACCESS_GRANTED = "company.access_granted"
    COMPANY_ACCESS_REVOKED = "company.access_revoked"

    # Phase 2 group administration
    HOLDING_UPDATED = "holding.updated"
    OWNERSHIP_CREATED = "ownership.created"
    OWNERSHIP_UPDATED = "ownership.updated"
    OWNERSHIP_ENDED = "ownership.ended"
    DEPARTMENT_CREATED = "department.created"
    DEPARTMENT_UPDATED = "department.updated"
    DEPARTMENT_STATUS_CHANGED = "department.status_changed"
    ROLE_CREATED = "role.created"
    ROLE_UPDATED = "role.updated"
    ROLE_PERMISSIONS_CHANGED = "role.permissions_changed"
    USER_DEPARTMENT_ASSIGNED = "user.department_assigned"

    # monthly reports
    REPORT_CREATED = "monthly_report.created"
    REPORT_UPDATED = "monthly_report.updated"
    REPORT_SUBMITTED = "monthly_report.submitted"
    REPORT_FINANCIAL_REVIEWED = "monthly_report.financial_reviewed"
    REPORT_ATTACHMENT_ADDED = "monthly_report.attachment_added"
    REPORT_ATTACHMENT_REMOVED = "monthly_report.attachment_removed"

    # support
    SUPPORT_REQUEST_CREATED = "support_request.created"
    SUPPORT_REQUEST_STATUS_CHANGED = "support_request.status_changed"
    SUPPORT_REQUEST_ASSIGNED = "support_request.assigned"
    SUPPORT_REQUEST_COMMENTED = "support_request.commented"

    # ai
    AI_CONVERSATION_STARTED = "ai.conversation_started"
    AI_MESSAGE_SENT = "ai.message_sent"

    # Phase 3: dynamic forms builder
    FORM_CREATED = "form.created"
    FORM_UPDATED = "form.updated"
    FORM_PUBLISHED = "form.published"
    FORM_ARCHIVED = "form.archived"
    FORM_DUPLICATED = "form.duplicated"
    FORM_FIELD_ADDED = "form.field_added"
    FORM_FIELD_UPDATED = "form.field_updated"
    FORM_FIELD_REMOVED = "form.field_removed"
    FORM_FIELD_REORDERED = "form.field_reordered"

    # Phase 3: requirements engine
    REQUIREMENT_CREATED = "requirement.created"
    REQUIREMENT_UPDATED = "requirement.updated"
    REQUIREMENT_REMOVED = "requirement.removed"
    REQUIREMENT_REORDERED = "requirement.reordered"

    # Phase 3: submissions
    SUBMISSION_CREATED = "form_submission.created"
    SUBMISSION_UPDATED = "form_submission.updated"
    SUBMISSION_SUBMITTED = "form_submission.submitted"
    SUBMISSION_INCOMPLETE = "form_submission.incomplete"
    SUBMISSION_CANCELLED = "form_submission.cancelled"
    SUBMISSION_OVERRIDDEN = "form_submission.requirements_overridden"

    # Phase 3: workflow builder
    WORKFLOW_CREATED = "workflow.created"
    WORKFLOW_UPDATED = "workflow.updated"
    WORKFLOW_PUBLISHED = "workflow.published"
    WORKFLOW_ARCHIVED = "workflow.archived"
    WORKFLOW_DUPLICATED = "workflow.duplicated"
    WORKFLOW_STEP_ADDED = "workflow.step_added"
    WORKFLOW_STEP_UPDATED = "workflow.step_updated"
    WORKFLOW_STEP_REMOVED = "workflow.step_removed"
    WORKFLOW_STEP_REORDERED = "workflow.step_reordered"

    # Phase 3: approval engine
    WORKFLOW_INSTANCE_STARTED = "approval.instance_started"
    APPROVAL_TASK_CREATED = "approval.task_created"
    APPROVAL_APPROVED = "approval.approved"
    APPROVAL_REJECTED = "approval.rejected"
    APPROVAL_RETURNED = "approval.returned"
    APPROVAL_COMPLETED = "approval.completed"

    # Phase 3: document management
    DOCUMENT_UPLOADED = "document.uploaded"
    DOCUMENT_UPDATED = "document.updated"
    DOCUMENT_ARCHIVED = "document.archived"
    DOCUMENT_DOWNLOADED = "document.downloaded"
    DOCUMENT_CATEGORY_CREATED = "document_category.created"
    DOCUMENT_CATEGORY_UPDATED = "document_category.updated"

    # security
    ACCESS_DENIED = "security.access_denied"
