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
    ReportClarificationKind,
    ReportStatus,
)
from backend.db.models.identity import User
from backend.db.models.report import (
    MonthlyReport,
    MonthlyReportFinancialReview,
    ReportClarification,
)
from backend.rbac.authorization import require_company_access, require_permission
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

    report.status = ReportStatus.SUBMITTED.value
    report.submitted_at = utcnow()
    report.submitted_by_id = user.id
    db.add(report)
    db.commit()
    db.refresh(report)

    audit_service.record(
        db,
        action=AuditAction.REPORT_SUBMITTED,
        actor_user_id=user.id,
        entity_type="monthly_report",
        entity_id=report.id,
        company_id=report.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"period": f"{report.period_year}-{report.period_month:02d}"},
    )

    _notify_report_submitted(db, report=report, actor=user)
    return report


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


def serialise(report: MonthlyReport) -> dict:
    """Attach company display names for the API response."""
    data = {
        "id": report.id,
        "company_id": report.company_id,
        "company_name_ar": report.company.name_ar if report.company else None,
        "company_name_en": report.company.name_en if report.company else None,
        "period_year": report.period_year,
        "period_month": report.period_month,
        "status": report.status,
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
    }
    return data


__all__ = [
    "create_report",
    "update_report",
    "submit_report",
    "review_financially",
    "add_attachment",
    "remove_attachment",
    "serialise",
    "MonthlyReport",
    "Decimal",
]
