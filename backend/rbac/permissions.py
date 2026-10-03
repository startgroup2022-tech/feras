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
}

# Holding Finance: group-wide financial oversight and read-only admin views.
HOLDING_FINANCE = _HOLDING_READ | {
    Perm.FINANCIAL_REVIEW_READ,
    Perm.FINANCIAL_REVIEW_WRITE,
    Perm.SUPPORT_READ_ALL,
    Perm.SUPPORT_COMMENT,
    Perm.USER_READ_ALL,
    Perm.ROLE_READ,
    Perm.PERMISSION_READ,
    Perm.AUDIT_READ,
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
}

COMPANY_OWNER = _COMPANY_READ | {
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
}

CEO = _COMPANY_READ | {
    Perm.REPORT_CREATE,
    Perm.REPORT_UPDATE,
    Perm.REPORT_SUBMIT,
    Perm.FINANCIAL_REVIEW_READ,
    Perm.SUPPORT_READ_OWN,
    Perm.SUPPORT_CREATE,
    Perm.SUPPORT_COMMENT,
    Perm.USER_READ,
    Perm.DEPARTMENT_READ,
}

FINANCE_MANAGER = _COMPANY_READ | {
    Perm.REPORT_READ_ALL,
    Perm.FINANCIAL_REVIEW_READ,
    Perm.FINANCIAL_REVIEW_WRITE,
    Perm.SUPPORT_READ_OWN,
    Perm.SUPPORT_CREATE,
    Perm.SUPPORT_COMMENT,
    Perm.DEPARTMENT_READ,
}

HR_MANAGER = _COMPANY_READ | {
    Perm.USER_READ,
    Perm.USER_UPDATE,
    Perm.USER_ASSIGN_COMPANY,
    Perm.DEPARTMENT_READ,
    Perm.DEPARTMENT_MANAGE,
    Perm.SUPPORT_READ_OWN,
    Perm.SUPPORT_CREATE,
    Perm.SUPPORT_COMMENT,
}

DEPARTMENT_MANAGER = _COMPANY_READ | {
    Perm.SUPPORT_READ_OWN,
    Perm.SUPPORT_CREATE,
    Perm.SUPPORT_COMMENT,
}

EMPLOYEE = {
    Perm.COMPANY_READ,
    Perm.REPORT_READ_OWN,
    Perm.DASHBOARD_COMPANY,
    Perm.AI_COMPANY,
    Perm.SUPPORT_READ_OWN,
    Perm.SUPPORT_CREATE,
}

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
    },
    {
        "code": RoleCode.SUPER_ADMIN.value,
        "name_ar": "مدير النظام الأعلى",
        "name_en": "Super Admin",
        "description": "Delegated group administration across the Holding.",
    },
    {
        "code": RoleCode.HOLDING_FINANCE.value,
        "name_ar": "مالية المجموعة",
        "name_en": "Holding Finance",
        "description": "Group-wide financial oversight and read-only administration.",
    },
    {
        "code": RoleCode.COMPANY_OWNER.value,
        "name_ar": "مالك الشركة",
        "name_en": "Company Owner",
        "description": "Governs one or more subsidiaries the user is granted.",
    },
    {
        "code": RoleCode.CEO.value,
        "name_ar": "الرئيس التنفيذي",
        "name_en": "CEO",
        "description": "Executive oversight of the granted subsidiaries.",
    },
    {
        "code": RoleCode.FINANCE_MANAGER.value,
        "name_ar": "مدير مالي",
        "name_en": "Finance Manager",
        "description": "Manages financial review within the granted subsidiaries.",
    },
    {
        "code": RoleCode.HR_MANAGER.value,
        "name_ar": "مدير الموارد البشرية",
        "name_en": "HR Manager",
        "description": "Manages people and departments within the granted subsidiaries.",
    },
    {
        "code": RoleCode.DEPARTMENT_MANAGER.value,
        "name_ar": "مدير قسم",
        "name_en": "Department Manager",
        "description": "Leads a department within a granted subsidiary.",
    },
    {
        "code": RoleCode.EMPLOYEE.value,
        "name_ar": "موظف",
        "name_en": "Employee",
        "description": "Reads company data and raises support requests.",
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
