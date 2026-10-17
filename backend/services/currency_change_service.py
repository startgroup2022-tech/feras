"""D09: base-currency change workflow.

Approved flow: **request -> accountant review -> owner approval -> scheduled for
a new financial period -> applied**. A change never rewrites history:

* the company's ``currency`` (its base currency) is only changed when the request
  is *applied*, and application is refused until the approved effective period
  begins;
* ``FinancialPeriod.currency`` is already snapshotted per period, so past
  journals, invoices, balances and reports keep the currency they were recorded
  in -- no retrospective conversion exists anywhere in the codebase;
* because there is no approved conversion-rate policy, this module never invents
  one. A request records the currencies and the effective period only. Any
  opening-balance / conversion entries a change might need stay **pending
  separate owner authorization** (see ``PENDING_TRANSITION_ITEMS``).

Every transition writes an audit row and notifies the relevant party.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.errors import ConflictError, NotFoundError, ValidationError
from backend.db.base import utcnow
from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import CurrencyChangeStatus
from backend.db.models.governance import CurrencyChangeRequest
from backend.db.models.identity import Company, User
from backend.rbac.authorization import (
    accessible_company_ids,
    require_company_access,
    require_permission,
)
from backend.rbac.permissions import Perm
from backend.services import audit_service

# Accounting transition entries a currency change may require. None may be
# created without a separate owner decision, so they are surfaced as pending.
PENDING_TRANSITION_ITEMS = (
    "opening_balances_in_new_currency",
    "currency_conversion_rate",
    "transition_journal_entries",
)


def _require_company(db: Session, company_id: int) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise NotFoundError("Company not found.")
    return company


def request_change(
    db: Session,
    *,
    user: User,
    company_id: int,
    requested_currency: str,
    justification: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> CurrencyChangeRequest:
    """Open a base-currency change request. Does not change anything yet."""
    require_permission(user, Perm.CURRENCY_CHANGE_REQUEST)
    require_company_access(user, company_id, write=True)
    if not justification or not justification.strip():
        raise ValidationError("A business justification is required.")
    requested_currency = (requested_currency or "").strip().upper()
    if not (2 <= len(requested_currency) <= 8) or not requested_currency.isalpha():
        raise ValidationError("A valid ISO currency code is required.")

    company = _require_company(db, company_id)
    if company.currency == requested_currency:
        raise ValidationError("The company already uses this currency.")

    # One open request per company at a time.
    open_rows = db.execute(
        select(CurrencyChangeRequest).where(
            CurrencyChangeRequest.company_id == company_id,
            CurrencyChangeRequest.status.in_(
                [
                    CurrencyChangeStatus.REQUESTED.value,
                    CurrencyChangeStatus.REVIEWED.value,
                    CurrencyChangeStatus.APPROVED.value,
                    CurrencyChangeStatus.SCHEDULED.value,
                ]
            ),
        )
    ).scalars().first()
    if open_rows is not None:
        raise ConflictError("A currency-change request is already open for this company.")

    row = CurrencyChangeRequest(
        company_id=company_id,
        current_currency=company.currency,
        requested_currency=requested_currency,
        justification=justification.strip(),
        status=CurrencyChangeStatus.REQUESTED.value,
        requested_by_id=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    audit_service.record(
        db, action=AuditAction.CURRENCY_CHANGE_REQUESTED, actor_user_id=user.id,
        entity_type="currency_change_request", entity_id=row.id, company_id=company_id,
        ip_address=ip_address, user_agent=user_agent,
        metadata={"from": row.current_currency, "to": row.requested_currency},
    )
    _notify_reviewers(db, row=row)
    return row


def review_change(
    db: Session,
    *,
    user: User,
    request_id: int,
    note: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> CurrencyChangeRequest:
    """Accountant review of a request (does not approve or apply it)."""
    require_permission(user, Perm.CURRENCY_CHANGE_REVIEW)
    row = db.get(CurrencyChangeRequest, request_id)
    if row is None:
        raise NotFoundError("Currency-change request not found.")
    require_company_access(user, row.company_id, write=True)
    if row.status != CurrencyChangeStatus.REQUESTED.value:
        raise ConflictError("This request is not awaiting review.")

    row.status = CurrencyChangeStatus.REVIEWED.value
    row.reviewed_by_id = user.id
    row.reviewed_at = utcnow()
    row.review_note = note
    db.add(row)
    db.commit()
    db.refresh(row)
    audit_service.record(
        db, action=AuditAction.CURRENCY_CHANGE_REVIEWED, actor_user_id=user.id,
        entity_type="currency_change_request", entity_id=row.id, company_id=row.company_id,
        ip_address=ip_address, user_agent=user_agent, metadata={"note": note},
    )
    _notify_owner(db, row=row, kind="reviewed")
    return row


def decide_change(
    db: Session,
    *,
    user: User,
    request_id: int,
    approve: bool,
    effective_year: int | None = None,
    effective_month: int | None = None,
    note: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> CurrencyChangeRequest:
    """Owner approval/rejection. Approval schedules the change for a period.

    Approval requires an explicit effective financial period and never applies
    the change immediately -- it becomes ``scheduled`` and is applied only by
    ``apply_change`` once that period begins.
    """
    require_permission(user, Perm.CURRENCY_CHANGE_APPROVE)
    row = db.get(CurrencyChangeRequest, request_id)
    if row is None:
        raise NotFoundError("Currency-change request not found.")
    if row.status not in {
        CurrencyChangeStatus.REQUESTED.value,
        CurrencyChangeStatus.REVIEWED.value,
    }:
        raise ConflictError("This request is not awaiting a decision.")

    if approve:
        if effective_year is None or effective_month is None:
            raise ValidationError(
                "An explicit effective financial period is required for approval."
            )
        if not 1 <= int(effective_month) <= 12:
            raise ValidationError("The effective month must be between 1 and 12.")
        row.status = CurrencyChangeStatus.SCHEDULED.value
        row.effective_year = int(effective_year)
        row.effective_month = int(effective_month)
        action = AuditAction.CURRENCY_CHANGE_APPROVED
    else:
        row.status = CurrencyChangeStatus.REJECTED.value
        action = AuditAction.CURRENCY_CHANGE_REJECTED

    row.decided_by_id = user.id
    row.decided_at = utcnow()
    row.decision_note = note
    db.add(row)
    db.commit()
    db.refresh(row)
    audit_service.record(
        db, action=action, actor_user_id=user.id,
        entity_type="currency_change_request", entity_id=row.id, company_id=row.company_id,
        ip_address=ip_address, user_agent=user_agent,
        metadata={"effective_year": row.effective_year, "effective_month": row.effective_month,
                  "note": note},
    )
    _notify_requester(db, row=row, approve=approve)
    return row


def apply_change(
    db: Session,
    *,
    user: User,
    request_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> CurrencyChangeRequest:
    """Apply an approved change once its effective period has begun.

    The company's base currency is updated; every historical row is left in its
    original currency. Application before the effective period is refused, so
    the change can never reinterpret a closed period.
    """
    require_permission(user, Perm.CURRENCY_CHANGE_APPROVE)
    row = db.get(CurrencyChangeRequest, request_id)
    if row is None:
        raise NotFoundError("Currency-change request not found.")
    if row.status != CurrencyChangeStatus.SCHEDULED.value:
        raise ConflictError("Only an approved, scheduled change can be applied.")
    if row.effective_year is None or row.effective_month is None:
        raise ConflictError("The change has no effective period.")

    today = utcnow().date()
    if (row.effective_year, row.effective_month) > (today.year, today.month):
        raise ConflictError(
            "The effective financial period has not begun yet; the change "
            "cannot be applied retroactively or early."
        )

    company = _require_company(db, row.company_id)
    company.currency = row.requested_currency
    db.add(company)
    row.status = CurrencyChangeStatus.APPLIED.value
    row.applied_at = utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    audit_service.record(
        db, action=AuditAction.CURRENCY_CHANGE_APPLIED, actor_user_id=user.id,
        entity_type="currency_change_request", entity_id=row.id, company_id=row.company_id,
        ip_address=ip_address, user_agent=user_agent,
        metadata={"currency": row.requested_currency,
                  "effective_year": row.effective_year,
                  "effective_month": row.effective_month},
    )
    _notify_requester(db, row=row, approve=True)
    return row


def list_requests(
    db: Session, *, user: User, company_id: int | None = None, status: str | None = None
) -> list[CurrencyChangeRequest]:
    require_permission(user, Perm.CURRENCY_CHANGE_READ)
    stmt = select(CurrencyChangeRequest).order_by(CurrencyChangeRequest.id.desc())
    allowed = accessible_company_ids(user)
    if allowed is not None:
        if not allowed:
            return []
        stmt = stmt.where(CurrencyChangeRequest.company_id.in_(allowed))
    if company_id is not None:
        stmt = stmt.where(CurrencyChangeRequest.company_id == company_id)
    if status is not None:
        stmt = stmt.where(CurrencyChangeRequest.status == status)
    return list(db.execute(stmt).scalars())


def serialise_request(r: CurrencyChangeRequest) -> dict:
    return {
        "id": r.id,
        "company_id": r.company_id,
        "current_currency": r.current_currency,
        "requested_currency": r.requested_currency,
        "justification": r.justification,
        "status": r.status,
        "effective_year": r.effective_year,
        "effective_month": r.effective_month,
        "requested_by_id": r.requested_by_id,
        "reviewed_by_id": r.reviewed_by_id,
        "reviewed_at": r.reviewed_at,
        "review_note": r.review_note,
        "decided_by_id": r.decided_by_id,
        "decided_at": r.decided_at,
        "decision_note": r.decision_note,
        "applied_at": r.applied_at,
        "created_at": r.created_at,
    }


def _notify_reviewers(db: Session, *, row: CurrencyChangeRequest) -> None:
    try:
        from backend.services import notification_service

        reviewer_ids = notification_service.users_with_role(db, role_code="accountant")
        if not reviewer_ids:
            return
        notification_service.notify(
            db, recipient_ids=reviewer_ids, type="currency_change.submitted",
            title_ar="طلب تغيير العملة الأساسية بانتظار المراجعة",
            title_en="A base-currency change awaits review",
            message_ar=(
                f"طلب تغيير العملة من {row.current_currency} إلى "
                f"{row.requested_currency}. السبب: {row.justification}"
            ),
            message_en=(
                f"Requested change from {row.current_currency} to "
                f"{row.requested_currency}. Justification: {row.justification}"
            ),
            priority="high", company_id=row.company_id,
            entity_type="currency_change_request", entity_id=row.id,
            dedupe_key=f"currency_change_review:{row.id}", emit_webhook=False,
        )
    except Exception:  # noqa: BLE001
        pass


def _notify_owner(db: Session, *, row: CurrencyChangeRequest, kind: str) -> None:
    try:
        from backend.services import notification_service

        owner_ids = notification_service.users_with_role(db, role_code="holding_owner")
        if not owner_ids:
            return
        notification_service.notify(
            db, recipient_ids=owner_ids, type="currency_change.submitted",
            title_ar="طلب تغيير العملة الأساسية بانتظار الاعتماد",
            title_en="A base-currency change awaits approval",
            message_ar=(
                f"راجع المحاسب طلب تغيير العملة من {row.current_currency} إلى "
                f"{row.requested_currency}. القرار مطلوب."
            ),
            message_en=(
                f"The accountant reviewed the change from {row.current_currency} to "
                f"{row.requested_currency}. Your decision is required."
            ),
            priority="high", company_id=row.company_id,
            entity_type="currency_change_request", entity_id=row.id,
            dedupe_key=f"currency_change_owner:{row.id}", emit_webhook=False,
        )
    except Exception:  # noqa: BLE001
        pass


def _notify_requester(db: Session, *, row: CurrencyChangeRequest, approve: bool) -> None:
    try:
        from backend.services import notification_service

        if not row.requested_by_id:
            return
        notification_service.notify(
            db, recipient_ids=[row.requested_by_id], type="currency_change.decided",
            title_ar=("تم اعتماد تغيير العملة" if approve else "تم رفض تغيير العملة"),
            title_en=("Currency change approved" if approve else "Currency change rejected"),
            message_ar=(
                f"قرار طلب تغيير العملة ({row.current_currency} -> "
                f"{row.requested_currency}): {'اعتماد' if approve else 'رفض'}."
            ),
            message_en=(
                f"Decision on the currency change ({row.current_currency} -> "
                f"{row.requested_currency}): {'approved' if approve else 'rejected'}."
            ),
            priority="normal", company_id=row.company_id,
            entity_type="currency_change_request", entity_id=row.id,
            dedupe_key=f"currency_change_decided:{row.id}", emit_webhook=False,
        )
    except Exception:  # noqa: BLE001
        pass


__all__ = [
    "PENDING_TRANSITION_ITEMS",
    "apply_change",
    "decide_change",
    "list_requests",
    "request_change",
    "review_change",
    "serialise_request",
]
