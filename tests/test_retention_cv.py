"""CV retention policy: six months, then the CV is deleted (site-integration.md).

The policy is a promise made on the public careers form, so these tests prove
both halves of it: an expired CV really is removed (file *and* row), and
nothing outside the policy's scope is ever touched.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.core import storage
from backend.core.config import settings
from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import WebsiteServiceType
from backend.db.models.ai import AuditLog
from backend.db.models.website import WebsiteLead, WebsiteLeadAttachment
from backend.services import retention_service


def _make_lead(
    db,
    *,
    service_type: str = WebsiteServiceType.CAREERS.value,
    reference: str = "SAF-CV-TEST",
    created_at: datetime | None = None,
) -> WebsiteLead:
    lead = WebsiteLead(
        reference=reference,
        source="website",
        market="gulf",
        service_type=service_type,
        locale="ar",
        full_name="مرشح",
        email="candidate@example.com",
        consent_given=True,
    )
    if created_at is not None:
        lead.created_at = created_at
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


def _make_attachment(
    db, lead: WebsiteLead, *, name: str, created_at: datetime | None = None
) -> WebsiteLeadAttachment:
    attachment = WebsiteLeadAttachment(
        lead_id=lead.id,
        original_filename=name,
        storage_key=f"{name}.pdf",
        content_type="application/pdf",
        size_bytes=10,
        is_public=False,
    )
    if created_at is not None:
        attachment.created_at = created_at
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return attachment


@pytest.fixture
def upload_root(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    return tmp_path


def _write_file(root: Path, key: str) -> Path:
    path = root / key
    path.write_bytes(b"%PDF-1.4 test")
    return path


# --------------------------------------------------------------------------
# cutoff maths
# --------------------------------------------------------------------------
def test_retention_cutoff_is_six_months_back():
    cutoff = retention_service.retention_cutoff(as_of=date(2027, 9, 15))

    assert cutoff == datetime(2027, 3, 15, tzinfo=timezone.utc)


def test_retention_cutoff_clamps_to_a_valid_day():
    # 31 March minus six months must be 30 September, never an invalid date.
    cutoff = retention_service.retention_cutoff(as_of=date(2027, 3, 31))

    assert cutoff == datetime(2026, 9, 30, tzinfo=timezone.utc)


def test_retention_cutoff_crosses_the_year_boundary():
    cutoff = retention_service.retention_cutoff(as_of=date(2027, 2, 10))

    assert cutoff == datetime(2026, 8, 10, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# expiry selection
# --------------------------------------------------------------------------
def test_only_expired_careers_cvs_are_selected(db, upload_root):
    old = datetime.now(timezone.utc) - timedelta(days=200)
    fresh = datetime.now(timezone.utc) - timedelta(days=10)

    careers = _make_lead(db, reference="SAF-CV-1")
    expired = _make_attachment(db, careers, name="expired", created_at=old)
    _make_attachment(db, careers, name="fresh", created_at=fresh)

    # A non-careers lead's attachment must never be a candidate.
    contact = _make_lead(
        db,
        service_type=WebsiteServiceType.GENERAL_CONTACT.value,
        reference="SAF-GC-1",
    )
    _make_attachment(db, contact, name="proof", created_at=old)

    selected = retention_service.expired_cv_attachments(db)

    assert [a.id for a in selected] == [expired.id]


def test_expired_cv_is_deleted_with_its_file_and_logged(db, upload_root):
    old = datetime.now(timezone.utc) - timedelta(days=200)
    lead = _make_lead(db, reference="SAF-CV-2")
    attachment = _make_attachment(db, lead, name="cv", created_at=old)
    file_path = _write_file(upload_root, attachment.storage_key)
    assert file_path.exists()

    result = retention_service.purge_expired_cvs(db)

    assert result["removed_count"] == 1
    assert result["removed_attachment_ids"] == [attachment.id]
    # The row is gone...
    assert db.get(WebsiteLeadAttachment, attachment.id) is None
    # ...the file is gone...
    assert not file_path.exists()
    # ...but the deletion is recorded.
    log = (
        db.query(AuditLog)
        .filter(AuditLog.action == AuditAction.WEBSITE_LEAD_CV_PURGED)
        .one()
    )
    assert str(attachment.id) in (log.entity_id or "")
    assert "retention_expired" in (log.meta_json or "")
    # ...and one summary row records the run.
    assert (
        db.query(AuditLog)
        .filter(AuditLog.action == AuditAction.RETENTION_CV_PURGE_RUN)
        .count()
        == 1
    )


def test_the_lead_record_survives_the_purge(db, upload_root):
    """Only the CV file is in scope; the lead itself must remain."""
    old = datetime.now(timezone.utc) - timedelta(days=200)
    lead = _make_lead(db, reference="SAF-CV-3")
    _make_attachment(db, lead, name="cv", created_at=old)

    retention_service.purge_expired_cvs(db)

    assert db.get(WebsiteLead, lead.id) is not None


def test_fresh_cvs_are_left_alone(db, upload_root):
    fresh = datetime.now(timezone.utc) - timedelta(days=30)
    lead = _make_lead(db, reference="SAF-CV-4")
    attachment = _make_attachment(db, lead, name="cv", created_at=fresh)
    file_path = _write_file(upload_root, attachment.storage_key)

    result = retention_service.purge_expired_cvs(db)

    assert result["removed_count"] == 0
    assert db.get(WebsiteLeadAttachment, attachment.id) is not None
    assert file_path.exists()


def test_purge_is_idempotent(db, upload_root):
    old = datetime.now(timezone.utc) - timedelta(days=200)
    lead = _make_lead(db, reference="SAF-CV-5")
    _make_attachment(db, lead, name="cv", created_at=old)

    first = retention_service.purge_expired_cvs(db)
    second = retention_service.purge_expired_cvs(db)

    assert first["removed_count"] == 1
    assert second["removed_count"] == 0


def test_dry_run_changes_nothing(db, upload_root):
    old = datetime.now(timezone.utc) - timedelta(days=200)
    lead = _make_lead(db, reference="SAF-CV-6")
    attachment = _make_attachment(db, lead, name="cv", created_at=old)
    file_path = _write_file(upload_root, attachment.storage_key)

    result = retention_service.purge_expired_cvs(db, dry_run=True)

    assert result["dry_run"] is True
    assert result["removed_count"] == 1
    # Nothing was actually removed.
    assert db.get(WebsiteLeadAttachment, attachment.id) is not None
    assert file_path.exists()
    assert (
        db.query(AuditLog)
        .filter(AuditLog.action == AuditAction.WEBSITE_LEAD_CV_PURGED)
        .count()
        == 0
    )


def test_a_missing_file_does_not_abort_the_purge(db, upload_root):
    """A row whose file already vanished is still cleaned up (best-effort)."""
    old = datetime.now(timezone.utc) - timedelta(days=200)
    lead = _make_lead(db, reference="SAF-CV-7")
    attachment = _make_attachment(db, lead, name="gone", created_at=old)
    # No file is written.

    result = retention_service.purge_expired_cvs(db)

    assert result["removed_count"] == 1
    assert db.get(WebsiteLeadAttachment, attachment.id) is None
