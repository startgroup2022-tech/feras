"""Organisational position service (S24).

A position is a company-scoped node in the organisation chart. Reads need
``position.read``; writes need ``position.manage``. Company scope is applied as
a SQL filter, exactly like the other scoped services, so an out-of-scope
company id matches nothing and surfaces as a 404 (never as a hint that the
record exists).

Positions are never hard-deleted: ``status`` moves to ``inactive`` so a
historical reporting line keeps its meaning.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.errors import ConflictError, NotFoundError, ValidationError
from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import PositionStatus
from backend.db.models.group import Department, Position
from backend.db.models.identity import Company, User
from backend.rbac.authorization import accessible_company_ids, require_permission
from backend.rbac.permissions import Perm
from backend.services import audit_service


def _assert_reporting_line_respects_role_structure(
    db: Session, *, child_holder_user_id: int | None, parent: Position
) -> None:
    """AC-24: a company manager never reports to business development.

    The spec fixes the holding structure: both the business-development manager
    and every subsidiary manager report to the owner. Business development
    coordinates but does not command a subsidiary manager, so a reporting line
    that makes a company manager a subordinate of a business-development
    position is refused -- it would misrepresent the org chart the spec pins.
    """
    if child_holder_user_id is None or parent.holder_user_id is None:
        return
    child = db.get(User, child_holder_user_id)
    parent_holder = db.get(User, parent.holder_user_id)
    if child is None or parent_holder is None:
        return
    child_role = child.role.code if child.role else None
    parent_role = parent_holder.role.code if parent_holder.role else None
    if child_role == "company_manager" and parent_role == "business_development":
        raise ValidationError(
            "A company manager cannot report to business development; "
            "both report to the owner."
        )


def _serialise(db: Session, position: Position) -> dict:
    company = db.get(Company, position.company_id)
    holder = db.get(User, position.holder_user_id) if position.holder_user_id else None
    department = (
        db.get(Department, position.department_id) if position.department_id else None
    )
    parent = (
        db.get(Position, position.reports_to_position_id)
        if position.reports_to_position_id
        else None
    )
    return {
        "id": position.id,
        "company_id": position.company_id,
        "department_id": position.department_id,
        "code": position.code,
        "title_ar": position.title_ar,
        "title_en": position.title_en,
        "holder_user_id": position.holder_user_id,
        "holder_employee_id": position.holder_employee_id,
        "reports_to_position_id": position.reports_to_position_id,
        "status": position.status,
        "notes": position.notes,
        "company_name_ar": company.name_ar if company else None,
        "company_name_en": company.name_en if company else None,
        "department_name_ar": department.name_ar if department else None,
        "department_name_en": department.name_en if department else None,
        "holder_name_ar": holder.full_name_ar if holder else None,
        "holder_name_en": (holder.full_name_en if holder else None),
        "reports_to_title_ar": parent.title_ar if parent else None,
        "reports_to_title_en": parent.title_en if parent else None,
    }


def _assert_company_visible(user: User, company_id: int) -> None:
    allowed = accessible_company_ids(user)
    if allowed is not None and company_id not in allowed:
        # Same error as a missing company, so scope cannot be probed for ids.
        raise NotFoundError("Company not found.")


def list_positions(
    db: Session, *, user: User, company_id: int | None = None
) -> list[dict]:
    require_permission(user, Perm.POSITION_READ)
    stmt = select(Position).order_by(Position.company_id, Position.title_en)
    allowed = accessible_company_ids(user)
    if allowed is not None:
        if not allowed:
            return []
        stmt = stmt.where(Position.company_id.in_(allowed))
    if company_id is not None:
        _assert_company_visible(user, company_id)
        stmt = stmt.where(Position.company_id == company_id)
    return [_serialise(db, row) for row in db.execute(stmt).scalars()]


def get_position(db: Session, *, user: User, position_id: int) -> dict:
    require_permission(user, Perm.POSITION_READ)
    position = db.get(Position, position_id)
    if position is None:
        raise NotFoundError("Position not found.")
    _assert_company_visible(user, position.company_id)
    return _serialise(db, position)


def create_position(
    db: Session,
    *,
    actor: User,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    require_permission(actor, Perm.POSITION_MANAGE)
    company = db.get(Company, payload["company_id"])
    if company is None:
        raise NotFoundError("Company not found.")
    _assert_company_visible(actor, company.id)

    code = payload["code"].strip().upper()
    if db.execute(
        select(Position).where(
            Position.company_id == company.id, Position.code == code
        )
    ).scalar_one_or_none():
        raise ConflictError("A position with this code already exists for the company.")

    department_id = payload.get("department_id")
    if department_id is not None:
        department = db.get(Department, department_id)
        if department is None or department.company_id != company.id:
            raise ValidationError("Department must belong to the same company.")

    parent_id = payload.get("reports_to_position_id")
    if parent_id is not None:
        parent = db.get(Position, parent_id)
        if parent is None or parent.company_id != company.id:
            raise ValidationError("The reporting line must stay within the same company.")
        _assert_reporting_line_respects_role_structure(
            db,
            child_holder_user_id=payload.get("holder_user_id"),
            parent=parent,
        )

    status = payload.get("status") or PositionStatus.ACTIVE.value
    if status not in {s.value for s in PositionStatus}:
        raise ValidationError("Invalid position status.")

    position = Position(
        company_id=company.id,
        department_id=department_id,
        code=code,
        title_ar=payload["title_ar"],
        title_en=payload["title_en"],
        holder_user_id=payload.get("holder_user_id"),
        holder_employee_id=payload.get("holder_employee_id"),
        reports_to_position_id=parent_id,
        status=status,
        notes=payload.get("notes"),
    )
    db.add(position)
    db.commit()
    db.refresh(position)

    audit_service.record(
        db,
        action=AuditAction.POSITION_CREATED,
        actor_user_id=actor.id,
        entity_type="position",
        entity_id=position.id,
        company_id=company.id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"code": code},
    )
    return _serialise(db, position)


def update_position(
    db: Session,
    *,
    actor: User,
    position_id: int,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    require_permission(actor, Perm.POSITION_MANAGE)
    position = db.get(Position, position_id)
    if position is None:
        raise NotFoundError("Position not found.")
    _assert_company_visible(actor, position.company_id)

    if payload.get("code") is not None:
        code = payload["code"].strip().upper()
        clash = db.execute(
            select(Position).where(
                Position.company_id == position.company_id,
                Position.code == code,
                Position.id != position.id,
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise ConflictError("A position with this code already exists for the company.")
        position.code = code

    for field in ("title_ar", "title_en", "notes", "holder_user_id", "holder_employee_id"):
        if field in payload and payload[field] is not None:
            setattr(position, field, payload[field])

    if payload.get("department_id") is not None:
        department = db.get(Department, payload["department_id"])
        if department is None or department.company_id != position.company_id:
            raise ValidationError("Department must belong to the same company.")
        position.department_id = department.id

    if payload.get("reports_to_position_id") is not None:
        parent_id = payload["reports_to_position_id"]
        if parent_id == position.id:
            raise ValidationError("A position cannot report to itself.")
        parent = db.get(Position, parent_id)
        if parent is None or parent.company_id != position.company_id:
            raise ValidationError("The reporting line must stay within the same company.")
        _assert_reporting_line_respects_role_structure(
            db,
            child_holder_user_id=position.holder_user_id,
            parent=parent,
        )
        position.reports_to_position_id = parent_id

    if payload.get("status") is not None:
        if payload["status"] not in {s.value for s in PositionStatus}:
            raise ValidationError("Invalid position status.")
        position.status = payload["status"]

    db.add(position)
    db.commit()
    db.refresh(position)

    audit_service.record(
        db,
        action=AuditAction.POSITION_UPDATED,
        actor_user_id=actor.id,
        entity_type="position",
        entity_id=position.id,
        company_id=position.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"fields": sorted(payload.keys())},
    )
    return _serialise(db, position)


__all__ = [
    "create_position",
    "get_position",
    "list_positions",
    "update_position",
]
