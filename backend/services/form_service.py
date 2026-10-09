"""Dynamic forms service.

Owns the form definition, its versioning and its fields.

Versioning contract (the property that protects history):

* A form always has at least one :class:`FormVersion`.
* Only a **draft** version may be edited. Editing a form that has a published
  version transparently forks a new draft (copying fields and requirements),
  so the published structure -- and every submission pinned to it -- is never
  mutated.
* Publishing freezes the draft and demotes any previously published version to
  ``archived``. Because submissions store ``form_version_id``, demotion is
  metadata only: the old version's fields still resolve for its submissions.

Company scoping: a company-scoped caller only ever sees holding-wide templates
plus forms explicitly linked to their companies, and may only configure forms
for companies they can write.
"""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from backend.db.base import utcnow
from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import FormScope, FormStatus
from backend.db.models.forms import (
    DynamicForm,
    FormCompany,
    FormField,
    FormVersion,
)
from backend.db.models.identity import Company, User
from backend.rbac.authorization import (
    accessible_company_ids,
    can_write_company,
    is_holding_wide,
    require_permission,
)
from backend.rbac.permissions import Perm
from backend.services import audit_service


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _visible_form_ids(db: Session, user: User):
    """Subquery of form ids a company-scoped user may see."""
    allowed = accessible_company_ids(user)
    if allowed is None:
        return None
    if not allowed:
        return []
    return list(
        db.execute(
            select(FormCompany.form_id).where(FormCompany.company_id.in_(allowed))
        ).scalars()
    )


def _apply_visibility(stmt, db: Session, user: User):
    allowed = accessible_company_ids(user)
    if allowed is None:
        return stmt
    ids = _visible_form_ids(db, user) or []
    # Holding-wide templates plus explicitly linked company forms.
    return stmt.where(
        or_(DynamicForm.scope == FormScope.HOLDING.value, DynamicForm.id.in_(ids))
    )


def serialise_form(db: Session, form: DynamicForm) -> dict:
    company_ids = list(
        db.execute(
            select(FormCompany.company_id).where(FormCompany.form_id == form.id)
        ).scalars()
    )
    published = form.published_version
    latest = form.latest_version
    field_count = (
        db.execute(
            select(func.count(FormField.id)).where(FormField.form_version_id == latest.id)
        ).scalar()
        if latest
        else 0
    )
    return {
        "id": form.id,
        "code": form.code,
        "name_ar": form.name_ar,
        "name_en": form.name_en,
        "description_ar": form.description_ar,
        "description_en": form.description_en,
        "category": form.category,
        "scope": form.scope,
        "status": form.status,
        "created_by_id": form.created_by_id,
        "created_at": form.created_at,
        "updated_at": form.updated_at,
        "company_ids": company_ids,
        "published_version_id": published.id if published else None,
        "published_version_number": published.version_number if published else None,
        "latest_version_id": latest.id if latest else None,
        "latest_version_number": latest.version_number if latest else None,
        "field_count": field_count,
    }


def serialise_field(field: FormField) -> dict:
    return {
        "id": field.id,
        "key": field.key,
        "field_type": field.field_type,
        "label_ar": field.label_ar,
        "label_en": field.label_en,
        "placeholder_ar": field.placeholder_ar,
        "placeholder_en": field.placeholder_en,
        "help_ar": field.help_ar,
        "help_en": field.help_en,
        "is_required": field.is_required,
        "is_active": field.is_active,
        "display_order": field.display_order,
        "default_value": field.default_value,
        "config": field.config,
    }


def serialise_version(db: Session, version: FormVersion) -> dict:
    from backend.services.requirement_service import serialise_requirement

    return {
        "id": version.id,
        "form_id": version.form_id,
        "version_number": version.version_number,
        "status": version.status,
        "created_at": version.created_at,
        "published_at": version.published_at,
        "fields": [serialise_field(f) for f in version.fields],
        "requirements": [serialise_requirement(r) for r in version.requirements],
    }


def get_form_scoped(db: Session, user: User, form_id: int) -> DynamicForm:
    """Fetch a form the user may see, or raise a non-leaking 404."""
    require_permission(user, Perm.FORM_READ)
    stmt = select(DynamicForm).where(DynamicForm.id == form_id)
    stmt = _apply_visibility(stmt, db, user)
    form = db.execute(stmt).scalar_one_or_none()
    if form is None:
        raise NotFoundError("Form not found.")
    return form


def get_form_or_404(db: Session, form_id: int) -> DynamicForm:
    form = db.get(DynamicForm, form_id)
    if form is None:
        raise NotFoundError("Form not found.")
    return form


def _assert_can_configure(user: User, scope: str, company_ids: list[int]) -> None:
    """A caller may only build forms within their write scope.

    A holding-wide user may create holding-scope and company-scope forms. A
    company-scoped user may only create company-scope forms for companies they
    can write.
    """
    if scope == FormScope.HOLDING.value:
        if not is_holding_wide(user):
            raise PermissionDeniedError(
                "Only Holding administrators may create holding-wide forms."
            )
        return
    if not company_ids:
        raise ValidationError("A company-scoped form needs at least one company.")
    for company_id in company_ids:
        if not can_write_company(user, company_id):
            raise PermissionDeniedError(
                "You cannot configure forms for a company you do not manage."
            )


def _replace_companies(db: Session, form: DynamicForm, company_ids: list[int]) -> None:
    db.query(FormCompany).filter(FormCompany.form_id == form.id).delete()
    for company_id in dict.fromkeys(company_ids):
        db.add(FormCompany(form_id=form.id, company_id=company_id))


def _validate_company_ids(db: Session, company_ids: list[int]) -> None:
    for company_id in dict.fromkeys(company_ids):
        if db.get(Company, company_id) is None:
            raise ValidationError(f"Company {company_id} does not exist.")


# --------------------------------------------------------------------------
# form definition CRUD
# --------------------------------------------------------------------------
def list_forms(
    db: Session,
    *,
    user: User,
    status: str | None = None,
    scope: str | None = None,
    company_id: int | None = None,
) -> list[dict]:
    require_permission(user, Perm.FORM_READ)
    stmt = select(DynamicForm).order_by(DynamicForm.created_at.desc(), DynamicForm.id.desc())
    stmt = _apply_visibility(stmt, db, user)
    if status is not None:
        stmt = stmt.where(DynamicForm.status == status)
    if scope is not None:
        stmt = stmt.where(DynamicForm.scope == scope)
    if company_id is not None:
        stmt = stmt.where(
            DynamicForm.id.in_(
                select(FormCompany.form_id).where(FormCompany.company_id == company_id)
            )
        )
    return [serialise_form(db, f) for f in db.execute(stmt).scalars()]


def create_form(
    db: Session,
    *,
    actor: User,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    require_permission(actor, Perm.FORM_CREATE)

    code = payload["code"].strip().lower()
    if db.execute(select(DynamicForm).where(DynamicForm.code == code)).scalar_one_or_none():
        raise ConflictError("A form with this code already exists.")

    scope = payload.get("scope", FormScope.COMPANY.value)
    company_ids = payload.get("company_ids") or []
    _assert_can_configure(actor, scope, company_ids)
    _validate_company_ids(db, company_ids)

    form = DynamicForm(
        code=code,
        name_ar=payload["name_ar"].strip(),
        name_en=payload["name_en"].strip(),
        description_ar=payload.get("description_ar"),
        description_en=payload.get("description_en"),
        category=payload.get("category"),
        scope=scope,
        status=FormStatus.DRAFT.value,
        created_by_id=actor.id,
    )
    db.add(form)
    db.flush()

    # Every form starts with an editable draft version.
    version = FormVersion(
        form_id=form.id,
        version_number=1,
        status=FormStatus.DRAFT.value,
        created_by_id=actor.id,
    )
    db.add(version)
    db.flush()

    if scope == FormScope.COMPANY.value:
        _replace_companies(db, form, company_ids)

    db.commit()
    db.refresh(form)

    audit_service.record(
        db,
        action=AuditAction.FORM_CREATED,
        actor_user_id=actor.id,
        entity_type="dynamic_form",
        entity_id=form.id,
        metadata={"code": form.code, "scope": scope},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return serialise_form(db, form)


def update_form(
    db: Session,
    *,
    actor: User,
    form_id: int,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    require_permission(actor, Perm.FORM_UPDATE)
    form = get_form_scoped(db, actor, form_id)

    new_scope = payload.get("scope", form.scope)
    new_company_ids = payload.get("company_ids")
    if new_company_ids is None:
        new_company_ids = list(
            db.execute(
                select(FormCompany.company_id).where(FormCompany.form_id == form.id)
            ).scalars()
        )
    _assert_can_configure(actor, new_scope, new_company_ids)
    _validate_company_ids(db, new_company_ids)

    for field in ("name_ar", "name_en", "description_ar", "description_en", "category"):
        if payload.get(field) is not None:
            setattr(form, field, payload[field])
    form.scope = new_scope
    db.add(form)

    if new_scope == FormScope.COMPANY.value:
        _replace_companies(db, form, new_company_ids)
    else:
        _replace_companies(db, form, [])

    db.commit()
    db.refresh(form)

    audit_service.record(
        db,
        action=AuditAction.FORM_UPDATED,
        actor_user_id=actor.id,
        entity_type="dynamic_form",
        entity_id=form.id,
        metadata={"fields": sorted(payload.keys())},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return serialise_form(db, form)


def get_editable_version(db: Session, *, actor: User, form: DynamicForm) -> FormVersion:
    """Return the version edits should target, forking a draft if needed.

    If the latest version is already a draft it is returned as-is. Otherwise a
    new draft is created by copying the latest version's fields and
    requirements, leaving the published version untouched.
    """
    latest = form.latest_version
    if latest is not None and latest.status == FormStatus.DRAFT.value:
        return latest

    next_number = (latest.version_number + 1) if latest else 1
    draft = FormVersion(
        form_id=form.id,
        version_number=next_number,
        status=FormStatus.DRAFT.value,
        created_by_id=actor.id,
    )
    db.add(draft)
    db.flush()

    if latest is not None:
        from backend.db.models.forms import FormRequirement

        for field in latest.fields:
            db.add(
                FormField(
                    form_version_id=draft.id,
                    key=field.key,
                    field_type=field.field_type,
                    label_ar=field.label_ar,
                    label_en=field.label_en,
                    placeholder_ar=field.placeholder_ar,
                    placeholder_en=field.placeholder_en,
                    help_ar=field.help_ar,
                    help_en=field.help_en,
                    is_required=field.is_required,
                    is_active=field.is_active,
                    display_order=field.display_order,
                    default_value=field.default_value,
                    config=field.config,
                )
            )
        for requirement in db.execute(
            select(FormRequirement).where(FormRequirement.form_version_id == latest.id)
        ).scalars():
            db.add(
                FormRequirement(
                    form_version_id=draft.id,
                    key=requirement.key,
                    name_ar=requirement.name_ar,
                    name_en=requirement.name_en,
                    description_ar=requirement.description_ar,
                    description_en=requirement.description_en,
                    requirement_type=requirement.requirement_type,
                    is_mandatory=requirement.is_mandatory,
                    is_active=requirement.is_active,
                    display_order=requirement.display_order,
                    config=requirement.config,
                )
            )
    db.flush()
    return draft


def publish_form(
    db: Session,
    *,
    actor: User,
    form_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    require_permission(actor, Perm.FORM_PUBLISH)
    form = get_form_scoped(db, actor, form_id)
    # Re-check configuration rights on the current scope.
    _assert_can_configure(
        actor,
        form.scope,
        list(
            db.execute(
                select(FormCompany.company_id).where(FormCompany.form_id == form.id)
            ).scalars()
        ),
    )

    latest = form.latest_version
    if latest is None or not latest.fields:
        raise ValidationError("A form must have at least one field before publishing.")

    # Demote any previously published version to archived (metadata only).
    for version in form.versions:
        if version.status == FormStatus.PUBLISHED.value:
            version.status = FormStatus.ARCHIVED.value
            db.add(version)

    latest.status = FormStatus.PUBLISHED.value
    latest.published_at = utcnow()
    db.add(latest)

    form.status = FormStatus.PUBLISHED.value
    db.add(form)
    db.commit()
    db.refresh(form)

    audit_service.record(
        db,
        action=AuditAction.FORM_PUBLISHED,
        actor_user_id=actor.id,
        entity_type="dynamic_form",
        entity_id=form.id,
        metadata={"version": latest.version_number},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return serialise_form(db, form)


def archive_form(
    db: Session,
    *,
    actor: User,
    form_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    require_permission(actor, Perm.FORM_ARCHIVE)
    form = get_form_scoped(db, actor, form_id)
    form.status = FormStatus.ARCHIVED.value
    db.add(form)
    db.commit()
    db.refresh(form)
    audit_service.record(
        db,
        action=AuditAction.FORM_ARCHIVED,
        actor_user_id=actor.id,
        entity_type="dynamic_form",
        entity_id=form.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return serialise_form(db, form)


def duplicate_form(
    db: Session,
    *,
    actor: User,
    form_id: int,
    new_code: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    require_permission(actor, Perm.FORM_CREATE)
    source = get_form_scoped(db, actor, form_id)
    new_code = new_code.strip().lower()
    if db.execute(select(DynamicForm).where(DynamicForm.code == new_code)).scalar_one_or_none():
        raise ConflictError("A form with this code already exists.")

    company_ids = list(
        db.execute(
            select(FormCompany.company_id).where(FormCompany.form_id == source.id)
        ).scalars()
    )
    _assert_can_configure(actor, source.scope, company_ids)

    clone = DynamicForm(
        code=new_code,
        name_ar=source.name_ar,
        name_en=source.name_en,
        description_ar=source.description_ar,
        description_en=source.description_en,
        category=source.category,
        scope=source.scope,
        status=FormStatus.DRAFT.value,
        created_by_id=actor.id,
    )
    db.add(clone)
    db.flush()

    draft = FormVersion(
        form_id=clone.id,
        version_number=1,
        status=FormStatus.DRAFT.value,
        created_by_id=actor.id,
    )
    db.add(draft)
    db.flush()

    latest = source.latest_version
    if latest is not None:
        from backend.db.models.forms import FormRequirement

        for field in latest.fields:
            db.add(
                FormField(
                    form_version_id=draft.id,
                    key=field.key,
                    field_type=field.field_type,
                    label_ar=field.label_ar,
                    label_en=field.label_en,
                    placeholder_ar=field.placeholder_ar,
                    placeholder_en=field.placeholder_en,
                    help_ar=field.help_ar,
                    help_en=field.help_en,
                    is_required=field.is_required,
                    is_active=field.is_active,
                    display_order=field.display_order,
                    default_value=field.default_value,
                    config=field.config,
                )
            )
        for requirement in db.execute(
            select(FormRequirement).where(FormRequirement.form_version_id == latest.id)
        ).scalars():
            db.add(
                FormRequirement(
                    form_version_id=draft.id,
                    key=requirement.key,
                    name_ar=requirement.name_ar,
                    name_en=requirement.name_en,
                    description_ar=requirement.description_ar,
                    description_en=requirement.description_en,
                    requirement_type=requirement.requirement_type,
                    is_mandatory=requirement.is_mandatory,
                    is_active=requirement.is_active,
                    display_order=requirement.display_order,
                    config=requirement.config,
                )
            )

    if clone.scope == FormScope.COMPANY.value:
        _replace_companies(db, clone, company_ids)

    db.commit()
    db.refresh(clone)
    audit_service.record(
        db,
        action=AuditAction.FORM_DUPLICATED,
        actor_user_id=actor.id,
        entity_type="dynamic_form",
        entity_id=clone.id,
        metadata={"source_form_id": source.id},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return serialise_form(db, clone)


# --------------------------------------------------------------------------
# version + field reads/writes
# --------------------------------------------------------------------------
def get_version(db: Session, *, user: User, form_id: int, version_id: int) -> FormVersion:
    form = get_form_scoped(db, user, form_id)
    version = db.get(FormVersion, version_id)
    if version is None or version.form_id != form.id:
        raise NotFoundError("Form version not found.")
    return version


def get_current_version(db: Session, *, user: User, form_id: int) -> FormVersion:
    """The published version if there is one, else the latest draft."""
    form = get_form_scoped(db, user, form_id)
    version = form.published_version or form.latest_version
    if version is None:
        raise NotFoundError("Form has no version.")
    return version


def add_field(
    db: Session,
    *,
    actor: User,
    form_id: int,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    require_permission(actor, Perm.FORM_UPDATE)
    form = get_form_scoped(db, actor, form_id)
    draft = get_editable_version(db, actor=actor, form=form)

    key = payload["key"].strip().lower()
    if db.execute(
        select(FormField).where(
            FormField.form_version_id == draft.id, FormField.key == key
        )
    ).scalar_one_or_none():
        raise ConflictError("A field with this key already exists on this version.")

    order = payload.get("display_order")
    if order is None or order == 0:
        order = (max([f.display_order for f in draft.fields], default=0)) + 1

    field = FormField(
        form_version_id=draft.id,
        key=key,
        field_type=payload["field_type"],
        label_ar=payload["label_ar"].strip(),
        label_en=payload["label_en"].strip(),
        placeholder_ar=payload.get("placeholder_ar"),
        placeholder_en=payload.get("placeholder_en"),
        help_ar=payload.get("help_ar"),
        help_en=payload.get("help_en"),
        is_required=bool(payload.get("is_required", False)),
        is_active=bool(payload.get("is_active", True)),
        display_order=order,
        default_value=payload.get("default_value"),
        config=payload.get("config"),
    )
    _validate_field_config(field)
    db.add(field)
    db.commit()
    db.refresh(field)

    audit_service.record(
        db,
        action=AuditAction.FORM_FIELD_ADDED,
        actor_user_id=actor.id,
        entity_type="form_field",
        entity_id=field.id,
        metadata={"form_id": form.id, "version_id": draft.id, "key": key},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return serialise_field(field)


def _validate_field_config(field: FormField) -> None:
    """Declarative validation of a field's config -- never executable."""
    from backend.db.models.enums import FieldType

    cfg = field.config or {}
    if field.field_type in (FieldType.SELECT.value, FieldType.MULTI_SELECT.value):
        options = cfg.get("options")
        if not options or not isinstance(options, list):
            raise ValidationError("Select fields need a non-empty 'options' list.")
        for option in options:
            if not isinstance(option, dict) or "value" not in option:
                raise ValidationError("Each option needs at least a 'value'.")
    if "min" in cfg and "max" in cfg:
        try:
            if float(cfg["min"]) > float(cfg["max"]):
                raise ValidationError("Field 'min' cannot exceed 'max'.")
        except (TypeError, ValueError) as exc:
            raise ValidationError("Field 'min'/'max' must be numeric.") from exc


def _require_draft_version(db: Session, *, actor: User, form_id: int) -> FormVersion:
    """Fields/requirements are edited on a draft; fork one if needed."""
    require_permission(actor, Perm.FORM_UPDATE)
    form = get_form_scoped(db, actor, form_id)
    return get_editable_version(db, actor=actor, form=form)


def update_field(
    db: Session,
    *,
    actor: User,
    form_id: int,
    field_id: int,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    require_permission(actor, Perm.FORM_UPDATE)
    form = get_form_scoped(db, actor, form_id)
    draft = get_editable_version(db, actor=actor, form=form)
    field = db.get(FormField, field_id)
    if field is None or field.form_version_id != draft.id:
        raise NotFoundError("Field not found on the editable version.")

    for attr in (
        "label_ar",
        "label_en",
        "placeholder_ar",
        "placeholder_en",
        "help_ar",
        "help_en",
        "default_value",
        "config",
    ):
        if attr in payload and payload[attr] is not None:
            setattr(field, attr, payload[attr])
    for attr in ("is_required", "is_active", "display_order"):
        if attr in payload and payload[attr] is not None:
            setattr(field, attr, payload[attr])
    _validate_field_config(field)
    db.add(field)
    db.commit()
    db.refresh(field)

    audit_service.record(
        db,
        action=AuditAction.FORM_FIELD_UPDATED,
        actor_user_id=actor.id,
        entity_type="form_field",
        entity_id=field.id,
        metadata={"form_id": form.id, "version_id": draft.id},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return serialise_field(field)


def remove_field(
    db: Session,
    *,
    actor: User,
    form_id: int,
    field_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    require_permission(actor, Perm.FORM_UPDATE)
    form = get_form_scoped(db, actor, form_id)
    draft = get_editable_version(db, actor=actor, form=form)
    field = db.get(FormField, field_id)
    if field is None or field.form_version_id != draft.id:
        raise NotFoundError("Field not found on the editable version.")
    db.delete(field)
    db.commit()
    audit_service.record(
        db,
        action=AuditAction.FORM_FIELD_REMOVED,
        actor_user_id=actor.id,
        entity_type="form_field",
        entity_id=field_id,
        metadata={"form_id": form.id, "version_id": draft.id},
        ip_address=ip_address,
        user_agent=user_agent,
    )


def reorder_fields(
    db: Session,
    *,
    actor: User,
    form_id: int,
    ordered_ids: list[int],
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> list[dict]:
    require_permission(actor, Perm.FORM_UPDATE)
    form = get_form_scoped(db, actor, form_id)
    draft = get_editable_version(db, actor=actor, form=form)

    current = {f.id: f for f in draft.fields}
    if set(ordered_ids) != set(current.keys()):
        raise ValidationError("The reorder list must contain exactly the current fields.")
    for index, field_id in enumerate(ordered_ids, start=1):
        current[field_id].display_order = index
        db.add(current[field_id])
    db.commit()
    audit_service.record(
        db,
        action=AuditAction.FORM_FIELD_REORDERED,
        actor_user_id=actor.id,
        entity_type="dynamic_form",
        entity_id=form.id,
        metadata={"version_id": draft.id},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.refresh(draft)
    return [serialise_field(f) for f in draft.fields]


__all__ = [
    "add_field",
    "archive_form",
    "create_form",
    "duplicate_form",
    "get_current_version",
    "get_editable_version",
    "get_form_or_404",
    "get_form_scoped",
    "get_version",
    "list_forms",
    "publish_form",
    "remove_field",
    "reorder_fields",
    "serialise_field",
    "serialise_form",
    "serialise_version",
    "update_field",
    "update_form",
]
