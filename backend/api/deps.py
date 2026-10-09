"""FastAPI dependencies for authentication and authorization.

``get_current_user`` resolves the bearer token to a live database user on every
request, so a revoked or deactivated account loses access immediately rather
than when its token happens to expire.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.core.errors import AuthenticationError, PermissionDeniedError
from backend.core.security import TokenError, decode_token
from backend.db.models.identity import User
from backend.db.session import get_db
from backend.rbac.authorization import (
    accessible_company_ids,
    has_permission,
    require_company_access,
    require_permission,
)

# auto_error=False so we can emit our own consistent error payload.
_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Authentication credentials were not provided.")

    try:
        payload = decode_token(credentials.credentials, expected_type="access")
    except TokenError as exc:
        raise AuthenticationError(str(exc)) from exc

    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthenticationError("Token subject is invalid.") from exc

    user = db.get(User, user_id)
    if user is None:
        raise AuthenticationError("Account no longer exists.")
    if not user.is_active:
        raise AuthenticationError("Account is disabled.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[Session, Depends(get_db)]


def require(permission: str):
    """Build a dependency that enforces a single permission code."""

    def _dep(user: CurrentUser) -> User:
        require_permission(user, permission)
        return user

    return _dep


__all__ = [
    "get_current_user",
    "CurrentUser",
    "DbSession",
    "require",
    "has_permission",
    "accessible_company_ids",
    "require_company_access",
    "PermissionDeniedError",
]
