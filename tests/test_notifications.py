"""Phase 6: notification centre.

Focus is on the properties that matter for an executive inbox: an event
produces exactly one row per recipient, the inbox is strictly personal, and the
expiry scan is idempotent. No notification is asserted for a business action
that did not actually happen.
"""

from __future__ import annotations

from datetime import date, timedelta

from backend.db.base import utcnow
from backend.db.models.enums import NotificationType, SupportCategory
from backend.db.models.notifications import Notification
from backend.services import notification_service

INBOX = "/api/v1/notifications"


def _rows(db, user):
    return (
        db.query(Notification)
        .filter(Notification.recipient_id == user.id)
        .order_by(Notification.id)
        .all()
    )


# --------------------------------------------------------------------------
# direct service behaviour
# --------------------------------------------------------------------------
def test_notify_creates_one_row_per_active_recipient(db, world):
    created = notification_service.notify(
        db,
        recipient_ids=[world["alpha_mgr"].id, world["owner"].id],
        type=NotificationType.SYSTEM.value,
        title_ar="عنوان",
        title_en="Title",
        message_ar="رسالة",
        message_en="Message",
    )
    assert len(created) == 2
    assert {n.recipient_id for n in created} == {world["alpha_mgr"].id, world["owner"].id}
    assert all(n.is_read is False for n in created)


def test_dedupe_key_prevents_a_second_row(db, world):
    kwargs = dict(
        recipient_ids=[world["owner"].id],
        type=NotificationType.SYSTEM.value,
        title_ar="عنوان",
        title_en="Title",
        message_ar="رسالة",
        message_en="Message",
        dedupe_key="same-key",
    )
    first = notification_service.notify(db, **kwargs)
    second = notification_service.notify(db, **kwargs)

    assert len(first) == 1
    assert second == []
    assert len(_rows(db, world["owner"])) == 1


def test_inactive_recipients_are_skipped(db, world):
    manager = world["alpha_mgr"]
    manager.is_active = False
    db.add(manager)
    db.commit()

    created = notification_service.notify(
        db,
        recipient_ids=[manager.id],
        type=NotificationType.SYSTEM.value,
        title_ar="ع",
        title_en="T",
        message_ar="ر",
        message_en="M",
    )
    assert created == []


def test_empty_recipients_is_a_noop(db):
    assert (
        notification_service.notify(
            db,
            recipient_ids=[],
            type=NotificationType.SYSTEM.value,
            title_ar="ع",
            title_en="T",
            message_ar="ر",
            message_en="M",
        )
        == []
    )


# --------------------------------------------------------------------------
# inbox API
# --------------------------------------------------------------------------
def test_inbox_is_personal(client, db, world, auth):
    notification_service.notify(
        db,
        recipient_ids=[world["alpha_mgr"].id],
        type=NotificationType.SYSTEM.value,
        title_ar="خاصة",
        title_en="Private",
        message_ar="للألفا",
        message_en="for alpha",
    )

    alpha = client.get(INBOX, headers=auth(world["alpha_mgr"])).json()
    beta = client.get(INBOX, headers=auth(world["beta_mgr"])).json()

    assert alpha["total"] == 1
    assert alpha["items"][0]["title_ar"] == "خاصة"
    assert beta["total"] == 0


def test_mark_read_only_affects_own_row(client, db, world, auth):
    created = notification_service.notify(
        db,
        recipient_ids=[world["alpha_mgr"].id],
        type=NotificationType.SYSTEM.value,
        title_ar="ع",
        title_en="T",
        message_ar="ر",
        message_en="M",
    )[0]

    # Another user cannot mark it read -- it is indistinguishable from missing.
    forbidden = client.post(
        f"{INBOX}/{created.id}/read", headers=auth(world["beta_mgr"])
    )
    assert forbidden.status_code == 404

    ok = client.post(f"{INBOX}/{created.id}/read", headers=auth(world["alpha_mgr"]))
    assert ok.status_code == 200
    assert ok.json()["is_read"] is True

    summary = client.get(f"{INBOX}/summary", headers=auth(world["alpha_mgr"])).json()
    assert summary["unread"] == 0


def test_summary_counts_by_type(client, db, world, auth):
    for _ in range(2):
        notification_service.notify(
            db,
            recipient_ids=[world["owner"].id],
            type=NotificationType.SUPPORT_ASSIGNED.value,
            title_ar="ع",
            title_en="T",
            message_ar="ر",
            message_en="M",
        )
    notification_service.notify(
        db,
        recipient_ids=[world["owner"].id],
        type=NotificationType.SYSTEM.value,
        title_ar="ع",
        title_en="T",
        message_ar="ر",
        message_en="M",
    )

    summary = client.get(f"{INBOX}/summary", headers=auth(world["owner"])).json()
    assert summary["unread"] == 3
    assert summary["by_type"][NotificationType.SUPPORT_ASSIGNED.value] == 2


def test_read_all_clears_the_inbox(client, db, world, auth):
    notification_service.notify(
        db,
        recipient_ids=[world["owner"].id],
        type=NotificationType.SYSTEM.value,
        title_ar="ع",
        title_en="T",
        message_ar="ر",
        message_en="M",
    )

    client.post(f"{INBOX}/read-all", headers=auth(world["owner"]))

    assert client.get(INBOX, headers=auth(world["owner"])).json()["total"] == 1
    unread = client.get(
        f"{INBOX}?unread_only=true", headers=auth(world["owner"])
    ).json()
    assert unread["total"] == 0


def test_unread_only_filters(client, db, world, auth):
    rows = notification_service.notify(
        db,
        recipient_ids=[world["owner"].id],
        type=NotificationType.SYSTEM.value,
        title_ar="ع",
        title_en="T",
        message_ar="ر",
        message_en="M",
    )
    client.post(f"{INBOX}/{rows[0].id}/read", headers=auth(world["owner"]))

    body = client.get(f"{INBOX}?unread_only=true", headers=auth(world["owner"])).json()
    assert body["total"] == 0


# --------------------------------------------------------------------------
# event wiring
# --------------------------------------------------------------------------
def test_support_assignment_notifies_the_assignee(client, db, world, auth):
    request = world["alpha_req"]
    client.patch(
        f"/api/v1/support-requests/{request.id}/assign",
        headers=auth(world["owner"]),
        json={"assigned_to_id": world["accountant"].id},
    )

    rows = _rows(db, world["accountant"])
    assert any(r.type == NotificationType.SUPPORT_ASSIGNED.value for r in rows)


def test_report_submission_notifies_reviewers(client, db, world, auth):
    # The accountant holds financial-review permissions.
    report = client.post(
        "/api/v1/monthly-reports",
        headers=auth(world["alpha_mgr"]),
        json={
            "company_id": world["alpha"].id,
            "period_year": 2027,
            "period_month": 11,
            "revenue": "100",
            "expenses": "50",
        },
    ).json()
    client.post(
        f"/api/v1/monthly-reports/{report['id']}/submit",
        headers=auth(world["alpha_mgr"]),
    )

    rows = _rows(db, world["accountant"])
    assert any(r.type == NotificationType.REPORT_SUBMITTED.value for r in rows)


# --------------------------------------------------------------------------
# expiry scan
# --------------------------------------------------------------------------
def test_expiry_scan_is_idempotent(db, world):
    from backend.db.models.documents import Document
    from backend.db.models.enums import DocumentStatus

    document = Document(
        company_id=world["alpha"].id,
        title_ar="سجل تجاري",
        title_en="Commercial register",
        original_filename="cr.pdf",
        storage_key="cr.pdf",
        content_type="application/pdf",
        size_bytes=10,
        status=DocumentStatus.ACTIVE.value,
        expiry_date=date.today() + timedelta(days=5),
        uploaded_by_id=world["alpha_mgr"].id,
    )
    db.add(document)
    db.commit()

    first = notification_service.scan_document_expiry(db)
    second = notification_service.scan_document_expiry(db)

    assert first["notifications_created"] >= 1
    assert second["notifications_created"] == 0


def test_expiry_scan_requires_manage_permission(client, auth, world):
    # A company manager has no notification.manage permission.
    denied = client.post(
        "/api/v1/notifications/scan-documents", headers=auth(world["alpha_mgr"])
    )
    assert denied.status_code == 403


def test_expiry_scan_endpoint_runs_for_owner(client, world, auth):
    response = client.post(
        "/api/v1/notifications/scan-documents", headers=auth(world["owner"])
    )
    assert response.status_code == 200
    assert "documents_scanned" in response.json()
