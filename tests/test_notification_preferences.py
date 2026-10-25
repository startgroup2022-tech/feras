"""D11: notification channel preferences and the delivery log.

Exercised against the real service + API + persistence path (no mocks):

* an unconfigured user gets the D11 default (in-app on, email off, not muted);
* a preference is strictly personal — reading and writing are always the
  caller's own row;
* muting an event type stops the notification being created at all;
* the in-app channel is the base and cannot be left empty;
* an email copy is never reported as delivered while no provider is configured —
  it is logged as ``skipped``;
* a sensitive notification's delivery log holds a redacted excerpt, never the
  confidential body.
"""

from __future__ import annotations

import pytest

from backend.core.config import settings
from backend.db.models.enums import NotificationType
from backend.services import notification_preference_service, notification_service

PREFS = "/api/v1/notifications/preferences"
DELIVERIES = "/api/v1/notifications/deliveries"


def _notify(db, user, *, type=None, dedupe=None):
    return notification_service.notify(
        db,
        recipient_ids=[user.id],
        type=type or NotificationType.SUPPORT_STATUS_CHANGED.value,
        title_ar="عنوان تجريبي",
        title_en="Title",
        message_ar="نصّ",
        message_en="Body",
        dedupe_key=dedupe,
        emit_webhook=False,
    )


# --------------------------------------------------------------------------
# defaults + personal scope
# --------------------------------------------------------------------------
def test_unconfigured_user_gets_the_default(db, world):
    pref = notification_preference_service.effective_preference(
        db, user_id=world["alpha_mgr"].id, event_type="any.event"
    )
    assert pref == {"in_app": True, "email": False, "muted": False}


def test_preferences_are_strictly_personal(client, world, auth):
    manager = world["alpha_mgr"]
    owner = world["owner"]

    response = client.put(
        f"{PREFS}/{NotificationType.REPORT_SUBMITTED.value}",
        json={"email": True},
        headers=auth(manager),
    )
    assert response.status_code == 200, response.text

    owner_rows = client.get(PREFS, headers=auth(owner)).json()["items"]
    assert owner_rows == []
    manager_rows = client.get(PREFS, headers=auth(manager)).json()["items"]
    assert manager_rows[0]["email"] is True


# --------------------------------------------------------------------------
# muting removes the notification entirely
# --------------------------------------------------------------------------
def test_muting_an_event_type_stops_the_notification(db, world):
    manager = world["alpha_mgr"]
    notification_preference_service.set_preference(
        db,
        user=manager,
        event_type=NotificationType.SUPPORT_ASSIGNED.value,
        muted=True,
    )
    created = _notify(db, manager, type=NotificationType.SUPPORT_ASSIGNED.value)
    assert created == []

    # A different type is unaffected by a single-type mute.
    created_other = _notify(db, manager, type=NotificationType.SYSTEM.value)
    assert len(created_other) == 1


def test_unmuting_restores_the_notification(db, world):
    manager = world["alpha_mgr"]
    notification_preference_service.set_preference(
        db, user=manager, event_type=NotificationType.SYSTEM.value, muted=True
    )
    assert _notify(db, manager, type=NotificationType.SYSTEM.value) == []
    notification_preference_service.set_preference(
        db, user=manager, event_type=NotificationType.SYSTEM.value, muted=False
    )
    assert len(_notify(db, manager, type=NotificationType.SYSTEM.value)) == 1


# --------------------------------------------------------------------------
# in-app base channel cannot be emptied
# --------------------------------------------------------------------------
def test_preference_cannot_disable_every_channel(client, world, auth):
    manager = world["alpha_mgr"]
    response = client.put(
        f"{PREFS}/{NotificationType.SYSTEM.value}",
        json={"in_app": False, "email": False},
        headers=auth(manager),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["in_app"] is True  # in-app is the base channel (D11)


def test_muting_clears_the_channels(client, world, auth):
    manager = world["alpha_mgr"]
    body = client.put(
        f"{PREFS}/{NotificationType.SYSTEM.value}",
        json={"email": True, "muted": True},
        headers=auth(manager),
    ).json()
    assert body["muted"] is True
    assert body["email"] is False
    assert body["in_app"] is False


# --------------------------------------------------------------------------
# delivery log
# --------------------------------------------------------------------------
def test_in_app_delivery_is_logged(db, world):
    manager = world["alpha_mgr"]
    _notify(db, manager)
    log = notification_preference_service.list_delivery_log(db, user=manager)
    assert any(row["channel"] == "in_app" and row["status"] == "delivered"
               for row in log["items"])


def test_email_is_skipped_without_a_provider(db, world, monkeypatch):
    manager = world["alpha_mgr"]
    # Email preference on, but the deployment has no provider configured.
    notification_preference_service.set_preference(
        db, user=manager, event_type=NotificationType.SYSTEM.value, email=True
    )
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "none", raising=False)
    row = _notify(db, manager, type=NotificationType.SYSTEM.value)[0]

    log_row = notification_preference_service.dispatch_email(
        db, notification=row, recipient_email="manager@corp.sa"
    )
    assert log_row.status == "skipped"
    assert log_row.error == "provider_not_configured"


def test_email_preference_off_records_skipped(db, world):
    manager = world["alpha_mgr"]
    row = _notify(db, manager, type=NotificationType.SYSTEM.value)[0]
    log_row = notification_preference_service.dispatch_email(
        db, notification=row, recipient_email="manager@corp.sa"
    )
    assert log_row.status == "skipped"
    assert log_row.error == "preference_disabled"


def test_sensitive_excerpt_is_redacted(db, world):
    manager = world["alpha_mgr"]
    # A document-expiry notification is treated as sensitive (not in the safe
    # whitelist), so its excerpt must not carry the title.
    row = _notify(db, manager, type=NotificationType.DOCUMENT_EXPIRING.value)[0]
    log = notification_preference_service.list_delivery_log(db, user=manager)
    excerpt = next(x["payload_excerpt"] for x in log["items"]
                   if x["notification_id"] == row.id)
    assert excerpt == notification_preference_service.SENSITIVE_EXCERPT
    assert row.title_ar not in excerpt


def test_delivery_log_is_personal_api(client, db, world, auth):
    manager = world["alpha_mgr"]
    _notify(db, manager)
    owner_log = client.get(DELIVERIES, headers=auth(world["owner"])).json()
    assert owner_log["total"] == 0
    manager_log = client.get(DELIVERIES, headers=auth(manager)).json()
    assert manager_log["total"] >= 1


def test_unknown_event_type_is_rejected(client, world, auth):
    response = client.put(
        f"{PREFS}/not.a.real.type", json={"email": True}, headers=auth(world["alpha_mgr"])
    )
    assert response.status_code == 422, response.text
