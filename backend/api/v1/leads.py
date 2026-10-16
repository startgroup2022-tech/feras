"""Internal API for website leads and submitted opportunities.

Lives under ``/api/v1/leads`` and is entirely authenticated and permission
gated -- it is the counterpart to ``/api/v1/public``. Every route requires
``website_lead.read``; mutation requires ``website_lead.manage`` (and
``website_lead.status_change`` / ``website_opportunity.*`` for their specific
actions), so a role can be given visibility without the ability to re-route.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from backend.api.deps import CurrentUser, DbSession, require
from backend.rbac.permissions import Perm
from backend.schemas import (
    LeadNoteCreateRequest,
    LeadNoteOut,
    LeadOut,
    LeadStatsOut,
    LeadUpdateRequest,
    OpportunityReviewRequest,
    PageOut,
)
from backend.schemas.governance import LeadAssignRequest, LeadAssignmentOut
from backend.services import audit_service, lead_assignment_service, website_lead_service

router = APIRouter(prefix="/leads", tags=["website-leads"])


@router.get("", response_model=PageOut)
def list_leads(
    db: DbSession,
    user=Depends(require(Perm.LEAD_READ)),
    market: str | None = Query(default=None),
    service_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    assigned_to_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PageOut:
    return PageOut(
        **website_lead_service.list_leads(
            db,
            user=user,
            market=market,
            service_type=service_type,
            status=status_filter,
            assigned_to_id=assigned_to_id,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/opportunities")
def list_opportunities(
    db: DbSession,
    user=Depends(require(Perm.OPPORTUNITY_REVIEW)),
) -> list[dict]:
    """Submitted listings awaiting review or already reviewed (internal view).

    The public endpoint returns only *published* listings; this one returns the
    review queue, so a reviewer can act on a submission. It is gated by the
    review permission, not by lead visibility.
    """
    return website_lead_service.list_internal_opportunities(db, user=user)


@router.get("/stats", response_model=LeadStatsOut)
def lead_stats(db: DbSession, user=Depends(require(Perm.LEAD_READ))) -> LeadStatsOut:
    """Aggregate funnel counts -- the business metrics the concept asks for."""
    return LeadStatsOut(**website_lead_service.lead_stats(db, user=user))


@router.get("/{lead_id}", response_model=LeadOut)
def get_lead(
    lead_id: int, db: DbSession, user=Depends(require(Perm.LEAD_READ))
) -> LeadOut:
    lead = website_lead_service.get_lead(db, user=user, lead_id=lead_id)
    return LeadOut(**website_lead_service.serialise_lead(lead))


@router.patch("/{lead_id}", response_model=LeadOut)
def update_lead(
    lead_id: int,
    payload: LeadUpdateRequest,
    request: Request,
    db: DbSession,
    user=Depends(require(Perm.LEAD_MANAGE)),
) -> LeadOut:
    ctx = audit_service.request_context(request)
    lead = website_lead_service.update_lead(
        db,
        user=user,
        lead_id=lead_id,
        changes=payload.model_dump(exclude_none=True),
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return LeadOut(**website_lead_service.serialise_lead(lead))


@router.get("/{lead_id}/notes", response_model=list[LeadNoteOut])
def list_lead_notes(
    lead_id: int, db: DbSession, user=Depends(require(Perm.LEAD_READ))
) -> list[LeadNoteOut]:
    """Independent manager notes (S13), newest first. Marketing may read them."""
    rows = website_lead_service.list_lead_notes(db, user=user, lead_id=lead_id)
    return [LeadNoteOut(**row) for row in rows]


@router.post("/{lead_id}/assign", response_model=LeadOut)
def assign_lead(
    lead_id: int,
    payload: LeadAssignRequest,
    request: Request,
    db: DbSession,
    user=Depends(require(Perm.LEAD_ASSIGN)),
) -> LeadOut:
    """Assign or reassign a lead (D03), recording an audited history row."""
    ctx = audit_service.request_context(request)
    lead = lead_assignment_service.assign_lead(
        db,
        user=user,
        lead_id=lead_id,
        assignee_id=payload.assignee_id,
        company_id=payload.company_id,
        reason=payload.reason,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return LeadOut(**website_lead_service.serialise_lead(lead))


@router.get("/{lead_id}/assignments", response_model=list[LeadAssignmentOut])
def list_lead_assignments(
    lead_id: int, db: DbSession, user=Depends(require(Perm.LEAD_READ))
) -> list[LeadAssignmentOut]:
    """The append-only assignment history of a lead (D03/D04), newest first."""
    rows = lead_assignment_service.list_assignments(db, user=user, lead_id=lead_id)
    return [LeadAssignmentOut(**lead_assignment_service.serialise_assignment(r)) for r in rows]


@router.post("/{lead_id}/notes", response_model=LeadNoteOut, status_code=201)
def add_lead_note(
    lead_id: int,
    payload: LeadNoteCreateRequest,
    request: Request,
    db: DbSession,
    user=Depends(require(Perm.LEAD_MANAGER_NOTE)),
) -> LeadNoteOut:
    """Write the manager note. Gated by ``website_lead.manager_note``."""
    ctx = audit_service.request_context(request)
    row = website_lead_service.add_lead_note(
        db,
        user=user,
        lead_id=lead_id,
        body=payload.body,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return LeadNoteOut(**row)


@router.post("/opportunities/{opportunity_id}/review", response_model=dict)
def review_opportunity(
    opportunity_id: int,
    payload: OpportunityReviewRequest,
    request: Request,
    db: DbSession,
    user=Depends(require(Perm.OPPORTUNITY_REVIEW)),
) -> dict:
    ctx = audit_service.request_context(request)
    opportunity = website_lead_service.review_opportunity(
        db,
        user=user,
        opportunity_id=opportunity_id,
        status=payload.status.value,
        publish=payload.publish,
        public_title_ar=payload.public_title_ar,
        public_title_en=payload.public_title_en,
        public_summary_ar=payload.public_summary_ar,
        public_summary_en=payload.public_summary_en,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return {
        "id": opportunity.id,
        "status": opportunity.status,
        "is_public": opportunity.is_public,
        "market": opportunity.market,
        "opportunity_type": opportunity.opportunity_type,
    }
