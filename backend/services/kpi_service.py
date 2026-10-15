"""D02: KPI target-versus-actual evaluation.

The owner decision D02 requires manageable KPIs per company "with a defined
data source, calculation method and period". The companion directive is
explicit that the *business* definition must not be invented: a KPI's target
or source is meaningless until an authorised person approves it. So this module
splits the two concerns:

* **Configuration** (target, metric binding, direction, period) can be recorded
  at any time through ``KpiDefinition`` — it is inert data.
* **Activation** is a separate, audited, permissioned step. Until a definition
  is activated its actual/target are reported as ``None`` and it never counts
  as a live KPI.

The actual value is never stored on the definition (that would be a second copy
of a figure the dashboard already computes). It is resolved live from the same
source records the dashboard uses, through ``METRIC_RESOLVERS``. This is what
makes the comparison reproducible and the drill-down truthful: the number and
its source records always come from the same query.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.errors import NotFoundError, ValidationError
from backend.db.models.accounting import KpiDefinition
from backend.db.models.enums import KpiDirection
from backend.db.models.identity import User
from backend.db.models.audit_actions import AuditAction
from backend.rbac.authorization import (
    accessible_company_ids,
    require_company_access,
    require_permission,
)
from backend.rbac.permissions import Perm
from backend.services import audit_service, dashboard_service

# A metric_key names a value the dashboard already computes for a period. The
# resolver returns a Decimal for the caller's scope. Keeping this registry in
# one place means a KPI, the dashboard tile and the drill-down can never drift.
METRIC_KEYS = (
    "total_revenue",
    "total_expenses",
    "total_net_result",
    "reports_submitted",
    "reports_missing",
    "companies_requiring_attention",
    "open_support_requests",
    "pending_financial_reviews",
)


def _metrics(db: Session, user: User, company_id: int | None, year: int, month: int) -> dict[str, Decimal]:
    payload = dashboard_service.build_dashboard(
        db, user=user, year=year, month=month, company_id=company_id
    )
    if payload.get("__not_found__"):
        raise NotFoundError("Company not found.")
    return {k: Decimal(str(v)) if not isinstance(v, Decimal) else v
            for k, v in payload["kpis"].items()}


def resolve_actual(
    db: Session, *, user: User, kpi: KpiDefinition, year: int, month: int
) -> Decimal | None:
    """The live actual for a KPI, or ``None`` when it is inert/unbound."""
    if not kpi.is_active or not kpi.metric_key:
        return None
    metrics = _metrics(db, user, kpi.company_id, year, month)
    if kpi.metric_key not in metrics:
        return None
    return metrics[kpi.metric_key]


def _evaluate(kpi: KpiDefinition, actual: Decimal | None, year: int, month: int) -> dict:
    """Target-vs-actual with a favourable-signed variance.

    ``variance`` is ``actual - target`` adjusted by the definition's direction,
    so a positive variance always means "better" regardless of whether the
    metric is revenue (up is good) or a cost (down is good). ``None`` is
    returned wherever a figure is unknown — an unapproved or unbound KPI never
    produces a number.
    """
    target = kpi.target_value
    variance: Decimal | None = None
    variance_pct: float | None = None
    favourable: bool | None = None
    if actual is not None and target is not None:
        raw = actual - target
        variance = raw if kpi.direction == KpiDirection.UP.value else -raw
        favourable = variance >= 0
        if target != 0:
            variance_pct = round(float(raw / target * 100), 1)

    return {
        "id": kpi.id,
        "company_id": kpi.company_id,
        "code": kpi.code,
        "name_ar": kpi.name_ar,
        "name_en": kpi.name_en,
        "unit": kpi.unit,
        "period_label": kpi.period_label,
        "period_year": year,
        "period_month": month,
        "metric_key": kpi.metric_key,
        "direction": kpi.direction,
        "target_value": target,
        "actual_value": actual,
        "variance": variance,
        "variance_pct": variance_pct,
        "favourable": favourable,
        "is_active": kpi.is_active,
        "approved_at": kpi.approved_at,
        # An inert (unapproved/unbound) definition is shown as "pending" rather
        # than presented as a real target.
        "status": "active" if (kpi.is_active and kpi.target_value is not None) else "pending",
    }


def list_evaluations(
    db: Session, *, user: User, company_id: int | None, year: int, month: int
) -> list[dict]:
    """Every KPI visible to the caller, evaluated for the period.

    Scoped exactly like ``list_kpis``: holding-wide rows plus the caller's own
    companies. A definition bound to a company the caller cannot see is never
    returned, so a KPI cannot become a side channel for another company's data.
    """
    require_permission(user, Perm.KPI_READ)
    stmt = select(KpiDefinition).order_by(KpiDefinition.code)
    allowed = accessible_company_ids(user)
    if allowed is not None:
        stmt = stmt.where(
            (KpiDefinition.company_id.is_(None)) | (KpiDefinition.company_id.in_(allowed))
        )
    if company_id is not None:
        if company_id not in (allowed if allowed is not None else [company_id]):
            raise NotFoundError("Company not found.")
        stmt = stmt.where(KpiDefinition.company_id == company_id)

    out: list[dict] = []
    for kpi in db.execute(stmt).scalars():
        actual = resolve_actual(db, user=user, kpi=kpi, year=year, month=month)
        out.append(_evaluate(kpi, actual, year, month))
    return out


def evaluate_sources(
    db: Session, *, user: User, kpi_id: int, year: int, month: int
) -> dict:
    """The source records behind a KPI's actual (drill-down, no copy).

    Reuses the dashboard's indicator drill-down so the record links a KPI shows
    are the same records the dashboard shows, read through the caller's scope.
    """
    require_permission(user, Perm.KPI_READ)
    kpi = db.get(KpiDefinition, kpi_id)
    if kpi is None:
        raise NotFoundError("KPI not found.")
    if kpi.company_id is not None:
        require_company_access(user, kpi.company_id)

    actual = resolve_actual(db, user=user, kpi=kpi, year=year, month=month)
    evaluation = _evaluate(kpi, actual, year, month)
    sources: list[dict] = []
    if kpi.metric_key:
        found = dashboard_service.indicator_sources(
            db, user=user, indicator=kpi.metric_key, year=year, month=month
        )
        sources = found or []
    evaluation["sources"] = sources
    return evaluation


# --------------------------------------------------------------------------
# configuration lifecycle (record / approve / activate)
# --------------------------------------------------------------------------
def update_kpi(
    db: Session,
    *,
    user: User,
    kpi_id: int,
    target_value: Decimal | None = None,
    metric_key: str | None = None,
    direction: str | None = None,
    name_en: str | None = None,
    unit: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> KpiDefinition:
    """Record configuration on a KPI. Never changes the active state."""
    require_permission(user, Perm.KPI_MANAGE)
    kpi = db.get(KpiDefinition, kpi_id)
    if kpi is None:
        raise NotFoundError("KPI not found.")
    if kpi.company_id is not None:
        require_company_access(user, kpi.company_id, write=True)
    if metric_key is not None and metric_key not in METRIC_KEYS:
        raise ValidationError(f"Unknown metric_key: {metric_key}")
    if direction is not None and direction not in {d.value for d in KpiDirection}:
        raise ValidationError("direction must be 'up' or 'down'.")

    if target_value is not None:
        kpi.target_value = target_value
    if metric_key is not None:
        kpi.metric_key = metric_key or None
    if direction is not None:
        kpi.direction = direction
    if name_en is not None:
        kpi.name_en = name_en
    if unit is not None:
        kpi.unit = unit
    db.commit()
    db.refresh(kpi)
    audit_service.record(
        db, action=AuditAction.KPI_UPDATED, actor_user_id=user.id,
        entity_type="kpi_definition", entity_id=kpi.id, company_id=kpi.company_id,
        ip_address=ip_address, user_agent=user_agent,
        metadata={"metric_key": kpi.metric_key, "target_value": str(kpi.target_value),
                  "direction": kpi.direction},
    )
    return kpi


def set_active(
    db: Session,
    *,
    user: User,
    kpi_id: int,
    active: bool,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> KpiDefinition:
    """Activate (approve) or deactivate a KPI.

    Activation *is* the approval record: it stamps ``approved_by_id`` /
    ``approved_at`` and writes an audit row. This exists precisely so an owner
    approval can be recorded without inventing one in the code — the workflow is
    ready, and stays inert until a human invokes it.
    """
    require_permission(user, Perm.KPI_MANAGE)
    kpi = db.get(KpiDefinition, kpi_id)
    if kpi is None:
        raise NotFoundError("KPI not found.")
    if kpi.company_id is not None:
        require_company_access(user, kpi.company_id, write=True)

    if active:
        if kpi.metric_key is None or kpi.target_value is None:
            raise ValidationError(
                "A KPI needs a target and a metric binding before it can be activated."
            )
        kpi.is_active = True
        kpi.approved_by_id = user.id
        from datetime import datetime, timezone

        kpi.approved_at = datetime.now(timezone.utc)
        action = AuditAction.KPI_ACTIVATED
    else:
        kpi.is_active = False
        action = AuditAction.KPI_DEACTIVATED

    db.commit()
    db.refresh(kpi)
    audit_service.record(
        db, action=action, actor_user_id=user.id,
        entity_type="kpi_definition", entity_id=kpi.id, company_id=kpi.company_id,
        ip_address=ip_address, user_agent=user_agent,
    )
    return kpi


def serialise_evaluation(row: dict) -> dict:
    return row


__all__ = [
    "METRIC_KEYS",
    "list_evaluations",
    "evaluate_sources",
    "resolve_actual",
    "update_kpi",
    "set_active",
    "serialise_evaluation",
]
