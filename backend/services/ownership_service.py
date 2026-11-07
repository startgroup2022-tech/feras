"""Ownership structure service.

Records who owns what. Two invariants are enforced here, because the database
cannot express them:

* **No cycles.** A company may not own itself, directly or transitively. A
  cycle would make the group structure graph ill-defined and any recursive
  traversal infinite.
* **Active stakes do not exceed 100%.** For a given company, the sum of active
  ownership percentages must stay at or below 100.

Stakes form a history: ``end_ownership`` closes a stake (status ``ended`` plus
an ``effective_to`` date) rather than deleting the row.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.errors import ConflictError, NotFoundError, ValidationError
from backend.db.models.audit_actions import AuditAction
from backend.db.models.enums import OwnershipStatus
from backend.db.models.group import InvestmentValuation, Ownership
from backend.db.models.identity import Company, User
from backend.rbac.authorization import accessible_company_ids, require_permission
from backend.rbac.permissions import Perm
from backend.services import audit_service

MAX_TOTAL_PERCENTAGE = Decimal("100")


def _today() -> date:
    """Today's date in UTC, matching the project's timezone-aware convention."""
    return datetime.now(timezone.utc).date()


def _label(company: Company) -> str:
    return company.name_en or company.name_ar


def _active_total(db: Session, owned_company_id: int, *, exclude_id: int | None = None) -> Decimal:
    stmt = select(func.coalesce(func.sum(Ownership.ownership_percentage), 0)).where(
        Ownership.owned_company_id == owned_company_id,
        Ownership.status == OwnershipStatus.ACTIVE.value,
    )
    if exclude_id is not None:
        stmt = stmt.where(Ownership.id != exclude_id)
    return Decimal(str(db.execute(stmt).scalar_one()))


def _would_create_cycle(
    db: Session, *, owner_company_id: int, owned_company_id: int
) -> bool:
    """True when making ``owner`` own ``owned`` closes a cycle.

    Walks up from the proposed owner: if we reach the prospective subsidiary,
    the edge would form a loop.
    """
    if owner_company_id == owned_company_id:
        return True

    seen: set[int] = set()
    frontier = [owner_company_id]
    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        parents = db.execute(
            select(Ownership.owner_company_id).where(
                Ownership.owned_company_id == current,
                Ownership.status == OwnershipStatus.ACTIVE.value,
                Ownership.owner_company_id.is_not(None),
            )
        ).scalars()
        for parent in parents:
            if parent == owned_company_id:
                return True
            if parent not in seen:
                frontier.append(parent)
    return False


def _serialize(db: Session, ownership: Ownership) -> dict:
    owned = db.get(Company, ownership.owned_company_id)
    owner = (
        db.get(Company, ownership.owner_company_id)
        if ownership.owner_company_id is not None
        else None
    )
    return {
        "id": ownership.id,
        "owned_company_id": ownership.owned_company_id,
        "owner_company_id": ownership.owner_company_id,
        "external_owner_name": ownership.external_owner_name,
        "ownership_percentage": float(ownership.ownership_percentage),
        "effective_from": ownership.effective_from,
        "effective_to": ownership.effective_to,
        "status": ownership.status,
        "notes": ownership.notes,
        "owned_company_name_ar": owned.name_ar if owned else None,
        "owned_company_name_en": owned.name_en if owned else None,
        "owner_company_name_ar": owner.name_ar if owner else None,
        "owner_company_name_en": owner.name_en if owner else None,
    }


def list_ownerships(
    db: Session,
    *,
    user: User,
    owned_company_id: int | None = None,
    owner_company_id: int | None = None,
    status: str | None = None,
) -> list[dict]:
    require_permission(user, Perm.OWNERSHIP_READ)
    stmt = select(Ownership).order_by(
        Ownership.owned_company_id, Ownership.effective_from.desc()
    )
    if owned_company_id is not None:
        stmt = stmt.where(Ownership.owned_company_id == owned_company_id)
    if owner_company_id is not None:
        stmt = stmt.where(Ownership.owner_company_id == owner_company_id)
    if status is not None:
        stmt = stmt.where(Ownership.status == status)
    return [_serialize(db, row) for row in db.execute(stmt).scalars()]


def group_structure(db: Session, *, user: User) -> list[dict]:
    """The full group graph as a flat list of company nodes with their parent.

    Each company carries at most one *primary* parent (the active internal stake
    with the largest percentage), which is what a tree view needs. A company can
    also hold several minority stakes; those remain visible through
    ``list_ownerships``.
    """
    require_permission(user, Perm.OWNERSHIP_READ)
    companies = list(db.execute(select(Company).order_by(Company.name_en)).scalars())

    active = list(
        db.execute(
            select(Ownership)
            .where(
                Ownership.status == OwnershipStatus.ACTIVE.value,
                Ownership.owner_company_id.is_not(None),
            )
            .order_by(Ownership.ownership_percentage.desc())
        ).scalars()
    )
    primary_parent: dict[int, Ownership] = {}
    child_counts: dict[int, int] = {}
    for stake in active:
        child_counts[stake.owner_company_id] = child_counts.get(stake.owner_company_id, 0) + 1
        primary_parent.setdefault(stake.owned_company_id, stake)

    nodes: list[dict] = []
    for company in companies:
        stake = primary_parent.get(company.id)
        parent = db.get(Company, stake.owner_company_id) if stake else None
        nodes.append(
            {
                "company_id": company.id,
                "code": company.code,
                "name_ar": company.name_ar,
                "name_en": company.name_en,
                "sector": company.sector,
                "status": company.status,
                "parent_company_id": parent.id if parent else None,
                "parent_name_ar": parent.name_ar if parent else None,
                "parent_name_en": parent.name_en if parent else None,
                "ownership_percentage": (
                    float(stake.ownership_percentage) if stake else None
                ),
                "direct_children": child_counts.get(company.id, 0),
            }
        )
    return nodes


def create_ownership(
    db: Session,
    *,
    actor: User,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    require_permission(actor, Perm.OWNERSHIP_MANAGE)

    owned = db.get(Company, payload["owned_company_id"])
    if owned is None:
        raise NotFoundError("Subsidiary not found.")

    owner_company_id = payload.get("owner_company_id")
    external_owner = (payload.get("external_owner_name") or "").strip() or None
    if (owner_company_id is None) == (external_owner is None):
        raise ValidationError(
            "Provide exactly one of owner_company_id or external_owner_name."
        )

    if owner_company_id is not None:
        owner = db.get(Company, owner_company_id)
        if owner is None:
            raise NotFoundError("Owner company not found.")
        if _would_create_cycle(
            db, owner_company_id=owner_company_id, owned_company_id=owned.id
        ):
            raise ConflictError(
                "This stake would create a circular ownership relationship."
            )

    percentage = Decimal(str(payload["ownership_percentage"]))
    effective_from: date = payload["effective_from"]

    # Reject a duplicate open stake for the same owner/company/date.
    duplicate = db.execute(
        select(Ownership).where(
            Ownership.owned_company_id == owned.id,
            Ownership.owner_company_id == owner_company_id,
            Ownership.external_owner_name == external_owner,
            Ownership.effective_from == effective_from,
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        raise ConflictError("An identical ownership stake already exists.")

    total = _active_total(db, owned.id)
    if effective_from <= _today() and total + percentage > MAX_TOTAL_PERCENTAGE:
        raise ValidationError(
            "Active ownership for this company would exceed 100%."
        )

    ownership = Ownership(
        owned_company_id=owned.id,
        owner_company_id=owner_company_id,
        external_owner_name=external_owner,
        ownership_percentage=percentage,
        effective_from=effective_from,
        status=OwnershipStatus.ACTIVE.value,
        notes=payload.get("notes"),
    )
    db.add(ownership)
    db.commit()
    db.refresh(ownership)

    audit_service.record(
        db,
        action=AuditAction.OWNERSHIP_CREATED,
        actor_user_id=actor.id,
        entity_type="ownership",
        entity_id=ownership.id,
        company_id=owned.id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={
            "owner_company_id": owner_company_id,
            "external_owner": external_owner,
            "percentage": float(percentage),
        },
    )
    return _serialize(db, ownership)


def update_ownership(
    db: Session,
    *,
    actor: User,
    ownership_id: int,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    require_permission(actor, Perm.OWNERSHIP_MANAGE)
    ownership = db.get(Ownership, ownership_id)
    if ownership is None:
        raise NotFoundError("Ownership stake not found.")

    if payload.get("ownership_percentage") is not None:
        percentage = Decimal(str(payload["ownership_percentage"]))
        total = _active_total(db, ownership.owned_company_id, exclude_id=ownership.id)
        if (
            ownership.status == OwnershipStatus.ACTIVE.value
            and total + percentage > MAX_TOTAL_PERCENTAGE
        ):
            raise ValidationError("Active ownership for this company would exceed 100%.")
        ownership.ownership_percentage = percentage

    if payload.get("effective_to") is not None:
        ownership.effective_to = payload["effective_to"]

    if payload.get("notes") is not None:
        ownership.notes = payload["notes"]

    if payload.get("status") is not None:
        ownership.status = payload["status"]
        if ownership.status == OwnershipStatus.ENDED.value and ownership.effective_to is None:
            ownership.effective_to = _today()

    db.add(ownership)
    db.commit()
    db.refresh(ownership)

    audit_service.record(
        db,
        action=AuditAction.OWNERSHIP_UPDATED,
        actor_user_id=actor.id,
        entity_type="ownership",
        entity_id=ownership.id,
        company_id=ownership.owned_company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"fields": sorted(payload.keys())},
    )
    return _serialize(db, ownership)


def end_ownership(
    db: Session,
    *,
    actor: User,
    ownership_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    """Close a stake without deleting it, preserving the ownership history."""
    require_permission(actor, Perm.OWNERSHIP_MANAGE)
    ownership = db.get(Ownership, ownership_id)
    if ownership is None:
        raise NotFoundError("Ownership stake not found.")

    ownership.status = OwnershipStatus.ENDED.value
    if ownership.effective_to is None:
        ownership.effective_to = _today()
    db.add(ownership)
    db.commit()
    db.refresh(ownership)

    audit_service.record(
        db,
        action=AuditAction.OWNERSHIP_ENDED,
        actor_user_id=actor.id,
        entity_type="ownership",
        entity_id=ownership.id,
        company_id=ownership.owned_company_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return _serialize(db, ownership)


# --------------------------------------------------------------------------
# Investment valuation summaries (deck slides 107-109)
# --------------------------------------------------------------------------
# Deck slide 109 states the rules this section enforces:
#   * The book value is entered as approved by the accountant with its date and
#     source -- never derived by summing contributions/financing/distributions.
#   * The valuation is a yes/no choice; when "no" the system stores no zero.
#   * Every ownership increase or exit carries a linked decision.
# Read scope follows the caller's company scope; a company manager only ever
# sees their own company's summary.
_VALUATION_FIELDS = (
    "currency",
    "investment_date",
    "original_value",
    "subsequent_contributions",
    "financing",
    "distributions",
    "book_value",
    "book_value_date",
    "book_value_source",
    "has_valuation",
    "valuation_amount",
    "valuation_date",
    "valuation_source",
    "valuation_reference",
    "decision_reference",
    "notes",
)


def _valuation_row(
    db: Session, owned_company_id: int, *, create: bool = False
) -> InvestmentValuation | None:
    row = db.execute(
        select(InvestmentValuation).where(
            InvestmentValuation.owned_company_id == owned_company_id
        )
    ).scalar_one_or_none()
    if row is None and create:
        row = InvestmentValuation(owned_company_id=owned_company_id)
        db.add(row)
    return row


def list_investment_valuations(db: Session, *, user: User) -> list[dict]:
    """Every valuation summary the caller may read, confined to their scope."""
    require_permission(user, Perm.INVESTMENT_READ)
    allowed = accessible_company_ids(user)
    stmt = select(InvestmentValuation).order_by(InvestmentValuation.owned_company_id)
    if allowed is not None:
        if not allowed:
            return []
        stmt = stmt.where(InvestmentValuation.owned_company_id.in_(allowed))
    return [_serialize_valuation(db, row) for row in db.execute(stmt).scalars()]


def get_investment_valuation(db: Session, *, user: User, owned_company_id: int) -> dict:
    """One company's summary. Out-of-scope is a 404, never a 403 that leaks."""
    require_permission(user, Perm.INVESTMENT_READ)
    allowed = accessible_company_ids(user)
    if allowed is not None and owned_company_id not in allowed:
        raise NotFoundError("Company not found.")
    company = db.get(Company, owned_company_id)
    if company is None:
        raise NotFoundError("Company not found.")
    row = _valuation_row(db, owned_company_id)
    if row is None:
        # A company with no recorded summary is not an error; return an empty
        # shell so the detail view can show "غير مُعدّ" rather than a zero.
        return {
            "id": None,
            "owned_company_id": owned_company_id,
            "currency": company.currency or "SAR",
            "has_valuation": False,
        }
    return _serialize_valuation(db, row)


def update_investment_valuation(
    db: Session,
    *,
    actor: User,
    owned_company_id: int,
    payload: dict,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    """Create or correct a company's valuation summary.

    The write permission is ``investment.manage`` (accountant/owner); the
    company scope is still enforced so a scoped editor cannot touch another
    entity. The yes/no valuation rule is validated in the schema; here we only
    persist what was approved.
    """
    require_permission(actor, Perm.INVESTMENT_MANAGE)
    allowed = accessible_company_ids(actor)
    if allowed is not None and owned_company_id not in allowed:
        raise NotFoundError("Company not found.")
    company = db.get(Company, owned_company_id)
    if company is None:
        raise NotFoundError("Company not found.")

    row = _valuation_row(db, owned_company_id, create=True)
    assert row is not None
    for field in _VALUATION_FIELDS:
        if field in payload and payload[field] is not None:
            setattr(row, field, payload[field])
    if row.currency is None:
        row.currency = company.currency or "SAR"
    db.add(row)
    db.commit()
    db.refresh(row)

    audit_service.record(
        db,
        action=AuditAction.INVESTMENT_VALUATION_UPDATED,
        actor_user_id=actor.id,
        entity_type="investment_valuation",
        entity_id=row.id,
        company_id=owned_company_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"has_valuation": row.has_valuation},
    )
    return _serialize_valuation(db, row)


def _serialize_valuation(db: Session, row: InvestmentValuation) -> dict:
    company = db.get(Company, row.owned_company_id)
    return {
        "id": row.id,
        "owned_company_id": row.owned_company_id,
        "owned_company_name_ar": company.name_ar if company else None,
        "owned_company_name_en": company.name_en if company else None,
        "currency": row.currency,
        "investment_date": row.investment_date,
        "original_value": _decimal_out(row.original_value),
        "subsequent_contributions": _decimal_out(row.subsequent_contributions),
        "financing": _decimal_out(row.financing),
        "distributions": _decimal_out(row.distributions),
        "book_value": _decimal_out(row.book_value),
        "book_value_date": row.book_value_date,
        "book_value_source": row.book_value_source,
        "has_valuation": bool(row.has_valuation),
        "valuation_amount": _decimal_out(row.valuation_amount),
        "valuation_date": row.valuation_date,
        "valuation_source": row.valuation_source,
        "valuation_reference": row.valuation_reference,
        "decision_reference": row.decision_reference,
        "notes": row.notes,
    }


def _decimal_out(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


__all__ = [
    "create_ownership",
    "end_ownership",
    "get_investment_valuation",
    "group_structure",
    "list_investment_valuations",
    "list_ownerships",
    "update_investment_valuation",
    "update_ownership",
]
