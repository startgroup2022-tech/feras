"""RBAC bootstrap.

Keeps the ``roles`` / ``permissions`` / ``role_permissions`` tables in sync with
the single source of truth in :mod:`backend.rbac.permissions`. Idempotent, so
it is safe to run on every deploy.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models.identity import Permission, Role, RolePermission
from backend.rbac.permissions import (
    ALL_PERMISSIONS,
    ROLE_DEFINITIONS,
    ROLE_PERMISSIONS,
)

logger = logging.getLogger("safir.rbac")


def sync_permissions(db: Session) -> dict[str, Permission]:
    existing = {p.code: p for p in db.execute(select(Permission)).scalars()}
    for code, description in ALL_PERMISSIONS.items():
        if code in existing:
            if existing[code].description != description:
                existing[code].description = description
        else:
            perm = Permission(code=code, description=description)
            db.add(perm)
            existing[code] = perm
    db.flush()
    return existing


def sync_roles(db: Session) -> dict[str, Role]:
    existing = {r.code: r for r in db.execute(select(Role)).scalars()}
    for definition in ROLE_DEFINITIONS:
        role = existing.get(definition["code"])
        if role is None:
            role = Role(
                code=definition["code"],
                name_ar=definition["name_ar"],
                name_en=definition["name_en"],
                description=definition["description"],
            )
            db.add(role)
            existing[definition["code"]] = role
        else:
            role.name_ar = definition["name_ar"]
            role.name_en = definition["name_en"]
            role.description = definition["description"]
    db.flush()
    return existing


def sync_role_permissions(db: Session) -> None:
    roles = sync_roles(db)
    permissions = sync_permissions(db)

    for role_code, wanted in ROLE_PERMISSIONS.items():
        role = roles[role_code]
        current_ids = {
            rp.permission_id
            for rp in db.execute(
                select(RolePermission).where(RolePermission.role_id == role.id)
            ).scalars()
        }
        wanted_ids = {permissions[code].id for code in wanted}

        for missing in wanted_ids - current_ids:
            db.add(RolePermission(role_id=role.id, permission_id=missing))
        for stale in current_ids - wanted_ids:
            row = db.execute(
                select(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id == stale,
                )
            ).scalar_one_or_none()
            if row:
                db.delete(row)
    db.commit()
    logger.info("RBAC synced: %d roles, %d permissions", len(roles), len(permissions))


def bootstrap_rbac(db: Session) -> None:
    sync_role_permissions(db)
