"""Audit logging service.

Every security-relevant or business-critical action is recorded. Metadata is
redacted before it is persisted, so a stray ``password`` or token in a payload
can never end up in the audit trail.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from backend.core.logging_config import redact
from backend.db.base import utcnow
from backend.db.models.ai import AuditLog

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
