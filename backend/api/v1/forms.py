"""Dynamic forms and requirements endpoints.

Routes under ``/api/v1/forms``. Every route is permission-gated; the services
additionally apply the caller's company scope, so a company-scoped user cannot
read or configure a form belonging to another company.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response, status

from backend.api.deps import CurrentUser, DbSession, require
from backend.rbac.permissions import Perm
from backend.schemas import (
    FormCreateRequest,
    FormFieldIn,
    FormFieldOut,
    FormFieldUpdateRequest,
    FormOut,
    FormRequirementOut,
    FormUpdateRequest,
    FormVersionOut,
    ReorderRequest,
    RequirementIn,
    RequirementUpdateRequest,
)
from backend.services import audit_service, form_service, requirement_service

router = APIRouter(prefix="/forms", tags=["forms"])


# --------------------------------------------------------------------------
# form definitions
# --------------------------------------------------------------------------
@router.get("", response_model=list[FormOut])
def list_forms(
    db: DbSession,
    user: CurrentUser,
    form_status: str | None = Query(default=None, alias="status"),
    scope: str | None = Query(default=None),
    company_id: int | None = Query(default=None),
) -> list[FormOut]:
    return [
        FormOut(**row)
        for row in form_service.list_forms(
            db, user=user, status=form_status, scope=scope, company_id=company_id
        )
    ]


@router.post("", response_model=FormOut, status_code=status.HTTP_201_CREATED)
def create_form(
    payload: FormCreateRequest,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.FORM_CREATE)),
) -> FormOut:
    ctx = audit_service.request_context(request)
    row = form_service.create_form(
        db,
        actor=actor,
        payload=payload.model_dump(),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return FormOut(**row)


@router.get("/{form_id}", response_model=FormOut)
def get_form(form_id: int, db: DbSession, user: CurrentUser) -> FormOut:
    return FormOut(**form_service.serialise_form(db, form_service.get_form_scoped(db, user, form_id)))


@router.patch("/{form_id}", response_model=FormOut)
def update_form(
    form_id: int,
    payload: FormUpdateRequest,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.FORM_UPDATE)),
) -> FormOut:
    ctx = audit_service.request_context(request)
    row = form_service.update_form(
        db,
        actor=actor,
        form_id=form_id,
        payload=payload.model_dump(exclude_unset=True),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return FormOut(**row)


@router.post("/{form_id}/publish", response_model=FormOut)
def publish_form(
    form_id: int, request: Request, db: DbSession, actor=Depends(require(Perm.FORM_PUBLISH))
) -> FormOut:
    ctx = audit_service.request_context(request)
    row = form_service.publish_form(
        db,
        actor=actor,
        form_id=form_id,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return FormOut(**row)


@router.post("/{form_id}/archive", response_model=FormOut)
def archive_form(
    form_id: int, request: Request, db: DbSession, actor=Depends(require(Perm.FORM_ARCHIVE))
) -> FormOut:
    ctx = audit_service.request_context(request)
    row = form_service.archive_form(
        db,
        actor=actor,
        form_id=form_id,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return FormOut(**row)


@router.post("/{form_id}/duplicate", response_model=FormOut, status_code=status.HTTP_201_CREATED)
def duplicate_form(
    form_id: int,
    request: Request,
    db: DbSession,
    new_code: str = Query(min_length=2, max_length=60),
    actor=Depends(require(Perm.FORM_CREATE)),
) -> FormOut:
    ctx = audit_service.request_context(request)
    row = form_service.duplicate_form(
        db,
        actor=actor,
        form_id=form_id,
        new_code=new_code,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return FormOut(**row)


# --------------------------------------------------------------------------
# versions + fields
# --------------------------------------------------------------------------
@router.get("/{form_id}/versions", response_model=list[FormVersionOut])
def list_versions(form_id: int, db: DbSession, user: CurrentUser) -> list[FormVersionOut]:
    form = form_service.get_form_scoped(db, user, form_id)
    return [
        FormVersionOut(**form_service.serialise_version(db, v)) for v in form.versions
    ]


@router.get("/{form_id}/versions/{version_id}", response_model=FormVersionOut)
def get_version(
    form_id: int, version_id: int, db: DbSession, user: CurrentUser
) -> FormVersionOut:
    version = form_service.get_version(db, user=user, form_id=form_id, version_id=version_id)
    return FormVersionOut(**form_service.serialise_version(db, version))


@router.get("/{form_id}/current", response_model=FormVersionOut)
def current_version(form_id: int, db: DbSession, user: CurrentUser) -> FormVersionOut:
    version = form_service.get_current_version(db, user=user, form_id=form_id)
    return FormVersionOut(**form_service.serialise_version(db, version))


@router.post(
    "/{form_id}/fields", response_model=FormFieldOut, status_code=status.HTTP_201_CREATED
)
def add_field(
    form_id: int,
    payload: FormFieldIn,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.FORM_UPDATE)),
) -> FormFieldOut:
    ctx = audit_service.request_context(request)
    row = form_service.add_field(
        db,
        actor=actor,
        form_id=form_id,
        payload=payload.model_dump(),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return FormFieldOut(**row)


@router.patch("/{form_id}/fields/{field_id}", response_model=FormFieldOut)
def update_field(
    form_id: int,
    field_id: int,
    payload: FormFieldUpdateRequest,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.FORM_UPDATE)),
) -> FormFieldOut:
    ctx = audit_service.request_context(request)
    row = form_service.update_field(
        db,
        actor=actor,
        form_id=form_id,
        field_id=field_id,
        payload=payload.model_dump(exclude_unset=True),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return FormFieldOut(**row)


@router.delete("/{form_id}/fields/{field_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None)
def remove_field(
    form_id: int,
    field_id: int,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.FORM_UPDATE)),
) -> None:
    ctx = audit_service.request_context(request)
    form_service.remove_field(
        db,
        actor=actor,
        form_id=form_id,
        field_id=field_id,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )


@router.post("/{form_id}/fields/reorder", response_model=list[FormFieldOut])
def reorder_fields(
    form_id: int,
    payload: ReorderRequest,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.FORM_UPDATE)),
) -> list[FormFieldOut]:
    ctx = audit_service.request_context(request)
    rows = form_service.reorder_fields(
        db,
        actor=actor,
        form_id=form_id,
        ordered_ids=payload.ordered_ids,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return [FormFieldOut(**row) for row in rows]


# --------------------------------------------------------------------------
# requirements
# --------------------------------------------------------------------------
@router.get("/{form_id}/requirements", response_model=list[FormRequirementOut])
def list_requirements(
    form_id: int,
    db: DbSession,
    user: CurrentUser,
    version_id: int | None = Query(default=None),
) -> list[FormRequirementOut]:
    return [
        FormRequirementOut(**row)
        for row in requirement_service.list_requirements(
            db, user=user, form_id=form_id, version_id=version_id
        )
    ]


@router.post(
    "/{form_id}/requirements",
    response_model=FormRequirementOut,
    status_code=status.HTTP_201_CREATED,
)
def add_requirement(
    form_id: int,
    payload: RequirementIn,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.REQUIREMENT_MANAGE)),
) -> FormRequirementOut:
    ctx = audit_service.request_context(request)
    row = requirement_service.add_requirement(
        db,
        actor=actor,
        form_id=form_id,
        payload=payload.model_dump(),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return FormRequirementOut(**row)


@router.patch("/{form_id}/requirements/{requirement_id}", response_model=FormRequirementOut)
def update_requirement(
    form_id: int,
    requirement_id: int,
    payload: RequirementUpdateRequest,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.REQUIREMENT_MANAGE)),
) -> FormRequirementOut:
    ctx = audit_service.request_context(request)
    row = requirement_service.update_requirement(
        db,
        actor=actor,
        form_id=form_id,
        requirement_id=requirement_id,
        payload=payload.model_dump(exclude_unset=True),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return FormRequirementOut(**row)


@router.delete(
    "/{form_id}/requirements/{requirement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
def remove_requirement(
    form_id: int,
    requirement_id: int,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.REQUIREMENT_MANAGE)),
) -> None:
    ctx = audit_service.request_context(request)
    requirement_service.remove_requirement(
        db,
        actor=actor,
        form_id=form_id,
        requirement_id=requirement_id,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )


@router.post("/{form_id}/requirements/reorder", response_model=list[FormRequirementOut])
def reorder_requirements(
    form_id: int,
    payload: ReorderRequest,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.REQUIREMENT_MANAGE)),
) -> list[FormRequirementOut]:
    ctx = audit_service.request_context(request)
    rows = requirement_service.reorder_requirements(
        db,
        actor=actor,
        form_id=form_id,
        ordered_ids=payload.ordered_ids,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return [FormRequirementOut(**row) for row in rows]
