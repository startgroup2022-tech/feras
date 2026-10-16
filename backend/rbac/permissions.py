"""Permission catalogue.

Every capability in the system is named here once. Roles are then defined as a
set of these codes. Nothing in the API layer should branch on a role name; it
should require a permission code. That keeps authorization auditable and lets
future modules add permissions without touching existing role logic.
"""

from __future__ import annotations

from backend.db.models.enums import RoleCode


class Perm:
    # ---- identity / administration ----
    USER_READ = "user.read"
    USER_MANAGE = "user.manage"
    COMPANY_READ = "company.read"
    COMPANY_MANAGE = "company.manage"
    COMPANY_ACCESS_MANAGE = "company.access.manage"
    AUDIT_READ = "audit.read"

    # ---- Phase 2 group administration ----
    # Kept as distinct codes (rather than one ``admin`` bit) so a role can be
    # granted exactly the slice of administration it needs.
    GROUP_MANAGE = "group.manage"
    COMPANY_CREATE = "company.create"
    COMPANY_UPDATE = "company.update"
    COMPANY_ARCHIVE = "company.archive"
    OWNERSHIP_READ = "ownership.read"
    OWNERSHIP_MANAGE = "ownership.manage"
    DEPARTMENT_READ = "department.read"
    DEPARTMENT_MANAGE = "department.manage"
    SECTOR_READ = "sector.read"
    SECTOR_MANAGE = "sector.manage"
    POSITION_READ = "position.read"
    POSITION_MANAGE = "position.manage"
    MOTIVATION_READ = "motivation.read"
    MOTIVATION_MANAGE = "motivation.manage"
    USER_READ_ALL = "user.read_all"
    USER_CREATE = "user.create"
    USER_UPDATE = "user.update"
    USER_ASSIGN_COMPANY = "user.assign_company"
    ROLE_READ = "role.read"
    ROLE_MANAGE = "role.manage"
    PERMISSION_READ = "permission.read"
    PERMISSION_ASSIGN = "permission.assign"

    # ---- monthly reports ----
    REPORT_READ_OWN = "monthly_report.read_own"
    REPORT_READ_ALL = "monthly_report.read_all"
    REPORT_CREATE = "monthly_report.create"
    REPORT_UPDATE = "monthly_report.update"
    REPORT_SUBMIT = "monthly_report.submit"
    REPORT_DELETE = "monthly_report.delete"

    # ---- accountant review ----
    FINANCIAL_REVIEW_READ = "financial_review.read"
    FINANCIAL_REVIEW_WRITE = "financial_review.write"

    # ---- Execution 02: subsidiary financial summary workflow (F-03/F-04) ----
    FINANCIAL_SUMMARY_READ_OWN = "financial_summary.read_own"  # read your companies' summaries
    FINANCIAL_SUMMARY_READ_ALL = "financial_summary.read_all"  # read every company's summaries
    FINANCIAL_SUMMARY_CREATE = "financial_summary.create"  # create a summary draft
    FINANCIAL_SUMMARY_UPDATE = "financial_summary.update"  # edit a summary draft / return
    FINANCIAL_SUMMARY_SUBMIT = "financial_summary.submit"  # submit / resubmit for review
    FINANCIAL_SUMMARY_CORRECT = "financial_summary.correct"  # create a corrective version
    FINANCIAL_ITEM_MANAGE = "financial_item.manage"  # manage special-item definitions
    FINANCIAL_REVIEW_ACT = "financial_review.act"  # approve / return a submitted summary
    FINANCIAL_BANK_READ = "financial_summary.bank_read"  # view a private bank statement

    # ---- support requests ----
    SUPPORT_READ_OWN = "support_request.read_own"
    SUPPORT_READ_ALL = "support_request.read_all"
    SUPPORT_CREATE = "support_request.create"
    SUPPORT_COMMENT = "support_request.comment"
    SUPPORT_ASSIGN = "support_request.assign"
    SUPPORT_STATUS_CHANGE = "support_request.status_change"

    # ---- dashboard ----
    DASHBOARD_HOLDING = "dashboard.holding"
    DASHBOARD_COMPANY = "dashboard.company"

    # ---- ai ----
    AI_HOLDING = "ai.holding"
    AI_COMPANY = "ai.company"

    # ---- Phase 3: dynamic forms builder ----
    FORM_READ = "form.read"
    FORM_CREATE = "form.create"
    FORM_UPDATE = "form.update"
    FORM_PUBLISH = "form.publish"
    FORM_ARCHIVE = "form.archive"
    FORM_SUBMIT = "form.submit"

    # ---- Phase 3: requirements engine ----
    REQUIREMENT_READ = "requirement.read"
    REQUIREMENT_MANAGE = "requirement.manage"

    # ---- Phase 3: submissions ----
    SUBMISSION_READ_OWN = "form_submission.read_own"
    SUBMISSION_READ_COMPANY = "form_submission.read_company"
    SUBMISSION_READ_ALL = "form_submission.read_all"
    SUBMISSION_CANCEL = "form_submission.cancel"

    # ---- Phase 3: workflow builder ----
    WORKFLOW_READ = "workflow.read"
    WORKFLOW_CREATE = "workflow.create"
    WORKFLOW_UPDATE = "workflow.update"
    WORKFLOW_PUBLISH = "workflow.publish"
    WORKFLOW_ARCHIVE = "workflow.archive"

    # ---- Phase 3: approval engine ----
    APPROVAL_ACT = "approval.act"
    APPROVAL_READ_OWN = "approval.read_own"  # see your own approval inbox
    APPROVAL_READ_ALL = "approval.read_all"  # see all approvals in scope
    APPROVAL_OVERRIDE = "approval.override"  # allow documented requirement bypass

    # ---- Phase 3: document management ----
    DOCUMENT_READ = "document.read"
    DOCUMENT_UPLOAD = "document.upload"
    DOCUMENT_UPDATE = "document.update"
    DOCUMENT_ARCHIVE = "document.archive"
    DOCUMENT_CATEGORY_MANAGE = "document.category.manage"

    # ---- Phase 6: notification centre ----
    NOTIFICATION_READ_OWN = "notification.read_own"  # read your own inbox
    NOTIFICATION_MANAGE = "notification.manage"  # trigger/inspect any inbox

    # ---- Phase 7: advanced reporting & analytics ----
    ANALYTICS_HOLDING = "analytics.holding"  # group-wide reporting
    ANALYTICS_COMPANY = "analytics.company"  # reporting within your companies
    ANALYTICS_OPERATIONS = "analytics.operations"  # requests/approvals analytics
    ANALYTICS_COMPLIANCE = "analytics.compliance"  # documents/compliance analytics
    ANALYTICS_EXPORT = "analytics.export"  # CSV / export endpoints

    # ---- Phase 9: external integrations ----
    INTEGRATION_READ = "integration.read"  # view configured integrations
    INTEGRATION_MANAGE = "integration.manage"  # create/edit/disable integrations

    # ---- Phase 10: public website leads and opportunities ----
    LEAD_READ = "website_lead.read"  # view website leads
    LEAD_MANAGE = "website_lead.manage"  # assign, re-route and update a lead
    LEAD_STATUS_CHANGE = "website_lead.status_change"  # move a lead through its pipeline
    LEAD_MANAGER_NOTE = "website_lead.manager_note"  # write the independent manager note (S13)
    OPPORTUNITY_REVIEW = "website_opportunity.review"  # review submitted listings
    OPPORTUNITY_PUBLISH = "website_opportunity.publish"  # publish a listing publicly

    # ---- Phase 11: public website CMS (Website Management) ----
    # Deliberately granular: editing content, uploading media, publishing and
    # changing settings are separate powers, so a marketing editor can draft
    # without being able to publish or alter site-wide configuration.
    WEBSITE_MANAGE = "website.manage"  # master switch for the CMS module
    WEBSITE_CONTENT_READ = "website.content.read"  # view pages/sections/slides
    WEBSITE_CONTENT_WRITE = "website.content.write"  # create/edit content
    WEBSITE_CONTENT_PUBLISH = "website.content.publish"  # publish/unpublish content
    WEBSITE_MEDIA_MANAGE = "website.media.manage"  # upload/replace/delete media
    WEBSITE_SETTINGS_MANAGE = "website.settings.manage"  # site-wide settings

    # ---- Executions 04-14: holding-business domain (D01-D11) ----
    # Opening balances (S04 / D08)
    OPENING_BALANCE_READ = "opening_balance.read"
    OPENING_BALANCE_MANAGE = "opening_balance.manage"
    OPENING_BALANCE_APPROVE = "opening_balance.approve"
    # Employees & assessments (S11 / S12 / D04 / D05 / D06)
    EMPLOYEE_READ = "employee.read"
    EMPLOYEE_MANAGE = "employee.manage"
    EMPLOYEE_SALARY_READ = "employee.salary.read"  # sensitive
    EMPLOYEE_MOVEMENT_READ = "employee.movement.read"
    EMPLOYEE_MOVEMENT_MANAGE = "employee.movement.manage"
    EMPLOYEE_MOVEMENT_APPROVE = "employee.movement.approve"
    ASSESSMENT_READ = "assessment.read"
    ASSESSMENT_MANAGE = "assessment.manage"
    ASSESSMENT_APPROVE = "assessment.approve"
    # Tasks (S17 / D03)
    TASK_READ_OWN = "task.read_own"
    TASK_READ_ALL = "task.read_all"
    TASK_CREATE = "task.create"
    TASK_UPDATE = "task.update"
    TASK_STATUS_CHANGE = "task.status_change"
    # Weekly reports (S18 / D02)
    WEEKLY_REPORT_READ_OWN = "weekly_report.read_own"
    WEEKLY_REPORT_READ_ALL = "weekly_report.read_all"
    WEEKLY_REPORT_SUBMIT = "weekly_report.submit"
    WEEKLY_REPORT_TEMPLATE_MANAGE = "weekly_report.template.manage"
    # Campaigns (S14 / D02)
    CAMPAIGN_READ = "campaign.read"
    CAMPAIGN_MANAGE = "campaign.manage"
    # Complaints (S15 / D04) -- confidential, owner-only by default
    COMPLAINT_CREATE = "complaint.create"
    COMPLAINT_READ_OWN = "complaint.read_own"
    COMPLAINT_DECIDE = "complaint.decide"
    # Design requests (S16 / D03)
    DESIGN_REQUEST_MANAGE = "design_request.manage"
    DESIGN_REQUEST_DELIVER = "design_request.deliver"
    # Advisors & sessions (S19 / D04)
    ADVISOR_READ = "advisor.read"
    ADVISOR_MANAGE = "advisor.manage"
    ADVISOR_SESSION_READ_OWN = "advisor.session.read_own"
    ADVISOR_SESSION_RECORD = "advisor.session.record"
    # Owner decisions (S22 / D07)
    OWNER_DECISION_READ = "owner_decision.read"
    OWNER_DECISION_MANAGE = "owner_decision.manage"
    # Projects & opportunities (S20)
    PROJECT_READ = "project.read"
    PROJECT_MANAGE = "project.manage"
    # Management reports & clarifications (S21 / S02 / S09). The five-axis brief
    # is a BD deliverable read by the owner; clarifications are linked to a
    # report's original without editing it.
    MANAGEMENT_BRIEF_READ = "management_brief.read"
    MANAGEMENT_BRIEF_SUBMIT = "management_brief.submit"
    REPORT_CLARIFY = "monthly_report.clarify"
    # Holding accounting (S26-S28 / D01 / D07)
    ACCOUNT_READ = "account.read"
    ACCOUNT_MANAGE = "account.manage"
    JOURNAL_READ = "journal.read"
    JOURNAL_CREATE = "journal.create"
    JOURNAL_POST = "journal.post"
    JOURNAL_REVERSE = "journal.reverse"
    INVOICE_READ = "invoice.read"
    INVOICE_MANAGE = "invoice.manage"
    SETTLEMENT_MANAGE = "settlement.manage"
    PARTY_READ = "party.read"
    PARTY_MANAGE = "party.manage"
    INTERBALANCE_READ = "interbalance.read"
    INTERBALANCE_MANAGE = "interbalance.manage"
    ASSET_READ = "asset.read"
    ASSET_MANAGE = "asset.manage"
    BUDGET_READ = "budget.read"
    BUDGET_MANAGE = "budget.manage"
    BUDGET_APPROVE = "budget.approve"
    POLICY_READ = "accounting_policy.read"
    POLICY_MANAGE = "accounting_policy.manage"
    POLICY_APPROVE = "accounting_policy.approve"
    # KPIs / management reports (S21 / D02)
    KPI_READ = "kpi.read"
    KPI_MANAGE = "kpi.manage"
    # Notification preferences (S25 / D11)
    NOTIFICATION_PREFERENCE_MANAGE = "notification.preference.manage"
    # Confidential delegated access (D04)
    CONFIDENTIAL_ACCESS_MANAGE = "confidential_access.manage"
    # S28: the monthly financial report and its archive
    FINANCIAL_REPORT_READ = "financial_report.read"
    FINANCIAL_REPORT_MANAGE = "financial_report.manage"
    FINANCIAL_REPORT_FINALISE = "financial_report.finalise"



ALL_PERMISSIONS: dict[str, str] = {
    Perm.USER_READ: "View users",
    Perm.USER_MANAGE: "Create, update and deactivate users",
    Perm.COMPANY_READ: "View companies",
    Perm.COMPANY_MANAGE: "Create and update companies",
    Perm.COMPANY_ACCESS_MANAGE: "Grant or revoke a user's company access",
    Perm.AUDIT_READ: "Read the audit log",
    Perm.GROUP_MANAGE: "Configure the Holding (legal name, registration, defaults)",
    Perm.COMPANY_CREATE: "Register a new subsidiary",
    Perm.COMPANY_UPDATE: "Edit a subsidiary's administrative details",
    Perm.COMPANY_ARCHIVE: "Activate, deactivate or archive a subsidiary",
    Perm.OWNERSHIP_READ: "View the group ownership structure",
    Perm.OWNERSHIP_MANAGE: "Create and change ownership stakes",
    Perm.DEPARTMENT_READ: "View company departments",
    Perm.DEPARTMENT_MANAGE: "Create and edit company departments",
    Perm.SECTOR_READ: "View the managed sector list",
    Perm.SECTOR_MANAGE: "Create and edit managed sectors",
    Perm.POSITION_READ: "View organisational positions",
    Perm.POSITION_MANAGE: "Create and edit organisational positions",
    Perm.MOTIVATION_READ: "View the motivational sentence library",
    Perm.MOTIVATION_MANAGE: "Create and edit motivational sentences",
    Perm.USER_READ_ALL: "View the full user directory",
    Perm.USER_CREATE: "Create users",
    Perm.USER_UPDATE: "Edit users, their role and their active state",
    Perm.USER_ASSIGN_COMPANY: "Assign a user to companies and departments",
    Perm.ROLE_READ: "View roles and their permissions",
    Perm.ROLE_MANAGE: "Create roles and change their permissions",
    Perm.PERMISSION_READ: "View the permission catalogue",
    Perm.PERMISSION_ASSIGN: "Grant or revoke a role's permissions",
    Perm.REPORT_READ_OWN: "Read monthly reports for accessible companies",
    Perm.REPORT_READ_ALL: "Read monthly reports across all companies",
    Perm.REPORT_CREATE: "Create a monthly report draft",
    Perm.REPORT_UPDATE: "Update a monthly report draft",
    Perm.REPORT_SUBMIT: "Submit a monthly report to the Holding",
    Perm.REPORT_DELETE: "Delete a monthly report draft",
    Perm.FINANCIAL_REVIEW_READ: "Read financial reviews",
    Perm.FINANCIAL_REVIEW_WRITE: "Verify and flag financial data",
    Perm.FINANCIAL_SUMMARY_READ_OWN: "Read financial summaries for accessible companies",
    Perm.FINANCIAL_SUMMARY_READ_ALL: "Read financial summaries across all companies",
    Perm.FINANCIAL_SUMMARY_CREATE: "Create a monthly financial summary draft",
    Perm.FINANCIAL_SUMMARY_UPDATE: "Update a financial summary draft",
    Perm.FINANCIAL_SUMMARY_SUBMIT: "Submit a financial summary for accountant review",
    Perm.FINANCIAL_SUMMARY_CORRECT: "Create a corrective version of an approved summary",
    Perm.FINANCIAL_ITEM_MANAGE: "Manage special financial item definitions",
    Perm.FINANCIAL_REVIEW_ACT: "Approve or return a submitted financial summary",
    Perm.FINANCIAL_BANK_READ: "View the private bank statement of a summary",
    Perm.SUPPORT_READ_OWN: "Read support requests for accessible companies",
    Perm.SUPPORT_READ_ALL: "Read support requests across all companies",
    Perm.SUPPORT_CREATE: "Raise a support request",
    Perm.SUPPORT_COMMENT: "Comment on a support request",
    Perm.SUPPORT_ASSIGN: "Assign a support request",
    Perm.SUPPORT_STATUS_CHANGE: "Change a support request status",
    Perm.DASHBOARD_HOLDING: "View the group executive dashboard",
    Perm.DASHBOARD_COMPANY: "View a company dashboard",
    Perm.AI_HOLDING: "Use Holding AI",
    Perm.AI_COMPANY: "Use Company AI",
    Perm.FORM_READ: "View form definitions available to you",
    Perm.FORM_CREATE: "Create a dynamic form definition",
    Perm.FORM_UPDATE: "Edit a draft form definition and its fields",
    Perm.FORM_PUBLISH: "Publish a form definition so it can be submitted",
    Perm.FORM_ARCHIVE: "Archive a form definition",
    Perm.FORM_SUBMIT: "Submit a published form",
    Perm.REQUIREMENT_READ: "View a form's requirements",
    Perm.REQUIREMENT_MANAGE: "Add, edit and reorder a draft form's requirements",
    Perm.SUBMISSION_READ_OWN: "Read the submissions you created",
    Perm.SUBMISSION_READ_COMPANY: "Read submissions raised within your companies",
    Perm.SUBMISSION_READ_ALL: "Read submissions across all companies",
    Perm.SUBMISSION_CANCEL: "Cancel a submission you own",
    Perm.WORKFLOW_READ: "View workflow definitions",
    Perm.WORKFLOW_CREATE: "Create a workflow definition",
    Perm.WORKFLOW_UPDATE: "Edit a draft workflow and its steps",
    Perm.WORKFLOW_PUBLISH: "Publish a workflow so new requests use it",
    Perm.WORKFLOW_ARCHIVE: "Archive a workflow definition",
    Perm.APPROVAL_ACT: "Approve, reject or return a request assigned to you",
    Perm.APPROVAL_READ_OWN: "See requests awaiting your approval",
    Perm.APPROVAL_READ_ALL: "See approvals across your company scope",
    Perm.APPROVAL_OVERRIDE: "Override a mandatory requirement with a recorded reason",
    Perm.DOCUMENT_READ: "View and download documents in your scope",
    Perm.DOCUMENT_UPLOAD: "Upload documents",
    Perm.DOCUMENT_UPDATE: "Edit document metadata",
    Perm.DOCUMENT_ARCHIVE: "Archive documents",
    Perm.DOCUMENT_CATEGORY_MANAGE: "Manage document categories",
    Perm.NOTIFICATION_READ_OWN: "Read your own notifications",
    Perm.NOTIFICATION_MANAGE: "Inspect and trigger notifications in scope",
    Perm.ANALYTICS_HOLDING: "View group-wide reporting and analytics",
    Perm.ANALYTICS_COMPANY: "View reporting and analytics for your companies",
    Perm.ANALYTICS_OPERATIONS: "View operational reporting (requests, approvals)",
    Perm.ANALYTICS_COMPLIANCE: "View compliance reporting (documents, expiry)",
    Perm.ANALYTICS_EXPORT: "Export reports as CSV",
    Perm.INTEGRATION_READ: "View configured integrations",
    Perm.INTEGRATION_MANAGE: "Create, edit and disable integrations",
    Perm.LEAD_READ: "View website leads and submitted opportunities",
    Perm.LEAD_MANAGE: "Assign, re-route and edit website leads",
    Perm.LEAD_STATUS_CHANGE: "Move a website lead through its pipeline",
    Perm.LEAD_MANAGER_NOTE: "Write the independent manager note on a lead",
    Perm.OPPORTUNITY_REVIEW: "Review submitted business listings",
    Perm.OPPORTUNITY_PUBLISH: "Publish a business listing on the public website",
    Perm.WEBSITE_MANAGE: "Access the Website Management module",
    Perm.WEBSITE_CONTENT_READ: "View website pages, sections and slides",
    Perm.WEBSITE_CONTENT_WRITE: "Create and edit website content",
    Perm.WEBSITE_CONTENT_PUBLISH: "Publish or unpublish website content",
    Perm.WEBSITE_MEDIA_MANAGE: "Upload, replace and delete website media",
    Perm.WEBSITE_SETTINGS_MANAGE: "Change site-wide website settings and SEO defaults",
    # Executions 04-14
    Perm.OPENING_BALANCE_READ: "View opening and carry-forward balances",
    Perm.OPENING_BALANCE_MANAGE: "Create and edit opening/carry-forward balances",
    Perm.OPENING_BALANCE_APPROVE: "Approve an opening balance so it becomes effective",
    Perm.EMPLOYEE_READ: "View employees in your companies",
    Perm.EMPLOYEE_MANAGE: "Create and edit employee records",
    Perm.EMPLOYEE_SALARY_READ: "View employee salary and allowances (sensitive)",
    Perm.EMPLOYEE_MOVEMENT_READ: "View employee leave and advance movements",
    Perm.EMPLOYEE_MOVEMENT_MANAGE: "Record employee leave and advance movements",
    Perm.EMPLOYEE_MOVEMENT_APPROVE: "Approve or reject employee movements",
    Perm.ASSESSMENT_READ: "View employee assessments",
    Perm.ASSESSMENT_MANAGE: "Create and edit employee assessments",
    Perm.ASSESSMENT_APPROVE: "Approve an employee assessment",
    Perm.TASK_READ_OWN: "View tasks assigned to you",
    Perm.TASK_READ_ALL: "View tasks across your company scope",
    Perm.TASK_CREATE: "Create and assign tasks",
    Perm.TASK_UPDATE: "Edit task details",
    Perm.TASK_STATUS_CHANGE: "Move a task through its lifecycle",
    Perm.WEEKLY_REPORT_READ_OWN: "View your own weekly reports",
    Perm.WEEKLY_REPORT_READ_ALL: "View weekly reports across your scope",
    Perm.WEEKLY_REPORT_SUBMIT: "Submit a weekly report",
    Perm.WEEKLY_REPORT_TEMPLATE_MANAGE: "Configure the weekly report questions",
    Perm.CAMPAIGN_READ: "View marketing campaigns",
    Perm.CAMPAIGN_MANAGE: "Create and edit marketing campaigns and results",
    Perm.COMPLAINT_CREATE: "Submit a confidential complaint",
    Perm.COMPLAINT_READ_OWN: "View complaints you submitted",
    Perm.COMPLAINT_DECIDE: "Decide on a confidential complaint (owner)",
    Perm.DESIGN_REQUEST_MANAGE: "Manage design request fields and lifecycle",
    Perm.DESIGN_REQUEST_DELIVER: "Attach a delivery link and complete a design request",
    Perm.ADVISOR_READ: "View advisor assignments and sessions",
    Perm.ADVISOR_MANAGE: "Assign advisors and manage sessions",
    Perm.ADVISOR_SESSION_READ_OWN: "View your own advisor sessions",
    Perm.ADVISOR_SESSION_RECORD: "Record an advisor session and recommendations",
    Perm.OWNER_DECISION_READ: "View owner decisions and directives",
    Perm.OWNER_DECISION_MANAGE: "Create and update owner decisions and directives",
    Perm.PROJECT_READ: "View opportunities and projects",
    Perm.PROJECT_MANAGE: "Create and update opportunities and projects",
    Perm.ACCOUNT_READ: "View the chart of accounts",
    Perm.ACCOUNT_MANAGE: "Manage the chart of accounts",
    Perm.JOURNAL_READ: "View journal entries",
    Perm.JOURNAL_CREATE: "Create a journal entry draft",
    Perm.JOURNAL_POST: "Post a journal entry",
    Perm.JOURNAL_REVERSE: "Reverse a posted journal entry",
    Perm.INVOICE_READ: "View invoices and receivables",
    Perm.INVOICE_MANAGE: "Create and edit invoices",
    Perm.SETTLEMENT_MANAGE: "Record invoice settlements",
    Perm.PARTY_READ: "View customers and suppliers",
    Perm.PARTY_MANAGE: "Manage the customer and supplier directory",
    Perm.INTERBALANCE_READ: "View inter-company balances",
    Perm.INTERBALANCE_MANAGE: "Record inter-company balances",
    Perm.ASSET_READ: "View assets",
    Perm.ASSET_MANAGE: "Manage assets",
    Perm.BUDGET_READ: "View budgets",
    Perm.BUDGET_MANAGE: "Create and edit budgets",
    Perm.BUDGET_APPROVE: "Approve a budget",
    Perm.POLICY_READ: "View approved accounting policies",
    Perm.POLICY_MANAGE: "Draft accounting policies",
    Perm.POLICY_APPROVE: "Approve an accounting policy",
    Perm.KPI_READ: "View KPI definitions and results",
    Perm.KPI_MANAGE: "Manage KPI definitions",
    Perm.NOTIFICATION_PREFERENCE_MANAGE: "Change your notification preferences",
    Perm.CONFIDENTIAL_ACCESS_MANAGE: "Delegate access to confidential records",
    # Management reports & clarifications (S21 / S02 / S09)
    Perm.MANAGEMENT_BRIEF_READ: "View the BD management brief",
    Perm.MANAGEMENT_BRIEF_SUBMIT: "Author and submit the BD management brief",
    Perm.REPORT_CLARIFY: "Raise or answer a report clarification",
    Perm.FINANCIAL_REPORT_READ: "View the monthly financial report",
    Perm.FINANCIAL_REPORT_MANAGE: "Generate and annotate the monthly financial report",
    Perm.FINANCIAL_REPORT_FINALISE: "Finalise or archive a monthly financial report",
}


# --------------------------------------------------------------------------
# Role -> permission grants
# --------------------------------------------------------------------------
HOLDING_OWNER = set(ALL_PERMISSIONS.keys())  # full platform authority

# Super Admin: full group administration without being the owner account. The
# same permission set as the Holding Owner, but the code exists as a distinct
# role so the owner can delegate day-to-day administration.
SUPER_ADMIN = set(ALL_PERMISSIONS.keys())

_HOLDING_READ = {
    Perm.COMPANY_READ,
    Perm.REPORT_READ_ALL,
    Perm.DASHBOARD_HOLDING,
    Perm.DASHBOARD_COMPANY,
    Perm.AI_HOLDING,
    Perm.AI_COMPANY,
    Perm.OWNERSHIP_READ,
    Perm.DEPARTMENT_READ,
    Perm.SECTOR_READ,
    Perm.POSITION_READ,
    Perm.MOTIVATION_READ,
    Perm.ANALYTICS_HOLDING,
    Perm.ANALYTICS_COMPANY,
    Perm.ANALYTICS_OPERATIONS,
    Perm.ANALYTICS_COMPLIANCE,
    Perm.ANALYTICS_EXPORT,
    # S02/S09: a holding-level reader (owner/BD) may ask a clarification that is
    # linked to a report's original without editing it.
    Perm.REPORT_CLARIFY,
}

# Every role that can *operate* the dynamic platform (read forms/submissions
# and act on approvals) gets this baseline. Configuration rights are added
# below, on top of it.
_OPERATOR_READ = {
    Perm.FORM_READ,
    Perm.REQUIREMENT_READ,
    Perm.WORKFLOW_READ,
    Perm.SUBMISSION_READ_OWN,
    Perm.APPROVAL_READ_OWN,
    Perm.APPROVAL_ACT,
    Perm.DOCUMENT_READ,
    Perm.DOCUMENT_UPLOAD,
    Perm.NOTIFICATION_READ_OWN,
}

# Holding Finance: group-wide financial oversight and read-only admin views.
HOLDING_FINANCE = _HOLDING_READ | _OPERATOR_READ | {
    Perm.FINANCIAL_REVIEW_READ,
    Perm.FINANCIAL_REVIEW_WRITE,
    Perm.FINANCIAL_SUMMARY_READ_ALL,
    Perm.FINANCIAL_SUMMARY_CREATE,
    Perm.FINANCIAL_SUMMARY_UPDATE,
    Perm.FINANCIAL_SUMMARY_SUBMIT,
    Perm.FINANCIAL_SUMMARY_CORRECT,
    Perm.FINANCIAL_ITEM_MANAGE,
    Perm.FINANCIAL_REVIEW_ACT,
    Perm.FINANCIAL_BANK_READ,
    Perm.SUPPORT_READ_ALL,
    Perm.SUPPORT_COMMENT,
    Perm.USER_READ_ALL,
    Perm.ROLE_READ,
    Perm.PERMISSION_READ,
    Perm.AUDIT_READ,
    Perm.SUBMISSION_READ_ALL,
    Perm.APPROVAL_READ_ALL,
    Perm.FORM_SUBMIT,
    Perm.NOTIFICATION_MANAGE,
    Perm.INTEGRATION_READ,
    Perm.LEAD_READ,
}

# Company-level configuration rights: an administrator (Company Owner) may
# build forms/workflows for the companies they are granted, but the services
# additionally confine every write to that company scope.
_COMPANY_BUILDER = {
    Perm.FORM_CREATE,
    Perm.FORM_UPDATE,
    Perm.FORM_PUBLISH,
    Perm.FORM_ARCHIVE,
    Perm.REQUIREMENT_MANAGE,
    Perm.WORKFLOW_CREATE,
    Perm.WORKFLOW_UPDATE,
    Perm.WORKFLOW_PUBLISH,
    Perm.WORKFLOW_ARCHIVE,
    Perm.DOCUMENT_UPDATE,
    Perm.DOCUMENT_ARCHIVE,
}

# Company-level governance roles. These are company-scoped: they only ever see
# the companies granted to them in ``user_company_access``.
_COMPANY_READ = {
    Perm.COMPANY_READ,
    Perm.REPORT_READ_OWN,
    Perm.DASHBOARD_COMPANY,
    Perm.AI_COMPANY,
    Perm.OWNERSHIP_READ,
    Perm.DEPARTMENT_READ,
    Perm.SECTOR_READ,
    Perm.POSITION_READ,
    Perm.MOTIVATION_READ,
    Perm.ANALYTICS_COMPANY,
}

COMPANY_OWNER = _COMPANY_READ | _OPERATOR_READ | _COMPANY_BUILDER | {
    Perm.REPORT_CREATE,
    Perm.REPORT_UPDATE,
    Perm.REPORT_SUBMIT,
    Perm.REPORT_DELETE,
    Perm.FINANCIAL_REVIEW_READ,
    Perm.FINANCIAL_SUMMARY_READ_OWN,
    Perm.FINANCIAL_SUMMARY_CREATE,
    Perm.FINANCIAL_SUMMARY_UPDATE,
    Perm.FINANCIAL_SUMMARY_SUBMIT,
    Perm.FINANCIAL_SUMMARY_CORRECT,
    Perm.FINANCIAL_ITEM_MANAGE,
    Perm.FINANCIAL_BANK_READ,
    Perm.SUPPORT_READ_OWN,
    Perm.SUPPORT_CREATE,
    Perm.SUPPORT_COMMENT,
    Perm.USER_READ,
    Perm.USER_UPDATE,
    Perm.USER_ASSIGN_COMPANY,
    Perm.DEPARTMENT_MANAGE,
    Perm.SECTOR_MANAGE,
    Perm.POSITION_MANAGE,
    Perm.MOTIVATION_MANAGE,
    Perm.COMPANY_UPDATE,
    Perm.FORM_SUBMIT,
    Perm.SUBMISSION_READ_COMPANY,
    Perm.SUBMISSION_CANCEL,
    Perm.APPROVAL_READ_ALL,
    Perm.DOCUMENT_CATEGORY_MANAGE,
    Perm.NOTIFICATION_MANAGE,
    # S13: the manager writes the independent lead note; marketing only reads it.
    Perm.LEAD_MANAGER_NOTE,
}

CEO = _COMPANY_READ | _OPERATOR_READ | {
    Perm.REPORT_CREATE,
    Perm.REPORT_UPDATE,
    Perm.REPORT_SUBMIT,
    Perm.FINANCIAL_REVIEW_READ,
    Perm.SUPPORT_READ_OWN,
    Perm.SUPPORT_CREATE,
    Perm.SUPPORT_COMMENT,
    Perm.USER_READ,
    Perm.DEPARTMENT_READ,
    Perm.FORM_SUBMIT,
    Perm.SUBMISSION_READ_COMPANY,
    Perm.APPROVAL_READ_ALL,
    Perm.NOTIFICATION_MANAGE,
}

FINANCE_MANAGER = _COMPANY_READ | _OPERATOR_READ | {
    Perm.REPORT_READ_ALL,
    Perm.FINANCIAL_REVIEW_READ,
    Perm.FINANCIAL_REVIEW_WRITE,
    Perm.SUPPORT_READ_OWN,
    Perm.SUPPORT_CREATE,
    Perm.SUPPORT_COMMENT,
    Perm.DEPARTMENT_READ,
    Perm.FORM_SUBMIT,
    Perm.SUBMISSION_READ_COMPANY,
    Perm.APPROVAL_READ_ALL,
}

HR_MANAGER = _COMPANY_READ | _OPERATOR_READ | {
    Perm.USER_READ,
    Perm.USER_UPDATE,
    Perm.USER_ASSIGN_COMPANY,
    Perm.DEPARTMENT_READ,
    Perm.DEPARTMENT_MANAGE,
    Perm.SECTOR_MANAGE,
    Perm.POSITION_MANAGE,
    Perm.MOTIVATION_MANAGE,
    Perm.SUPPORT_READ_OWN,
    Perm.SUPPORT_CREATE,
    Perm.SUPPORT_COMMENT,
    Perm.FORM_SUBMIT,
    Perm.SUBMISSION_READ_COMPANY,
}

DEPARTMENT_MANAGER = _COMPANY_READ | _OPERATOR_READ | {
    Perm.SUPPORT_READ_OWN,
    Perm.SUPPORT_CREATE,
    Perm.SUPPORT_COMMENT,
    Perm.FORM_SUBMIT,
    Perm.SUBMISSION_READ_COMPANY,
}

EMPLOYEE = {
    Perm.COMPANY_READ,
    Perm.REPORT_READ_OWN,
    Perm.DASHBOARD_COMPANY,
    Perm.AI_COMPANY,
    Perm.SUPPORT_READ_OWN,
    Perm.SUPPORT_CREATE,
    Perm.FORM_READ,
    Perm.REQUIREMENT_READ,
    Perm.FORM_SUBMIT,
    Perm.SUBMISSION_READ_OWN,
    Perm.APPROVAL_READ_OWN,
    Perm.APPROVAL_ACT,
    Perm.DOCUMENT_READ,
    Perm.DOCUMENT_UPLOAD,
    Perm.NOTIFICATION_READ_OWN,
}

COMPANY_MANAGER = _COMPANY_READ | _OPERATOR_READ | {
    Perm.REPORT_CREATE,
    Perm.REPORT_UPDATE,
    Perm.REPORT_SUBMIT,
    Perm.REPORT_DELETE,
    Perm.FINANCIAL_SUMMARY_READ_OWN,
    Perm.FINANCIAL_SUMMARY_CREATE,
    Perm.FINANCIAL_SUMMARY_UPDATE,
    Perm.FINANCIAL_SUMMARY_SUBMIT,
    Perm.FINANCIAL_SUMMARY_CORRECT,
    Perm.FINANCIAL_ITEM_MANAGE,
    Perm.FINANCIAL_BANK_READ,
    Perm.SUPPORT_READ_OWN,
    Perm.SUPPORT_CREATE,
    Perm.SUPPORT_COMMENT,
    Perm.DASHBOARD_COMPANY,
    Perm.AI_COMPANY,
    Perm.FORM_SUBMIT,
    Perm.SUBMISSION_READ_COMPANY,
    Perm.APPROVAL_READ_ALL,
    # S13: the company manager writes the independent lead note; marketing
    # reads it. Leads stay Holding-level (see website.py), so this grants the
    # write only -- visibility is still governed by website_lead.read.
    Perm.LEAD_MANAGER_NOTE,
    # S02/S09: the company replies to a clarification linked to its report.
    Perm.REPORT_CLARIFY,
}

ACCOUNTANT = _OPERATOR_READ | {
    Perm.COMPANY_READ,
    Perm.REPORT_READ_ALL,
    Perm.FINANCIAL_REVIEW_READ,
    Perm.FINANCIAL_REVIEW_WRITE,
    # Execution 02: the accountant reviews and decides, but never edits the
    # manager's entered financial figures (no create/update/submit/correct).
    Perm.FINANCIAL_SUMMARY_READ_ALL,
    Perm.FINANCIAL_REVIEW_ACT,
    Perm.FINANCIAL_BANK_READ,
    Perm.SUPPORT_READ_ALL,
    Perm.SUPPORT_COMMENT,
    Perm.SUPPORT_STATUS_CHANGE,
    Perm.DASHBOARD_HOLDING,
    Perm.DASHBOARD_COMPANY,
    Perm.AI_HOLDING,
    Perm.AI_COMPANY,
    Perm.APPROVAL_READ_ALL,
    Perm.SUBMISSION_READ_ALL,
    Perm.ANALYTICS_HOLDING,
    Perm.ANALYTICS_COMPANY,
    Perm.ANALYTICS_OPERATIONS,
    Perm.ANALYTICS_COMPLIANCE,
}

BUSINESS_DEVELOPMENT = _OPERATOR_READ | {
    Perm.COMPANY_READ,
    Perm.REPORT_READ_ALL,
    # Read-only financial view (spec: BD may read, never approve or edit, and
    # the private bank statement is not part of their view).
    Perm.FINANCIAL_SUMMARY_READ_ALL,
    Perm.SUPPORT_READ_ALL,
    Perm.SUPPORT_COMMENT,
    Perm.SUPPORT_STATUS_CHANGE,
    Perm.DASHBOARD_HOLDING,
    Perm.AI_HOLDING,
    Perm.APPROVAL_READ_ALL,
    Perm.ANALYTICS_OPERATIONS,
    # Website leads are routed to Business Development by default, so this role
    # owns the full lead pipeline and the opportunity review queue.
    Perm.LEAD_READ,
    Perm.LEAD_MANAGE,
    Perm.LEAD_STATUS_CHANGE,
    Perm.OPPORTUNITY_REVIEW,
}

MARKETING = _OPERATOR_READ | {
    Perm.COMPANY_READ,
    Perm.REPORT_READ_ALL,
    Perm.SUPPORT_READ_ALL,
    Perm.SUPPORT_COMMENT,
    Perm.SUPPORT_STATUS_CHANGE,
    Perm.DASHBOARD_HOLDING,
    Perm.AI_HOLDING,
    Perm.APPROVAL_READ_ALL,
    Perm.ANALYTICS_OPERATIONS,
    Perm.LEAD_READ,
    Perm.LEAD_STATUS_CHANGE,
    Perm.OPPORTUNITY_REVIEW,
    # Website Management: marketing drafts and uploads, but publishing and
    # site-wide settings stay with Holding administration.
    Perm.WEBSITE_MANAGE,
    Perm.WEBSITE_CONTENT_READ,
    Perm.WEBSITE_CONTENT_WRITE,
    Perm.WEBSITE_MEDIA_MANAGE,
}

DESIGNER = _OPERATOR_READ | {
    Perm.COMPANY_READ,
    Perm.REPORT_READ_ALL,
    Perm.SUPPORT_READ_ALL,
    Perm.SUPPORT_COMMENT,
    Perm.SUPPORT_STATUS_CHANGE,
    Perm.DASHBOARD_HOLDING,
    Perm.AI_HOLDING,
    Perm.APPROVAL_READ_ALL,
    Perm.ANALYTICS_OPERATIONS,
    # Executions 04-14: designer work queue (S16/S17)
    Perm.TASK_READ_OWN,
    Perm.TASK_STATUS_CHANGE,
    Perm.DESIGN_REQUEST_MANAGE,
    Perm.DESIGN_REQUEST_DELIVER,
    Perm.WEEKLY_REPORT_READ_OWN,
    Perm.WEEKLY_REPORT_SUBMIT,
}


# --------------------------------------------------------------------------
# Executions 04-14: holding-business domain grants (D01-D11)
# --------------------------------------------------------------------------

# Every role that operates day-to-day gets read access to tasks in its scope.
_BUSINESS_READ = {
    Perm.TASK_READ_OWN,
    Perm.TASK_READ_ALL,
    Perm.WEEKLY_REPORT_READ_OWN,
    Perm.KPI_READ,
}

# Business Development: assigns tasks, reviews employees, reads projects,
# owner decisions and (read-only) holding finance. Never edits salaries.
BUSINESS_DEVELOPMENT_EXT = {
    Perm.EMPLOYEE_READ,
    Perm.EMPLOYEE_MOVEMENT_READ,
    Perm.ASSESSMENT_READ,
    Perm.ASSESSMENT_MANAGE,
    Perm.TASK_CREATE,
    Perm.TASK_UPDATE,
    Perm.TASK_STATUS_CHANGE,
    Perm.WEEKLY_REPORT_READ_ALL,
    Perm.WEEKLY_REPORT_TEMPLATE_MANAGE,
    Perm.CAMPAIGN_READ,
    Perm.CAMPAIGN_MANAGE,
    Perm.ADVISOR_READ,
    Perm.ADVISOR_MANAGE,
    Perm.OWNER_DECISION_READ,
    Perm.PROJECT_READ,
    Perm.PROJECT_MANAGE,
    # S21: BD authors the five-axis monthly brief and can raise a clarification
    # against a company's original report (without editing it).
    Perm.MANAGEMENT_BRIEF_READ,
    Perm.MANAGEMENT_BRIEF_SUBMIT,
    Perm.REPORT_CLARIFY,
    Perm.REPORT_READ_ALL,
    Perm.OPENING_BALANCE_READ,
    Perm.ACCOUNT_READ,
    Perm.JOURNAL_READ,
    Perm.INVOICE_READ,
    Perm.ASSET_READ,
    Perm.BUDGET_READ,
    Perm.PARTY_READ,
    Perm.INTERBALANCE_READ,
    Perm.KPI_MANAGE,
    # S28 Table 80: BD reads the holding's financial reports (read-only).
    Perm.FINANCIAL_REPORT_READ,
}

# Accountant: the holding accounts surface (D01) plus budget approval input.
ACCOUNTANT_EXT = {
    # S21: the accountant reads the management brief (the spec lists the
    # accountant's financial reports alongside it), but does not author it.
    Perm.MANAGEMENT_BRIEF_READ,
    # S07 / AC-07: the spec gives form-and-field (incl. special-item) item
    # configuration to the owner *and* the accountant. Without this the
    # accountant cannot create the item definitions the special-item screen
    # requires.
    Perm.FINANCIAL_ITEM_MANAGE,
    Perm.OPENING_BALANCE_READ,
    Perm.OPENING_BALANCE_MANAGE,
    Perm.OPENING_BALANCE_APPROVE,
    Perm.ACCOUNT_READ,
    Perm.ACCOUNT_MANAGE,
    Perm.JOURNAL_READ,
    Perm.JOURNAL_CREATE,
    Perm.JOURNAL_POST,
    Perm.JOURNAL_REVERSE,
    Perm.INVOICE_READ,
    Perm.INVOICE_MANAGE,
    Perm.SETTLEMENT_MANAGE,
    Perm.PARTY_READ,
    Perm.PARTY_MANAGE,
    Perm.INTERBALANCE_READ,
    Perm.INTERBALANCE_MANAGE,
    Perm.ASSET_READ,
    Perm.ASSET_MANAGE,
    Perm.BUDGET_READ,
    Perm.BUDGET_MANAGE,
    # D01: the accountant drafts and approves accounting policy.
    Perm.POLICY_READ,
    Perm.POLICY_MANAGE,
    Perm.POLICY_APPROVE,
    Perm.TASK_READ_OWN,
    Perm.TASK_STATUS_CHANGE,
    Perm.WEEKLY_REPORT_READ_OWN,
    Perm.WEEKLY_REPORT_SUBMIT,
    Perm.KPI_READ,
    # S28: the accountant owns the monthly financial report.
    Perm.FINANCIAL_REPORT_READ,
    Perm.FINANCIAL_REPORT_MANAGE,
    Perm.FINANCIAL_REPORT_FINALISE,
}

# Marketing: campaigns and confidential complaint submission (D02/D04).
MARKETING_EXT = {
    Perm.CAMPAIGN_READ,
    Perm.CAMPAIGN_MANAGE,
    Perm.COMPLAINT_CREATE,
    Perm.COMPLAINT_READ_OWN,
    Perm.TASK_READ_OWN,
    Perm.TASK_STATUS_CHANGE,
    Perm.WEEKLY_REPORT_READ_OWN,
    Perm.WEEKLY_REPORT_SUBMIT,
    Perm.KPI_READ,
}

# Company Manager: employees, tasks, weekly reports, opening balances for its
# companies, and the received owner directives.
COMPANY_MANAGER_EXT = {
    Perm.EMPLOYEE_READ,
    Perm.EMPLOYEE_MANAGE,
    Perm.EMPLOYEE_MOVEMENT_READ,
    Perm.EMPLOYEE_MOVEMENT_MANAGE,
    Perm.EMPLOYEE_MOVEMENT_APPROVE,
    Perm.ASSESSMENT_READ,
    Perm.ASSESSMENT_MANAGE,
    Perm.TASK_READ_OWN,
    Perm.TASK_READ_ALL,
    Perm.TASK_CREATE,
    Perm.TASK_UPDATE,
    Perm.TASK_STATUS_CHANGE,
    Perm.WEEKLY_REPORT_READ_OWN,
    Perm.WEEKLY_REPORT_SUBMIT,
    Perm.WEEKLY_REPORT_READ_ALL,
    Perm.OPENING_BALANCE_READ,
    Perm.OPENING_BALANCE_MANAGE,
    Perm.OWNER_DECISION_READ,
    Perm.KPI_READ,
    # S28: a company-scoped manager reads its own company's financial report.
    Perm.FINANCIAL_REPORT_READ,
}

# External Consultant (S19 / D04): only explicitly granted data; no ledger, no
# approvals, no other employees, no leadership assessment.
EXTERNAL_CONSULTANT = {
    Perm.COMPANY_READ,
    Perm.DASHBOARD_COMPANY,
    Perm.ADVISOR_SESSION_READ_OWN,
    Perm.ADVISOR_SESSION_RECORD,
    Perm.WEEKLY_REPORT_READ_OWN,
    Perm.WEEKLY_REPORT_SUBMIT,
    Perm.NOTIFICATION_READ_OWN,
}



ROLE_PERMISSIONS: dict[str, set[str]] = {
    RoleCode.HOLDING_OWNER.value: HOLDING_OWNER,
    RoleCode.SUPER_ADMIN.value: SUPER_ADMIN,
    RoleCode.HOLDING_FINANCE.value: HOLDING_FINANCE | ACCOUNTANT_EXT,
    RoleCode.COMPANY_OWNER.value: COMPANY_OWNER | COMPANY_MANAGER_EXT,
    RoleCode.CEO.value: CEO | COMPANY_MANAGER_EXT,
    RoleCode.COMPANY_MANAGER.value: COMPANY_MANAGER | COMPANY_MANAGER_EXT,
    RoleCode.FINANCE_MANAGER.value: FINANCE_MANAGER | {
        Perm.OPENING_BALANCE_READ,
        Perm.ACCOUNT_READ,
        Perm.JOURNAL_READ,
        Perm.INVOICE_READ,
        Perm.ASSET_READ,
        Perm.BUDGET_READ,
        Perm.KPI_READ,
        Perm.PARTY_READ,
        Perm.INTERBALANCE_READ,
        Perm.TASK_READ_OWN,
        # S28: the finance manager reads the holding's financial reports.
        Perm.FINANCIAL_REPORT_READ,
    },
    RoleCode.HR_MANAGER.value: HR_MANAGER | {
        Perm.EMPLOYEE_READ,
        Perm.EMPLOYEE_MANAGE,
        Perm.EMPLOYEE_MOVEMENT_READ,
        Perm.EMPLOYEE_MOVEMENT_MANAGE,
        Perm.EMPLOYEE_MOVEMENT_APPROVE,
        Perm.ASSESSMENT_READ,
        Perm.ASSESSMENT_MANAGE,
        Perm.TASK_READ_OWN,
        Perm.WEEKLY_REPORT_READ_OWN,
        Perm.WEEKLY_REPORT_SUBMIT,
        Perm.WEEKLY_REPORT_READ_ALL,
    },
    RoleCode.DEPARTMENT_MANAGER.value: DEPARTMENT_MANAGER | {
        Perm.TASK_READ_OWN,
        Perm.TASK_CREATE,
        Perm.TASK_UPDATE,
        Perm.TASK_STATUS_CHANGE,
        Perm.WEEKLY_REPORT_READ_OWN,
        Perm.WEEKLY_REPORT_SUBMIT,
    },
    RoleCode.ACCOUNTANT.value: ACCOUNTANT | ACCOUNTANT_EXT,
    RoleCode.BUSINESS_DEVELOPMENT.value: BUSINESS_DEVELOPMENT | BUSINESS_DEVELOPMENT_EXT,
    RoleCode.MARKETING.value: MARKETING | MARKETING_EXT,
    RoleCode.DESIGNER.value: DESIGNER,
    RoleCode.EMPLOYEE.value: EMPLOYEE | {
        Perm.TASK_READ_OWN,
        Perm.TASK_STATUS_CHANGE,
        Perm.WEEKLY_REPORT_READ_OWN,
        Perm.WEEKLY_REPORT_SUBMIT,
        Perm.KPI_READ,
    },
    RoleCode.EXTERNAL_CONSULTANT.value: EXTERNAL_CONSULTANT,
}


ROLE_DEFINITIONS: list[dict[str, str]] = [
    {
        "code": RoleCode.HOLDING_OWNER.value,
        "name_ar": "مالك المجموعة",
        "name_en": "Holding Owner",
        "description": "Full authority across the Holding and all subsidiaries.",
        "description_ar": "صلاحية كاملة على القابضة وجميع الشركات التابعة.",
    },
    {
        "code": RoleCode.SUPER_ADMIN.value,
        "name_ar": "مدير النظام الأعلى",
        "name_en": "Super Admin",
        "description": "Delegated group administration across the Holding.",
        "description_ar": "إدارة مفوّضة لعمليات المجموعة على مستوى القابضة.",
    },
    {
        "code": RoleCode.HOLDING_FINANCE.value,
        "name_ar": "مالية المجموعة",
        "name_en": "Holding Finance",
        "description": "Group-wide financial oversight and read-only administration.",
        "description_ar": "إشراف مالي على مستوى المجموعة وإدارة للاطّلاع فقط.",
    },
    {
        "code": RoleCode.COMPANY_OWNER.value,
        "name_ar": "مالك الشركة",
        "name_en": "Company Owner",
        "description": "Governs one or more subsidiaries the user is granted.",
        "description_ar": "يتولّى إدارة شركة تابعة أو أكثر ممنوحة للمستخدم.",
    },
    {
        "code": RoleCode.CEO.value,
        "name_ar": "الرئيس التنفيذي",
        "name_en": "CEO",
        "description": "Executive oversight of the granted subsidiaries.",
        "description_ar": "إشراف تنفيذي على الشركات التابعة الممنوحة.",
    },
    {
        "code": RoleCode.FINANCE_MANAGER.value,
        "name_ar": "مدير مالي",
        "name_en": "Finance Manager",
        "description": "Manages financial review within the granted subsidiaries.",
        "description_ar": "يدير المراجعة المالية داخل الشركات التابعة الممنوحة.",
    },
    {
        "code": RoleCode.HR_MANAGER.value,
        "name_ar": "مدير الموارد البشرية",
        "name_en": "HR Manager",
        "description": "Manages people and departments within the granted subsidiaries.",
        "description_ar": "يدير الموظفين والأقسام داخل الشركات التابعة الممنوحة.",
    },
    {
        "code": RoleCode.DEPARTMENT_MANAGER.value,
        "name_ar": "مدير قسم",
        "name_en": "Department Manager",
        "description": "Leads a department within a granted subsidiary.",
        "description_ar": "يقود قسمًا داخل شركة تابعة ممنوحة.",
    },
    {
        "code": RoleCode.EMPLOYEE.value,
        "name_ar": "موظف",
        "name_en": "Employee",
        "description": "Reads company data and raises support requests.",
        "description_ar": "يطّلع على بيانات الشركة ويرفع طلبات الدعم.",
    },
    {
        "code": RoleCode.COMPANY_MANAGER.value,
        "name_ar": "مدير الشركة",
        "name_en": "Company Manager",
        "description": "Manages one subsidiary and submits its monthly report.",
        "description_ar": "يدير شركة تابعة واحدة ويرفع تقريرها الشهري.",
    },
    {
        "code": RoleCode.ACCOUNTANT.value,
        "name_ar": "المحاسب",
        "name_en": "Accountant",
        "description": "Reviews and verifies the financial data of submitted reports.",
        "description_ar": "يراجع ويتحقّق من البيانات المالية للتقارير المرفوعة.",
    },
    {
        "code": RoleCode.BUSINESS_DEVELOPMENT.value,
        "name_ar": "تطوير الأعمال",
        "name_en": "Business Development",
        "description": "Handles business development support requests.",
        "description_ar": "يتعامل مع طلبات دعم تطوير الأعمال.",
    },
    {
        "code": RoleCode.MARKETING.value,
        "name_ar": "التسويق",
        "name_en": "Marketing",
        "description": "Handles marketing support requests.",
        "description_ar": "يتعامل مع طلبات الدعم التسويقي.",
    },
    {
        "code": RoleCode.DESIGNER.value,
        "name_ar": "التصميم",
        "name_en": "Designer",
        "description": "Handles design support requests.",
        "description_ar": "يتعامل مع طلبات الدعم التصميمي.",
    },
    {
        "code": RoleCode.EXTERNAL_CONSULTANT.value,
        "name_ar": "مستشار خارجي",
        "name_en": "External Consultant",
        "description": "Advisor with access only to explicitly granted employees and sessions.",
        "description_ar": "مستشار يصل فقط إلى الموظفين والجلسات المصرّح بها صراحةً.",
    },
]


# Roles that may see across company boundaries (subject to further checks).
# Company-level governance roles (Company Owner, CEO, Finance/HR/Department
# Manager, Employee) are deliberately *not* here: they stay confined to the
# companies granted in ``user_company_access``.
HOLDING_WIDE_ROLES = {
    RoleCode.HOLDING_OWNER.value,
    RoleCode.SUPER_ADMIN.value,
    RoleCode.HOLDING_FINANCE.value,
    RoleCode.ACCOUNTANT.value,
    RoleCode.BUSINESS_DEVELOPMENT.value,
    RoleCode.MARKETING.value,
    RoleCode.DESIGNER.value,
}


# Roles whose administration scope is the entire group. A user may only be
# granted a role whose permission set is a subset of their own, which is how
# privilege escalation is prevented (see ``admin_service.assert_can_grant_role``).
def role_permission_set(role_code: str) -> set[str]:
    return set(ROLE_PERMISSIONS.get(role_code, set()))
