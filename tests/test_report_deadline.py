"""Monthly report deadline rule (business-rules.md rule 1).

A period's report is due on the 5th of the following month; a company is late
once that date has passed while the report is missing or still editable. These
tests cover the pure date maths, the scope-safe reads, and the idempotent scan.
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.db.models.enums import NotificationType, ReportStatus
from backend.db.models.identity import User
from backend.db.models.notifications import Notification
from backend.db.models.report import MonthlyReport
from backend.services import report_deadline

# A period whose deadline (5 February) has certainly passed, and one that has
# not, relative to the fixed "today" used throughout.
PAST = (2027, 1)
AFTER_DEADLINE = date(2027, 2, 20)
BEFORE_DEADLINE = date(2027, 2, 1)


# --------------------------------------------------------------------------
# pure date helpers
# --------------------------------------------------------------------------
def test_deadline_is_the_fifth_of_the_following_month():
    assert report_deadline.deadline_for_period(2027, 1) == date(2027, 2, 5)
    assert report_deadline.deadline_for_period(2027, 6) == date(2027, 7, 5)


def test_december_deadline_rolls_into_the_next_year():
    assert report_deadline.deadline_for_period(2027, 12) == date(2028, 1, 5)


def test_invalid_month_is_rejected():
    with pytest.raises(ValueError):
        report_deadline.deadline_for_period(2027, 13)


def test_configured_day_is_clamped_to_the_month_length(monkeypatch):
    from backend.core.config import settings

    # A mis-set day must degrade to the last valid day, never raise.
    monkeypatch.setattr(settings, "REPORT_DEADLINE_DAY", 31)
    assert report_deadline.deadline_for_period(2027, 1) == date(2027, 2, 28)
    assert report_deadline.deadline_for_period(2028, 1) == date(2028, 2, 29)


def test_previous_period_wraps_the_year():
    assert report_deadline.previous_period(date(2027, 3, 10)) == (2027, 2)
    assert report_deadline.previous_period(date(2027, 1, 3)) == (2026, 12)


def test_period_late_only_after_the_deadline():
    assert report_deadline.is_period_late(*PAST, today=AFTER_DEADLINE) is True
    assert report_deadline.is_period_late(*PAST, today=BEFORE_DEADLINE) is False
    # On the deadline day itself the report is still on time.
    assert (
        report_deadline.is_period_late(*PAST, today=date(2027, 2, 5)) is False
    )


@pytest.mark.parametrize("status", [ReportStatus.DRAFT.value, ReportStatus.RETURNED.value])
def test_missing_or_editable_report_past_deadline_is_late(status):
    assert (
        report_deadline.is_report_late(
            status, year=PAST[0], month=PAST[1], today=AFTER_DEADLINE
        )
        is True
    )
    assert (
        report_deadline.is_report_late(
            None, year=PAST[0], month=PAST[1], today=AFTER_DEADLINE
        )
        is True
    )


@pytest.mark.parametrize(
    "status",
    [
        ReportStatus.SUBMITTED.value,
        ReportStatus.UNDER_REVIEW.value,
        ReportStatus.REVIEWED.value,
        ReportStatus.LOCKED.value,
        ReportStatus.CANCELLED.value,
    ],
)
def test_a_submitted_report_is_never_late(status):
    assert (
        report_deadline.is_report_late(
            status, year=PAST[0], month=PAST[1], today=AFTER_DEADLINE
        )
        is False
    )


def test_an_editable_report_before_the_deadline_is_not_late():
    assert (
        report_deadline.is_report_late(
            ReportStatus.DRAFT.value, year=PAST[0], month=PAST[1], today=BEFORE_DEADLINE
        )
        is False
    )


# --------------------------------------------------------------------------
# scoped reads
# --------------------------------------------------------------------------
def _add_report(db, company, *, year, month, status):
    report = MonthlyReport(
        company_id=company.id,
        period_year=year,
        period_month=month,
        status=status,
        is_live=True,
    )
    db.add(report)
    db.commit()
    return report


def test_late_companies_lists_the_missing_report(db, make_company, make_user):
    company = make_company("LATE", "شركة متأخرة")
    manager = make_user("late.mgr@corp.sa", "company_manager", [company])
    owner = make_user("late.owner@corp.sa", "holding_owner")

    late = report_deadline.late_companies(
        db, user=owner, year=PAST[0], month=PAST[1], today=AFTER_DEADLINE
    )

    assert [row["id"] for row in late] == [company.id]
    assert late[0]["report_status"] is None
    assert late[0]["deadline"] == date(2027, 2, 5)
    assert manager is not None  # fixture creates the manager for the scan test


def test_late_companies_excludes_a_submitted_report(db, make_company, make_user):
    company = make_company("ONTIME", "شركة ملتزمة")
    _add_report(db, company, year=PAST[0], month=PAST[1], status=ReportStatus.SUBMITTED.value)
    owner = make_user("ontime.owner@corp.sa", "holding_owner")

    late = report_deadline.late_companies(
        db, user=owner, year=PAST[0], month=PAST[1], today=AFTER_DEADLINE
    )

    assert late == []


def test_late_companies_is_company_scoped(db, make_company, make_user):
    alpha = make_company("ALPHA-D", "شركة ألفا")
    beta = make_company("BETA-D", "شركة بيتا")
    alpha_mgr = make_user("alpha.d@corp.sa", "company_manager", [alpha])
    make_user("beta.d@corp.sa", "company_manager", [beta])

    late = report_deadline.late_companies(
        db, user=alpha_mgr, year=PAST[0], month=PAST[1], today=AFTER_DEADLINE
    )

    # The manager only ever sees its own company, never the sibling.
    assert [row["id"] for row in late] == [alpha.id]


def test_late_companies_is_empty_before_the_deadline(db, make_company, make_user):
    make_company("EARLY", "شركة مبكرة")
    owner = make_user("early.owner@corp.sa", "holding_owner")

    late = report_deadline.late_companies(
        db, user=owner, year=PAST[0], month=PAST[1], today=BEFORE_DEADLINE
    )

    assert late == []


# --------------------------------------------------------------------------
# idempotent scan
# --------------------------------------------------------------------------
def test_scan_notifies_managers_and_owners(db, make_company, make_user):
    company = make_company("SCAN", "شركة مسح")
    manager = make_user("scan.mgr@corp.sa", "company_manager", [company])
    owner = make_user("scan.owner@corp.sa", "holding_owner")

    result = report_deadline.scan_report_deadlines(db, today=AFTER_DEADLINE)

    assert result["period_year"] == PAST[0]
    assert result["period_month"] == PAST[1]
    assert result["late_count"] == 1

    rows = (
        db.query(Notification)
        .filter(Notification.type == NotificationType.REPORT_DEADLINE_MISSED.value)
        .all()
    )
    recipients = {row.recipient_id for row in rows}
    assert {manager.id, owner.id} <= recipients


def test_scan_is_idempotent(db, make_company, make_user):
    company = make_company("SCAN2", "شركة مسح")
    make_user("scan2.mgr@corp.sa", "company_manager", [company])

    first = report_deadline.scan_report_deadlines(db, today=AFTER_DEADLINE)
    second = report_deadline.scan_report_deadlines(db, today=AFTER_DEADLINE)

    # The first run raises one alert; the second is deduped and raises none,
    # so exactly one notification row exists no matter how often the scan runs.
    assert first["notifications"] == 1
    assert second["notifications"] == 0
    assert second["late_count"] == 1
    assert (
        db.query(Notification)
        .filter(Notification.type == NotificationType.REPORT_DEADLINE_MISSED.value)
        .count()
        == 1
    )


def test_scan_is_silent_before_the_deadline(db, make_company, make_user):
    company = make_company("SCAN3", "شركة مسح")
    make_user("scan3.mgr@corp.sa", "company_manager", [company])

    result = report_deadline.scan_report_deadlines(db, today=BEFORE_DEADLINE)

    assert result["late_count"] == 0
    assert result["notifications"] == 0
    assert (
        db.query(Notification)
        .filter(Notification.type == NotificationType.REPORT_DEADLINE_MISSED.value)
        .count()
        == 0
    )


def test_scan_does_not_touch_the_report(db, make_company, make_user):
    company = make_company("SCAN4", "شركة مسح")
    report = _add_report(
        db, company, year=PAST[0], month=PAST[1], status=ReportStatus.DRAFT.value
    )
    make_user("scan4.mgr@corp.sa", "company_manager", [company])

    report_deadline.scan_report_deadlines(db, today=AFTER_DEADLINE)

    db.refresh(report)
    assert report.status == ReportStatus.DRAFT.value
