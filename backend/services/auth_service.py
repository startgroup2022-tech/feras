"""Authentication service: registration, login, token refresh, logout.

Design notes
------------
* Login failures return a single generic message regardless of whether the
  email exists, so the endpoint cannot be used to enumerate accounts.
* The user row is re-read on every request by ``get_current_user``; deactivating
  an account therefore takes effect immediately.
* There is no server-side session store in V1: access tokens are short lived
  and refresh tokens are exchanged for new access tokens. This keeps the
  foundation stateless and horizontally scalable. A token revocation list can
  be added later behind :func:`revoke` without changing callers.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.errors import AuthenticationError, ConflictError, ValidationError
from backend.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    dummy_verify,
    hash_password,
    password_is_valid_length,
    verify_password,
)
from backend.db.base import utcnow
from backend.db.models.audit_actions import AuditAction
from backend.db.models.identity import Role, User
from backend.services import audit_service

logger = logging.getLogger("safir.auth")


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.execute(
        select(User).where(User.email == email.strip().lower())
    ).scalar_one_or_none()


def authenticate(db: Session, email: str, password: str) -> User | None:
    """Return the user when credentials are valid, else ``None``."""
    user = get_user_by_email(db, email)
    if user is None:
        # Still run a hash comparison so response time does not reveal whether
        # the account exists.
        dummy_verify(password)
        return None
    if not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def login(
    db: Session,
    *,
    email: str,
    password: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[User, str, str]:
    """Authenticate and mint a token pair. Raises on failure."""
    user = authenticate(db, email, password)

    if user is None:
        audit_service.record(
            db,
            action=AuditAction.LOGIN_FAILED,
            entity_type="user",
            entity_id=email,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"email": email},
        )
        raise AuthenticationError("Incorrect email or password.")

    user.last_login_at = utcnow()
    db.add(user)
    db.commit()

    audit_service.record(
        db,
        action=AuditAction.LOGIN,
        actor_user_id=user.id,
        entity_type="user",
        entity_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return user, create_access_token(user.id), create_refresh_token(user.id)


def refresh(
    db: Session,
    *,
    refresh_token: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[User, str, str]:
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except TokenError as exc:
        raise AuthenticationError(str(exc)) from exc

    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise AuthenticationError("Account is unavailable.")

    audit_service.record(
        db,
        action=AuditAction.TOKEN_REFRESH,
        actor_user_id=user.id,
        entity_type="user",
        entity_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return user, create_access_token(user.id), create_refresh_token(user.id)


def logout(
    db: Session,
    *,
    user: User | None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Record the logout. Token invalidation is a Phase 2 concern (see module docstring)."""
    audit_service.record(
        db,
        action=AuditAction.LOGOUT,
        actor_user_id=user.id if user else None,
        entity_type="user",
        entity_id=user.id if user else None,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def create_user(
    db: Session,
    *,
    email: str,
    password: str,
    full_name_ar: str,
    full_name_en: str | None,
    role_code: str,
    is_active: bool = True,
) -> User:
    """Create a user with a hashed password. Used by admin API and seed script."""
    email = email.strip().lower()
    if not password_is_valid_length(password):
        raise ValidationError("Password must not exceed 72 bytes.")
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters.")
    if get_user_by_email(db, email) is not None:
        raise ConflictError("A user with this email already exists.")

    role = db.execute(select(Role).where(Role.code == role_code)).scalar_one_or_none()
    if role is None:
        raise ValidationError(f"Unknown role code: {role_code}")

    user = User(
        email=email,
        full_name_ar=full_name_ar,
        full_name_en=full_name_en,
        hashed_password=hash_password(password),
        role_id=role.id,
        is_active=is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
