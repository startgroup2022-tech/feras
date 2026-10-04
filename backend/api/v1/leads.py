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
    LeadOut,
    LeadStatsOut,
    LeadUpdateRequest,
    OpportunityReviewRequest,
    PageOut,
)
from backend.services import audit_service, website_lead_service

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
