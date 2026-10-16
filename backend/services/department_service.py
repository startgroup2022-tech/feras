"""Department service.

Departments belong to a company. Reads and writes are permission-checked, and
a company-scoped user only sees departments of the companies granted to them --
the company scope is applied as a SQL filter, exactly like the other scoped
repositories, so an out-of-scope company id simply matches nothing.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.errors import ConflictError, NotFoundError, ValidationError
from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import DepartmentStatus
from backend.db.models.group import Department
from backend.db.models.identity import Company, User
from backend.rbac.authorization import accessible_company_ids, require_permission
from backend.rbac.permissions import Perm
from backend.services import audit_service


def _serialize(db: Session, department: Department) -> dict:
    company = db.get(Company, department.company_id)
    manager = db.get(User, department.manager_user_id) if department.manager_user_id else None
    return {
        "id": department.id,
        "company_id": department.company_id,
        "code": department.code,
        "name_ar": department.name_ar,
        "name_en": department.name_en,
        "manager_user_id": department.manager_user_id,
        "parent_department_id": department.parent_department_id,
        "status": department.status,
        "notes": department.notes,
        "company_name_ar": company.name_ar if company else None,
        "company_name_en": company.name_en if company else None,
        "manager_name_ar": manager.full_name_ar if manager else None,
        "manager_name_en": (manager.full_name_en if manager else None),
    }


def _assert_company_visible(user: User, company_id: int) -> None:
    allowed = accessible_company_ids(user)
    if allowed is not None and company_id not in allowed:
        # Same error as a missing company, so scope cannot be probed for ids.
        raise NotFoundError("Company not found.")


def list_departments(
    db: Session, *, user: User, company_id: int | None = None
) -> list[dict]:
    require_permission(user, Perm.DEPARTMENT_READ)
    stmt = select(Department).order_by(Department.company_id, Department.name_en)
    allowed = accessible_company_ids(user)
    if allowed is not None:
        if not allowed:
            return []
        stmt = stmt.where(Department.company_id.in_(allowed))
    if company_id is not None:
        _assert_company_visible(user, company_id)
        stmt = stmt.where(Department.company_id == company_id)
    return [_serialize(db, row) for row in db.execute(stmt).scalars()]


def get_department(db: Session, *, user: User, department_id: int) -> dict:
    require_permission(user, Perm.DEPARTMENT_READ)
    department = db.get(Department, department_id)
    if department is None:
        raise NotFoundError("Department not found.")
    _assert_company_visible(user, department.company_id)
    return _serialize(db, department)


def create_department(
    db: Session,
    *,
    actor: User,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    require_permission(actor, Perm.DEPARTMENT_MANAGE)
    company = db.get(Company, payload["company_id"])
    if company is None:
        raise NotFoundError("Company not found.")
    _assert_company_visible(actor, company.id)

    code = payload["code"].strip().upper()
    if db.execute(
        select(Department).where(
            Department.company_id == company.id, Department.code == code
        )
    ).scalar_one_or_none():
        raise ConflictError("A department with this code already exists for the company.")

    parent_id = payload.get("parent_department_id")
    if parent_id is not None:
        parent = db.get(Department, parent_id)
        if parent is None or parent.company_id != company.id:
            raise ValidationError("Parent department must belong to the same company.")

    department = Department(
        company_id=company.id,
        code=code,
        name_ar=payload["name_ar"],
        name_en=payload["name_en"],
        manager_user_id=payload.get("manager_user_id"),
        parent_department_id=parent_id,
        status=DepartmentStatus.ACTIVE.value,
        notes=payload.get("notes"),
    )
    db.add(department)
    db.commit()
    db.refresh(department)

    audit_service.record(
        db,
        action=AuditAction.DEPARTMENT_CREATED,
        actor_user_id=actor.id,
        entity_type="department",
        entity_id=department.id,
        company_id=company.id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"code": code},
    )
    return _serialize(db, department)


def update_department(
    db: Session,
    *,
    actor: User,
    department_id: int,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    require_permission(actor, Perm.DEPARTMENT_MANAGE)
    department = db.get(Department, department_id)
    if department is None:
        raise NotFoundError("Department not found.")
    _assert_company_visible(actor, department.company_id)

    if payload.get("code") is not None:
        code = payload["code"].strip().upper()
        clash = db.execute(
            select(Department).where(
                Department.company_id == department.company_id,
                Department.code == code,
                Department.id != department.id,
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise ConflictError("A department with this code already exists for the company.")
        department.code = code

    for field in ("name_ar", "name_en", "notes", "manager_user_id", "status"):
        if field in payload and payload[field] is not None:
            setattr(department, field, payload[field])

    if payload.get("parent_department_id") is not None:
        parent_id = payload["parent_department_id"]
        if parent_id == department.id:
            raise ValidationError("A department cannot be its own parent.")
        parent = db.get(Department, parent_id)
        if parent is None or parent.company_id != department.company_id:
            raise ValidationError("Parent department must belong to the same company.")
        department.parent_department_id = parent_id

    if department.status not in {s.value for s in DepartmentStatus}:
        raise ValidationError("Invalid department status.")

    db.add(department)
    db.commit()
    db.refresh(department)

    audit_service.record(
        db,
        action=AuditAction.DEPARTMENT_UPDATED,
        actor_user_id=actor.id,
        entity_type="department",
        entity_id=department.id,
        company_id=department.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"fields": sorted(payload.keys())},
    )
    return _serialize(db, department)


__all__ = [
    "create_department",
    "get_department",
    "list_departments",
    "update_department",
]
