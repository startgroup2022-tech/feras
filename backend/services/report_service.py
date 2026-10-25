"""Monthly report and accountant-review services.

Business rules enforced here (not in the UI):

* A report belongs to exactly one company and one month.
* Only a draft can be edited or deleted; once submitted it is locked.
* Submitting moves ``draft`` -> ``submitted`` and stamps ``submitted_at``.
* The accountant records verified figures in a separate review row and moves
  the report to ``under_review`` or ``reviewed``. The originally submitted
  numbers are never overwritten, so an audit always shows both.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.errors import ConflictError, NotFoundError, ValidationError
from backend.db.base import utcnow
from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import (
    FinancialReviewStatus,
    NotificationType,
    ReportApprovalStatus,
    ReportClarificationKind,
    ReportLifecycleAction,
    ReportStatus,
)
from backend.db.models.identity import User
from backend.db.models.report import (
    MonthlyReport,
    MonthlyReportFinancialReview,
    ReportClarification,
    ReportLifecycleEvent,
)
from backend.rbac.authorization import (
    has_permission,
    require_company_access,
    require_permission,
)
from backend.rbac.permissions import Perm
from backend.repositories.scoped import MonthlyReportRepository
from backend.services import audit_service, notification_service


def create_report(
    db: Session,
    *,
    user: User,
    company_id: int,
    period_year: int,
    period_month: int,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> MonthlyReport:
    require_permission(user, Perm.REPORT_CREATE)
    # Company isolation: the caller must be able to *write* this company.
    require_company_access(user, company_id, write=True)

    repo = MonthlyReportRepository(db)
    if repo.get_by_company_period(company_id, period_year, period_month) is not None:
        raise ConflictError("A report already exists for this company and month.")

    report = MonthlyReport(
        company_id=company_id,
        period_year=period_year,
        period_month=period_month,
        status=ReportStatus.DRAFT.value,
        **payload,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    audit_service.record(
        db,
        action=AuditAction.REPORT_CREATED,
        actor_user_id=user.id,
        entity_type="monthly_report",
        entity_id=report.id,
        company_id=company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"period": f"{period_year}-{period_month:02d}"},
    )
    return report


def update_report(
    db: Session,
    *,
    user: User,
    report_id: int,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> MonthlyReport:
    require_permission(user, Perm.REPORT_UPDATE)
    report = _get_scoped_or_404(db, user, report_id)
    require_company_access(user, report.company_id, write=True)

    if report.status != ReportStatus.DRAFT.value:
        raise ConflictError("Only draft reports can be edited.")

    for key, value in payload.items():
        setattr(report, key, value)
    db.add(report)
    db.commit()
    db.refresh(report)

    audit_service.record(
        db,
        action=AuditAction.REPORT_UPDATED,
        actor_user_id=user.id,
        entity_type="monthly_report",
        entity_id=report.id,
        company_id=report.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"fields": sorted(payload.keys())},
    )
    return report


def organize_report_narrative(
    db: Session,
    *,
    user: User,
    report_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    """Return an AI organization *proposal* for a report's narrative (S09).

    The report itself is never modified: this reads the narrative fields and
    returns a suggestion for each, so the manager reviews it and keeps or
    discards it. The action is scoped like an edit -- a caller who could not
    write the report cannot reach its text -- and it is audited.
    """
    from backend.ai import organize as organize_module

    require_permission(user, Perm.REPORT_UPDATE)
    report = _get_scoped_or_404(db, user, report_id)
    require_company_access(user, report.company_id, write=True)
    # Organization is an editing action, so it obeys the same lock as an edit:
    # only a draft report can be organised.
    if report.status != ReportStatus.DRAFT.value:
        raise ConflictError("Only draft reports can be edited.")

    fields = {name: getattr(report, name) for name in organize_module.ORGANIZABLE_FIELDS}
    proposal = organize_module.organize_narrative(fields)

    audit_service.record(
        db,
        action=AuditAction.AI_TEXT_ORGANIZED,
        actor_user_id=user.id,
        entity_type="monthly_report",
        entity_id=report.id,
        company_id=report.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"fields": [p["field"] for p in proposal["proposals"]]},
    )
    return proposal


def _record_lifecycle(
    db: Session,
    *,
    report: MonthlyReport,
    action: str,
    from_status: str | None,
    to_status: str,
    actor: User | None,
    note: str | None = None,
) -> None:
    """Append one transition to the report version's workflow trail (D03).

    The trail is append-only: rows are added here and never updated. It is
    committed together with the status change so the two cannot drift.
    """
    db.add(
        ReportLifecycleEvent(
            report_id=report.id,
            action=action,
            from_status=from_status,
            to_status=to_status,
            actor_id=actor.id if actor is not None else None,
            note=note,
        )
    )


def submit_report(
    db: Session,
    *,
    user: User,
    report_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> MonthlyReport:
    require_permission(user, Perm.REPORT_SUBMIT)
    report = _get_scoped_or_404(db, user, report_id)
    require_company_access(user, report.company_id, write=True)

    if report.status != ReportStatus.DRAFT.value:
        raise ConflictError("Only a draft report can be submitted.")
    if report.revenue is None or report.expenses is None:
        raise ValidationError("Revenue and expenses are required before submitting.")

    previous_status = report.status
    report.status = ReportStatus.SUBMITTED.value
    report.submitted_at = utcnow()
    report.submitted_by_id = user.id
    # A correction version (version_number > 1) is a *resubmission*: the trail
    # keeps the two distinguishable while the status is the same.
    action = (
        ReportLifecycleAction.RESUBMITTED.value
        if report.version_number > 1
        else ReportLifecycleAction.SUBMITTED.value
    )
    _record_lifecycle(
        db,
        report=report,
        action=action,
        from_status=previous_status,
        to_status=report.status,
        actor=user,
        note=report.return_reason if report.version_number > 1 else None,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    audit_service.record(
        db,
        action=(
            AuditAction.REPORT_RESUBMITTED
            if report.version_number > 1
            else AuditAction.REPORT_SUBMITTED
        ),
        actor_user_id=user.id,
        entity_type="monthly_report",
        entity_id=report.id,
        company_id=report.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={
            "period": f"{report.period_year}-{report.period_month:02d}",
            "version_number": report.version_number,
        },
    )

    _notify_report_submitted(db, report=report, actor=user)
    return report


def return_report(
    db: Session,
    *,
    user: User,
    report_id: int,
    reason: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> MonthlyReport:
    """D03: a Holding reviewer returns a submitted report for correction (S09).

    The reason is mandatory. The report's status becomes ``returned`` and the
    *original submission is preserved*: the company manager fixes it by creating
    a linked correction version, never by editing this row.
    """
    require_permission(user, Perm.REPORT_REVIEW)
    report = _get_scoped_or_404(db, user, report_id)
    require_company_access(user, report.company_id)

    if not report.is_live:
        raise ConflictError("Only the current report version can be returned.")
    if report.status not in {
        ReportStatus.SUBMITTED.value,
        ReportStatus.UNDER_REVIEW.value,
        ReportStatus.REVIEWED.value,
    }:
        raise ConflictError("Only a submitted or reviewed report can be returned.")
    text = (reason or "").strip()
    if not text:
        raise ValidationError("A return reason is required.")

    previous_status = report.status
    report.status = ReportStatus.RETURNED.value
    report.return_reason = text
    report.returned_by_id = user.id
    report.returned_at = utcnow()
    _record_lifecycle(
        db,
        report=report,
        action=ReportLifecycleAction.RETURNED.value,
        from_status=previous_status,
        to_status=report.status,
        actor=user,
        note=text,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    audit_service.record(
        db,
        action=AuditAction.REPORT_RETURNED,
        actor_user_id=user.id,
        entity_type="monthly_report",
        entity_id=report.id,
        company_id=report.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"version_number": report.version_number, "reason": text},
    )
    _notify_report_lifecycle(
        db,
        report=report,
        actor=user,
        type=NotificationType.REPORT_RETURNED,
        title_ar="أُعيد تقرير شهري للتصحيح",
        title_en="A monthly report was returned for correction",
        message_ar=(
            f"أُعيد تقرير {report.period_month}/{report.period_year} للتصحيح: {text}"
        ),
        message_en=(
            f"The {report.period_month}/{report.period_year} report was returned "
            f"for correction: {text}"
        ),
    )
    return report


def create_correction(
    db: Session,
    *,
    user: User,
    report_id: int,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> MonthlyReport:
    """D03: create a *linked* correction version of a returned report (S09).

    The correction is a brand-new row with ``version_number`` incremented and
    ``corrects_report_id`` pointing at the returned version. The returned version
    is marked ``is_live = 0`` (superseded) but kept intact, so the full history
    survives. Only narrative fields are re-entered; the financial figures are
    carried over from the corrected version (the financial side is corrected
    through F-03, not here).
    """
    require_permission(user, Perm.REPORT_CREATE)
    require_permission(user, Perm.REPORT_UPDATE)
    report = _get_scoped_or_404(db, user, report_id)
    require_company_access(user, report.company_id, write=True)

    if not report.is_live:
        raise ConflictError("Only the current report version can be corrected.")
    if report.status != ReportStatus.RETURNED.value:
        raise ConflictError("Only a report returned for correction can be corrected.")

    repo = MonthlyReportRepository(db)
    version_number = repo.next_version_number(
        report.company_id, report.period_year, report.period_month
    )

    # Supersede the returned version; the unique live index guarantees only one
    # live version per company/period.
    report.is_live = False
    db.add(report)

    def _narrative(field: str):
        value = payload.get(field)
        return value if value is not None else getattr(report, field)

    correction = MonthlyReport(
        company_id=report.company_id,
        period_year=report.period_year,
        period_month=report.period_month,
        status=ReportStatus.DRAFT.value,
        version_number=version_number,
        corrects_report_id=report.id,
        is_live=True,
        approval_status=ReportApprovalStatus.PENDING.value,
        revenue=report.revenue,
        expenses=report.expenses,
        net_result=report.net_result,
        outstanding_receivables=report.outstanding_receivables,
        important_developments=_narrative("important_developments"),
        new_customers=_narrative("new_customers"),
        new_opportunities=_narrative("new_opportunities"),
        major_problems=_narrative("major_problems"),
        support_required=_narrative("support_required"),
        marketing_status=_narrative("marketing_status"),
        business_development_status=_narrative("business_development_status"),
        management_notes=_narrative("management_notes"),
    )
    db.add(correction)
    db.commit()
    db.refresh(correction)

    audit_service.record(
        db,
        action=AuditAction.REPORT_CORRECTION_CREATED,
        actor_user_id=user.id,
        entity_type="monthly_report",
        entity_id=correction.id,
        company_id=correction.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={
            "corrects_report_id": report.id,
            "version_number": version_number,
        },
    )
    return correction


def approve_report(
    db: Session,
    *,
    user: User,
    report_id: int,
    note: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> MonthlyReport:
    """D03: the Holding Owner gives the management report its final approval.

    Kept separate from the accountant's *financial* review: this closes the
    non-financial (management) side of the report. Owner-only by permission.
    """
    require_permission(user, Perm.REPORT_APPROVE)
    report = _get_scoped_or_404(db, user, report_id)
    require_company_access(user, report.company_id)

    if not report.is_live:
        raise ConflictError("Only the current report version can be approved.")
    if report.status not in {
        ReportStatus.SUBMITTED.value,
        ReportStatus.UNDER_REVIEW.value,
        ReportStatus.REVIEWED.value,
    }:
        raise ConflictError("Only a submitted or reviewed report can be approved.")

    previous_status = report.status
    report.status = ReportStatus.REVIEWED.value
    report.approval_status = ReportApprovalStatus.APPROVED.value
    report.approved_by_id = user.id
    report.approved_at = utcnow()
    _record_lifecycle(
        db,
        report=report,
        action=ReportLifecycleAction.APPROVED.value,
        from_status=previous_status,
        to_status=report.status,
        actor=user,
        note=note,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    audit_service.record(
        db,
        action=AuditAction.REPORT_APPROVED,
        actor_user_id=user.id,
        entity_type="monthly_report",
        entity_id=report.id,
        company_id=report.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"version_number": report.version_number},
    )
    _notify_report_lifecycle(
        db,
        report=report,
        actor=user,
        type=NotificationType.REPORT_APPROVED,
        title_ar="اعتُمد تقرير شهري",
        title_en="A monthly report was approved",
        message_ar=f"اعتُمد تقرير {report.period_month}/{report.period_year} نهائياً.",
        message_en=f"The {report.period_month}/{report.period_year} report was approved.",
    )
    return report


def cancel_report(
    db: Session,
    *,
    user: User,
    report_id: int,
    reason: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> MonthlyReport:
    """D03: owner-only cancellation of a report version (S09)."""
    require_permission(user, Perm.REPORT_APPROVE)
    report = _get_scoped_or_404(db, user, report_id)
    require_company_access(user, report.company_id)

    if report.status == ReportStatus.CANCELLED.value:
        raise ConflictError("The report is already cancelled.")
    text = (reason or "").strip()
    if not text:
        raise ValidationError("A cancellation reason is required.")

    previous_status = report.status
    report.status = ReportStatus.CANCELLED.value
    report.approval_status = ReportApprovalStatus.CANCELLED.value
    report.cancelled_by_id = user.id
    report.cancelled_at = utcnow()
    report.cancel_reason = text
    _record_lifecycle(
        db,
        report=report,
        action=ReportLifecycleAction.CANCELLED.value,
        from_status=previous_status,
        to_status=report.status,
        actor=user,
        note=text,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    audit_service.record(
        db,
        action=AuditAction.REPORT_CANCELLED,
        actor_user_id=user.id,
        entity_type="monthly_report",
        entity_id=report.id,
        company_id=report.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"version_number": report.version_number, "reason": text},
    )
    _notify_report_lifecycle(
        db,
        report=report,
        actor=user,
        type=NotificationType.REPORT_CANCELLED,
        title_ar="أُلغي تقرير شهري",
        title_en="A monthly report was cancelled",
        message_ar=f"أُلغي تقرير {report.period_month}/{report.period_year}: {text}",
        message_en=f"The {report.period_month}/{report.period_year} report was cancelled: {text}",
    )
    return report


def _notify_report_lifecycle(
    db: Session,
    *,
    report: MonthlyReport,
    actor: User,
    type: str,
    title_ar: str,
    title_en: str,
    message_ar: str,
    message_en: str,
) -> None:
    """Notify the company's report author of a workflow transition (best-effort)."""
    from backend.services import notification_service

    recipients = [report.submitted_by_id] if report.submitted_by_id else []
    recipients = [uid for uid in recipients if uid != actor.id]
    if not recipients:
        return
    try:
        notification_service.notify(
            db,
            recipient_ids=recipients,
            type=type,
            title_ar=title_ar,
            title_en=title_en,
            message_ar=message_ar,
            message_en=message_en,
            company_id=report.company_id,
            entity_type="monthly_report",
            entity_id=report.id,
            actor_user_id=actor.id,
        )
    except Exception:  # noqa: BLE001 - best-effort
        import logging

        logging.getLogger("safir.reports").exception("report lifecycle notification failed")


def _notify_report_submitted(db: Session, *, report, actor: User) -> None:
    """Tell the Holding's finance reviewers a subsidiary report has arrived."""
    from backend.db.models.identity import Company
    from backend.services import integration_service, notification_service

    try:
        recipients = notification_service.finance_reviewer_ids(db)
        company = db.get(Company, report.company_id)
        notification_service.notify_report_submitted(
            db,
            recipient_ids=recipients,
            report_id=report.id,
            company_id=report.company_id,
            company_name_ar=company.name_ar if company else "",
            company_name_en=(company.name_en if company else "") or "",
            year=report.period_year,
            month=report.period_month,
            actor_user_id=actor.id,
        )
        integration_service.emit(
            db,
            event_type="report.submitted",
            payload={
                "report_id": report.id,
                "company_id": report.company_id,
                "period_year": report.period_year,
                "period_month": report.period_month,
            },
            company_id=report.company_id,
        )
    except Exception:  # noqa: BLE001 - best-effort
        import logging

        logging.getLogger("safir.reports").exception("report submitted notification failed")


def review_financially(
    db: Session,
    *,
    user: User,
    report_id: int,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> MonthlyReportFinancialReview:
    """Accountant verification of a submitted report."""
    require_permission(user, Perm.FINANCIAL_REVIEW_WRITE)
    report = _get_scoped_or_404(db, user, report_id)
    require_company_access(user, report.company_id)

    if report.status == ReportStatus.DRAFT.value:
        raise ConflictError("A draft report cannot be financially reviewed.")

    accurate = bool(payload.get("is_financially_accurate"))
    review = db.query(MonthlyReportFinancialReview).filter(
        MonthlyReportFinancialReview.report_id == report.id
    ).one_or_none()

    if review is None:
        review = MonthlyReportFinancialReview(
            report_id=report.id, reviewer_id=user.id
        )

    review.reviewer_id = user.id
    review.status = (
        FinancialReviewStatus.APPROVED.value
        if accurate
        else FinancialReviewStatus.FLAGGED.value
    )
    review.is_financially_accurate = accurate
    review.financial_notes = payload.get("financial_notes")
    review.flagged_reason = payload.get("flagged_reason")

    # Default verified figures to the submitted ones unless corrected.
    review.verified_revenue = _coalesce(payload.get("verified_revenue"), report.revenue)
    review.verified_expenses = _coalesce(payload.get("verified_expenses"), report.expenses)
    review.verified_net_result = _coalesce(payload.get("verified_net_result"), report.net_result)
    review.verified_outstanding_receivables = _coalesce(
        payload.get("verified_outstanding_receivables"), report.outstanding_receivables
    )
    review.reviewed_at = utcnow()

    # Accurate data closes the loop; flagged data stays under review.
    report.status = (
        ReportStatus.REVIEWED.value
        if accurate
        else ReportStatus.UNDER_REVIEW.value
    )

    db.add(review)
    db.add(report)
    db.commit()
    db.refresh(review)

    audit_service.record(
        db,
        action=AuditAction.REPORT_FINANCIAL_REVIEWED,
        actor_user_id=user.id,
        entity_type="monthly_report",
        entity_id=report.id,
        company_id=report.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"accurate": accurate, "status": review.status},
    )
    return review


def _coalesce(new_value, existing):
    return new_value if new_value is not None else existing


def add_attachment(
    db: Session,
    *,
    user: User,
    report_id: int,
    filename: str,
    content_type: str | None,
    data: bytes,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> MonthlyReportAttachment:
    """Attach a file to a report.

    Permitted while the report is a draft (the manager is assembling it) and
    afterwards for evidence; a *reviewed* report is frozen, so attachments are
    refused there to keep the reviewed record immutable.
    """
    from backend.core import storage
    from backend.db.models.report import MonthlyReportAttachment

    require_permission(user, Perm.REPORT_UPDATE)
    report = _get_scoped_or_404(db, user, report_id)
    require_company_access(user, report.company_id, write=True)

    if report.status == ReportStatus.REVIEWED.value:
        raise ConflictError("A reviewed report cannot be modified.")

    extension = storage.validate_upload(
        filename=filename, content_type=content_type, size=len(data)
    )
    storage_key = storage.store_bytes(data=data, extension=extension)

    attachment = MonthlyReportAttachment(
        report_id=report.id,
        original_filename=filename.strip()[:255],
        storage_key=storage_key,
        content_type=content_type,
        size_bytes=len(data),
        uploaded_by_id=user.id,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)

    audit_service.record(
        db,
        action=AuditAction.REPORT_ATTACHMENT_ADDED,
        actor_user_id=user.id,
        entity_type="monthly_report",
        entity_id=report.id,
        company_id=report.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"filename": filename, "size": len(data)},
    )
    return attachment


def remove_attachment(
    db: Session,
    *,
    user: User,
    report_id: int,
    attachment_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    from backend.core import storage
    from backend.db.models.report import MonthlyReportAttachment

    require_permission(user, Perm.REPORT_UPDATE)
    report = _get_scoped_or_404(db, user, report_id)
    require_company_access(user, report.company_id, write=True)

    if report.status == ReportStatus.REVIEWED.value:
        raise ConflictError("A reviewed report cannot be modified.")

    attachment = db.get(MonthlyReportAttachment, attachment_id)
    if attachment is None or attachment.report_id != report.id:
        raise NotFoundError("Attachment not found.")

    storage.delete_stored(attachment.storage_key)
    db.delete(attachment)
    db.commit()

    audit_service.record(
        db,
        action=AuditAction.REPORT_ATTACHMENT_REMOVED,
        actor_user_id=user.id,
        entity_type="monthly_report",
        entity_id=report.id,
        company_id=report.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"attachment_id": attachment_id},
    )


def serialise_clarification(c: "ReportClarification") -> dict:
    return {
        "id": c.id,
        "report_id": c.report_id,
        "kind": c.kind,
        "body": c.body,
        "author_id": c.author_id,
        "author_name_ar": c.author.full_name_ar if c.author else None,
        "author_name_en": (c.author.full_name_en if c.author else None),
        "parent_id": c.parent_id,
        "created_at": c.created_at,
    }


def add_clarification(
    db: Session,
    *,
    user: User,
    report_id: int,
    body: str,
    kind: str = ReportClarificationKind.REQUEST.value,
    parent_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> "ReportClarification":
    """Attach a clarification request/reply to a report's original (S02/S09).

    The report itself is never modified. A ``request`` may be raised by a
    holding-level reader (owner/BD) or by the company's own manager; a ``reply``
    answers an existing request in the same report. The clarification is scoped
    through ``_get_scoped_or_404`` so an out-of-scope report id is a 404.
    """
    require_permission(user, Perm.REPORT_CLARIFY)
    report = _get_scoped_or_404(db, user, report_id)

    if kind not in {k.value for k in ReportClarificationKind}:
        raise ValidationError("Unknown clarification kind.")
    text = (body or "").strip()
    if not text:
        raise ValidationError("A clarification must carry a message.")

    if parent_id is not None:
        parent = db.get(ReportClarification, parent_id)
        if parent is None or parent.report_id != report.id:
            raise ValidationError("The clarification being answered is not on this report.")
    else:
        parent = None

    clarification = ReportClarification(
        report_id=report.id,
        kind=kind,
        body=text,
        author_id=user.id,
        parent_id=parent_id,
    )
    db.add(clarification)
    db.commit()
    db.refresh(clarification)

    audit_service.record(
        db,
        action=AuditAction.REPORT_CLARIFICATION_ADDED,
        actor_user_id=user.id,
        entity_type="monthly_report",
        entity_id=report.id,
        company_id=report.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"clarification_id": clarification.id, "kind": kind},
    )

    # Notify the counterpart: a request goes to the company's author, a reply
    # goes back to the request's author. Never expose another company's data.
    recipients: list[int] = []
    if kind == ReportClarificationKind.REQUEST.value and report.submitted_by_id:
        recipients = [report.submitted_by_id]
    elif parent is not None and parent.author_id:
        recipients = [parent.author_id]
    recipients = [uid for uid in recipients if uid != user.id]
    if recipients:
        notification_service.notify(
            db,
            recipient_ids=recipients,
            type=NotificationType.SYSTEM.value,
            title_ar="إيضاح على تقرير شهري",
            title_en="A clarification on a monthly report",
            message_ar=f"يوجد إيضاح مرتبط بتقرير {report.period_month}/{report.period_year}.",
            message_en=(
                f"There is a clarification linked to the "
                f"{report.period_month}/{report.period_year} report."
            ),
            company_id=report.company_id,
            entity_type="monthly_report",
            entity_id=report.id,
            actor_user_id=user.id,
        )
    return clarification


def list_clarifications(db: Session, *, user: User, report_id: int) -> list["ReportClarification"]:
    """The clarification thread for a report the caller may read."""
    _get_scoped_or_404(db, user, report_id)
    return list(
        db.execute(
            select(ReportClarification)
            .where(ReportClarification.report_id == report_id)
            .order_by(ReportClarification.created_at)
        ).scalars()
    )


def _get_scoped_or_404(db: Session, user: User, report_id: int) -> MonthlyReport:
    """Fetch a report inside the caller's company scope.

    An out-of-scope id is reported as *not found* rather than *forbidden*, so a
    caller cannot use the error to discover that another company's report
    exists (IDOR protection).
    """
    report = MonthlyReportRepository(db).get_for_user(user, report_id)
    if report is None:
        raise NotFoundError("Report not found.")
    return report


def serialise_lifecycle_event(event: ReportLifecycleEvent) -> dict:
    return {
        "id": event.id,
        "action": event.action,
        "from_status": event.from_status,
        "to_status": event.to_status,
        "actor_id": event.actor_id,
        "actor_name_ar": event.actor.full_name_ar if event.actor else None,
        "note": event.note,
        "created_at": event.created_at,
    }


def serialise_version(report: MonthlyReport) -> dict:
    """One row of the D03 version chain (summary, no narrative)."""
    return {
        "id": report.id,
        "version_number": report.version_number,
        "status": report.status,
        "approval_status": report.approval_status,
        "is_live": report.is_live,
        "corrects_report_id": report.corrects_report_id,
        "submitted_at": report.submitted_at,
        "returned_at": report.returned_at,
        "return_reason": report.return_reason,
        "approved_at": report.approved_at,
        "cancelled_at": report.cancelled_at,
        "created_at": report.created_at,
    }


def list_versions(db: Session, *, user: User, report_id: int) -> list[dict]:
    """The full correction chain for a report the caller may read (D03/S09).

    Every version is returned oldest-first, so the S09 screen can render the
    original alongside each correction. The read is scoped through the same
    404-not-403 rule as the report itself.
    """
    report = _get_scoped_or_404(db, user, report_id)
    rows = MonthlyReportRepository(db).versions_for(
        report.company_id, report.period_year, report.period_month
    )
    return [serialise_version(r) for r in rows]


def list_lifecycle(db: Session, *, user: User, report_id: int) -> list[dict]:
    """The ordered workflow trail for a report version the caller may read."""
    report = _get_scoped_or_404(db, user, report_id)
    events = (
        db.query(ReportLifecycleEvent)
        .filter(ReportLifecycleEvent.report_id == report.id)
        .order_by(ReportLifecycleEvent.id)
        .all()
    )
    return [serialise_lifecycle_event(e) for e in events]


def serialise(report: MonthlyReport, *, financial_part: dict | None = None) -> dict:
    """Attach company display names and the D03 version context to the response."""
    data = {
        "id": report.id,
        "company_id": report.company_id,
        "company_name_ar": report.company.name_ar if report.company else None,
        "company_name_en": report.company.name_en if report.company else None,
        "period_year": report.period_year,
        "period_month": report.period_month,
        "status": report.status,
        "version_number": report.version_number,
        "corrects_report_id": report.corrects_report_id,
        "is_live": report.is_live,
        "approval_status": report.approval_status,
        "return_reason": report.return_reason,
        "returned_at": report.returned_at,
        "approved_at": report.approved_at,
        "cancelled_at": report.cancelled_at,
        "cancel_reason": report.cancel_reason,
        "revenue": report.revenue,
        "expenses": report.expenses,
        "net_result": report.net_result,
        "outstanding_receivables": report.outstanding_receivables,
        "important_developments": report.important_developments,
        "new_customers": report.new_customers,
        "new_opportunities": report.new_opportunities,
        "major_problems": report.major_problems,
        "support_required": report.support_required,
        "marketing_status": report.marketing_status,
        "business_development_status": report.business_development_status,
        "management_notes": report.management_notes,
        "submitted_at": report.submitted_at,
        "created_at": report.created_at,
        "updated_at": report.updated_at,
        "financial_review": report.financial_review,
        "attachments": report.attachments,
        "financial_part": financial_part,
    }
    return data


__all__ = [
    "create_report",
    "update_report",
    "submit_report",
    "organize_report_narrative",
    "review_financially",
    "return_report",
    "create_correction",
    "approve_report",
    "cancel_report",
    "list_versions",
    "list_lifecycle",
    "add_attachment",
    "remove_attachment",
    "financial_part_status",
    "serialise",
    "serialise_version",
    "serialise_lifecycle_event",
    "MonthlyReport",
    "Decimal",
]


def financial_part_status(
    db: Session, *, report: MonthlyReport, user: User
) -> dict | None:
    """The linked F-03 financial part for a report's period (spec Table 42/AC-09).

    A report always shows the status of the financial part it is tied to: the
    company's financial period for the same year and month, with its single
    effective (approved) version or the current in-flight version. The figures
    are read from F-03, never copied into the report, so the report's own
    narrative and the accountant-verified numbers cannot drift apart.

    Returns ``None`` when the caller may not read financial summaries, or when no
    financial period exists yet -- in which case the report honestly shows "لا
    بيانات" for the financial part rather than a zero.
    """
    from backend.db.models.financial import FinancialPeriod
    from backend.repositories.scoped import FinancialPeriodRepository

    if not has_permission(user, Perm.FINANCIAL_SUMMARY_READ_OWN) and not has_permission(
        user, Perm.FINANCIAL_SUMMARY_READ_ALL
    ):
        return None

    period = FinancialPeriodRepository(db).get_by_company_period(
        report.company_id, report.period_year, report.period_month
    )
    if period is None:
        return {"status": "no_data", "effective_version": None, "current_version": None}

    effective = period.effective_version
    current = None
    if period.versions:
        current = sorted(period.versions, key=lambda v: v.version_number, reverse=True)[0]

    def _shape(version) -> dict | None:
        if version is None:
            return None
        return {
            "id": version.id,
            "version_number": version.version_number,
            "status": version.status,
        }

    return {
        "status": effective.status if effective is not None else (current.status if current else "no_data"),
        "effective_version": _shape(effective),
        "current_version": _shape(current),
    }
