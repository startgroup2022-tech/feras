"""Employees, movements and assessments (S11, S12) -- D04/D05/D06.

The policy-dependent parts are deliberately *disabled*, not invented:

* creating an employee movement does **not** touch payroll or post a journal --
  it is a logged, approvable record only (D06 v1);
* approving an assessment is **blocked** while a mandatory-evidence item is
  incomplete (D05), and the block is audited;
* a leadership assessment read is gated by
  :mod:`backend.services.confidential_access_service` (D04).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.errors import ConflictError, NotFoundError, ValidationError
from backend.db.base import utcnow
from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import (
    AssessmentStatus,
    AssessmentType,
    EmployeeStatus,
    MovementStatus,
)
from backend.db.models.hr import (
    ASSESSMENT_SCORE_MAX,
    ASSESSMENT_SCORE_MIN,
    Assessment,
    AssessmentItem,
    Employee,
    EmployeeMovement,
)
from backend.db.models.identity import User
from backend.rbac.authorization import (
    accessible_company_ids,
    require_company_access,
    require_permission,
)
from backend.rbac.permissions import Perm
from backend.services import audit_service, confidential_access_service


# --------------------------------------------------------------------------
# employees
# --------------------------------------------------------------------------
def create_employee(
    db: Session,
    *,
    user: User,
    company_id: int,
    full_name_ar: str,
    full_name_en: str | None = None,
    job_title: str | None = None,
    department_id: int | None = None,
    employee_code: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    hire_date=None,
    currency: str = "SAR",
    base_salary: Decimal | None = None,
    housing_allowance: Decimal | None = None,
    transport_allowance: Decimal | None = None,
    leave_balance_days: Decimal | None = None,
    advance_balance: Decimal | None = None,
    notes: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Employee:
    require_permission(user, Perm.EMPLOYEE_MANAGE)
    require_company_access(user, company_id, write=True)

    employee = Employee(
        company_id=company_id,
        full_name_ar=full_name_ar.strip(),
        full_name_en=full_name_en,
        job_title=job_title,
        department_id=department_id,
        employee_code=employee_code,
        email=email,
        phone=phone,
        hire_date=hire_date,
        status=EmployeeStatus.ACTIVE.value,
        currency=currency,
        base_salary=base_salary,
        housing_allowance=housing_allowance,
        transport_allowance=transport_allowance,
        leave_balance_days=leave_balance_days,
        advance_balance=advance_balance,
        notes=notes,
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)

    audit_service.record(
        db,
        action=AuditAction.EMPLOYEE_CREATED,
        actor_user_id=user.id,
        entity_type="employee",
        entity_id=employee.id,
        company_id=company_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return employee


def list_employees(
    db: Session, *, user: User, company_id: int | None = None
) -> list[Employee]:
    require_permission(user, Perm.EMPLOYEE_READ)
    stmt = select(Employee).order_by(Employee.full_name_ar)
    allowed = accessible_company_ids(user)
    if allowed is not None:
        stmt = stmt.where(Employee.company_id.in_(allowed)) if allowed else stmt.where(False)
    if company_id is not None:
        stmt = stmt.where(Employee.company_id == company_id)
    return list(db.execute(stmt).scalars())


def get_employee(db: Session, *, user: User, employee_id: int) -> Employee:
    require_permission(user, Perm.EMPLOYEE_READ)
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise NotFoundError("Employee not found.")
    require_company_access(user, employee.company_id)
    return employee


def update_employee(
    db: Session, *, user: User, employee_id: int, changes: dict,
    ip_address: str | None = None, user_agent: str | None = None,
) -> Employee:
    require_permission(user, Perm.EMPLOYEE_MANAGE)
    employee = get_employee(db, user=user, employee_id=employee_id)
    require_company_access(user, employee.company_id, write=True)

    # Salary fields are sensitive and need the dedicated permission.
    salary_fields = {"base_salary", "housing_allowance", "transport_allowance", "currency"}
    if salary_fields & set(changes) and not _can_read_salary(user):
        from backend.core.errors import PermissionDeniedError

        raise PermissionDeniedError("You may not change salary information.")

    for key, value in changes.items():
        if value is not None and hasattr(employee, key):
            setattr(employee, key, value)
    db.add(employee)
    db.commit()
    db.refresh(employee)

    audit_service.record(
        db,
        action=AuditAction.EMPLOYEE_UPDATED,
        actor_user_id=user.id,
        entity_type="employee",
        entity_id=employee.id,
        company_id=employee.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"fields": sorted(changes.keys())},
    )
    return employee


def _can_read_salary(user: User) -> bool:
    from backend.rbac.authorization import has_permission

    return has_permission(user, Perm.EMPLOYEE_SALARY_READ)


def serialise_employee(employee: Employee, *, include_salary: bool) -> dict:
    data = {
        "id": employee.id,
        "company_id": employee.company_id,
        "employee_code": employee.employee_code,
        "full_name_ar": employee.full_name_ar,
        "full_name_en": employee.full_name_en,
        "job_title": employee.job_title,
        "department_id": employee.department_id,
        "manager_id": employee.manager_id,
        "hire_date": employee.hire_date,
        "status": employee.status,
        "email": employee.email,
        "phone": employee.phone,
        "leave_balance_days": employee.leave_balance_days,
        "advance_balance": employee.advance_balance,
        "is_active": employee.is_active,
        "notes": employee.notes,
        "created_at": employee.created_at,
        "updated_at": employee.updated_at,
    }
    if include_salary:
        data.update(
            {
                "currency": employee.currency,
                "base_salary": employee.base_salary,
                "housing_allowance": employee.housing_allowance,
                "transport_allowance": employee.transport_allowance,
            }
        )
    return data


# --------------------------------------------------------------------------
# movements (D06 v1: logged + approvable; no payroll/accounting link)
# --------------------------------------------------------------------------
def create_movement(
    db: Session,
    *,
    user: User,
    employee_id: int,
    movement_type: str,
    effective_date=None,
    days: Decimal | None = None,
    amount: Decimal | None = None,
    currency: str = "SAR",
    reason: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> EmployeeMovement:
    require_permission(user, Perm.EMPLOYEE_MOVEMENT_MANAGE)
    employee = get_employee(db, user=user, employee_id=employee_id)
    require_company_access(user, employee.company_id, write=True)

    movement = EmployeeMovement(
        employee_id=employee.id,
        company_id=employee.company_id,
        movement_type=movement_type,
        effective_date=effective_date,
        days=days,
        amount=amount,
        currency=currency,
        reason=reason,
        status=MovementStatus.PENDING.value,
        requested_by_id=user.id,
    )
    db.add(movement)
    db.commit()
    db.refresh(movement)

    audit_service.record(
        db,
        action=AuditAction.EMPLOYEE_MOVEMENT_CREATED,
        actor_user_id=user.id,
        entity_type="employee_movement",
        entity_id=movement.id,
        company_id=employee.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"movement_type": movement_type},
    )
    return movement


def decide_movement(
    db: Session,
    *,
    user: User,
    movement_id: int,
    approve: bool,
    note: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> EmployeeMovement:
    require_permission(user, Perm.EMPLOYEE_MOVEMENT_APPROVE)
    movement = db.get(EmployeeMovement, movement_id)
    if movement is None:
        raise NotFoundError("Movement not found.")
    require_company_access(user, movement.company_id, write=True)
    if movement.status != MovementStatus.PENDING.value:
        raise ConflictError("This movement has already been decided.")

    movement.status = MovementStatus.APPROVED.value if approve else MovementStatus.REJECTED.value
    movement.decided_by_id = user.id
    movement.decided_at = utcnow()
    movement.decision_note = note
    db.add(movement)
    db.commit()
    db.refresh(movement)

    audit_service.record(
        db,
        action=AuditAction.EMPLOYEE_MOVEMENT_DECIDED,
        actor_user_id=user.id,
        entity_type="employee_movement",
        entity_id=movement.id,
        company_id=movement.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"approved": approve},
    )
    # D06 v1: approval changes the logged status only. It deliberately does NOT
    # adjust the employee balance, create a payroll entry or post a journal --
    # those await an approved linking policy.
    return movement


def list_movements(db: Session, *, user: User, employee_id: int) -> list[EmployeeMovement]:
    require_permission(user, Perm.EMPLOYEE_MOVEMENT_READ)
    employee = get_employee(db, user=user, employee_id=employee_id)
    return list(
        db.execute(
            select(EmployeeMovement)
            .where(EmployeeMovement.employee_id == employee.id)
            .order_by(EmployeeMovement.created_at.desc())
        ).scalars()
    )


def serialise_movement(movement: EmployeeMovement) -> dict:
    return {
        "id": movement.id,
        "employee_id": movement.employee_id,
        "company_id": movement.company_id,
        "movement_type": movement.movement_type,
        "effective_date": movement.effective_date,
        "days": movement.days,
        "amount": movement.amount,
        "currency": movement.currency,
        "reason": movement.reason,
        "status": movement.status,
        "requested_by_id": movement.requested_by_id,
        "decided_by_id": movement.decided_by_id,
        "decided_at": movement.decided_at,
        "decision_note": movement.decision_note,
        "created_at": movement.created_at,
    }


# --------------------------------------------------------------------------
# assessments (D05)
# --------------------------------------------------------------------------
def create_assessment(
    db: Session,
    *,
    user: User,
    company_id: int,
    period_label: str,
    assessment_type: str = AssessmentType.EMPLOYEE.value,
    employee_id: int | None = None,
    subject_user_id: int | None = None,
    summary: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Assessment:
    require_permission(user, Perm.ASSESSMENT_MANAGE)
    require_company_access(user, company_id, write=True)

    if assessment_type == AssessmentType.EMPLOYEE.value and employee_id is None:
        raise ValidationError("An employee assessment requires an employee.")
    if assessment_type == AssessmentType.LEADERSHIP.value and subject_user_id is None:
        raise ValidationError("A leadership assessment requires a subject user.")

    assessment = Assessment(
        company_id=company_id,
        employee_id=employee_id,
        subject_user_id=subject_user_id,
        assessment_type=assessment_type,
        period_label=period_label,
        status=AssessmentStatus.DRAFT.value,
        summary=summary,
        created_by_id=user.id,
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)

    audit_service.record(
        db,
        action=AuditAction.ASSESSMENT_CREATED,
        actor_user_id=user.id,
        entity_type="assessment",
        entity_id=assessment.id,
        company_id=company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"assessment_type": assessment_type},
    )
    return assessment


def set_assessment_item(
    db: Session,
    *,
    user: User,
    assessment_id: int,
    criterion_code: str,
    criterion_name_ar: str,
    criterion_name_en: str | None = None,
    weight: Decimal = Decimal("1"),
    score: Decimal | None = None,
    evidence_required: bool = False,
    evidence_text: str | None = None,
    evidence_complete: bool = False,
    comment: str | None = None,
) -> AssessmentItem:
    require_permission(user, Perm.ASSESSMENT_MANAGE)
    assessment = _get_assessment(db, user=user, assessment_id=assessment_id)
    require_company_access(user, assessment.company_id, write=True)
    if assessment.status == AssessmentStatus.APPROVED.value:
        raise ConflictError("An approved assessment is immutable; create a new one.")

    if score is not None and not (ASSESSMENT_SCORE_MIN <= score <= ASSESSMENT_SCORE_MAX):
        raise ValidationError(
            f"Score must be between {ASSESSMENT_SCORE_MIN} and {ASSESSMENT_SCORE_MAX}."
        )

    item = db.execute(
        select(AssessmentItem).where(
            AssessmentItem.assessment_id == assessment.id,
            AssessmentItem.criterion_code == criterion_code,
        )
    ).scalar_one_or_none()
    if item is None:
        item = AssessmentItem(assessment_id=assessment.id, criterion_code=criterion_code,
                              criterion_name_ar=criterion_name_ar)
        db.add(item)
    item.criterion_name_ar = criterion_name_ar
    item.criterion_name_en = criterion_name_en
    item.weight = weight
    item.score = score
    item.evidence_required = evidence_required
    item.evidence_text = evidence_text
    item.evidence_complete = evidence_complete
    item.comment = comment
    db.commit()
    db.refresh(item)

    audit_service.record(
        db,
        action=AuditAction.ASSESSMENT_UPDATED,
        actor_user_id=user.id,
        entity_type="assessment",
        entity_id=assessment.id,
        company_id=assessment.company_id,
        metadata={"criterion": criterion_code},
    )
    return item


def approve_assessment(
    db: Session,
    *,
    user: User,
    assessment_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Assessment:
    """Approve an assessment, enforcing the D05 mandatory-evidence rule."""
    require_permission(user, Perm.ASSESSMENT_APPROVE)
    assessment = _get_assessment(db, user=user, assessment_id=assessment_id)
    require_company_access(user, assessment.company_id, write=True)

    # D05: an assessment missing mandatory evidence cannot be approved.
    if assessment.has_evidence_gap:
        audit_service.record(
            db,
            action=AuditAction.ASSESSMENT_APPROVAL_BLOCKED,
            actor_user_id=user.id,
            entity_type="assessment",
            entity_id=assessment.id,
            company_id=assessment.company_id,
            metadata={"reason": "evidence_gap"},
        )
        raise ValidationError(
            "This assessment has a mandatory-evidence gap and cannot be approved."
        )

    assessment.status = AssessmentStatus.APPROVED.value
    assessment.approved_by_id = user.id
    assessment.approved_at = utcnow()
    assessment.overall_score = _weighted_score(assessment)
    db.add(assessment)
    db.commit()
    db.refresh(assessment)

    audit_service.record(
        db,
        action=AuditAction.ASSESSMENT_APPROVED,
        actor_user_id=user.id,
        entity_type="assessment",
        entity_id=assessment.id,
        company_id=assessment.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return assessment


def _weighted_score(assessment: Assessment) -> Decimal | None:
    total_weight = Decimal("0")
    weighted = Decimal("0")
    for item in assessment.items:
        if item.score is None:
            continue
        total_weight += item.weight
        weighted += item.score * item.weight
    if total_weight == 0:
        return None
    return (weighted / total_weight).quantize(Decimal("0.01"))


def _get_assessment(db: Session, *, user: User, assessment_id: int) -> Assessment:
    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise NotFoundError("Assessment not found.")
    if assessment.assessment_type == AssessmentType.LEADERSHIP.value:
        # D04: leadership assessments are confidential.
        confidential_access_service.require_confidential_read(
            db,
            user=user,
            subject_type="leadership_assessment",
            subject_id=assessment.id,
            permission=Perm.ASSESSMENT_READ,
        )
    else:
        require_company_access(user, assessment.company_id)
    return assessment


def list_assessments(
    db: Session, *, user: User, company_id: int | None = None,
    assessment_type: str = AssessmentType.EMPLOYEE.value,
) -> list[Assessment]:
    require_permission(user, Perm.ASSESSMENT_READ)
    stmt = select(Assessment).where(Assessment.assessment_type == assessment_type)
    if assessment_type == AssessmentType.LEADERSHIP.value:
        # Only the owner (or grantees) may list leadership assessments; a
        # non-owner sees nothing here.
        if not confidential_access_service.is_confidential_owner(user):
            return []
    else:
        allowed = accessible_company_ids(user)
        if allowed is not None:
            stmt = stmt.where(Assessment.company_id.in_(allowed)) if allowed else stmt.where(False)
    if company_id is not None:
        stmt = stmt.where(Assessment.company_id == company_id)
    stmt = stmt.order_by(Assessment.created_at.desc())
    return list(db.execute(stmt).scalars())


def serialise_assessment(assessment: Assessment) -> dict:
    return {
        "id": assessment.id,
        "company_id": assessment.company_id,
        "employee_id": assessment.employee_id,
        "subject_user_id": assessment.subject_user_id,
        "assessment_type": assessment.assessment_type,
        "period_label": assessment.period_label,
        "status": assessment.status,
        "overall_score": assessment.overall_score,
        "summary": assessment.summary,
        "has_evidence_gap": assessment.has_evidence_gap,
        "created_by_id": assessment.created_by_id,
        "approved_by_id": assessment.approved_by_id,
        "approved_at": assessment.approved_at,
        "created_at": assessment.created_at,
        "items": [
            {
                "id": item.id,
                "criterion_code": item.criterion_code,
                "criterion_name_ar": item.criterion_name_ar,
                "criterion_name_en": item.criterion_name_en,
                "weight": item.weight,
                "score": item.score,
                "evidence_required": item.evidence_required,
                "evidence_text": item.evidence_text,
                "evidence_complete": item.evidence_complete,
                "comment": item.comment,
            }
            for item in assessment.items
        ],
    }
