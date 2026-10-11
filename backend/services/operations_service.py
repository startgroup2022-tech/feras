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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.errors import ConflictError, NotFoundError, ValidationError
from backend.db.base import utcnow
from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import (
    AdvisorSessionStatus,
    CampaignStatus,
    ComplaintStatus,
    OwnerDecisionStatus,
    TaskLifecycleStatus,
    WeeklyReportStatus,
)
from backend.db.models.identity import User
from backend.db.models.operations import (
    WEEKLY_REPORT_MAX_QUESTIONS,
    AdvisorAssignment,
    AdvisorySession,
    Campaign,
    Complaint,
    OwnerDecision,
    OwnerDecisionEvent,
    Task,
    TaskEvent,
    WeeklyReport,
    WeeklyReportAnswer,
    WeeklyReportQuestion,
)
from backend.rbac.authorization import (
    accessible_company_ids,
    has_any_permission,
    require_company_access,
    require_permission,
)
from backend.rbac.permissions import Perm
from backend.services import audit_service, confidential_access_service

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
    status: str | None = None, mine: bool = False,
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
    return list(db.execute(stmt).scalars())


def _get_task(db: Session, *, user: User, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise NotFoundError("Task not found.")
    require_company_access(user, task.company_id)
    return task


def serialise_task(task: Task) -> dict:
    return {
        "id": task.id, "company_id": task.company_id, "title": task.title,
        "description": task.description, "status": task.status, "priority": task.priority,
        "progress_percent": task.progress_percent, "due_date": task.due_date,
        "created_by_id": task.created_by_id, "assignee_id": task.assignee_id,
        "reviewer_id": task.reviewer_id, "completed_at": task.completed_at,
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
    require_permission(user, Perm.WEEKLY_REPORT_READ_OWN)
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


def serialise_campaign(c: Campaign) -> dict:
    return {
        "id": c.id, "company_id": c.company_id, "name": c.name, "platform": c.platform,
        "goal": c.goal, "start_date": c.start_date, "end_date": c.end_date,
        "budget": c.budget, "spend": c.spend, "currency": c.currency,
        "lead_count": c.lead_count, "conversion_count": c.conversion_count,
        "status": c.status, "manager_note": c.manager_note, "marketing_note": c.marketing_note,
        "created_at": c.created_at,
    }


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
    return complaint


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
    return {
        "id": s.id, "company_id": s.company_id, "advisor_user_id": s.advisor_user_id,
        "scheduled_at": s.scheduled_at, "status": s.status, "topic": s.topic,
        "notes": s.notes, "recommendations": s.recommendations,
        "recorded_by_id": s.recorded_by_id, "created_at": s.created_at,
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
    return {
        "id": d.id, "number": d.number, "company_id": d.company_id, "title": d.title,
        "body": d.body, "status": d.status, "executor_user_id": d.executor_user_id,
        "due_date": d.due_date, "follow_up_note": d.follow_up_note,
        "created_by_id": d.created_by_id, "decided_at": d.decided_at,
        "created_at": d.created_at,
        "history": [
            {"status": e.status, "note": e.note, "actor_id": e.actor_id,
             "created_at": e.created_at}
            for e in sorted(d.history, key=lambda x: x.created_at)
        ],
    }
