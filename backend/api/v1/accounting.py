"""Holding accounting endpoints: opening balances, accounts, journals,
invoices, assets, budgets and KPIs (D01/D02/D07/D08)."""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from backend.api.deps import CurrentUser, DbSession
from backend.schemas.domain import (
    AccountCreateRequest,
    AssetCreateRequest,
    BudgetApproveRequest,
    BudgetCreateRequest,
    InvoiceCreateRequest,
    JournalCreateRequest,
    JournalReverseRequest,
    KpiCreateRequest,
    OpeningBalanceCreateRequest,
    SettlementCreateRequest,
)
from backend.services import accounting_service, audit_service

router = APIRouter(prefix="/accounting", tags=["accounting"])


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


@router.post("/invoices", status_code=status.HTTP_201_CREATED)
def create_invoice(
    payload: InvoiceCreateRequest, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    ctx = audit_service.request_context(request)
    data = payload.model_dump()
    lines = data.pop("lines")
    invoice = accounting_service.create_invoice(db, user=user, lines=lines, **data, **ctx)
    return accounting_service.serialise_invoice(invoice)


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
