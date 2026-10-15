"""Holding accounting endpoints: opening balances, accounts, journals,
invoices, assets, budgets and KPIs (D01/D02/D07/D08)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request, status

from backend.api.deps import CurrentUser, DbSession
from backend.schemas.domain import (
    AccountCreateRequest,
    AssetCreateRequest,
    BudgetApproveRequest,
    BudgetCreateRequest,
    InterbalanceCreateRequest,
    InvoiceCreateRequest,
    JournalCreateRequest,
    JournalReverseRequest,
    KpiActiveRequest,
    KpiCreateRequest,
    KpiUpdateRequest,
    OpeningBalanceCreateRequest,
    PartyCreateRequest,
    PolicyCreateRequest,
    SettlementCreateRequest,
)
from backend.services import accounting_service, audit_service, kpi_service

router = APIRouter(prefix="/accounting", tags=["accounting"])


def _period(request: Request) -> tuple[int, int]:
    now = datetime.now(timezone.utc)
    year = request.query_params.get("year")
    month = request.query_params.get("month")
    return (
        int(year) if year else now.year,
        int(month) if month else now.month,
    )


# ---- opening balances (D08) ----
@router.get("/opening-balances")
def list_opening_balances(
    user: CurrentUser, db: DbSession, company_id: int | None = None
) -> list[dict]:
    return [
        accounting_service.serialise_opening_balance(o)
        for o in accounting_service.list_opening_balances(db, user=user, company_id=company_id)
    ]


@router.post("/opening-balances", status_code=status.HTTP_201_CREATED)
def create_opening_balance(
    payload: OpeningBalanceCreateRequest, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    ctx = audit_service.request_context(request)
    data = payload.model_dump()
    data["kind"] = payload.kind.value
    ob = accounting_service.create_opening_balance(db, user=user, **data, **ctx)
    return accounting_service.serialise_opening_balance(ob)


@router.post("/opening-balances/{ob_id}/submit")
def submit_opening_balance(
    ob_id: int, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    ctx = audit_service.request_context(request)
    ob = accounting_service.submit_opening_balance(db, user=user, opening_balance_id=ob_id, **ctx)
    return accounting_service.serialise_opening_balance(ob)


@router.post("/opening-balances/{ob_id}/approve")
def approve_opening_balance(
    ob_id: int, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    ctx = audit_service.request_context(request)
    ob = accounting_service.approve_opening_balance(db, user=user, opening_balance_id=ob_id, **ctx)
    return accounting_service.serialise_opening_balance(ob)


# ---- chart of accounts (D01) ----
@router.get("/accounts")
def list_accounts(
    user: CurrentUser, db: DbSession, company_id: int | None = None
) -> list[dict]:
    return [
        accounting_service.serialise_account(a)
        for a in accounting_service.list_accounts(db, user=user, company_id=company_id)
    ]


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
def create_account(
    payload: AccountCreateRequest, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    ctx = audit_service.request_context(request)
    data = payload.model_dump()
    data["account_type"] = payload.account_type.value
    account = accounting_service.create_account(db, user=user, **data, **ctx)
    return accounting_service.serialise_account(account)


# ---- journals (D01) ----
@router.get("/journals")
def list_journals(
    user: CurrentUser, db: DbSession, company_id: int | None = None
) -> list[dict]:
    return [
        accounting_service.serialise_journal(j)
        for j in accounting_service.list_journals(db, user=user, company_id=company_id)
    ]


@router.post("/journals", status_code=status.HTTP_201_CREATED)
def create_journal(
    payload: JournalCreateRequest, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    ctx = audit_service.request_context(request)
    data = payload.model_dump()
    lines = data.pop("lines")
    journal = accounting_service.create_journal(db, user=user, lines=lines, **data, **ctx)
    return accounting_service.serialise_journal(journal)


@router.get("/journals/{journal_id}")
def get_journal(journal_id: int, user: CurrentUser, db: DbSession) -> dict:
    return accounting_service.serialise_journal(
        accounting_service._get_journal(db, user=user, journal_id=journal_id)
    )


@router.get("/trial-balance")
def trial_balance(
    user: CurrentUser, db: DbSession, company_id: int,
    fiscal_year: int | None = None, fiscal_month: int | None = None,
) -> dict:
    return accounting_service.trial_balance(
        db, user=user, company_id=company_id,
        fiscal_year=fiscal_year, fiscal_month=fiscal_month,
    )


@router.post("/journals/{journal_id}/post")
def post_journal(journal_id: int, request: Request, user: CurrentUser, db: DbSession) -> dict:
    ctx = audit_service.request_context(request)
    journal = accounting_service.post_journal(db, user=user, journal_id=journal_id, **ctx)
    return accounting_service.serialise_journal(journal)


@router.post("/journals/{journal_id}/reverse")
def reverse_journal(
    journal_id: int, payload: JournalReverseRequest, request: Request,
    user: CurrentUser, db: DbSession,
) -> dict:
    ctx = audit_service.request_context(request)
    reversal = accounting_service.reverse_journal(
        db, user=user, journal_id=journal_id, reason=payload.reason, **ctx
    )
    return accounting_service.serialise_journal(reversal)


# ---- invoices & settlements ----
@router.get("/invoices")
def list_invoices(
    user: CurrentUser, db: DbSession, company_id: int | None = None
) -> list[dict]:
    return [
        accounting_service.serialise_invoice(i)
        for i in accounting_service.list_invoices(db, user=user, company_id=company_id)
    ]


@router.get("/receivables")
def receivables(
    user: CurrentUser, db: DbSession, company_id: int | None = None
) -> dict:
    return accounting_service.receivables_summary(db, user=user, company_id=company_id)


@router.get("/ledger-activity")
def ledger_activity(
    user: CurrentUser, db: DbSession, company_id: int,
    account_type: str | None = None,
    fiscal_year: int | None = None, fiscal_month: int | None = None,
) -> dict:
    """View revenue or expense as its source lines, adding no record (S26 Table 53)."""
    return accounting_service.ledger_activity(
        db, user=user, company_id=company_id, account_type=account_type,
        fiscal_year=fiscal_year, fiscal_month=fiscal_month,
    )


@router.get("/financial-statements")
def financial_statements(
    user: CurrentUser, db: DbSession, company_id: int,
    fiscal_year: int | None = None, fiscal_month: int | None = None,
    compare_previous: bool = False,
) -> dict:
    return accounting_service.financial_statements(
        db, user=user, company_id=company_id, fiscal_year=fiscal_year,
        fiscal_month=fiscal_month, compare_previous=compare_previous,
    )


@router.post("/invoices", status_code=status.HTTP_201_CREATED)
def create_invoice(
    payload: InvoiceCreateRequest, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    ctx = audit_service.request_context(request)
    data = payload.model_dump()
    lines = data.pop("lines")
    data["direction"] = payload.direction.value
    invoice = accounting_service.create_invoice(db, user=user, lines=lines, **data, **ctx)
    return accounting_service.serialise_invoice(invoice)


# ---- parties (S27) ----
@router.get("/parties")
def list_parties(
    user: CurrentUser, db: DbSession, company_id: int | None = None
) -> list[dict]:
    return [
        accounting_service.serialise_party(p)
        for p in accounting_service.list_parties(db, user=user, company_id=company_id)
    ]


@router.post("/parties", status_code=status.HTTP_201_CREATED)
def create_party(
    payload: PartyCreateRequest, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    ctx = audit_service.request_context(request)
    party = accounting_service.create_party(db, user=user, **payload.model_dump(), **ctx)
    return accounting_service.serialise_party(party)


# ---- inter-company balances (S27) ----
@router.get("/interbalances")
def list_interbalances(
    user: CurrentUser, db: DbSession, company_id: int | None = None
) -> list[dict]:
    return [
        accounting_service.serialise_interbalance(b)
        for b in accounting_service.list_interbalances(db, user=user, company_id=company_id)
    ]


@router.post("/interbalances", status_code=status.HTTP_201_CREATED)
def record_interbalance(
    payload: InterbalanceCreateRequest, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    ctx = audit_service.request_context(request)
    balance = accounting_service.record_interbalance(
        db, user=user, **payload.model_dump(), **ctx
    )
    return accounting_service.serialise_interbalance(balance)


@router.post("/invoices/{invoice_id}/settlements", status_code=status.HTTP_201_CREATED)
def record_settlement(
    invoice_id: int, payload: SettlementCreateRequest, request: Request,
    user: CurrentUser, db: DbSession,
) -> dict:
    ctx = audit_service.request_context(request)
    settlement = accounting_service.record_settlement(
        db, user=user, invoice_id=invoice_id, **payload.model_dump(), **ctx
    )
    return {"id": settlement.id, "invoice_id": settlement.invoice_id,
            "amount": settlement.amount, "currency": settlement.currency}


# ---- assets ----
@router.get("/assets")
def list_assets(
    user: CurrentUser, db: DbSession, company_id: int | None = None
) -> list[dict]:
    return [
        accounting_service.serialise_asset(a)
        for a in accounting_service.list_assets(db, user=user, company_id=company_id)
    ]


@router.post("/assets", status_code=status.HTTP_201_CREATED)
def create_asset(
    payload: AssetCreateRequest, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    ctx = audit_service.request_context(request)
    asset = accounting_service.create_asset(db, user=user, **payload.model_dump(), **ctx)
    return accounting_service.serialise_asset(asset)


# ---- budgets (D07) ----
@router.get("/budgets")
def list_budgets(
    user: CurrentUser, db: DbSession, company_id: int | None = None
) -> list[dict]:
    return [
        accounting_service.serialise_budget(b)
        for b in accounting_service.list_budgets(db, user=user, company_id=company_id)
    ]


@router.post("/budgets", status_code=status.HTTP_201_CREATED)
def create_budget(
    payload: BudgetCreateRequest, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    ctx = audit_service.request_context(request)
    budget = accounting_service.create_budget(db, user=user, **payload.model_dump(), **ctx)
    return accounting_service.serialise_budget(budget)


@router.post("/budgets/{budget_id}/approve")
def approve_budget(
    budget_id: int, payload: BudgetApproveRequest, request: Request,
    user: CurrentUser, db: DbSession,
) -> dict:
    ctx = audit_service.request_context(request)
    budget = accounting_service.approve_budget(
        db, user=user, budget_id=budget_id, source=payload.source, **ctx
    )
    return accounting_service.serialise_budget(budget)


# ---- KPIs (D02) ----
@router.get("/kpis")
def list_kpis(
    user: CurrentUser, db: DbSession, company_id: int | None = None
) -> list[dict]:
    return [
        accounting_service.serialise_kpi(k)
        for k in accounting_service.list_kpis(db, user=user, company_id=company_id)
    ]


@router.post("/kpis", status_code=status.HTTP_201_CREATED)
def create_kpi(
    payload: KpiCreateRequest, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    ctx = audit_service.request_context(request)
    kpi = accounting_service.create_kpi(db, user=user, **payload.model_dump(), **ctx)
    return accounting_service.serialise_kpi(kpi)


@router.patch("/kpis/{kpi_id}")
def update_kpi(
    kpi_id: int, payload: KpiUpdateRequest, request: Request,
    user: CurrentUser, db: DbSession,
) -> dict:
    """Record target/metric/direction. Never activates the KPI (D02)."""
    ctx = audit_service.request_context(request)
    kpi = kpi_service.update_kpi(
        db, user=user, kpi_id=kpi_id, **payload.model_dump(), **ctx
    )
    return accounting_service.serialise_kpi(kpi)


@router.post("/kpis/{kpi_id}/active")
def set_kpi_active(
    kpi_id: int, payload: KpiActiveRequest, request: Request,
    user: CurrentUser, db: DbSession,
) -> dict:
    """Approve (activate) or deactivate a KPI, stamping the approval record."""
    ctx = audit_service.request_context(request)
    kpi = kpi_service.set_active(
        db, user=user, kpi_id=kpi_id, active=payload.active, **ctx
    )
    return accounting_service.serialise_kpi(kpi)


@router.get("/kpis/evaluations")
def list_kpi_evaluations(
    request: Request, user: CurrentUser, db: DbSession,
    company_id: int | None = None,
) -> list[dict]:
    """Target-versus-actual for the period, computed from source records (D02)."""
    year, month = _period(request)
    return kpi_service.list_evaluations(
        db, user=user, company_id=company_id, year=year, month=month
    )


@router.get("/kpis/{kpi_id}/sources")
def kpi_sources(
    kpi_id: int, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    """Source records behind a KPI's actual, with no copy (S01 Table 13)."""
    year, month = _period(request)
    return kpi_service.evaluate_sources(
        db, user=user, kpi_id=kpi_id, year=year, month=month
    )


# ---- accounting policy registry (D01) ----
@router.get("/policies")
def list_policies(
    user: CurrentUser, db: DbSession, company_id: int | None = None,
    kind: str | None = None, approved_only: bool = False,
) -> list[dict]:
    return [
        accounting_service.serialise_policy(p)
        for p in accounting_service.list_policies(
            db, user=user, company_id=company_id, kind=kind,
            approved_only=approved_only,
        )
    ]


@router.post("/policies", status_code=status.HTTP_201_CREATED)
def create_policy(
    payload: PolicyCreateRequest, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    """Record a draft accounting policy. A draft never affects a calculation."""
    ctx = audit_service.request_context(request)
    policy = accounting_service.create_policy(db, user=user, **payload.model_dump(), **ctx)
    return accounting_service.serialise_policy(policy)


@router.post("/policies/{policy_id}/approve")
def approve_policy(
    policy_id: int, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    """Approve a policy (accountant act); the prior version is superseded."""
    ctx = audit_service.request_context(request)
    policy = accounting_service.approve_policy(db, user=user, policy_id=policy_id, **ctx)
    return accounting_service.serialise_policy(policy)


@router.get("/policies/effective")
def effective_policy(
    user: CurrentUser, db: DbSession, company_id: int, kind: str,
    on_date: str | None = None,
) -> dict | None:
    """The *approved* policy that applies to a company (never a draft, D01)."""
    from datetime import date as _date

    parsed = _date.fromisoformat(on_date) if on_date else None
    policy = accounting_service.effective_policy(
        db, company_id=company_id, kind=kind, on_date=parsed
    )
    return accounting_service.serialise_policy(policy) if policy else None
