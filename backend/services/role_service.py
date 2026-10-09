"""Role administration service.

The RBAC catalogue is the single source of truth in
:mod:`backend.rbac.permissions`; this service exposes it for editing and keeps
the database in sync. The security property that matters here is
**no privilege escalation**: an actor may never grant a permission they do not
themselves hold, and may never edit a role that is already more privileged than
they are.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from backend.db.models.audit_actions import AuditAction
from backend.db.models.identity import Permission, Role, RolePermission, User
from backend.rbac.authorization import require_permission, role_permissions
from backend.rbac.permissions import ROLE_DEFINITIONS, Perm
from backend.services import audit_service

_SYSTEM_CODES = {d["code"] for d in ROLE_DEFINITIONS}


def _serialize(role: Role) -> dict:
    return {
        "code": role.code,
        "name_ar": role.name_ar,
        "name_en": role.name_en,
        "description": role.description,
        "description_ar": role.description_ar,
        "permissions": sorted(p.code for p in role.permissions),
        "is_system": role.code in _SYSTEM_CODES,
    }


def list_roles(db: Session, *, user: User) -> list[dict]:
    require_permission(user, Perm.ROLE_READ)
    roles = db.execute(select(Role).order_by(Role.id)).scalars()
    return [_serialize(r) for r in roles]


def get_role(db: Session, *, user: User, code: str) -> dict:
    require_permission(user, Perm.ROLE_READ)
    role = db.execute(select(Role).where(Role.code == code)).scalar_one_or_none()
    if role is None:
        raise NotFoundError("Role not found.")
    return _serialize(role)


def list_permission_catalogue(db: Session, *, user: User) -> list[dict]:
    require_permission(user, Perm.PERMISSION_READ)
    rows = db.execute(select(Permission).order_by(Permission.code)).scalars()
    return [{"code": p.code, "description": p.description} for p in rows]


def _assert_no_escalation(actor: User, desired: set[str]) -> None:
    """An actor may only grant permissions they already hold."""
    granted = role_permissions(actor)
    if not desired <= granted:
        excess = sorted(desired - granted)
        raise PermissionDeniedError(
            "You cannot grant permissions you do not hold: " + ", ".join(excess)
        )


def _assert_can_touch_role(actor: User, role: Role) -> None:
    """An actor may not modify a role more privileged than their own."""
    _assert_no_escalation(actor, {p.code for p in role.permissions})


def _resolve_permissions(db: Session, codes: list[str]) -> set[int]:
    if not codes:
        return set()
    rows = db.execute(select(Permission).where(Permission.code.in_(codes))).scalars()
    found = {p.code: p.id for p in rows}
    unknown = sorted(set(codes) - set(found))
    if unknown:
        raise ValidationError("Unknown permissions: " + ", ".join(unknown))
    return set(found.values())


def create_role(
    db: Session,
    *,
    actor: User,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    require_permission(actor, Perm.ROLE_MANAGE)
    code = payload["code"]
    if db.execute(select(Role).where(Role.code == code)).scalar_one_or_none():
        raise ConflictError("A role with this code already exists.")

    desired = set(payload.get("permissions") or [])
    _assert_no_escalation(actor, desired)
    permission_ids = _resolve_permissions(db, sorted(desired))

    role = Role(
        code=code,
        name_ar=payload["name_ar"],
        name_en=payload["name_en"],
        description=payload.get("description"),
        description_ar=payload.get("description_ar"),
    )
    db.add(role)
    db.flush()
    for permission_id in permission_ids:
        db.add(RolePermission(role_id=role.id, permission_id=permission_id))
    db.commit()
    db.refresh(role)

    audit_service.record(
        db,
        action=AuditAction.ROLE_CREATED,
        actor_user_id=actor.id,
        entity_type="role",
        entity_id=role.code,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"permissions": sorted(desired)},
    )
    return _serialize(role)


def update_role(
    db: Session,
    *,
    actor: User,
    code: str,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    require_permission(actor, Perm.ROLE_MANAGE)
    role = db.execute(select(Role).where(Role.code == code)).scalar_one_or_none()
    if role is None:
        raise NotFoundError("Role not found.")
    _assert_can_touch_role(actor, role)

    for field in ("name_ar", "name_en", "description", "description_ar"):
        if field in payload and payload[field] is not None:
            setattr(role, field, payload[field])

    db.add(role)
    db.commit()
    db.refresh(role)

    audit_service.record(
        db,
        action=AuditAction.ROLE_UPDATED,
        actor_user_id=actor.id,
        entity_type="role",
        entity_id=role.code,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"fields": sorted(payload.keys())},
    )
    return _serialize(role)


def set_role_permissions(
    db: Session,
    *,
    actor: User,
    code: str,
    codes: list[str],
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    require_permission(actor, Perm.PERMISSION_ASSIGN)
    role = db.execute(select(Role).where(Role.code == code)).scalar_one_or_none()
    if role is None:
        raise NotFoundError("Role not found.")

    desired = set(codes or [])
    # Guard both directions: an actor cannot grant itself new powers, and it
    # cannot strip a role that is more privileged than its own.
    _assert_no_escalation(actor, desired)
    _assert_can_touch_role(actor, role)

    permission_ids = _resolve_permissions(db, sorted(desired))
    current_ids = {p.id for p in role.permissions}

    for missing in permission_ids - current_ids:
        db.add(RolePermission(role_id=role.id, permission_id=missing))
    for stale in current_ids - permission_ids:
        row = db.execute(
            select(RolePermission).where(
                RolePermission.role_id == role.id,
                RolePermission.permission_id == stale,
            )
        ).scalar_one_or_none()
        if row is not None:
            db.delete(row)
    db.commit()
    db.refresh(role)

    audit_service.record(
        db,
        action=AuditAction.ROLE_PERMISSIONS_CHANGED,
        actor_user_id=actor.id,
        entity_type="role",
        entity_id=role.code,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"permissions": sorted(desired)},
    )
    return _serialize(role)


__all__ = [
    "create_role",
    "get_role",
    "list_permission_catalogue",
    "list_roles",
    "set_role_permissions",
    "update_role",
]
