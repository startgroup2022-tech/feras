"""Executions 06-11: operations, campaigns, complaints, advisors, decisions.

Implements the safe, independently-specified parts of the owner decisions:

* **D03** -- a single task lifecycle (New -> In-Progress -> Awaiting Review ->
  Complete, plus Return / Cancel / Reopen) with an audit entry on every change.
* **D02** -- weekly reports with a configurable question set (default five).
* **D04** -- confidential complaints are *not* company-scoped reads: they are
  visible only to the owner and to explicit confidential-access grantees. The
  generic counters and search deliberately do not count them.
* **D07** -- numbered owner decisions/directives with an executor, due date and
  follow-up status.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin
from backend.db.models.enums import (
    AdvisorSessionStatus,
    CampaignStatus,
    ComplaintStatus,
    OwnerDecisionStatus,
    TaskLifecycleStatus,
    TaskPriority,
    WeeklyReportStatus,
)

if TYPE_CHECKING:
    from backend.db.models.identity import Company, User

MONEY = Numeric(18, 2)

# D02: the weekly report asks at most this many core questions.
WEEKLY_REPORT_MAX_QUESTIONS = 5


class Task(Base, TimestampMixin):
    """A task with the D03 lifecycle.

    ``status`` changes are validated in the service; ``created_by``/``assignee``
    are explicit columns so the owner/assignee read scopes are query filters.
    """

    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_company_status", "company_id", "status"),
        Index("ix_tasks_assignee_status", "assignee_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=TaskLifecycleStatus.NEW.value, index=True
    )
    priority: Mapped[str] = mapped_column(
        String(10), nullable=False, default=TaskPriority.NORMAL.value
    )
    progress_percent: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reviewer_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped["Company"] = relationship()
    events: Mapped[list["TaskEvent"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class TaskEvent(Base, TimestampMixin):
    """Append-only history of a task's lifecycle (D03: every change audited)."""

    __tablename__ = "task_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    task: Mapped[Task] = relationship(back_populates="events")


class WeeklyReportQuestion(Base, TimestampMixin):
    """A configurable weekly-report question (D02). Not company-specific."""

    __tablename__ = "weekly_report_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    text_ar: Mapped[str] = mapped_column(String(400), nullable=False)
    text_en: Mapped[str | None] = mapped_column(String(400), nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )


class WeeklyReport(Base, TimestampMixin):
    """A submitted weekly report (D02: at most five core questions)."""

    __tablename__ = "weekly_reports"
    __table_args__ = (
        Index("ix_weekly_reports_company_week", "company_id", "period_year", "period_week"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_week: Mapped[int] = mapped_column(Integer, nullable=False)  # ISO week 1..53
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=WeeklyReportStatus.DRAFT.value, index=True
    )
    submitted_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    company: Mapped["Company"] = relationship()
    answers: Mapped[list["WeeklyReportAnswer"]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )


class WeeklyReportAnswer(Base, TimestampMixin):
    """One answer to one configured question."""

    __tablename__ = "weekly_report_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("weekly_reports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[int | None] = mapped_column(
        ForeignKey("weekly_report_questions.id", ondelete="SET NULL"), nullable=True
    )
    question_code: Mapped[str] = mapped_column(String(60), nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)

    report: Mapped[WeeklyReport] = relationship(back_populates="answers")


class Campaign(Base, TimestampMixin):
    """A marketing campaign and its measured results (S14 / D02)."""

    __tablename__ = "campaigns"
    __table_args__ = (
        Index("ix_campaigns_company_status", "company_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    platform: Mapped[str | None] = mapped_column(String(80), nullable=True)
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    budget: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    spend: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="SAR")
    lead_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    conversion_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CampaignStatus.PLANNED.value, index=True
    )
    manager_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    marketing_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    company: Mapped["Company"] = relationship()


class Complaint(Base, TimestampMixin):
    """A confidential complaint (S15 / D04).

    Confidential by construction: it has **no** company-scope read. Only the
    owner and explicit confidential-access grantees may read it, and the owner
    decides route/handle/postpone.
    """

    __tablename__ = "complaints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Optional: a complaint may concern a specific company or the group itself.
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ComplaintStatus.NEW.value, index=True
    )
    submitted_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_anonymous: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    routed_to_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class AdvisorAssignment(Base, TimestampMixin):
    """An external advisor assigned to a company (S19 / D04)."""

    __tablename__ = "advisor_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    advisor_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    specialty: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    assigned_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    company: Mapped["Company"] = relationship()


class AdvisorySession(Base, TimestampMixin):
    """A recorded advisory session with recommendations (S19)."""

    __tablename__ = "advisory_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    advisor_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AdvisorSessionStatus.SCHEDULED.value, index=True
    )
    topic: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendations: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class OwnerDecision(Base, TimestampMixin):
    """A numbered owner decision or directive (S22 / D07).

    ``number`` is unique per company scope (``company_id`` NULL = group-wide) so
    decisions can be referenced unambiguously.
    """

    __tablename__ = "owner_decisions"
    __table_args__ = (
        Index("ix_owner_decisions_company_status", "company_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=OwnerDecisionStatus.OPEN.value, index=True
    )
    executor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    follow_up_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped["Company | None"] = relationship()
    history: Mapped[list["OwnerDecisionEvent"]] = relationship(
        back_populates="decision", cascade="all, delete-orphan"
    )


class OwnerDecisionEvent(Base, TimestampMixin):
    """History/follow-up trail for an owner decision (D07)."""

    __tablename__ = "owner_decision_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    decision_id: Mapped[int] = mapped_column(
        ForeignKey("owner_decisions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    decision: Mapped[OwnerDecision] = relationship(back_populates="history")


class ConfidentialAccessGrant(Base, TimestampMixin):
    """A delegated grant to a specific confidential record (D04).

    The owner may delegate access to one record and one permission, with an
    expiry and an audit trail. Enforcement reads ``is_active`` (expiry checked
    in the service) so a grant cannot widen access after it lapses.
    """

    __tablename__ = "confidential_access_grants"
    __table_args__ = (
        Index("ix_confidential_grants_subject", "subject_type", "subject_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    subject_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    grantee_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    permission_code: Mapped[str] = mapped_column(String(80), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
