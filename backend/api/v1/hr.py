"""Employee and assessment endpoints (S11, S12) -- D04/D05/D06."""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from backend.api.deps import CurrentUser, DbSession
from backend.rbac.authorization import has_permission, require_permission
from backend.rbac.permissions import Perm
from backend.schemas.domain import (
    AssessmentCreateRequest,
    AssessmentItemRequest,
    EmployeeCreateRequest,
    EmployeeMovementCreateRequest,
    EmployeeMovementDecisionRequest,
    EmployeeUpdateRequest,
)
from backend.services import audit_service, hr_service
from backend.services.assessment_criteria import (
    criteria_for_template,
    template_for_role,
    template_keys,
)

router = APIRouter(prefix="/employees", tags=["employees"])


def _serialise_employee(user, employee) -> dict:
    return hr_service.serialise_employee(
        employee, include_salary=has_permission(user, Perm.EMPLOYEE_SALARY_READ)
    )


@router.get("")
def list_employees(
    user: CurrentUser, db: DbSession, company_id: int | None = None
) -> list[dict]:
    employees = hr_service.list_employees(db, user=user, company_id=company_id)
    return [_serialise_employee(user, e) for e in employees]


@router.get("/{employee_id}")
def get_employee(employee_id: int, user: CurrentUser, db: DbSession) -> dict:
    return _serialise_employee(user, hr_service.get_employee(db, user=user, employee_id=employee_id))


@router.post("", status_code=status.HTTP_201_CREATED)
def create_employee(
    payload: EmployeeCreateRequest, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    ctx = audit_service.request_context(request)
    employee = hr_service.create_employee(
        db, user=user, **payload.model_dump(), **ctx
    )
    return _serialise_employee(user, employee)


@router.patch("/{employee_id}")
def update_employee(
    employee_id: int, payload: EmployeeUpdateRequest, request: Request,
    user: CurrentUser, db: DbSession,
) -> dict:
    ctx = audit_service.request_context(request)
    changes = payload.model_dump(exclude_unset=True)
    if "status" in changes and changes["status"] is not None:
        changes["status"] = changes["status"].value
    employee = hr_service.update_employee(
        db, user=user, employee_id=employee_id, changes=changes, **ctx
    )
    return _serialise_employee(user, employee)


# ---- movements (D06 v1) ----
@router.get("/{employee_id}/movements")
def list_movements(employee_id: int, user: CurrentUser, db: DbSession) -> list[dict]:
    return [
        hr_service.serialise_movement(m)
        for m in hr_service.list_movements(db, user=user, employee_id=employee_id)
    ]


@router.post("/{employee_id}/movements", status_code=status.HTTP_201_CREATED)
def create_movement(
    employee_id: int, payload: EmployeeMovementCreateRequest, request: Request,
    user: CurrentUser, db: DbSession,
) -> dict:
    ctx = audit_service.request_context(request)
    data = payload.model_dump()
    data["movement_type"] = payload.movement_type.value
    movement = hr_service.create_movement(
        db, user=user, employee_id=employee_id, **data, **ctx
    )
    return hr_service.serialise_movement(movement)


@router.post("/movements/{movement_id}/decision")
def decide_movement(
    movement_id: int, payload: EmployeeMovementDecisionRequest, request: Request,
    user: CurrentUser, db: DbSession,
) -> dict:
    ctx = audit_service.request_context(request)
    movement = hr_service.decide_movement(
        db, user=user, movement_id=movement_id, approve=payload.approve,
        note=payload.note, **ctx,
    )
    return hr_service.serialise_movement(movement)


# ---- assessments (D05) ----
@router.get("/assessments/criteria")
def assessment_criteria(user: CurrentUser) -> dict:
    """The role assessment criteria and their fixed weights (Table 72, AC-12).

    Read-only reference data: the specification fixes both the criteria and the
    weights per role. ``?template=accountant`` returns one template; a role code
    is also accepted (``?template=business_development`` resolves to its
    leadership template).
    """
    require_permission(user, Perm.ASSESSMENT_READ)
    key = template_for_role(user.role_code) or "accountant"
    return {
        "templates": {
            k: criteria_for_template(k) for k in template_keys()
        },
        "default_template": key,
    }


@router.get("/assessments/list")
def list_assessments(
    user: CurrentUser, db: DbSession, company_id: int | None = None,
    assessment_type: str | None = None,
) -> list[dict]:
    return [
        hr_service.serialise_assessment(a)
        for a in hr_service.list_assessments(
            db, user=user, company_id=company_id, assessment_type=assessment_type
        )
    ]


@router.post("/assessments", status_code=status.HTTP_201_CREATED)
def create_assessment(
    payload: AssessmentCreateRequest, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    ctx = audit_service.request_context(request)
    data = payload.model_dump()
    data["assessment_type"] = payload.assessment_type.value
    assessment = hr_service.create_assessment(db, user=user, **data, **ctx)
    return hr_service.serialise_assessment(assessment)


@router.post("/assessments/{assessment_id}/items")
def set_assessment_item(
    assessment_id: int, payload: AssessmentItemRequest, user: CurrentUser, db: DbSession
) -> dict:
    hr_service.set_assessment_item(
        db, user=user, assessment_id=assessment_id, **payload.model_dump()
    )
    assessment = hr_service._get_assessment(db, user=user, assessment_id=assessment_id)
    return hr_service.serialise_assessment(assessment)


@router.post("/assessments/{assessment_id}/approve")
def approve_assessment(
    assessment_id: int, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    ctx = audit_service.request_context(request)
    assessment = hr_service.approve_assessment(
        db, user=user, assessment_id=assessment_id, **ctx
    )
    return hr_service.serialise_assessment(assessment)
