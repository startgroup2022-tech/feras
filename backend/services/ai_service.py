"""AI foundation: context assembly with enforced data isolation.

The critical property of this module is *ordering*:

1. Determine the caller's permitted company scope from the database.
2. Build the context payload using only that scope.
3. Only then hand the payload to a provider.

A provider therefore never receives data the caller could not have read
directly. There is no code path that accepts a company id from the request and
passes it to the provider without first passing through
:func:`backend.rbac.authorization.require_company_access`.

Provider status
---------------
No provider is wired in Phase 1. ``AI_PROVIDER=none`` selects
:class:`NullProvider`, which returns a deterministic, *grounded* summary built
only from real database values (counts and totals). It never invents a number:
every figure in its output comes from a query. When a real provider is added in
Phase 2 it implements the same :class:`AIProvider` interface, so nothing above
this layer changes.
"""

from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy.orm import Session

from backend.ai import AIAnswer, AIProvider, find_ungrounded, get_provider
from backend.ai.base import PaidModelError, ProviderError
from backend.core.config import settings
from backend.core.errors import NotFoundError, RateLimitError
from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import AIUsageOutcome, AIScope, ReportStatus
from backend.db.models.ai import AIConversation, AIMessage
from backend.db.models.identity import User
from backend.rbac.authorization import require_company_access, require_permission
from backend.rbac.permissions import Perm
from backend.repositories.scoped import (
    CompanyRepository,
    MonthlyReportRepository,
    SupportRequestRepository,
)
from backend.services import (
    ai_usage_service,
    audit_service,
    dashboard_service,
    knowledge_service,
)


# --------------------------------------------------------------------------
# context assembly -- isolation happens BEFORE this is called
# --------------------------------------------------------------------------
def _company_payload(company) -> dict:
    return {
        "id": company.id,
        "code": company.code,
        "name_ar": company.name_ar,
        "name_en": company.name_en,
        "sector": company.sector,
        "health": company.health,
    }


def build_holding_context(db: Session, user: User, year: int, month: int) -> dict:
    """Group-level context for Holding AI, limited to what the user may read."""
    data = dashboard_service.build_dashboard(db, user=user, year=year, month=month)
    if data.get("__not_found__"):
        raise NotFoundError("Scope not found.")
    return {
        "scope": "holding",
        "period": {"year": year, "month": month},
        "kpis": {k: (float(v) if isinstance(v, Decimal) else v) for k, v in data["kpis"].items()},
        "companies": [_company_payload(c) for c in data["companies"]],
        "companies_missing_report": [
            _company_payload(c) for c in data["companies_missing_report"]
        ],
        "companies_requiring_attention": data["companies_requiring_attention"],
        "change_vs_previous": {
            k: (float(v) if isinstance(v, Decimal) else v)
            for k, v in data["change_vs_previous"].items()
        },
    }


def build_company_context(
    db: Session, user: User, company_id: int, year: int, month: int
) -> dict:
    """Company context. Raises before any data is read if access is denied."""
    require_company_access(user, company_id)

    company = CompanyRepository(db).get_for_user(user, company_id)
    if company is None:
        raise NotFoundError("Company not found.")

    reports = MonthlyReportRepository(db).list_for_user(
        user, company_id=company_id, year=year
    )
    report = next(
        (r for r in reports if r.period_month == month), None
    )
    support = SupportRequestRepository(db).list_for_user(user, company_id=company_id)

    data = dashboard_service.build_dashboard(
        db, user=user, year=year, month=month, company_id=company_id
    )

    return {
        "scope": "company",
        "period": {"year": year, "month": month},
        "kpis": {
            k: (float(v) if isinstance(v, Decimal) else v)
            for k, v in data["kpis"].items()
        },
        "companies": [_company_payload(company)],
        "companies_missing_report": [],
        "report_status": report.status if report else None,
        "major_problems": report.major_problems if report else None,
        "support_required": report.support_required if report else None,
        "open_support_requests": sum(
            1 for s in support if s.status in ("new", "in_progress")
        ),
        # Never include another company's identifier here.
        "grounded_on_company_ids": [company.id],
    }


# --------------------------------------------------------------------------
# conversation handling
# --------------------------------------------------------------------------
def ask(
    db: Session,
    *,
    user: User,
    question: str,
    scope: str,
    year: int,
    month: int,
    company_id: int | None = None,
    conversation_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    """Answer a question within an enforced scope.

    Isolation is applied *before* the provider is reached, in every scope: the
    holding/company contexts are built from scoped dashboard reads, and the
    knowledge context is retrieved with the sensitivity and company filters in
    SQL. A provider therefore never sees data the caller could not have read.
    """
    if scope == AIScope.HOLDING.value:
        require_permission(user, Perm.AI_HOLDING)
        context = build_holding_context(db, user, year, month)
    elif scope == AIScope.COMPANY.value:
        require_permission(user, Perm.AI_COMPANY)
        if company_id is None:
            from backend.core.errors import ValidationError

            raise ValidationError("company_id is required for company-scoped AI.")
        context = build_company_context(db, user, company_id, year, month)
    elif scope == AIScope.KNOWLEDGE.value:
        require_permission(user, Perm.AI_KNOWLEDGE_ASK)
        if company_id is not None:
            # Narrow to one company, but only one the caller may access.
            require_company_access(user, company_id)
        context = knowledge_service.build_knowledge_context(
            db, user, question=question, company_id=company_id
        )
    else:
        from backend.core.errors import ValidationError

        raise ValidationError("Unknown AI scope.")

    conversation = _resolve_conversation(
        db,
        user=user,
        scope=scope,
        company_id=company_id,
        conversation_id=conversation_id,
        question=question,
    )

    db.add(
        AIMessage(conversation_id=conversation.id, role="user", content=question)
    )
    db.commit()

    result, provider_name, degraded = _run_provider(db, user=user, question=question, context=context)

    # Verify the answer against the scoped context before it reaches the user.
    ungrounded = find_ungrounded(result.text, context)

    grounded = context.get("grounded_on_company_ids") or [
        c["id"] for c in context.get("companies", [])
    ]
    message = AIMessage(
        conversation_id=conversation.id,
        role="assistant",
        content=result.text,
        context_company_ids=json.dumps(grounded),
        model=result.model or settings.AI_MODEL or result.provider,
    )
    db.add(message)
    db.commit()
    db.refresh(message)

    audit_service.record(
        db,
        action=AuditAction.AI_MESSAGE_SENT,
        actor_user_id=user.id,
        entity_type="ai_conversation",
        entity_id=conversation.id,
        company_id=company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={
            "scope": scope,
            "grounded_on": grounded,
            "provider": provider_name,
            "degraded": degraded,
            "grounded": result.grounded and not ungrounded,
        },
    )

    return {
        "conversation_id": conversation.id,
        "scope": scope,
        "company_id": company_id,
        "answer": result.text,
        "grounded_on_company_ids": grounded,
        "provider": provider_name,
        "grounded": not ungrounded,
        "ungrounded_numbers": ungrounded,
        "message": message,
        "degraded": degraded,
        "sources": context.get("knowledge", []) if scope == AIScope.KNOWLEDGE.value else [],
    }


def _run_provider(
    db: Session, *, user: User, question: str, context: dict
) -> tuple[AIAnswer, str, bool]:
    """Run the configured provider under the application-level limits.

    Returns ``(answer, provider_name, degraded)``. ``degraded`` is True when the
    deterministic provider was used because the configured one was unavailable,
    refused a non-free model, or the daily ceiling was reached -- so the caller
    and the audit trail can always tell whether a real model answered.
    """
    from backend.ai.providers import NullProvider

    provider = get_provider()
    provider_name = provider.name

    # The deterministic provider is offline and free; it is never rate limited
    # and never metered.
    if provider_name == "none":
        return provider.answer(question=question, context=context), provider_name, False

    if ai_usage_service.rate_limit_exceeded(db, user):
        raise RateLimitError(
            "You have reached the AI request limit for now. Please try again later."
        )

    if ai_usage_service.daily_budget_exceeded(db):
        ai_usage_service.record_usage(
            db,
            user_id=user.id,
            provider=provider_name,
            model=settings.OPENROUTER_MODEL or "",
            outcome=AIUsageOutcome.BLOCKED_BUDGET.value,
            detail="daily ceiling reached",
        )
        return NullProvider().answer(question=question, context=context), "none", True

    try:
        result = provider.answer(question=question, context=context)
    except PaidModelError as exc:
        # A refusal, not an outage: record it distinctly, then degrade.
        ai_usage_service.record_usage(
            db,
            user_id=user.id,
            provider=provider_name,
            model=settings.OPENROUTER_MODEL or "",
            outcome=AIUsageOutcome.REJECTED_PAID.value,
            is_free=False,
            detail=str(exc)[:400],
        )
        audit_service.record(
            db,
            action=AuditAction.AI_PROVIDER_REJECTED_PAID_MODEL,
            actor_user_id=user.id,
            entity_type="ai_provider",
            metadata={"provider": provider_name, "detail": str(exc)[:200]},
        )
        return NullProvider().answer(question=question, context=context), "none", True
    except ProviderError as exc:
        ai_usage_service.record_usage(
            db,
            user_id=user.id,
            provider=provider_name,
            model=settings.OPENROUTER_MODEL or "",
            outcome=_error_outcome(exc),
            detail=str(exc)[:400],
        )
        return NullProvider().answer(question=question, context=context), "none", True

    ai_usage_service.record_usage(
        db,
        user_id=user.id,
        provider=provider_name,
        model=result.model or settings.OPENROUTER_MODEL or provider_name,
        outcome=AIUsageOutcome.SUCCESS.value,
        tokens_used=result.tokens_used,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
        is_free=result.cost_usd == 0,
    )
    return result, provider_name, False


def _error_outcome(exc: ProviderError) -> str:
    message = str(exc).lower()
    if "rate" in message or "429" in message:
        return AIUsageOutcome.RATE_LIMITED.value
    if "timeout" in message or "timed out" in message:
        return AIUsageOutcome.TIMEOUT.value
    return AIUsageOutcome.PROVIDER_ERROR.value


def _resolve_conversation(
    db: Session,
    *,
    user: User,
    scope: str,
    company_id: int | None,
    conversation_id: int | None,
    question: str,
) -> AIConversation:
    if conversation_id is not None:
        conversation = db.get(AIConversation, conversation_id)
        # A conversation is readable only by its owner, and its scope/company
        # must match the requested scope so it cannot be used to pivot.
        if (
            conversation is None
            or conversation.user_id != user.id
            or conversation.scope != scope
            or conversation.company_id != company_id
        ):
            raise NotFoundError("Conversation not found.")
        return conversation

    conversation = AIConversation(
        scope=scope,
        company_id=company_id,
        user_id=user.id,
        title=question[:120],
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    audit_service.record(
        db,
        action=AuditAction.AI_CONVERSATION_STARTED,
        actor_user_id=user.id,
        entity_type="ai_conversation",
        entity_id=conversation.id,
        company_id=company_id,
        metadata={"scope": scope},
    )
    return conversation
