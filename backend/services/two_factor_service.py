"""D11: two-factor authentication (TOTP, RFC 6238) and recovery codes.

Implemented without a third-party dependency so the security-critical code is
small and auditable. A TOTP secret is generated at enrolment, returned **once**,
and only counts as "on" after the user confirms it with a valid code. Recovery
codes are generated once, shown once, and stored only as hashes.

Security properties enforced here:

* the secret is never returned after enrolment;
* a code is single-use within its window (``last_used_counter`` blocks replay);
* login 2FA is verified server-side from the stored secret -- a client cannot
  bypass it by omitting a field, because the login path checks ``is_enabled``
  and requires a valid code/recovery code;
* enrolment and disabling are audited.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.errors import ConflictError, NotFoundError, ValidationError
from backend.db.base import utcnow
from backend.db.models.audit_actions import AuditAction
from backend.db.models.governance import TwoFactorRecoveryCode, UserTwoFactor
from backend.db.models.identity import User
from backend.rbac.authorization import require_permission
from backend.rbac.permissions import Perm
from backend.services import audit_service

TOTP_DIGITS = 6
TOTP_INTERVAL = 30
TOTP_WINDOW = 1  # accept the previous and next step for clock skew
RECOVERY_CODE_COUNT = 8


def generate_secret() -> str:
    """A base32 TOTP secret (20 random bytes, the RFC-recommended size)."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _hotp(secret: str, counter: int) -> str:
    padding = "=" * (-len(secret) % 8)
    key = base64.b32decode(secret + padding)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(binary % (10 ** TOTP_DIGITS)).zfill(TOTP_DIGITS)


def totp_now(secret: str, *, at: int | None = None) -> str:
    counter = (at if at is not None else int(time.time())) // TOTP_INTERVAL
    return _hotp(secret, counter)


def verify_totp(secret: str, code: str, *, at: int | None = None) -> int | None:
    """Return the matched counter, or ``None`` when the code is invalid.

    Accepts a one-step window either side for clock skew.
    """
    if not code or not code.strip().isdigit():
        return None
    code = code.strip()
    now = at if at is not None else int(time.time())
    base = now // TOTP_INTERVAL
    for offset in range(-TOTP_WINDOW, TOTP_WINDOW + 1):
        counter = base + offset
        if hmac.compare_digest(_hotp(secret, counter), code):
            return counter
    return None


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def get_two_factor(db: Session, *, user_id: int) -> UserTwoFactor | None:
    return db.execute(
        select(UserTwoFactor).where(UserTwoFactor.user_id == user_id)
    ).scalar_one_or_none()


def is_enabled(db: Session, *, user_id: int) -> bool:
    row = get_two_factor(db, user_id=user_id)
    return bool(row and row.is_enabled)


def enrol(db: Session, *, user: User, ip_address: str | None = None,
          user_agent: str | None = None) -> dict:
    """Begin enrolment: return the secret and an otpauth URI, once.

    The factor is not enabled until ``confirm`` supplies a valid code, so an
    abandoned enrolment never locks a user out or counts as 2FA.
    """
    row = get_two_factor(db, user_id=user.id)
    if row is not None and row.is_enabled:
        raise ConflictError("Two-factor authentication is already enabled.")
    secret = generate_secret()
    if row is None:
        row = UserTwoFactor(user_id=user.id, secret=secret, is_enabled=False)
        db.add(row)
    else:
        row.secret = secret
        row.is_enabled = False
        row.confirmed_at = None
        row.last_used_counter = None
        db.add(row)
    db.commit()
    db.refresh(row)
    label = f"Safir:{user.email}"
    uri = (
        f"otpauth://totp/{label}?secret={secret}"
        f"&issuer=Safir&digits={TOTP_DIGITS}&period={TOTP_INTERVAL}"
    )
    return {"secret": secret, "otpauth_uri": uri}


def confirm(db: Session, *, user: User, code: str, ip_address: str | None = None,
            user_agent: str | None = None) -> dict:
    """Confirm enrolment with a valid code and issue recovery codes (once)."""
    row = get_two_factor(db, user_id=user.id)
    if row is None:
        raise NotFoundError("Start enrolment before confirming it.")
    if row.is_enabled:
        raise ConflictError("Two-factor authentication is already enabled.")
    counter = verify_totp(row.secret, code)
    if counter is None:
        raise ValidationError("The verification code is invalid.")

    row.is_enabled = True
    row.confirmed_at = utcnow()
    db.add(row)

    # Fresh recovery codes: remove any old set, issue a new one.
    for old in db.execute(
        select(TwoFactorRecoveryCode).where(TwoFactorRecoveryCode.user_id == user.id)
    ).scalars():
        db.delete(old)
    codes = [_recovery_code() for _ in range(RECOVERY_CODE_COUNT)]
    for code_plain in codes:
        db.add(TwoFactorRecoveryCode(user_id=user.id, code_hash=_hash_code(code_plain)))
    db.commit()
    audit_service.record(
        db, action=AuditAction.TWO_FACTOR_ENROLLED, actor_user_id=user.id,
        entity_type="user", entity_id=user.id, ip_address=ip_address,
        user_agent=user_agent,
    )
    return {"recovery_codes": codes}


def disable(db: Session, *, user: User, code: str, ip_address: str | None = None,
            user_agent: str | None = None) -> None:
    """Disable 2FA. Requires a currently valid code (or a recovery code)."""
    row = get_two_factor(db, user_id=user.id)
    if row is None or not row.is_enabled:
        raise ConflictError("Two-factor authentication is not enabled.")
    if not _consume(db, user=user, row=row, code=code):
        raise ValidationError("The verification code is invalid.")
    row.is_enabled = False
    row.confirmed_at = None
    db.add(row)
    for rc in db.execute(
        select(TwoFactorRecoveryCode).where(TwoFactorRecoveryCode.user_id == user.id)
    ).scalars():
        db.delete(rc)
    db.commit()
    audit_service.record(
        db, action=AuditAction.TWO_FACTOR_DISABLED, actor_user_id=user.id,
        entity_type="user", entity_id=user.id, ip_address=ip_address,
        user_agent=user_agent,
    )


def verify_login(db: Session, *, user: User, code: str, ip_address: str | None = None,
                 user_agent: str | None = None) -> bool:
    """Verify a second factor at login. Records success/failure."""
    row = get_two_factor(db, user_id=user.id)
    if row is None or not row.is_enabled:
        return True  # no second factor required
    ok = _consume(db, user=user, row=row, code=code)
    audit_service.record(
        db,
        action=(AuditAction.TWO_FACTOR_VERIFIED if ok else AuditAction.TWO_FACTOR_FAILED),
        actor_user_id=user.id, entity_type="user", entity_id=user.id,
        ip_address=ip_address, user_agent=user_agent,
    )
    return ok


def reset_for_user(db: Session, *, actor: User, target_user_id: int,
                   ip_address: str | None = None, user_agent: str | None = None) -> None:
    """Owner-only: clear a user's 2FA (e.g. lost device, with identity proof)."""
    require_permission(actor, Perm.TWO_FACTOR_ENFORCE)
    row = get_two_factor(db, user_id=target_user_id)
    if row is None:
        raise NotFoundError("This user has no two-factor configuration.")
    db.delete(row)
    for rc in db.execute(
        select(TwoFactorRecoveryCode).where(
            TwoFactorRecoveryCode.user_id == target_user_id
        )
    ).scalars():
        db.delete(rc)
    db.commit()
    audit_service.record(
        db, action=AuditAction.TWO_FACTOR_RESET, actor_user_id=actor.id,
        entity_type="user", entity_id=target_user_id, ip_address=ip_address,
        user_agent=user_agent,
    )


def _recovery_code() -> str:
    raw = secrets.token_hex(5).upper()
    return f"{raw[:5]}-{raw[5:]}"


def _consume(db: Session, *, user: User, row: UserTwoFactor, code: str) -> bool:
    """Accept a TOTP code (single-use) or a one-time recovery code."""
    counter = verify_totp(row.secret, code)
    if counter is not None:
        if row.last_used_counter is not None and counter <= row.last_used_counter:
            return False  # replay of an already-used step
        row.last_used_counter = counter
        db.add(row)
        db.commit()
        return True

    candidate = (code or "").strip().upper()
    digest = _hash_code(candidate)
    for rc in db.execute(
        select(TwoFactorRecoveryCode).where(
            TwoFactorRecoveryCode.user_id == user.id,
            TwoFactorRecoveryCode.used_at.is_(None),
        )
    ).scalars():
        if hmac.compare_digest(rc.code_hash, digest):
            rc.used_at = utcnow()
            db.add(rc)
            db.commit()
            audit_service.record(
                db, action=AuditAction.RECOVERY_CODE_USED, actor_user_id=user.id,
                entity_type="user", entity_id=user.id,
            )
            return True
    return False


__all__ = [
    "confirm",
    "disable",
    "enrol",
    "generate_secret",
    "get_two_factor",
    "is_enabled",
    "reset_for_user",
    "totp_now",
    "verify_login",
    "verify_totp",
]
