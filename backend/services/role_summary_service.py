"""Per-role dashboard summary (S01 / deck slides 7-11).

Spec §7 S01: "لكل دور ملخص من سجلاته فقط" -- each role's dashboard is a summary
drawn **only** from the records it may read. The deck gives each of the five
primary roles its own four KPI tiles:

* slide 7  owner            -- profit trend, operating cash, liquidity risk, pending decisions
* slide 8  business dev.    -- awaiting assignment, tasks in progress, active opportunities, reports to follow up
* slide 9  company manager  -- month result, cash balance, prospective clients, support requests
* slide 10 specialist       -- my open tasks, overdue, awaiting information, completed this month
* slide 11 sales            -- new leads, awaiting contact, qualified leads, follow up this week

This module computes those tiles from the database. It is **presentation only**:
no business rule, permission or scope check changes. Every figure is restricted
with the same ``accessible_company_ids`` scope the underlying view uses, and a
source is included only when the caller holds its read permission -- so a tile
can never report a figure the caller could not otherwise open.

When a role has no dedicated summary (or none of its sources are permitted) the
function returns ``None`` and the dashboard falls back to the holding strip.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.db.models.enums import (
    FinancialReviewStatus,
    LeadStatus,
    OwnerDecisionStatus,
    ProjectRecordType,
    ReportStatus,
    SupportStatus,
    TaskLifecycleStatus,
)
from backend.db.models.financial import FinancialPeriod, FinancialSummaryVersion
from backend.db.models.identity import User
from backend.db.models.operations import OwnerDecision, ProjectRecord, Task
from backend.db.models.report import MonthlyReport, MonthlyReportFinancialReview
from backend.db.models.support import SupportRequest
from backend.db.models.website import WebsiteLead
from backend.rbac.authorization import accessible_company_ids, has_permission
from backend.rbac.permissions import Perm

MILLION = Decimal(1000000)

# Roles that share a deck dashboard. The deck names five; a couple of adjacent
# roles in the same family reuse the closest one rather than getting a tile set
# the deck never drew.
OWNER_ROLES = {"holding_owner", "super_admin"}
MANAGER_ROLES = {"company_manager", "company_owner"}
SPECIALIST_ROLES = {"designer"}
SALES_ROLES = {"marketing"}

# Deck slides 7-11 each carry a role title and the greeting line
# "مرحبًا <role> | يعرض النظام البيانات المسموح بها لدورك" above the tiles. The
# title is the deck's own wording (slide 9's "شركة نموذجية" is the sample
# company name, so the generic "لوحة الشركة" is used for a real tenant).
ROLE_TITLES = {
    "holding_owner": ("لوحة القيادة للمجموعة", "Holding Dashboard"),
    "super_admin": ("لوحة القيادة للمجموعة", "Holding Dashboard"),
    "business_development": ("لوحة تطوير الأعمال", "Business Development Dashboard"),
    "company_manager": ("لوحة الشركة", "Company Dashboard"),
    "company_owner": ("لوحة الشركة", "Company Dashboard"),
    "designer": ("مساحة عملي", "My Workspace"),
    "marketing": ("العملاء والفرص", "Leads and Opportunities"),
}

ROLE_NAMES = {
    "holding_owner": ("المالك", "Owner"),
    "super_admin": ("المالك", "Owner"),
    "business_development": ("مدير تطوير الأعمال", "Business Development Manager"),
    "company_manager": ("مدير الشركة", "Company Manager"),
    "company_owner": ("مدير الشركة", "Company Manager"),
    "designer": ("موظف مختص", "Specialist"),
    "marketing": ("موظف المبيعات", "Sales"),
}

# Deck slides 7-11 name the follow-up list under the role's tiles after the role
# itself: the owner sees [قرارات بانتظار الاعتماد], BD [طلبات ومهام القابضة], the
# company manager [متابعة شركتك], the specialist [مهامي المسندة إليّ] and sales
# [العملاء المحتملون / مصفوفة العملاء]. The dashboard paints this exact heading
# above the shared attention list so the deck's own section name is present.
ROLE_SECTIONS = {
    "holding_owner": ("قرارات بانتظار الاعتماد", "Decisions awaiting approval"),
    "super_admin": ("قرارات بانتظار الاعتماد", "Decisions awaiting approval"),
    "business_development": ("طلبات ومهام القابضة", "Holding requests and tasks"),
    "company_manager": ("متابعة شركتك", "Follow up your company"),
    "company_owner": ("متابعة شركتك", "Follow up your company"),
    "designer": ("مهامي المسندة إليّ", "Tasks assigned to me"),
    "marketing": ("العملاء المحتملون / مصفوفة العملاء",
                  "Leads / lead matrix"),
}


# Deck slides 7-11 each draw a shortcut strip under the tiles -- "اختصارات
# الشركة" (manager), "أدواتي" (specialist), "أولويات الأسبوع" (BD) and the
# unlabelled owner/sales grids. Every card is a jump into a section the role can
# already open, so the strip adds navigation, never access: the target view is
# still gated by ``canView`` in the client and by the permission on its routes.
ROLE_SHORTCUTS: dict[str, list[tuple[str, str, str]]] = {
    "holding_owner": [
        ("مؤشرات المجموعة", "Group indicators", "dashboard"),
        ("الشركات التابعة", "Subsidiaries", "subsidiaries"),
        ("حالة المديرين", "Manager status", "employees"),
        ("الفرص ورأس المال", "Opportunities & capital", "investments"),
    ],
    "super_admin": [
        ("مؤشرات المجموعة", "Group indicators", "dashboard"),
        ("الشركات التابعة", "Subsidiaries", "subsidiaries"),
        ("حالة المديرين", "Manager status", "employees"),
        ("الفرص ورأس المال", "Opportunities & capital", "investments"),
    ],
    "business_development": [
        ("الشركات", "Companies", "subsidiaries"),
        ("الموظفون", "Employees", "employees"),
        ("الفرص", "Opportunities", "projects"),
        ("تقرير المالك", "Owner report", "reports"),
    ],
    "company_manager": [
        ("أداء الشركة", "Company performance", "dashboard"),
        ("التقرير الشهري", "Monthly report", "reports"),
        ("الموظفون", "Employees", "employees"),
        ("العملاء", "Leads", "leads"),
    ],
    "company_owner": [
        ("أداء الشركة", "Company performance", "dashboard"),
        ("التقرير الشهري", "Monthly report", "reports"),
        ("الموظفون", "Employees", "employees"),
        ("العملاء", "Leads", "leads"),
    ],
    "designer": [
        ("المهام الجديدة", "New tasks", "operations"),
        ("قيد التنفيذ", "In progress", "operations"),
        ("الأعمال المكتملة", "Completed work", "operations"),
        ("تقاريري", "My reports", "reports"),
    ],
    "marketing": [
        ("إضافة عميل", "Add lead", "leads"),
        ("مصفوفة العملاء", "Lead matrix", "leads"),
        ("الفرص", "Opportunities", "leads"),
        ("التقرير الأسبوعي", "Weekly report", "reports"),
    ],
}

# Where the deck's [عرض الكل] ("View all") sends each role: the "all" list of
# that role's follow-up section.
ROLE_VIEW_ALL: dict[str, str] = {
    "holding_owner": "decisions",
    "super_admin": "decisions",
    "business_development": "requests",
    "company_manager": "reports",
    "company_owner": "reports",
    "designer": "operations",
    "marketing": "leads",
}


def _greeting(role: str) -> tuple[str, str]:
    name_ar, name_en = ROLE_NAMES.get(role, ("المستخدم", "User"))
    return (
        f"مرحبًا {name_ar} | يعرض النظام البيانات المسموح بها لدورك",
        f"Welcome, {name_en} | The system shows the data permitted for your role",
    )


def _scoped(stmt, column, user: User):
    """Restrict a statement to the companies the caller may read."""
    allowed = accessible_company_ids(user)
    if allowed is None:
        return stmt
    if not allowed:
        return stmt.where(False)
    return stmt.where(column.in_(allowed))


def _millions(amount: Decimal | None) -> str:
    value = Decimal(amount or 0) / MILLION
    return f"{value:.1f}"


def _kpi(
    key: str,
    label_ar: str,
    label_en: str,
    value,
    *,
    unit: str | None = None,
    delta: str | None = None,
    delta_dir: str | None = None,
    tone: str = "navy",
) -> dict:
    return {
        "key": key,
        "label_ar": label_ar,
        "label_en": label_en,
        "value": str(value),
        "unit": unit,
        "delta": delta,
        "delta_dir": delta_dir,
        "tone": tone,
    }


# --------------------------------------------------------------------------
# source aggregates (each gated by the caller's own read permission)
# --------------------------------------------------------------------------
def _tasks(db: Session, user: User) -> list[Task]:
    """Tasks the caller may see: all in scope, or only their own."""
    if has_permission(user, Perm.TASK_READ_ALL):
        stmt = _scoped(select(Task), Task.company_id, user)
    elif has_permission(user, Perm.TASK_READ_OWN):
        stmt = select(Task).where(Task.assignee_id == user.id)
    else:
        return []
    return list(db.execute(stmt).scalars())


def _task_counts(tasks: list[Task], year: int, month: int) -> dict:
    closed = {TaskLifecycleStatus.COMPLETE.value, TaskLifecycleStatus.CANCELLED.value}
    today = date.today()
    open_tasks = [t for t in tasks if t.status not in closed]
    overdue = [
        t
        for t in open_tasks
        if t.due_date is not None and t.due_date < today
    ]
    awaiting = [
        t
        for t in tasks
        if t.status
        in (
            TaskLifecycleStatus.AWAITING_REVIEW.value,
            TaskLifecycleStatus.RETURNED.value,
        )
    ]
    completed = [
        t
        for t in tasks
        if t.status == TaskLifecycleStatus.COMPLETE.value
        and t.completed_at is not None
        and t.completed_at.year == year
        and t.completed_at.month == month
    ]
    return {
        "open": len(open_tasks),
        "overdue": len(overdue),
        "awaiting": len(awaiting),
        "completed": len(completed),
        "in_progress": sum(
            1 for t in tasks if t.status == TaskLifecycleStatus.IN_PROGRESS.value
        ),
    }


def _lead_counts(db: Session, user: User) -> dict | None:
    """Lead funnel counts, or ``None`` when the caller may not read leads."""
    if not has_permission(user, Perm.LEAD_READ):
        return None
    rows = db.execute(
        select(WebsiteLead.status, func.count(WebsiteLead.id)).group_by(
            WebsiteLead.status
        )
    ).all()
    by_status = {str(status): int(count) for status, count in rows}
    return {
        "total": sum(by_status.values()),
        "new": by_status.get(LeadStatus.NEW.value, 0),
        "assigned": by_status.get(LeadStatus.ASSIGNED.value, 0),
        "in_progress": by_status.get(LeadStatus.IN_PROGRESS.value, 0),
        "qualified": by_status.get(LeadStatus.QUALIFIED.value, 0),
    }


def _leads_created(db: Session, user: User, year: int, month: int) -> int:
    # A half-open month range, not ``strftime``: the SQLite date function does
    # not exist on PostgreSQL, where it raises UndefinedFunction.
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    end = datetime(year + (month // 12), (month % 12) + 1, 1, tzinfo=timezone.utc)
    stmt = select(func.count(WebsiteLead.id)).where(
        WebsiteLead.created_at >= start,
        WebsiteLead.created_at < end,
    )
    return int(db.execute(stmt).scalar_one())


def _reports_needing_follow_up(db: Session, user: User, year: int, month: int) -> int:
    stmt = (
        select(func.count(MonthlyReport.id))
        .where(
            MonthlyReport.period_year == year,
            MonthlyReport.period_month == month,
            MonthlyReport.status.in_(
                [ReportStatus.SUBMITTED.value, ReportStatus.UNDER_REVIEW.value]
            ),
        )
    )
    stmt = _scoped(stmt, MonthlyReport.company_id, user)
    return int(db.execute(stmt).scalar_one())


def _active_opportunities(db: Session, user: User) -> int:
    stmt = select(func.count(ProjectRecord.id)).where(
        ProjectRecord.record_type == ProjectRecordType.OPPORTUNITY.value,
        ProjectRecord.status == "open",
    )
    stmt = _scoped(stmt, ProjectRecord.company_id, user)
    return int(db.execute(stmt).scalar_one())


def _pending_decisions(db: Session, user: User) -> int:
    stmt = select(func.count(OwnerDecision.id)).where(
        OwnerDecision.status != OwnerDecisionStatus.DONE.value
    )
    stmt = _scoped(stmt, OwnerDecision.company_id, user)
    return int(db.execute(stmt).scalar_one())


def _support_open(db: Session, user: User) -> int:
    stmt = select(func.count(SupportRequest.id)).where(
        SupportRequest.status.in_(
            [SupportStatus.NEW.value, SupportStatus.IN_PROGRESS.value]
        )
    )
    stmt = _scoped(stmt, SupportRequest.company_id, user)
    return int(db.execute(stmt).scalar_one())


def _month_result(db: Session, user: User, year: int, month: int) -> Decimal:
    """Net result for the period, preferring the accountant's verified figure."""
    net_expr = func.coalesce(
        MonthlyReportFinancialReview.verified_net_result, MonthlyReport.net_result
    )
    stmt = (
        select(func.coalesce(func.sum(net_expr), 0))
        .select_from(MonthlyReport)
        .outerjoin(
            MonthlyReportFinancialReview,
            (MonthlyReportFinancialReview.report_id == MonthlyReport.id)
            & (
                MonthlyReportFinancialReview.status
                == FinancialReviewStatus.APPROVED.value
            ),
        )
        .where(
            MonthlyReport.period_year == year,
            MonthlyReport.period_month == month,
            MonthlyReport.status != ReportStatus.DRAFT.value,
        )
    )
    stmt = _scoped(stmt, MonthlyReport.company_id, user)
    return Decimal(db.execute(stmt).scalar_one() or 0)


def _effective_cash(db: Session, user: User, year: int, month: int) -> tuple[Decimal, int]:
    """(total cash, companies with negative cash) from the approved versions."""
    stmt = (
        select(FinancialSummaryVersion.calculated_total_cash)
        .select_from(FinancialPeriod)
        .join(
            FinancialSummaryVersion,
            FinancialSummaryVersion.id == FinancialPeriod.effective_version_id,
        )
        .where(
            FinancialPeriod.period_year == year,
            FinancialPeriod.period_month == month,
        )
    )
    stmt = _scoped(stmt, FinancialPeriod.company_id, user)
    values = [Decimal(v) for (v,) in db.execute(stmt).all() if v is not None]
    total = sum(values, Decimal(0))
    return total, sum(1 for v in values if v < 0)


# --------------------------------------------------------------------------
# per-role tile sets
# --------------------------------------------------------------------------
def _owner_summary(db, user, year, month) -> list[dict]:
    net = _month_result(db, user, year, month)
    cash, negative = _effective_cash(db, user, year, month)
    kpis = [
        _kpi("profit_trend", "اتجاه الأرباح", "Profit trend", _millions(net),
             unit="M SAR", tone="green" if net >= 0 else "red"),
        _kpi("operating_cash", "النقد التشغيلي", "Operating cash", _millions(cash),
             unit="M SAR", tone="navy"),
        _kpi("liquidity_risk", "مخاطر السيولة", "Liquidity risk", negative,
             tone="red" if negative else "green"),
        _kpi("pending_decisions", "قرارات معلقة", "Pending decisions",
             _pending_decisions(db, user), tone="amber"),
    ]
    return kpis


def _bd_summary(db, user, year, month) -> list[dict]:
    leads = _lead_counts(db, user) or {"new": 0}
    counts = _task_counts(_tasks(db, user), year, month)
    kpis = [
        _kpi("awaiting_assignment", "طلبات بانتظار الإسناد", "Awaiting assignment",
             leads["new"], tone="amber"),
        _kpi("tasks_in_progress", "مهام قيد التنفيذ", "Tasks in progress",
             counts["in_progress"], tone="navy"),
        _kpi("active_opportunities", "فرص نشطة", "Active opportunities",
             _active_opportunities(db, user), tone="green"),
        _kpi("reports_follow_up", "تقارير تحتاج متابعة", "Reports to follow up",
             _reports_needing_follow_up(db, user, year, month), tone="gold"),
    ]
    return kpis


def _manager_summary(db, user, year, month) -> list[dict]:
    net = _month_result(db, user, year, month)
    cash, _ = _effective_cash(db, user, year, month)
    kpis = [
        _kpi("month_result", "نتيجة الشهر", "Month result", _millions(net),
             unit="M SAR", tone="green" if net >= 0 else "red"),
        _kpi("cash_balance", "الرصيد النقدي", "Cash balance", _millions(cash),
             unit="M SAR", tone="navy"),
    ]
    leads = _lead_counts(db, user)
    if leads is not None:
        kpis.append(
            _kpi("prospective_clients", "العملاء المحتملون", "Prospective clients",
                 leads["total"], tone="gold")
        )
    kpis.append(
        _kpi("support_requests", "طلبات الدعم", "Support requests",
             _support_open(db, user), tone="amber")
    )
    return kpis


def _specialist_summary(db, user, year, month) -> list[dict]:
    counts = _task_counts(_tasks(db, user), year, month)
    return [
        _kpi("my_open_tasks", "مهامي المفتوحة", "My open tasks", counts["open"],
             tone="navy"),
        _kpi("overdue", "متأخرة", "Overdue", counts["overdue"],
             tone="red" if counts["overdue"] else "green"),
        _kpi("awaiting_info", "بانتظار معلومات", "Awaiting information",
             counts["awaiting"], tone="amber"),
        _kpi("completed_month", "مكتملة هذا الشهر", "Completed this month",
             counts["completed"], tone="green"),
    ]


def _sales_summary(db, user, year, month) -> list[dict]:
    leads = _lead_counts(db, user)
    if leads is None:
        return []
    return [
        _kpi("new_leads", "عملاء جدد", "New leads",
             _leads_created(db, user, year, month), tone="navy"),
        _kpi("awaiting_contact", "بانتظار التواصل", "Awaiting contact",
             leads["new"], tone="amber"),
        _kpi("qualified_leads", "فرص مؤهلة", "Qualified leads",
             leads["qualified"], tone="green"),
        _kpi("follow_up_week", "متابعة هذا الأسبوع", "Follow up this week",
             leads["in_progress"], tone="gold"),
    ]


def build_role_summary(
    db: Session, *, user: User, year: int, month: int
) -> dict | None:
    """The caller's role dashboard, or ``None`` when the role has none.

    Returns ``{"title_ar", "title_en", "kpis": [...]}``. The tile list is never
    empty when a summary is returned; a role whose every source is denied gets
    ``None`` so the dashboard keeps its holding strip rather than rendering an
    empty role block.
    """
    role = user.role_code
    if role in OWNER_ROLES:
        kpis = _owner_summary(db, user, year, month)
    elif role == "business_development":
        kpis = _bd_summary(db, user, year, month)
    elif role in MANAGER_ROLES:
        kpis = _manager_summary(db, user, year, month)
    elif role in SPECIALIST_ROLES:
        kpis = _specialist_summary(db, user, year, month)
    elif role in SALES_ROLES:
        kpis = _sales_summary(db, user, year, month)
    else:
        return None

    if not kpis:
        return None
    title_ar, title_en = ROLE_TITLES.get(role, ("لوحة القيادة", "Dashboard"))
    greet_ar, greet_en = _greeting(role)
    section_ar, section_en = ROLE_SECTIONS.get(role, ("", ""))
    shortcuts = [
        {"label_ar": a, "label_en": b, "view": v}
        for a, b, v in ROLE_SHORTCUTS.get(role, [])
    ]
    return {
        "role_code": role,
        "title_ar": title_ar,
        "title_en": title_en,
        "greeting_ar": greet_ar,
        "greeting_en": greet_en,
        "section_ar": section_ar,
        "section_en": section_en,
        "shortcuts": shortcuts,
        "view_all": ROLE_VIEW_ALL.get(role),
        "kpis": kpis,
    }
