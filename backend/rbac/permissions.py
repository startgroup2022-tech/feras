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


ALL_PERMISSIONS: dict[str, str] = {
    Perm.USER_READ: "View users",
    Perm.USER_MANAGE: "Create, update and deactivate users",
    Perm.COMPANY_READ: "View companies",
    Perm.COMPANY_MANAGE: "Create and update companies",
    Perm.COMPANY_ACCESS_MANAGE: "Grant or revoke a user's company access",
    Perm.AUDIT_READ: "Read the audit log",
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
}


# --------------------------------------------------------------------------
# Role -> permission grants
# --------------------------------------------------------------------------
HOLDING_OWNER = set(ALL_PERMISSIONS.keys())  # full platform authority

COMPANY_MANAGER = {
    Perm.COMPANY_READ,
    Perm.REPORT_READ_OWN,
    Perm.REPORT_CREATE,
    Perm.REPORT_UPDATE,
    Perm.REPORT_SUBMIT,
    Perm.REPORT_DELETE,
    Perm.SUPPORT_READ_OWN,
    Perm.SUPPORT_CREATE,
    Perm.SUPPORT_COMMENT,
    Perm.DASHBOARD_COMPANY,
    Perm.AI_COMPANY,
}

ACCOUNTANT = {
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
}

BUSINESS_DEVELOPMENT = {
    Perm.COMPANY_READ,
    Perm.REPORT_READ_ALL,
    Perm.SUPPORT_READ_ALL,
    Perm.SUPPORT_COMMENT,
    Perm.SUPPORT_STATUS_CHANGE,
    Perm.DASHBOARD_HOLDING,
    Perm.AI_HOLDING,
}

MARKETING = {
    Perm.COMPANY_READ,
    Perm.REPORT_READ_ALL,
    Perm.SUPPORT_READ_ALL,
    Perm.SUPPORT_COMMENT,
    Perm.SUPPORT_STATUS_CHANGE,
    Perm.DASHBOARD_HOLDING,
    Perm.AI_HOLDING,
}

DESIGNER = {
    Perm.COMPANY_READ,
    Perm.REPORT_READ_ALL,
    Perm.SUPPORT_READ_ALL,
    Perm.SUPPORT_COMMENT,
    Perm.SUPPORT_STATUS_CHANGE,
    Perm.DASHBOARD_HOLDING,
    Perm.AI_HOLDING,
}


ROLE_PERMISSIONS: dict[str, set[str]] = {
    RoleCode.HOLDING_OWNER.value: HOLDING_OWNER,
    RoleCode.COMPANY_MANAGER.value: COMPANY_MANAGER,
    RoleCode.ACCOUNTANT.value: ACCOUNTANT,
    RoleCode.BUSINESS_DEVELOPMENT.value: BUSINESS_DEVELOPMENT,
    RoleCode.MARKETING.value: MARKETING,
    RoleCode.DESIGNER.value: DESIGNER,
}


ROLE_DEFINITIONS: list[dict[str, str]] = [
    {
        "code": RoleCode.HOLDING_OWNER.value,
        "name_ar": "مالك المجموعة",
        "name_en": "Holding Owner",
        "description": "Full authority across the Holding and all subsidiaries.",
    },
    {
        "code": RoleCode.COMPANY_MANAGER.value,
        "name_ar": "مدير الشركة",
        "name_en": "Company Manager",
        "description": "Manages one subsidiary and submits its monthly report.",
    },
    {
        "code": RoleCode.ACCOUNTANT.value,
        "name_ar": "المحاسب",
        "name_en": "Accountant",
        "description": "Reviews and verifies the financial data of submitted reports.",
    },
    {
        "code": RoleCode.BUSINESS_DEVELOPMENT.value,
        "name_ar": "تطوير الأعمال",
        "name_en": "Business Development",
        "description": "Handles business development support requests.",
    },
    {
        "code": RoleCode.MARKETING.value,
        "name_ar": "التسويق",
        "name_en": "Marketing",
        "description": "Handles marketing support requests.",
    },
    {
        "code": RoleCode.DESIGNER.value,
        "name_ar": "التصميم",
        "name_en": "Designer",
        "description": "Handles design support requests.",
    },
]


# Roles that may see across company boundaries (subject to further checks).
HOLDING_WIDE_ROLES = {
    RoleCode.HOLDING_OWNER.value,
    RoleCode.ACCOUNTANT.value,
    RoleCode.BUSINESS_DEVELOPMENT.value,
    RoleCode.MARKETING.value,
    RoleCode.DESIGNER.value,
}
