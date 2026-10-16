"""Requirements engine.

Requirements are configured on a **draft** form version (like fields). The
runtime uses them to decide whether a submission is complete:

* ``document``  -- satisfied when at least one document is linked to the
  submission's requirement row (and, for ``min_count`` > 1, that many);
* ``field_value`` -- satisfied when the referenced form field has a non-empty
  value (optionally equal to a configured expected value);
* ``acknowledgement`` -- satisfied when the submitter explicitly acknowledges
  it (recorded via the submission service).

The evaluation is a pure function over the *submission's own snapshot*
(``SubmissionRequirement`` rows), so it does not depend on the form definition
still existing in its current shape.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.errors import ConflictError, NotFoundError, ValidationError
from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import RequirementType
from backend.db.models.forms import FormRequirement
from backend.db.models.identity import User
from backend.rbac.authorization import require_permission
from backend.rbac.permissions import Perm
from backend.services import audit_service, form_service


def serialise_requirement(requirement: FormRequirement) -> dict:
    return {
        "id": requirement.id,
        "key": requirement.key,
        "name_ar": requirement.name_ar,
        "name_en": requirement.name_en,
        "description_ar": requirement.description_ar,
        "description_en": requirement.description_en,
        "requirement_type": requirement.requirement_type,
        "is_mandatory": requirement.is_mandatory,
        "is_active": requirement.is_active,
        "display_order": requirement.display_order,
        "config": requirement.config,
    }


def list_requirements(
    db: Session, *, user: User, form_id: int, version_id: int | None = None
) -> list[dict]:
    require_permission(user, Perm.REQUIREMENT_READ)
    if version_id is None:
        version = form_service.get_current_version(db, user=user, form_id=form_id)
    else:
        version = form_service.get_version(
            db, user=user, form_id=form_id, version_id=version_id
        )
    return [serialise_requirement(r) for r in version.requirements]


def add_requirement(
    db: Session,
    *,
    actor: User,
    form_id: int,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    require_permission(actor, Perm.REQUIREMENT_MANAGE)
    form = form_service.get_form_scoped(db, actor, form_id)
    draft = form_service.get_editable_version(db, actor=actor, form=form)

    key = payload["key"].strip().lower()
    if db.execute(
        select(FormRequirement).where(
            FormRequirement.form_version_id == draft.id, FormRequirement.key == key
        )
    ).scalar_one_or_none():
        raise ConflictError("A requirement with this key already exists on this version.")

    _validate_requirement_payload(payload, draft)

    order = payload.get("display_order")
    if not order:
        order = (max([r.display_order for r in draft.requirements], default=0)) + 1

    requirement = FormRequirement(
        form_version_id=draft.id,
        key=key,
        name_ar=payload["name_ar"].strip(),
        name_en=payload["name_en"].strip(),
        description_ar=payload.get("description_ar"),
        description_en=payload.get("description_en"),
        requirement_type=payload.get("requirement_type", RequirementType.DOCUMENT.value),
        is_mandatory=bool(payload.get("is_mandatory", True)),
        is_active=bool(payload.get("is_active", True)),
        display_order=order,
        config=payload.get("config"),
    )
    db.add(requirement)
    db.commit()
    db.refresh(requirement)

    audit_service.record(
        db,
        action=AuditAction.REQUIREMENT_CREATED,
        actor_user_id=actor.id,
        entity_type="form_requirement",
        entity_id=requirement.id,
        metadata={"form_id": form.id, "version_id": draft.id, "key": key},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return serialise_requirement(requirement)


def _validate_requirement_payload(payload: dict, version) -> None:
    req_type = payload.get("requirement_type", RequirementType.DOCUMENT.value)
    config = payload.get("config") or {}
    if req_type == RequirementType.FIELD_VALUE.value:
        field_key = config.get("field_key")
        if not field_key:
            raise ValidationError("A field-value requirement needs config.field_key.")
        if not any(f.key == field_key for f in version.fields):
            raise ValidationError(
                f"config.field_key '{field_key}' does not match a field on this version."
            )
    if req_type == RequirementType.DOCUMENT.value:
        min_count = config.get("min_count", 1)
        try:
            if int(min_count) < 1:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise ValidationError("config.min_count must be a positive integer.") from exc


def update_requirement(
    db: Session,
    *,
    actor: User,
    form_id: int,
    requirement_id: int,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    require_permission(actor, Perm.REQUIREMENT_MANAGE)
    form = form_service.get_form_scoped(db, actor, form_id)
    draft = form_service.get_editable_version(db, actor=actor, form=form)
    requirement = db.get(FormRequirement, requirement_id)
    if requirement is None or requirement.form_version_id != draft.id:
        raise NotFoundError("Requirement not found on the editable version.")

    merged = {
        "name_ar": payload.get("name_ar", requirement.name_ar),
        "name_en": payload.get("name_en", requirement.name_en),
        "requirement_type": requirement.requirement_type,
        "config": payload.get("config", requirement.config),
    }
    _validate_requirement_payload(merged, draft)

    for attr in ("name_ar", "name_en", "description_ar", "description_en", "config"):
        if attr in payload and payload[attr] is not None:
            setattr(requirement, attr, payload[attr])
    for attr in ("is_mandatory", "is_active", "display_order"):
        if attr in payload and payload[attr] is not None:
            setattr(requirement, attr, payload[attr])
    db.add(requirement)
    db.commit()
    db.refresh(requirement)

    audit_service.record(
        db,
        action=AuditAction.REQUIREMENT_UPDATED,
        actor_user_id=actor.id,
        entity_type="form_requirement",
        entity_id=requirement.id,
        metadata={"form_id": form.id, "version_id": draft.id},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return serialise_requirement(requirement)


def remove_requirement(
    db: Session,
    *,
    actor: User,
    form_id: int,
    requirement_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    require_permission(actor, Perm.REQUIREMENT_MANAGE)
    form = form_service.get_form_scoped(db, actor, form_id)
    draft = form_service.get_editable_version(db, actor=actor, form=form)
    requirement = db.get(FormRequirement, requirement_id)
    if requirement is None or requirement.form_version_id != draft.id:
        raise NotFoundError("Requirement not found on the editable version.")
    db.delete(requirement)
    db.commit()
    audit_service.record(
        db,
        action=AuditAction.REQUIREMENT_REMOVED,
        actor_user_id=actor.id,
        entity_type="form_requirement",
        entity_id=requirement_id,
        metadata={"form_id": form.id, "version_id": draft.id},
        ip_address=ip_address,
        user_agent=user_agent,
    )


def reorder_requirements(
    db: Session,
    *,
    actor: User,
    form_id: int,
    ordered_ids: list[int],
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> list[dict]:
    require_permission(actor, Perm.REQUIREMENT_MANAGE)
    form = form_service.get_form_scoped(db, actor, form_id)
    draft = form_service.get_editable_version(db, actor=actor, form=form)

    current = {r.id: r for r in draft.requirements}
    if set(ordered_ids) != set(current.keys()):
        raise ValidationError(
            "The reorder list must contain exactly the current requirements."
        )
    for index, requirement_id in enumerate(ordered_ids, start=1):
        current[requirement_id].display_order = index
        db.add(current[requirement_id])
    db.commit()
    audit_service.record(
        db,
        action=AuditAction.REQUIREMENT_REORDERED,
        actor_user_id=actor.id,
        entity_type="dynamic_form",
        entity_id=form.id,
        metadata={"version_id": draft.id},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.refresh(draft)
    return [serialise_requirement(r) for r in draft.requirements]


__all__ = [
    "add_requirement",
    "list_requirements",
    "remove_requirement",
    "reorder_requirements",
    "serialise_requirement",
    "update_requirement",
]
