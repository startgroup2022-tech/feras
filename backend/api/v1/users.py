"""User administration and company endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from backend.api.deps import CurrentUser, DbSession, require
from backend.core.errors import NotFoundError
from backend.db.models.audit_actions import AuditAction
from backend.db.models.identity import Company, User, UserCompanyAccess
from backend.rbac.authorization import (
    accessible_company_ids,
    require_permission,
)
from backend.rbac.permissions import Perm
from backend.repositories.scoped import CompanyRepository
from backend.schemas import (
    CompanyCreateRequest,
    CompanyOut,
    CreateUserRequest,
    UserOut,
)
from backend.services import audit_service, auth_service
from backend.services.rbac_service import bootstrap_rbac

router = APIRouter(tags=["users", "companies"])


# --------------------------------------------------------------------------
# users
# --------------------------------------------------------------------------
@router.get("/users/me/permissions", response_model=UserOut, tags=["users"])
def my_permissions(user: CurrentUser) -> UserOut:
    """Re-read effective permissions for the current user."""
    from backend.api.v1.auth import _user_payload

    return UserOut(**_user_payload(user))


@router.post(
    "/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    tags=["users"],
)
def create_user(
    payload: CreateUserRequest,
    request: Request,
    db: DbSession,
    actor: User = Depends(require(Perm.USER_MANAGE)),
) -> UserOut:
    """Create a user. Holding Owner only."""
    from backend.api.v1.auth import _user_payload

    user = auth_service.create_user(
        db,
        email=payload.email,
        password=payload.password,
        full_name_ar=payload.full_name_ar,
        full_name_en=payload.full_name_en,
        role_code=payload.role_code,
    )

    # Grant company access where requested. Holding-wide roles need none.
    if payload.company_ids:
        require_permission(actor, Perm.COMPANY_ACCESS_MANAGE)
        for company_id in payload.company_ids:
            company = db.get(Company, company_id)
            if company is None:
                raise NotFoundError(f"Company {company_id} not found.")
            db.add(
                UserCompanyAccess(
                    user_id=user.id,
                    company_id=company_id,
                    can_read=True,
                    can_write=True,
                    is_primary=True,
                )
            )
        db.commit()
        db.refresh(user)

    ctx = audit_service.request_context(request)
    audit_service.record(
        db,
        action=AuditAction.USER_CREATED,
        actor_user_id=actor.id,
        entity_type="user",
        entity_id=user.id,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
        metadata={"role": user.role_code, "companies": payload.company_ids},
    )
    return UserOut(**_user_payload(user))


# --------------------------------------------------------------------------
# companies
# --------------------------------------------------------------------------
@router.get("/companies", response_model=list[CompanyOut], tags=["companies"])
def list_companies(user: CurrentUser, db: DbSession) -> list[CompanyOut]:
    """Companies the caller may see. Scope is applied in the query itself."""
    require_permission(user, Perm.COMPANY_READ)
    companies = CompanyRepository(db).list_for_user(user)
    return [CompanyOut.model_validate(c) for c in companies]


@router.get("/companies/{company_id}", response_model=CompanyOut, tags=["companies"])
def get_company(company_id: int, user: CurrentUser, db: DbSession) -> CompanyOut:
    """A single company, only if the caller is in scope (else 404)."""
    require_permission(user, Perm.COMPANY_READ)
    company = CompanyRepository(db).get_for_user(user, company_id)
    if company is None:
        raise NotFoundError("Company not found.")
    return CompanyOut.model_validate(company)


@router.post(
    "/companies",
    response_model=CompanyOut,
    status_code=status.HTTP_201_CREATED,
    tags=["companies"],
)
def create_company(
    payload: CompanyCreateRequest,
    request: Request,
    db: DbSession,
    actor: User = Depends(require(Perm.COMPANY_MANAGE)),
) -> CompanyOut:
    """Register a subsidiary. Holding Owner only."""
    if CompanyRepository(db).get_by_code(payload.code) is not None:
        from backend.core.errors import ConflictError

        raise ConflictError("A company with this code already exists.")

    company = Company(
        code=payload.code.strip().upper(),
        name_ar=payload.name_ar,
        name_en=payload.name_en,
        sector=payload.sector,
        contact_email=str(payload.contact_email) if payload.contact_email else None,
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    ctx = audit_service.request_context(request)
    audit_service.record(
        db,
        action=AuditAction.COMPANY_CREATED,
        actor_user_id=actor.id,
        entity_type="company",
        entity_id=company.id,
        company_id=company.id,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
        metadata={"code": company.code},
    )
    return CompanyOut.model_validate(company)


@router.get("/rbac/roles", tags=["rbac"])
def list_roles(user: CurrentUser, db: DbSession) -> list[dict]:
    """The role catalogue with granted permissions."""
    require_permission(user, Perm.USER_READ)
    from sqlalchemy import select

    from backend.db.models.identity import Role

    roles = db.execute(select(Role).order_by(Role.id)).scalars()
    return [
        {
            "code": r.code,
            "name_ar": r.name_ar,
            "name_en": r.name_en,
            "description": r.description,
            "permissions": sorted(p.code for p in r.permissions),
        }
        for r in roles
    ]


@router.post("/rbac/sync", tags=["rbac"])
def sync_rbac(db: DbSession, actor: User = Depends(require(Perm.USER_MANAGE))) -> dict:
    """Re-apply the permission catalogue to the database. Idempotent."""
    bootstrap_rbac(db)
    return {"status": "ok"}


__all__ = ["router", "accessible_company_ids"]
