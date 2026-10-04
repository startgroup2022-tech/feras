"""Website branding service: the Holding logo.

The logo is managed like any other Holding metadata -- it is edited from the
administration area and stored on the Holding row -- but the binary lives in
the upload root via :mod:`backend.core.branding_storage`. Only the opaque
storage key and safe display metadata are persisted.

Authorization reuses ``group.manage`` (the permission that already governs the
Holding profile), so no new permission is introduced and existing roles keep
working. Every change is audited.

The public website never sees the storage key: :func:`logo_url` returns a
stable, cache-busting URL that the public API resolves back to the key.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core import branding_storage
from backend.core.errors import ValidationError
from backend.db.base import utcnow
from backend.db.models.audit_actions import AuditAction
from backend.db.models.group import Holding
from backend.db.models.identity import User
from backend.rbac.authorization import require_permission
from backend.rbac.permissions import Perm
from backend.services import audit_service

# Public path the website and the admin preview both use.
LOGO_PATH = "/api/v1/public/branding/logo"


def get_holding(db: Session) -> Holding:
    """Return the Holding row, creating a default one if none exists.

    Delegates to the group service so there is exactly one definition of the
    default Holding.
    """
    from backend.services import holding_service

    return holding_service.get_holding(db)


def logo_url(holding: Holding | None) -> str | None:
    """The public URL of the uploaded logo, or ``None`` for the fallback mark.

    A ``?v=`` cache-buster derived from ``logo_updated_at`` means a re-upload
    is picked up immediately by browsers and CDNs without a purge.
    """
    if holding is None or not holding.logo_storage_key:
        return None
    stamp = holding.logo_updated_at or holding.updated_at
    version = int(stamp.timestamp()) if isinstance(stamp, datetime) else 0
    return f"{LOGO_PATH}?v={version}"


def branding_payload(db: Session) -> dict:
    """Public branding values, degrading gracefully if the asset is missing.

    If the Holding points at a logo whose file has gone (a failed disk, a
    manual deletion), the URL is suppressed so the site shows its fallback
    mark instead of a broken image.
    """
    holding = (
        db.execute(select(Holding).order_by(Holding.id).limit(1))
        .scalar_one_or_none()
    )
    if holding is None or not holding.logo_storage_key:
        return {"logo_url": None, "logo_updated_at": None}
    try:
        branding_storage.resolve_branding_path(holding.logo_storage_key)
    except Exception:  # noqa: BLE001 - missing file -> fallback
        return {"logo_url": None, "logo_updated_at": None}
    return {
        "logo_url": logo_url(holding),
        "logo_updated_at": holding.logo_updated_at,
    }


def set_logo(
    db: Session,
    *,
    actor: User,
    data: bytes,
    filename: str,
    content_type: str | None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Holding:
    """Store a new logo and point the Holding at it.

    Validation (type/size) happens in the storage layer. The previous asset is
    deleted only after the new one is stored and committed, so a failure cannot
    leave the site without a logo.
    """
    require_permission(actor, Perm.GROUP_MANAGE)

    extension = branding_storage.validate_branding_image(
        filename=filename, content_type=content_type, size=len(data)
    )
    new_key = branding_storage.store_branding_bytes(data=data, extension=extension)

    holding = get_holding(db)
    previous_key = holding.logo_storage_key

    holding.logo_storage_key = new_key
    holding.logo_content_type = content_type
    holding.logo_original_name = (filename or "")[:255] or None
    holding.logo_updated_at = utcnow()
    db.add(holding)
    db.commit()
    db.refresh(holding)

    if previous_key and previous_key != new_key:
        branding_storage.delete_branding_bytes(previous_key)

    audit_service.record(
        db,
        action=AuditAction.BRANDING_LOGO_UPDATED,
        actor_user_id=actor.id,
        entity_type="holding",
        entity_id=holding.id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"content_type": content_type, "bytes": len(data)},
    )
    return holding


def remove_logo(
    db: Session,
    *,
    actor: User,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Holding:
    """Clear the logo so the public site shows its built-in fallback mark."""
    require_permission(actor, Perm.GROUP_MANAGE)

    holding = get_holding(db)
    previous_key = holding.logo_storage_key
    if not previous_key:
        raise ValidationError("There is no logo to remove.")

    holding.logo_storage_key = None
    holding.logo_content_type = None
    holding.logo_original_name = None
    holding.logo_updated_at = None
    db.add(holding)
    db.commit()
    db.refresh(holding)

    branding_storage.delete_branding_bytes(previous_key)

    audit_service.record(
        db,
        action=AuditAction.BRANDING_LOGO_REMOVED,
        actor_user_id=actor.id,
        entity_type="holding",
        entity_id=holding.id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={},
    )
    return holding


def resolve_logo(db: Session):
    """Return ``(path, content_type)`` for the current logo, or ``(None, None)``.

    Used by the public endpoint that streams the image. Reads the singleton
    Holding directly so an unauthenticated request never needs the group
    service's write path.
    """
    holding = (
        db.execute(select(Holding).order_by(Holding.id).limit(1))
        .scalar_one_or_none()
    )
    if holding is None or not holding.logo_storage_key:
        return None, None
    try:
        path = branding_storage.resolve_branding_path(holding.logo_storage_key)
    except Exception:  # noqa: BLE001 - a missing file degrades to the fallback
        return None, None
    return path, holding.logo_content_type


__all__ = [
    "LOGO_PATH",
    "branding_payload",
    "get_holding",
    "logo_url",
    "remove_logo",
    "resolve_logo",
    "set_logo",
]
