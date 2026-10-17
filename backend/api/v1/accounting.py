"""Holding accounting endpoints: opening balances, accounts, journals,
invoices, assets, budgets and KPIs (D01/D02/D07/D08)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request, status

from backend.api.deps import CurrentUser, DbSession
from backend.schemas.domain import (
    AccountCreateRequest,
    AssetCreateRequest,
    BudgetApproveRequest,
    BudgetCreateRequest,
    FinancialReportAnalysisRequest,
    FinancialReportGenerateRequest,
    InterbalanceCreateRequest,
    InvoiceCreateRequest,
    InvoiceJournalLinkRequest,
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
from backend.schemas.governance import (
    CurrencyChangeDecisionRequest,
    CurrencyChangeRequestCreate,
    CurrencyChangeReviewRequest,
    PolicyProposalCreateRequest,
    PolicyProposalDecisionRequest,
)
from backend.services import (
    accounting_service,
    audit_service,
    currency_change_service,
    kpi_service,
    policy_governance_service,
)

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


@router.post("/invoices/{invoice_id}/journal")
def link_invoice_journal(
    invoice_id: int, payload: InvoiceJournalLinkRequest, request: Request,
    user: CurrentUser, db: DbSession,
) -> dict:
    """Link the invoice to the single ledger entry that records it (S27/AC-27)."""
    ctx = audit_service.request_context(request)
    invoice = accounting_service.link_invoice_to_journal(
        db, user=user, invoice_id=invoice_id, journal_id=payload.journal_id, **ctx
    )
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


@router.get("/budgets/utilisation")
def budget_utilisation(
    user: CurrentUser, db: DbSession, company_id: int, fiscal_year: int,
    fiscal_month: int | None = None,
) -> dict:
    return accounting_service.budget_utilisation(
        db, user=user, company_id=company_id, fiscal_year=fiscal_year,
        fiscal_month=fiscal_month,
    )


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


# ---- D01 governance: policy proposals (accountant proposes, owner approves) ----
@router.get("/policies/proposals")
def list_policy_proposals(
    user: CurrentUser, db: DbSession, company_id: int | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
) -> list[dict]:
    rows = policy_governance_service.list_proposals(
        db, user=user, company_id=company_id, status=status_filter
    )
    return [policy_governance_service.serialise_proposal(p) for p in rows]


@router.post("/policies/proposals", status_code=status.HTTP_201_CREATED)
def propose_policy_change(
    payload: PolicyProposalCreateRequest, request: Request,
    user: CurrentUser, db: DbSession,
) -> dict:
    """The accountant proposes a financial-policy change (D01). Stays inert."""
    ctx = audit_service.request_context(request)
    proposal = policy_governance_service.propose_policy_change(
        db, user=user, **payload.model_dump(), **ctx
    )
    return policy_governance_service.serialise_proposal(proposal)


@router.post("/policies/proposals/{proposal_id}/decide")
def decide_policy_proposal(
    proposal_id: int, payload: PolicyProposalDecisionRequest, request: Request,
    user: CurrentUser, db: DbSession,
) -> dict:
    """Owner approves/rejects a proposal (D01). Approval activates the version."""
    ctx = audit_service.request_context(request)
    proposal = policy_governance_service.decide_proposal(
        db, user=user, proposal_id=proposal_id, approve=payload.approve,
        note=payload.note, **ctx,
    )
    return policy_governance_service.serialise_proposal(proposal)


# ---- D09: base-currency change workflow ----
@router.get("/currency-changes")
def list_currency_changes(
    user: CurrentUser, db: DbSession, company_id: int | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
) -> list[dict]:
    rows = currency_change_service.list_requests(
        db, user=user, company_id=company_id, status=status_filter
    )
    return [currency_change_service.serialise_request(r) for r in rows]


@router.post("/currency-changes", status_code=status.HTTP_201_CREATED)
def request_currency_change(
    payload: CurrencyChangeRequestCreate, request: Request,
    user: CurrentUser, db: DbSession,
) -> dict:
    ctx = audit_service.request_context(request)
    row = currency_change_service.request_change(
        db, user=user, company_id=payload.company_id,
        requested_currency=payload.requested_currency,
        justification=payload.justification, **ctx,
    )
    return currency_change_service.serialise_request(row)


@router.post("/currency-changes/{request_id}/review")
def review_currency_change(
    request_id: int, payload: CurrencyChangeReviewRequest, request: Request,
    user: CurrentUser, db: DbSession,
) -> dict:
    ctx = audit_service.request_context(request)
    row = currency_change_service.review_change(
        db, user=user, request_id=request_id, note=payload.note, **ctx
    )
    return currency_change_service.serialise_request(row)


@router.post("/currency-changes/{request_id}/decide")
def decide_currency_change(
    request_id: int, payload: CurrencyChangeDecisionRequest, request: Request,
    user: CurrentUser, db: DbSession,
) -> dict:
    ctx = audit_service.request_context(request)
    row = currency_change_service.decide_change(
        db, user=user, request_id=request_id, approve=payload.approve,
        effective_year=payload.effective_year, effective_month=payload.effective_month,
        note=payload.note, **ctx,
    )
    return currency_change_service.serialise_request(row)


@router.post("/currency-changes/{request_id}/apply")
def apply_currency_change(
    request_id: int, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    ctx = audit_service.request_context(request)
    row = currency_change_service.apply_change(db, user=user, request_id=request_id, **ctx)
    return currency_change_service.serialise_request(row)


# ---- monthly financial report (S28 Table 57) ----
@router.get("/financial-reports")
def list_financial_reports(
    user: CurrentUser, db: DbSession, company_id: int | None = None,
    period_year: int | None = None, period_month: int | None = None,
) -> list[dict]:
    """The financial report archive (S28), scoped to the caller's companies."""
    return [
        accounting_service.serialise_financial_report(r)
        for r in accounting_service.list_monthly_financial_reports(
            db, user=user, company_id=company_id,
            period_year=period_year, period_month=period_month,
        )
    ]


@router.get("/financial-reports/group")
def group_financial_report(
    user: CurrentUser, db: DbSession, period_year: int, period_month: int,
) -> dict:
    return accounting_service.group_financial_report(
        db, user=user, period_year=period_year, period_month=period_month
    )


@router.get("/financial-reports/{report_id}")
def get_financial_report(
    report_id: int, user: CurrentUser, db: DbSession
) -> dict:
    report = accounting_service.get_monthly_financial_report(db, user=user, report_id=report_id)
    return accounting_service.serialise_financial_report(report)


@router.post("/financial-reports", status_code=status.HTTP_201_CREATED)
def generate_financial_report(
    payload: FinancialReportGenerateRequest, request: Request,
    user: CurrentUser, db: DbSession,
) -> dict:
    """Draw the accounts for a company/month into a report draft (Table 57)."""
    ctx = audit_service.request_context(request)
    report = accounting_service.generate_monthly_financial_report(
        db, user=user, **payload.model_dump(), **ctx
    )
    return accounting_service.serialise_financial_report(report)


@router.patch("/financial-reports/{report_id}/analysis")
def update_financial_report_analysis(
    report_id: int, payload: FinancialReportAnalysisRequest, request: Request,
    user: CurrentUser, db: DbSession,
) -> dict:
    ctx = audit_service.request_context(request)
    report = accounting_service.update_report_analysis(
        db, user=user, report_id=report_id, analysis=payload.analysis, **ctx
    )
    return accounting_service.serialise_financial_report(report)


@router.post("/financial-reports/{report_id}/finalise")
def finalise_financial_report(
    report_id: int, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    ctx = audit_service.request_context(request)
    report = accounting_service.finalise_monthly_financial_report(
        db, user=user, report_id=report_id, **ctx
    )
    return accounting_service.serialise_financial_report(report)


@router.post("/financial-reports/{report_id}/archive")
def archive_financial_report(
    report_id: int, request: Request, user: CurrentUser, db: DbSession
) -> dict:
    ctx = audit_service.request_context(request)
    report = accounting_service.archive_monthly_financial_report(
        db, user=user, report_id=report_id, **ctx
    )
    return accounting_service.serialise_financial_report(report)
