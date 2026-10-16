"""Password hashing and JWT token handling.

Passwords are hashed with bcrypt directly. ``passlib`` is deliberately not used:
its last release predates bcrypt 4.1 and it emits spurious version errors
against current bcrypt, whereas the ``bcrypt`` API is small and stable.

Tokens are signed JWTs carrying only the subject (user id), token type and
expiry -- never roles or company scope, so that authorization is always
re-evaluated server-side from the database on every request.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from backend.core.config import settings

# bcrypt truncates at 72 bytes; reject longer input instead of silently cutting.
MAX_PASSWORD_BYTES = 72

# A precomputed hash used to equalise timing when an account does not exist.
_DUMMY_HASH = bcrypt.hashpw(b"dummy-password-for-timing", bcrypt.gensalt()).decode()


class TokenError(Exception):
    """Raised when a token is missing, malformed, expired or of wrong type."""


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def dummy_verify(password: str) -> None:
    """Burn a comparable amount of time when the account does not exist.

    Without this, a login attempt against an unknown email returns measurably
    faster than one against a real account, which leaks which emails are
    registered.
    """
    verify_password(password, _DUMMY_HASH)


def password_is_valid_length(password: str) -> bool:
    return len(password.encode("utf-8")) <= MAX_PASSWORD_BYTES


def _create_token(
    subject: str, token_type: str, expires_delta: timedelta, extra: dict[str, Any] | None = None
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: int | str) -> str:
    return _create_token(
        str(user_id),
        "access",
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user_id: int | str) -> str:
    return _create_token(
        str(user_id),
        "refresh",
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str, expected_type: str = "access") -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired.") from exc
    except jwt.PyJWTError as exc:
        raise TokenError("Token is invalid.") from exc

    if payload.get("type") != expected_type:
        raise TokenError("Token type is not valid for this operation.")
    if not payload.get("sub"):
        raise TokenError("Token is missing a subject.")
    return payload
