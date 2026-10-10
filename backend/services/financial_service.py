"""Subsidiary financial summary workflow service (Execution 02).

Implements the approved state machine of spec section 14.1 (S05/S06/S08) on top
of :mod:`backend.db.models.financial`. All business rules live here, never in
the API layer or the UI.

State machine (per version)::

    DRAFT ──submit──▶ SUBMITTED ──approve──▶ APPROVED (effective)
      ▲                 │
      │                 └──return (mandatory note)──▶ CORRECTION_REQUIRED
      │                                                     │
      └──────────── resubmit ◀──────────────────────────────┘

    APPROVED ──create corrective version──▶ DRAFT (new version, original kept
                                             effective until the correction is
                                             approved)

Guarantees enforced here:

* Submission requires a bank statement (F-03); a draft may exist without one.
* A return must carry a note (spec AC-08: "الإرجاع بلا ملاحظة يرفض").
* The accountant may approve or return but can never edit the manager's
  manager-entered amounts (their role simply lacks the update permission).
* An approved version is never mutated; a correction is a *new* version linked
  to it, and the original stays the single effective version until the
  correction is approved.
* Approving a version atomically makes it the one effective version for the
  period -- the previous effective version is superseded, never double-counted.
* Re-submitting or re-approving the same version is rejected, so a double click
  cannot duplicate an action or a notification.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from backend.core.errors import ConflictError, NotFoundError, ValidationError
from backend.db.base import utcnow
from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import (
    FinancialInclusionRule,
    FinancialItemKind,
    FinancialReviewAction,
    FinancialSummaryStatus,
)
from backend.db.models.financial import (
    FinancialBankAttachment,
    FinancialItemDefinition,
    FinancialPeriod,
    FinancialReviewAction as FinancialReviewActionRow,
    FinancialSummaryItem,
    FinancialSummaryVersion,
)
from backend.db.models.identity import Company, User
from backend.rbac.authorization import require_company_access, require_permission
from backend.rbac.permissions import Perm
from backend.repositories.scoped import (
    FinancialPeriodRepository,
    FinancialVersionRepository,
)
from backend.services import audit_service
from backend.services.financial_calc import (
    CalculationResult,
    UnsupportedCurrencyError,
    calculate,
)

ACTIONABLE_STATUSES = {
    FinancialSummaryStatus.DRAFT.value,
    FinancialSummaryStatus.CORRECTION_REQUIRED.value,
}


# --------------------------------------------------------------------------
# creation
# --------------------------------------------------------------------------
def create_summary(
    db: Session,
    *,
    user: User,
    company_id: int,
    period_year: int,
    period_month: int,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> FinancialSummaryVersion:
    """Create the period (if needed) and its original draft version (F-03)."""
    require_permission(user, Perm.FINANCIAL_SUMMARY_CREATE)
    require_company_access(user, company_id, write=True)

    if not 1 <= period_month <= 12:
        raise ValidationError("The financial month must be between 1 and 12.")
    if not 2000 <= period_year <= 2100:
        raise ValidationError("The financial year is out of range.")

    repo = FinancialPeriodRepository(db)
    period = repo.get_by_company_period(company_id, period_year, period_month)
    version_repo = FinancialVersionRepository(db)

    if period is not None:
        # A period already exists: only allow a brand-new draft when it has no
        # versions yet. Otherwise the manager must open the existing summary.
        if version_repo.list_for_period(period.id):
            raise ConflictError(
                "A financial summary already exists for this company and month."
            )
    else:
        company = db.get(Company, company_id)
        period = FinancialPeriod(
            company_id=company_id,
            period_year=period_year,
            period_month=period_month,
            currency=(company.currency if company and company.currency else "SAR"),
        )
        db.add(period)
        db.flush()
        audit_service.record(
            db,
            action=AuditAction.FINANCIAL_PERIOD_CREATED,
            actor_user_id=user.id,
            entity_type="financial_period",
            entity_id=period.id,
            company_id=company_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"period": f"{period_year}-{period_month:02d}"},
            commit=False,
        )

    version = FinancialSummaryVersion(
        period_id=period.id,
        company_id=company_id,
        version_number=1,
        status=FinancialSummaryStatus.DRAFT.value,
        currency=period.currency,
        created_by_id=user.id,
    )
    _apply_editable_fields(version, payload)
    recompute(version)
    db.add(version)
    db.flush()

    audit_service.record(
        db,
        action=AuditAction.FINANCIAL_SUMMARY_CREATED,
        actor_user_id=user.id,
        entity_type="financial_summary_version",
        entity_id=version.id,
        company_id=company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"period": f"{period_year}-{period_month:02d}", "version": 1},
        commit=False,
    )
    db.commit()
    db.refresh(version)
    return version


def _apply_editable_fields(version: FinancialSummaryVersion, payload: dict) -> None:
    """Copy the manager-editable fields from a payload onto the version."""
    editable = {
        "submitted_revenue",
        "submitted_expenses",
        "closing_bank_balance",
        "closing_cash_balance",
        "outstanding_debts",
        "customer_receivables",
        "manager_notes",
        "bank_statement_reference",
    }
    for key, value in payload.items():
        if key in editable and value is not None:
            setattr(version, key, value)


def update_draft(
    db: Session,
    *,
    user: User,
    version_id: int,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> FinancialSummaryVersion:
    """Edit a draft (or a version returned for correction)."""
    require_permission(user, Perm.FINANCIAL_SUMMARY_UPDATE)
    version = _get_version_or_404(db, user, version_id)
    require_company_access(user, version.company_id, write=True)

    if version.status not in ACTIONABLE_STATUSES:
        raise ConflictError("Only a draft or correction-required summary can be edited.")

    _apply_editable_fields(version, payload)
    recompute(version)
    db.add(version)
    db.flush()

    audit_service.record(
        db,
        action=AuditAction.FINANCIAL_SUMMARY_UPDATED,
        actor_user_id=user.id,
        entity_type="financial_summary_version",
        entity_id=version.id,
        company_id=version.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"fields": sorted(payload.keys())},
        commit=False,
    )
    db.commit()
    db.refresh(version)
    return version


# --------------------------------------------------------------------------
# special items (F-04)
# --------------------------------------------------------------------------
def add_item(
    db: Session,
    *,
    user: User,
    version_id: int,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> FinancialSummaryItem:
    """Attach a special-item value to a draft version and recompute.

    The item's rules (name/category/kind/inclusion) are snapshotted from its
    definition so later edits to the definition never rewrite this version's
    history.
    """
    require_permission(user, Perm.FINANCIAL_SUMMARY_UPDATE)
    version = _get_version_or_404(db, user, version_id)
    require_company_access(user, version.company_id, write=True)
    if version.status not in ACTIONABLE_STATUSES:
        raise ConflictError("Items can only be changed on a draft summary.")

    definition = None
    definition_id = payload.get("definition_id")
    if definition_id is not None:
        definition = db.get(FinancialItemDefinition, definition_id)
        if definition is None or definition.company_id != version.company_id:
            raise NotFoundError("Item definition not found.")
        if not definition.is_active:
            raise ValidationError("This item definition is no longer active.")

    amount = payload.get("amount")
    if amount is None:
        raise ValidationError("An item amount is required.")
    amount = Decimal(str(amount))

    if definition is not None:
        code = definition.code
        name_ar = definition.name_ar
        name_en = definition.name_en
        category = definition.category
        kind = definition.kind
        inclusion_rule = definition.inclusion_rule
        decision_reference = definition.decision_reference
    else:
        # Ad-hoc item: the caller supplies the snapshot fields explicitly.
        code = payload.get("code") or "adhoc"
        name_ar = payload.get("name_ar") or code
        name_en = payload.get("name_en") or code
        category = payload.get("category") or "other"
        kind = payload.get("kind") or FinancialItemKind.OTHER.value
        inclusion_rule = (
            payload.get("inclusion_rule") or FinancialInclusionRule.INCLUDED.value
        )
        decision_reference = payload.get("decision_reference")

    item = FinancialSummaryItem(
        version_id=version.id,
        definition_id=definition.id if definition else None,
        code=code,
        name_ar=name_ar,
        name_en=name_en,
        category=category,
        kind=kind,
        inclusion_rule=inclusion_rule,
        decision_reference=decision_reference,
        amount=amount,
        currency=payload.get("currency") or version.currency,
        reason=payload.get("reason"),
        notes=payload.get("notes"),
    )
    db.add(item)
    db.flush()
    _recompute_version(db, version)

    audit_service.record(
        db,
        action=AuditAction.FINANCIAL_ITEM_ADDED,
        actor_user_id=user.id,
        entity_type="financial_summary_version",
        entity_id=version.id,
        company_id=version.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"item_code": code, "amount": str(amount)},
        commit=False,
    )
    db.commit()
    db.refresh(item)
    return item


def remove_item(
    db: Session,
    *,
    user: User,
    version_id: int,
    item_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    require_permission(user, Perm.FINANCIAL_SUMMARY_UPDATE)
    version = _get_version_or_404(db, user, version_id)
    require_company_access(user, version.company_id, write=True)
    if version.status not in ACTIONABLE_STATUSES:
        raise ConflictError("Items can only be changed on a draft summary.")

    item = db.get(FinancialSummaryItem, item_id)
    if item is None or item.version_id != version.id:
        raise NotFoundError("Item not found.")

    db.delete(item)
    db.flush()
    _recompute_version(db, version)

    audit_service.record(
        db,
        action=AuditAction.FINANCIAL_ITEM_REMOVED,
        actor_user_id=user.id,
        entity_type="financial_summary_version",
        entity_id=version.id,
        company_id=version.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"item_id": item_id},
        commit=False,
    )
    db.commit()


# --------------------------------------------------------------------------
# bank statement (F-03, mandatory at submission)
# --------------------------------------------------------------------------
def add_bank_attachment(
    db: Session,
    *,
    user: User,
    version_id: int,
    filename: str,
    content_type: str | None,
    data: bytes,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> FinancialBankAttachment:
    """Attach a bank statement. Allowed while the version is still editable."""
    from backend.core import storage

    require_permission(user, Perm.FINANCIAL_SUMMARY_UPDATE)
    version = _get_version_or_404(db, user, version_id)
    require_company_access(user, version.company_id, write=True)
    if version.status not in ACTIONABLE_STATUSES:
        raise ConflictError("A bank statement can only be attached to a draft summary.")

    # The bank statement is a financial document: reuse the private internal
    # allow-list (PDF/XLSX/DOCX/CSV/PNG/JPEG), never a public image list.
    extension = storage.validate_upload(
        filename=filename, content_type=content_type, size=len(data)
    )
    storage_key = storage.store_bytes(data=data, extension=extension)

    attachment = FinancialBankAttachment(
        version_id=version.id,
        company_id=version.company_id,
        original_filename=filename.strip()[:255],
        storage_key=storage_key,
        content_type=content_type,
        size_bytes=len(data),
        uploaded_by_id=user.id,
    )
    db.add(attachment)
    db.flush()

    audit_service.record(
        db,
        action=AuditAction.FINANCIAL_BANK_ATTACHMENT_ADDED,
        actor_user_id=user.id,
        entity_type="financial_summary_version",
        entity_id=version.id,
        company_id=version.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"filename": filename, "size": len(data)},
        commit=False,
    )
    db.commit()
    db.refresh(attachment)
    return attachment


def get_bank_attachment_for_download(
    db: Session,
    *,
    user: User,
    version_id: int,
    attachment_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> FinancialBankAttachment:
    """Resolve a bank statement for an authenticated, scoped download.

    Company scope is applied when fetching the version, so an out-of-scope id is
    reported as *not found* -- the same IDOR protection used elsewhere. The
    attachment id must belong to that version, so a guessed id cannot cross to
    another record's file.
    """
    require_permission(user, Perm.FINANCIAL_BANK_READ)
    version = _get_version_or_404(db, user, version_id)
    require_company_access(user, version.company_id)

    attachment = db.get(FinancialBankAttachment, attachment_id)
    if attachment is None or attachment.version_id != version.id:
        raise NotFoundError("Bank statement not found.")

    audit_service.record(
        db,
        action=AuditAction.FINANCIAL_BANK_ATTACHMENT_VIEWED,
        actor_user_id=user.id,
        entity_type="financial_summary_version",
        entity_id=version.id,
        company_id=version.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"attachment_id": attachment_id},
        commit=True,
    )
    return attachment


# --------------------------------------------------------------------------
# workflow transitions
# --------------------------------------------------------------------------
def submit_version(
    db: Session,
    *,
    user: User,
    version_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> FinancialSummaryVersion:
    """Send a draft (or corrected) version to the accountant with its bank statement."""
    require_permission(user, Perm.FINANCIAL_SUMMARY_SUBMIT)
    version = _get_version_or_404(db, user, version_id)
    require_company_access(user, version.company_id, write=True)

    if version.status not in ACTIONABLE_STATUSES:
        raise ConflictError("Only a draft summary can be submitted.")
    if not version.bank_attachments:
        raise ValidationError("A bank statement is required before submitting.")
    _recompute_version(db, version)

    was_correction = version.status == FinancialSummaryStatus.CORRECTION_REQUIRED.value
    from_status = version.status
    version.status = FinancialSummaryStatus.SUBMITTED.value
    version.submitted_at = utcnow()
    version.submitted_by_id = user.id
    version.return_note = None
    db.add(version)
    _record_action(
        db,
        version=version,
        action=(
            FinancialReviewAction.RESUBMITTED.value
            if was_correction
            else FinancialReviewAction.SUBMITTED.value
        ),
        actor=user,
        from_status=from_status,
        to_status=version.status,
    )
    audit_service.record(
        db,
        action=(
            AuditAction.FINANCIAL_SUMMARY_RESUBMITTED
            if was_correction
            else AuditAction.FINANCIAL_SUMMARY_SUBMITTED
        ),
        actor_user_id=user.id,
        entity_type="financial_summary_version",
        entity_id=version.id,
        company_id=version.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"version": version.version_number, "correction": was_correction},
        commit=False,
    )
    db.commit()
    db.refresh(version)

    _notify(
        db,
        version=version,
        event="submitted" if not was_correction else "resubmitted",
        actor=user,
    )
    return version


def return_version(
    db: Session,
    *,
    user: User,
    version_id: int,
    note: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> FinancialSummaryVersion:
    """Accountant returns a submitted version for correction (mandatory note)."""
    require_permission(user, Perm.FINANCIAL_REVIEW_ACT)
    version = _get_version_or_404(db, user, version_id)
    require_company_access(user, version.company_id)

    if not (note and note.strip()):
        raise ValidationError("A note is required when returning a summary for correction.")
    if version.status != FinancialSummaryStatus.SUBMITTED.value:
        raise ConflictError("Only a submitted summary can be returned for correction.")

    from_status = version.status
    version.status = FinancialSummaryStatus.CORRECTION_REQUIRED.value
    version.return_note = note.strip()
    version.reviewed_at = utcnow()
    version.reviewed_by_id = user.id
    db.add(version)
    _record_action(
        db,
        version=version,
        action=FinancialReviewAction.RETURNED.value,
        actor=user,
        from_status=from_status,
        to_status=version.status,
        note=note.strip(),
    )
    audit_service.record(
        db,
        action=AuditAction.FINANCIAL_SUMMARY_RETURNED,
        actor_user_id=user.id,
        entity_type="financial_summary_version",
        entity_id=version.id,
        company_id=version.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"version": version.version_number, "note": note.strip()},
        commit=False,
    )
    db.commit()
    db.refresh(version)

    _notify(db, version=version, event="returned", actor=user)
    return version


def approve_version(
    db: Session,
    *,
    user: User,
    version_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> FinancialSummaryVersion:
    """Accountant approves a submitted version.

    Atomically closes the version and makes it the single effective version for
    its period. A previously effective version is superseded (its status is left
    ``APPROVED`` for history, but ``period.effective_version_id`` moves), so the
    two are never both counted as current.
    """
    require_permission(user, Perm.FINANCIAL_REVIEW_ACT)
    version = _get_version_or_404(db, user, version_id)
    require_company_access(user, version.company_id)

    if version.status != FinancialSummaryStatus.SUBMITTED.value:
        raise ConflictError("Only a submitted summary can be approved.")
    if not version.bank_attachments:
        raise ValidationError("A summary cannot be approved without a bank statement.")

    from_status = version.status
    version.status = FinancialSummaryStatus.APPROVED.value
    version.approved_at = utcnow()
    version.approved_by_id = user.id
    version.reviewed_at = version.reviewed_at or utcnow()
    version.reviewed_by_id = version.reviewed_by_id or user.id
    db.add(version)

    period = db.get(FinancialPeriod, version.period_id)
    if period is not None:
        period.effective_version_id = version.id
        db.add(period)

    _record_action(
        db,
        version=version,
        action=FinancialReviewAction.APPROVED.value,
        actor=user,
        from_status=from_status,
        to_status=version.status,
    )
    audit_service.record(
        db,
        action=AuditAction.FINANCIAL_SUMMARY_APPROVED,
        actor_user_id=user.id,
        entity_type="financial_summary_version",
        entity_id=version.id,
        company_id=version.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={
            "version": version.version_number,
            "effective_version_id": version.id,
        },
        commit=False,
    )
    # The version change and the effective-version pointer are one transaction.
    db.commit()
    db.refresh(version)

    _notify(db, version=version, event="approved", actor=user)
    return version


def create_correction(
    db: Session,
    *,
    user: User,
    period_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> FinancialSummaryVersion:
    """Create a corrective version linked to the currently effective one.

    Copies the effective version's figures and items as a starting point. The
    original approved version is not modified and remains effective until the
    correction is itself approved.
    """
    require_permission(user, Perm.FINANCIAL_SUMMARY_CORRECT)
    period = FinancialPeriodRepository(db).get_for_user(user, period_id)
    if period is None:
        raise NotFoundError("Financial period not found.")
    require_company_access(user, period.company_id, write=True)

    if period.effective_version_id is None:
        raise ConflictError(
            "A corrective version can only be created for an approved summary."
        )
    original = db.get(FinancialSummaryVersion, period.effective_version_id)
    if original is None or original.status != FinancialSummaryStatus.APPROVED.value:
        raise ConflictError("The effective version is not available for correction.")

    repo = FinancialVersionRepository(db)
    next_number = repo.latest_number(period.id) + 1
    correction = FinancialSummaryVersion(
        period_id=period.id,
        company_id=period.company_id,
        version_number=next_number,
        status=FinancialSummaryStatus.DRAFT.value,
        currency=original.currency,
        corrects_version_id=original.id,
        created_by_id=user.id,
        submitted_revenue=original.submitted_revenue,
        submitted_expenses=original.submitted_expenses,
        closing_bank_balance=original.closing_bank_balance,
        closing_cash_balance=original.closing_cash_balance,
        outstanding_debts=original.outstanding_debts,
        customer_receivables=original.customer_receivables,
        manager_notes=original.manager_notes,
    )
    db.add(correction)
    db.flush()

    # Copy the items as a fresh snapshot, so editing the correction's items does
    # not touch the original's.
    for item in list(original.items):
        db.add(
            FinancialSummaryItem(
                version_id=correction.id,
                definition_id=item.definition_id,
                code=item.code,
                name_ar=item.name_ar,
                name_en=item.name_en,
                category=item.category,
                kind=item.kind,
                inclusion_rule=item.inclusion_rule,
                decision_reference=item.decision_reference,
                amount=item.amount,
                currency=item.currency,
                reason=item.reason,
                notes=item.notes,
            )
        )
    db.flush()
    _recompute_version(db, correction)

    _record_action(
        db,
        version=correction,
        action=FinancialReviewAction.CORRECTION_CREATED.value,
        actor=user,
        from_status=None,
        to_status=correction.status,
        note=f"corrects version {original.version_number}",
    )
    audit_service.record(
        db,
        action=AuditAction.FINANCIAL_SUMMARY_CORRECTION_CREATED,
        actor_user_id=user.id,
        entity_type="financial_summary_version",
        entity_id=correction.id,
        company_id=period.company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={
            "period_id": period.id,
            "corrects_version_id": original.id,
            "version": next_number,
        },
        commit=False,
    )
    db.commit()
    db.refresh(correction)
    return correction


# --------------------------------------------------------------------------
# calculation
# --------------------------------------------------------------------------
def recompute(version: FinancialSummaryVersion) -> CalculationResult:
    """Recompute a version's effective figures from its current items."""
    return _recompute_version_from_items(version, list(version.items))


def _recompute_version(db: Session, version: FinancialSummaryVersion) -> CalculationResult:
    db.flush()
    items = list(
        db.query(FinancialSummaryItem)
        .filter(FinancialSummaryItem.version_id == version.id)
        .all()
    )
    return _recompute_version_from_items(version, items)


def _recompute_version_from_items(
    version: FinancialSummaryVersion, items: list[FinancialSummaryItem]
) -> CalculationResult:
    result = calculate(
        entered_revenue=version.submitted_revenue,
        entered_expenses=version.submitted_expenses,
        items=items,
        closing_bank_balance=version.closing_bank_balance,
        closing_cash_balance=version.closing_cash_balance,
        base_currency=version.currency or "SAR",
    )
    version.effective_revenue = result.effective_revenue
    version.effective_expenses = result.effective_expenses
    version.calculated_result = result.result
    version.calculated_total_cash = result.total_cash
    return result


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _record_action(
    db: Session,
    *,
    version: FinancialSummaryVersion,
    action: str,
    actor: User,
    from_status: str | None,
    to_status: str | None,
    note: str | None = None,
) -> FinancialReviewActionRow:
    row = FinancialReviewActionRow(
        period_id=version.period_id,
        version_id=version.id,
        action=action,
        from_status=from_status,
        to_status=to_status,
        actor_user_id=actor.id,
        note=note,
    )
    db.add(row)
    db.flush()
    return row


def _get_version_or_404(db: Session, user: User, version_id: int) -> FinancialSummaryVersion:
    version = FinancialVersionRepository(db).get_for_user(user, version_id)
    if version is None:
        raise NotFoundError("Financial summary not found.")
    return version


def _notify(db: Session, *, version: FinancialSummaryVersion, event: str, actor: User) -> None:
    """Best-effort notification; never breaks the committed workflow action."""
    try:
        from backend.services import financial_notifications
        from backend.services import integration_service

        company = db.get(Company, version.company_id)
        financial_notifications.emit_summary_event(
            db,
            version=version,
            event=event,
            company=company,
            actor_user_id=actor.id,
        )
        integration_service.emit(
            db,
            event_type=f"financial_summary.{event}",
            payload={
                "version_id": version.id,
                "period_id": version.period_id,
                "company_id": version.company_id,
                "version_number": version.version_number,
                "status": version.status,
            },
            company_id=version.company_id,
        )
    except Exception:  # noqa: BLE001 - notifications are best-effort
        import logging

        logging.getLogger("safir.financial").exception(
            "financial summary notification failed"
        )


def serialise(version: FinancialSummaryVersion) -> dict:
    """Serialise a version with its computed trace, items and attachments."""
    period = version.period
    return {
        "id": version.id,
        "period_id": version.period_id,
        "company_id": version.company_id,
        "company_name_ar": version.company.name_ar if version.company else None,
        "company_name_en": version.company.name_en if version.company else None,
        "period_year": period.period_year if period else None,
        "period_month": period.period_month if period else None,
        "version_number": version.version_number,
        "status": version.status,
        "currency": version.currency,
        "corrects_version_id": version.corrects_version_id,
        "submitted_revenue": version.submitted_revenue,
        "submitted_expenses": version.submitted_expenses,
        "effective_revenue": version.effective_revenue,
        "effective_expenses": version.effective_expenses,
        "calculated_result": version.calculated_result,
        "closing_bank_balance": version.closing_bank_balance,
        "closing_cash_balance": version.closing_cash_balance,
        "calculated_total_cash": version.calculated_total_cash,
        "outstanding_debts": version.outstanding_debts,
        "customer_receivables": version.customer_receivables,
        "manager_notes": version.manager_notes,
        "bank_statement_reference": version.bank_statement_reference,
        "return_note": version.return_note,
        "submitted_at": version.submitted_at,
        "reviewed_at": version.reviewed_at,
        "approved_at": version.approved_at,
        "created_at": version.created_at,
        "updated_at": version.updated_at,
        "created_by_id": version.created_by_id,
        "items": [_serialise_item(i) for i in version.items],
        "bank_attachments": [_serialise_bank(a) for a in version.bank_attachments],
    }


def _serialise_item(item: FinancialSummaryItem) -> dict:
    return {
        "id": item.id,
        "definition_id": item.definition_id,
        "code": item.code,
        "name_ar": item.name_ar,
        "name_en": item.name_en,
        "category": item.category,
        "kind": item.kind,
        "inclusion_rule": item.inclusion_rule,
        "decision_reference": item.decision_reference,
        "amount": item.amount,
        "currency": item.currency,
        "reason": item.reason,
        "notes": item.notes,
    }


def _serialise_bank(attachment: FinancialBankAttachment) -> dict:
    # The storage key is never exposed; only metadata a viewer needs.
    return {
        "id": attachment.id,
        "original_filename": attachment.original_filename,
        "content_type": attachment.content_type,
        "size_bytes": attachment.size_bytes,
        "created_at": attachment.created_at,
    }


def serialise_period(period: FinancialPeriod) -> dict:
    """Serialise a period with its versions (newest first) and effective id."""
    return {
        "id": period.id,
        "company_id": period.company_id,
        "company_name_ar": period.company.name_ar if period.company else None,
        "company_name_en": period.company.name_en if period.company else None,
        "period_year": period.period_year,
        "period_month": period.period_month,
        "currency": period.currency,
        "effective_version_id": period.effective_version_id,
        "versions": [
            serialise(v)
            for v in sorted(period.versions, key=lambda v: v.version_number, reverse=True)
        ],
    }


__all__ = [
    "create_summary",
    "update_draft",
    "add_item",
    "remove_item",
    "add_bank_attachment",
    "get_bank_attachment_for_download",
    "submit_version",
    "return_version",
    "approve_version",
    "create_correction",
    "recompute",
    "serialise",
    "serialise_period",
    "UnsupportedCurrencyError",
]
