"""Authorization engine.

Two independent questions are answered here, and both must pass:

1. **Does this user hold the required permission?** (role based)
2. **Is this user allowed to touch this specific company?** (scope based)

The second question is the one that enforces company data isolation. It is
answered from the database on every call, never from the request payload, so
changing ``company_id``, a record id, a URL or a query parameter cannot widen
access.

A company-scoped user (Company Manager) is restricted to the companies granted
in ``user_company_access``. A holding-wide user (Holding Owner, Accountant,
Business Development, Marketing, Designer) may read across companies, but only
for the companies that exist -- and writes are still permission-checked.
"""

from __future__ import annotations

from sqlalchemy.orm import object_session

from backend.core.errors import PermissionDeniedError
from backend.db.models.enums import RoleCode
from backend.db.models.identity import Company, User
from backend.rbac.permissions import HOLDING_WIDE_ROLES, ROLE_PERMISSIONS


def role_permissions(user: User) -> set[str]:
    """Permission codes granted to a user's role.

    Grants are read from the database when the user is session-bound, so an
    administrator can edit a role's permissions (or add a custom role) and have
    it enforced immediately. The static catalogue remains the fallback whenever
    the row is unavailable or the role is unknown.
    """
    if user.is_superuser:
        return set().union(*ROLE_PERMISSIONS.values())

    cached = user.__dict__.get("_effective_permissions")
    if cached is not None:
        return cached

    code = user.role_code
    permissions: set[str] | None = None
    session = object_session(user)
    if session is not None:
        # Imported lazily to avoid an import cycle (rbac_service imports models).
        from backend.services.rbac_service import effective_permissions

        permissions = effective_permissions(session, code)
    if permissions is None:
        permissions = set(ROLE_PERMISSIONS.get(code, set()))

    # Cache on the instance; it lives for the duration of one request.
    user.__dict__["_effective_permissions"] = permissions
    return permissions


def has_permission(user: User, permission: str) -> bool:
    return permission in role_permissions(user)


def require_permission(user: User, permission: str) -> None:
    if not has_permission(user, permission):
        raise PermissionDeniedError("You do not have permission to perform this action.")


def has_any_permission(user: User, *permissions: str) -> bool:
    granted = role_permissions(user)
    return any(p in granted for p in permissions)


def require_any_permission(user: User, *permissions: str) -> None:
    """Pass when the user holds at least one of the given permissions.

    Needed where a read can be satisfied by either a narrow grant (read your
    own company) or a broad one (read all companies) -- for example the
    Accountant, who holds ``REPORT_READ_ALL`` but not ``REPORT_READ_OWN``.
    """
    if not has_any_permission(user, *permissions):
        raise PermissionDeniedError("You do not have permission to perform this action.")


def is_holding_wide(user: User) -> bool:
    """True when the user is not confined to a single company.

    Holding staff (Owner, Accountant, Business Development, Marketing,
    Designer) read across companies so they can do their jobs; what they may
    actually *do* is still governed by their permission set. A Company Manager
    is confined to the companies granted in ``user_company_access``.
    """
    return user.is_superuser or user.role_code in HOLDING_WIDE_ROLES


def accessible_company_ids(user: User) -> list[int] | None:
    """Company ids the user may read.

    Returns ``None`` to mean "all companies" (holding-wide scope) and a concrete
    list otherwise. ``None`` is deliberately distinct from an empty list: an
    empty list means the user has access to nothing.
    """
    if is_holding_wide(user):
        return None
    return [a.company_id for a in user.company_access if a.can_read]


def can_access_company(user: User, company_id: int) -> bool:
    """Whether the user may read the given company's data."""
    allowed = accessible_company_ids(user)
    if allowed is None:
        return True
    return company_id in allowed


def can_write_company(user: User, company_id: int) -> bool:
    """Whether the user may modify the given company's data."""
    if user.is_superuser:
        return True
    for access in user.company_access:
        if access.company_id == company_id and access.can_write:
            return True
    return False


def require_company_access(user: User, company_id: int, *, write: bool = False) -> None:
    """Raise unless the user may act on the company.

    Raises the *same* error for "not permitted" and "does not exist" so that a
    caller cannot distinguish an inaccessible company from a missing one, which
    would otherwise leak the existence of other companies' records.
    """
    ok = can_write_company(user, company_id) if write else can_access_company(user, company_id)
    if not ok:
        raise PermissionDeniedError("You do not have access to this company's data.")


def scope_company_ids(user: User) -> list[int] | None:
    """Alias used by repositories when building query filters."""
    return accessible_company_ids(user)


def visible_companies(user: User, companies: list[Company]) -> list[Company]:
    """Filter a company collection down to those the user may see."""
    allowed = accessible_company_ids(user)
    if allowed is None:
        return list(companies)
    allowed_set = set(allowed)
    return [c for c in companies if c.id in allowed_set]
