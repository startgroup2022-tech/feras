"""Group administration API.

All routes live under ``/api/v1/admin`` and are permission-gated individually,
so a role can be granted exactly one slice of administration. Company-scoped
roles (Company Owner, CEO, ...) are confined by the services, which apply the
caller's company scope as part of the query.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status

from backend.api.deps import CurrentUser, DbSession, require
from backend.rbac import permission_metadata
from backend.rbac.permissions import Perm
from backend.schemas import (
    BrandingOut,
    DepartmentCreateRequest,
    DepartmentOut,
    DepartmentUpdateRequest,
    GroupStructureNode,
    HoldingOut,
    HoldingUpdateRequest,
    OwnershipCreateRequest,
    OwnershipOut,
    OwnershipUpdateRequest,
    PageOut,
    PermissionActionOut,
    PermissionCatalogueOut,
    PermissionCategoryOut,
    PermissionDetailOut,
    PermissionOut,
    RoleCreateRequest,
    RoleOut,
    RolePermissionsRequest,
    RoleUpdateRequest,
)
from backend.services import (
    admin_service,
    audit_service,
    branding_service,
    department_service,
    holding_service,
    ownership_service,
    role_service,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def _holding_out(holding) -> HoldingOut:
    """Serialise the Holding and attach its public logo URL.

    ``logo_url`` is derived, not stored, so the schema stays free of storage
    internals while the admin UI can still preview the current logo.
    """
    data = HoldingOut.model_validate(holding)
    data.logo_url = branding_service.logo_url(holding)
    return data


# --------------------------------------------------------------------------
# group profile and structure
# --------------------------------------------------------------------------
@router.get("/holding", response_model=HoldingOut)
def get_holding(db: DbSession, user: CurrentUser) -> HoldingOut:
    """The Holding's own metadata. Visible to any authenticated user."""
    return _holding_out(holding_service.get_holding(db))


@router.patch("/holding", response_model=HoldingOut)
def update_holding(
    payload: HoldingUpdateRequest,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.GROUP_MANAGE)),
) -> HoldingOut:
    ctx = audit_service.request_context(request)
    holding = holding_service.update_holding(
        db,
        actor=actor,
        payload=payload.model_dump(exclude_unset=True),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return _holding_out(holding)


# --------------------------------------------------------------------------
# public website branding (logo)
# --------------------------------------------------------------------------
@router.get("/branding", response_model=BrandingOut)
def get_branding(db: DbSession, user: CurrentUser) -> BrandingOut:
    """Current website branding (logo URL). Any authenticated user may read."""
    return BrandingOut(**branding_service.branding_payload(db))


@router.post("/branding/logo", response_model=BrandingOut, status_code=status.HTTP_201_CREATED)
async def upload_branding_logo(
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.GROUP_MANAGE)),
    file: UploadFile = File(...),
) -> BrandingOut:
    """Upload/replace the Holding logo used across the public website.

    Type and size are validated on the server; the client filename never
    influences the stored path.
    """
    data = await file.read()
    ctx = audit_service.request_context(request)
    holding = branding_service.set_logo(
        db,
        actor=actor,
        data=data,
        filename=file.filename or "",
        content_type=file.content_type,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return BrandingOut(**branding_service.branding_payload(db))


@router.delete("/branding/logo", response_model=BrandingOut)
def delete_branding_logo(
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.GROUP_MANAGE)),
) -> BrandingOut:
    """Remove the uploaded logo so the site falls back to its built-in mark."""
    ctx = audit_service.request_context(request)
    branding_service.remove_logo(
        db,
        actor=actor,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return BrandingOut(**branding_service.branding_payload(db))


@router.get("/holding/structure", response_model=list[GroupStructureNode])
def group_structure(db: DbSession, user: CurrentUser) -> list[GroupStructureNode]:
    """Parent/child edges of the group, for the ownership tree view."""
    return [
        GroupStructureNode(**node)
        for node in ownership_service.group_structure(db, user=user)
    ]


# --------------------------------------------------------------------------
# ownership
# --------------------------------------------------------------------------
@router.get("/ownerships", response_model=list[OwnershipOut])
def list_ownerships(
    db: DbSession,
    user: CurrentUser,
    owned_company_id: int | None = Query(default=None),
    owner_company_id: int | None = Query(default=None),
    ownership_status: str | None = Query(default=None, alias="status"),
) -> list[OwnershipOut]:
    return [
        OwnershipOut(**row)
        for row in ownership_service.list_ownerships(
            db,
            user=user,
            owned_company_id=owned_company_id,
            owner_company_id=owner_company_id,
            status=ownership_status,
        )
    ]


@router.post(
    "/ownerships",
    response_model=OwnershipOut,
    status_code=status.HTTP_201_CREATED,
)
def create_ownership(
    payload: OwnershipCreateRequest,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.OWNERSHIP_MANAGE)),
) -> OwnershipOut:
    ctx = audit_service.request_context(request)
    row = ownership_service.create_ownership(
        db,
        actor=actor,
        payload=payload.model_dump(),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return OwnershipOut(**row)


@router.patch("/ownerships/{ownership_id}", response_model=OwnershipOut)
def update_ownership(
    ownership_id: int,
    payload: OwnershipUpdateRequest,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.OWNERSHIP_MANAGE)),
) -> OwnershipOut:
    ctx = audit_service.request_context(request)
    row = ownership_service.update_ownership(
        db,
        actor=actor,
        ownership_id=ownership_id,
        payload=payload.model_dump(exclude_unset=True),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return OwnershipOut(**row)


@router.post("/ownerships/{ownership_id}/end", response_model=OwnershipOut)
def end_ownership(
    ownership_id: int,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.OWNERSHIP_MANAGE)),
) -> OwnershipOut:
    ctx = audit_service.request_context(request)
    row = ownership_service.end_ownership(
        db,
        actor=actor,
        ownership_id=ownership_id,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return OwnershipOut(**row)


# --------------------------------------------------------------------------
# departments
# --------------------------------------------------------------------------
@router.get("/departments", response_model=list[DepartmentOut])
def list_departments(
    db: DbSession,
    user: CurrentUser,
    company_id: int | None = Query(default=None),
) -> list[DepartmentOut]:
    return [
        DepartmentOut(**row)
        for row in department_service.list_departments(
            db, user=user, company_id=company_id
        )
    ]


@router.post(
    "/departments",
    response_model=DepartmentOut,
    status_code=status.HTTP_201_CREATED,
)
def create_department(
    payload: DepartmentCreateRequest,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.DEPARTMENT_MANAGE)),
) -> DepartmentOut:
    ctx = audit_service.request_context(request)
    row = department_service.create_department(
        db,
        actor=actor,
        payload=payload.model_dump(),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return DepartmentOut(**row)


@router.patch("/departments/{department_id}", response_model=DepartmentOut)
def update_department(
    department_id: int,
    payload: DepartmentUpdateRequest,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.DEPARTMENT_MANAGE)),
) -> DepartmentOut:
    ctx = audit_service.request_context(request)
    row = department_service.update_department(
        db,
        actor=actor,
        department_id=department_id,
        payload=payload.model_dump(exclude_unset=True),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return DepartmentOut(**row)


# --------------------------------------------------------------------------
# user directory (paginated)
# --------------------------------------------------------------------------
@router.get("/users", response_model=PageOut)
def list_users(
    db: DbSession,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, max_length=120),
    role_code: str | None = Query(default=None, max_length=40),
    is_active: bool | None = Query(default=None),
) -> PageOut:
    """Paginated user directory. Requires ``user.read_all``."""
    return PageOut(
        **admin_service.list_users_page(
            db,
            user=user,
            limit=limit,
            offset=offset,
            search=search,
            role_code=role_code,
            is_active=is_active,
        )
    )


# --------------------------------------------------------------------------
# roles and permissions
# --------------------------------------------------------------------------
@router.get("/roles", response_model=list[RoleOut])
def list_roles(db: DbSession, user: CurrentUser) -> list[RoleOut]:
    return [RoleOut(**row) for row in role_service.list_roles(db, user=user)]


@router.get("/roles/{code}", response_model=RoleOut)
def get_role(code: str, db: DbSession, user: CurrentUser) -> RoleOut:
    return RoleOut(**role_service.get_role(db, user=user, code=code))


@router.post("/roles", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
def create_role(
    payload: RoleCreateRequest,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.ROLE_MANAGE)),
) -> RoleOut:
    ctx = audit_service.request_context(request)
    row = role_service.create_role(
        db,
        actor=actor,
        payload=payload.model_dump(),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return RoleOut(**row)


@router.patch("/roles/{code}", response_model=RoleOut)
def update_role(
    code: str,
    payload: RoleUpdateRequest,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.ROLE_MANAGE)),
) -> RoleOut:
    ctx = audit_service.request_context(request)
    row = role_service.update_role(
        db,
        actor=actor,
        code=code,
        payload=payload.model_dump(exclude_unset=True),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return RoleOut(**row)


@router.put("/roles/{code}/permissions", response_model=RoleOut)
def set_role_permissions(
    code: str,
    payload: RolePermissionsRequest,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.PERMISSION_ASSIGN)),
) -> RoleOut:
    ctx = audit_service.request_context(request)
    row = role_service.set_role_permissions(
        db,
        actor=actor,
        code=code,
        codes=payload.permissions,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return RoleOut(**row)


@router.get("/permissions", response_model=list[PermissionOut])
def list_permissions(db: DbSession, user: CurrentUser) -> list[PermissionOut]:
    return [
        PermissionOut(**row)
        for row in role_service.list_permission_catalogue(db, user=user)
    ]


@router.get("/permissions/catalogue", response_model=PermissionCatalogueOut)
def permission_catalogue(
    user: CurrentUser,
    db: DbSession,
    actor=Depends(require(Perm.PERMISSION_READ)),
) -> PermissionCatalogueOut:
    """Bilingual, grouped permission catalogue for the admin UI.

    Read-only presentation data. Authorization still happens against the codes
    in :mod:`backend.rbac.permissions`; this endpoint only describes them.
    """
    return PermissionCatalogueOut(
        categories=[PermissionCategoryOut(**c) for c in permission_metadata.CATEGORIES],
        actions=[PermissionActionOut(**a) for a in permission_metadata.ACTIONS],
        permissions=[PermissionDetailOut(**p) for p in permission_metadata.catalogue()],
    )


# --------------------------------------------------------------------------
# audit trail
# --------------------------------------------------------------------------
@router.get("/audit-logs", response_model=PageOut)
def list_audit_logs(
    db: DbSession,
    actor=Depends(require(Perm.AUDIT_READ)),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    action: str | None = Query(default=None, max_length=80),
    actor_user_id: int | None = Query(default=None),
    entity_type: str | None = Query(default=None, max_length=80),
    company_id: int | None = Query(default=None),
) -> PageOut:
    return PageOut(
        **audit_service.list_audit_logs(
            db,
            limit=limit,
            offset=offset,
            action=action,
            actor_user_id=actor_user_id,
            entity_type=entity_type,
            company_id=company_id,
        )
    )
