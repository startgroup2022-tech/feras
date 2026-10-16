"""Effective-version reporting for the financial summary workflow (spec S10).

The reporting layer must read **one** version per period: the effective
(approved) one. This module builds that view without touching the existing
dashboard aggregation, so no existing figure or test changes and there is no
path by which two versions of the same period could both be counted.

For each company with a period in the requested month it reports the effective
figures when an approved version exists, and a status classification otherwise:

* ``draft``               -- assembled, not yet sent (no notice);
* ``submitted``           -- awaiting the accountant (للمراجعة);
* ``correction_required`` -- returned for correction (مطلوب تصحيح);
* ``approved``            -- effective and included in the totals;
* ``missing``             -- no financial summary for the period.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session, selectinload

from backend.db.models.enums import CompanyStatus, FinancialSummaryStatus
from backend.db.models.financial import FinancialPeriod, FinancialSummaryVersion
from backend.db.models.identity import Company, User
from backend.rbac.authorization import accessible_company_ids

ZERO = Decimal("0")

_EMPTY_TOTALS = (
    "effective_revenue",
    "effective_expenses",
    "calculated_result",
    "total_cash",
    "outstanding_debts",
    "customer_receivables",
)

# The status precedence used to classify a period that has several versions.
_STATUS_PRECEDENCE = [
    FinancialSummaryStatus.APPROVED.value,
    FinancialSummaryStatus.SUBMITTED.value,
    FinancialSummaryStatus.CORRECTION_REQUIRED.value,
    FinancialSummaryStatus.DRAFT.value,
]


def _classify(versions: list[FinancialSummaryVersion], effective_id: int | None) -> str:
    if effective_id is not None:
        return FinancialSummaryStatus.APPROVED.value
    present = {v.status for v in versions}
    for status in _STATUS_PRECEDENCE:
        if status in present:
            return status
    return "missing"


def effective_period_report(
    db: Session, *, user: User, year: int, month: int
) -> dict:
    """Per-company effective financial report for one calendar month."""
    allowed = accessible_company_ids(user)

    companies_stmt = db.query(Company).filter(
        Company.status == CompanyStatus.ACTIVE.value
    )
    if allowed is not None:
        companies_stmt = companies_stmt.filter(Company.id.in_(allowed or [-1]))
    companies = companies_stmt.order_by(Company.name_en).all()

    periods = {
        p.company_id: p
        for p in db.query(FinancialPeriod)
        .options(selectinload(FinancialPeriod.versions))
        .filter(FinancialPeriod.period_year == year, FinancialPeriod.period_month == month)
        .all()
    }

    rows: list[dict] = []
    # AC-10 / T10: "a currency difference separates the results". Amounts are
    # only ever summed inside one currency, so the group strip can never add a
    # SAR revenue to a USD one. ``totals`` keeps the familiar single-currency
    # shape when every contributing company shares a currency; with two or more
    # currencies it carries no number at all (``None``, not a mixed sum) and the
    # per-currency breakdown in ``totals_by_currency`` is the real answer.
    totals_by_currency: dict[str, dict[str, Decimal]] = {}
    counts = {
        "approved": 0,
        "submitted": 0,
        "correction_required": 0,
        "draft": 0,
        "missing": 0,
    }

    def _bucket(currency: str) -> dict[str, Decimal]:
        return totals_by_currency.setdefault(
            currency or "",
            {
                "effective_revenue": ZERO,
                "effective_expenses": ZERO,
                "calculated_result": ZERO,
                "total_cash": ZERO,
                "outstanding_debts": ZERO,
                "customer_receivables": ZERO,
            },
        )

    for company in companies:
        period = periods.get(company.id)
        effective = None
        if period is not None and period.effective_version_id is not None:
            effective = next(
                (v for v in period.versions if v.id == period.effective_version_id), None
            )
        status = _classify(period.versions if period else [], period.effective_version_id if period else None)
        counts[status] = counts.get(status, 0) + 1

        row = {
            "company_id": company.id,
            "company_name_ar": company.name_ar,
            "company_name_en": company.name_en,
            "period_id": period.id if period else None,
            "status": status,
            "is_effective": effective is not None,
            "effective_version_id": effective.id if effective else None,
            "version_number": effective.version_number if effective else None,
            "currency": (effective.currency if effective else (period.currency if period else company.currency)),
            "effective_revenue": effective.effective_revenue if effective else None,
            "effective_expenses": effective.effective_expenses if effective else None,
            "calculated_result": effective.calculated_result if effective else None,
            "total_cash": effective.calculated_total_cash if effective else None,
            "outstanding_debts": effective.outstanding_debts if effective else None,
            "customer_receivables": effective.customer_receivables if effective else None,
        }
        rows.append(row)

        if effective is not None:
            bucket = _bucket(row["currency"])
            bucket["effective_revenue"] += effective.effective_revenue or ZERO
            bucket["effective_expenses"] += effective.effective_expenses or ZERO
            bucket["calculated_result"] += effective.calculated_result or ZERO
            bucket["total_cash"] += effective.calculated_total_cash or ZERO
            bucket["outstanding_debts"] += effective.outstanding_debts or ZERO
            bucket["customer_receivables"] += effective.customer_receivables or ZERO

    currencies = sorted(c for c in totals_by_currency if c)
    single = currencies[0] if len(currencies) == 1 else None
    if single is not None:
        totals = {k: str(v) for k, v in totals_by_currency[single].items()}
    else:
        # Two or more currencies (or none at all): never present a mixed sum.
        totals = {k: None for k in _EMPTY_TOTALS}

    return {
        "period_year": year,
        "period_month": month,
        "companies": rows,
        "totals": totals,
        "totals_by_currency": {
            c: {k: str(v) for k, v in values.items()}
            for c, values in sorted(totals_by_currency.items())
        },
        "counts": counts,
    }


__all__ = ["effective_period_report"]
