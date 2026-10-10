"""Typed notification emitters for the financial summary workflow (spec Table 73).

Kept separate from :mod:`backend.services.notification_service` only to avoid
bloating that module; it calls the shared :func:`notify` so dedupe, audit and
webhook behaviour are identical.

Recipients follow the specification:

* submitted / resubmitted -> the accountants who hold a financial-review permission;
* returned -> the subsidiary manager who submitted the version;
* approved -> the manager (the outcome is visible to the Owner and Business
  Development through the reporting layer; no disbursement is implied).

Every event carries a ``dedupe_key`` including the version id and event, so a
repeated request cannot raise a duplicate notification.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.db.models.enums import NotificationPriority, NotificationType
from backend.db.models.financial import FinancialSummaryVersion
from backend.services import notification_service


def _manager_ids(version: FinancialSummaryVersion) -> list[int]:
    ids = {version.submitted_by_id, version.created_by_id}
    return [uid for uid in ids if uid]


def emit_summary_event(
    db: Session,
    *,
    version: FinancialSummaryVersion,
    event: str,
    company,
    actor_user_id: int | None = None,
) -> None:
    """Raise the notification(s) for one workflow event on a version."""
    company_ar = company.name_ar if company else ""
    company_en = (company.name_en if company else "") or ""
    period = version.period
    period_label = (
        f"{period.period_month:02d}/{period.period_year}" if period else ""
    )
    version_no = version.version_number

    if event in ("submitted", "resubmitted"):
        recipients = notification_service.finance_reviewer_ids(db)
        if event == "submitted":
            type_ = NotificationType.FINANCIAL_SUMMARY_SUBMITTED.value
            title_ar = "ملخص مالي جديد بانتظار المراجعة"
            title_en = "A financial summary awaits your review"
            msg_ar = f"{company_ar} أرسلت الملخص المالي {period_label} (نسخة {version_no})."
            msg_en = f"{company_en} submitted its {period_label} financial summary (v{version_no})."
        else:
            type_ = NotificationType.FINANCIAL_SUMMARY_RESUBMITTED.value
            title_ar = "ملخص مالي مُصحَّح بانتظار المراجعة"
            title_en = "A corrected financial summary awaits your review"
            msg_ar = f"{company_ar} أعادت إرسال الملخص المالي {period_label} (نسخة {version_no})."
            msg_en = f"{company_en} resubmitted its {period_label} financial summary (v{version_no})."
        notification_service.notify(
            db,
            recipient_ids=recipients,
            type=type_,
            priority=(
                NotificationPriority.HIGH.value
                if event == "resubmitted"
                else NotificationPriority.NORMAL.value
            ),
            title_ar=title_ar,
            title_en=title_en,
            message_ar=msg_ar,
            message_en=msg_en,
            company_id=version.company_id,
            entity_type="financial_summary_version",
            entity_id=version.id,
            actor_user_id=actor_user_id,
            dedupe_key=f"fin_summary:{event}:{version.id}",
        )
        return

    if event == "returned":
        notification_service.notify(
            db,
            recipient_ids=_manager_ids(version),
            type=NotificationType.FINANCIAL_SUMMARY_RETURNED.value,
            priority=NotificationPriority.HIGH.value,
            title_ar="أُعيد الملخص المالي للتصحيح",
            title_en="Your financial summary was returned for correction",
            message_ar=(
                f"أُعيد الملخص المالي {period_label} (نسخة {version_no}) للتصحيح: "
                f"{version.return_note or ''}"
            ),
            message_en=(
                f"The {period_label} financial summary (v{version_no}) was returned "
                f"for correction: {version.return_note or ''}"
            ),
            company_id=version.company_id,
            entity_type="financial_summary_version",
            entity_id=version.id,
            actor_user_id=actor_user_id,
            dedupe_key=f"fin_summary:{event}:{version.id}",
        )
        return

    if event == "approved":
        notification_service.notify(
            db,
            recipient_ids=_manager_ids(version),
            type=NotificationType.FINANCIAL_SUMMARY_APPROVED.value,
            priority=NotificationPriority.NORMAL.value,
            title_ar="تم اعتماد الملخص المالي",
            title_en="Your financial summary was approved",
            message_ar=(
                f"اعتُمد الملخص المالي {period_label} (نسخة {version_no}) وأصبح النسخة الفعالة."
            ),
            message_en=(
                f"The {period_label} financial summary (v{version_no}) was approved "
                f"and is now the effective version."
            ),
            company_id=version.company_id,
            entity_type="financial_summary_version",
            entity_id=version.id,
            actor_user_id=actor_user_id,
            dedupe_key=f"fin_summary:{event}:{version.id}",
        )


__all__ = ["emit_summary_event"]
