"""Sector catalogue service (S03).

Sectors are holding-wide classification labels. Reads are open to anyone with
``sector.read`` (the admin screens and company forms need the list); writes
need ``sector.manage``. A sector is never deleted -- deactivating it keeps the
existing company strings meaningful.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.errors import ConflictError, NotFoundError, ValidationError
from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import DepartmentStatus
from backend.db.models.group import Sector
from backend.db.models.identity import User
from backend.rbac.authorization import require_permission
from backend.rbac.permissions import Perm
from backend.services import audit_service


def _serialise(sector: Sector) -> dict:
    return {
        "id": sector.id,
        "code": sector.code,
        "name_ar": sector.name_ar,
        "name_en": sector.name_en,
        "status": sector.status,
        "sort_order": sector.sort_order,
        "notes": sector.notes,
    }


def list_sectors(db: Session, *, user: User) -> list[dict]:
    require_permission(user, Perm.SECTOR_READ)
    stmt = select(Sector).order_by(Sector.sort_order, Sector.name_en)
    return [_serialise(row) for row in db.execute(stmt).scalars()]


def get_sector(db: Session, *, user: User, sector_id: int) -> dict:
    require_permission(user, Perm.SECTOR_READ)
    sector = db.get(Sector, sector_id)
    if sector is None:
        raise NotFoundError("Sector not found.")
    return _serialise(sector)


def create_sector(
    db: Session,
    *,
    actor: User,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    require_permission(actor, Perm.SECTOR_MANAGE)
    code = payload["code"].strip().upper()
    if db.execute(select(Sector).where(Sector.code == code)).scalar_one_or_none():
        raise ConflictError("A sector with this code already exists.")

    sector = Sector(
        code=code,
        name_ar=payload["name_ar"],
        name_en=payload["name_en"],
        status=payload.get("status") or DepartmentStatus.ACTIVE.value,
        sort_order=payload.get("sort_order") or 0,
        notes=payload.get("notes"),
    )
    if sector.status not in {s.value for s in DepartmentStatus}:
        raise ValidationError("Invalid sector status.")
    db.add(sector)
    db.commit()
    db.refresh(sector)

    audit_service.record(
        db,
        action=AuditAction.SECTOR_CREATED,
        actor_user_id=actor.id,
        entity_type="sector",
        entity_id=sector.id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"code": code},
    )
    return _serialise(sector)


def update_sector(
    db: Session,
    *,
    actor: User,
    sector_id: int,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    require_permission(actor, Perm.SECTOR_MANAGE)
    sector = db.get(Sector, sector_id)
    if sector is None:
        raise NotFoundError("Sector not found.")

    if payload.get("code") is not None:
        code = payload["code"].strip().upper()
        clash = db.execute(
            select(Sector).where(Sector.code == code, Sector.id != sector.id)
        ).scalar_one_or_none()
        if clash is not None:
            raise ConflictError("A sector with this code already exists.")
        sector.code = code

    for field in ("name_ar", "name_en", "notes", "status", "sort_order"):
        if field in payload and payload[field] is not None:
            setattr(sector, field, payload[field])

    if sector.status not in {s.value for s in DepartmentStatus}:
        raise ValidationError("Invalid sector status.")

    db.add(sector)
    db.commit()
    db.refresh(sector)

    audit_service.record(
        db,
        action=AuditAction.SECTOR_UPDATED,
        actor_user_id=actor.id,
        entity_type="sector",
        entity_id=sector.id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"fields": sorted(payload.keys())},
    )
    return _serialise(sector)


__all__ = [
    "create_sector",
    "get_sector",
    "list_sectors",
    "update_sector",
]
