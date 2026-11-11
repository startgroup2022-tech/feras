"""Public CV retention policy (site-integration.md).

The careers form on the public website states that a submitted CV is kept by
the Holding for **six months**, after which it is deleted. This module is the
retention job that makes that promise true.

Scope discipline is the whole point:

* Only attachments belonging to a lead whose ``service_type`` is ``careers``
  are ever considered -- a business-listing photo or a proof document is never
  touched, no matter how old.
* Only attachments older than the retention window are removed. The window is
  measured from the lead's creation time, not from "now".
* The lead record itself is **not** deleted: the policy covers the CV file, and
  removing more than the policy allows is exactly the kind of over-reach the
  brief warns against.
* Each removed CV writes an ``AuditLog`` row (the file is gone, but the fact
  that it existed and was deleted is retained), and one summary row records the
  run.

The job is safe to run repeatedly: a run with nothing expired changes nothing,
and a dry run reports what *would* be removed without removing it.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core import storage
from backend.core.config import settings
from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import WebsiteServiceType
from backend.db.models.website import WebsiteLead, WebsiteLeadAttachment
from backend.services import audit_service

# Kept as a module constant so the query reads the same intent the policy does.
CAREERS_SERVICE_TYPE = WebsiteServiceType.CAREERS.value


def _subtract_months(value: date, months: int) -> date:
    """``value`` shifted back by ``months`` calendar months.

    Implemented without a date library so the service has no extra dependency.
    The day is clamped to the last valid day of the target month (so the 31st of
    March minus one month is the 28th/29th of February, never an invalid date).
    """
    total = value.year * 12 + (value.month - 1) - months
    year, month_index = divmod(total, 12)
    month = month_index + 1
    # Clamp the day to the target month's length.
    last_day = monthrange(year, month)[1]
    return date(year, month, min(value.day, last_day))


def retention_cutoff(*, as_of: date | None = None) -> datetime:
    """The instant on or before which a CV is considered expired.

    A CV created strictly before this timestamp is past its retention window.
    Returned as an aware UTC datetime so it compares directly against the
    timezone-aware ``created_at`` column.
    """
    as_of = as_of or date.today()
    cutoff_date = _subtract_months(as_of, settings.CV_RETENTION_MONTHS)
    return datetime.combine(cutoff_date, time.min, tzinfo=timezone.utc)


def expired_cv_attachments(
    db: Session, *, as_of: date | None = None
) -> list[WebsiteLeadAttachment]:
    """CV attachments on careers leads that are past the retention window.

    The join to ``WebsiteLead`` is what confines the result to careers
    submissions; ``created_at < cutoff`` is what confines it to the expired
    ones. Nothing else is eligible.
    """
    cutoff = retention_cutoff(as_of=as_of)
    stmt = (
        select(WebsiteLeadAttachment)
        .join(WebsiteLead, WebsiteLead.id == WebsiteLeadAttachment.lead_id)
        .where(
            WebsiteLead.service_type == CAREERS_SERVICE_TYPE,
            WebsiteLeadAttachment.created_at < cutoff,
        )
        .order_by(WebsiteLeadAttachment.id)
    )
    return list(db.execute(stmt).scalars())


def purge_expired_cvs(
    db: Session,
    *,
    as_of: date | None = None,
    dry_run: bool = False,
    actor_user_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    """Delete expired CVs and their storage files; log every deletion.

    Returns a summary: the cutoff, how many CVs were (or would be) removed, and
    their ids. When ``dry_run`` is true nothing is written -- not the files, not
    the rows, not the audit entries -- so the job can be previewed safely.
    """
    attachments = expired_cv_attachments(db, as_of=as_of)
    cutoff = retention_cutoff(as_of=as_of)

    removed_ids: list[int] = []
    for attachment in attachments:
        removed_ids.append(attachment.id)
        if dry_run:
            continue
        # Remove the file first, then the row. ``delete_stored`` is best-effort
        # and never raises, so a missing file cannot abort the run; the row is
        # still removed so the database stays the source of truth.
        storage.delete_stored(attachment.storage_key)
        audit_service.record(
            db,
            action=AuditAction.WEBSITE_LEAD_CV_PURGED,
            actor_user_id=actor_user_id,
            entity_type="website_lead_attachment",
            entity_id=attachment.id,
            metadata={
                "lead_id": attachment.lead_id,
                "original_filename": attachment.original_filename,
                "storage_key": attachment.storage_key,
                "reason": "retention_expired",
                "retention_months": settings.CV_RETENTION_MONTHS,
                "cutoff": cutoff.isoformat(),
            },
            commit=False,
        )
        db.delete(attachment)

    if not dry_run:
        db.commit()
        # One summary row per run, so an operator can tell a clean run from a
        # run that removed CVs without scrolling the per-file entries.
        audit_service.record(
            db,
            action=AuditAction.RETENTION_CV_PURGE_RUN,
            actor_user_id=actor_user_id,
            entity_type="cv_retention",
            metadata={
                "removed_count": len(removed_ids),
                "cutoff": cutoff.isoformat(),
                "retention_months": settings.CV_RETENTION_MONTHS,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

    return {
        "cutoff": cutoff,
        "retention_months": settings.CV_RETENTION_MONTHS,
        "dry_run": dry_run,
        "removed_count": len(removed_ids),
        "removed_attachment_ids": removed_ids,
    }


__all__ = [
    "CAREERS_SERVICE_TYPE",
    "retention_cutoff",
    "expired_cv_attachments",
    "purge_expired_cvs",
]
