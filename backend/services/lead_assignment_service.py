"""D03: lead assignment and reassignment with a mandatory, audited reason.

Only the Holding Owner and the Business Development Manager may assign or
reassign a lead (``website_lead.assign``). Every change writes an append-only
``LeadAssignment`` row carrying the previous assignee, the new assignee, the
actor, the timestamp and the reason, so the distribution history can never be
rewritten. A reassignment (the assignee actually changes) *requires* a reason;
the first assignment may omit one.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.errors import NotFoundError, ValidationError
from backend.db.models.audit_actions import AuditAction
from backend.db.models.governance import LeadAssignment
from backend.db.models.identity import Company, User, UserCompanyAccess
from backend.db.models.website import WebsiteLead
from backend.rbac.authorization import require_company_access, require_permission
from backend.rbac.permissions import Perm
from backend.services import audit_service, website_lead_service


def assign_lead(
    db: Session,
    *,
    user: User,
    lead_id: int,
    reason: str | None = None,
    assignee_id: int | None = None,
    company_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> WebsiteLead:
    """Assign or reassign a lead, recording an immutable history row.

    ``assignee_id`` (a responsible person) and ``company_id`` (the company the
    lead is routed to) are both optional, but at least one must be supplied. If
    the assignee or company actually changes, a reason is required.
    """
    require_permission(user, Perm.LEAD_ASSIGN)
    lead = website_lead_service.get_lead(db, user=user, lead_id=lead_id)

    if assignee_id is None and company_id is None:
        raise ValidationError("Provide an assignee, a company, or both.")

    if company_id is not None:
        company = db.get(Company, company_id)
        if company is None:
            raise NotFoundError("Company not found.")
        # Routing a lead to a company exposes it to that company, so it is a
        # write to that company.
        require_company_access(user, company_id, write=True)

    new_assignee: User | None = None
    if assignee_id is not None:
        new_assignee = db.get(User, assignee_id)
        if new_assignee is None or not new_assignee.is_active:
            raise NotFoundError("Assignee not found.")

    previous_assignee_id = lead.assigned_to_id
    previous_company_id = lead.routed_company_id
    assignee_changed = (
        assignee_id is not None and assignee_id != previous_assignee_id
    )
    company_changed = company_id is not None and company_id != previous_company_id
    is_reassignment = (previous_assignee_id is not None or previous_company_id is not None) and (
        assignee_changed or company_changed
    )

    if is_reassignment and not (reason and reason.strip()):
        raise ValidationError("A reason is required when reassigning a lead.")

    if assignee_id is not None:
        lead.assigned_to_id = assignee_id
    if company_id is not None:
        lead.routed_company_id = company_id
    db.add(lead)

    event = LeadAssignment(
        lead_id=lead.id,
        action="reassign" if is_reassignment else "assign",
        previous_assignee_id=previous_assignee_id,
        new_assignee_id=assignee_id if assignee_id is not None else previous_assignee_id,
        previous_company_id=previous_company_id,
        new_company_id=company_id if company_id is not None else previous_company_id,
        reason=(reason.strip() if reason else None),
        actor_id=user.id,
    )
    db.add(event)
    db.commit()
    db.refresh(lead)

    audit_service.record(
        db,
        action=(AuditAction.LEAD_REASSIGNED if is_reassignment else AuditAction.LEAD_ASSIGNED),
        actor_user_id=user.id, entity_type="website_lead", entity_id=lead.id,
        company_id=lead.routed_company_id, ip_address=ip_address, user_agent=user_agent,
        metadata={
            "previous_assignee_id": previous_assignee_id,
            "new_assignee_id": event.new_assignee_id,
            "previous_company_id": previous_company_id,
            "new_company_id": event.new_company_id,
            "reason": event.reason,
        },
    )
    _notify(db, lead=lead, event=event, actor=user)
    return lead


def list_assignments(
    db: Session, *, user: User, lead_id: int
) -> list[LeadAssignment]:
    """The assignment history of a lead (D03/D04), newest first."""
    require_permission(user, Perm.LEAD_READ)
    # Reuse the lead loader so an out-of-scope lead is a 404, not a leak.
    website_lead_service.get_lead(db, user=user, lead_id=lead_id)
    stmt = (
        select(LeadAssignment)
        .where(LeadAssignment.lead_id == lead_id)
        .order_by(LeadAssignment.id.desc())
    )
    return list(db.execute(stmt).scalars())


def serialise_assignment(a: LeadAssignment) -> dict:
    return {
        "id": a.id,
        "lead_id": a.lead_id,
        "action": a.action,
        "previous_assignee_id": a.previous_assignee_id,
        "previous_assignee_name_ar": a.previous_assignee.full_name_ar if a.previous_assignee else None,
        "new_assignee_id": a.new_assignee_id,
        "new_assignee_name_ar": a.new_assignee.full_name_ar if a.new_assignee else None,
        "previous_company_id": a.previous_company_id,
        "new_company_id": a.new_company_id,
        "reason": a.reason,
        "actor_id": a.actor_id,
        "actor_name_ar": a.actor.full_name_ar if a.actor else None,
        "created_at": a.created_at,
    }


def _notify(db: Session, *, lead: WebsiteLead, event: LeadAssignment, actor: User) -> None:
    """Tell the new assignee (and the routed company's managers) about it."""
    try:
        from backend.services import notification_service

        recipients: set[int] = set()
        if event.new_assignee_id:
            recipients.add(event.new_assignee_id)
        if lead.routed_company_id:
            recipients |= set(
                db.execute(
                    select(UserCompanyAccess.user_id).where(
                        UserCompanyAccess.company_id == lead.routed_company_id,
                        UserCompanyAccess.can_read.is_(True),
                    )
                ).scalars()
            )
        recipients.discard(actor.id)
        if not recipients:
            return
        label = "reassigned" if event.action == "reassign" else "assigned"
        notification_service.notify(
            db, recipient_ids=list(recipients), type="lead.assigned",
            title_ar=("إعادة توزيع عميل محتمل" if event.action == "reassign"
                      else "توزيع عميل محتمل"),
            title_en=(f"Lead {label}"),
            message_ar=(
                f"تم {'إعادة ' if event.action == 'reassign' else ''}توزيع العميل "
                f"{lead.reference}. السبب: {event.reason or '—'}"
            ),
            message_en=(
                f"Lead {lead.reference} was {label}. Reason: {event.reason or '—'}"
            ),
            priority="normal", company_id=lead.routed_company_id,
            entity_type="website_lead", entity_id=lead.id,
            dedupe_key=f"lead_assignment:{event.id}", emit_webhook=False,
        )
    except Exception:  # noqa: BLE001 - a notification must never fail an assignment
        pass


__all__ = ["assign_lead", "list_assignments", "serialise_assignment"]
