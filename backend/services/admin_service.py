"""Administration service: user management and company access control.

This is deliberately the *minimum* needed to make the six-role system
manageable -- create/list/update users, edit a company's descriptive fields, and
grant or revoke a user's access to a company. There is no bulk import, no
delegation tree, no approval matrix.

Every mutation is audited. Deactivating a user takes effect immediately because
``get_current_user`` re-reads the row on each request.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.errors import NotFoundError, ValidationError
from backend.db.models.audit_actions import AuditAction
from backend.db.models.identity import Company, Role, User, UserCompanyAccess
from backend.rbac.authorization import require_permission
from backend.rbac.permissions import Perm
from backend.services import audit_service


def list_users(db: Session, *, user: User) -> list[User]:
    require_permission(user, Perm.USER_READ)
    return list(db.execute(select(User).order_by(User.full_name_ar)).scalars())


def get_user(db: Session, *, user: User, user_id: int) -> User:
    require_permission(user, Perm.USER_READ)
    target = db.get(User, user_id)
    if target is None:
        raise NotFoundError("User not found.")
    return target


def update_user(
    db: Session,
    *,
    actor: User,
    user_id: int,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> User:
    """Partial update of a user's profile, role or active state."""
    require_permission(actor, Perm.USER_MANAGE)
    target = db.get(User, user_id)
    if target is None:
        raise NotFoundError("User not found.")

    if "full_name_ar" in payload and payload["full_name_ar"] is not None:
        target.full_name_ar = payload["full_name_ar"]
    if "full_name_en" in payload and payload["full_name_en"] is not None:
        target.full_name_en = payload["full_name_en"]

    if payload.get("role_code") is not None:
        role = db.execute(
            select(Role).where(Role.code == payload["role_code"])
        ).scalar_one_or_none()
        if role is None:
            raise ValidationError(f"Unknown role code: {payload['role_code']}")
        target.role_id = role.id

    if payload.get("is_active") is not None:
        # An admin must not lock themselves out.
        if target.id == actor.id and payload["is_active"] is False:
            raise ValidationError("You cannot deactivate your own account.")
        target.is_active = payload["is_active"]

    db.add(target)
    db.commit()
    db.refresh(target)

    audit_service.record(
        db,
        action=AuditAction.USER_UPDATED,
        actor_user_id=actor.id,
        entity_type="user",
        entity_id=target.id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"fields": sorted(payload.keys())},
    )
    return target


def update_company(
    db: Session,
    *,
    actor: User,
    company_id: int,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Company:
    require_permission(actor, Perm.COMPANY_MANAGE)
    company = db.get(Company, company_id)
    if company is None:
        raise NotFoundError("Company not found.")

    for field in ("name_ar", "name_en", "sector", "health", "status", "contact_email"):
        if field in payload and payload[field] is not None:
            setattr(company, field, str(payload[field]) if payload[field] is not None else None)

    db.add(company)
    db.commit()
    db.refresh(company)

    audit_service.record(
        db,
        action=AuditAction.COMPANY_UPDATED,
        actor_user_id=actor.id,
        entity_type="company",
        entity_id=company.id,
        company_id=company.id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"fields": sorted(payload.keys())},
    )
    return company


def grant_company_access(
    db: Session,
    *,
    actor: User,
    user_id: int,
    company_id: int,
    can_read: bool = True,
    can_write: bool = True,
    is_primary: bool = False,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> UserCompanyAccess:
    require_permission(actor, Perm.COMPANY_ACCESS_MANAGE)
    target = db.get(User, user_id)
    if target is None:
        raise NotFoundError("User not found.")
    company = db.get(Company, company_id)
    if company is None:
        raise NotFoundError("Company not found.")

    existing = db.execute(
        select(UserCompanyAccess).where(
            UserCompanyAccess.user_id == user_id,
            UserCompanyAccess.company_id == company_id,
        )
    ).scalar_one_or_none()

    if existing is not None:
        # Update in place rather than erroring: granting twice is idempotent.
        existing.can_read = can_read
        existing.can_write = can_write
        existing.is_primary = is_primary
        access = existing
    else:
        access = UserCompanyAccess(
            user_id=user_id,
            company_id=company_id,
            can_read=can_read,
            can_write=can_write,
            is_primary=is_primary,
        )
        db.add(access)

    db.commit()
    db.refresh(access)

    audit_service.record(
        db,
        action=AuditAction.COMPANY_ACCESS_GRANTED,
        actor_user_id=actor.id,
        entity_type="user",
        entity_id=user_id,
        company_id=company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"can_read": can_read, "can_write": can_write},
    )
    return access


def revoke_company_access(
    db: Session,
    *,
    actor: User,
    user_id: int,
    company_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    require_permission(actor, Perm.COMPANY_ACCESS_MANAGE)
    access = db.execute(
        select(UserCompanyAccess).where(
            UserCompanyAccess.user_id == user_id,
            UserCompanyAccess.company_id == company_id,
        )
    ).scalar_one_or_none()
    if access is None:
        raise NotFoundError("Access grant not found.")

    db.delete(access)
    db.commit()

    audit_service.record(
        db,
        action=AuditAction.COMPANY_ACCESS_REVOKED,
        actor_user_id=actor.id,
        entity_type="user",
        entity_id=user_id,
        company_id=company_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )


__all__ = [
    "get_user",
    "grant_company_access",
    "list_users",
    "revoke_company_access",
    "update_company",
    "update_user",
]
