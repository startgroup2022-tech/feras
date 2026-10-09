"""Outbound webhook delivery with SSRF protection.

The rule this module enforces: **a subscriber URL is validated before a socket
is opened**. An administrator (or an attacker who has stolen an admin session)
must not be able to point a webhook at ``http://127.0.0.1:8000/admin`` and turn
the platform into a proxy for internal services. The checks reject:

* non-HTTP(S) schemes;
* hostnames that resolve to loopback, private, link-local or reserved ranges;
* cloud metadata addresses (covered by the link-local range, kept explicit);
* credentials embedded in the URL.

Payloads are signed with an HMAC-SHA256 over the raw body using the endpoint's
secret, delivered in ``X-Safir-Signature`` so the receiver can verify
authenticity without a shared session.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import socket
import urllib.error
import urllib.request
import uuid
from urllib.parse import urlparse

from backend.core.config import settings
from backend.core.errors import ValidationError

logger = logging.getLogger("safir.integrations.webhooks")


class UnsafeUrlError(ValidationError):
    """Raised when a webhook URL could reach a non-public destination.

    Subclasses the application's validation error so the API returns a clean
    400 with a stable code instead of an unhandled 500.
    """


_BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "169.254.169.254",
}


def validate_outbound_url(url: str) -> str:
    """Validate and normalise a webhook URL, or raise :class:`UnsafeUrlError`.

    Returns the URL unchanged on success so callers can write
    ``url = validate_outbound_url(url)``.
    """
    if not url or not url.strip():
        raise UnsafeUrlError("A webhook URL is required.")
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrlError("Only http and https webhook URLs are allowed.")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("Credentials must not be embedded in the webhook URL.")
    host = (parsed.hostname or "").lower()
    if not host:
        raise UnsafeUrlError("The webhook URL has no host.")
    if host in _BLOCKED_HOSTNAMES:
        raise UnsafeUrlError("The webhook host is not a permitted destination.")

    # Resolve every address the name maps to; a name with one public and one
    # private address is still unsafe.
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise UnsafeUrlError("The webhook host could not be resolved.") from exc

    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            raise UnsafeUrlError("The webhook host resolved to an invalid address.")
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise UnsafeUrlError("The webhook host is not a permitted destination.")
    return url.strip()


def build_signature(secret: str, body: bytes, *, timestamp: str) -> str:
    """HMAC-SHA256 signature over ``timestamp.body`` (Stripe-style)."""
    signed = timestamp.encode("utf-8") + b"." + body
    return hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()


def deliver_webhook(
    *,
    url: str,
    secret: str,
    event_type: str,
    payload: dict,
    event_id: str | None = None,
    timeout: float | None = None,
) -> dict:
    """POST a signed event to a subscriber. Never raises.

    Returns a small result dict the caller stores on the delivery row. Network
    failures are reported, not propagated: the business action that produced the
    event has already succeeded and must not be undone by a flaky subscriber.
    """
    event_id = event_id or uuid.uuid4().hex
    body = json.dumps(
        {
            "id": event_id,
            "type": event_type,
            "data": payload,
        },
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")

    from datetime import datetime, timezone

    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    signature = build_signature(secret, body, timestamp=timestamp)

    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Safir-Holding-Webhook/1.0",
            "X-Safir-Event": event_type,
            "X-Safir-Event-Id": event_id,
            "X-Safir-Timestamp": timestamp,
            "X-Safir-Signature": f"sha256={signature}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request, timeout=timeout or settings.WEBHOOK_TIMEOUT_SECONDS
        ) as response:
            status = getattr(response, "status", 200)
            return {"ok": 200 <= status < 300, "status": status, "event_id": event_id, "error": None}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": exc.code, "event_id": event_id, "error": f"HTTP {exc.code}"}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("Webhook delivery failed for %s: %s", url, exc)
        return {"ok": False, "status": None, "event_id": event_id, "error": str(exc)[:200]}


__all__ = [
    "UnsafeUrlError",
    "build_signature",
    "deliver_webhook",
    "validate_outbound_url",
]
