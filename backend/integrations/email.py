"""Email provider abstraction.

The platform sends at most a handful of transactional messages (a notification
copy, an expiry reminder). Rather than pull in a mail library and a template
engine, this module defines the smallest interface that a real provider can
satisfy, plus three implementations:

* ``NullEmailProvider`` -- does nothing, reports ``sent=False``. The default, so
  no network call happens unless a deployment explicitly opts in.
* ``ConsoleEmailProvider`` -- logs the message. Useful in staging to prove the
  pipeline works without sending anything.
* ``SmtpEmailProvider`` -- a real send over ``smtplib`` using the ``SMTP_*``
  settings.

A provider is chosen by ``EMAIL_PROVIDER``; swapping in a hosted API (SES,
SendGrid, ...) means adding one class here and one branch in the factory --
no caller changes.
"""

from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage as _StdEmailMessage
from typing import Protocol, runtime_checkable

from backend.core.config import settings

logger = logging.getLogger("safir.integrations.email")


@dataclass(slots=True)
class EmailMessage:
    to: list[str]
    subject: str
    body: str
    # Optional HTML alternative. Kept separate so a plain-text fallback always
    # exists (some clients and every log reader prefer it).
    html: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class EmailResult:
    sent: bool
    provider: str
    detail: str | None = None


@runtime_checkable
class EmailProvider(Protocol):
    name: str

    def send(self, message: EmailMessage) -> EmailResult: ...


class NullEmailProvider:
    name = "none"

    def send(self, message: EmailMessage) -> EmailResult:  # noqa: ARG002
        return EmailResult(sent=False, provider=self.name, detail="email disabled")


class ConsoleEmailProvider:
    """Writes the message to the application log instead of sending it."""

    name = "console"

    def send(self, message: EmailMessage) -> EmailResult:
        logger.info(
            "email(console) to=%s subject=%r bytes=%d",
            ",".join(message.to),
            message.subject,
            len(message.body or ""),
        )
        return EmailResult(sent=True, provider=self.name, detail="logged")


class SmtpEmailProvider:
    name = "smtp"

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        use_tls: bool,
        sender: str,
        timeout: float = 15.0,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._sender = sender
        self._timeout = timeout

    def send(self, message: EmailMessage) -> EmailResult:
        if not self._host:
            return EmailResult(sent=False, provider=self.name, detail="SMTP_HOST unset")
        std = _StdEmailMessage()
        std["From"] = self._sender
        std["To"] = ", ".join(message.to)
        std["Subject"] = message.subject
        for key, value in (message.headers or {}).items():
            std[key] = value
        std.set_content(message.body or "")
        if message.html:
            std.add_alternative(message.html, subtype="html")

        try:
            with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as client:
                if self._use_tls:
                    client.starttls()
                if self._username:
                    client.login(self._username, self._password)
                client.send_message(std)
        except Exception as exc:  # noqa: BLE001 - never propagate to the caller
            logger.warning("SMTP delivery failed: %s", exc)
            return EmailResult(sent=False, provider=self.name, detail=str(exc)[:200])
        return EmailResult(sent=True, provider=self.name, detail="sent")


def get_email_provider() -> EmailProvider:
    choice = (settings.EMAIL_PROVIDER or "none").strip().lower()
    if choice == "console":
        return ConsoleEmailProvider()
    if choice == "smtp":
        return SmtpEmailProvider(
            host=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USERNAME,
            password=settings.SMTP_PASSWORD,
            use_tls=settings.SMTP_USE_TLS,
            sender=settings.EMAIL_FROM,
        )
    return NullEmailProvider()


__all__ = [
    "ConsoleEmailProvider",
    "EmailMessage",
    "EmailProvider",
    "EmailResult",
    "NullEmailProvider",
    "SmtpEmailProvider",
    "get_email_provider",
]
