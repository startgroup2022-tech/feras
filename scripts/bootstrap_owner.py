"""Secure first-owner bootstrap for an empty Safir Holding 2027 database.

Creates the *first real* Holding Owner on a freshly migrated database, after
initialising the RBAC catalogue. This is the supported production/staging path;
``scripts/seed_demo.py`` must never be used there.

Guarantees
----------
* No demo credentials are accepted (the demo password and ``@demo.safir.local``
  domain are rejected outright).
* A strong password is required. It is supplied interactively (never echoed) or
  via the ``SAFIR_OWNER_PASSWORD`` environment variable. Passing ``--password``
  on the command line is supported but discouraged because the shell may keep
  it in history.
* The password is never written to logs or stdout.
* Re-running against a database that already has a Holding Owner is refused, so
  the operation cannot silently create a second initial owner.
* The RBAC catalogue is synced before the owner is created, so the owner's role
  and permissions exist.

Usage::

    # interactive (recommended)
    python -m scripts.bootstrap_owner \
        --email owner@holding.sa --name-ar "عبدالله السفير"

    # non-interactive (CI / provisioning), password from the environment
    SAFIR_OWNER_PASSWORD='<strong>' python -m scripts.bootstrap_owner \
        --email owner@holding.sa --name-ar "عبدالله السفير"
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from backend.core.security import password_is_valid_length  # noqa: E402
from backend.db.models.identity import Role, User  # noqa: E402
from backend.db.session import session_scope  # noqa: E402
from backend.services.auth_service import create_user  # noqa: E402
from backend.services.rbac_service import bootstrap_rbac  # noqa: E402

OWNER_ROLE_CODE = "holding_owner"
DEMO_EMAIL_DOMAIN = "demo.safir.local"
DEMO_PASSWORD = "SafirDemo!2027"
MIN_PASSWORD_LENGTH = 12

# Values that must never become a real owner password.
FORBIDDEN_PASSWORDS = {DEMO_PASSWORD, "dev-only-insecure-change-me"}


class BootstrapError(Exception):
    """A bootstrap precondition failed. The message is safe to show a user."""


def password_problem(password: str) -> str | None:
    """Return a human-readable problem with the password, or ``None`` if strong.

    The rules are deliberately simple and explained to the operator rather than
    enforced silently: length, character variety, and a ban on known demo/dev
    values. bcrypt's 72-byte cap is enforced separately.
    """
    if password in FORBIDDEN_PASSWORDS:
        return "This password is a known demo/development value and cannot be used."
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if not password_is_valid_length(password):
        return "Password must not exceed 72 bytes."
    classes = 0
    classes += any(c.islower() for c in password)
    classes += any(c.isupper() for c in password)
    classes += any(c.isdigit() for c in password)
    classes += any(not c.isalnum() for c in password)
    if classes < 3:
        return (
            "Password must combine at least three of: lowercase, uppercase, "
            "digits, symbols."
        )
    return None


def existing_owner_count(db) -> int:
    role = db.execute(select(Role).where(Role.code == OWNER_ROLE_CODE)).scalar_one_or_none()
    if role is None:
        return 0
    return db.execute(
        select(func.count(User.id)).where(User.role_id == role.id)
    ).scalar_one()


def bootstrap_owner(
    db,
    *,
    email: str,
    full_name_ar: str,
    full_name_en: str | None,
    password: str,
) -> User:
    """Create the first Holding Owner. Raises :class:`BootstrapError` on misuse."""
    email = email.strip().lower()

    if not email or "@" not in email:
        raise BootstrapError("A valid owner email is required.")
    if email.endswith("@" + DEMO_EMAIL_DOMAIN):
        raise BootstrapError("Demo email addresses cannot be used for a real owner.")

    problem = password_problem(password)
    if problem:
        raise BootstrapError(problem)

    # RBAC first, so the owner role exists before it is referenced.
    bootstrap_rbac(db)

    if existing_owner_count(db) > 0:
        raise BootstrapError(
            "A Holding Owner already exists. Refusing to create a second initial "
            "owner; use the admin API to add more users."
        )

    return create_user(
        db,
        email=email,
        password=password,
        full_name_ar=full_name_ar,
        full_name_en=full_name_en,
        role_code=OWNER_ROLE_CODE,
    )


def _resolve_password(args: argparse.Namespace) -> str:
    if args.password:
        return args.password
    from_env = os.environ.get("SAFIR_OWNER_PASSWORD")
    if from_env:
        return from_env
    first = getpass.getpass("Owner password: ")
    second = getpass.getpass("Confirm password: ")
    if first != second:
        raise BootstrapError("Passwords do not match.")
    return first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create the first Holding Owner.")
    parser.add_argument("--email", required=True, help="Owner email address")
    parser.add_argument("--name-ar", required=True, help="Owner name (Arabic)")
    parser.add_argument("--name-en", default=None, help="Owner name (English)")
    parser.add_argument(
        "--password",
        default=None,
        help="Password (discouraged; prefer interactive input or SAFIR_OWNER_PASSWORD)",
    )
    args = parser.parse_args(argv)

    try:
        password = _resolve_password(args)
    except BootstrapError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        with session_scope() as db:
            bootstrap_owner(
                db,
                email=args.email,
                full_name_ar=args.name_ar,
                full_name_en=args.name_en,
                password=password,
            )
    except BootstrapError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # Never echo the password -- only the account that was created.
    print(f"Holding Owner created: {args.email.strip().lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
