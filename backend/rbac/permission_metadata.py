"""Bilingual, human-readable metadata for the permission catalogue.

This module is the *presentation* layer for :mod:`backend.rbac.permissions`.
It adds Arabic/English names, short descriptions, a logical category, the
action kind (view/create/edit/delete/manage/approve/assign/publish/read own/
read all) and a "danger" hint to each permission code.

It changes no authorization semantics: enforcement still happens against the
codes in :mod:`backend.rbac.permissions`, and a permission missing here simply
falls back to its code and the generic description from ``ALL_PERMISSIONS``.
"""

from __future__ import annotations

from backend.rbac.permissions import ALL_PERMISSIONS, Perm

# Logical groups an administrator can scan. ``order`` drives the UI ordering.
CATEGORIES: list[dict] = [
    {"key": "dashboard", "name_ar": "لوحة القيادة", "name_en": "Dashboard", "order": 10},
    {"key": "companies", "name_ar": "الشركات التابعة", "name_en": "Companies", "order": 20},
    {"key": "users", "name_ar": "المستخدمون", "name_en": "Users", "order": 30},
    {"key": "roles", "name_ar": "الأدوار والصلاحيات", "name_en": "Roles & Permissions", "order": 40},
    {"key": "reports", "name_ar": "التقارير الشهرية", "name_en": "Monthly Reports", "order": 50},
    {"key": "financial", "name_ar": "المراجعة المالية", "name_en": "Financial Reviews", "order": 60},
    {"key": "support", "name_ar": "طلبات الدعم", "name_en": "Support Requests", "order": 70},
    {"key": "forms", "name_ar": "النماذج", "name_en": "Forms", "order": 80},
    {"key": "workflows", "name_ar": "سير العمل", "name_en": "Workflows", "order": 90},
    {"key": "approvals", "name_ar": "الموافقات", "name_en": "Approvals", "order": 100},
    {"key": "documents", "name_ar": "المستندات", "name_en": "Documents", "order": 110},
    {"key": "leads", "name_ar": "طلبات الموقع", "name_en": "Website Leads", "order": 120},
    {"key": "opportunities", "name_ar": "الفرص", "name_en": "Opportunities", "order": 130},
    {"key": "website", "name_ar": "إدارة الموقع", "name_en": "Website Management", "order": 135},
    {"key": "notifications", "name_ar": "الإشعارات", "name_en": "Notifications", "order": 140},
    {"key": "analytics", "name_ar": "التحليلات", "name_en": "Analytics", "order": 150},
    {"key": "ai", "name_ar": "الذكاء الاصطناعي", "name_en": "AI", "order": 160},
    {"key": "integrations", "name_ar": "التكاملات", "name_en": "Integrations", "order": 170},
    # Executions 04-14
    {"key": "employees", "name_ar": "الموظفون والتقييم", "name_en": "Employees & Assessment", "order": 175},
    {"key": "tasks", "name_ar": "المهام والتقارير الأسبوعية", "name_en": "Tasks & Weekly Reports", "order": 178},
    {"key": "campaigns", "name_ar": "الحملات التسويقية", "name_en": "Campaigns", "order": 182},
    {"key": "complaints", "name_ar": "الشكاوى السرية", "name_en": "Complaints", "order": 185},
    {"key": "advisors", "name_ar": "المستشارون والجلسات", "name_en": "Advisors & Sessions", "order": 188},
    {"key": "decisions", "name_ar": "قرارات المالك", "name_en": "Owner Decisions", "order": 190},
    {"key": "projects", "name_ar": "المشاريع والفرص", "name_en": "Projects & Opportunities", "order": 191},
    {"key": "accounting", "name_ar": "محاسبة القابضة", "name_en": "Holding Accounting", "order": 192},
    {"key": "balances", "name_ar": "الأرصدة الافتتاحية", "name_en": "Opening Balances", "order": 194},
    {"key": "kpi", "name_ar": "مؤشرات الأداء", "name_en": "KPIs", "order": 196},
    {"key": "confidential", "name_ar": "الوصول السري", "name_en": "Confidential Access", "order": 198},
    {"key": "audit", "name_ar": "التدقيق والإدارة", "name_en": "Audit / Administration", "order": 180},
]

# Action kinds, in the order they should be shown inside a category.
ACTIONS: list[dict] = [
    {"key": "view", "name_ar": "عرض", "name_en": "View", "order": 10},
    {"key": "read_own", "name_ar": "قراءة الخاصة", "name_en": "Read own", "order": 20},
    {"key": "read_all", "name_ar": "قراءة الكل", "name_en": "Read all", "order": 30},
    {"key": "create", "name_ar": "إنشاء", "name_en": "Create", "order": 40},
    {"key": "edit", "name_ar": "تعديل", "name_en": "Edit", "order": 50},
    {"key": "assign", "name_ar": "إسناد", "name_en": "Assign", "order": 60},
    {"key": "approve", "name_ar": "اعتماد", "name_en": "Approve", "order": 70},
    {"key": "publish", "name_ar": "نشر", "name_en": "Publish", "order": 80},
    {"key": "manage", "name_ar": "إدارة", "name_en": "Manage", "order": 90},
    {"key": "delete", "name_ar": "حذف", "name_en": "Delete", "order": 100},
]

_ACTION_BY_KEY = {a["key"]: a for a in ACTIONS}
_CATEGORY_BY_KEY = {c["key"]: c for c in CATEGORIES}


def _p(code, category, action, name_ar, name_en, desc_ar, desc_en, danger=False):
    return {
        "code": code,
        "category": category,
        "action": action,
        "name_ar": name_ar,
        "name_en": name_en,
        "description_ar": desc_ar,
        "description_en": desc_en,
        "danger": danger,
    }


# Every permission code in ALL_PERMISSIONS, described for a non-technical owner.
PERMISSION_METADATA: list[dict] = [
    # ---- dashboard ----
    _p(Perm.DASHBOARD_HOLDING, "dashboard", "view",
       "لوحة القيادة التنفيذية للمجموعة", "Group executive dashboard",
       "عرض مؤشرات المجموعة كاملة وإيرادات الشركات التابعة.",
       "View group-wide indicators and subsidiary revenue."),
    _p(Perm.DASHBOARD_COMPANY, "dashboard", "view",
       "لوحة قيادة الشركة", "Company dashboard",
       "عرض لوحة القيادة الخاصة بالشركات المصرّح بها فقط.",
       "View the dashboard for your permitted companies only."),

    # ---- companies ----
    _p(Perm.COMPANY_READ, "companies", "view",
       "عرض الشركات التابعة", "View subsidiaries",
       "الاطّلاع على بيانات الشركات التابعة المصرّح بها.",
       "See the subsidiaries you have been granted access to."),
    _p(Perm.COMPANY_MANAGE, "companies", "manage",
       "إدارة الشركات", "Manage companies",
       "إنشاء الشركات التابعة وتعديل بياناتها.",
       "Create subsidiaries and edit their details.", danger=True),
    _p(Perm.COMPANY_CREATE, "companies", "create",
       "إضافة شركة تابعة", "Register a subsidiary",
       "تسجيل شركة تابعة جديدة في المجموعة.",
       "Register a new subsidiary in the group.", danger=True),
    _p(Perm.COMPANY_UPDATE, "companies", "edit",
       "تعديل بيانات الشركة", "Edit company details",
       "تعديل البيانات الإدارية لشركة تابعة.",
       "Edit a subsidiary's administrative details."),
    _p(Perm.COMPANY_ARCHIVE, "companies", "manage",
       "أرشفة الشركة", "Archive a company",
       "تفعيل أو تعطيل أو أرشفة شركة تابعة.",
       "Activate, deactivate or archive a subsidiary.", danger=True),
    _p(Perm.COMPANY_ACCESS_MANAGE, "companies", "assign",
       "إدارة صلاحية الوصول للشركات", "Manage company access",
       "منح أو سحب صلاحية وصول المستخدم إلى شركة معيّنة.",
       "Grant or revoke a user's access to a company.", danger=True),
    _p(Perm.OWNERSHIP_READ, "companies", "view",
       "عرض هيكل الملكية", "View ownership structure",
       "الاطّلاع على هيكل ملكية المجموعة وحصص الشركات.",
       "See the group ownership structure and stakes."),
    _p(Perm.OWNERSHIP_MANAGE, "companies", "manage",
       "إدارة هيكل الملكية", "Manage ownership",
       "إنشاء وتعديل حصص الملكية في الشركات.",
       "Create and change ownership stakes.", danger=True),
    _p(Perm.DEPARTMENT_READ, "companies", "view",
       "عرض الأقسام", "View departments",
       "الاطّلاع على أقسام الشركات.",
       "See company departments."),
    _p(Perm.DEPARTMENT_MANAGE, "companies", "manage",
       "إدارة الأقسام", "Manage departments",
       "إنشاء وتعديل أقسام الشركات.",
       "Create and edit company departments."),
    _p(Perm.SECTOR_READ, "companies", "view",
       "عرض القطاعات", "View sectors",
       "الاطّلاع على قائمة القطاعات المُدارة.",
       "See the managed sector list."),
    _p(Perm.SECTOR_MANAGE, "companies", "manage",
       "إدارة القطاعات", "Manage sectors",
       "إنشاء وتعديل القطاعات المستخدمة لتصنيف الشركات.",
       "Create and edit the sectors used to classify companies."),
    _p(Perm.POSITION_READ, "companies", "view",
       "عرض المناصب التنظيمية", "View positions",
       "الاطّلاع على المناصب والتبعية التنظيمية.",
       "See organisational positions and reporting lines."),
    _p(Perm.POSITION_MANAGE, "companies", "manage",
       "إدارة المناصب التنظيمية", "Manage positions",
       "إنشاء وتعديل المناصب وربط الموظفين والتبعية.",
       "Create and edit positions, holders and reporting lines."),
    _p(Perm.MOTIVATION_READ, "dashboard", "view",
       "عرض الجمل التحفيزية", "View motivation texts",
       "الاطّلاع على مكتبة الجمل التحفيزية في لوحات المعلومات.",
       "See the motivational sentence library shown on dashboards."),
    _p(Perm.MOTIVATION_MANAGE, "dashboard", "manage",
       "إدارة الجمل التحفيزية", "Manage motivation texts",
       "إنشاء وتعديل الجمل التحفيزية المعروضة في لوحات المعلومات.",
       "Create and edit the motivational sentences shown on dashboards."),
    _p(Perm.GROUP_MANAGE, "companies", "manage",
       "إدارة بيانات القابضة", "Manage Holding settings",
       "ضبط بيانات القابضة (الاسم القانوني والسجل والافتراضات).",
       "Configure the Holding (legal name, registration, defaults).", danger=True),

    # ---- users ----
    _p(Perm.USER_READ, "users", "view",
       "عرض مستخدمي الشركة", "View company users",
       "الاطّلاع على مستخدمي الشركات المصرّح بها.",
       "See users within your permitted companies."),
    _p(Perm.USER_READ_ALL, "users", "read_all",
       "عرض كل المستخدمين", "View all users",
       "الاطّلاع على دليل المستخدمين كاملًا في المجموعة.",
       "See the full user directory across the group."),
    _p(Perm.USER_MANAGE, "users", "manage",
       "إدارة المستخدمين", "Manage users",
       "إنشاء المستخدمين وتعديلهم وتعطيلهم.",
       "Create, update and deactivate users.", danger=True),
    _p(Perm.USER_CREATE, "users", "create",
       "إضافة مستخدم", "Create users",
       "إنشاء حسابات مستخدمين جديدة.",
       "Create new user accounts.", danger=True),
    _p(Perm.USER_UPDATE, "users", "edit",
       "تعديل المستخدم", "Edit users",
       "تعديل بيانات المستخدم ودوره وحالة تفعيله.",
       "Edit a user's details, role and active state.", danger=True),
    _p(Perm.USER_ASSIGN_COMPANY, "users", "assign",
       "إسناد المستخدم للشركات", "Assign users to companies",
       "ربط المستخدم بشركات وأقسام محدّدة.",
       "Assign a user to companies and departments.", danger=True),

    # ---- roles & permissions ----
    _p(Perm.ROLE_READ, "roles", "view",
       "عرض الأدوار", "View roles",
       "الاطّلاع على الأدوار وصلاحياتها.",
       "See roles and their permissions."),
    _p(Perm.ROLE_MANAGE, "roles", "manage",
       "إدارة الأدوار", "Manage roles",
       "إنشاء الأدوار وتعديل صلاحياتها.",
       "Create roles and change their permissions.", danger=True),
    _p(Perm.PERMISSION_READ, "roles", "view",
       "عرض كتالوج الصلاحيات", "View permission catalogue",
       "الاطّلاع على قائمة الصلاحيات المتاحة.",
       "See the catalogue of available permissions."),
    _p(Perm.PERMISSION_ASSIGN, "roles", "assign",
       "إسناد الصلاحيات للأدوار", "Assign permissions to roles",
       "منح أو سحب صلاحيات دور معيّن.",
       "Grant or revoke a role's permissions.", danger=True),

    # ---- monthly reports ----
    _p(Perm.REPORT_READ_OWN, "reports", "read_own",
       "قراءة تقارير شركاتي", "Read own company reports",
       "قراءة التقارير الشهرية للشركات المصرّح بها.",
       "Read monthly reports for your permitted companies."),
    _p(Perm.REPORT_READ_ALL, "reports", "read_all",
       "قراءة تقارير كل الشركات", "Read all company reports",
       "قراءة التقارير الشهرية لكل الشركات التابعة.",
       "Read monthly reports across all subsidiaries."),
    _p(Perm.REPORT_CREATE, "reports", "create",
       "إنشاء تقرير شهري", "Create a monthly report",
       "إنشاء مسودة تقرير شهري.",
       "Create a monthly report draft."),
    _p(Perm.REPORT_UPDATE, "reports", "edit",
       "تعديل التقرير الشهري", "Edit a monthly report",
       "تعديل مسودة التقرير الشهري.",
       "Update a monthly report draft."),
    _p(Perm.REPORT_SUBMIT, "reports", "approve",
       "إرسال التقرير للقابضة", "Submit a report to the Holding",
       "إرسال التقرير الشهري إلى القابضة.",
       "Submit a monthly report to the Holding."),
    _p(Perm.REPORT_DELETE, "reports", "delete",
       "حذف مسودة التقرير", "Delete a report draft",
       "حذف مسودة تقرير شهري.",
       "Delete a monthly report draft.", danger=True),

    # ---- financial reviews ----
    _p(Perm.FINANCIAL_REVIEW_READ, "financial", "view",
       "عرض المراجعات المالية", "View financial reviews",
       "الاطّلاع على المراجعات المالية للتقارير.",
       "Read financial reviews."),
    _p(Perm.FINANCIAL_REVIEW_WRITE, "financial", "edit",
       "مراجعة البيانات المالية", "Review financial data",
       "توثيق صحة البيانات المالية أو التحفظ عليها.",
       "Verify financial data or raise a reservation.", danger=True),
    _p(Perm.FINANCIAL_SUMMARY_READ_OWN, "financial", "read_own",
       "قراءة ملخصات شركاتي المالية", "Read own financial summaries",
       "قراءة الملخصات المالية الشهرية للشركات المصرّح بها.",
       "Read monthly financial summaries for your permitted companies."),
    _p(Perm.FINANCIAL_SUMMARY_READ_ALL, "financial", "read_all",
       "قراءة كل الملخصات المالية", "Read all financial summaries",
       "قراءة الملخصات المالية الشهرية لكل الشركات التابعة.",
       "Read monthly financial summaries across all subsidiaries."),
    _p(Perm.FINANCIAL_SUMMARY_CREATE, "financial", "create",
       "إنشاء ملخص مالي شهري", "Create a financial summary",
       "إنشاء مسودة الملخص المالي الشهري (F-03).",
       "Create a monthly financial summary draft (F-03)."),
    _p(Perm.FINANCIAL_SUMMARY_UPDATE, "financial", "edit",
       "تعديل الملخص المالي", "Edit a financial summary",
       "تعديل مسودة الملخص المالي أو النسخة المعادة للتصحيح.",
       "Edit a financial summary draft or a version returned for correction."),
    _p(Perm.FINANCIAL_SUMMARY_SUBMIT, "financial", "approve",
       "إرسال الملخص للمراجعة", "Submit a financial summary",
       "إرسال الملخص المالي إلى المحاسب مع كشف البنك الإلزامي.",
       "Submit a financial summary to the accountant with the mandatory bank statement."),
    _p(Perm.FINANCIAL_SUMMARY_CORRECT, "financial", "create",
       "إنشاء نسخة تصحيحية", "Create a corrective version",
       "إنشاء نسخة تصحيح مرتبطة بالملخص المعتمد دون تعديل الأصل.",
       "Create a corrective version linked to an approved summary without altering the original.", danger=True),
    _p(Perm.FINANCIAL_ITEM_MANAGE, "financial", "manage",
       "إدارة بنود الحركات الخاصة", "Manage special financial items",
       "تعريف بنود الحركات الخاصة وقواعد تصنيفها وشمولها.",
       "Define special financial items and their classification/inclusion rules."),
    _p(Perm.FINANCIAL_REVIEW_ACT, "financial", "approve",
       "اعتماد أو إرجاع الملخص المالي", "Approve or return a financial summary",
       "اعتماد الملخص المالي أو إرجاعه للتصحيح بملاحظة إلزامية.",
       "Approve a financial summary or return it for correction with a mandatory note.", danger=True),
    _p(Perm.FINANCIAL_BANK_READ, "financial", "view",
       "عرض كشف البنك", "View the bank statement",
       "الاطّلاع على كشف البنك الخاص بالملخص المالي.",
       "View the private bank statement attached to a financial summary."),

    # ---- support requests ----
    _p(Perm.SUPPORT_READ_OWN, "support", "read_own",
       "قراءة طلبات شركاتي", "Read own support requests",
       "قراءة طلبات الدعم الخاصة بالشركات المصرّح بها.",
       "Read support requests for your permitted companies."),
    _p(Perm.SUPPORT_READ_ALL, "support", "read_all",
       "قراءة كل طلبات الدعم", "Read all support requests",
       "قراءة طلبات الدعم لكل الشركات.",
       "Read support requests across all companies."),
    _p(Perm.SUPPORT_CREATE, "support", "create",
       "رفع طلب دعم", "Raise a support request",
       "إنشاء طلب دعم جديد للقابضة.",
       "Raise a new support request to the Holding."),
    _p(Perm.SUPPORT_COMMENT, "support", "edit",
       "التعليق على الطلبات", "Comment on requests",
       "إضافة تعليقات على طلب دعم.",
       "Comment on a support request."),
    _p(Perm.SUPPORT_ASSIGN, "support", "assign",
       "إسناد طلبات الدعم", "Assign support requests",
       "إسناد طلب دعم إلى مسؤول.",
       "Assign a support request to a responsible person."),
    _p(Perm.SUPPORT_STATUS_CHANGE, "support", "edit",
       "تغيير حالة الطلب", "Change request status",
       "نقل طلب الدعم بين حالاته.",
       "Move a support request through its statuses."),

    # ---- forms ----
    _p(Perm.FORM_READ, "forms", "view",
       "عرض النماذج", "View forms",
       "الاطّلاع على النماذج المتاحة لك.",
       "View form definitions available to you."),
    _p(Perm.FORM_CREATE, "forms", "create",
       "إنشاء نموذج", "Create a form",
       "إنشاء نموذج ديناميكي جديد.",
       "Create a dynamic form definition."),
    _p(Perm.FORM_UPDATE, "forms", "edit",
       "تعديل النموذج", "Edit a form",
       "تعديل مسودة نموذج وحقوله.",
       "Edit a draft form definition and its fields."),
    _p(Perm.FORM_PUBLISH, "forms", "publish",
       "نشر النموذج", "Publish a form",
       "نشر النموذج ليصبح قابلًا للتعبئة.",
       "Publish a form so it can be submitted.", danger=True),
    _p(Perm.FORM_ARCHIVE, "forms", "manage",
       "أرشفة النموذج", "Archive a form",
       "أرشفة نموذج وإيقاف استخدامه.",
       "Archive a form definition.", danger=True),
    _p(Perm.FORM_SUBMIT, "forms", "create",
       "تعبئة النموذج", "Submit a form",
       "تعبئة وإرسال نموذج منشور.",
       "Fill in and submit a published form."),
    _p(Perm.REQUIREMENT_READ, "forms", "view",
       "عرض متطلبات النموذج", "View form requirements",
       "الاطّلاع على متطلبات النموذج.",
       "View a form's requirements."),
    _p(Perm.REQUIREMENT_MANAGE, "forms", "manage",
       "إدارة متطلبات النموذج", "Manage form requirements",
       "إضافة متطلبات مسودة النموذج وتعديلها وترتيبها.",
       "Add, edit and reorder a draft form's requirements."),
    _p(Perm.SUBMISSION_READ_OWN, "forms", "read_own",
       "قراءة طلباتي", "Read own submissions",
       "قراءة الطلبات التي أنشأتها.",
       "Read the submissions you created."),
    _p(Perm.SUBMISSION_READ_COMPANY, "forms", "read_all",
       "قراءة طلبات الشركة", "Read company submissions",
       "قراءة الطلبات المرفوعة داخل شركاتك.",
       "Read submissions raised within your companies."),
    _p(Perm.SUBMISSION_READ_ALL, "forms", "read_all",
       "قراءة كل الطلبات", "Read all submissions",
       "قراءة الطلبات في كل الشركات.",
       "Read submissions across all companies."),
    _p(Perm.SUBMISSION_CANCEL, "forms", "delete",
       "إلغاء الطلب", "Cancel a submission",
       "إلغاء طلب تملكه.",
       "Cancel a submission you own."),

    # ---- workflows ----
    _p(Perm.WORKFLOW_READ, "workflows", "view",
       "عرض سير العمل", "View workflows",
       "الاطّلاع على تعريفات سير العمل.",
       "View workflow definitions."),
    _p(Perm.WORKFLOW_CREATE, "workflows", "create",
       "إنشاء سير عمل", "Create a workflow",
       "إنشاء تعريف سير عمل جديد.",
       "Create a workflow definition."),
    _p(Perm.WORKFLOW_UPDATE, "workflows", "edit",
       "تعديل سير العمل", "Edit a workflow",
       "تعديل مسودة سير العمل وخطواته.",
       "Edit a draft workflow and its steps."),
    _p(Perm.WORKFLOW_PUBLISH, "workflows", "publish",
       "نشر سير العمل", "Publish a workflow",
       "نشر سير العمل ليُستخدم في الطلبات الجديدة.",
       "Publish a workflow so new requests use it.", danger=True),
    _p(Perm.WORKFLOW_ARCHIVE, "workflows", "manage",
       "أرشفة سير العمل", "Archive a workflow",
       "أرشفة تعريف سير عمل.",
       "Archive a workflow definition.", danger=True),

    # ---- approvals ----
    _p(Perm.APPROVAL_ACT, "approvals", "approve",
       "اعتماد الطلبات", "Approve requests",
       "اعتماد أو رفض أو إعادة طلب مُسند إليك.",
       "Approve, reject or return a request assigned to you."),
    _p(Perm.APPROVAL_READ_OWN, "approvals", "read_own",
       "عرض موافقاتي", "See your approval inbox",
       "الاطّلاع على الطلبات التي تنتظر موافقتك.",
       "See requests awaiting your approval."),
    _p(Perm.APPROVAL_READ_ALL, "approvals", "read_all",
       "عرض كل الموافقات", "See all approvals",
       "الاطّلاع على الموافقات في نطاق شركاتك.",
       "See approvals across your company scope."),
    _p(Perm.APPROVAL_OVERRIDE, "approvals", "manage",
       "تجاوز المتطلبات الإلزامية", "Override mandatory requirements",
       "تجاوز متطلب إلزامي مع تسجيل سبب موثّق.",
       "Override a mandatory requirement with a recorded reason.", danger=True),

    # ---- documents ----
    _p(Perm.DOCUMENT_READ, "documents", "view",
       "عرض المستندات", "View documents",
       "الاطّلاع على المستندات وتنزيلها في نطاقك.",
       "View and download documents in your scope."),
    _p(Perm.DOCUMENT_UPLOAD, "documents", "create",
       "رفع مستند", "Upload documents",
       "رفع مستندات جديدة.",
       "Upload new documents."),
    _p(Perm.DOCUMENT_UPDATE, "documents", "edit",
       "تعديل بيانات المستند", "Edit document metadata",
       "تعديل بيانات المستند الوصفية.",
       "Edit document metadata."),
    _p(Perm.DOCUMENT_ARCHIVE, "documents", "manage",
       "أرشفة المستندات", "Archive documents",
       "أرشفة المستندات.",
       "Archive documents.", danger=True),
    _p(Perm.DOCUMENT_CATEGORY_MANAGE, "documents", "manage",
       "إدارة تصنيفات المستندات", "Manage document categories",
       "إنشاء تصنيفات المستندات وتعديلها.",
       "Manage document categories."),

    # ---- website leads ----
    _p(Perm.LEAD_READ, "leads", "view",
       "عرض طلبات الموقع", "View website leads",
       "الاطّلاع على الطلبات الواردة من الموقع والفرص المقدَّمة.",
       "View website leads and submitted opportunities."),
    _p(Perm.LEAD_MANAGE, "leads", "manage",
       "إدارة طلبات الموقع", "Manage website leads",
       "إسناد الطلبات وإعادة توجيهها وتعديل بياناتها.",
       "Assign, re-route and edit website leads."),
    _p(Perm.LEAD_STATUS_CHANGE, "leads", "edit",
       "تغيير حالة الطلب", "Change lead status",
       "نقل طلب الموقع بين مراحل المتابعة.",
       "Move a website lead through its pipeline."),
    _p(Perm.LEAD_MANAGER_NOTE, "leads", "edit",
       "كتابة ملاحظة المدير", "Write the manager note",
       "كتابة ملاحظة مدير مستقلة عن ملاحظات التسويق؛ التسويق يقرأها دون تعديل.",
       "Write an independent manager note; marketing reads it without editing."),

    # ---- opportunities ----
    _p(Perm.OPPORTUNITY_REVIEW, "opportunities", "approve",
       "مراجعة الفرص المقدَّمة", "Review submitted listings",
       "مراجعة العروض والفرص المقدَّمة من الشركات.",
       "Review submitted business listings."),
    _p(Perm.OPPORTUNITY_PUBLISH, "opportunities", "publish",
       "نشر الفرص على الموقع", "Publish a listing publicly",
       "نشر عرض أو فرصة على الموقع العام.",
       "Publish a business listing on the public website.", danger=True),

    # ---- notifications ----
    _p(Perm.NOTIFICATION_READ_OWN, "notifications", "read_own",
       "قراءة إشعاراتي", "Read your notifications",
       "الاطّلاع على إشعاراتك الخاصة.",
       "Read your own notifications."),
    _p(Perm.NOTIFICATION_MANAGE, "notifications", "manage",
       "إدارة الإشعارات", "Manage notifications",
       "فحص الإشعارات وإرسالها في نطاقك.",
       "Inspect and trigger notifications in scope."),

    # ---- analytics ----
    _p(Perm.ANALYTICS_HOLDING, "analytics", "read_all",
       "تحليلات المجموعة", "Group-wide analytics",
       "عرض تقارير وتحليلات المجموعة كاملة.",
       "View group-wide reporting and analytics."),
    _p(Perm.ANALYTICS_COMPANY, "analytics", "read_own",
       "تحليلات الشركة", "Company analytics",
       "عرض تقارير وتحليلات شركاتك.",
       "View reporting and analytics for your companies."),
    _p(Perm.ANALYTICS_OPERATIONS, "analytics", "view",
       "التحليلات التشغيلية", "Operational analytics",
       "عرض التحليلات التشغيلية (الطلبات والموافقات).",
       "View operational reporting (requests, approvals)."),
    _p(Perm.ANALYTICS_COMPLIANCE, "analytics", "view",
       "تحليلات الالتزام", "Compliance analytics",
       "عرض تقارير الالتزام (المستندات والانتهاء).",
       "View compliance reporting (documents, expiry)."),
    _p(Perm.ANALYTICS_EXPORT, "analytics", "manage",
       "تصدير التقارير", "Export reports",
       "تصدير التقارير بصيغة CSV.",
       "Export reports as CSV."),

    # ---- ai ----
    _p(Perm.AI_HOLDING, "ai", "view",
       "استخدام ذكاء القابضة", "Use Holding AI",
       "استخدام مساعد القابضة للذكاء الاصطناعي.",
       "Use the Holding AI assistant."),
    _p(Perm.AI_COMPANY, "ai", "view",
       "استخدام ذكاء الشركة", "Use Company AI",
       "استخدام مساعد الذكاء الاصطناعي للشركة.",
       "Use the Company AI assistant."),

    # ---- integrations ----
    _p(Perm.INTEGRATION_READ, "integrations", "view",
       "عرض التكاملات", "View integrations",
       "الاطّلاع على التكاملات المُهيّأة.",
       "View configured integrations."),
    _p(Perm.INTEGRATION_MANAGE, "integrations", "manage",
       "إدارة التكاملات", "Manage integrations",
       "إنشاء التكاملات وتعديلها وتعطيلها.",
       "Create, edit and disable integrations.", danger=True),

    # ---- website management (Phase 11 CMS) ----
    _p(Perm.WEBSITE_MANAGE, "website", "manage",
       "الدخول إلى إدارة الموقع", "Access Website Management",
       "فتح وحدة إدارة الموقع العام.",
       "Open the public Website Management module."),
    _p(Perm.WEBSITE_CONTENT_READ, "website", "view",
       "عرض محتوى الموقع", "View website content",
       "الاطّلاع على الصفحات والأقسام والشرائح وبطاقات الشركات.",
       "View pages, sections, slides and company cards."),
    _p(Perm.WEBSITE_CONTENT_WRITE, "website", "edit",
       "تعديل محتوى الموقع", "Edit website content",
       "إنشاء محتوى الموقع وتعديله (مسودات).",
       "Create and edit website content (drafts)."),
    _p(Perm.WEBSITE_CONTENT_PUBLISH, "website", "publish",
       "نشر محتوى الموقع", "Publish website content",
       "نشر المحتوى على الموقع العام أو إلغاء نشره.",
       "Publish content to the public site or unpublish it.", danger=True),
    _p(Perm.WEBSITE_MEDIA_MANAGE, "website", "manage",
       "إدارة وسائط الموقع", "Manage website media",
       "رفع الصور والملفات واستبدالها وحذفها من مكتبة الوسائط.",
       "Upload, replace and delete images and files in the media library."),
    _p(Perm.WEBSITE_SETTINGS_MANAGE, "website", "manage",
       "إعدادات الموقع", "Website settings",
       "تغيير إعدادات الموقع العامة وقيم SEO الافتراضية ووضع الصيانة.",
       "Change site-wide settings, SEO defaults and maintenance mode.", danger=True),

    # ---- audit / administration ----
    _p(Perm.AUDIT_READ, "audit", "view",
       "عرض سجل النشاط", "View the audit log",
       "الاطّلاع على سجل النشاط والتدقيق.",
       "Read the audit log."),

    # ---- Executions 04-14: balances ----
    _p(Perm.OPENING_BALANCE_READ, "balances", "view",
       "عرض الأرصدة الافتتاحية", "View opening balances",
       "عرض الأرصدة الافتتاحية والأرصدة المرحّلة.", "View opening and carry-forward balances."),
    _p(Perm.OPENING_BALANCE_MANAGE, "balances", "edit",
       "إدخال الأرصدة الافتتاحية", "Enter opening balances",
       "إدخال وتعديل الأرصدة الافتتاحية والمرحّلة.", "Create and edit opening and carry-forward balances."),
    _p(Perm.OPENING_BALANCE_APPROVE, "balances", "approve",
       "اعتماد الرصيد الافتتاحي", "Approve opening balance",
       "اعتماد الرصيد الافتتاحي ليصبح نافذًا.", "Approve an opening balance so it becomes effective.", danger=True),

    # ---- Executions 04-14: employees ----
    _p(Perm.EMPLOYEE_READ, "employees", "view",
       "عرض الموظفين", "View employees",
       "عرض الموظفين داخل الشركات المصرّح بها.", "View employees in your companies."),
    _p(Perm.EMPLOYEE_MANAGE, "employees", "edit",
       "إدارة الموظفين", "Manage employees",
       "إضافة وتعديل سجلات الموظفين.", "Create and edit employee records."),
    _p(Perm.EMPLOYEE_SALARY_READ, "employees", "view",
       "عرض الرواتب", "View salaries",
       "عرض راتب الموظف وبدلاته (حساس).", "View employee salary and allowances (sensitive).", danger=True),
    _p(Perm.EMPLOYEE_MOVEMENT_READ, "employees", "view",
       "عرض حركات الموظفين", "View employee movements",
       "عرض الإجازات والسلف.", "View leave and advance movements."),
    _p(Perm.EMPLOYEE_MOVEMENT_MANAGE, "employees", "edit",
       "إدخال حركات الموظفين", "Record employee movements",
       "إدخال الإجازات والسلف يدويًا.", "Record leave and advance movements."),
    _p(Perm.EMPLOYEE_MOVEMENT_APPROVE, "employees", "approve",
       "اعتماد حركات الموظفين", "Approve employee movements",
       "اعتماد أو رفض الإجازات والسلف.", "Approve or reject leave and advance movements.", danger=True),
    _p(Perm.ASSESSMENT_READ, "employees", "view",
       "عرض التقييمات", "View assessments",
       "عرض تقييمات الموظفين.", "View employee assessments."),
    _p(Perm.ASSESSMENT_MANAGE, "employees", "edit",
       "إدارة التقييمات", "Manage assessments",
       "إنشاء وتعديل تقييمات الموظفين مع الأدلة.", "Create and edit assessments with evidence."),
    _p(Perm.ASSESSMENT_APPROVE, "employees", "approve",
       "اعتماد التقييمات", "Approve assessments",
       "اعتماد التقييم بعد اكتمال الأدلة الإلزامية.", "Approve an assessment once mandatory evidence is complete.", danger=True),

    # ---- Executions 04-14: tasks & weekly reports ----
    _p(Perm.TASK_READ_OWN, "tasks", "read_own",
       "عرض مهامي", "View my tasks",
       "عرض المهام المسندة إليك.", "View tasks assigned to you."),
    _p(Perm.TASK_READ_ALL, "tasks", "read_all",
       "عرض كل المهام", "View all tasks",
       "عرض المهام ضمن نطاق شركاتك.", "View tasks across your company scope."),
    _p(Perm.TASK_CREATE, "tasks", "create",
       "إنشاء المهام", "Create tasks",
       "إنشاء المهام وإسنادها.", "Create and assign tasks."),
    _p(Perm.TASK_UPDATE, "tasks", "edit",
       "تعديل المهام", "Edit tasks",
       "تعديل تفاصيل المهمة.", "Edit task details."),
    _p(Perm.TASK_STATUS_CHANGE, "tasks", "manage",
       "تغيير حالة المهمة", "Change task status",
       "تحريك المهمة في دورة حياتها.", "Move a task through its lifecycle.", danger=True),
    _p(Perm.WEEKLY_REPORT_READ_OWN, "tasks", "read_own",
       "عرض تقاريري الأسبوعية", "View my weekly reports",
       "عرض تقاريرك الأسبوعية.", "View your own weekly reports."),
    _p(Perm.WEEKLY_REPORT_READ_ALL, "tasks", "read_all",
       "عرض التقارير الأسبوعية", "View weekly reports",
       "عرض التقارير الأسبوعية ضمن نطاقك.", "View weekly reports across your scope."),
    _p(Perm.WEEKLY_REPORT_SUBMIT, "tasks", "create",
       "رفع التقرير الأسبوعي", "Submit weekly report",
       "رفع التقرير الأسبوعي.", "Submit a weekly report."),
    _p(Perm.WEEKLY_REPORT_TEMPLATE_MANAGE, "tasks", "manage",
       "إدارة أسئلة التقرير", "Manage weekly questions",
       "تخصيص أسئلة التقرير الأسبوعي.", "Configure the weekly report questions."),

    # ---- Executions 04-14: campaigns ----
    _p(Perm.CAMPAIGN_READ, "campaigns", "view",
       "عرض الحملات", "View campaigns",
       "عرض الحملات التسويقية.", "View marketing campaigns."),
    _p(Perm.CAMPAIGN_MANAGE, "campaigns", "manage",
       "إدارة الحملات", "Manage campaigns",
       "إنشاء وتعديل الحملات ونتائجها.", "Create and edit campaigns and their results."),

    # ---- Executions 04-14: complaints (confidential) ----
    _p(Perm.COMPLAINT_CREATE, "complaints", "create",
       "تقديم شكوى سرية", "Submit a complaint",
       "تقديم شكوى سرية للمالك.", "Submit a confidential complaint to the owner."),
    _p(Perm.COMPLAINT_READ_OWN, "complaints", "read_own",
       "عرض شكاواي", "View my complaints",
       "عرض الشكاوى التي قدمتها.", "View complaints you submitted."),
    _p(Perm.COMPLAINT_DECIDE, "complaints", "approve",
       "البتّ في الشكاوى", "Decide on complaints",
       "قرار المالك بشأن الشكوى السرية.", "Decide on a confidential complaint (owner only).", danger=True),

    # ---- Executions 04-14: design requests ----
    _p(Perm.DESIGN_REQUEST_MANAGE, "support", "manage",
       "إدارة طلبات التصميم", "Manage design requests",
       "إدارة حقول ودورة طلب التصميم.", "Manage design request fields and lifecycle."),
    _p(Perm.DESIGN_REQUEST_DELIVER, "support", "edit",
       "تسليم طلب التصميم", "Deliver design request",
       "إرفاق رابط التسليم وإكمال الطلب.", "Attach a delivery link and complete a design request."),

    # ---- Executions 04-14: advisors ----
    _p(Perm.ADVISOR_READ, "advisors", "view",
       "عرض المستشارين", "View advisors",
       "عرض إسنادات المستشارين والجلسات.", "View advisor assignments and sessions."),
    _p(Perm.ADVISOR_MANAGE, "advisors", "manage",
       "إدارة المستشارين", "Manage advisors",
       "إسناد المستشارين وإدارة الجلسات.", "Assign advisors and manage sessions."),
    _p(Perm.ADVISOR_SESSION_READ_OWN, "advisors", "read_own",
       "عرض جلساتي", "View my sessions",
       "عرض الجلسات الخاصة بك.", "View your own advisor sessions."),
    _p(Perm.ADVISOR_SESSION_RECORD, "advisors", "edit",
       "تسجيل الجلسة", "Record a session",
       "تسجيل الجلسة والتوصيات.", "Record a session and its recommendations."),

    # ---- Executions 04-14: owner decisions ----
    _p(Perm.OWNER_DECISION_READ, "decisions", "view",
       "عرض قرارات المالك", "View owner decisions",
       "عرض القرارات والتوجيهات.", "View owner decisions and directives."),
    _p(Perm.OWNER_DECISION_MANAGE, "decisions", "manage",
       "إدارة قرارات المالك", "Manage owner decisions",
       "إنشاء وتحديث القرارات والتوجيهات.", "Create and update owner decisions and directives."),

    # ---- S20: projects & opportunities ----
    _p(Perm.PROJECT_READ, "projects", "view",
       "عرض المشاريع والفرص", "View projects and opportunities",
       "عرض سجل المشاريع والفرص.", "View the opportunities and projects register."),
    _p(Perm.PROJECT_MANAGE, "projects", "manage",
       "إدارة المشاريع والفرص", "Manage projects and opportunities",
       "إنشاء وتحديث الفرص والمشاريع.", "Create and update opportunities and projects."),

    # ---- Executions 04-14: holding accounting ----
    _p(Perm.ACCOUNT_READ, "accounting", "view",
       "عرض دليل الحسابات", "View chart of accounts",
       "عرض دليل الحسابات.", "View the chart of accounts."),
    _p(Perm.ACCOUNT_MANAGE, "accounting", "manage",
       "إدارة دليل الحسابات", "Manage chart of accounts",
       "إدارة دليل الحسابات.", "Manage the chart of accounts."),
    _p(Perm.JOURNAL_READ, "accounting", "view",
       "عرض القيود", "View journals",
       "عرض القيود اليومية.", "View journal entries."),
    _p(Perm.JOURNAL_CREATE, "accounting", "create",
       "إنشاء قيد", "Create journal",
       "إنشاء مسودة قيد.", "Create a journal entry draft."),
    _p(Perm.JOURNAL_POST, "accounting", "approve",
       "ترحيل القيد", "Post journal",
       "ترحيل القيد (لا يُعدّل بعد الترحيل).", "Post a journal entry (never edited in place afterwards).", danger=True),
    _p(Perm.JOURNAL_REVERSE, "accounting", "approve",
       "عكس القيد", "Reverse journal",
       "عكس قيد مُرحّل بقيد عكسي.", "Reverse a posted entry via a reversal.", danger=True),
    _p(Perm.INVOICE_READ, "accounting", "view",
       "عرض الفواتير", "View invoices",
       "عرض الفواتير والمدفوعات.", "View invoices and receivables."),
    _p(Perm.INVOICE_MANAGE, "accounting", "manage",
       "إدارة الفواتير", "Manage invoices",
       "إنشاء وتعديل الفواتير.", "Create and edit invoices."),
    _p(Perm.SETTLEMENT_MANAGE, "accounting", "manage",
       "إدارة التسويات", "Manage settlements",
       "تسجيل تسويات الفواتير.", "Record invoice settlements."),
    _p(Perm.ASSET_READ, "accounting", "view",
       "عرض الأصول", "View assets",
       "عرض الأصول.", "View assets."),
    _p(Perm.ASSET_MANAGE, "accounting", "manage",
       "إدارة الأصول", "Manage assets",
       "إدارة الأصول.", "Manage assets."),
    _p(Perm.BUDGET_READ, "accounting", "view",
       "عرض الموازنات", "View budgets",
       "عرض الموازنات المعتمدة.", "View budgets."),
    _p(Perm.BUDGET_MANAGE, "accounting", "manage",
       "إدارة الموازنات", "Manage budgets",
       "إعداد الموازنات مع المصدر والإصدار.", "Create budgets with source and version."),
    _p(Perm.BUDGET_APPROVE, "accounting", "approve",
       "اعتماد الموازنة", "Approve budget",
       "اعتماد الموازنة من المالك أو المفوض.", "Approve a budget (owner or delegate).", danger=True),

    # ---- Executions 04-14: KPIs ----
    _p(Perm.KPI_READ, "kpi", "view",
       "عرض المؤشرات", "View KPIs",
       "عرض مؤشرات الأداء ونتائجها.", "View KPI definitions and results."),
    _p(Perm.KPI_MANAGE, "kpi", "manage",
       "إدارة المؤشرات", "Manage KPIs",
       "تعريف المؤشرات ومصدرها وطريقة حسابها.", "Define KPIs with source and calculation."),

    # ---- Executions 04-14: confidential access & notifications ----
    _p(Perm.CONFIDENTIAL_ACCESS_MANAGE, "confidential", "manage",
       "تفويض الوصول السري", "Delegate confidential access",
       "تفويض الوصول إلى سجل سري محدد بمدة انتهاء وسجل تدقيق.",
       "Delegate access to a specific confidential record with an expiry and audit trail.", danger=True),
    _p(Perm.NOTIFICATION_PREFERENCE_MANAGE, "notifications", "manage",
       "إدارة تفضيلات الإشعارات", "Manage notification preferences",
       "ضبط قنوات الإشعارات لكل نوع حدث.", "Configure notification channels per event type."),
]

_METADATA_BY_CODE = {m["code"]: m for m in PERMISSION_METADATA}


def _infer_action(code: str) -> str:
    """Best-effort action kind for a code that has no explicit metadata."""
    if code.endswith(".read_own"):
        return "read_own"
    if code.endswith(".read_all") or code.endswith(".read"):
        return "view"
    if code.endswith(".manage"):
        return "manage"
    if code.endswith(".create"):
        return "create"
    if code.endswith(".update") or code.endswith(".write"):
        return "edit"
    if code.endswith(".delete") or code.endswith(".archive") or code.endswith(".cancel"):
        return "delete"
    if code.endswith(".assign"):
        return "assign"
    if code.endswith(".publish"):
        return "publish"
    if code.endswith(".act") or code.endswith(".review") or code.endswith(".submit"):
        return "approve"
    return "manage"


def describe(code: str) -> dict:
    """Return the full presentation record for ``code``.

    Falls back to the code itself plus the generic description from
    ``ALL_PERMISSIONS`` when no curated metadata exists, so a newly added
    permission is never hidden from the UI.
    """
    meta = _METADATA_BY_CODE.get(code)
    if meta is None:
        generic = ALL_PERMISSIONS.get(code, "")
        return {
            "code": code,
            "category": "audit",
            "action": _infer_action(code),
            "name_ar": code,
            "name_en": code,
            "description_ar": generic,
            "description_en": generic,
            "danger": False,
        }
    return dict(meta)


def catalogue() -> list[dict]:
    """Every known permission, described and ordered for display."""
    return [describe(code) for code in ALL_PERMISSIONS]


def unknown_codes() -> list[str]:
    """Codes present in ``ALL_PERMISSIONS`` but missing curated metadata."""
    return sorted(set(ALL_PERMISSIONS) - set(_METADATA_BY_CODE))


def category_order() -> dict[str, int]:
    return {c["key"]: c["order"] for c in CATEGORIES}


def action_order() -> dict[str, int]:
    return {a["key"]: a["order"] for a in ACTIONS}
