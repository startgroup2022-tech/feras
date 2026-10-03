"""Workflow builder endpoints under ``/api/v1/workflows``."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response, status

from backend.api.deps import CurrentUser, DbSession, require
from backend.rbac.permissions import Perm
from backend.schemas import (
    ReorderRequest,
    WorkflowCreateRequest,
    WorkflowOut,
    WorkflowStepIn,
    WorkflowStepOut,
    WorkflowStepUpdateRequest,
    WorkflowUpdateRequest,
    WorkflowVersionOut,
)
from backend.services import audit_service, workflow_service

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("", response_model=list[WorkflowOut])
def list_workflows(
    db: DbSession,
    user: CurrentUser,
    form_id: int | None = Query(default=None),
    workflow_status: str | None = Query(default=None, alias="status"),
) -> list[WorkflowOut]:
    return [
        WorkflowOut(**row)
        for row in workflow_service.list_workflows(
            db, user=user, form_id=form_id, status=workflow_status
        )
    ]


@router.post("", response_model=WorkflowOut, status_code=status.HTTP_201_CREATED)
def create_workflow(
    payload: WorkflowCreateRequest,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.WORKFLOW_CREATE)),
) -> WorkflowOut:
    ctx = audit_service.request_context(request)
    row = workflow_service.create_workflow(
        db,
        actor=actor,
        payload=payload.model_dump(),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return WorkflowOut(**row)


@router.get("/{workflow_id}", response_model=WorkflowOut)
def get_workflow(workflow_id: int, db: DbSession, user: CurrentUser) -> WorkflowOut:
    definition = workflow_service.get_workflow_scoped(db, user, workflow_id)
    return WorkflowOut(**workflow_service.serialise_definition(db, definition))


@router.patch("/{workflow_id}", response_model=WorkflowOut)
def update_workflow(
    workflow_id: int,
    payload: WorkflowUpdateRequest,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.WORKFLOW_UPDATE)),
) -> WorkflowOut:
    ctx = audit_service.request_context(request)
    row = workflow_service.update_workflow(
        db,
        actor=actor,
        workflow_id=workflow_id,
        payload=payload.model_dump(exclude_unset=True),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return WorkflowOut(**row)


@router.post("/{workflow_id}/publish", response_model=WorkflowOut)
def publish_workflow(
    workflow_id: int, request: Request, db: DbSession, actor=Depends(require(Perm.WORKFLOW_PUBLISH))
) -> WorkflowOut:
    ctx = audit_service.request_context(request)
    row = workflow_service.publish_workflow(
        db,
        actor=actor,
        workflow_id=workflow_id,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return WorkflowOut(**row)


@router.post("/{workflow_id}/archive", response_model=WorkflowOut)
def archive_workflow(
    workflow_id: int, request: Request, db: DbSession, actor=Depends(require(Perm.WORKFLOW_ARCHIVE))
) -> WorkflowOut:
    ctx = audit_service.request_context(request)
    row = workflow_service.archive_workflow(
        db,
        actor=actor,
        workflow_id=workflow_id,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return WorkflowOut(**row)


@router.post(
    "/{workflow_id}/duplicate", response_model=WorkflowOut, status_code=status.HTTP_201_CREATED
)
def duplicate_workflow(
    workflow_id: int,
    request: Request,
    db: DbSession,
    new_code: str = Query(min_length=2, max_length=60),
    actor=Depends(require(Perm.WORKFLOW_CREATE)),
) -> WorkflowOut:
    ctx = audit_service.request_context(request)
    row = workflow_service.duplicate_workflow(
        db,
        actor=actor,
        workflow_id=workflow_id,
        new_code=new_code,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return WorkflowOut(**row)


# --------------------------------------------------------------------------
# versions + steps
# --------------------------------------------------------------------------
@router.get("/{workflow_id}/versions", response_model=list[WorkflowVersionOut])
def list_versions(
    workflow_id: int, db: DbSession, user: CurrentUser
) -> list[WorkflowVersionOut]:
    definition = workflow_service.get_workflow_scoped(db, user, workflow_id)
    return [
        WorkflowVersionOut(**workflow_service.serialise_version(v))
        for v in definition.versions
    ]


@router.get("/{workflow_id}/current", response_model=WorkflowVersionOut)
def current_version(
    workflow_id: int, db: DbSession, user: CurrentUser
) -> WorkflowVersionOut:
    definition = workflow_service.get_workflow_scoped(db, user, workflow_id)
    version = definition.published_version or definition.latest_version
    return WorkflowVersionOut(**workflow_service.serialise_version(version))


@router.post(
    "/{workflow_id}/steps", response_model=WorkflowStepOut, status_code=status.HTTP_201_CREATED
)
def add_step(
    workflow_id: int,
    payload: WorkflowStepIn,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.WORKFLOW_UPDATE)),
) -> WorkflowStepOut:
    ctx = audit_service.request_context(request)
    row = workflow_service.add_step(
        db,
        actor=actor,
        workflow_id=workflow_id,
        payload=payload.model_dump(),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return WorkflowStepOut(**row)


@router.patch("/{workflow_id}/steps/{step_id}", response_model=WorkflowStepOut)
def update_step(
    workflow_id: int,
    step_id: int,
    payload: WorkflowStepUpdateRequest,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.WORKFLOW_UPDATE)),
) -> WorkflowStepOut:
    ctx = audit_service.request_context(request)
    row = workflow_service.update_step(
        db,
        actor=actor,
        workflow_id=workflow_id,
        step_id=step_id,
        payload=payload.model_dump(exclude_unset=True),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return WorkflowStepOut(**row)


@router.delete("/{workflow_id}/steps/{step_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None)
def remove_step(
    workflow_id: int,
    step_id: int,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.WORKFLOW_UPDATE)),
) -> None:
    ctx = audit_service.request_context(request)
    workflow_service.remove_step(
        db,
        actor=actor,
        workflow_id=workflow_id,
        step_id=step_id,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )


@router.post("/{workflow_id}/steps/reorder", response_model=list[WorkflowStepOut])
def reorder_steps(
    workflow_id: int,
    payload: ReorderRequest,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.WORKFLOW_UPDATE)),
) -> list[WorkflowStepOut]:
    ctx = audit_service.request_context(request)
    rows = workflow_service.reorder_steps(
        db,
        actor=actor,
        workflow_id=workflow_id,
        ordered_ids=payload.ordered_ids,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return [WorkflowStepOut(**row) for row in rows]
