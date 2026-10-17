"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from backend.api.deps import CurrentUser, DbSession
from backend.core.config import settings
from backend.core.errors import RateLimitError
from backend.core.rate_limit import RateLimiter
from backend.rbac.authorization import role_permissions
from backend.schemas import LoginRequest, RefreshRequest, TokenResponse, UserOut
from backend.schemas.governance import (
    TwoFactorConfirmOut,
    TwoFactorConfirmRequest,
    TwoFactorDisableRequest,
    TwoFactorEnrolOut,
    TwoFactorStatusOut,
)
from backend.services import audit_service, auth_service, two_factor_service

router = APIRouter(prefix="/auth", tags=["auth"])

# Shared limiter for login attempts. Keyed by client IP + submitted email.
_login_limiter = RateLimiter(
    max_events=settings.LOGIN_RATE_LIMIT,
    window_seconds=settings.LOGIN_RATE_WINDOW_SECONDS,
)


def _user_payload(user) -> dict:
    """Serialise a user for the API.

    ``role_code`` is the user's (single) role and is always populated. ``roles``
    repeats it as a list so the contract already matches a future many-to-many
    role model; existing clients that read ``role_code`` are unaffected.
    """
    role_code = user.role_code or None
    return {
        "id": user.id,
        "email": user.email,
        "full_name_ar": user.full_name_ar,
        "full_name_en": user.full_name_en,
        "is_active": user.is_active,
        "role_code": role_code,
        "role_name_ar": user.role.name_ar if user.role else None,
        "role_name_en": user.role.name_en if user.role else None,
        "roles": [role_code] if role_code else [],
        "permissions": sorted(role_permissions(user)),
        "company_ids": user.permitted_company_ids,
        "department_id": getattr(user, "department_id", None),
        "last_login_at": user.last_login_at,
    }


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: DbSession) -> TokenResponse:
    """Authenticate and return an access/refresh token pair."""
    ctx = audit_service.request_context(request)
    limiter_key = f"{ctx['ip_address']}:{payload.email.lower()}"

    if settings.RATE_LIMIT_ENABLED and not _login_limiter.check(limiter_key):
        raise RateLimitError(
            "Too many login attempts. Please try again later.",
        )

    user, access, refresh = auth_service.login(
        db,
        email=payload.email,
        password=payload.password,
        code=payload.code,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    # Successful login clears the counter for this key.
    _login_limiter.reset(limiter_key)

    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, request: Request, db: DbSession) -> TokenResponse:
    ctx = audit_service.request_context(request)
    _, access, new_refresh = auth_service.refresh(
        db,
        refresh_token=payload.refresh_token,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return TokenResponse(
        access_token=access,
        refresh_token=new_refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", status_code=204, response_class=Response)
def logout(request: Request, user: CurrentUser, db: DbSession) -> Response:
    """Record the logout. Returns an empty body."""
    ctx = audit_service.request_context(request)
    auth_service.logout(
        db, user=user, ip_address=ctx["ip_address"], user_agent=ctx["user_agent"]
    )
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    """Current identity, effective permissions and permitted company ids."""
    return UserOut(**_user_payload(user))


# ---- D11: two-factor authentication (self-service, any authenticated user) ----
@router.get("/2fa", response_model=TwoFactorStatusOut)
def two_factor_status(user: CurrentUser, db: DbSession) -> TwoFactorStatusOut:
    return TwoFactorStatusOut(enabled=two_factor_service.is_enabled(db, user_id=user.id))


@router.post("/2fa/enrol", response_model=TwoFactorEnrolOut)
def two_factor_enrol(user: CurrentUser, db: DbSession) -> TwoFactorEnrolOut:
    """Begin 2FA enrolment. The secret is returned exactly once."""
    return TwoFactorEnrolOut(**two_factor_service.enrol(db, user=user))


@router.post("/2fa/confirm", response_model=TwoFactorConfirmOut)
def two_factor_confirm(
    payload: TwoFactorConfirmRequest, user: CurrentUser, db: DbSession
) -> TwoFactorConfirmOut:
    """Confirm enrolment and receive one-time recovery codes (shown once)."""
    result = two_factor_service.confirm(db, user=user, code=payload.code)
    return TwoFactorConfirmOut(**result)


@router.post("/2fa/disable", status_code=204, response_class=Response)
def two_factor_disable(
    payload: TwoFactorDisableRequest, request: Request, user: CurrentUser, db: DbSession
) -> Response:
    """Disable 2FA. Requires a current code or a recovery code."""
    ctx = audit_service.request_context(request)
    two_factor_service.disable(
        db, user=user, code=payload.code, ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return Response(status_code=204)
