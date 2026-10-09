"""External integration models: outbound webhooks and their delivery log.

The foundation is deliberately small: a webhook subscription (name, endpoint,
subscribed events, scope, signing secret) plus an append-only delivery record.
Nothing about a provider is hardcoded into business logic -- services emit
*domain events* (see :mod:`backend.services.integration_service`) and this layer
decides whether an endpoint is interested.

Security properties enforced in the service layer:

* the signing secret is stored only as a hash-able value and is **never**
  returned by the API after creation/rotation;
* a delivery attempt is recorded even when it fails, and a failure never
  propagates back into the business transaction that triggered it;
* endpoints are validated against SSRF (no loopback / private / link-local
  destinations) before a subscription is saved.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin
from backend.db.models.enums import DeliveryStatus, WebhookStatus

if TYPE_CHECKING:
    from backend.db.models.identity import Company, User


class WebhookEndpoint(Base, TimestampMixin):
    """A configured outbound webhook subscription."""

    __tablename__ = "webhook_endpoints"
    __table_args__ = (
        Index("ix_webhook_endpoints_status", "status"),
        Index("ix_webhook_endpoints_scope", "scope", "company_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=WebhookStatus.ACTIVE.value
    )
    # Comma-separated list of WebhookEventType values the endpoint subscribes to.
    subscribed_events: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # ``holding`` (all companies) or ``company`` (only company_id).
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="holding")
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=True
    )
    # HMAC signing secret. Never returned by the API after creation.
    signing_secret: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    last_delivery_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_status: Mapped[str | None] = mapped_column(String(20), nullable=True)

    company: Mapped["Company | None"] = relationship()
    deliveries: Mapped[list["WebhookDelivery"]] = relationship(
        back_populates="endpoint", cascade="all, delete-orphan"
    )


class WebhookDelivery(Base, TimestampMixin):
    """One delivery attempt of one event to one endpoint.

    Append-only in spirit: a retry creates a new attempt counter on the same row
    (``attempt_count`` is bumped) rather than a second row, so the table does not
    grow without bound when an endpoint is persistently down.
    """

    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        Index("ix_webhook_deliveries_endpoint", "endpoint_id", "created_at"),
        Index("ix_webhook_deliveries_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    endpoint_id: Mapped[int] = mapped_column(
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DeliveryStatus.PENDING.value
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    endpoint: Mapped[WebhookEndpoint] = relationship(back_populates="deliveries")


__all__ = ["WebhookDelivery", "WebhookEndpoint"]
