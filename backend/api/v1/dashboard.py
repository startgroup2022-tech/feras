"""Dashboard endpoints.

Every KPI is computed live from the database. Nothing here is hardcoded and no
demo figure is ever returned in place of real data.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from backend.api.deps import CurrentUser, DbSession
from backend.core.errors import NotFoundError, PermissionDeniedError
from backend.rbac.authorization import has_permission
from backend.rbac.permissions import Perm
from backend.schemas import (
    AttentionCompanyOut,
    CompanyOut,
    DashboardKpis,
    DashboardResponse,
)
from backend.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _default_period() -> tuple[int, int]:
    now = datetime.now(timezone.utc)
    return now.year, now.month


@router.get("/holding", response_model=DashboardResponse)
def holding_dashboard(
    user: CurrentUser,
    db: DbSession,
    year: int | None = None,
    month: int | None = None,
) -> DashboardResponse:
    """Group-level executive dashboard."""
    if not has_permission(user, Perm.DASHBOARD_HOLDING):
        raise PermissionDeniedError("You do not have access to the Holding dashboard.")

    default_year, default_month = _default_period()
    year = year or default_year
    month = month or default_month

    data = dashboard_service.build_dashboard(db, user=user, year=year, month=month)
    return DashboardResponse(
        scope="holding",
        company_id=None,
        period_year=year,
        period_month=month,
        kpis=DashboardKpis(**data["kpis"]),
        companies=[CompanyOut.model_validate(c) for c in data["companies"]],
        companies_missing_report=[
            CompanyOut.model_validate(c) for c in data["companies_missing_report"]
        ],
        companies_requiring_attention=[
            AttentionCompanyOut.model_validate(c)
            for c in data["companies_requiring_attention"]
        ],
    )


@router.get("/company/{company_id}", response_model=DashboardResponse)
def company_dashboard(
    company_id: int,
    user: CurrentUser,
    db: DbSession,
    year: int | None = None,
    month: int | None = None,
) -> DashboardResponse:
    """Dashboard for one company, restricted to the caller's scope."""
    if not (
        has_permission(user, Perm.DASHBOARD_COMPANY)
        or has_permission(user, Perm.DASHBOARD_HOLDING)
    ):
        raise PermissionDeniedError("You do not have access to this dashboard.")

    default_year, default_month = _default_period()
    year = year or default_year
    month = month or default_month

    data = dashboard_service.build_dashboard(
        db, user=user, year=year, month=month, company_id=company_id
    )
    if data.get("__not_found__"):
        # Out of scope and non-existent are reported identically.
        raise NotFoundError("Company not found.")

    return DashboardResponse(
        scope="company",
        company_id=company_id,
        period_year=year,
        period_month=month,
        kpis=DashboardKpis(**data["kpis"]),
        companies=[CompanyOut.model_validate(c) for c in data["companies"]],
        companies_missing_report=[
            CompanyOut.model_validate(c) for c in data["companies_missing_report"]
        ],
        companies_requiring_attention=[
            AttentionCompanyOut.model_validate(c)
            for c in data["companies_requiring_attention"]
        ],
    )
