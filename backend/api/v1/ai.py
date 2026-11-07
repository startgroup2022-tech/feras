"""AI endpoints: Holding AI and Company AI.

Both routes delegate to :mod:`backend.services.ai_service`, which enforces
company isolation *before* any context is assembled or passed to a provider.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request

from backend.api.deps import CurrentUser, DbSession
from backend.core.config import settings
from backend.db.models.enums import AIScope
from backend.rbac.authorization import has_permission
from backend.rbac.permissions import Perm
from backend.schemas import (
    AIAskRequest,
    AIAskResponse,
    AIInsightOut,
    AIMessageOut,
    AIProviderStatusOut,
)
from backend.services import (
    ai_service,
    ai_usage_service,
    audit_service,
    insights_service,
)

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
        degraded=result.get("degraded", False),
        sources=result.get("sources", []),
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


@router.post("/knowledge", response_model=AIAskResponse)
def ask_knowledge(
    payload: AIAskRequest, request: Request, user: CurrentUser, db: DbSession
) -> AIAskResponse:
    """Ask a question answered from the curated knowledge base.

    Retrieval is scoped before it runs: the caller only ever matches documents
    their company scope and sensitivity level allow. The answer cites the
    retrieved chunks so it can be audited against its sources.
    """
    return _run(request, user, db, payload, AIScope.KNOWLEDGE.value)


@router.get("/usage", response_model=AIProviderStatusOut)
def usage(
    request: Request, user: CurrentUser, db: DbSession
) -> AIProviderStatusOut:
    """AI provider status and metered usage for the management panel.

    Requires ``ai.admin``. The API key is never returned -- only whether one is
    present. Free-model discovery is attempted live but a failure is reported
    rather than raised, so the panel still renders.
    """
    from backend.ai import get_provider
    from backend.ai.openrouter import OpenRouterProvider

    if not has_permission(user, Perm.AI_ADMIN):
        from backend.core.errors import PermissionDeniedError

        raise PermissionDeniedError("You do not have access to AI administration.")

    provider = get_provider()
    free_models: list[dict] = []
    discovery_error: str | None = None
    verified_free = False

    if isinstance(provider, OpenRouterProvider):
        try:
            free_models = [
                {
                    "id": m.id,
                    "name": m.name,
                    "context_length": m.context_length,
                }
                for m in provider.free_models()
            ]
            verified_free = provider.is_verified_free(provider.configured_model)
        except Exception as exc:  # noqa: BLE001 - reported, never raised to the panel
            discovery_error = str(exc)[:300]

    return AIProviderStatusOut(
        provider=provider.name,
        model=settings.OPENROUTER_MODEL or settings.AI_MODEL or "",
        fallbacks=settings.OPENROUTER_FALLBACK_MODELS.split(",")
        if settings.OPENROUTER_FALLBACK_MODELS
        else [],
        configured=provider.name != "none",
        api_key_present=bool(settings.OPENROUTER_API_KEY or settings.AI_API_KEY),
        base_url=settings.OPENROUTER_BASE_URL,
        max_cost_usd=settings.OPENROUTER_MAX_COST_USD,
        verified_free=verified_free,
        free_models=free_models,
        discovery_error=discovery_error,
        usage=ai_usage_service.summary(db),
        rate_limit={
            "enabled": settings.AI_RATE_LIMIT_ENABLED,
            "requests": settings.AI_RATE_LIMIT_REQUESTS,
            "window_seconds": settings.AI_RATE_LIMIT_WINDOW_SECONDS,
        },
        daily_limit=settings.AI_DAILY_REQUEST_LIMIT,
        daily_used=ai_usage_service.daily_count(db),
    )
