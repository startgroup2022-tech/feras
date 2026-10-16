"""Form submission, request and approval endpoints.

``/api/v1/form-submissions`` covers the request lifecycle (create, edit,
upload requirement documents, submit, cancel, detail) and
``/api/v1/approvals`` covers the approver's inbox and actions.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status

from backend.api.deps import CurrentUser, DbSession, require
from backend.core.errors import NotFoundError, PermissionDeniedError
from backend.db.models.enums import DocumentEntityType
from backend.db.models.submissions import SubmissionRequirement
from backend.rbac.authorization import has_permission
from backend.rbac.permissions import Perm
from backend.schemas import (
    ApprovalActionRequest,
    DocumentOut,
    PageOut,
    RequirementOverrideRequest,
    SubmissionCreateRequest,
    SubmissionDetailOut,
    SubmissionOut,
    SubmissionSubmitRequest,
    SubmissionUpdateRequest,
)
from backend.services import (
    approval_service,
    audit_service,
    document_service,
    submission_service,
)

router = APIRouter(prefix="/form-submissions", tags=["form-submissions"])
approvals_router = APIRouter(prefix="/approvals", tags=["approvals"])


def _out(row: dict) -> SubmissionOut:
    return SubmissionOut(**row)


# --------------------------------------------------------------------------
# listing / creation
# --------------------------------------------------------------------------
@router.get("", response_model=PageOut)
def list_submissions(
    db: DbSession,
    user: CurrentUser,
    mine: bool = Query(default=False),
    company_id: int | None = Query(default=None),
    submission_status: str | None = Query(default=None, alias="status"),
    form_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PageOut:
    return PageOut(
        **submission_service.list_submissions(
            db,
            user=user,
            mine=mine,
            company_id=company_id,
            status=submission_status,
            form_id=form_id,
            limit=limit,
            offset=offset,
        )
    )


@router.post("", response_model=SubmissionOut, status_code=status.HTTP_201_CREATED)
def create_submission(
    payload: SubmissionCreateRequest,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.FORM_SUBMIT)),
) -> SubmissionOut:
    ctx = audit_service.request_context(request)
    submission = submission_service.create_submission(
        db,
        actor=actor,
        payload=payload.model_dump(),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return _out(submission_service.serialise(db, submission))


@router.get("/{submission_id}", response_model=SubmissionDetailOut)
def get_submission(submission_id: int, db: DbSession, user: CurrentUser) -> SubmissionDetailOut:
    return SubmissionDetailOut(**submission_service.detail(db, user=user, submission_id=submission_id))


@router.patch("/{submission_id}", response_model=SubmissionOut)
def update_submission(
    submission_id: int,
    payload: SubmissionUpdateRequest,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.FORM_SUBMIT)),
) -> SubmissionOut:
    ctx = audit_service.request_context(request)
    submission = submission_service.update_submission(
        db,
        actor=actor,
        submission_id=submission_id,
        payload=payload.model_dump(exclude_unset=True),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return _out(submission_service.serialise(db, submission))


@router.post("/{submission_id}/submit", response_model=SubmissionOut)
def submit_submission(
    submission_id: int,
    payload: SubmissionSubmitRequest,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.FORM_SUBMIT)),
) -> SubmissionOut:
    ctx = audit_service.request_context(request)
    submission = submission_service.submit_submission(
        db,
        actor=actor,
        submission_id=submission_id,
        override_requirements=payload.override_requirements,
        override_reason=payload.override_reason,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return _out(submission_service.serialise(db, submission))


@router.post("/{submission_id}/cancel", response_model=SubmissionOut)
def cancel_submission(
    submission_id: int,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.SUBMISSION_CANCEL)),
) -> SubmissionOut:
    ctx = audit_service.request_context(request)
    submission = submission_service.cancel_submission(
        db,
        actor=actor,
        submission_id=submission_id,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return _out(submission_service.serialise(db, submission))


# --------------------------------------------------------------------------
# requirements: acknowledge / override / upload
# --------------------------------------------------------------------------
@router.post(
    "/{submission_id}/requirements/{requirement_id}/acknowledge",
    response_model=dict,
)
def acknowledge_requirement(
    submission_id: int,
    requirement_id: int,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.FORM_SUBMIT)),
) -> dict:
    ctx = audit_service.request_context(request)
    return submission_service.acknowledge_requirement(
        db,
        actor=actor,
        submission_id=submission_id,
        requirement_id=requirement_id,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )


@router.post(
    "/{submission_id}/requirements/{requirement_id}/override",
    response_model=dict,
)
def override_requirement(
    submission_id: int,
    requirement_id: int,
    payload: RequirementOverrideRequest,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.APPROVAL_OVERRIDE)),
) -> dict:
    ctx = audit_service.request_context(request)
    return submission_service.override_requirement(
        db,
        actor=actor,
        submission_id=submission_id,
        requirement_id=requirement_id,
        reason=payload.reason,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )


@router.post(
    "/{submission_id}/requirements/{requirement_id}/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_requirement_document(
    submission_id: int,
    requirement_id: int,
    request: Request,
    db: DbSession,
    file: UploadFile = File(...),
    actor=Depends(require(Perm.DOCUMENT_UPLOAD)),
) -> DocumentOut:
    """Upload a document that satisfies a specific requirement.

    The requirement must belong to the submission, and the submission must be
    one the caller can see -- both checked against the database, never trusted
    from the URL.
    """
    ctx = audit_service.request_context(request)
    submission = submission_service.get_submission_scoped(db, actor, submission_id)
    if submission.submitted_by_id != actor.id and not has_permission(
        actor, Perm.DOCUMENT_UPDATE
    ):
        raise PermissionDeniedError("You may only add documents to your own request.")

    requirement = db.get(SubmissionRequirement, requirement_id)
    if requirement is None or requirement.submission_id != submission.id:
        raise NotFoundError("Requirement not found on this request.")

    data = await file.read()
    document = document_service.upload_document(
        db,
        actor=actor,
        company_id=submission.company_id,
        filename=file.filename or "",
        content_type=file.content_type,
        data=data,
        title_ar=requirement.name_ar,
        title_en=requirement.name_en,
        related_entity_type=DocumentEntityType.SUBMISSION_REQUIREMENT.value,
        related_entity_id=requirement.id,
        submission_id=submission.id,
        submission_requirement_id=requirement.id,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    # Re-evaluate completeness now that a document exists.
    submission_service.evaluate_requirements(db, submission)
    db.commit()
    return DocumentOut(**document_service.serialise_document(db, document))


# --------------------------------------------------------------------------
# approvals
# --------------------------------------------------------------------------
@approvals_router.get("/my", response_model=PageOut)
def my_approvals(
    db: DbSession,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PageOut:
    """Requests currently waiting for the caller's action."""
    return PageOut(**approval_service.my_approvals(db, user=user, limit=limit, offset=offset))


@approvals_router.post("/tasks/{task_id}", response_model=SubmissionOut)
def act_on_task(
    task_id: int,
    payload: ApprovalActionRequest,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.APPROVAL_ACT)),
) -> SubmissionOut:
    ctx = audit_service.request_context(request)
    instance = approval_service.act(
        db,
        actor=actor,
        task_id=task_id,
        decision=payload.decision.value,
        comment=payload.comment,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    submission = submission_service.get_submission_or_404(db, instance.submission_id)
    return _out(submission_service.serialise(db, submission))
