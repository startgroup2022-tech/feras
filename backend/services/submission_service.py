"""Form submission service and the request lifecycle.

Responsibilities:

* create/update a draft submission, pinned to a *published form version*;
* validate submitted values against that version's fields -- **on the server**,
  never trusting the client;
* snapshot the version's requirements and evaluate completeness;
* gate submission on mandatory requirements (unless the workflow allows an
  override the actor is permitted to use);
* start the approval workflow.

Value validation is declarative: each field type has a small, fixed rule set
derived from the field's ``config``. Nothing here evaluates user-authored code.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from backend.db.base import utcnow
from backend.db.models.audit_actions import AuditAction
from backend.db.models.documents import Document
from backend.db.models.enums import (
    FieldType,
    FormStatus,
    RequirementType,
    SubmissionStatus,
)
from backend.db.models.forms import FormField, FormVersion
from backend.db.models.identity import Company, User
from backend.db.models.submissions import FormSubmission, SubmissionRequirement
from backend.db.models.workflows import WorkflowDefinition
from backend.rbac.authorization import (
    accessible_company_ids,
    can_write_company,
    has_permission,
    require_company_access,
    require_permission,
)
from backend.rbac.permissions import Perm
from backend.services import audit_service, form_service, workflow_service

# Statuses in which a submission's values may still be edited.
EDITABLE_STATUSES = {
    SubmissionStatus.DRAFT.value,
    SubmissionStatus.INCOMPLETE.value,
    SubmissionStatus.RETURNED.value,
}


# --------------------------------------------------------------------------
# value validation
# --------------------------------------------------------------------------
def validate_values(
    db: Session, version: FormVersion, values: dict | None, *, partial: bool
) -> dict:
    """Validate/normalise submitted values against a form version.

    ``partial`` is used for drafts: missing required fields are tolerated, but
    any present value is still type-checked. On submit, ``partial`` is False
    and every required field must be present and non-empty.
    """
    values = values or {}
    fields = [f for f in version.fields if f.is_active]
    by_key = {f.key: f for f in fields}
    errors: list[str] = []

    unknown = set(values) - set(by_key)
    if unknown:
        errors.append("Unknown field(s): " + ", ".join(sorted(unknown)))

    normalised: dict = dict(values)
    for field in fields:
        present = field.key in values and not _is_empty(values.get(field.key))
        if not present:
            if field.is_required and not partial:
                errors.append(f"'{field.label_en}' is required.")
            continue
        try:
            normalised[field.key] = _validate_single(db, field, values[field.key])
        except ValidationError as exc:
            errors.append(f"'{field.label_en}': {exc.message}")

    if errors:
        raise ValidationError("; ".join(errors))
    return normalised


def _is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (list, dict)) and not value:
        return True
    return False


def _validate_single(db: Session, field: FormField, value):
    ftype = field.field_type
    config = field.config or {}

    if ftype in (FieldType.SHORT_TEXT.value, FieldType.LONG_TEXT.value):
        text = str(value)
        max_length = config.get("max_length")
        if max_length and len(text) > int(max_length):
            raise ValidationError(f"must be at most {max_length} characters.")
        return text

    if ftype == FieldType.INTEGER.value:
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError("must be a whole number.") from exc

    if ftype in (FieldType.DECIMAL.value, FieldType.CURRENCY.value):
        try:
            number = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValidationError("must be a number.") from exc
        if ftype == FieldType.CURRENCY.value and number < 0:
            raise ValidationError("must not be negative.")
        return float(number)

    if ftype == FieldType.DATE.value:
        return _parse_date(value, with_time=False)

    if ftype == FieldType.DATETIME.value:
        return _parse_date(value, with_time=True)

    if ftype == FieldType.CHECKBOX.value:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "on"}
        return bool(value)

    if ftype == FieldType.SELECT.value:
        allowed = {str(o.get("value")) for o in config.get("options", [])}
        if str(value) not in allowed:
            raise ValidationError("is not one of the allowed options.")
        return str(value)

    if ftype == FieldType.MULTI_SELECT.value:
        if not isinstance(value, list):
            raise ValidationError("must be a list of options.")
        allowed = {str(o.get("value")) for o in config.get("options", [])}
        chosen = [str(v) for v in value]
        if any(c not in allowed for c in chosen):
            raise ValidationError("contains an option that is not allowed.")
        return chosen

    if ftype == FieldType.EMAIL.value:
        text = str(value).strip()
        if "@" not in text or text.startswith("@") or text.endswith("@"):
            raise ValidationError("must be a valid email address.")
        return text

    if ftype == FieldType.PHONE.value:
        text = str(value).strip()
        digits = [c for c in text if c.isdigit()]
        if len(digits) < 7 or len(digits) > 15:
            raise ValidationError("must be a valid phone number.")
        return text

    if ftype == FieldType.URL.value:
        text = str(value).strip()
        if not (text.startswith("http://") or text.startswith("https://")):
            raise ValidationError("must be a valid URL.")
        return text

    if ftype == FieldType.FILE.value:
        # File values carry a document id produced by the document service.
        return value

    if ftype in (
        FieldType.COMPANY.value,
        FieldType.DEPARTMENT.value,
        FieldType.USER.value,
    ):
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError("must be a valid reference id.") from exc

    raise ValidationError("has an unsupported field type.")


def _parse_date(value, *, with_time: bool):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    try:
        if with_time:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError as exc:
        raise ValidationError("must be a valid date.") from exc


# --------------------------------------------------------------------------
# completeness
# --------------------------------------------------------------------------
def _document_count(db: Session, submission_requirement_id: int) -> int:
    return int(
        db.execute(
            select(func.count(Document.id)).where(
                Document.submission_requirement_id == submission_requirement_id
            )
        ).scalar_one()
    )


def evaluate_requirements(db: Session, submission: FormSubmission) -> list[dict]:
    """Evaluate each requirement against the submission's current state.

    Returns a list of dicts (satisfied + detail) and updates the stored
    ``is_satisfied`` flags. The submission's own values and linked documents are
    the source of truth -- never client-supplied claims.
    """
    values = submission.values or {}
    results: list[dict] = []
    for requirement in submission.requirements:
        satisfied = False
        detail: dict = {}
        if requirement.requirement_type == RequirementType.DOCUMENT.value:
            min_count = 1
            if requirement.detail and isinstance(requirement.detail.get("config"), dict):
                min_count = int(requirement.detail["config"].get("min_count", 1) or 1)
            count = _document_count(db, requirement.id)
            satisfied = count >= min_count
            detail = {"document_count": count, "min_count": min_count}
        elif requirement.requirement_type == RequirementType.FIELD_VALUE.value:
            cfg = (requirement.detail or {}).get("config") or {}
            field_key = cfg.get("field_key")
            value = values.get(field_key) if field_key else None
            satisfied = not _is_empty(value)
            expected = cfg.get("expected_value")
            if satisfied and expected is not None:
                satisfied = str(value) == str(expected)
            detail = {"field_key": field_key, "value": value, "expected_value": expected}
        elif requirement.requirement_type == RequirementType.ACKNOWLEDGEMENT.value:
            acknowledged = bool((requirement.detail or {}).get("acknowledged"))
            satisfied = acknowledged
            detail = {"acknowledged": acknowledged}

        # A recorded override counts as satisfied.
        if requirement.overridden:
            satisfied = True

        requirement.is_satisfied = satisfied
        if satisfied and requirement.satisfied_at is None:
            requirement.satisfied_at = utcnow()
        db.add(requirement)
        results.append(
            {
                "id": requirement.id,
                "requirement_key": requirement.requirement_key,
                "name_ar": requirement.name_ar,
                "name_en": requirement.name_en,
                "requirement_type": requirement.requirement_type,
                "is_mandatory": requirement.is_mandatory,
                "is_satisfied": satisfied,
                "overridden": requirement.overridden,
                "override_reason": requirement.override_reason,
                "satisfied_at": requirement.satisfied_at,
                "document_ids": [
                    d.id
                    for d in db.execute(
                        select(Document).where(
                            Document.submission_requirement_id == requirement.id
                        )
                    ).scalars()
                ],
                "detail": detail,
            }
        )
    db.flush()
    return results


def mandatory_unmet(db: Session, submission: FormSubmission) -> list[SubmissionRequirement]:
    return [
        r
        for r in submission.requirements
        if r.is_mandatory and not r.is_satisfied and not r.overridden
    ]


# --------------------------------------------------------------------------
# scoping / reads
# --------------------------------------------------------------------------
def _apply_submission_scope(stmt, user: User):
    allowed = accessible_company_ids(user)
    if allowed is None:
        return stmt
    if not allowed:
        return stmt.where(False)
    return stmt.where(FormSubmission.company_id.in_(allowed))


def _can_read_all(user: User) -> bool:
    return has_permission(user, Perm.SUBMISSION_READ_ALL)


def _can_read_company(user: User) -> bool:
    return has_permission(user, Perm.SUBMISSION_READ_COMPANY) or _can_read_all(user)


def get_submission_scoped(db: Session, user: User, submission_id: int) -> FormSubmission:
    """Fetch a submission the user may read.

    Three read grants, from narrowest to widest:
    * ``read_own``    -- you may read submissions you created;
    * ``read_company``-- you may read submissions within your companies;
    * ``read_all``    -- holding-wide read.

    Company scope is still applied, so ``read_all`` cannot cross into a company
    the user could not otherwise see.
    """
    require_permission(user, Perm.SUBMISSION_READ_OWN)
    stmt = select(FormSubmission).where(FormSubmission.id == submission_id)
    stmt = _apply_submission_scope(stmt, user)
    submission = db.execute(stmt).scalar_one_or_none()
    if submission is None:
        raise NotFoundError("Submission not found.")

    if _can_read_company(user):
        return submission
    # read_own only: must be the creator.
    if submission.submitted_by_id != user.id:
        raise NotFoundError("Submission not found.")
    return submission


def get_submission_or_404(db: Session, submission_id: int) -> FormSubmission:
    submission = db.get(FormSubmission, submission_id)
    if submission is None:
        raise NotFoundError("Submission not found.")
    return submission


def list_submissions(
    db: Session,
    *,
    user: User,
    mine: bool = False,
    company_id: int | None = None,
    status: str | None = None,
    form_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    require_permission(user, Perm.SUBMISSION_READ_OWN)
    stmt = select(FormSubmission)
    stmt = _apply_submission_scope(stmt, user)

    if mine or not _can_read_company(user):
        stmt = stmt.where(FormSubmission.submitted_by_id == user.id)
    if company_id is not None:
        stmt = stmt.where(FormSubmission.company_id == company_id)
    if status is not None:
        stmt = stmt.where(FormSubmission.status == status)
    if form_id is not None:
        stmt = stmt.where(FormSubmission.form_id == form_id)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = int(db.execute(count_stmt).scalar_one())
    rows = list(
        db.execute(
            stmt.order_by(FormSubmission.created_at.desc(), FormSubmission.id.desc())
            .limit(limit)
            .offset(offset)
        ).scalars()
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [serialise(db, s) for s in rows],
    }


# --------------------------------------------------------------------------
# serialisation
# --------------------------------------------------------------------------
def _reference(db: Session, submission: FormSubmission) -> str:
    from backend.db.models.forms import DynamicForm

    form = db.get(DynamicForm, submission.form_id)
    prefix = (form.code.upper() if form else "REQ")[:8]
    return f"{prefix}-{submission.id:06d}"


def serialise(db: Session, submission: FormSubmission) -> dict:
    from backend.db.models.forms import DynamicForm

    form = db.get(DynamicForm, submission.form_id)
    company = db.get(Company, submission.company_id)
    submitter = db.get(User, submission.submitted_by_id) if submission.submitted_by_id else None

    current_step_name_ar = current_step_name_en = None
    current_step_order = total_steps = None
    instance = _instance_for(db, submission.id)
    if instance is not None:
        from backend.db.models.workflows import WorkflowStep, WorkflowVersion

        if instance.current_step_id:
            step = db.get(WorkflowStep, instance.current_step_id)
            if step:
                current_step_name_ar = step.name_ar
                current_step_name_en = step.name_en
                current_step_order = step.display_order
        version = db.get(WorkflowVersion, instance.workflow_version_id)
        if version:
            total_steps = len(version.steps)

    return {
        "id": submission.id,
        "reference": submission.reference or _reference(db, submission),
        "form_id": submission.form_id,
        "form_version_id": submission.form_version_id,
        "form_name_ar": form.name_ar if form else None,
        "form_name_en": form.name_en if form else None,
        "company_id": submission.company_id,
        "company_name_ar": company.name_ar if company else None,
        "company_name_en": company.name_en if company else None,
        "department_id": submission.department_id,
        "submitted_by_id": submission.submitted_by_id,
        "submitted_by_name_ar": submitter.full_name_ar if submitter else None,
        "submitted_by_name_en": submitter.full_name_en if submitter else None,
        "status": submission.status,
        "title": submission.title,
        "values": submission.values,
        "submitted_at": submission.submitted_at,
        "created_at": submission.created_at,
        "updated_at": submission.updated_at,
        "current_step_name_ar": current_step_name_ar,
        "current_step_name_en": current_step_name_en,
        "current_step_order": current_step_order,
        "total_steps": total_steps,
    }


def _instance_for(db: Session, submission_id: int):
    from backend.db.models.workflows import WorkflowInstance

    return db.execute(
        select(WorkflowInstance).where(WorkflowInstance.submission_id == submission_id)
    ).scalar_one_or_none()


# --------------------------------------------------------------------------
# writes
# --------------------------------------------------------------------------
def create_submission(
    db: Session,
    *,
    actor: User,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> FormSubmission:
    require_permission(actor, Perm.FORM_SUBMIT)

    form = form_service.get_form_scoped(db, actor, payload["form_id"])
    if form.status != FormStatus.PUBLISHED.value:
        raise ConflictError("This form is not published.")
    version = form.published_version
    if version is None:
        raise ConflictError("This form has no published version.")

    company_id = payload["company_id"]
    require_company_access(actor, company_id, write=True)
    _assert_form_available_to_company(db, form, company_id)

    values = validate_values(db, version, payload.get("values"), partial=True)

    submission = FormSubmission(
        reference="PENDING",  # replaced after flush once the id exists
        form_id=form.id,
        form_version_id=version.id,
        company_id=company_id,
        department_id=payload.get("department_id"),
        submitted_by_id=actor.id,
        status=SubmissionStatus.DRAFT.value,
        title=payload.get("title"),
        values=values,
    )
    db.add(submission)
    db.flush()
    submission.reference = _reference(db, submission)

    _snapshot_requirements(db, submission, version)

    db.commit()
    db.refresh(submission)

    audit_service.record(
        db,
        action=AuditAction.SUBMISSION_CREATED,
        actor_user_id=actor.id,
        entity_type="form_submission",
        entity_id=submission.id,
        company_id=company_id,
        metadata={"form_id": form.id, "version_id": version.id},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return submission


def _assert_form_available_to_company(db: Session, form, company_id: int) -> None:
    from backend.db.models.enums import FormScope
    from backend.db.models.forms import FormCompany

    if form.scope == FormScope.HOLDING.value:
        return
    linked = db.execute(
        select(FormCompany.company_id).where(
            FormCompany.form_id == form.id, FormCompany.company_id == company_id
        )
    ).scalar_one_or_none()
    if linked is None:
        raise PermissionDeniedError("This form is not available to the selected company.")


def _snapshot_requirements(db: Session, submission: FormSubmission, version: FormVersion) -> None:
    for requirement in version.requirements:
        if not requirement.is_active:
            continue
        db.add(
            SubmissionRequirement(
                submission_id=submission.id,
                form_requirement_id=requirement.id,
                requirement_key=requirement.key,
                name_ar=requirement.name_ar,
                name_en=requirement.name_en,
                requirement_type=requirement.requirement_type,
                is_mandatory=requirement.is_mandatory,
                detail={"config": requirement.config or {}},
            )
        )
    db.flush()


def update_submission(
    db: Session,
    *,
    actor: User,
    submission_id: int,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> FormSubmission:
    require_permission(actor, Perm.FORM_SUBMIT)
    submission = get_submission_scoped(db, actor, submission_id)
    if submission.submitted_by_id != actor.id:
        raise PermissionDeniedError("Only the submitter may edit this request.")
    if submission.status not in EDITABLE_STATUSES:
        raise ConflictError("This request can no longer be edited.")
    require_company_access(actor, submission.company_id, write=True)

    version = db.get(FormVersion, submission.form_version_id)
    if payload.get("values") is not None:
        submission.values = validate_values(db, version, payload["values"], partial=True)
    if payload.get("title") is not None:
        submission.title = payload["title"]
    if payload.get("department_id") is not None:
        submission.department_id = payload["department_id"]

    # Values may satisfy field-value requirements.
    evaluate_requirements(db, submission)
    db.add(submission)
    db.commit()
    db.refresh(submission)

    audit_service.record(
        db,
        action=AuditAction.SUBMISSION_UPDATED,
        actor_user_id=actor.id,
        entity_type="form_submission",
        entity_id=submission.id,
        company_id=submission.company_id,
        metadata={"fields": sorted(payload.keys())},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return submission


def acknowledge_requirement(
    db: Session,
    *,
    actor: User,
    submission_id: int,
    requirement_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    require_permission(actor, Perm.FORM_SUBMIT)
    submission = get_submission_scoped(db, actor, submission_id)
    if submission.submitted_by_id != actor.id:
        raise PermissionDeniedError("Only the submitter may acknowledge requirements.")
    if submission.status not in EDITABLE_STATUSES:
        raise ConflictError("This request can no longer be edited.")
    requirement = db.get(SubmissionRequirement, requirement_id)
    if requirement is None or requirement.submission_id != submission.id:
        raise NotFoundError("Requirement not found on this submission.")
    if requirement.requirement_type != RequirementType.ACKNOWLEDGEMENT.value:
        raise ValidationError("Only acknowledgement requirements can be acknowledged.")
    detail = dict(requirement.detail or {})
    detail["acknowledged"] = True
    requirement.detail = detail
    requirement.satisfied_by_id = actor.id
    db.add(requirement)
    db.commit()
    db.refresh(requirement)
    return {
        "id": requirement.id,
        "is_satisfied": requirement.is_satisfied,
    }


def override_requirement(
    db: Session,
    *,
    actor: User,
    submission_id: int,
    requirement_id: int,
    reason: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    """Record a permission-gated override of a mandatory requirement."""
    require_permission(actor, Perm.APPROVAL_OVERRIDE)
    submission = get_submission_scoped(db, actor, submission_id)
    requirement = db.get(SubmissionRequirement, requirement_id)
    if requirement is None or requirement.submission_id != submission.id:
        raise NotFoundError("Requirement not found on this submission.")
    if not requirement.is_mandatory:
        raise ValidationError("Only mandatory requirements can be overridden.")

    requirement.overridden = True
    requirement.override_reason = reason
    requirement.satisfied_by_id = actor.id
    requirement.satisfied_at = utcnow()
    db.add(requirement)
    db.commit()
    db.refresh(requirement)

    audit_service.record(
        db,
        action=AuditAction.SUBMISSION_OVERRIDDEN,
        actor_user_id=actor.id,
        entity_type="form_submission",
        entity_id=submission.id,
        company_id=submission.company_id,
        metadata={"requirement_id": requirement.id, "reason": reason},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return {
        "id": requirement.id,
        "overridden": True,
        "override_reason": requirement.override_reason,
    }


def submit_submission(
    db: Session,
    *,
    actor: User,
    submission_id: int,
    override_requirements: bool = False,
    override_reason: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> FormSubmission:
    require_permission(actor, Perm.FORM_SUBMIT)
    submission = get_submission_scoped(db, actor, submission_id)
    if submission.submitted_by_id != actor.id:
        raise PermissionDeniedError("Only the submitter may submit this request.")
    if submission.status not in EDITABLE_STATUSES:
        raise ConflictError("This request has already been submitted.")

    version = db.get(FormVersion, submission.form_version_id)
    # Full validation on submit (drafts were only partially validated).
    submission.values = validate_values(db, version, submission.values, partial=False)

    results = evaluate_requirements(db, submission)
    unmet = mandatory_unmet(db, submission)

    if unmet:
        # A bypass exists only when the workflow explicitly allows it AND the
        # actor holds the override permission AND a reason is recorded.
        allowed = _override_allowed(db, submission, actor)
        if override_requirements and allowed and (override_reason or "").strip():
            for requirement in unmet:
                requirement.overridden = True
                requirement.override_reason = override_reason.strip()
                requirement.satisfied_by_id = actor.id
                requirement.satisfied_at = utcnow()
                db.add(requirement)
            audit_service.record(
                db,
                action=AuditAction.SUBMISSION_OVERRIDDEN,
                actor_user_id=actor.id,
                entity_type="form_submission",
                entity_id=submission.id,
                company_id=submission.company_id,
                metadata={"reason": override_reason, "count": len(unmet)},
                ip_address=ip_address,
                user_agent=user_agent,
                commit=False,
            )
        else:
            submission.status = SubmissionStatus.INCOMPLETE.value
            db.add(submission)
            db.commit()
            missing = ", ".join(r.name_en for r in unmet)
            audit_service.record(
                db,
                action=AuditAction.SUBMISSION_INCOMPLETE,
                actor_user_id=actor.id,
                entity_type="form_submission",
                entity_id=submission.id,
                company_id=submission.company_id,
                metadata={"missing": [r.requirement_key for r in unmet]},
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise ConflictError(
                "This request is incomplete. Missing mandatory requirements: " + missing
            )

    workflow_version = _select_workflow_version(db, submission)
    if workflow_version is None:
        raise ConflictError(
            "No published workflow is configured for this form; the request cannot be routed."
        )

    submission.status = SubmissionStatus.SUBMITTED.value
    submission.submitted_at = utcnow()
    db.add(submission)
    db.flush()

    from backend.services import approval_service

    approval_service.start_instance(
        db,
        submission=submission,
        workflow_version=workflow_version,
        actor=actor,
        ip_address=ip_address,
        user_agent=user_agent,
        commit=False,
    )

    db.commit()
    db.refresh(submission)

    audit_service.record(
        db,
        action=AuditAction.SUBMISSION_SUBMITTED,
        actor_user_id=actor.id,
        entity_type="form_submission",
        entity_id=submission.id,
        company_id=submission.company_id,
        metadata={"workflow_version_id": workflow_version.id},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return submission


def _override_allowed(db: Session, submission: FormSubmission, actor: User) -> bool:
    if not has_permission(actor, Perm.APPROVAL_OVERRIDE):
        return False
    definition = db.execute(
        select(WorkflowDefinition).where(
            WorkflowDefinition.form_id == submission.form_id,
            WorkflowDefinition.status == FormStatus.PUBLISHED.value,
        )
    ).scalar_one_or_none()
    return bool(definition and definition.allow_requirement_override)


def _select_workflow_version(db: Session, submission: FormSubmission):
    """Pick the published workflow for the submission's form."""
    from backend.db.models.enums import WorkflowStatus

    definition = db.execute(
        select(WorkflowDefinition)
        .where(WorkflowDefinition.form_id == submission.form_id)
        .order_by(WorkflowDefinition.id)
    ).scalars()
    candidates = [
        d for d in definition if d.published_version is not None and d.status != WorkflowStatus.ARCHIVED.value
    ]
    if not candidates:
        return None
    # Deterministic choice: the first published, non-archived definition.
    return candidates[0].published_version


def cancel_submission(
    db: Session,
    *,
    actor: User,
    submission_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> FormSubmission:
    require_permission(actor, Perm.SUBMISSION_CANCEL)
    submission = get_submission_scoped(db, actor, submission_id)
    if submission.submitted_by_id != actor.id and not has_permission(
        actor, Perm.SUBMISSION_READ_ALL
    ):
        raise PermissionDeniedError("Only the submitter may cancel this request.")
    if submission.status in (
        SubmissionStatus.APPROVED.value,
        SubmissionStatus.CANCELLED.value,
    ):
        raise ConflictError("This request can no longer be cancelled.")

    previous = submission.status
    submission.status = SubmissionStatus.CANCELLED.value
    db.add(submission)

    from backend.services import approval_service

    approval_service.cancel_instance(db, submission=submission, actor=actor, commit=False)

    db.commit()
    db.refresh(submission)

    audit_service.record(
        db,
        action=AuditAction.SUBMISSION_CANCELLED,
        actor_user_id=actor.id,
        entity_type="form_submission",
        entity_id=submission.id,
        company_id=submission.company_id,
        metadata={"from": previous},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return submission


def detail(db: Session, *, user: User, submission_id: int) -> dict:
    """Full request detail: values, requirements, documents, workflow, timeline."""
    from backend.services import approval_service, document_service

    submission = get_submission_scoped(db, user, submission_id)
    base = serialise(db, submission)
    requirements = evaluate_requirements(db, submission)
    db.commit()

    documents = [
        document_service.serialise_document(db, d)
        for d in db.execute(
            select(Document).where(Document.submission_id == submission.id)
        ).scalars()
    ]

    instance = _instance_for(db, submission.id)
    workflow = (
        approval_service.serialise_instance(db, instance) if instance is not None else None
    )

    me_is_submitter = submission.submitted_by_id == user.id
    can_edit = me_is_submitter and submission.status in EDITABLE_STATUSES
    base.update(
        {
            "requirements": requirements,
            "documents": documents,
            "workflow": workflow,
            "can_submit": can_edit,
            "can_act": workflow is not None and approval_service.user_can_act(
                db, user, instance
            ),
            "can_override": has_permission(user, Perm.APPROVAL_OVERRIDE)
            and _override_allowed(db, submission, user),
        }
    )
    return base


__all__ = [
    "EDITABLE_STATUSES",
    "acknowledge_requirement",
    "cancel_submission",
    "create_submission",
    "detail",
    "evaluate_requirements",
    "get_submission_or_404",
    "get_submission_scoped",
    "list_submissions",
    "mandatory_unmet",
    "override_requirement",
    "serialise",
    "submit_submission",
    "update_submission",
    "validate_values",
]
