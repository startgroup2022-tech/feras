"""D01: financial-policy governance (propose -> decide -> activate).

The approved workflow is deliberately explicit:

* a holder of ``accounting_policy.propose`` drafts a policy version and
  *proposes* it, giving a mandatory reason and the previous value for
  side-by-side comparison;
* only a holder of ``accounting_policy.approve`` may approve or reject that
  proposal, and only approval *activates* the underlying policy version.

The critical safety property is that no code path -- including a direct API call
-- lets a proposer activate a policy. ``propose`` never touches the policy's
``status``; ``decide`` is the sole place that calls ``accounting_service`` to
approve, and it re-checks ``policy.approve`` before doing so. Every transition
writes an audit row and preserves the prior version, so history is immutable.

Unresolved financial *values* (rates, fiscal-year settings, numbering) are never
invented here: a proposal carries whatever value the proposer typed, and the
decision is what makes it effective. Where a value has not been decided,
callers must report it as pending (see ``PENDING_OWNER_CONFIGURATION``).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.errors import ConflictError, NotFoundError, ValidationError
from backend.db.base import utcnow
from backend.db.models.accounting import AccountingPolicy
from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import PolicyKind, PolicyProposalStatus, PolicyStatus
from backend.db.models.governance import PolicyProposal
from backend.db.models.identity import User
from backend.rbac.authorization import (
    accessible_company_ids,
    require_company_access,
    require_permission,
)
from backend.rbac.permissions import Perm
from backend.services import accounting_service, audit_service

# The financial parameter areas the owner has *not* yet configured. Any caller
# that needs one of these must report it as pending rather than substitute a
# default (spec: "Keep unresolved financial settings marked PENDING OWNER
# CONFIGURATION").
PENDING_OWNER_CONFIGURATION = (
    "depreciation_rate",
    "tax_rate",
    "fiscal_year_start",
    "invoice_numbering",
    "base_currency_conversion_rate",
    "kpi_target_amounts",
)

# Human labels for the register/documentation.
PENDING_LABELS_AR = {
    "depreciation_rate": "معدلات الإهلاك",
    "tax_rate": "النسب الضريبية",
    "fiscal_year_start": "إعدادات السنة المالية",
    "invoice_numbering": "سياسة ترقيم الفواتير",
    "base_currency_conversion_rate": "أسعار تحويل العملات",
    "kpi_target_amounts": "المستهدفات المالية",
}


def _as_decimal(value: str | None) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _prior_effective(db: Session, *, company_id: int | None, kind: str) -> AccountingPolicy | None:
    stmt = select(AccountingPolicy).where(
        AccountingPolicy.kind == kind,
        AccountingPolicy.company_id.is_(None) if company_id is None
        else AccountingPolicy.company_id == company_id,
        AccountingPolicy.status == PolicyStatus.APPROVED.value,
    )
    return db.execute(stmt).scalars().first()


def propose_policy_change(
    db: Session,
    *,
    user: User,
    kind: str,
    reason: str,
    company_id: int | None = None,
    value: Decimal | None = None,
    value_text: str | None = None,
    currency: str | None = None,
    description: str | None = None,
    effective_from: date | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> PolicyProposal:
    """Record an accountant's proposal to change a financial policy.

    A draft policy version is created (inert) and the proposal is attached to
    it. The proposal is ``pending`` until the owner decides. The accountant
    must hold ``accounting_policy.propose``; a company-scoped proposal also
    requires write access to that company.
    """
    require_permission(user, Perm.POLICY_PROPOSE)
    if not reason or not reason.strip():
        raise ValidationError("A proposal reason is required.")
    if kind not in {k.value for k in PolicyKind}:
        raise ValidationError(f"Unknown policy kind: {kind}")
    if company_id is not None:
        require_company_access(user, company_id, write=True)

    # The draft version is created through the existing registry so versioning
    # and validation stay in one place. It stays a draft (inert).
    policy = accounting_service.create_policy(
        db, user=user, kind=kind, company_id=company_id, value=value,
        value_text=value_text, currency=currency, description=description,
        effective_from=effective_from, ip_address=ip_address, user_agent=user_agent,
    )

    prior = _prior_effective(db, company_id=company_id, kind=kind)
    previous_value = None
    if prior is not None:
        previous_value = (
            str(prior.value) if prior.value is not None else (prior.value_text or None)
        )

    proposal = PolicyProposal(
        policy_id=policy.id,
        company_id=company_id,
        kind=kind,
        reason=reason.strip(),
        previous_value=previous_value,
        proposed_value=str(value) if value is not None else None,
        proposed_value_text=value_text,
        proposed_currency=currency,
        proposed_effective_from=effective_from,
        status=PolicyProposalStatus.PENDING.value,
        submitted_by_id=user.id,
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)

    audit_service.record(
        db, action=AuditAction.POLICY_PROPOSED, actor_user_id=user.id,
        entity_type="policy_proposal", entity_id=proposal.id, company_id=company_id,
        ip_address=ip_address, user_agent=user_agent,
        metadata={"kind": kind, "previous_value": previous_value,
                  "proposed_value": proposal.proposed_value, "reason": proposal.reason},
    )
    _notify_owner(db, proposal=proposal, actor=user)
    return proposal


def decide_proposal(
    db: Session,
    *,
    user: User,
    proposal_id: int,
    approve: bool,
    note: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> PolicyProposal:
    """Owner decision on a proposal. Approval activates the policy version.

    This is the *only* place that activates a proposed policy. It requires
    ``accounting_policy.approve`` (owner/super-admin), refuses a proposal that
    is already decided, and on approval calls the existing ``approve_policy`` so
    the prior version is superseded and preserved.
    """
    require_permission(user, Perm.POLICY_APPROVE)
    proposal = db.get(PolicyProposal, proposal_id)
    if proposal is None:
        raise NotFoundError("Proposal not found.")
    if proposal.company_id is not None:
        require_company_access(user, proposal.company_id, write=True)
    if proposal.status != PolicyProposalStatus.PENDING.value:
        raise ConflictError("This proposal has already been decided.")

    if approve:
        policy = db.get(AccountingPolicy, proposal.policy_id) if proposal.policy_id else None
        if policy is None:
            raise NotFoundError("The policy version for this proposal no longer exists.")
        # Activate the policy version (supersedes and preserves the prior one).
        accounting_service.approve_policy(
            db, user=user, policy_id=policy.id,
            ip_address=ip_address, user_agent=user_agent,
        )
        proposal.status = PolicyProposalStatus.APPROVED.value
    else:
        proposal.status = PolicyProposalStatus.REJECTED.value

    proposal.decided_by_id = user.id
    proposal.decided_at = utcnow()
    proposal.decision_note = note
    db.add(proposal)
    db.commit()
    db.refresh(proposal)

    audit_service.record(
        db,
        action=(AuditAction.POLICY_PROPOSAL_APPROVED if approve
                else AuditAction.POLICY_PROPOSAL_REJECTED),
        actor_user_id=user.id, entity_type="policy_proposal", entity_id=proposal.id,
        company_id=proposal.company_id, ip_address=ip_address, user_agent=user_agent,
        metadata={"kind": proposal.kind, "note": note},
    )
    _notify_submitter(db, proposal=proposal, approve=approve)
    return proposal


def list_proposals(
    db: Session,
    *,
    user: User,
    company_id: int | None = None,
    status: str | None = None,
) -> list[PolicyProposal]:
    require_permission(user, Perm.POLICY_READ)
    stmt = select(PolicyProposal).order_by(PolicyProposal.id.desc())
    allowed = accessible_company_ids(user)
    if allowed is not None:
        stmt = stmt.where(
            (PolicyProposal.company_id.is_(None))
            | (PolicyProposal.company_id.in_(allowed))
        )
    if company_id is not None:
        stmt = stmt.where(PolicyProposal.company_id == company_id)
    if status is not None:
        stmt = stmt.where(PolicyProposal.status == status)
    return list(db.execute(stmt).scalars())


def serialise_proposal(p: PolicyProposal) -> dict:
    return {
        "id": p.id,
        "policy_id": p.policy_id,
        "company_id": p.company_id,
        "kind": p.kind,
        "reason": p.reason,
        "previous_value": p.previous_value,
        "proposed_value": p.proposed_value,
        "proposed_value_text": p.proposed_value_text,
        "proposed_currency": p.proposed_currency,
        "proposed_effective_from": p.proposed_effective_from,
        "status": p.status,
        "submitted_by_id": p.submitted_by_id,
        "decided_by_id": p.decided_by_id,
        "decided_at": p.decided_at,
        "decision_note": p.decision_note,
        "created_at": p.created_at,
    }


def _notify_owner(db: Session, *, proposal: PolicyProposal, actor: User) -> None:
    try:
        from backend.services import notification_service

        owner_ids = notification_service.users_with_role(
            db, role_code="holding_owner"
        )
        if not owner_ids:
            return
        notification_service.notify(
            db, recipient_ids=owner_ids, type="policy.proposal_submitted",
            title_ar="مقترح تغيير سياسة مالية بانتظار الاعتماد",
            title_en="A financial-policy change awaits approval",
            message_ar=(
                f"قدّم {actor.full_name_ar} مقترح تغيير على السياسة ({proposal.kind}). "
                f"السبب: {proposal.reason}"
            ),
            message_en=(
                f"{actor.full_name_ar} proposed a change to the {proposal.kind} policy. "
                f"Reason: {proposal.reason}"
            ),
            priority="high",
            company_id=proposal.company_id,
            entity_type="policy_proposal", entity_id=proposal.id,
            dedupe_key=f"policy_proposal:{proposal.id}",
            emit_webhook=False,
        )
    except Exception:  # noqa: BLE001 - a notification must never fail a proposal
        pass


def _notify_submitter(db: Session, *, proposal: PolicyProposal, approve: bool) -> None:
    try:
        from backend.services import notification_service

        if not proposal.submitted_by_id:
            return
        notification_service.notify(
            db, recipient_ids=[proposal.submitted_by_id],
            type="policy.proposal_decided",
            title_ar=("تم اعتماد مقترح السياسة" if approve else "تم رفض مقترح السياسة"),
            title_en=("Policy proposal approved" if approve else "Policy proposal rejected"),
            message_ar=(
                f"قرار المالك على مقترح السياسة ({proposal.kind}): "
                f"{'اعتماد' if approve else 'رفض'}."
            ),
            message_en=(
                f"Owner decision on the {proposal.kind} proposal: "
                f"{'approved' if approve else 'rejected'}."
            ),
            priority="normal",
            company_id=proposal.company_id,
            entity_type="policy_proposal", entity_id=proposal.id,
            dedupe_key=f"policy_proposal_decided:{proposal.id}",
            emit_webhook=False,
        )
    except Exception:  # noqa: BLE001
        pass


__all__ = [
    "PENDING_LABELS_AR",
    "PENDING_OWNER_CONFIGURATION",
    "decide_proposal",
    "list_proposals",
    "propose_policy_change",
    "serialise_proposal",
]
