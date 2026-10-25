"""Audit logging service.

Every security-relevant or business-critical action is recorded. Metadata is
redacted before it is persisted, so a stray ``password`` or token in a payload
can never end up in the audit trail.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.logging_config import redact
from backend.db.base import utcnow
from backend.db.models.ai import AuditLog
from backend.db.models.identity import User

logger = logging.getLogger("safir.audit")


def record(
    db: Session,
    *,
    action: str,
    actor_user_id: int | None = None,
    entity_type: str | None = None,
    entity_id: str | int | None = None,
    company_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    metadata: dict | None = None,
    commit: bool = True,
) -> AuditLog:
    """Write one immutable audit row."""
    entry = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        company_id=company_id,
        ip_address=ip_address,
        user_agent=(user_agent or "")[:255] or None,
        meta_json=json.dumps(redact(metadata), ensure_ascii=False, default=str)
        if metadata
        else None,
        created_at=utcnow(),
    )
    db.add(entry)
    if commit:
        db.commit()
    logger.info(
        "audit action=%s actor=%s entity=%s:%s company=%s",
        action,
        actor_user_id,
        entity_type,
        entity_id,
        company_id,
    )
    return entry


def list_audit_logs(
    db: Session,
    *,
    limit: int = 50,
    offset: int = 0,
    action: str | None = None,
    actor_user_id: int | None = None,
    entity_type: str | None = None,
    company_id: int | None = None,
) -> dict:
    """Paginated audit trail, newest first.

    Authorization is enforced by the caller (``AUDIT_READ``); this function is a
    pure query helper so it stays trivially testable.
    """
    conditions = []
    if action:
        conditions.append(AuditLog.action == action)
    if actor_user_id is not None:
        conditions.append(AuditLog.actor_user_id == actor_user_id)
    if entity_type:
        conditions.append(AuditLog.entity_type == entity_type)
    if company_id is not None:
        conditions.append(AuditLog.company_id == company_id)

    count_stmt = select(func.count(AuditLog.id))
    for condition in conditions:
        count_stmt = count_stmt.where(condition)
    total = int(db.execute(count_stmt).scalar_one())

    stmt = select(AuditLog)
    for condition in conditions:
        stmt = stmt.where(condition)
    rows = list(
        db.execute(
            stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
            .offset(offset)
        ).scalars()
    )

    actor_ids = {row.actor_user_id for row in rows if row.actor_user_id}
    actors: dict[int, User] = {}
    if actor_ids:
        for actor in db.execute(select(User).where(User.id.in_(actor_ids))).scalars():
            actors[actor.id] = actor

    items = []
    for row in rows:
        actor = actors.get(row.actor_user_id) if row.actor_user_id else None
        meta = None
        if row.meta_json:
            try:
                meta = json.loads(row.meta_json)
            except (TypeError, ValueError):
                meta = None
        items.append(
            {
                "id": row.id,
                "actor_user_id": row.actor_user_id,
                "actor_name_ar": actor.full_name_ar if actor else None,
                "actor_name_en": actor.full_name_en if actor else None,
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "company_id": row.company_id,
                "ip_address": row.ip_address,
                "meta": meta,
                "created_at": row.created_at,
            }
        )
    return {"total": total, "limit": limit, "offset": offset, "items": items}


def request_context(request) -> dict[str, str | None]:
    """Extract safe client context from a request for audit records."""
    if request is None:
        return {"ip_address": None, "user_agent": None}
    client = getattr(request, "client", None)
    ip = getattr(client, "host", None) if client else None
    # Respect a proxy header only if present; never trust it for authorization.
    forwarded = request.headers.get("x-forwarded-for") if request.headers else None
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    return {
        "ip_address": ip,
        "user_agent": request.headers.get("user-agent") if request.headers else None,
    }
