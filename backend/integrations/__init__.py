"""Outbound integration adapters.

Two concerns live here, both behind a small interface so the platform never
hardcodes a vendor:

* **Email** -- :class:`EmailProvider` implementations. ``none`` (default) does
  nothing, ``console`` logs, ``smtp`` sends. Selection is configuration only.
* **Webhooks** -- :func:`deliver_webhook`, which POSTs a signed JSON payload to
  a subscriber, with SSRF protection applied *before* any connection is opened.

Nothing in this package is imported on the default request path: the service
layer imports it lazily and treats every failure as non-fatal, so a
misconfigured integration can never break a business action.
"""

from __future__ import annotations

from backend.integrations.email import EmailMessage, get_email_provider
from backend.integrations.webhooks import (
    UnsafeUrlError,
    build_signature,
    deliver_webhook,
    validate_outbound_url,
)

__all__ = [
    "EmailMessage",
    "UnsafeUrlError",
    "build_signature",
    "deliver_webhook",
    "get_email_provider",
    "validate_outbound_url",
]
