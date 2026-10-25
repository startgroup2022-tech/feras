"""External integration endpoints under ``/api/v1/integrations``.

Reading a subscription requires ``integration.read``; creating, editing,
disabling and rotating a secret require ``integration.manage``. The signing
secret is returned exactly once -- on creation or rotation -- and never again,
so a read of the list can be shared without leaking the credential.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, status

from backend.api.deps import CurrentUser, DbSession, require
from backend.core.config import settings
from backend.rbac.permissions import Perm
from backend.schemas import (
    IntegrationEventOut,
    WebhookDeliveryOut,
    WebhookEndpointCreateRequest,
    WebhookEndpointOut,
    WebhookEndpointUpdateRequest,
    WebhookSecretOut,
)
from backend.services import audit_service, integration_service

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("/events", response_model=IntegrationEventOut)
def list_events(user=Depends(require(Perm.INTEGRATION_READ))) -> IntegrationEventOut:
    return IntegrationEventOut(
        events=list(integration_service.SUPPORTED_EVENTS),
        email_provider=settings.EMAIL_PROVIDER,
        webhooks_enabled=settings.WEBHOOKS_ENABLED,
    )


@router.get("", response_model=list[WebhookEndpointOut])
def list_endpoints(
    db: DbSession, user=Depends(require(Perm.INTEGRATION_READ))
) -> list[WebhookEndpointOut]:
    return [
        WebhookEndpointOut(**row) for row in integration_service.list_endpoints(db, user=user)
    ]


@router.post("", response_model=WebhookSecretOut, status_code=status.HTTP_201_CREATED)
def create_endpoint(
    payload: WebhookEndpointCreateRequest,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.INTEGRATION_MANAGE)),
) -> WebhookSecretOut:
    ctx = audit_service.request_context(request)
    endpoint, secret = integration_service.create_endpoint(
        db,
        actor=actor,
        name=payload.name,
        url=payload.url,
        subscribed_events=payload.subscribed_events,
        scope=payload.scope,
        company_id=payload.company_id,
        description=payload.description,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return WebhookSecretOut(
        endpoint=WebhookEndpointOut(**integration_service.serialise_endpoint(endpoint)),
        signing_secret=secret,
    )


@router.patch("/{endpoint_id}", response_model=WebhookEndpointOut)
def update_endpoint(
    endpoint_id: int,
    payload: WebhookEndpointUpdateRequest,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.INTEGRATION_MANAGE)),
) -> WebhookEndpointOut:
    ctx = audit_service.request_context(request)
    endpoint = integration_service.update_endpoint(
        db,
        actor=actor,
        endpoint_id=endpoint_id,
        payload=payload.model_dump(exclude_unset=True),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return WebhookEndpointOut(**integration_service.serialise_endpoint(endpoint))


@router.post("/{endpoint_id}/disable", response_model=WebhookEndpointOut)
def disable_endpoint(
    endpoint_id: int,
    request: Request,
    db: DbSession,
    actor=Depends(require(Perm.INTEGRATION_MANAGE)),
) -> WebhookEndpointOut:
    ctx = audit_service.request_context(request)
    endpoint = integration_service.disable_endpoint(
        db,
        actor=actor,
        endpoint_id=endpoint_id,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return WebhookEndpointOut(**integration_service.serialise_endpoint(endpoint))


@router.post("/{endpoint_id}/rotate-secret", response_model=WebhookSecretOut)
def rotate_secret(
    endpoint_id: int,
    db: DbSession,
    actor=Depends(require(Perm.INTEGRATION_MANAGE)),
) -> WebhookSecretOut:
    endpoint, secret = integration_service.rotate_secret(
        db, actor=actor, endpoint_id=endpoint_id
    )
    return WebhookSecretOut(
        endpoint=WebhookEndpointOut(**integration_service.serialise_endpoint(endpoint)),
        signing_secret=secret,
    )


@router.get("/deliveries", response_model=list[WebhookDeliveryOut])
def list_deliveries(
    db: DbSession,
    user=Depends(require(Perm.INTEGRATION_READ)),
    endpoint_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[WebhookDeliveryOut]:
    return [
        WebhookDeliveryOut(**row)
        for row in integration_service.list_deliveries(
            db, user=user, endpoint_id=endpoint_id, limit=limit
        )
    ]
