"""Advanced reporting and analytics endpoints under ``/api/v1/analytics``.

Each report family is gated by its own permission, so the Holding can grant
operational analytics without granting group financials. Every figure is
computed from the caller's company scope, which is applied inside the service
as a SQL filter -- a query parameter can narrow the result but never widen it.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request

from backend.api.deps import CurrentUser, DbSession, require
from backend.db.models.audit_actions import AuditAction
from backend.rbac.permissions import Perm
from backend.schemas import (
    ComplianceReportOut,
    ExecutiveBriefingOut,
    HoldingOverviewOut,
    InvestmentReportOut,
    OperationalReportOut,
)
from backend.services import audit_service, analytics_service, executive_intelligence_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _period(year: int | None, month: int | None) -> tuple[int, int]:
    now = datetime.now(timezone.utc)
    return (year or now.year, month or now.month)


@router.get("/holding", response_model=HoldingOverviewOut)
def holding_overview(
    db: DbSession,
    user=Depends(require(Perm.ANALYTICS_HOLDING)),
    year: int | None = Query(default=None),
    month: int | None = Query(default=None),
) -> HoldingOverviewOut:
    y, m = _period(year, month)
    return HoldingOverviewOut(**analytics_service.holding_overview(db, user=user, year=y, month=m))


@router.get("/operations", response_model=OperationalReportOut)
def operational_report(
    db: DbSession,
    user=Depends(require(Perm.ANALYTICS_OPERATIONS)),
    year: int | None = Query(default=None),
    month: int | None = Query(default=None),
) -> OperationalReportOut:
    y, m = _period(year, month)
    return OperationalReportOut(**analytics_service.operational_report(db, user=user, year=y, month=m))


@router.get("/compliance", response_model=ComplianceReportOut)
def compliance_report(
    db: DbSession,
    user=Depends(require(Perm.ANALYTICS_COMPLIANCE)),
    year: int | None = Query(default=None),
    month: int | None = Query(default=None),
) -> ComplianceReportOut:
    y, m = _period(year, month)
    return ComplianceReportOut(**analytics_service.compliance_report(db, user=user, year=y, month=m))


@router.get("/investments", response_model=InvestmentReportOut)
def investment_report(
    db: DbSession,
    user=Depends(require(Perm.ANALYTICS_HOLDING)),
    year: int | None = Query(default=None),
    month: int | None = Query(default=None),
) -> InvestmentReportOut:
    y, m = _period(year, month)
    return InvestmentReportOut(**analytics_service.investment_report(db, user=user, year=y, month=m))


@router.get("/briefing", response_model=ExecutiveBriefingOut)
def executive_briefing(
    db: DbSession,
    user: CurrentUser,
    request: Request,
    year: int | None = Query(default=None),
    month: int | None = Query(default=None),
) -> ExecutiveBriefingOut:
    """The narrative executive briefing, grounded and permission-shaped.

    Requires one of the analytics permissions; a company-scoped user gets a
    briefing built only from their companies.
    """
    from backend.core.errors import PermissionDeniedError
    from backend.rbac.authorization import has_permission

    if not (
        has_permission(user, Perm.ANALYTICS_HOLDING)
        or has_permission(user, Perm.ANALYTICS_COMPANY)
        or has_permission(user, Perm.ANALYTICS_OPERATIONS)
    ):
        raise PermissionDeniedError("You do not have access to executive intelligence.")

    y, m = _period(year, month)
    result = executive_intelligence_service.executive_briefing(db, user=user, year=y, month=m)
    if result.get("__not_found__"):
        from backend.core.errors import NotFoundError

        raise NotFoundError("Scope not found.")

    ctx = audit_service.request_context(request)
    audit_service.record(
        db,
        action=AuditAction.ANALYTICS_VIEWED,
        actor_user_id=user.id,
        entity_type="executive_briefing",
        company_id=None,
        metadata={"report": "briefing", "provider": result.get("provider")},
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return ExecutiveBriefingOut(**result)
