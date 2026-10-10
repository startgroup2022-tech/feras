"""Financial calculation engine for subsidiary summaries (spec section 15.1).

One reusable, side-effect-free module. Every monetary operation uses
:class:`decimal.Decimal` -- never ``float`` -- so an aggregated figure is exact.

Rules (Arabic spec, section 15.1, decisions 2 and 3):

* **Effective revenue** = submitted revenue + Σ(item amounts whose
  *classification* is revenue **and** whose *inclusion rule* is ``ADDED``).
* **Effective expenses** = submitted expenses + Σ(item amounts whose
  *classification* is expense **and** whose rule is ``ADDED``).
* **Result** = effective revenue − effective expenses.
* ``INCLUDED`` items are already inside the entered totals and must **not** be
  added again -- that is the double-counting the spec explicitly forbids.
* Items classified ``OTHER`` (transfers, withdrawals, loans, settlements) never
  change the result automatically. A transfer to the Holding is **not** revenue.
* Closing bank/cash/debts/receivables are period-end **balances**, independent
  of the result. ``total_cash`` = closing bank + closing cash.

Currency: amounts in a currency other than the company base currency are
rejected (``UnsupportedCurrencyError``) because no conversion rule is approved
yet (decision D09). This prevents a silent, wrong aggregation.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Protocol, Sequence

from backend.core.errors import ValidationError
from backend.db.models.enums import (
    FinancialInclusionRule,
    FinancialItemKind,
)

ZERO = Decimal("0")


class UnsupportedCurrencyError(ValidationError):
    """Raised when a cross-currency aggregation is attempted without a rule."""


class _ItemLike(Protocol):
    amount: Decimal | None
    currency: str
    kind: str
    inclusion_rule: str


@dataclass(frozen=True)
class CalculationResult:
    """The computed figures, with the traceable breakdown the UI must show."""

    entered_revenue: Decimal
    entered_expenses: Decimal
    revenue_additions: Decimal
    expense_additions: Decimal
    effective_revenue: Decimal
    effective_expenses: Decimal
    result: Decimal
    total_cash: Decimal

    def as_dict(self) -> dict:
        return {
            "entered_revenue": self.entered_revenue,
            "entered_expenses": self.entered_expenses,
            "revenue_additions": self.revenue_additions,
            "expense_additions": self.expense_additions,
            "effective_revenue": self.effective_revenue,
            "effective_expenses": self.effective_expenses,
            "result": self.result,
            "total_cash": self.total_cash,
        }


def _dec(value: Decimal | int | str | None) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _check_currency(item: _ItemLike, base_currency: str) -> None:
    if item.currency and item.currency != base_currency:
        raise UnsupportedCurrencyError(
            "An item in a different currency cannot be combined without an "
            "approved conversion rule."
        )


def _addition(items: Sequence[_ItemLike], kind: str, base_currency: str) -> Decimal:
    """Sum the ``ADDED`` items of one classification, in the base currency."""
    total = ZERO
    for item in items:
        if item.kind != kind:
            continue
        # Only ADDED items change the effective total; INCLUDED items are
        # already inside the entered figure and must not be counted twice.
        if item.inclusion_rule != FinancialInclusionRule.ADDED.value:
            continue
        _check_currency(item, base_currency)
        total += _dec(item.amount)
    return total


def calculate(
    *,
    entered_revenue: Decimal | int | str | None,
    entered_expenses: Decimal | int | str | None,
    items: Iterable[_ItemLike] = (),
    closing_bank_balance: Decimal | int | str | None = None,
    closing_cash_balance: Decimal | int | str | None = None,
    base_currency: str = "SAR",
) -> CalculationResult:
    """Compute the effective totals, result and total cash.

    Deterministic and free of database access, so it can be unit-tested in
    isolation and reused by the summary service and the reporting layer.
    """
    item_list = list(items)
    # Validate every item's currency up front, even OTHER items, so a bad
    # classification cannot hide a currency mismatch.
    for item in item_list:
        if item.currency and item.currency != base_currency:
            raise UnsupportedCurrencyError(
                "An item in a different currency cannot be combined without an "
                "approved conversion rule."
            )

    revenue = _dec(entered_revenue)
    expenses = _dec(entered_expenses)

    revenue_additions = _addition(item_list, FinancialItemKind.REVENUE.value, base_currency)
    expense_additions = _addition(item_list, FinancialItemKind.EXPENSE.value, base_currency)

    effective_revenue = revenue + revenue_additions
    effective_expenses = expenses + expense_additions
    result = effective_revenue - effective_expenses

    total_cash = _dec(closing_bank_balance) + _dec(closing_cash_balance)

    return CalculationResult(
        entered_revenue=revenue,
        entered_expenses=expenses,
        revenue_additions=revenue_additions,
        expense_additions=expense_additions,
        effective_revenue=effective_revenue,
        effective_expenses=effective_expenses,
        result=result,
        total_cash=total_cash,
    )


__all__ = [
    "CalculationResult",
    "UnsupportedCurrencyError",
    "calculate",
    "ZERO",
]
