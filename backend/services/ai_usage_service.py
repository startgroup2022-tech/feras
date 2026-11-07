"""AI usage monitoring and application-level limits.

Two independent protections live here, both stored in the database so they
survive a process restart and are shared across workers:

* **Per-user rate limit** -- a sliding window over ``ai_usage_events``. It stops
  one account from exhausting the group's free quota or hammering an upstream,
  independently of whatever the provider enforces.
* **Group-wide daily ceiling** -- a hard cap on metered calls per UTC day. When
  it is reached the caller degrades to the deterministic provider rather than
  failing, so the executive still gets a grounded answer.

Every provider call is recorded with its outcome, model, tokens, latency and
reported cost -- but never its prompt or answer text. That keeps the monitor an
operational counter, not a second copy of the conversation.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.db.base import utcnow
from backend.db.models.ai import AIUsageEvent
from backend.db.models.enums import AIUsageOutcome
from backend.db.models.identity import User


def record_usage(
    db: Session,
    *,
    user_id: int | None,
    provider: str,
    model: str,
    outcome: str,
    tokens_used: int | None = None,
    cost_usd: float = 0.0,
    latency_ms: int | None = None,
    is_free: bool = True,
    detail: str | None = None,
    commit: bool = True,
) -> AIUsageEvent:
    """Persist one usage event. Never stores prompt or answer text."""
    event = AIUsageEvent(
        user_id=user_id,
        provider=provider,
        model=(model or "")[:120],
        outcome=outcome,
        tokens_used=tokens_used,
        cost_usd=cost_usd or 0,
        latency_ms=latency_ms,
        is_free=is_free,
        detail=(detail or "")[:400] or None,
        created_at=utcnow(),
    )
    db.add(event)
    if commit:
        db.commit()
    return event


def recent_count(db: Session, *, user_id: int, window_seconds: int) -> int:
    since = utcnow() - timedelta(seconds=window_seconds)
    return int(
        db.execute(
            select(func.count(AIUsageEvent.id)).where(
                AIUsageEvent.user_id == user_id,
                AIUsageEvent.created_at >= since,
            )
        ).scalar_one()
    )


def daily_count(db: Session) -> int:
    since = utcnow() - timedelta(days=1)
    return int(
        db.execute(
            select(func.count(AIUsageEvent.id)).where(AIUsageEvent.created_at >= since)
        ).scalar_one()
    )


def rate_limit_exceeded(db: Session, user: User) -> bool:
    """Whether the user has spent their per-window request allowance."""
    if not settings.AI_RATE_LIMIT_ENABLED:
        return False
    return recent_count(
        db, user_id=user.id, window_seconds=settings.AI_RATE_LIMIT_WINDOW_SECONDS
    ) >= settings.AI_RATE_LIMIT_REQUESTS


def daily_budget_exceeded(db: Session) -> bool:
    """Whether the group has hit its daily metered-call ceiling."""
    limit = settings.AI_DAILY_REQUEST_LIMIT
    if limit <= 0:
        return False
    return daily_count(db) >= limit


def summary(db: Session, *, window_hours: int = 24) -> dict:
    """Aggregate usage for the admin panel."""
    since = utcnow() - timedelta(hours=window_hours)
    rows = db.execute(
        select(
            AIUsageEvent.model,
            AIUsageEvent.outcome,
            func.count(AIUsageEvent.id),
            func.coalesce(func.sum(AIUsageEvent.tokens_used), 0),
            func.coalesce(func.sum(AIUsageEvent.cost_usd), 0),
            func.coalesce(func.avg(AIUsageEvent.latency_ms), 0),
        )
        .where(AIUsageEvent.created_at >= since)
        .group_by(AIUsageEvent.model, AIUsageEvent.outcome)
    ).all()

    by_model: dict[str, dict] = {}
    totals = {
        "requests": 0,
        "tokens": 0,
        "cost_usd": 0.0,
        "errors": 0,
        "rejected_paid": 0,
    }
    for model, outcome, count, tokens, cost, avg_latency in rows:
        count = int(count)
        entry = by_model.setdefault(
            model,
            {"model": model, "requests": 0, "tokens": 0, "cost_usd": 0.0,
             "errors": 0, "avg_latency_ms": 0, "outcomes": {}},
        )
        entry["requests"] += count
        entry["tokens"] += int(tokens or 0)
        entry["cost_usd"] += float(cost or 0)
        entry["avg_latency_ms"] = int(avg_latency or 0)
        entry["outcomes"][outcome] = entry["outcomes"].get(outcome, 0) + count
        totals["requests"] += count
        totals["tokens"] += int(tokens or 0)
        totals["cost_usd"] += float(cost or 0)
        if outcome != AIUsageOutcome.SUCCESS.value:
            totals["errors"] += count
        if outcome == AIUsageOutcome.REJECTED_PAID.value:
            totals["rejected_paid"] += count

    return {
        "window_hours": window_hours,
        "totals": totals,
        "by_model": sorted(by_model.values(), key=lambda m: m["requests"], reverse=True),
        "rate_limit": {
            "enabled": settings.AI_RATE_LIMIT_ENABLED,
            "requests": settings.AI_RATE_LIMIT_REQUESTS,
            "window_seconds": settings.AI_RATE_LIMIT_WINDOW_SECONDS,
        },
        "daily_limit": settings.AI_DAILY_REQUEST_LIMIT,
        "daily_used": daily_count(db),
    }
