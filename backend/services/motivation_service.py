"""Motivational sentence library service (S01).

Spec §7 / Table 74: each role dashboard shows one motivational sentence drawn
from a small, owner-editable bilingual library. Reads need ``motivation.read``
(every scoped dashboard role has it); writes need ``motivation.manage``.

``pick_for_role`` returns the sentence a dashboard should display: the first
active row matching the caller's role, falling back to the first active
role-agnostic row. It is deterministic (``sort_order`` then id) so the same
dashboard always shows the same sentence for the same library state.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.errors import NotFoundError
from backend.db.models.audit_actions import AuditAction
from backend.db.models.identity import User
from backend.db.models.operations import MotivationText
from backend.rbac.authorization import require_permission
from backend.rbac.permissions import Perm
from backend.services import audit_service


def _serialise(row: MotivationText) -> dict:
    return {
        "id": row.id,
        "text_ar": row.text_ar,
        "text_en": row.text_en,
        "audience_role": row.audience_role,
        "sort_order": row.sort_order,
        "is_active": row.is_active,
    }


def list_motivation_texts(
    db: Session, *, user: User, include_inactive: bool = False
) -> list[dict]:
    require_permission(user, Perm.MOTIVATION_READ)
    stmt = select(MotivationText).order_by(
        MotivationText.sort_order, MotivationText.id
    )
    if not include_inactive:
        stmt = stmt.where(MotivationText.is_active.is_(True))
    return [_serialise(row) for row in db.execute(stmt).scalars()]


def pick_for_role(db: Session, *, role_code: str | None) -> dict | None:
    """The sentence a dashboard shows for ``role_code`` (no permission gate).

    Called while assembling a dashboard payload the caller is already allowed
    to read, so it deliberately does not require ``motivation.read`` again.
    """
    rows = list(
        db.execute(
            select(MotivationText)
            .where(MotivationText.is_active.is_(True))
            .order_by(MotivationText.sort_order, MotivationText.id)
        ).scalars()
    )
    if role_code:
        for row in rows:
            if row.audience_role == role_code:
                return _serialise(row)
    for row in rows:
        if row.audience_role is None:
            return _serialise(row)
    return _serialise(rows[0]) if rows else None


def create_motivation_text(
    db: Session,
    *,
    actor: User,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    require_permission(actor, Perm.MOTIVATION_MANAGE)
    row = MotivationText(
        text_ar=payload["text_ar"],
        text_en=payload["text_en"],
        audience_role=payload.get("audience_role"),
        sort_order=payload.get("sort_order") or 0,
        is_active=payload.get("is_active", True),
        created_by_id=actor.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    audit_service.record(
        db,
        action=AuditAction.MOTIVATION_CREATED,
        actor_user_id=actor.id,
        entity_type="motivation_text",
        entity_id=row.id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"audience_role": row.audience_role},
    )
    return _serialise(row)


def update_motivation_text(
    db: Session,
    *,
    actor: User,
    motivation_id: int,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    require_permission(actor, Perm.MOTIVATION_MANAGE)
    row = db.get(MotivationText, motivation_id)
    if row is None:
        raise NotFoundError("Motivational sentence not found.")

    for field in ("text_ar", "text_en", "audience_role", "sort_order", "is_active"):
        if field in payload and payload[field] is not None:
            setattr(row, field, payload[field])

    db.add(row)
    db.commit()
    db.refresh(row)

    audit_service.record(
        db,
        action=AuditAction.MOTIVATION_UPDATED,
        actor_user_id=actor.id,
        entity_type="motivation_text",
        entity_id=row.id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"fields": sorted(payload.keys())},
    )
    return _serialise(row)


__all__ = [
    "create_motivation_text",
    "list_motivation_texts",
    "pick_for_role",
    "update_motivation_text",
]
