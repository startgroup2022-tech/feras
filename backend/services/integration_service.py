"""External integration service.

This is the single seam through which the platform talks to the outside world.
Business services never call an email library or an HTTP client directly; they
call :func:`emit` (a domain event) or :func:`send_email`. That keeps three
properties true:

* **No vendor lock-in** -- the transport is chosen by configuration, and adding
  a provider is a new adapter, not a change to business logic.
* **Failure isolation** -- every outbound attempt is wrapped; a broken
  subscriber or SMTP server is recorded on a delivery row and never surfaces to
  the user who triggered the business action.
* **No secret leakage** -- an endpoint's signing secret is written once and is
  never returned by any read path; a rotation returns the new value exactly once.

Webhook subscriptions are matched on two axes: the event type they subscribe to
and the company scope they were created for. A company-scoped subscriber never
receives another company's event.
"""

from __future__ import annotations

import logging
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.errors import NotFoundError, ValidationError
from backend.db.base import utcnow
from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import DeliveryStatus, WebhookEventType, WebhookStatus
from backend.db.models.identity import User
from backend.db.models.integrations import WebhookDelivery, WebhookEndpoint
from backend.integrations import EmailMessage, get_email_provider, validate_outbound_url
from backend.rbac.authorization import require_permission
from backend.rbac.permissions import Perm
from backend.services import audit_service

logger = logging.getLogger("safir.integrations")

# The complete set of event types a subscriber may choose. Exposed so the admin
# UI and the API can validate against one list.
SUPPORTED_EVENTS: tuple[str, ...] = tuple(e.value for e in WebhookEventType)


# --------------------------------------------------------------------------
# serialisation
# --------------------------------------------------------------------------
def serialise_endpoint(endpoint: WebhookEndpoint, *, delivery_count: int = 0) -> dict:
    """Public view of an endpoint. The signing secret is deliberately absent."""
    return {
        "id": endpoint.id,
        "name": endpoint.name,
        "url": endpoint.url,
        "status": endpoint.status,
        "scope": endpoint.scope,
        "company_id": endpoint.company_id,
        "subscribed_events": split_events(endpoint.subscribed_events),
        "description": endpoint.description,
        "last_delivery_at": endpoint.last_delivery_at,
        "last_status": endpoint.last_status,
        "delivery_count": delivery_count,
        "created_at": endpoint.created_at,
    }


def serialise_delivery(delivery: WebhookDelivery) -> dict:
    return {
        "id": delivery.id,
        "endpoint_id": delivery.endpoint_id,
        "event_id": delivery.event_id,
        "event_type": delivery.event_type,
        "status": delivery.status,
        "attempt_count": delivery.attempt_count,
        "response_status": delivery.response_status,
        "error": delivery.error,
        "last_attempt_at": delivery.last_attempt_at,
        "created_at": delivery.created_at,
    }


def split_events(value: str | None) -> list[str]:
    return [e.strip() for e in (value or "").split(",") if e.strip()]


# --------------------------------------------------------------------------
# admin CRUD
# --------------------------------------------------------------------------
def list_endpoints(db: Session, *, user: User) -> list[dict]:
    require_permission(user, Perm.INTEGRATION_READ)
    rows = list(
        db.execute(select(WebhookEndpoint).order_by(WebhookEndpoint.created_at.desc())).scalars()
    )
    counts: dict[int, int] = {}
    for endpoint_id in [r.id for r in rows]:
        counts[endpoint_id] = len(
            list(
                db.execute(
                    select(WebhookDelivery.id).where(
                        WebhookDelivery.endpoint_id == endpoint_id
                    )
                ).scalars()
            )
        )
    return [serialise_endpoint(r, delivery_count=counts.get(r.id, 0)) for r in rows]


def create_endpoint(
    db: Session,
    *,
    actor: User,
    name: str,
    url: str,
    subscribed_events: list[str],
    scope: str = "holding",
    company_id: int | None = None,
    description: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[WebhookEndpoint, str]:
    """Create a subscription and return it with its one-time signing secret."""
    require_permission(actor, Perm.INTEGRATION_MANAGE)
    _validate_events(subscribed_events)
    if scope not in ("holding", "company"):
        raise ValidationError("Scope must be 'holding' or 'company'.")
    if scope == "company" and company_id is None:
        raise ValidationError("A company-scoped webhook requires a company_id.")

    safe_url = validate_outbound_url(url)
    secret = secrets.token_urlsafe(32)
    endpoint = WebhookEndpoint(
        name=name.strip(),
        url=safe_url,
        status=WebhookStatus.ACTIVE.value,
        subscribed_events=",".join(sorted(set(subscribed_events))),
        scope=scope,
        company_id=company_id if scope == "company" else None,
        signing_secret=secret,
        description=description,
        created_by_id=actor.id,
    )
    db.add(endpoint)
    db.commit()
    db.refresh(endpoint)

    audit_service.record(
        db,
        action=AuditAction.INTEGRATION_CREATED,
        actor_user_id=actor.id,
        entity_type="webhook_endpoint",
        entity_id=endpoint.id,
        company_id=endpoint.company_id,
        metadata={"events": subscribed_events, "scope": scope},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return endpoint, secret


def update_endpoint(
    db: Session,
    *,
    actor: User,
    endpoint_id: int,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> WebhookEndpoint:
    require_permission(actor, Perm.INTEGRATION_MANAGE)
    endpoint = _get_or_404(db, endpoint_id)

    if "url" in payload and payload["url"]:
        endpoint.url = validate_outbound_url(payload["url"])
    if "name" in payload and payload["name"]:
        endpoint.name = payload["name"].strip()
    if "description" in payload:
        endpoint.description = payload["description"]
    if "subscribed_events" in payload and payload["subscribed_events"] is not None:
        _validate_events(payload["subscribed_events"])
        endpoint.subscribed_events = ",".join(sorted(set(payload["subscribed_events"])))
    if "status" in payload and payload["status"]:
        if payload["status"] not in (WebhookStatus.ACTIVE.value, WebhookStatus.INACTIVE.value):
            raise ValidationError("Unknown webhook status.")
        endpoint.status = payload["status"]

    db.add(endpoint)
    db.commit()
    db.refresh(endpoint)

    audit_service.record(
        db,
        action=AuditAction.INTEGRATION_UPDATED,
        actor_user_id=actor.id,
        entity_type="webhook_endpoint",
        entity_id=endpoint.id,
        company_id=endpoint.company_id,
        metadata={"fields": sorted(k for k in payload if k != "signing_secret")},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return endpoint


def disable_endpoint(
    db: Session,
    *,
    actor: User,
    endpoint_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> WebhookEndpoint:
    require_permission(actor, Perm.INTEGRATION_MANAGE)
    endpoint = _get_or_404(db, endpoint_id)
    endpoint.status = WebhookStatus.INACTIVE.value
    db.add(endpoint)
    db.commit()
    db.refresh(endpoint)
    audit_service.record(
        db,
        action=AuditAction.INTEGRATION_DISABLED,
        actor_user_id=actor.id,
        entity_type="webhook_endpoint",
        entity_id=endpoint.id,
        company_id=endpoint.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return endpoint


def rotate_secret(
    db: Session, *, actor: User, endpoint_id: int
) -> tuple[WebhookEndpoint, str]:
    require_permission(actor, Perm.INTEGRATION_MANAGE)
    endpoint = _get_or_404(db, endpoint_id)
    secret = secrets.token_urlsafe(32)
    endpoint.signing_secret = secret
    db.add(endpoint)
    db.commit()
    db.refresh(endpoint)
    audit_service.record(
        db,
        action=AuditAction.INTEGRATION_SECRET_ROTATED,
        actor_user_id=actor.id,
        entity_type="webhook_endpoint",
        entity_id=endpoint.id,
        company_id=endpoint.company_id,
    )
    return endpoint, secret


def list_deliveries(
    db: Session, *, user: User, endpoint_id: int | None = None, limit: int = 50
) -> list[dict]:
    require_permission(user, Perm.INTEGRATION_READ)
    stmt = select(WebhookDelivery).order_by(WebhookDelivery.created_at.desc()).limit(limit)
    if endpoint_id is not None:
        stmt = stmt.where(WebhookDelivery.endpoint_id == endpoint_id)
    return [serialise_delivery(d) for d in db.execute(stmt).scalars()]


def _get_or_404(db: Session, endpoint_id: int) -> WebhookEndpoint:
    endpoint = db.get(WebhookEndpoint, endpoint_id)
    if endpoint is None:
        raise NotFoundError("Integration endpoint not found.")
    return endpoint


def _validate_events(events: list[str]) -> None:
    unknown = [e for e in (events or []) if e not in SUPPORTED_EVENTS]
    if unknown:
        raise ValidationError("Unknown event type(s): " + ", ".join(unknown))
    if not events:
        raise ValidationError("At least one event type must be subscribed.")


# --------------------------------------------------------------------------
# event emission
# --------------------------------------------------------------------------
def matching_endpoints(db: Session, *, event_type: str, company_id: int | None) -> list[WebhookEndpoint]:
    """Active endpoints subscribed to ``event_type`` and in scope for ``company_id``."""
    rows = list(
        db.execute(
            select(WebhookEndpoint).where(WebhookEndpoint.status == WebhookStatus.ACTIVE.value)
        ).scalars()
    )
    matched = []
    for endpoint in rows:
        if event_type not in split_events(endpoint.subscribed_events):
            continue
        if endpoint.scope == "company" and endpoint.company_id != company_id:
            continue
        matched.append(endpoint)
    return matched


def emit(
    db: Session,
    *,
    event_type: str,
    payload: dict,
    company_id: int | None = None,
) -> list[dict]:
    """Record and (when enabled) deliver a domain event to matching subscribers.

    Always returns the per-endpoint results so a caller or test can assert what
    happened. Never raises.
    """
    try:
        endpoints = matching_endpoints(db, event_type=event_type, company_id=company_id)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to resolve webhook endpoints for %s", event_type)
        return []
    if not endpoints:
        return []

    results: list[dict] = []
    for endpoint in endpoints:
        delivery = _record_delivery(db, endpoint=endpoint, event_type=event_type, payload=payload)
        if settings.WEBHOOKS_ENABLED:
            outcome = _attempt_delivery(db, endpoint=endpoint, delivery=delivery, event_type=event_type, payload=payload)
        else:
            outcome = {"ok": False, "status": None, "error": "webhooks disabled"}
            delivery.status = DeliveryStatus.PENDING.value
            delivery.error = "webhooks disabled"
            db.add(delivery)
            db.commit()
        results.append({"endpoint_id": endpoint.id, **outcome})
    return results


def _record_delivery(
    db: Session, *, endpoint: WebhookEndpoint, event_type: str, payload: dict
) -> WebhookDelivery:
    import json
    import uuid

    delivery = WebhookDelivery(
        endpoint_id=endpoint.id,
        event_id=uuid.uuid4().hex,
        event_type=event_type,
        payload_json=json.dumps(payload, ensure_ascii=False, default=str),
        status=DeliveryStatus.PENDING.value,
    )
    db.add(delivery)
    db.commit()
    db.refresh(delivery)
    return delivery


def _attempt_delivery(
    db: Session,
    *,
    endpoint: WebhookEndpoint,
    delivery: WebhookDelivery,
    event_type: str,
    payload: dict,
) -> dict:
    from backend.integrations import deliver_webhook

    outcome = deliver_webhook(
        url=endpoint.url,
        secret=endpoint.signing_secret,
        event_type=event_type,
        payload=payload,
        event_id=delivery.event_id,
    )
    delivery.attempt_count += 1
    delivery.last_attempt_at = utcnow()
    delivery.response_status = outcome.get("status")
    delivery.error = outcome.get("error")
    delivery.status = (
        DeliveryStatus.DELIVERED.value if outcome.get("ok") else DeliveryStatus.FAILED.value
    )
    endpoint.last_delivery_at = utcnow()
    endpoint.last_status = delivery.status
    db.add(delivery)
    db.add(endpoint)
    db.commit()
    audit_service.record(
        db,
        action=AuditAction.INTEGRATION_DELIVERY_ATTEMPTED,
        entity_type="webhook_endpoint",
        entity_id=endpoint.id,
        company_id=endpoint.company_id,
        metadata={"event": event_type, "status": delivery.status, "code": delivery.response_status},
        commit=False,
    )
    return {"ok": bool(outcome.get("ok")), "status": outcome.get("status"), "error": outcome.get("error")}


# --------------------------------------------------------------------------
# email
# --------------------------------------------------------------------------
def send_email(
    db: Session,
    *,
    to: list[str],
    subject: str,
    body: str,
    html: str | None = None,
    headers: dict[str, str] | None = None,
) -> dict:
    """Send a transactional email through the configured provider.

    Returns a small result dict; never raises. A provider failure is logged and
    reported but does not affect the caller.
    """
    recipients = [addr for addr in (to or []) if addr and "@" in addr]
    if not recipients:
        return {"sent": False, "provider": settings.EMAIL_PROVIDER, "detail": "no recipients"}
    try:
        provider = get_email_provider()
        result = provider.send(
            EmailMessage(to=recipients, subject=subject, body=body, html=html, headers=headers or {})
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Email dispatch failed")
        return {"sent": False, "provider": settings.EMAIL_PROVIDER, "detail": str(exc)[:200]}
    return {"sent": result.sent, "provider": result.provider, "detail": result.detail}


__all__ = [
    "SUPPORTED_EVENTS",
    "create_endpoint",
    "disable_endpoint",
    "emit",
    "list_deliveries",
    "list_endpoints",
    "matching_endpoints",
    "rotate_secret",
    "send_email",
    "serialise_delivery",
    "serialise_endpoint",
    "split_events",
    "update_endpoint",
]
