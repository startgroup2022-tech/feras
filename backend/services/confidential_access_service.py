"""Delegated confidential access (D04).

Confidential records (complaints, leadership assessments) are visible to the
owner only by default. The owner may delegate access to a *specific record* and
a *specific permission*, with an expiry and an audit trail. An external
consultant sees only what is explicitly granted.

This module is the single place that answers "may this user see this
confidential record?". Nothing else branches on role names for confidentiality.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.errors import NotFoundError, PermissionDeniedError, ValidationError
from backend.db.base import utcnow
from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import RoleCode
from backend.db.models.identity import User
from backend.db.models.operations import ConfidentialAccessGrant
from backend.rbac.authorization import require_permission
from backend.rbac.permissions import Perm
from backend.services import audit_service

# Roles that own confidential data outright. The owner (and the delegated
# super admin) see everything; everyone else needs an explicit grant.
_OWNER_ROLES = {RoleCode.HOLDING_OWNER.value, RoleCode.SUPER_ADMIN.value}


def is_confidential_owner(user: User) -> bool:
    """True for the owner and delegated super admin (full confidential read)."""
    return user.is_superuser or user.role_code in _OWNER_ROLES


def _as_aware(value: datetime | None) -> datetime | None:
    """Normalise a possibly-naive stored datetime to UTC.

    SQLite returns naive datetimes even for ``DateTime(timezone=True)`` columns,
    so comparisons against an aware ``utcnow()`` would raise. Treat a naive
    value as UTC (the platform stores UTC everywhere).
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _is_live(grant: ConfidentialAccessGrant, now: datetime) -> bool:
    if not grant.is_active:
        return False
    expires = _as_aware(grant.expires_at)
    return expires is None or expires > now


def _active_grants(db: Session, *, subject_type: str, subject_id: int) -> list[ConfidentialAccessGrant]:
    now = utcnow()
    rows = db.execute(
        select(ConfidentialAccessGrant).where(
            ConfidentialAccessGrant.subject_type == subject_type,
            ConfidentialAccessGrant.subject_id == subject_id,
            ConfidentialAccessGrant.is_active.is_(True),
        )
    ).scalars()
    return [g for g in rows if _is_live(g, now)]


def can_read_confidential(
    db: Session, *, user: User, subject_type: str, subject_id: int, permission: str
) -> bool:
    """Whether ``user`` may read this specific confidential record.

    The owner always may. Anyone else must hold a live grant for *this* record
    with the *required* permission code (or the blanket decide permission).
    """
    if is_confidential_owner(user):
        return True
    for grant in _active_grants(db, subject_type=subject_type, subject_id=subject_id):
        if grant.grantee_user_id != user.id:
            continue
        if grant.permission_code in (permission, Perm.COMPLAINT_DECIDE):
            return True
    return False


def require_confidential_read(
    db: Session, *, user: User, subject_type: str, subject_id: int, permission: str
) -> None:
    if not can_read_confidential(
        db, user=user, subject_type=subject_type, subject_id=subject_id, permission=permission
    ):
        # Same error shape as a missing record, so the existence of a
        # confidential record is not leaked to a caller who may not see it.
        raise NotFoundError("Record not found.")


def grant_access(
    db: Session,
    *,
    actor: User,
    subject_type: str,
    subject_id: int,
    grantee_user_id: int,
    permission_code: str,
    expires_at: datetime | None = None,
    reason: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> ConfidentialAccessGrant:
    """Delegate access to one confidential record (owner action, D04)."""
    require_permission(actor, Perm.CONFIDENTIAL_ACCESS_MANAGE)
    if not is_confidential_owner(actor):
        raise PermissionDeniedError("Only the owner may delegate confidential access.")

    grantee = db.get(User, grantee_user_id)
    if grantee is None or not grantee.is_active:
        raise ValidationError("Grantee not found or inactive.")
    if expires_at is None:
        raise ValidationError("An expiry is required for a confidential access grant.")

    grant = ConfidentialAccessGrant(
        subject_type=subject_type,
        subject_id=subject_id,
        grantee_user_id=grantee_user_id,
        permission_code=permission_code,
        expires_at=expires_at,
        is_active=True,
        created_by_id=actor.id,
        reason=reason,
    )
    db.add(grant)
    db.commit()
    db.refresh(grant)

    audit_service.record(
        db,
        action=AuditAction.CONFIDENTIAL_ACCESS_GRANTED,
        actor_user_id=actor.id,
        entity_type="confidential_access_grant",
        entity_id=grant.id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={
            "subject_type": subject_type,
            "subject_id": subject_id,
            "grantee_user_id": grantee_user_id,
            "permission_code": permission_code,
            "expires_at": expires_at.isoformat(),
        },
    )
    return grant


def revoke_access(
    db: Session,
    *,
    actor: User,
    grant_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> ConfidentialAccessGrant:
    require_permission(actor, Perm.CONFIDENTIAL_ACCESS_MANAGE)
    grant = db.get(ConfidentialAccessGrant, grant_id)
    if grant is None:
        raise NotFoundError("Grant not found.")
    grant.is_active = False
    db.add(grant)
    db.commit()
    db.refresh(grant)

    audit_service.record(
        db,
        action=AuditAction.CONFIDENTIAL_ACCESS_REVOKED,
        actor_user_id=actor.id,
        entity_type="confidential_access_grant",
        entity_id=grant.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return grant


def list_grants(db: Session, *, actor: User, subject_type: str, subject_id: int) -> list[ConfidentialAccessGrant]:
    require_permission(actor, Perm.CONFIDENTIAL_ACCESS_MANAGE)
    if not is_confidential_owner(actor):
        raise PermissionDeniedError("Only the owner may view confidential access grants.")
    return list(
        db.execute(
            select(ConfidentialAccessGrant)
            .where(
                ConfidentialAccessGrant.subject_type == subject_type,
                ConfidentialAccessGrant.subject_id == subject_id,
            )
            .order_by(ConfidentialAccessGrant.created_at.desc())
        ).scalars()
    )


def serialise(grant: ConfidentialAccessGrant) -> dict:
    return {
        "id": grant.id,
        "subject_type": grant.subject_type,
        "subject_id": grant.subject_id,
        "grantee_user_id": grant.grantee_user_id,
        "permission_code": grant.permission_code,
        "expires_at": grant.expires_at,
        "is_active": _is_live(grant, utcnow()),
        "reason": grant.reason,
        "created_at": grant.created_at,
    }
