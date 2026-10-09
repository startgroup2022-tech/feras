"""Holding (group) metadata service.

The Holding is a single logical entity. ``get_holding`` creates the row on first
use from a sane default so the group profile is always present and editable
rather than being hardcoded in the frontend.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.errors import ValidationError
from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import HoldingStatus
from backend.db.models.group import Holding
from backend.db.models.identity import User
from backend.rbac.authorization import require_permission
from backend.rbac.permissions import Perm
from backend.services import audit_service

_DEFAULT_CODE = "SAFIR"


def get_holding(db: Session) -> Holding:
    """Return the Holding row, creating a default one if none exists."""
    holding = db.execute(
        select(Holding).order_by(Holding.id).limit(1)
    ).scalar_one_or_none()
    if holding is None:
        holding = Holding(
            code=_DEFAULT_CODE,
            legal_name_ar="شركة سفير القابضة",
            legal_name_en="Safir Holding Company",
            display_name_ar="سفير القابضة",
            display_name_en="Safir Holding",
            default_currency="SAR",
            status=HoldingStatus.ACTIVE.value,
        )
        db.add(holding)
        db.commit()
        db.refresh(holding)
    return holding


def update_holding(
    db: Session,
    *,
    actor: User,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> Holding:
    require_permission(actor, Perm.GROUP_MANAGE)
    holding = get_holding(db)

    fields = (
        "legal_name_ar",
        "legal_name_en",
        "display_name_ar",
        "display_name_en",
        "country",
        "commercial_registration",
        "tax_number",
        "default_currency",
        "contact_email",
        "phone",
        "address",
        "status",
    )
    for field in fields:
        if field in payload and payload[field] is not None:
            setattr(holding, field, payload[field])

    if holding.status not in {s.value for s in HoldingStatus}:
        raise ValidationError("Invalid holding status.")

    db.add(holding)
    db.commit()
    db.refresh(holding)

    audit_service.record(
        db,
        action=AuditAction.HOLDING_UPDATED,
        actor_user_id=actor.id,
        entity_type="holding",
        entity_id=holding.id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"fields": sorted(payload.keys())},
    )
    return holding


__all__ = ["get_holding", "update_holding"]
