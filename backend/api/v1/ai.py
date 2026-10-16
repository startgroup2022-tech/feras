"""AI endpoints: Holding AI and Company AI.

Both routes delegate to :mod:`backend.services.ai_service`, which enforces
company isolation *before* any context is assembled or passed to a provider.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request

from backend.api.deps import CurrentUser, DbSession
from backend.db.models.enums import AIScope
from backend.rbac.authorization import has_permission
from backend.rbac.permissions import Perm
from backend.schemas import AIAskRequest, AIAskResponse, AIInsightOut, AIMessageOut
from backend.services import ai_service, audit_service, insights_service

router = APIRouter(prefix="/ai", tags=["ai"])


def _period(request: Request) -> tuple[int, int]:
    now = datetime.now(timezone.utc)
    year = request.query_params.get("year")
    month = request.query_params.get("month")
    return (
        int(year) if year else now.year,
        int(month) if month else now.month,
    )


def _run(request: Request, user, db, payload: AIAskRequest, scope: str) -> AIAskResponse:
    year, month = _period(request)
    ctx = audit_service.request_context(request)
    result = ai_service.ask(
        db,
        user=user,
        question=payload.question,
        scope=scope,
        year=year,
        month=month,
        company_id=payload.company_id,
        conversation_id=payload.conversation_id,
        ip_address=ctx["ip_address"],
        user_agent=ctx["user_agent"],
    )
    return AIAskResponse(
        conversation_id=result["conversation_id"],
        scope=result["scope"],
        company_id=result["company_id"],
        answer=result["answer"],
        grounded_on_company_ids=result["grounded_on_company_ids"],
        provider=result["provider"],
        grounded=result["grounded"],
        ungrounded_numbers=result["ungrounded_numbers"],
        message=AIMessageOut.model_validate(result["message"]),
    )


@router.post("/holding", response_model=AIAskResponse)
def ask_holding(
    payload: AIAskRequest, request: Request, user: CurrentUser, db: DbSession
) -> AIAskResponse:
    """Ask Holding AI a question about group performance."""
    return _run(request, user, db, payload, AIScope.HOLDING.value)


@router.post("/company", response_model=AIAskResponse)
def ask_company(
    payload: AIAskRequest, request: Request, user: CurrentUser, db: DbSession
) -> AIAskResponse:
    """Ask Company AI a question about one company. Isolation is enforced."""
    return _run(request, user, db, payload, AIScope.COMPANY.value)


@router.get("/insights", response_model=list[AIInsightOut])
def insights(
    request: Request, user: CurrentUser, db: DbSession
) -> list[AIInsightOut]:
    """The four data-driven executive insights for the period.

    Each insight is computed from the database; when the data is insufficient
    the entry states so explicitly rather than inventing an observation.
    """
    if not (
        has_permission(user, Perm.DASHBOARD_HOLDING)
        or has_permission(user, Perm.DASHBOARD_COMPANY)
    ):
        from backend.core.errors import PermissionDeniedError

        raise PermissionDeniedError("You do not have access to insights.")

    year, month = _period(request)
    rows = insights_service.build_insights(db, user=user, year=year, month=month)
    return [AIInsightOut(**row) for row in rows]
