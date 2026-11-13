"""Tasks, weekly reports, campaigns, complaints, advisors, owner decisions.

Owner decisions D02/D03/D04/D07. Policy-dependent behaviour is left disabled:

* task lifecycle transitions are enforced here (D03), with an audit entry on
  every change;
* the weekly report accepts at most the configured number of core questions
  (D02);
* confidential complaints are never listed or counted by company scope -- only
  the owner and explicit grantees read them (D04).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.errors import ConflictError, NotFoundError, ValidationError
from backend.db.base import utcnow
from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import (
    AdvisorReportStatus,
    AdvisorSessionStatus,
    CampaignStatus,
    ComplaintStatus,
    ManagementBriefStatus,
    ManagementBriefUrgency,
    NotificationPriority,
    NotificationType,
    OwnerDecisionStatus,
    PlanRequestStatus,
    ProjectRecordType,
    ProjectStage,
    ReportApprovalStatus,
    TaskLifecycleStatus,
    WeeklyReportStatus,
)
from backend.db.models.identity import Role, RoleCode, User
from backend.db.models.operations import (
    WEEKLY_REPORT_MAX_QUESTIONS,
    AdvisorAssignment,
    AdvisorMonthlyReport,
    AdvisorySession,
    Campaign,
    Complaint,
    ManagementBrief,
    OwnerDecision,
    OwnerDecisionEvent,
    PlanRequest,
    ProjectRecord,
    Task,
    TaskEvent,
    WeeklyReport,
    WeeklyReportAnswer,
    WeeklyReportQuestion,
)
from backend.rbac.authorization import (
    accessible_company_ids,
    has_any_permission,
    require_any_permission,
    require_company_access,
    require_permission,
)
from backend.db.models.report import MonthlyReport
from backend.rbac.permissions import Perm
from backend.services import audit_service, confidential_access_service, notification_service

# D03 lifecycle transitions. Return / Cancel / Reopen are explicit edges.
TASK_TRANSITIONS: dict[str, set[str]] = {
    TaskLifecycleStatus.NEW.value: {
        TaskLifecycleStatus.IN_PROGRESS.value,
        TaskLifecycleStatus.CANCELLED.value,
    },
    TaskLifecycleStatus.IN_PROGRESS.value: {
        TaskLifecycleStatus.AWAITING_REVIEW.value,
        TaskLifecycleStatus.CANCELLED.value,
    },
    TaskLifecycleStatus.AWAITING_REVIEW.value: {
        TaskLifecycleStatus.COMPLETE.value,
        TaskLifecycleStatus.RETURNED.value,
    },
    TaskLifecycleStatus.RETURNED.value: {
        TaskLifecycleStatus.IN_PROGRESS.value,
        TaskLifecycleStatus.CANCELLED.value,
    },
    TaskLifecycleStatus.COMPLETE.value: {TaskLifecycleStatus.IN_PROGRESS.value},  # reopen
    TaskLifecycleStatus.CANCELLED.value: {TaskLifecycleStatus.NEW.value},  # reopen
}

TASK_STATUS_LABELS: dict[str, tuple[str, str]] = {
    TaskLifecycleStatus.NEW.value: ("جديد", "New"),
    TaskLifecycleStatus.IN_PROGRESS.value: ("قيد التنفيذ", "In progress"),
    TaskLifecycleStatus.AWAITING_REVIEW.value: ("بانتظار المراجعة", "Awaiting review"),
    TaskLifecycleStatus.COMPLETE.value: ("منجز", "Complete"),
    TaskLifecycleStatus.RETURNED.value: ("مُعاد", "Returned"),
    TaskLifecycleStatus.CANCELLED.value: ("ملغى", "Cancelled"),
}


def _task_status_labels(status: str) -> tuple[str, str]:
    return TASK_STATUS_LABELS.get(status, (status, status))


# --------------------------------------------------------------------------
# tasks (D03)
# --------------------------------------------------------------------------
def create_task(
    db: Session, *, user: User, company_id: int, title: str,
    description: str | None = None, assignee_id: int | None = None,
    reviewer_id: int | None = None, priority: str = "normal", due_date=None,
    ip_address: str | None = None, user_agent: str | None = None,
) -> Task:
    require_permission(user, Perm.TASK_CREATE)
    require_company_access(user, company_id, write=True)

    task = Task(
        company_id=company_id,
        title=title.strip(),
        description=description,
        assignee_id=assignee_id,
        reviewer_id=reviewer_id,
        priority=priority,
        due_date=due_date,
        status=TaskLifecycleStatus.NEW.value,
        created_by_id=user.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    _add_task_event(db, task=task, actor=user, from_status=None, to_status=task.status,
                    note="created")
    audit_service.record(
        db, action=AuditAction.TASK_CREATED, actor_user_id=user.id,
        entity_type="task", entity_id=task.id, company_id=company_id,
        ip_address=ip_address, user_agent=user_agent,
    )
    notification_service.notify_task_assigned(
        db, assignee_id=task.assignee_id, task_id=task.id, company_id=company_id,
        task_title=task.title, actor_user_id=user.id,
    )
    return task


def _add_task_event(db: Session, *, task: Task, actor: User, from_status: str | None,
                    to_status: str, note: str | None) -> None:
    db.add(TaskEvent(task_id=task.id, from_status=from_status, to_status=to_status,
                     actor_id=actor.id, note=note))
    db.commit()


def change_task_status(
    db: Session, *, user: User, task_id: int, new_status: str, note: str | None = None,
    ip_address: str | None = None, user_agent: str | None = None,
) -> Task:
    require_permission(user, Perm.TASK_STATUS_CHANGE)
    task = _get_task(db, user=user, task_id=task_id)
    require_company_access(user, task.company_id, write=True)

    if new_status == task.status:
        raise ConflictError("The task already has this status.")
    if new_status not in TASK_TRANSITIONS.get(task.status, set()):
        raise ValidationError(
            f"Cannot move a task from '{task.status}' to '{new_status}'."
        )

    previous = task.status
    task.status = new_status
    if new_status == TaskLifecycleStatus.COMPLETE.value:
        task.completed_at = utcnow()
        task.progress_percent = 100
    db.add(task)
    db.commit()
    db.refresh(task)

    _add_task_event(db, task=task, actor=user, from_status=previous, to_status=new_status,
                    note=note)
    audit_service.record(
        db, action=AuditAction.TASK_STATUS_CHANGED, actor_user_id=user.id,
        entity_type="task", entity_id=task.id, company_id=task.company_id,
        ip_address=ip_address, user_agent=user_agent,
        metadata={"from": previous, "to": new_status},
    )
    status_ar, status_en = _task_status_labels(new_status)
    notification_service.notify_task_status_changed(
        db,
        recipient_ids=[uid for uid in (task.created_by_id, task.reviewer_id) if uid],
        task_id=task.id, company_id=task.company_id, task_title=task.title,
        status_ar=status_ar, status_en=status_en, actor_user_id=user.id,
    )
    return task


def note_task(
    db: Session, *, user: User, task_id: int, note: str,
    ip_address: str | None = None, user_agent: str | None = None,
) -> Task:
    """Deck slide 20: [إضافة سؤال] records a clarification on the task log.

    The task does not change state -- the specialist is asking while it stays
    where it is -- so this appends a same-state event with the question as its
    note. A note is a question, not a transition: the status history therefore
    shows ``X -> X`` with the text, which is exactly the append-only audit the
    deck asks for.
    """
    require_permission(user, Perm.TASK_STATUS_CHANGE)
    task = _get_task(db, user=user, task_id=task_id)
    require_company_access(user, task.company_id, write=True)

    _add_task_event(db, task=task, actor=user, from_status=task.status,
                    to_status=task.status, note=note)
    audit_service.record(
        db, action=AuditAction.TASK_STATUS_CHANGED, actor_user_id=user.id,
        entity_type="task", entity_id=task.id, company_id=task.company_id,
        ip_address=ip_address, user_agent=user_agent,
        metadata={"from": task.status, "to": task.status, "note": note},
    )
    return task


def update_task(
    db: Session, *, user: User, task_id: int, changes: dict,
    ip_address: str | None = None, user_agent: str | None = None,
) -> Task:
    require_permission(user, Perm.TASK_UPDATE)
    task = _get_task(db, user=user, task_id=task_id)
    require_company_access(user, task.company_id, write=True)
    for key, value in changes.items():
        if value is not None and hasattr(task, key):
            setattr(task, key, value)
    db.add(task)
    db.commit()
    db.refresh(task)
    audit_service.record(
        db, action=AuditAction.TASK_UPDATED, actor_user_id=user.id,
        entity_type="task", entity_id=task.id, company_id=task.company_id,
        ip_address=ip_address, user_agent=user_agent,
        metadata={"fields": sorted(changes.keys())},
    )
    return task


def list_tasks(
    db: Session, *, user: User, company_id: int | None = None,
    status: str | None = None, mine: bool = False, overdue: bool = False,
) -> list[Task]:
    read_all = has_any_permission(user, Perm.TASK_READ_ALL)
    read_own = has_any_permission(user, Perm.TASK_READ_OWN)
    if not (read_all or read_own):
        from backend.core.errors import PermissionDeniedError

        raise PermissionDeniedError("You do not have permission to view tasks.")
    stmt = select(Task).order_by(Task.created_at.desc())
    if mine or not read_all:
        stmt = stmt.where(Task.assignee_id == user.id)
    else:
        allowed = accessible_company_ids(user)
        if allowed is not None:
            stmt = stmt.where(Task.company_id.in_(allowed)) if allowed else stmt.where(False)
    if company_id is not None:
        stmt = stmt.where(Task.company_id == company_id)
    if status is not None:
        stmt = stmt.where(Task.status == status)
    if overdue:
        # AC-17: a completed (or cancelled) task is never in the overdue list.
        stmt = stmt.where(
            Task.due_date.is_not(None),
            Task.due_date < date.today(),
            Task.status.not_in(
                [TaskLifecycleStatus.COMPLETE.value, TaskLifecycleStatus.CANCELLED.value]
            ),
        )
    return list(db.execute(stmt).scalars())


def _is_task_overdue(task: Task) -> bool:
    return bool(
        task.due_date
        and task.due_date < date.today()
        and task.status
        not in (TaskLifecycleStatus.COMPLETE.value, TaskLifecycleStatus.CANCELLED.value)
    )


def _get_task(db: Session, *, user: User, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise NotFoundError("Task not found.")
    require_company_access(user, task.company_id)
    return task


def serialise_task(task: Task) -> dict:
    # ``assignee``/``reviewer`` display names are added so the list can offer
    # the deck's "مسؤول" filter (slides 134-136) and the detail view can label
    # the reviewer without resolving bare ids on the client.
    assignee = task.assignee
    reviewer = task.reviewer
    return {
        "id": task.id, "company_id": task.company_id, "title": task.title,
        "description": task.description, "status": task.status, "priority": task.priority,
        "progress_percent": task.progress_percent, "due_date": task.due_date,
        "created_by_id": task.created_by_id, "assignee_id": task.assignee_id,
        "assignee_name_ar": assignee.full_name_ar if assignee else None,
        "assignee_name_en": assignee.full_name_en if assignee else None,
        "reviewer_id": task.reviewer_id,
        "reviewer_name_ar": reviewer.full_name_ar if reviewer else None,
        "reviewer_name_en": reviewer.full_name_en if reviewer else None,
        "completed_at": task.completed_at,
        "is_overdue": _is_task_overdue(task),
        "created_at": task.created_at, "updated_at": task.updated_at,
        "events": [
            {"from_status": e.from_status, "to_status": e.to_status, "actor_id": e.actor_id,
             "note": e.note, "created_at": e.created_at}
            for e in sorted(task.events, key=lambda x: x.created_at)
        ],
    }


# --------------------------------------------------------------------------
# weekly reports (D02)
# --------------------------------------------------------------------------
def create_weekly_question(db: Session, *, user: User, code: str, text_ar: str,
                           text_en: str | None = None, order_index: int = 0) -> WeeklyReportQuestion:
    require_permission(user, Perm.WEEKLY_REPORT_TEMPLATE_MANAGE)
    q = WeeklyReportQuestion(code=code, text_ar=text_ar, text_en=text_en,
                             order_index=order_index, is_active=True)
    db.add(q)
    db.commit()
    db.refresh(q)
    audit_service.record(db, action=AuditAction.WEEKLY_REPORT_QUESTION_CREATED,
                         actor_user_id=user.id, entity_type="weekly_report_question",
                         entity_id=q.id)
    return q


def list_weekly_questions(db: Session, *, user: User) -> list[WeeklyReportQuestion]:
    # Readable by anyone who may view weekly reports, and by the template
    # manager (who holds only ``template.manage`` and must see the questions
    # they are editing). The write path is still ``TEMPLATE_MANAGE``-only.
    require_any_permission(
        user, Perm.WEEKLY_REPORT_READ_OWN, Perm.WEEKLY_REPORT_TEMPLATE_MANAGE
    )
    return list(db.execute(
        select(WeeklyReportQuestion).where(WeeklyReportQuestion.is_active.is_(True))
        .order_by(WeeklyReportQuestion.order_index)
    ).scalars())


def submit_weekly_report(
    db: Session, *, user: User, company_id: int, period_year: int, period_week: int,
    answers: list[dict], summary: str | None = None,
    ip_address: str | None = None, user_agent: str | None = None,
) -> WeeklyReport:
    require_permission(user, Perm.WEEKLY_REPORT_SUBMIT)
    require_company_access(user, company_id, write=True)

    # D02: the weekly report contains at most the configured number of core
    # questions.
    if len(answers) > WEEKLY_REPORT_MAX_QUESTIONS:
        raise ValidationError(
            f"A weekly report may contain at most {WEEKLY_REPORT_MAX_QUESTIONS} answers."
        )

    report = WeeklyReport(
        company_id=company_id, period_year=period_year, period_week=period_week,
        status=WeeklyReportStatus.SUBMITTED.value, submitted_by_id=user.id,
        submitted_at=utcnow(), summary=summary,
    )
    db.add(report)
    db.flush()
    for a in answers:
        db.add(WeeklyReportAnswer(
            report_id=report.id,
            question_id=a.get("question_id"),
            question_code=a.get("question_code", ""),
            answer=a.get("answer"),
        ))
    db.commit()
    db.refresh(report)

    audit_service.record(
        db, action=AuditAction.WEEKLY_REPORT_SUBMITTED, actor_user_id=user.id,
        entity_type="weekly_report", entity_id=report.id, company_id=company_id,
        ip_address=ip_address, user_agent=user_agent,
    )
    return report


def list_weekly_reports(db: Session, *, user: User, company_id: int | None = None) -> list[WeeklyReport]:
    read_all = has_any_permission(user, Perm.WEEKLY_REPORT_READ_ALL)
    read_own = has_any_permission(user, Perm.WEEKLY_REPORT_READ_OWN)
    if not (read_all or read_own):
        from backend.core.errors import PermissionDeniedError

        raise PermissionDeniedError("You do not have permission to view weekly reports.")
    stmt = select(WeeklyReport).order_by(WeeklyReport.created_at.desc())
    if not read_all:
        stmt = stmt.where(WeeklyReport.submitted_by_id == user.id)
    else:
        allowed = accessible_company_ids(user)
        if allowed is not None:
            stmt = stmt.where(WeeklyReport.company_id.in_(allowed)) if allowed else stmt.where(False)
    if company_id is not None:
        stmt = stmt.where(WeeklyReport.company_id == company_id)
    return list(db.execute(stmt).scalars())


def serialise_weekly_report(report: WeeklyReport) -> dict:
    return {
        "id": report.id, "company_id": report.company_id,
        "period_year": report.period_year, "period_week": report.period_week,
        "status": report.status, "submitted_by_id": report.submitted_by_id,
        "submitted_at": report.submitted_at, "summary": report.summary,
        "created_at": report.created_at,
        "answers": [
            {"question_code": a.question_code, "answer": a.answer} for a in report.answers
        ],
    }


# --------------------------------------------------------------------------
# campaigns (D02)
# --------------------------------------------------------------------------
def create_campaign(db: Session, *, user: User, company_id: int, name: str,
                    platform: str | None = None, goal: str | None = None,
                    start_date=None, end_date=None, budget=None, currency: str = "SAR",
                    ip_address: str | None = None, user_agent: str | None = None) -> Campaign:
    require_permission(user, Perm.CAMPAIGN_MANAGE)
    require_company_access(user, company_id, write=True)
    campaign = Campaign(company_id=company_id, name=name.strip(), platform=platform,
                        goal=goal, start_date=start_date, end_date=end_date,
                        budget=budget, currency=currency, status=CampaignStatus.PLANNED.value,
                        created_by_id=user.id)
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    audit_service.record(db, action=AuditAction.CAMPAIGN_CREATED, actor_user_id=user.id,
                         entity_type="campaign", entity_id=campaign.id, company_id=company_id,
                         ip_address=ip_address, user_agent=user_agent)
    return campaign


def update_campaign(db: Session, *, user: User, campaign_id: int, changes: dict,
                    ip_address: str | None = None, user_agent: str | None = None) -> Campaign:
    require_permission(user, Perm.CAMPAIGN_MANAGE)
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise NotFoundError("Campaign not found.")
    require_company_access(user, campaign.company_id, write=True)
    for key, value in changes.items():
        if value is not None and hasattr(campaign, key):
            setattr(campaign, key, value)
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    audit_service.record(db, action=AuditAction.CAMPAIGN_UPDATED, actor_user_id=user.id,
                         entity_type="campaign", entity_id=campaign.id,
                         company_id=campaign.company_id, ip_address=ip_address,
                         user_agent=user_agent, metadata={"fields": sorted(changes.keys())})
    return campaign


def list_campaigns(db: Session, *, user: User, company_id: int | None = None) -> list[Campaign]:
    require_permission(user, Perm.CAMPAIGN_READ)
    stmt = select(Campaign).order_by(Campaign.created_at.desc())
    allowed = accessible_company_ids(user)
    if allowed is not None:
        stmt = stmt.where(Campaign.company_id.in_(allowed)) if allowed else stmt.where(False)
    if company_id is not None:
        stmt = stmt.where(Campaign.company_id == company_id)
    return list(db.execute(stmt).scalars())


def serialise_campaign(c: Campaign, *, linked_lead_count: int | None = None) -> dict:
    return {
        "id": c.id, "company_id": c.company_id, "name": c.name, "platform": c.platform,
        "goal": c.goal, "start_date": c.start_date, "end_date": c.end_date,
        "budget": c.budget, "spend": c.spend, "currency": c.currency,
        # ``lead_count`` is the manually entered external result (spec S14
        # "نتائج خارجية"). ``linked_lead_count`` is the number of *linked* lead
        # records. They are reported side by side and never summed: AC-14
        # forbids double counting a customer registered both manually and by
        # link.
        "lead_count": c.lead_count, "conversion_count": c.conversion_count,
        "linked_lead_count": linked_lead_count,
        "status": c.status, "manager_note": c.manager_note, "marketing_note": c.marketing_note,
        "created_at": c.created_at,
    }


def linked_lead_count(db: Session, *, campaign_id: int) -> int:
    """How many leads are linked to this campaign (S14 'عرض العملاء')."""
    from backend.db.models.website import WebsiteLead

    return int(
        db.execute(
            select(func.count(WebsiteLead.id)).where(
                WebsiteLead.campaign_id == campaign_id
            )
        ).scalar_one()
    )


def list_campaign_leads(db: Session, *, user: User, campaign_id: int) -> list:
    """The *same* lead records linked to a campaign -- never a second copy.

    S14's "عرض العملاء" opens the linked records; this returns the existing
    ``website_leads`` rows, so the campaign view and the leads view show one
    record, not two.
    """
    require_permission(user, Perm.CAMPAIGN_READ)
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise NotFoundError("Campaign not found.")
    require_company_access(user, campaign.company_id, write=False)
    from backend.db.models.website import WebsiteLead

    stmt = (
        select(WebsiteLead)
        .where(WebsiteLead.campaign_id == campaign_id)
        .order_by(WebsiteLead.created_at.desc(), WebsiteLead.id.desc())
    )
    return list(db.execute(stmt).scalars())


# --------------------------------------------------------------------------
# complaints (D04 -- confidential)
# --------------------------------------------------------------------------
def create_complaint(
    db: Session, *, user: User, subject: str, body: str, company_id: int | None = None,
    is_anonymous: bool = False, ip_address: str | None = None, user_agent: str | None = None,
) -> Complaint:
    require_permission(user, Perm.COMPLAINT_CREATE)
    if company_id is not None:
        require_company_access(user, company_id, write=True)
    complaint = Complaint(company_id=company_id, subject=subject.strip(), body=body,
                          status=ComplaintStatus.NEW.value, submitted_by_id=user.id,
                          is_anonymous=is_anonymous)
    db.add(complaint)
    db.commit()
    db.refresh(complaint)
    # Deliberately no company-scoped audit payload detail: the subject must not
    # leak into a shared log.
    audit_service.record(db, action=AuditAction.COMPLAINT_SUBMITTED, actor_user_id=user.id,
                         entity_type="complaint", entity_id=complaint.id,
                         ip_address=ip_address, user_agent=user_agent)
    return complaint


def decide_complaint(
    db: Session, *, user: User, complaint_id: int, new_status: str, decision: str | None = None,
    routed_to_id: int | None = None, ip_address: str | None = None,
    user_agent: str | None = None,
) -> Complaint:
    require_permission(user, Perm.COMPLAINT_DECIDE)
    complaint = db.get(Complaint, complaint_id)
    if complaint is None:
        raise NotFoundError("Complaint not found.")
    confidential_access_service.require_confidential_read(
        db, user=user, subject_type="complaint", subject_id=complaint.id,
        permission=Perm.COMPLAINT_DECIDE,
    )
    complaint.status = new_status
    complaint.decision = decision
    complaint.routed_to_id = routed_to_id
    complaint.decided_by_id = user.id
    complaint.decided_at = utcnow()
    db.add(complaint)
    db.commit()
    db.refresh(complaint)
    audit_service.record(db, action=AuditAction.COMPLAINT_DECIDED, actor_user_id=user.id,
                         entity_type="complaint", entity_id=complaint.id,
                         ip_address=ip_address, user_agent=user_agent,
                         metadata={"status": new_status})
    _notify_complaint_route(db, complaint=complaint, actor=user)
    return complaint


def _notify_complaint_route(db: Session, *, complaint: Complaint, actor: User) -> None:
    """S15: notify only the person the owner explicitly names (never a manager).

    The complaint stays confidential: the notification carries no subject or
    body, only a pointer to the decision the owner made. A non-routed decision
    notifies nobody (AC-15: logging a complaint never notifies a manager).
    """
    if not complaint.routed_to_id or complaint.routed_to_id == actor.id:
        return
    try:
        notification_service.notify(
            db,
            recipient_ids=[complaint.routed_to_id],
            type=NotificationType.SYSTEM.value,
            priority=NotificationPriority.HIGH.value,
            title_ar="إحالة من المالك",
            title_en="Referred by the owner",
            message_ar="أحال إليك المالك شكوى للمعالجة.",
            message_en="The owner referred a complaint to you for handling.",
            entity_type="complaint",
            entity_id=complaint.id,
            actor_user_id=actor.id,
            dedupe_key=f"complaint_routed:{complaint.id}:{complaint.routed_to_id}",
        )
    except Exception:  # noqa: BLE001 - a notification must never break the decision
        import logging

        logging.getLogger("safir.operations").exception("complaint route notification failed")


def list_complaints(db: Session, *, user: User) -> list[Complaint]:
    """Confidential listing: owner sees all, others only their own submissions.

    A non-owner never sees other people's complaints, and never sees one they
    only have a grant for in the list (they open it directly). This keeps the
    list itself from becoming a leak.
    """
    if confidential_access_service.is_confidential_owner(user):
        require_permission(user, Perm.COMPLAINT_DECIDE)
        return list(db.execute(
            select(Complaint).order_by(Complaint.created_at.desc())
        ).scalars())
    require_permission(user, Perm.COMPLAINT_READ_OWN)
    return list(db.execute(
        select(Complaint).where(Complaint.submitted_by_id == user.id)
        .order_by(Complaint.created_at.desc())
    ).scalars())


def get_complaint(db: Session, *, user: User, complaint_id: int) -> Complaint:
    complaint = db.get(Complaint, complaint_id)
    if complaint is None:
        raise NotFoundError("Complaint not found.")
    confidential_access_service.require_confidential_read(
        db, user=user, subject_type="complaint", subject_id=complaint.id,
        permission=Perm.COMPLAINT_DECIDE,
    )
    return complaint


def serialise_complaint(c: Complaint, *, include_identity: bool = True) -> dict:
    data = {
        "id": c.id, "company_id": c.company_id, "subject": c.subject, "body": c.body,
        "status": c.status, "is_anonymous": c.is_anonymous, "decision": c.decision,
        "decided_by_id": c.decided_by_id, "decided_at": c.decided_at,
        "routed_to_id": c.routed_to_id, "created_at": c.created_at,
    }
    if include_identity and not c.is_anonymous:
        data["submitted_by_id"] = c.submitted_by_id
    return data


# --------------------------------------------------------------------------
# advisors (D04)
# --------------------------------------------------------------------------
def assign_advisor(db: Session, *, user: User, company_id: int, advisor_user_id: int,
                   specialty: str | None = None, ip_address: str | None = None,
                   user_agent: str | None = None) -> AdvisorAssignment:
    require_permission(user, Perm.ADVISOR_MANAGE)
    require_company_access(user, company_id, write=True)
    assignment = AdvisorAssignment(company_id=company_id, advisor_user_id=advisor_user_id,
                                   specialty=specialty, is_active=True, assigned_by_id=user.id)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    audit_service.record(db, action=AuditAction.ADVISOR_ASSIGNED, actor_user_id=user.id,
                         entity_type="advisor_assignment", entity_id=assignment.id,
                         company_id=company_id, ip_address=ip_address, user_agent=user_agent)
    return assignment


def record_session(db: Session, *, user: User, company_id: int, advisor_user_id: int,
                   scheduled_at=None, topic: str | None = None, notes: str | None = None,
                   recommendations: str | None = None, status: str = AdvisorSessionStatus.SCHEDULED.value,
                   ip_address: str | None = None, user_agent: str | None = None) -> AdvisorySession:
    require_permission(user, Perm.ADVISOR_SESSION_RECORD)
    require_company_access(user, company_id, write=True)
    # An external consultant may only record their own sessions.
    from backend.db.models.enums import RoleCode

    if user.role_code == RoleCode.EXTERNAL_CONSULTANT.value and user.id != advisor_user_id:
        from backend.core.errors import PermissionDeniedError

        raise PermissionDeniedError("You may only record your own sessions.")
    session = AdvisorySession(company_id=company_id, advisor_user_id=advisor_user_id,
                              scheduled_at=scheduled_at, status=status, topic=topic,
                              notes=notes, recommendations=recommendations,
                              recorded_by_id=user.id)
    db.add(session)
    db.commit()
    db.refresh(session)
    audit_service.record(db, action=AuditAction.ADVISORY_SESSION_RECORDED,
                         actor_user_id=user.id, entity_type="advisory_session",
                         entity_id=session.id, company_id=company_id,
                         ip_address=ip_address, user_agent=user_agent)
    return session


def list_advisor_assignments(db: Session, *, user: User, company_id: int | None = None) -> list[AdvisorAssignment]:
    require_permission(user, Perm.ADVISOR_READ)
    stmt = select(AdvisorAssignment).order_by(AdvisorAssignment.created_at.desc())
    allowed = accessible_company_ids(user)
    if allowed is not None:
        stmt = stmt.where(AdvisorAssignment.company_id.in_(allowed)) if allowed else stmt.where(False)
    if company_id is not None:
        stmt = stmt.where(AdvisorAssignment.company_id == company_id)
    return list(db.execute(stmt).scalars())


def serialise_assignment(a: AdvisorAssignment) -> dict:
    return {
        "id": a.id, "company_id": a.company_id, "advisor_user_id": a.advisor_user_id,
        "specialty": a.specialty, "is_active": a.is_active,
        "assigned_by_id": a.assigned_by_id, "created_at": a.created_at,
    }


def list_sessions(db: Session, *, user: User, company_id: int | None = None) -> list[AdvisorySession]:
    from backend.db.models.enums import RoleCode

    stmt = select(AdvisorySession).order_by(AdvisorySession.created_at.desc())
    if user.role_code == RoleCode.EXTERNAL_CONSULTANT.value:
        # An external consultant sees only their own sessions (D04).
        stmt = stmt.where(AdvisorySession.advisor_user_id == user.id)
    else:
        require_permission(user, Perm.ADVISOR_READ)
        allowed = accessible_company_ids(user)
        if allowed is not None:
            stmt = stmt.where(AdvisorySession.company_id.in_(allowed)) if allowed else stmt.where(False)
    if company_id is not None:
        stmt = stmt.where(AdvisorySession.company_id == company_id)
    return list(db.execute(stmt).scalars())


def serialise_session(s: AdvisorySession) -> dict:
    # ``advisor`` display names back the deck's "مسند إليه" filter and the
    # session row (slide 136); without them the list could only show a bare id.
    advisor = s.advisor
    return {
        "id": s.id, "company_id": s.company_id, "advisor_user_id": s.advisor_user_id,
        "advisor_name_ar": advisor.full_name_ar if advisor else None,
        "advisor_name_en": advisor.full_name_en if advisor else None,
        "scheduled_at": s.scheduled_at, "status": s.status, "topic": s.topic,
        "notes": s.notes, "recommendations": s.recommendations,
        "recorded_by_id": s.recorded_by_id, "created_at": s.created_at,
    }


# --------------------------------------------------------------------------
# advisor monthly reports (S19)
# --------------------------------------------------------------------------
def _advisor_report_period(period_year: int, period_month: int) -> None:
    if not (1 <= period_month <= 12):
        raise ValidationError("Period month must be between 1 and 12.")


def save_advisor_report(
    db: Session, *, user: User, company_id: int, advisor_user_id: int,
    period_year: int, period_month: int, development: str | None = None,
    challenges: str | None = None, recommendations: str | None = None,
    ip_address: str | None = None, user_agent: str | None = None,
) -> AdvisorMonthlyReport:
    """Create or update the draft monthly report for one advisor/company/period.

    The report is keyed by (company, advisor, year, month) so re-saving updates
    the same draft rather than duplicating it. An external consultant may only
    write their own report.
    """
    from backend.db.models.enums import RoleCode

    require_permission(user, Perm.ADVISOR_SESSION_RECORD)
    require_company_access(user, company_id, write=True)
    _advisor_report_period(period_year, period_month)
    if user.role_code == RoleCode.EXTERNAL_CONSULTANT.value and user.id != advisor_user_id:
        from backend.core.errors import PermissionDeniedError

        raise PermissionDeniedError("You may only write your own report.")

    report = db.execute(
        select(AdvisorMonthlyReport).where(
            AdvisorMonthlyReport.company_id == company_id,
            AdvisorMonthlyReport.advisor_user_id == advisor_user_id,
            AdvisorMonthlyReport.period_year == period_year,
            AdvisorMonthlyReport.period_month == period_month,
        )
    ).scalar_one_or_none()
    if report is None:
        report = AdvisorMonthlyReport(
            company_id=company_id, advisor_user_id=advisor_user_id,
            period_year=period_year, period_month=period_month,
            status=AdvisorReportStatus.DRAFT.value, created_by_id=user.id,
        )
        db.add(report)
    elif report.status == AdvisorReportStatus.SUBMITTED.value:
        raise ConflictError("A submitted report is immutable; create the next period instead.")

    report.development = development
    report.challenges = challenges
    report.recommendations = recommendations
    db.commit()
    db.refresh(report)

    audit_service.record(
        db, action=AuditAction.ADVISOR_REPORT_SAVED, actor_user_id=user.id,
        entity_type="advisor_monthly_report", entity_id=report.id, company_id=company_id,
        ip_address=ip_address, user_agent=user_agent,
    )
    return report


def submit_advisor_report(
    db: Session, *, user: User, report_id: int,
    ip_address: str | None = None, user_agent: str | None = None,
) -> AdvisorMonthlyReport:
    """Submit a draft report, freezing it as the original for development."""
    from backend.db.models.enums import RoleCode

    require_permission(user, Perm.ADVISOR_SESSION_RECORD)
    report = db.get(AdvisorMonthlyReport, report_id)
    if report is None:
        raise NotFoundError("Advisor report not found.")
    require_company_access(user, report.company_id, write=True)
    if user.role_code == RoleCode.EXTERNAL_CONSULTANT.value and user.id != report.advisor_user_id:
        from backend.core.errors import PermissionDeniedError

        raise PermissionDeniedError("You may only submit your own report.")
    if report.status == AdvisorReportStatus.SUBMITTED.value:
        raise ConflictError("This report has already been submitted.")

    report.status = AdvisorReportStatus.SUBMITTED.value
    report.submitted_at = utcnow()
    db.commit()
    db.refresh(report)

    audit_service.record(
        db, action=AuditAction.ADVISOR_REPORT_SUBMITTED, actor_user_id=user.id,
        entity_type="advisor_monthly_report", entity_id=report.id, company_id=report.company_id,
        ip_address=ip_address, user_agent=user_agent,
    )
    return report


def list_advisor_reports(
    db: Session, *, user: User, company_id: int | None = None,
    period_year: int | None = None, period_month: int | None = None,
) -> list[AdvisorMonthlyReport]:
    from backend.db.models.enums import RoleCode

    stmt = select(AdvisorMonthlyReport).order_by(
        AdvisorMonthlyReport.period_year.desc(),
        AdvisorMonthlyReport.period_month.desc(),
        AdvisorMonthlyReport.id.desc(),
    )
    if user.role_code == RoleCode.EXTERNAL_CONSULTANT.value:
        stmt = stmt.where(AdvisorMonthlyReport.advisor_user_id == user.id)
    else:
        require_permission(user, Perm.ADVISOR_READ)
        allowed = accessible_company_ids(user)
        if allowed is not None:
            stmt = stmt.where(AdvisorMonthlyReport.company_id.in_(allowed)) if allowed else stmt.where(False)
    if company_id is not None:
        stmt = stmt.where(AdvisorMonthlyReport.company_id == company_id)
    if period_year is not None:
        stmt = stmt.where(AdvisorMonthlyReport.period_year == period_year)
    if period_month is not None:
        stmt = stmt.where(AdvisorMonthlyReport.period_month == period_month)
    return list(db.execute(stmt).scalars())


def serialise_advisor_report(r: AdvisorMonthlyReport) -> dict:
    return {
        "id": r.id, "company_id": r.company_id, "advisor_user_id": r.advisor_user_id,
        "period_year": r.period_year, "period_month": r.period_month,
        "development": r.development, "challenges": r.challenges,
        "recommendations": r.recommendations, "status": r.status,
        "submitted_at": r.submitted_at, "created_by_id": r.created_by_id,
        "created_at": r.created_at,
    }


# --------------------------------------------------------------------------
# owner decisions (D07)
# --------------------------------------------------------------------------
def create_owner_decision(
    db: Session, *, user: User, number: str, title: str, company_id: int | None = None,
    body: str | None = None, executor_user_id: int | None = None, due_date=None,
    ip_address: str | None = None, user_agent: str | None = None,
) -> OwnerDecision:
    require_permission(user, Perm.OWNER_DECISION_MANAGE)
    decision = OwnerDecision(number=number, company_id=company_id, title=title.strip(),
                             body=body, executor_user_id=executor_user_id, due_date=due_date,
                             status=OwnerDecisionStatus.OPEN.value, created_by_id=user.id,
                             decided_at=utcnow())
    db.add(decision)
    db.commit()
    db.refresh(decision)
    audit_service.record(db, action=AuditAction.OWNER_DECISION_CREATED, actor_user_id=user.id,
                         entity_type="owner_decision", entity_id=decision.id,
                         company_id=company_id, ip_address=ip_address, user_agent=user_agent)
    return decision


def update_owner_decision(
    db: Session, *, user: User, decision_id: int, new_status: str | None = None,
    follow_up_note: str | None = None, ip_address: str | None = None,
    user_agent: str | None = None,
) -> OwnerDecision:
    require_permission(user, Perm.OWNER_DECISION_MANAGE)
    decision = db.get(OwnerDecision, decision_id)
    if decision is None:
        raise NotFoundError("Owner decision not found.")
    if new_status is not None:
        decision.status = new_status
    if follow_up_note is not None:
        decision.follow_up_note = follow_up_note
    db.add(decision)
    db.add(OwnerDecisionEvent(decision_id=decision.id, status=new_status,
                              note=follow_up_note, actor_id=user.id))
    db.commit()
    db.refresh(decision)
    audit_service.record(db, action=AuditAction.OWNER_DECISION_UPDATED, actor_user_id=user.id,
                         entity_type="owner_decision", entity_id=decision.id,
                         company_id=decision.company_id, ip_address=ip_address,
                         user_agent=user_agent)
    return decision


def respond_to_owner_decision(
    db: Session, *, user: User, decision_id: int, note: str,
    ip_address: str | None = None, user_agent: str | None = None,
) -> OwnerDecision:
    """S22: the named executor (e.g. a subsidiary manager) replies to a directive.

    The owner *issues* a decision or directive; the person it names responds with
    an execution update. A response is deliberately narrower than an owner edit:
    it records a follow-up note and can move an ``open`` decision to
    ``in_progress``, but it can never mark it ``done`` or ``cancelled`` -- only
    the owner closes a decision. A response never widens the audience, so the
    owner is notified of the reply.
    """
    require_permission(user, Perm.OWNER_DECISION_READ)
    decision = db.get(OwnerDecision, decision_id)
    if decision is None:
        raise NotFoundError("Owner decision not found.")
    if decision.executor_user_id != user.id:
        # "Not yours" and "does not exist" are the same answer (isolation rule).
        raise NotFoundError("Owner decision not found.")
    if decision.company_id is not None:
        require_company_access(user, decision.company_id, write=True)

    text = (note or "").strip()
    if not text:
        raise ValidationError("A response note is required.")

    if decision.status == OwnerDecisionStatus.OPEN.value:
        decision.status = OwnerDecisionStatus.IN_PROGRESS.value
    db.add(decision)
    db.add(OwnerDecisionEvent(decision_id=decision.id, status=decision.status,
                              note=text, actor_id=user.id))
    db.commit()
    db.refresh(decision)

    audit_service.record(db, action=AuditAction.OWNER_DECISION_RESPONDED,
                         actor_user_id=user.id, entity_type="owner_decision",
                         entity_id=decision.id, company_id=decision.company_id,
                         ip_address=ip_address, user_agent=user_agent)
    _notify_decision_response(db, decision=decision, actor=user, note=text)
    return decision


def _notify_decision_response(
    db: Session, *, decision: OwnerDecision, actor: User, note: str
) -> None:
    """Tell the issuer (the owner) that the named executor replied."""
    recipient = decision.created_by_id
    if not recipient or recipient == actor.id:
        return
    try:
        notification_service.notify(
            db,
            recipient_ids=[recipient],
            type=NotificationType.SYSTEM.value,
            priority=NotificationPriority.NORMAL.value,
            title_ar="رد على توجيه",
            title_en="Reply to a directive",
            message_ar=f"ردّ المعني على «{decision.title}»: {note[:120]}",
            message_en=f"The assignee replied on “{decision.title}”: {note[:120]}",
            entity_type="owner_decision",
            entity_id=decision.id,
            actor_user_id=actor.id,
            dedupe_key=None,
        )
    except Exception:  # noqa: BLE001 - a notification must never break the reply
        import logging

        logging.getLogger("safir.operations").exception("decision reply notification failed")


def list_owner_decisions(db: Session, *, user: User, company_id: int | None = None) -> list[OwnerDecision]:
    require_permission(user, Perm.OWNER_DECISION_READ)
    stmt = select(OwnerDecision).order_by(OwnerDecision.created_at.desc())
    allowed = accessible_company_ids(user)
    if allowed is not None:
        # A scoped user sees group-wide decisions (company_id NULL) plus their
        # own companies' decisions.
        stmt = stmt.where(
            (OwnerDecision.company_id.is_(None)) | (OwnerDecision.company_id.in_(allowed))
        )
    if company_id is not None:
        stmt = stmt.where(OwnerDecision.company_id == company_id)
    return list(db.execute(stmt).scalars())


def serialise_owner_decision(d: OwnerDecision) -> dict:
    # ``executor`` display names back the deck's "مسؤول" filter (slide 135) and
    # the executor picker on the decisions list.
    executor = d.executor
    return {
        "id": d.id, "number": d.number, "company_id": d.company_id, "title": d.title,
        "body": d.body, "status": d.status, "executor_user_id": d.executor_user_id,
        "executor_name_ar": executor.full_name_ar if executor else None,
        "executor_name_en": executor.full_name_en if executor else None,
        "due_date": d.due_date, "follow_up_note": d.follow_up_note,
        "created_by_id": d.created_by_id, "decided_at": d.decided_at,
        "created_at": d.created_at,
        "history": [
            {"status": e.status, "note": e.note, "actor_id": e.actor_id,
             "created_at": e.created_at}
            for e in sorted(d.history, key=lambda x: x.created_at)
        ],
    }


# --------------------------------------------------------------------------
# projects & opportunities (S20)
# --------------------------------------------------------------------------
def _validate_project_period(period_start, period_end) -> None:
    if period_start is not None and period_end is not None and period_end < period_start:
        raise ValidationError("The follow-up period end cannot precede its start.")


def create_project_record(
    db: Session, *, user: User, name: str, record_type: str = "opportunity",
    company_id: int | None = None, description: str | None = None,
    objective: str | None = None, period_start=None, period_end=None,
    results: str | None = None, resource_estimate: str | None = None,
    estimated_value=None, currency: str = "SAR", status: str = "open",
    owner_decision_id: int | None = None,
    stage: str | None = None, market_customers: str | None = None,
    information_source: str | None = None, expected_revenue: str | None = None,
    key_risks: str | None = None, alternatives: str | None = None,
    recommendation: str | None = None, study_sources: str | None = None,
    ip_address: str | None = None, user_agent: str | None = None,
) -> ProjectRecord:
    require_permission(user, Perm.PROJECT_MANAGE)
    if company_id is not None:
        require_company_access(user, company_id, write=True)
    if record_type not in {t.value for t in ProjectRecordType}:
        raise ValidationError("Unknown record type.")
    if stage is not None and stage not in {s.value for s in ProjectStage}:
        raise ValidationError("Unknown opportunity stage.")
    _validate_project_period(period_start, period_end)

    record = ProjectRecord(
        record_type=record_type,
        name=name.strip(),
        company_id=company_id,
        description=description,
        objective=objective,
        period_start=period_start,
        period_end=period_end,
        results=results,
        resource_estimate=resource_estimate,
        estimated_value=estimated_value,
        currency=currency or "SAR",
        status=status,
        owner_decision_id=owner_decision_id,
        stage=stage,
        market_customers=market_customers,
        information_source=information_source,
        expected_revenue=expected_revenue,
        key_risks=key_risks,
        alternatives=alternatives,
        recommendation=recommendation,
        study_sources=study_sources,
        created_by_id=user.id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    audit_service.record(
        db, action=AuditAction.PROJECT_RECORD_CREATED, actor_user_id=user.id,
        entity_type="project_record", entity_id=record.id, company_id=company_id,
        ip_address=ip_address, user_agent=user_agent,
    )
    return record


def raise_project_to_owner(
    db: Session, *, user: User, record_id: int,
    ip_address: str | None = None, user_agent: str | None = None,
) -> ProjectRecord:
    """Deck slide 26 [رفع للمالك عند الحاجة] / spec §7 Table 21 "رفع للمالك".

    An opportunity the BD manager cannot decide within its own authority is
    raised as an owner *decision topic*. The deck is explicit about the shape:
    a topic is opened for the owner, and the record is linked to the decision it
    produced (AC-20 "السجل يربط بالقرار نفسه").

    The decision is created ``open`` with no executor -- the owner assigns one
    when issuing the actual decision -- and the record's ``owner_decision_id``
    points at it, so the two stay joined. This is deliberately *not* an approval
    chain: nothing is blocked, and the owner may still decide informally.
    """
    require_permission(user, Perm.PROJECT_MANAGE)
    record = db.get(ProjectRecord, record_id)
    if record is None:
        raise NotFoundError("Project or opportunity not found.")
    if record.company_id is not None:
        require_company_access(user, record.company_id, write=True)

    decision = OwnerDecision(
        number=f"OPP-{record.id}",
        company_id=record.company_id,
        title=record.name,
        body=record.recommendation or record.objective or record.description,
        status=OwnerDecisionStatus.OPEN.value,
        created_by_id=user.id,
        decided_at=utcnow(),
    )
    db.add(decision)
    db.flush()
    record.owner_decision_id = decision.id
    db.add(record)
    db.commit()
    db.refresh(record)

    audit_service.record(
        db, action=AuditAction.OWNER_DECISION_CREATED, actor_user_id=user.id,
        entity_type="owner_decision", entity_id=decision.id,
        company_id=record.company_id, ip_address=ip_address, user_agent=user_agent,
        metadata={"raised_from": "project_record", "project_record_id": record.id},
    )
    notification_service.notify(
        db,
        recipient_ids=_owner_recipient_ids(db),
        type=NotificationType.SYSTEM.value,
        title_ar="موضوع مرفوع من تطوير الأعمال",
        title_en="Topic raised by Business Development",
        message_ar=f"رفع تطوير الأعمال «{record.name}» لموضوع قرار.",
        message_en=f"Business Development raised “{record.name}” as a decision topic.",
        priority=NotificationPriority.HIGH.value,
        entity_type="owner_decision", entity_id=decision.id,
        company_id=record.company_id,
        actor_user_id=user.id,
    )
    return record


def update_project_record(
    db: Session, *, user: User, record_id: int, changes: dict,
    ip_address: str | None = None, user_agent: str | None = None,
) -> ProjectRecord:
    require_permission(user, Perm.PROJECT_MANAGE)
    record = db.get(ProjectRecord, record_id)
    if record is None:
        raise NotFoundError("Project or opportunity not found.")

    # The *current* company must be writable, otherwise a user scoped to one
    # company could edit a record that belongs to another.
    if record.company_id is not None:
        require_company_access(user, record.company_id, write=True)
    # A change of company must be authorized against the *target* company too.
    if "company_id" in changes and changes["company_id"] is not None:
        require_company_access(user, changes["company_id"], write=True)

    if "record_type" in changes and changes["record_type"] is not None:
        if changes["record_type"] not in {t.value for t in ProjectRecordType}:
            raise ValidationError("Unknown record type.")

    if changes.get("stage") is not None:
        if changes["stage"] not in {s.value for s in ProjectStage}:
            raise ValidationError("Unknown opportunity stage.")

    period_start = changes.get("period_start", record.period_start)
    period_end = changes.get("period_end", record.period_end)
    _validate_project_period(period_start, period_end)

    for field, value in changes.items():
        if value is None:
            continue
        setattr(record, field, value)
    db.add(record)
    db.commit()
    db.refresh(record)
    audit_service.record(
        db, action=AuditAction.PROJECT_RECORD_UPDATED, actor_user_id=user.id,
        entity_type="project_record", entity_id=record.id, company_id=record.company_id,
        ip_address=ip_address, user_agent=user_agent,
    )
    return record


def list_project_records(
    db: Session, *, user: User, company_id: int | None = None,
    record_type: str | None = None, status: str | None = None,
) -> list[ProjectRecord]:
    require_permission(user, Perm.PROJECT_READ)
    stmt = select(ProjectRecord).order_by(ProjectRecord.created_at.desc())
    allowed = accessible_company_ids(user)
    if allowed is not None:
        # A scoped reader sees group-wide records (company_id NULL) plus its own
        # companies' records, mirroring the owner-decision visibility rule.
        stmt = stmt.where(
            (ProjectRecord.company_id.is_(None)) | (ProjectRecord.company_id.in_(allowed))
        )
    if company_id is not None:
        stmt = stmt.where(ProjectRecord.company_id == company_id)
    if record_type is not None:
        stmt = stmt.where(ProjectRecord.record_type == record_type)
    if status is not None:
        stmt = stmt.where(ProjectRecord.status == status)
    return list(db.execute(stmt).scalars())


def get_project_record(db: Session, *, user: User, record_id: int) -> ProjectRecord:
    require_permission(user, Perm.PROJECT_READ)
    # Scope the lookup rather than fetching then checking: an out-of-scope record
    # then returns the same "not found" as a genuinely missing id, so a scoped
    # user probing ids cannot tell which ones exist.
    stmt = select(ProjectRecord).where(ProjectRecord.id == record_id)
    allowed = accessible_company_ids(user)
    if allowed is not None:
        stmt = stmt.where(
            (ProjectRecord.company_id.is_(None)) | (ProjectRecord.company_id.in_(allowed))
        )
    record = db.execute(stmt).scalar_one_or_none()
    if record is None:
        raise NotFoundError("Project or opportunity not found.")
    return record


def serialise_project_record(r: ProjectRecord) -> dict:
    return {
        "id": r.id, "record_type": r.record_type, "name": r.name,
        "company_id": r.company_id, "description": r.description,
        "objective": r.objective, "period_start": r.period_start,
        "period_end": r.period_end, "results": r.results,
        "resource_estimate": r.resource_estimate,
        "estimated_value": r.estimated_value, "currency": r.currency,
        "status": r.status, "owner_decision_id": r.owner_decision_id,
        "stage": r.stage,
        "market_customers": r.market_customers,
        "information_source": r.information_source,
        "expected_revenue": r.expected_revenue,
        "key_risks": r.key_risks,
        "alternatives": r.alternatives,
        "recommendation": r.recommendation,
        "study_sources": r.study_sources,
        "created_by_id": r.created_by_id, "created_at": r.created_at,
    }


# --------------------------------------------------------------------------
# deck slide 46: the manager's smart-brief plan request
# --------------------------------------------------------------------------
def _bd_recipient_ids(db: Session) -> list[int]:
    """Active Business Development ids (the plan request's sole reader)."""
    return list(
        db.execute(
            select(User.id)
            .join(Role, Role.id == User.role_id)
            .where(
                User.is_active.is_(True),
                Role.code == RoleCode.BUSINESS_DEVELOPMENT.value,
            )
        ).scalars()
    )


def request_plan(
    db: Session, *, user: User, period_year: int, period_month: int,
    company_id: int | None = None,
    ip_address: str | None = None, user_agent: str | None = None,
) -> PlanRequest:
    """Deck slide 46 [نعم، اطلب خطة]: the manager asks BD for a plan.

    Only a company manager (of the company, or the owner acting for it) may
    raise the request, and only after the period's report is approved -- the
    brief itself only appears then. The request is a hand-off, never an approval
    chain: the AI's role ends at the summary, so BD answers the plan by hand.
    The stored summary/advice are rebuilt server-side from the approved report
    so a client cannot fabricate the figures.
    """
    require_permission(user, Perm.SUPPORT_CREATE)  # the manager's own capability
    target_company = company_id
    if target_company is None:
        permitted = user.permitted_company_ids
        if len(permitted) == 1:
            target_company = permitted[0]
    if target_company is None:
        raise ValidationError("A company is required to request a plan.")
    require_company_access(user, target_company, write=False)
    _validate_brief_period(period_year, period_month)

    report = db.execute(
        select(MonthlyReport).where(
            MonthlyReport.company_id == target_company,
            MonthlyReport.period_year == period_year,
            MonthlyReport.period_month == period_month,
            MonthlyReport.is_live.is_(True),
        )
    ).scalar_one_or_none()
    if report is None:
        raise ValidationError("No report exists for this company and period.")
    if report.approval_status != ReportApprovalStatus.APPROVED.value:
        raise ValidationError("The report must be approved before a plan can be requested.")

    summary, advice = _smart_brief_text(report)
    # One open request per company/period: re-asking just returns the existing
    # row rather than piling up duplicates for BD.
    existing = db.execute(
        select(PlanRequest).where(
            PlanRequest.company_id == target_company,
            PlanRequest.period_year == period_year,
            PlanRequest.period_month == period_month,
            PlanRequest.status == PlanRequestStatus.REQUESTED.value,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    request = PlanRequest(
        company_id=target_company,
        period_year=period_year,
        period_month=period_month,
        summary=summary,
        advice=advice,
        status=PlanRequestStatus.REQUESTED.value,
        requested_by_id=user.id,
    )
    db.add(request)
    db.commit()
    db.refresh(request)

    audit_service.record(
        db, action=AuditAction.PLAN_REQUEST_CREATED, actor_user_id=user.id,
        entity_type="plan_request", entity_id=request.id, company_id=target_company,
        ip_address=ip_address, user_agent=user_agent,
    )
    notification_service.notify(
        db,
        recipient_ids=_bd_recipient_ids(db),
        type=NotificationType.SYSTEM.value,
        title_ar="طلب خطة من مدير شركة",
        title_en="Plan requested by a company manager",
        message_ar=f"طلب مدير الشركة خطة للفترة {period_year}-{period_month:02d}.",
        message_en=f"A company manager requested a plan for {period_year}-{period_month:02d}.",
        priority=NotificationPriority.NORMAL.value,
        entity_type="plan_request", entity_id=request.id,
        company_id=target_company,
        actor_user_id=user.id,
    )
    return request


def _smart_brief_text(report: MonthlyReport) -> tuple[str, str]:
    """The one fact + one advice the manager's brief shows (deck slide 46).

    Deterministic, built from the approved report's own figures, so the brief
    can never cite a number the manager cannot already read. Returns
    ``(summary_ar, advice_ar)``.
    """
    revenue = report.revenue
    expenses = report.expenses
    net = report.net_result
    if net is None and revenue is not None and expenses is not None:
        net = revenue - expenses
    if net is not None and net < 0:
        summary = "نتيجة الشهر سالبة؛ راجعوا المصروفات."
    elif revenue is not None and expenses is not None and expenses > revenue:
        summary = "المصروفات تجاوزت الإيراد هذا الشهر."
    elif revenue is not None:
        summary = "الإيراد مسجل لهذا الشهر؛ استكملوا التحصيل."
    else:
        summary = "التقرير المعتمد متاح للمراجعة."

    if report.outstanding_receivables is not None and report.outstanding_receivables > 0:
        advice = "راجعوا المستحقات المتأخرة وحددوا موعد متابعة لكل منها."
    elif report.support_required:
        advice = f"تابعوا الدعم المطلوب: {report.support_required}"
    else:
        advice = "حافظوا على وتيرة الإيراد وراجعوا المصروفات المتكررة."
    return summary, advice


def list_plan_requests(
    db: Session, *, user: User, company_id: int | None = None,
    status: str | None = None,
) -> list[PlanRequest]:
    require_permission(user, Perm.PROJECT_READ)
    stmt = select(PlanRequest).order_by(PlanRequest.created_at.desc())
    allowed = accessible_company_ids(user)
    if allowed is not None:
        stmt = stmt.where(PlanRequest.company_id.in_(allowed))
    if company_id is not None:
        stmt = stmt.where(PlanRequest.company_id == company_id)
    if status is not None:
        stmt = stmt.where(PlanRequest.status == status)
    return list(db.execute(stmt).scalars())


def serialise_plan_request(r: PlanRequest) -> dict:
    return {
        "id": r.id, "company_id": r.company_id,
        "period_year": r.period_year, "period_month": r.period_month,
        "summary": r.summary, "advice": r.advice, "status": r.status,
        "requested_by_id": r.requested_by_id, "created_at": r.created_at,
    }


# --------------------------------------------------------------------------
# management reports: the BD five-axis brief (S21)
# --------------------------------------------------------------------------
# Spec §16 Table 71 / §9 S21: the brief's five axes are fixed by the
# specification; only the indicator *definitions* inside them are gated by D02,
# so the axes are free text and no metric is computed here.
BRIEF_AXIS_FIELDS = (
    "axis_companies",
    "axis_projects",
    "axis_employees",
    "axis_risks",
    "axis_decisions",
)
# A fixed output test requires the executive summary to fit within half a page.
MAX_BRIEF_SUMMARY_CHARS = 2000


def _owner_recipient_ids(db: Session) -> list[int]:
    """Active Holding Owner / superuser ids (the brief's sole reader)."""
    return list(
        db.execute(
            select(User.id)
            .join(Role, Role.id == User.role_id)
            .where(
                User.is_active.is_(True),
                (User.is_superuser.is_(True)) | (Role.code == RoleCode.HOLDING_OWNER.value),
            )
        ).scalars()
    )


def _validate_brief_period(period_year: int, period_month: int) -> None:
    if not (2000 <= period_year <= 2100):
        raise ValidationError("The period year must be between 2000 and 2100.")
    if not (1 <= period_month <= 12):
        raise ValidationError("The period month must be between 1 and 12.")


def save_management_brief(
    db: Session, *, user: User, period_year: int, period_month: int,
    executive_summary: str | None = None, axis_companies: str | None = None,
    axis_projects: str | None = None, axis_employees: str | None = None,
    axis_risks: str | None = None, axis_decisions: str | None = None,
    source_report_ids: list[int] | None = None, urgency: str | None = None,
    ip_address: str | None = None, user_agent: str | None = None,
) -> ManagementBrief:
    """Create or update the caller's draft brief for a period (S21).

    The brief is the author's own; ``created_by_id`` is set from the session and
    a caller never edits someone else's brief. The source reports are stored as
    ids only -- the originals are never copied or modified.
    """
    require_permission(user, Perm.MANAGEMENT_BRIEF_SUBMIT)
    _validate_brief_period(period_year, period_month)

    if executive_summary is not None and len(executive_summary) > MAX_BRIEF_SUMMARY_CHARS:
        raise ValidationError(
            f"The executive summary must not exceed {MAX_BRIEF_SUMMARY_CHARS} characters."
        )
    if urgency is not None and urgency not in {u.value for u in ManagementBriefUrgency}:
        raise ValidationError("Unknown brief urgency.")

    brief = db.execute(
        select(ManagementBrief).where(
            ManagementBrief.period_year == period_year,
            ManagementBrief.period_month == period_month,
            ManagementBrief.created_by_id == user.id,
        )
    ).scalar_one_or_none()
    created = brief is None
    if brief is None:
        brief = ManagementBrief(
            period_year=period_year, period_month=period_month, created_by_id=user.id
        )
        db.add(brief)

    for field, value in (
        ("executive_summary", executive_summary),
        ("axis_companies", axis_companies),
        ("axis_projects", axis_projects),
        ("axis_employees", axis_employees),
        ("axis_risks", axis_risks),
        ("axis_decisions", axis_decisions),
        ("urgency", urgency),
    ):
        if value is not None:
            setattr(brief, field, value)
    if source_report_ids is not None:
        brief.source_report_ids = ",".join(str(int(i)) for i in source_report_ids)

    db.add(brief)
    db.commit()
    db.refresh(brief)

    audit_service.record(
        db,
        action=AuditAction.MANAGEMENT_BRIEF_CREATED if created else AuditAction.MANAGEMENT_BRIEF_UPDATED,
        actor_user_id=user.id, entity_type="management_brief", entity_id=brief.id,
        ip_address=ip_address, user_agent=user_agent,
        metadata={"period": f"{period_year}-{period_month:02d}"},
    )
    return brief


def submit_management_brief(
    db: Session, *, user: User, brief_id: int,
    ip_address: str | None = None, user_agent: str | None = None,
) -> ManagementBrief:
    """Submit the caller's own brief to the owner (routine or urgent).

    An urgent escalation notifies the owner immediately; a routine monthly brief
    also notifies the owner, but the spec's point is that an urgent item never
    waits for month-end. The brief's author is the only one who may submit it.
    """
    require_permission(user, Perm.MANAGEMENT_BRIEF_SUBMIT)
    brief = db.get(ManagementBrief, brief_id)
    if brief is None or brief.created_by_id != user.id:
        raise NotFoundError("Management brief not found.")

    brief.status = ManagementBriefStatus.SUBMITTED.value
    brief.submitted_at = utcnow()
    db.add(brief)
    db.commit()
    db.refresh(brief)

    audit_service.record(
        db, action=AuditAction.MANAGEMENT_BRIEF_SUBMITTED, actor_user_id=user.id,
        entity_type="management_brief", entity_id=brief.id,
        ip_address=ip_address, user_agent=user_agent,
        metadata={"urgency": brief.urgency},
    )

    urgent = brief.urgency == ManagementBriefUrgency.URGENT.value
    notification_service.notify(
        db,
        recipient_ids=_owner_recipient_ids(db),
        type=NotificationType.SYSTEM.value,
        title_ar="تصعيد عاجل من تطوير الأعمال" if urgent else "تقرير تطوير الأعمال الشهري",
        title_en="Urgent escalation from Business Development" if urgent else "Monthly Business Development brief",
        message_ar=(
            f"موجز {brief.period_month}/{brief.period_year} "
            + ("عاجل بانتظار قرارك." if urgent else "أُرسل للاطلاع.")
        ),
        message_en=(
            f"The {brief.period_month}/{brief.period_year} brief "
            + ("is urgent and awaits your decision." if urgent else "was submitted for review.")
        ),
        priority=NotificationPriority.HIGH.value if urgent else NotificationPriority.NORMAL.value,
        entity_type="management_brief", entity_id=brief.id,
        actor_user_id=user.id,
    )
    return brief


def list_management_briefs(
    db: Session, *, user: User, period_year: int | None = None,
    period_month: int | None = None,
) -> list[ManagementBrief]:
    require_permission(user, Perm.MANAGEMENT_BRIEF_READ)
    stmt = select(ManagementBrief).order_by(
        ManagementBrief.period_year.desc(), ManagementBrief.period_month.desc()
    )
    # An author (BD) sees only their own briefs; the owner reads every brief and
    # the accountant reads as a holding-level reviewer. A user who can author but
    # is not the owner is treated as an author, so one BD never reads another's
    # draft. A reader without the author permission always sees the full set.
    owner_codes = {RoleCode.HOLDING_OWNER.value, RoleCode.SUPER_ADMIN.value}
    author_only = (
        has_any_permission(user, Perm.MANAGEMENT_BRIEF_SUBMIT)
        and user.role_code not in owner_codes
    )
    if author_only:
        stmt = stmt.where(ManagementBrief.created_by_id == user.id)
    if period_year is not None:
        stmt = stmt.where(ManagementBrief.period_year == period_year)
    if period_month is not None:
        stmt = stmt.where(ManagementBrief.period_month == period_month)
    return list(db.execute(stmt).scalars())


def serialise_management_brief(b: ManagementBrief) -> dict:
    return {
        "id": b.id, "period_year": b.period_year, "period_month": b.period_month,
        "status": b.status, "urgency": b.urgency,
        "executive_summary": b.executive_summary,
        "axis_companies": b.axis_companies, "axis_projects": b.axis_projects,
        "axis_employees": b.axis_employees, "axis_risks": b.axis_risks,
        "axis_decisions": b.axis_decisions,
        "source_report_ids": [
            int(x) for x in (b.source_report_ids or "").split(",") if x.strip()
        ],
        "submitted_at": b.submitted_at, "created_by_id": b.created_by_id,
        "created_at": b.created_at,
    }
