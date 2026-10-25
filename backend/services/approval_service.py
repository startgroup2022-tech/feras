"""Approval engine.

Executes a published workflow against a submission. The engine guarantees:

* **Authorization** -- a user may act only on a *pending task assigned to them*
  (or, for holding-wide read-all users, may view but not act). Knowing an id is
  never enough: the task is resolved from the caller's identity.
* **Concurrency safety** -- acting on a task is a conditional UPDATE
  (``WHERE status = 'pending'``); if the row was already advanced by another
  approver, ``rowcount`` is 0 and the call is rejected with a conflict. Two
  simultaneous approvals cannot advance the workflow twice.
* **Self-approval policy** -- by default the submitter is not asked to approve
  their own request; such a step is recorded as skipped and the chain advances.
  A step may opt in via ``assignment_config.allow_self_approval``.
* **Immutable history** -- every action writes an :class:`ApprovalEvent`; rows
  are only ever inserted.
"""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from backend.core.errors import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from backend.db.base import utcnow
from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import (
    ApprovalDecision,
    SubmissionStatus,
    TaskStatus,
    WorkflowStatus,
)
from backend.db.models.identity import User
from backend.db.models.submissions import FormSubmission
from backend.db.models.workflows import (
    ApprovalEvent,
    ApprovalTask,
    WorkflowInstance,
    WorkflowStep,
    WorkflowVersion,
)
from backend.rbac.authorization import require_permission
from backend.rbac.permissions import Perm
from backend.services import audit_service, workflow_service


# --------------------------------------------------------------------------
# serialisation
# --------------------------------------------------------------------------
def serialise_instance(db: Session, instance: WorkflowInstance) -> dict:
    version = db.get(WorkflowVersion, instance.workflow_version_id)
    tasks = [
        _serialise_task(db, t)
        for t in db.execute(
            select(ApprovalTask)
            .where(ApprovalTask.instance_id == instance.id)
            .order_by(ApprovalTask.step_order, ApprovalTask.id)
        ).scalars()
    ]
    events = [
        _serialise_event(db, e)
        for e in db.execute(
            select(ApprovalEvent)
            .where(ApprovalEvent.instance_id == instance.id)
            .order_by(ApprovalEvent.id)
        ).scalars()
    ]
    return {
        "id": instance.id,
        "submission_id": instance.submission_id,
        "workflow_definition_id": instance.workflow_definition_id,
        "workflow_version_id": instance.workflow_version_id,
        "company_id": instance.company_id,
        "current_step_id": instance.current_step_id,
        "status": instance.status,
        "started_at": instance.started_at,
        "completed_at": instance.completed_at,
        "version_number": version.version_number if version else None,
        "tasks": tasks,
        "events": events,
    }


def _serialise_task(db: Session, task: ApprovalTask) -> dict:
    step = db.get(WorkflowStep, task.step_id)
    assignee = db.get(User, task.assignee_id) if task.assignee_id else None
    return {
        "id": task.id,
        "instance_id": task.instance_id,
        "submission_id": task.instance.submission_id if task.instance else None,
        "step_id": task.step_id,
        "step_order": task.step_order,
        "step_name_ar": step.name_ar if step else None,
        "step_name_en": step.name_en if step else None,
        "assignee_id": task.assignee_id,
        "assignee_name_ar": assignee.full_name_ar if assignee else None,
        "assignee_name_en": assignee.full_name_en if assignee else None,
        "status": task.status,
        "acted_at": task.acted_at,
        "comment": task.comment,
    }


def _serialise_event(db: Session, event: ApprovalEvent) -> dict:
    actor = db.get(User, event.actor_user_id) if event.actor_user_id else None
    step = db.get(WorkflowStep, event.step_id) if event.step_id else None
    return {
        "id": event.id,
        "action": event.action,
        "actor_user_id": event.actor_user_id,
        "actor_name_ar": actor.full_name_ar if actor else None,
        "actor_name_en": actor.full_name_en if actor else None,
        "step_id": event.step_id,
        "step_name_ar": step.name_ar if step else None,
        "step_name_en": step.name_en if step else None,
        "comment": event.comment,
        "from_status": event.from_status,
        "to_status": event.to_status,
        "created_at": event.created_at,
    }


# --------------------------------------------------------------------------
# instance lifecycle
# --------------------------------------------------------------------------
def start_instance(
    db: Session,
    *,
    submission: FormSubmission,
    workflow_version: WorkflowVersion,
    actor: User,
    ip_address: str | None = None,
    user_agent: str | None = None,
    commit: bool = True,
) -> WorkflowInstance:
    """Create a workflow instance and open the first step's tasks."""
    steps = sorted(workflow_version.steps, key=lambda s: s.display_order)
    if not steps:
        raise ConflictError("The workflow has no steps.")

    instance = WorkflowInstance(
        submission_id=submission.id,
        workflow_definition_id=workflow_version.definition_id,
        workflow_version_id=workflow_version.id,
        company_id=submission.company_id,
        status=SubmissionStatus.IN_REVIEW.value,
        started_at=utcnow(),
    )
    db.add(instance)
    db.flush()

    submission.status = SubmissionStatus.IN_REVIEW.value
    db.add(submission)

    _write_event(
        db,
        instance=instance,
        submission=submission,
        action="started",
        actor_id=actor.id,
        step_id=None,
        comment=None,
        from_status=SubmissionStatus.SUBMITTED.value,
        to_status=SubmissionStatus.IN_REVIEW.value,
    )

    _open_step(db, instance=instance, submission=submission, step=steps[0])
    # A step whose only candidate is the submitter may be skipped immediately,
    # which can cascade; resolve the chain until a real task exists or it ends.
    _advance_past_skipped(db, instance=instance, submission=submission)

    if commit:
        db.commit()
        db.refresh(instance)

    audit_service.record(
        db,
        action=AuditAction.WORKFLOW_INSTANCE_STARTED,
        actor_user_id=actor.id,
        entity_type="workflow_instance",
        entity_id=instance.id,
        company_id=submission.company_id,
        metadata={"workflow_version_id": workflow_version.id},
        ip_address=ip_address,
        user_agent=user_agent,
        commit=commit,
    )
    return instance


def _open_step(
    db: Session, *, instance: WorkflowInstance, submission: FormSubmission, step: WorkflowStep
) -> None:
    instance.current_step_id = step.id
    db.add(instance)
    db.flush()

    submitter = db.get(User, submission.submitted_by_id) if submission.submitted_by_id else None
    submitter_department_id = submission.department_id
    if submitter_department_id is None and submitter is not None:
        submitter_department_id = submitter.department_id

    assignee_ids = workflow_service.resolve_assignees(
        db,
        step,
        submission_company_id=submission.company_id,
        submitter_id=submission.submitted_by_id,
        submitter_department_id=submitter_department_id,
    )

    allow_self = bool((step.assignment_config or {}).get("allow_self_approval", False))
    if not allow_self and submission.submitted_by_id is not None:
        assignee_ids = [uid for uid in assignee_ids if uid != submission.submitted_by_id]

    if not assignee_ids:
        # Nothing to ask at this step: record it as skipped (not a silent
        # bypass -- the event makes the reason explicit).
        db.add(
            ApprovalTask(
                instance_id=instance.id,
                step_id=step.id,
                step_order=step.display_order,
                assignee_id=None,
                status=TaskStatus.SKIPPED.value,
                acted_at=utcnow(),
                comment="auto-skipped: no eligible approver (self-approval policy)",
            )
        )
        db.flush()
        _write_event(
            db,
            instance=instance,
            submission=submission,
            action="step_skipped",
            actor_id=None,
            step_id=step.id,
            comment="No eligible approver",
            from_status=SubmissionStatus.IN_REVIEW.value,
            to_status=SubmissionStatus.IN_REVIEW.value,
        )
        return

    for assignee_id in assignee_ids:
        db.add(
            ApprovalTask(
                instance_id=instance.id,
                step_id=step.id,
                step_order=step.display_order,
                assignee_id=assignee_id,
                status=TaskStatus.PENDING.value,
            )
        )
    db.flush()

    # Tell each approver a request has landed in their queue. The notification
    # is written after the task rows exist; it never blocks the workflow.
    _notify_step_assignees(
        db,
        instance=instance,
        submission=submission,
        step=step,
        assignee_ids=assignee_ids,
    )


def _notify_step_assignees(
    db: Session,
    *,
    instance: WorkflowInstance,
    submission: FormSubmission,
    step: WorkflowStep,
    assignee_ids: list[int],
) -> None:
    from backend.services import notification_service

    try:
        notification_service.notify_approval_assigned(
            db,
            assignee_ids=assignee_ids,
            submission_id=submission.id,
            company_id=submission.company_id,
            title=submission.title or submission.reference,
            step_name_ar=step.name_ar,
            step_name_en=step.name_en,
            actor_user_id=submission.submitted_by_id,
        )
        _emit_request_event(db, "request.submitted", submission, {"step": step.key})
    except Exception:  # noqa: BLE001 - notifications are best-effort
        import logging

        logging.getLogger("safir.approvals").exception("approval notification failed")


def _emit_request_event(
    db: Session, event_type: str, submission: FormSubmission, extra: dict | None = None
) -> None:
    try:
        from backend.services import integration_service

        payload = {
            "submission_id": submission.id,
            "reference": submission.reference,
            "company_id": submission.company_id,
            "status": submission.status,
            "title": submission.title,
        }
        if extra:
            payload.update(extra)
        integration_service.emit(
            db, event_type=event_type, payload=payload, company_id=submission.company_id
        )
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger("safir.approvals").exception("request webhook emit failed")


def _advance_past_skipped(
    db: Session, *, instance: WorkflowInstance, submission: FormSubmission
) -> None:
    """While the current step has no pending task, move to the next step."""
    version = db.get(WorkflowVersion, instance.workflow_version_id)
    steps = sorted(version.steps, key=lambda s: s.display_order)
    by_id = {s.id: s for s in steps}

    guard = 0
    while instance.status == SubmissionStatus.IN_REVIEW.value and guard < len(steps) + 1:
        guard += 1
        current = by_id.get(instance.current_step_id)
        if current is None:
            _complete(db, instance=instance, submission=submission)
            return
        pending = db.execute(
            select(ApprovalTask).where(
                ApprovalTask.instance_id == instance.id,
                ApprovalTask.step_id == current.id,
                ApprovalTask.status == TaskStatus.PENDING.value,
            )
        ).scalars().all()
        if pending:
            return
        # No pending task at this step -- advance.
        nxt = _next_step(steps, current)
        if nxt is None:
            _complete(db, instance=instance, submission=submission)
            return
        _open_step(db, instance=instance, submission=submission, step=nxt)


def _next_step(steps: list[WorkflowStep], current: WorkflowStep) -> WorkflowStep | None:
    ordered = sorted(steps, key=lambda s: s.display_order)
    for step in ordered:
        if step.display_order > current.display_order:
            return step
    return None


def _complete(
    db: Session, *, instance: WorkflowInstance, submission: FormSubmission
) -> None:
    instance.status = SubmissionStatus.APPROVED.value
    instance.completed_at = utcnow()
    instance.current_step_id = None
    db.add(instance)
    submission.status = SubmissionStatus.APPROVED.value
    db.add(submission)
    _write_event(
        db,
        instance=instance,
        submission=submission,
        action="completed",
        actor_id=None,
        step_id=None,
        comment="All steps approved",
        from_status=SubmissionStatus.IN_REVIEW.value,
        to_status=SubmissionStatus.APPROVED.value,
    )


def cancel_instance(
    db: Session, *, submission: FormSubmission, actor: User, commit: bool = True
) -> None:
    instance = db.execute(
        select(WorkflowInstance).where(WorkflowInstance.submission_id == submission.id)
    ).scalar_one_or_none()
    if instance is None:
        return
    db.execute(
        update(ApprovalTask)
        .where(
            ApprovalTask.instance_id == instance.id,
            ApprovalTask.status == TaskStatus.PENDING.value,
        )
        .values(status=TaskStatus.CANCELLED.value, acted_at=utcnow())
    )
    instance.status = SubmissionStatus.CANCELLED.value
    instance.completed_at = utcnow()
    db.add(instance)
    _write_event(
        db,
        instance=instance,
        submission=submission,
        action="cancelled",
        actor_id=actor.id,
        step_id=None,
        comment=None,
        from_status=SubmissionStatus.IN_REVIEW.value,
        to_status=SubmissionStatus.CANCELLED.value,
    )
    db.flush()
    if commit:
        db.commit()


def _write_event(
    db: Session,
    *,
    instance: WorkflowInstance,
    submission: FormSubmission,
    action: str,
    actor_id: int | None,
    step_id: int | None,
    comment: str | None,
    from_status: str | None,
    to_status: str | None,
) -> ApprovalEvent:
    event = ApprovalEvent(
        instance_id=instance.id,
        submission_id=submission.id,
        step_id=step_id,
        actor_user_id=actor_id,
        action=action,
        comment=comment,
        from_status=from_status,
        to_status=to_status,
    )
    db.add(event)
    db.flush()
    return event


# --------------------------------------------------------------------------
# acting on a task
# --------------------------------------------------------------------------
def act(
    db: Session,
    *,
    actor: User,
    task_id: int,
    decision: str,
    comment: str | None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> WorkflowInstance:
    require_permission(actor, Perm.APPROVAL_ACT)

    task = db.get(ApprovalTask, task_id)
    if task is None:
        raise NotFoundError("Approval task not found.")
    if task.assignee_id != actor.id:
        # Do not reveal whether the task exists for someone else.
        raise NotFoundError("Approval task not found.")
    if task.status != TaskStatus.PENDING.value:
        raise ConflictError("This task has already been actioned.")

    instance = db.get(WorkflowInstance, task.instance_id)
    if instance is None:
        raise NotFoundError("Approval task not found.")
    submission = db.get(FormSubmission, instance.submission_id)
    if submission is None:
        raise NotFoundError("Submission not found.")
    step = db.get(WorkflowStep, task.step_id)

    decision = decision.lower()
    if decision not in (
        ApprovalDecision.APPROVE.value,
        ApprovalDecision.REJECT.value,
        ApprovalDecision.RETURN.value,
    ):
        raise ValidationError("Unknown approval decision.")

    if step is not None:
        if decision == ApprovalDecision.APPROVE.value and not step.allow_approve:
            raise PermissionDeniedError("Approval is not allowed at this step.")
        if decision == ApprovalDecision.REJECT.value and not step.allow_reject:
            raise PermissionDeniedError("Rejection is not allowed at this step.")
        if decision == ApprovalDecision.RETURN.value and not step.allow_return:
            raise PermissionDeniedError("Returning is not allowed at this step.")
        if (
            decision in (ApprovalDecision.REJECT.value, ApprovalDecision.RETURN.value)
            and step.require_comment_on_reject
            and not (comment or "").strip()
        ):
            raise ValidationError("A comment is required for this action.")
    if step is not None and step.required_permission:
        from backend.rbac.authorization import has_permission

        if not has_permission(actor, step.required_permission):
            raise PermissionDeniedError(
                "You do not hold the permission required for this step."
            )

    # Concurrency guard: only the caller that flips 'pending' proceeds.
    result = db.execute(
        update(ApprovalTask)
        .where(ApprovalTask.id == task.id, ApprovalTask.status == TaskStatus.PENDING.value)
        .values(
            status={
                ApprovalDecision.APPROVE.value: TaskStatus.APPROVED.value,
                ApprovalDecision.REJECT.value: TaskStatus.REJECTED.value,
                ApprovalDecision.RETURN.value: TaskStatus.RETURNED.value,
            }[decision],
            acted_at=utcnow(),
            comment=(comment or None),
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise ConflictError("This task has already been actioned.")

    from_status = submission.status
    step_id = task.step_id

    if decision == ApprovalDecision.APPROVE.value:
        # Any-of progression: sibling tasks at this step are superseded.
        db.execute(
            update(ApprovalTask)
            .where(
                ApprovalTask.instance_id == instance.id,
                ApprovalTask.step_id == step_id,
                ApprovalTask.status == TaskStatus.PENDING.value,
            )
            .values(status=TaskStatus.SKIPPED.value, acted_at=utcnow())
        )
        db.flush()
        _write_event(
            db,
            instance=instance,
            submission=submission,
            action="approved",
            actor_id=actor.id,
            step_id=step_id,
            comment=comment,
            from_status=from_status,
            to_status=SubmissionStatus.IN_REVIEW.value,
        )
        version = db.get(WorkflowVersion, instance.workflow_version_id)
        nxt = _next_step(sorted(version.steps, key=lambda s: s.display_order), step) if step else None
        if nxt is None:
            _complete(db, instance=instance, submission=submission)
        else:
            _open_step(db, instance=instance, submission=submission, step=nxt)
            _advance_past_skipped(db, instance=instance, submission=submission)

    elif decision == ApprovalDecision.REJECT.value:
        db.execute(
            update(ApprovalTask)
            .where(
                ApprovalTask.instance_id == instance.id,
                ApprovalTask.status == TaskStatus.PENDING.value,
            )
            .values(status=TaskStatus.CANCELLED.value, acted_at=utcnow())
        )
        instance.status = SubmissionStatus.REJECTED.value
        instance.completed_at = utcnow()
        instance.current_step_id = None
        db.add(instance)
        submission.status = SubmissionStatus.REJECTED.value
        db.add(submission)
        _write_event(
            db,
            instance=instance,
            submission=submission,
            action="rejected",
            actor_id=actor.id,
            step_id=step_id,
            comment=comment,
            from_status=from_status,
            to_status=SubmissionStatus.REJECTED.value,
        )

    else:  # return for correction
        db.execute(
            update(ApprovalTask)
            .where(
                ApprovalTask.instance_id == instance.id,
                ApprovalTask.status == TaskStatus.PENDING.value,
            )
            .values(status=TaskStatus.CANCELLED.value, acted_at=utcnow())
        )
        instance.status = SubmissionStatus.RETURNED.value
        instance.completed_at = utcnow()
        instance.current_step_id = None
        db.add(instance)
        submission.status = SubmissionStatus.RETURNED.value
        db.add(submission)
        _write_event(
            db,
            instance=instance,
            submission=submission,
            action="returned",
            actor_id=actor.id,
            step_id=step_id,
            comment=comment,
            from_status=from_status,
            to_status=SubmissionStatus.RETURNED.value,
        )

    db.commit()
    db.refresh(instance)

    audit_service.record(
        db,
        action={
            ApprovalDecision.APPROVE.value: AuditAction.APPROVAL_APPROVED,
            ApprovalDecision.REJECT.value: AuditAction.APPROVAL_REJECTED,
            ApprovalDecision.RETURN.value: AuditAction.APPROVAL_RETURNED,
        }[decision],
        actor_user_id=actor.id,
        entity_type="form_submission",
        entity_id=submission.id,
        company_id=submission.company_id,
        metadata={"step_id": step_id, "task_id": task.id},
        ip_address=ip_address,
        user_agent=user_agent,
    )

    _notify_decision(db, instance=instance, submission=submission, decision=decision, actor=actor)
    return instance


def _notify_decision(
    db: Session,
    *,
    instance: WorkflowInstance,
    submission: FormSubmission,
    decision: str,
    actor: User,
) -> None:
    from backend.services import notification_service

    try:
        notification_service.notify_decision(
            db,
            submitter_id=submission.submitted_by_id,
            decision=decision,
            submission_id=submission.id,
            company_id=submission.company_id,
            title=submission.title or submission.reference,
            actor_user_id=actor.id,
        )
        event_type = {
            ApprovalDecision.APPROVE.value: "request.approved",
            ApprovalDecision.REJECT.value: "request.rejected",
            ApprovalDecision.RETURN.value: "request.returned",
        }.get(decision)
        if event_type:
            _emit_request_event(
                db,
                event_type,
                submission,
                {"decision": decision, "actor_user_id": actor.id},
            )
    except Exception:  # noqa: BLE001 - notifications are best-effort
        import logging

        logging.getLogger("safir.approvals").exception("decision notification failed")


# --------------------------------------------------------------------------
# inbox / authorization helpers
# --------------------------------------------------------------------------
def user_can_act(db: Session, user: User, instance: WorkflowInstance | None) -> bool:
    if instance is None or instance.status != SubmissionStatus.IN_REVIEW.value:
        return False
    from backend.rbac.authorization import has_permission

    if not has_permission(user, Perm.APPROVAL_ACT):
        return False
    task = db.execute(
        select(ApprovalTask).where(
            ApprovalTask.instance_id == instance.id,
            ApprovalTask.assignee_id == user.id,
            ApprovalTask.status == TaskStatus.PENDING.value,
        )
    ).scalar_one_or_none()
    return task is not None


def my_approvals(
    db: Session, *, user: User, limit: int = 50, offset: int = 0
) -> dict:
    """Requests currently awaiting this user's action."""
    require_permission(user, Perm.APPROVAL_READ_OWN)

    base = (
        select(ApprovalTask)
        .where(
            ApprovalTask.assignee_id == user.id,
            ApprovalTask.status == TaskStatus.PENDING.value,
        )
        .order_by(ApprovalTask.created_at.desc())
    )
    total = int(
        db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    )
    tasks = list(db.execute(base.limit(limit).offset(offset)).scalars())

    from backend.services import submission_service

    items = []
    for task in tasks:
        instance = db.get(WorkflowInstance, task.instance_id)
        submission = (
            db.get(FormSubmission, instance.submission_id) if instance else None
        )
        row = submission_service.serialise(db, submission) if submission else {}
        row["task_id"] = task.id
        row["step_id"] = task.step_id
        row["step_order"] = task.step_order
        step = db.get(WorkflowStep, task.step_id)
        row["step_name_ar"] = step.name_ar if step else None
        row["step_name_en"] = step.name_en if step else None
        items.append(row)

    return {"total": total, "limit": limit, "offset": offset, "items": items}


__all__ = [
    "act",
    "cancel_instance",
    "my_approvals",
    "serialise_instance",
    "start_instance",
    "user_can_act",
]
