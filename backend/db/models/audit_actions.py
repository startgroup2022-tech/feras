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
    SECTOR_CREATED = "sector.created"
    SECTOR_UPDATED = "sector.updated"
    POSITION_CREATED = "position.created"
    POSITION_UPDATED = "position.updated"
    MOTIVATION_CREATED = "motivation.created"
    MOTIVATION_UPDATED = "motivation.updated"
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
    # S02/S09: a clarification request/reply linked to a report's original.
    REPORT_CLARIFICATION_ADDED = "monthly_report.clarification_added"

    # Execution 02: subsidiary financial summary workflow
    FINANCIAL_PERIOD_CREATED = "financial_period.created"
    FINANCIAL_SUMMARY_CREATED = "financial_summary.created"
    FINANCIAL_SUMMARY_UPDATED = "financial_summary.updated"
    FINANCIAL_SUMMARY_SUBMITTED = "financial_summary.submitted"
    FINANCIAL_SUMMARY_RESUBMITTED = "financial_summary.resubmitted"
    FINANCIAL_SUMMARY_RETURNED = "financial_summary.returned"
    FINANCIAL_SUMMARY_APPROVED = "financial_summary.approved"
    FINANCIAL_SUMMARY_CORRECTION_CREATED = "financial_summary.correction_created"
    FINANCIAL_ITEM_ADDED = "financial_summary.item_added"
    FINANCIAL_ITEM_REMOVED = "financial_summary.item_removed"
    FINANCIAL_BANK_ATTACHMENT_ADDED = "financial_summary.bank_attachment_added"
    FINANCIAL_BANK_ATTACHMENT_VIEWED = "financial_summary.bank_attachment_viewed"

    # support
    SUPPORT_REQUEST_CREATED = "support_request.created"
    SUPPORT_REQUEST_STATUS_CHANGED = "support_request.status_changed"
    SUPPORT_REQUEST_ASSIGNED = "support_request.assigned"
    SUPPORT_REQUEST_COMMENTED = "support_request.commented"
    SUPPORT_REQUEST_DELIVERED = "support_request.delivered"

    # ai
    AI_CONVERSATION_STARTED = "ai.conversation_started"
    AI_MESSAGE_SENT = "ai.message_sent"
    AI_TEXT_ORGANIZED = "ai.text_organized"

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

    # Phase 6: notification centre
    NOTIFICATION_CREATED = "notification.created"
    NOTIFICATION_READ = "notification.read"
    NOTIFICATION_READ_ALL = "notification.read_all"
    NOTIFICATION_EMAIL_QUEUED = "notification.email_queued"

    # Phase 7: reporting & analytics
    ANALYTICS_VIEWED = "analytics.viewed"
    ANALYTICS_EXPORTED = "analytics.exported"

    # Phase 9: external integrations
    INTEGRATION_CREATED = "integration.created"
    INTEGRATION_UPDATED = "integration.updated"
    INTEGRATION_DISABLED = "integration.disabled"
    INTEGRATION_SECRET_ROTATED = "integration.secret_rotated"
    INTEGRATION_DELIVERY_ATTEMPTED = "integration.delivery_attempted"

    # security
    ACCESS_DENIED = "security.access_denied"

    # Phase 10: public website leads and opportunities
    WEBSITE_LEAD_CREATED = "website_lead.created"
    WEBSITE_LEAD_UPDATED = "website_lead.updated"
    WEBSITE_LEAD_ASSIGNED = "website_lead.assigned"
    WEBSITE_LEAD_STATUS_CHANGED = "website_lead.status_changed"
    WEBSITE_LEAD_ATTACHMENT_ADDED = "website_lead.attachment_added"
    WEBSITE_LEAD_NOTE_ADDED = "website_lead.note_added"
    WEBSITE_OPPORTUNITY_SUBMITTED = "website_opportunity.submitted"
    WEBSITE_OPPORTUNITY_REVIEWED = "website_opportunity.reviewed"
    WEBSITE_OPPORTUNITY_PUBLISHED = "website_opportunity.published"

    # public website branding (logo)
    BRANDING_LOGO_UPDATED = "branding.logo_updated"
    BRANDING_LOGO_REMOVED = "branding.logo_removed"

    # Phase 11: website CMS
    WEBSITE_SETTINGS_UPDATED = "website.settings_updated"
    WEBSITE_CONTENT_CREATED = "website.content_created"
    WEBSITE_CONTENT_UPDATED = "website.content_updated"
    WEBSITE_CONTENT_PUBLISHED = "website.content_published"
    WEBSITE_CONTENT_UNPUBLISHED = "website.content_unpublished"
    WEBSITE_CONTENT_DELETED = "website.content_deleted"
    WEBSITE_MEDIA_UPLOADED = "website.media_uploaded"
    WEBSITE_MEDIA_DELETED = "website.media_deleted"
    WEBSITE_MEDIA_VISIBILITY_CHANGED = "website.media_visibility_changed"

    # Executions 04-14: holding-business domain
    OPENING_BALANCE_CREATED = "opening_balance.created"
    OPENING_BALANCE_UPDATED = "opening_balance.updated"
    OPENING_BALANCE_SUBMITTED = "opening_balance.submitted"
    OPENING_BALANCE_APPROVED = "opening_balance.approved"

    EMPLOYEE_CREATED = "employee.created"
    EMPLOYEE_UPDATED = "employee.updated"
    EMPLOYEE_STATUS_CHANGED = "employee.status_changed"
    EMPLOYEE_MOVEMENT_CREATED = "employee.movement_created"
    EMPLOYEE_MOVEMENT_DECIDED = "employee.movement_decided"
    ASSESSMENT_CREATED = "assessment.created"
    ASSESSMENT_UPDATED = "assessment.updated"
    ASSESSMENT_APPROVED = "assessment.approved"
    ASSESSMENT_APPROVAL_BLOCKED = "assessment.approval_blocked"
    ASSESSMENT_OWNER_NOTE_SAVED = "assessment.owner_note_saved"

    TASK_CREATED = "task.created"
    TASK_UPDATED = "task.updated"
    TASK_STATUS_CHANGED = "task.status_changed"

    WEEKLY_REPORT_CREATED = "weekly_report.created"
    WEEKLY_REPORT_SUBMITTED = "weekly_report.submitted"
    WEEKLY_REPORT_QUESTION_CREATED = "weekly_report.question_created"

    CAMPAIGN_CREATED = "campaign.created"
    CAMPAIGN_UPDATED = "campaign.updated"

    COMPLAINT_SUBMITTED = "complaint.submitted"
    COMPLAINT_DECIDED = "complaint.decided"

    ADVISOR_ASSIGNED = "advisor.assigned"
    ADVISORY_SESSION_RECORDED = "advisory_session.recorded"
    ADVISOR_REPORT_SAVED = "advisor_report.saved"
    ADVISOR_REPORT_SUBMITTED = "advisor_report.submitted"

    OWNER_DECISION_CREATED = "owner_decision.created"
    OWNER_DECISION_UPDATED = "owner_decision.updated"
    OWNER_DECISION_RESPONDED = "owner_decision.responded"

    # S21: the BD five-axis management brief.
    MANAGEMENT_BRIEF_CREATED = "management_brief.created"
    MANAGEMENT_BRIEF_UPDATED = "management_brief.updated"
    MANAGEMENT_BRIEF_SUBMITTED = "management_brief.submitted"

    PROJECT_RECORD_CREATED = "project_record.created"
    PROJECT_RECORD_UPDATED = "project_record.updated"

    CONFIDENTIAL_ACCESS_GRANTED = "confidential_access.granted"
    CONFIDENTIAL_ACCESS_REVOKED = "confidential_access.revoked"
    CONFIDENTIAL_ACCESS_USED = "confidential_access.used"

    ACCOUNT_CREATED = "account.created"
    ACCOUNT_UPDATED = "account.updated"
    JOURNAL_CREATED = "journal.created"
    JOURNAL_POSTED = "journal.posted"
    JOURNAL_REVERSED = "journal.reversed"
    INVOICE_CREATED = "invoice.created"
    INVOICE_UPDATED = "invoice.updated"
    INVOICE_JOURNAL_LINKED = "invoice.journal_linked"
    SETTLEMENT_RECORDED = "settlement.recorded"
    PARTY_CREATED = "party.created"
    PARTY_UPDATED = "party.updated"
    INTERBALANCE_RECORDED = "interbalance.recorded"
    ASSET_CREATED = "asset.created"
    ASSET_UPDATED = "asset.updated"
    BUDGET_CREATED = "budget.created"
    BUDGET_UPDATED = "budget.updated"
    BUDGET_APPROVED = "budget.approved"
    KPI_CREATED = "kpi.created"
    KPI_UPDATED = "kpi.updated"
    KPI_APPROVED = "kpi.approved"
    KPI_ACTIVATED = "kpi.activated"
    KPI_DEACTIVATED = "kpi.deactivated"
    POLICY_CREATED = "accounting_policy.created"
    POLICY_APPROVED = "accounting_policy.approved"

    # S28: the monthly financial report (generated from the ledger, finalised).
    FINANCIAL_REPORT_GENERATED = "monthly_financial_report.generated"
    FINANCIAL_REPORT_ANALYSIS_UPDATED = "monthly_financial_report.analysis_updated"
    FINANCIAL_REPORT_FINALISED = "monthly_financial_report.finalised"
    FINANCIAL_REPORT_ARCHIVED = "monthly_financial_report.archived"

    # Execution 30: owner-decision governance (D01/D02/D04/D09/D11).
    POLICY_PROPOSED = "accounting_policy.proposed"
    POLICY_PROPOSAL_APPROVED = "accounting_policy.proposal_approved"
    POLICY_PROPOSAL_REJECTED = "accounting_policy.proposal_rejected"
    LEAD_ASSIGNED = "website_lead.assigned_event"
    LEAD_REASSIGNED = "website_lead.reassigned"
    CURRENCY_CHANGE_REQUESTED = "currency_change.requested"
    CURRENCY_CHANGE_REVIEWED = "currency_change.reviewed"
    CURRENCY_CHANGE_APPROVED = "currency_change.approved"
    CURRENCY_CHANGE_REJECTED = "currency_change.rejected"
    CURRENCY_CHANGE_APPLIED = "currency_change.applied"
    TWO_FACTOR_ENROLLED = "auth.two_factor_enrolled"
    TWO_FACTOR_VERIFIED = "auth.two_factor_verified"
    TWO_FACTOR_FAILED = "auth.two_factor_failed"
    TWO_FACTOR_DISABLED = "auth.two_factor_disabled"
    TWO_FACTOR_RESET = "auth.two_factor_reset"
    RECOVERY_CODE_USED = "auth.recovery_code_used"
