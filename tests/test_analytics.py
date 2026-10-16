"""Phase 7-8: advanced analytics and the executive briefing.

Two properties are asserted throughout: figures are derived from real rows (a
company with no report contributes zero, not a guess), and a company-scoped
caller only ever sees their own companies in every report family.
"""

from __future__ import annotations

from decimal import Decimal

from backend.db.models.enums import ReportStatus
from backend.db.models.report import MonthlyReport

BASE = "/api/v1/analytics"


def _add_prior_month(db, company, revenue="800000", expenses="500000", net="300000"):
    report = MonthlyReport(
        company_id=company.id,
        period_year=2027,
        period_month=9,
        status=ReportStatus.SUBMITTED.value,
        revenue=Decimal(revenue),
        expenses=Decimal(expenses),
        net_result=Decimal(net),
    )
    db.add(report)
    db.commit()
    return report


# --------------------------------------------------------------------------
# holding overview
# --------------------------------------------------------------------------
def test_holding_overview_trend_has_continuous_months(client, world, auth):
    body = client.get(f"{BASE}/holding?year=2027&month=10", headers=auth(world["owner"])).json()

    assert len(body["trend"]) == 12
    assert body["trend"][-1]["year"] == 2027
    assert body["trend"][-1]["month"] == 10
    # October revenue is the sum of both companies' reports.
    assert body["trend"][-1]["revenue"] == 1111110.0
    assert body["trend"][-1]["companies_reporting"] == 2
    # September is empty and must read as zero, not be omitted.
    assert body["trend"][-2]["revenue"] == 0.0


def test_holding_overview_compliance(client, world, auth, make_company):
    make_company("GAMMA", "شركة جاما")
    body = client.get(f"{BASE}/holding?year=2027&month=10", headers=auth(world["owner"])).json()

    compliance = body["compliance"]
    assert compliance["companies_total"] == 3
    assert compliance["companies_reported"] == 2
    assert compliance["companies_missing"] == 1
    assert compliance["compliance_pct"] == 66.7


def test_holding_overview_movers_need_a_baseline(client, world, auth, db):
    _add_prior_month(db, world["alpha"], revenue="1000000")
    body = client.get(f"{BASE}/holding?year=2027&month=10", headers=auth(world["owner"])).json()

    movers = body["movers"]["top"]
    alpha = next(m for m in movers if m["company_id"] == world["alpha"].id)
    # 111,111 vs 1,000,000 -> roughly -88.9%.
    assert alpha["change_pct"] == -88.9
    # Beta had no September report, so it cannot be ranked.
    assert all(m["company_id"] != world["beta"].id for m in body["movers"]["top"])


def test_scoped_user_sees_only_their_companies(client, world, auth):
    body = client.get(
        f"{BASE}/holding?year=2027&month=10", headers=auth(world["alpha_mgr"])
    )
    # A company manager has no ANALYTICS_HOLDING permission.
    assert body.status_code == 403


def test_investment_report_uses_reported_figures(client, world, auth):
    body = client.get(
        f"{BASE}/investments?year=2027&month=10", headers=auth(world["owner"])
    ).json()

    alpha = next(c for c in body["companies"] if c["company_id"] == world["alpha"].id)
    assert alpha["revenue"] == 111111.0
    assert alpha["net_result"] == 111110.0
    assert body["portfolio_revenue"] == 1111110.0
    assert body["opportunities_reported"] == 0


def test_investment_report_flags_opportunity_from_data(client, world, auth, db):
    report = db.get(MonthlyReport, world["alpha_report"].id)
    report.new_opportunities = "توسع في السوق الشمالي"
    db.add(report)
    db.commit()

    body = client.get(
        f"{BASE}/investments?year=2027&month=10", headers=auth(world["owner"])
    ).json()
    assert body["opportunities_reported"] == 1
    assert body["opportunity_companies"][0]["company_id"] == world["alpha"].id


# --------------------------------------------------------------------------
# operational report
# --------------------------------------------------------------------------
def test_operational_report_counts_support(client, world, auth):
    body = client.get(
        f"{BASE}/operations?year=2027&month=10", headers=auth(world["owner"])
    ).json()
    assert body["support_by_category"][0]["total"] == 2
    assert body["support_by_category"][0]["open"] == 2


def test_operational_report_requires_permission(client, world, auth):
    # The accountant holds ANALYTICS_OPERATIONS; a company manager does not.
    denied = client.get(
        f"{BASE}/operations?year=2027&month=10", headers=auth(world["alpha_mgr"])
    )
    assert denied.status_code == 403


# --------------------------------------------------------------------------
# compliance report
# --------------------------------------------------------------------------
def test_compliance_report_document_exposure(client, world, auth):
    body = client.get(
        f"{BASE}/compliance?year=2027&month=10", headers=auth(world["accountant"])
    ).json()
    assert body["documents"]["total"] == 0
    assert body["documents"]["expired"] == 0


# --------------------------------------------------------------------------
# executive briefing
# --------------------------------------------------------------------------
def test_briefing_is_grounded_and_deterministic_without_a_provider(client, world, auth):
    body = client.get(
        f"{BASE}/briefing?year=2027&month=10", headers=auth(world["owner"])
    ).json()

    # The default provider is "none", so the briefing is the deterministic one.
    assert body["provider"] == "none"
    assert body["degraded"] is True
    assert body["generated_from"] == "live_data"
    assert "1,111,110" in body["summary_ar"]
    assert body["highlights"]
    # Both companies reported, so no "missing report" risk is raised.
    assert all(r["key"] != "missing_reports" for r in body["risks"])


def test_briefing_raises_missing_report_risk(client, world, auth, make_company):
    make_company("GAMMA", "شركة جاما")
    body = client.get(
        f"{BASE}/briefing?year=2027&month=10", headers=auth(world["owner"])
    ).json()

    keys = {r["key"] for r in body["risks"]}
    assert "missing_reports" in keys
    actions = {a["key"] for a in body["recommended_actions"]}
    assert "chase_reports" in actions


def test_briefing_denied_for_a_user_with_no_analytics_at_all(client, world, auth, make_user):
    # An employee holds no analytics permission.
    outsider = make_user("emp@corp.sa", "employee")
    denied = client.get(
        f"{BASE}/briefing?year=2027&month=10", headers=auth(outsider)
    )
    assert denied.status_code == 403


def test_executive_context_is_permission_shaped(db, world):
    """Group analytics enter the context only for a user permitted to read them."""
    from backend.services.executive_intelligence_service import build_executive_context

    owner_ctx = build_executive_context(db, user=world["owner"], year=2027, month=10)
    manager_ctx = build_executive_context(
        db, user=world["alpha_mgr"], year=2027, month=10
    )

    assert "trend" in owner_ctx
    assert "sectors" in owner_ctx
    # A company manager never receives group analytics in the prompt.
    assert "trend" not in manager_ctx
    assert "sectors" not in manager_ctx
    # But both see the KPI block and the data-driven insights.
    assert "kpis" in manager_ctx
    assert "insights" in manager_ctx

