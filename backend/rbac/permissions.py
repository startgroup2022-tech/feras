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
    OPPORTUNITY_REVIEW = "website_opportunity.review"  # review submitted listings
    OPPORTUNITY_PUBLISH = "website_opportunity.publish"  # publish a listing publicly


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
    Perm.OPPORTUNITY_REVIEW: "Review submitted business listings",
    Perm.OPPORTUNITY_PUBLISH: "Publish a business listing on the public website",
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
    Perm.ANALYTICS_HOLDING,
    Perm.ANALYTICS_COMPANY,
    Perm.ANALYTICS_OPERATIONS,
    Perm.ANALYTICS_COMPLIANCE,
    Perm.ANALYTICS_EXPORT,
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
    Perm.ANALYTICS_COMPANY,
}

COMPANY_OWNER = _COMPANY_READ | _OPERATOR_READ | _COMPANY_BUILDER | {
    Perm.REPORT_CREATE,
    Perm.REPORT_UPDATE,
    Perm.REPORT_SUBMIT,
    Perm.REPORT_DELETE,
    Perm.FINANCIAL_REVIEW_READ,
    Perm.SUPPORT_READ_OWN,
    Perm.SUPPORT_CREATE,
    Perm.SUPPORT_COMMENT,
    Perm.USER_READ,
    Perm.USER_UPDATE,
    Perm.USER_ASSIGN_COMPANY,
    Perm.DEPARTMENT_MANAGE,
    Perm.COMPANY_UPDATE,
    Perm.FORM_SUBMIT,
    Perm.SUBMISSION_READ_COMPANY,
    Perm.SUBMISSION_CANCEL,
    Perm.APPROVAL_READ_ALL,
    Perm.DOCUMENT_CATEGORY_MANAGE,
    Perm.NOTIFICATION_MANAGE,
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
    Perm.SUPPORT_READ_OWN,
    Perm.SUPPORT_CREATE,
    Perm.SUPPORT_COMMENT,
    Perm.DASHBOARD_COMPANY,
    Perm.AI_COMPANY,
    Perm.FORM_SUBMIT,
    Perm.SUBMISSION_READ_COMPANY,
    Perm.APPROVAL_READ_ALL,
}

ACCOUNTANT = _OPERATOR_READ | {
    Perm.COMPANY_READ,
    Perm.REPORT_READ_ALL,
    Perm.FINANCIAL_REVIEW_READ,
    Perm.FINANCIAL_REVIEW_WRITE,
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
}


ROLE_PERMISSIONS: dict[str, set[str]] = {
    RoleCode.HOLDING_OWNER.value: HOLDING_OWNER,
    RoleCode.SUPER_ADMIN.value: SUPER_ADMIN,
    RoleCode.HOLDING_FINANCE.value: HOLDING_FINANCE,
    RoleCode.COMPANY_OWNER.value: COMPANY_OWNER,
    RoleCode.CEO.value: CEO,
    RoleCode.COMPANY_MANAGER.value: COMPANY_MANAGER,
    RoleCode.FINANCE_MANAGER.value: FINANCE_MANAGER,
    RoleCode.HR_MANAGER.value: HR_MANAGER,
    RoleCode.DEPARTMENT_MANAGER.value: DEPARTMENT_MANAGER,
    RoleCode.ACCOUNTANT.value: ACCOUNTANT,
    RoleCode.BUSINESS_DEVELOPMENT.value: BUSINESS_DEVELOPMENT,
    RoleCode.MARKETING.value: MARKETING,
    RoleCode.DESIGNER.value: DESIGNER,
    RoleCode.EMPLOYEE.value: EMPLOYEE,
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
