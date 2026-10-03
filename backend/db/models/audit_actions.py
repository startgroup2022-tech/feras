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

    # security
    ACCESS_DENIED = "security.access_denied"
