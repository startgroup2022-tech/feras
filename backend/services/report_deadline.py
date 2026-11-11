"""Monthly report submission deadline (business rule 1).

``business-rules.md`` rule 1 and the approved prototype both state it plainly:

    "موعد التسليم يوم 5 من الشهر التالي. الشركة متأخرة إذا تجاوز التاريخ الموعد
     ولم يُرسل التقرير."

So a month's report is due on the 5th of the following month, and a company is
*late* once that date has passed while its report for the period is still
missing or in an editable state (``draft`` / ``returned``). A submitted,
reviewed, approved, locked or cancelled report is never late -- the company did
its part.

The functions here are pure date helpers plus two scoped reads and one
idempotent scan. Nothing mutates a report: the deadline is a *derived* state, so
a late company is reported, never rewritten.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import NotificationType, ReportStatus
from backend.db.models.identity import Company, User
from backend.db.models.report import MonthlyReport
from backend.rbac.authorization import accessible_company_ids
from backend.services import audit_service, notification_service

# A report in one of these states has *not* reached the Holding yet, so the
# deadline applies to it. Everything else (submitted and beyond) is on time.
EDITABLE_STATUSES = frozenset({ReportStatus.DRAFT.value, ReportStatus.RETURNED.value})


def _scope(stmt, column, user: User):
    """Apply the caller's company scope as a SQL filter (IDOR-safe)."""
    allowed = accessible_company_ids(user)
    if allowed is None:
        return stmt
    if not allowed:
        return stmt.where(False)
    return stmt.where(column.in_(allowed))


# --------------------------------------------------------------------------
# pure date helpers
# --------------------------------------------------------------------------
def deadline_for_period(year: int, month: int) -> date:
    """The submission deadline for a reporting period.

    ``month`` is 1..12; the deadline falls on ``REPORT_DEADLINE_DAY`` of the
    following month (the 5th, by default). The configured day is clamped to the
    target month's length so a mis-set ``REPORT_DEADLINE_DAY`` degrades to the
    last day of the month instead of raising on, say, 31 February.
    """
    if month < 1 or month > 12:
        raise ValueError("month must be between 1 and 12")
    target_year, target_month = (year + 1, 1) if month == 12 else (year, month + 1)
    day = max(1, min(settings.REPORT_DEADLINE_DAY, monthrange(target_year, target_month)[1]))
    return date(target_year, target_month, day)


def previous_period(today: date) -> tuple[int, int]:
    """The period a report is expected for on ``today`` (the month before it)."""
    if today.month == 1:
        return today.year - 1, 12
    return today.year, today.month - 1


def is_period_late(year: int, month: int, *, today: date | None = None) -> bool:
    """Whether the deadline for the period has already passed."""
    today = today or date.today()
    return today > deadline_for_period(year, month)


def is_report_late(status: str | None, *, year: int, month: int, today: date | None = None) -> bool:
    """Whether a company is late for a period given its report status.

    ``status`` is ``None`` when the company has no report at all. A missing or
    still-editable report past the deadline is late; anything already sent is
    not.
    """
    if not is_period_late(year, month, today=today):
        return False
    return status is None or status in EDITABLE_STATUSES


# --------------------------------------------------------------------------
# scoped reads
# --------------------------------------------------------------------------
def late_companies(
    db: Session, *, user: User, year: int, month: int, today: date | None = None
) -> list[dict]:
    """Companies in the caller's scope that are late for the period.

    Applies the caller's company scope as a SQL filter, so a company-scoped user
    only ever sees its own companies. Returns one dict per late company with the
    derived reason and the deadline date.
    """
    today = today or date.today()
    if not is_period_late(year, month, today=today):
        return []

    # The live report for the period, per company (None when there is none).
    stmt = (
        select(Company, MonthlyReport)
        .select_from(Company)
        .outerjoin(
            MonthlyReport,
            (MonthlyReport.company_id == Company.id)
            & (MonthlyReport.period_year == year)
            & (MonthlyReport.period_month == month)
            & (MonthlyReport.is_live.is_(True)),
        )
        .order_by(Company.name_en)
    )
    stmt = _scope(stmt, Company.id, user)
    deadline = deadline_for_period(year, month)

    late: list[dict] = []
    for company, report in db.execute(stmt).all():
        status = report.status if report else None
        if not is_report_late(status, year=year, month=month, today=today):
            continue
        if status is None:
            reason_ar = f"تقرير {month}/{year} لم يُرسل بعد"
            reason_en = f"The {month}/{year} report has not been submitted"
        else:
            reason_ar = f"تقرير {month}/{year} ما زال بانتظار الإرسال"
            reason_en = f"The {month}/{year} report is still awaiting submission"
        late.append(
            {
                "id": company.id,
                "code": company.code,
                "name_ar": company.name_ar,
                "name_en": company.name_en,
                "health": company.health,
                "report_status": status,
                "deadline": deadline,
                "reason_ar": reason_ar,
                "reason_en": reason_en,
            }
        )
    return late


# --------------------------------------------------------------------------
# idempotent scan (scheduled job)
# --------------------------------------------------------------------------
def _manager_and_owner_ids(db: Session, company_id: int) -> list[int]:
    """Active recipients for a late-report alert: the company's managers and
    every holding-wide owner. Never widens any single user's scope -- it is the
    set of people already responsible for the company."""
    from backend.db.models.enums import RoleCode
    from backend.db.models.identity import Role, UserCompanyAccess

    managers = set(
        db.execute(
            select(UserCompanyAccess.user_id)
            .join(User, User.id == UserCompanyAccess.user_id)
            .join(Role, Role.id == User.role_id)
            .where(
                UserCompanyAccess.company_id == company_id,
                Role.code == RoleCode.COMPANY_MANAGER.value,
                User.is_active.is_(True),
            )
        ).scalars()
    )
    owners = set(
        db.execute(
            select(User.id)
            .join(Role, Role.id == User.role_id)
            .where(
                User.is_active.is_(True),
                (User.is_superuser.is_(True))
                | (Role.code == RoleCode.HOLDING_OWNER.value),
            )
        ).scalars()
    )
    return sorted(managers | owners)


def scan_report_deadlines(
    db: Session,
    *,
    today: date | None = None,
    actor_user_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    """Raise "report is late" notifications for the expected period.

    Idempotent by construction: the ``dedupe_key`` includes the period, so
    running the scan daily raises at most one notification per recipient per
    period. The scan never edits a report; it only reads and notifies, which is
    what makes it safe to run unattended as a scheduled job.

    Returns a summary: the period scanned, the late companies, and how many
    notifications were created.
    """
    today = today or date.today()
    year, month = previous_period(today)
    deadline = deadline_for_period(year, month)

    if not is_period_late(year, month, today=today):
        return {
            "period_year": year,
            "period_month": month,
            "deadline": deadline,
            "late_count": 0,
            "notifications": 0,
            "late": [],
        }

    # Read every late company holding-wide (the job is not user-scoped); each
    # recipient then only ever learns about a company they already handle.
    stmt = (
        select(Company, MonthlyReport)
        .select_from(Company)
        .outerjoin(
            MonthlyReport,
            (MonthlyReport.company_id == Company.id)
            & (MonthlyReport.period_year == year)
            & (MonthlyReport.period_month == month)
            & (MonthlyReport.is_live.is_(True)),
        )
        .order_by(Company.name_en)
    )
    late: list[dict] = []
    created_total = 0
    for company, report in db.execute(stmt).all():
        status = report.status if report else None
        if not is_report_late(status, year=year, month=month, today=today):
            continue
        late.append(
            {
                "id": company.id,
                "code": company.code,
                "name_ar": company.name_ar,
                "name_en": company.name_en,
                "report_status": status,
            }
        )
        recipients = _manager_and_owner_ids(db, company.id)
        if not recipients:
            continue
        created = notification_service.notify(
            db,
            recipient_ids=recipients,
            type=NotificationType.REPORT_DEADLINE_MISSED.value,
            priority="high",
            title_ar="تقرير شهري متأخر",
            title_en="A monthly report is late",
            message_ar=(
                f"{company.name_ar}: تقرير {month}/{year} متأخر عن موعد "
                f"{deadline.isoformat()}."
            ),
            message_en=(
                f"{company.name_en or company.name_ar}: the {month}/{year} report "
                f"is past its {deadline.isoformat()} deadline."
            ),
            company_id=company.id,
            entity_type="company",
            entity_id=company.id,
            dedupe_key=f"report_deadline:{company.id}:{year}-{month:02d}",
            commit=False,
            actor_user_id=actor_user_id,
            emit_webhook=False,
        )
        created_total += len(created)

    db.commit()

    audit_service.record(
        db,
        action=AuditAction.REPORT_DEADLINE_SCANNED,
        actor_user_id=actor_user_id,
        entity_type="monthly_report_deadline",
        entity_id=f"{year}-{month:02d}",
        metadata={
            "period": f"{year}-{month:02d}",
            "late_count": len(late),
            "notifications": created_total,
        },
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return {
        "period_year": year,
        "period_month": month,
        "deadline": deadline,
        "late_count": len(late),
        "notifications": created_total,
        "late": late,
    }


__all__ = [
    "EDITABLE_STATUSES",
    "deadline_for_period",
    "previous_period",
    "is_period_late",
    "is_report_late",
    "late_companies",
    "scan_report_deadlines",
]
