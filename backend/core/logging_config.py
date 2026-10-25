"""Application logging setup.

Structured-enough logging that never emits secrets. A redaction helper is
provided for the audit trail so that sensitive values are never persisted.
"""

from __future__ import annotations

import logging
import sys

_REDACT_KEYS = {
    "password",
    "new_password",
    "current_password",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "secret",
    "api_key",
    "hashed_password",
}


def redact(data: dict | None) -> dict:
    """Return a copy of ``data`` with sensitive keys masked."""
    if not data:
        return {}
    out: dict = {}
    for key, value in data.items():
        if key.lower() in _REDACT_KEYS:
            out[key] = "***"
        elif isinstance(value, dict):
            out[key] = redact(value)
        else:
            out[key] = value
    return out


def configure_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
