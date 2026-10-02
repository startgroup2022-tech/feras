"""Phase 2 dashboard enrichment: month-over-month change, per-company
performance, and the data-driven AI insights endpoint.
"""

from __future__ import annotations

from decimal import Decimal

from backend.db.models.enums import CompanyHealth, ReportStatus
from backend.db.models.report import MonthlyReport

HOLDING = "/api/v1/dashboard/holding?year=2027&month=10"
INSIGHTS = "/api/v1/ai/insights?year=2027&month=10"


def _prior_month_report(db, company, revenue="800000", expenses="500000", net="300000"):
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
# month-over-month
# --------------------------------------------------------------------------
def test_change_is_null_without_previous_data(client, world, auth):
    body = client.get(HOLDING, headers=auth(world["owner"])).json()

    change = body["change_vs_previous"]
    assert change["previous_month"] == 9
    # No September data -> "no baseline", distinct from "flat".
    assert change["revenue_pct"] is None
    assert change["net_pct"] is None


def test_change_computes_percentage(client, world, auth, db):
    # October revenue is 1,111,110; add September revenue of 1,000,000.
    _prior_month_report(db, world["alpha"], revenue="1000000")
    _prior_month_report(db, world["beta"], revenue="0")

    body = client.get(HOLDING, headers=auth(world["owner"])).json()
    change = body["change_vs_previous"]

    assert Decimal(change["revenue_previous"]) == Decimal("1000000.00")
    assert change["revenue_pct"] == 11.1


def test_performance_rows_include_every_company(client, world, auth, make_company):
    make_company("GAMMA", "شركة جاما", health=CompanyHealth.WATCH.value)

    body = client.get(HOLDING, headers=auth(world["owner"])).json()
    perf = {row["code"]: row for row in body["companies_performance"]}

    assert set(perf) == {"ALPHA", "BETA", "GAMMA"}
    assert perf["ALPHA"]["has_report"] is True
    assert perf["GAMMA"]["has_report"] is False
    assert perf["GAMMA"]["revenue"] is None
    assert perf["ALPHA"]["revenue"] == "111111.00"


def test_performance_growth_versus_previous_month(client, world, auth, db):
    _prior_month_report(db, world["alpha"], revenue="100000")

    body = client.get(HOLDING, headers=auth(world["owner"])).json()
    perf = {row["code"]: row for row in body["companies_performance"]}

    # 111,111 vs 100,000 -> +11.1%
    assert perf["ALPHA"]["revenue_pct"] == 11.1
    # Beta had no September report -> growth unknown, not zero.
    assert perf["BETA"]["revenue_pct"] is None


def test_company_scope_dashboard_is_isolated(client, world, auth):
    body = client.get(
        f"/api/v1/dashboard/company/{world['alpha'].id}?year=2027&month=10",
        headers=auth(world["alpha_mgr"]),
    ).json()

    assert body["scope"] == "company"
    assert body["kpis"]["companies_count"] == 1
    assert body["kpis"]["total_revenue"] == "111111.00"


def test_company_scope_performance_only_own_company(client, world, auth):
    body = client.get(
        f"/api/v1/dashboard/company/{world['alpha'].id}?year=2027&month=10",
        headers=auth(world["alpha_mgr"]),
    ).json()

    assert [row["code"] for row in body["companies_performance"]] == ["ALPHA"]


# --------------------------------------------------------------------------
# AI insights
# --------------------------------------------------------------------------
def test_insights_returns_four_observations(client, world, auth):
    body = client.get(INSIGHTS, headers=auth(world["owner"])).json()

    assert [row["key"] for row in body] == [
        "revenue_change",
        "attention",
        "opportunity",
        "financial_review",
    ]
    # Every insight carries both languages and a tone.
    for row in body:
        assert row["title_ar"] and row["title_en"]
        assert row["detail_ar"] and row["detail_en"]
        assert row["tone"] in {"up", "down", "warn", "risk", "gold", "neutral"}


def test_revenue_insight_reflects_real_change(client, world, auth, db):
    _prior_month_report(db, world["alpha"], revenue="1000000")
    _prior_month_report(db, world["beta"], revenue="0")

    body = client.get(INSIGHTS, headers=auth(world["owner"])).json()
    revenue = next(r for r in body if r["key"] == "revenue_change")

    assert revenue["tone"] == "up"
    assert revenue["metric"] == "+11.1%"


def test_revenue_insight_is_neutral_without_baseline(client, world, auth):
    body = client.get(INSIGHTS, headers=auth(world["owner"])).json()
    revenue = next(r for r in body if r["key"] == "revenue_change")

    assert revenue["tone"] == "neutral"


def test_attention_insight_names_the_company(client, world, auth, db):
    alpha = db.get(type(world["alpha"]), world["alpha"].id)
    alpha.health = CompanyHealth.ATTENTION.value
    db.add(alpha)
    db.commit()

    body = client.get(INSIGHTS, headers=auth(world["owner"])).json()
    attention = next(r for r in body if r["key"] == "attention")

    assert attention["tone"] == "warn"
    assert "ألفا" in attention["detail_ar"]


def test_opportunity_insight_uses_reported_opportunity(client, world, auth, db):
    report = db.get(MonthlyReport, world["alpha_report"].id)
    report.new_opportunities = "توسّع في السوق الشمالي"
    db.add(report)
    db.commit()

    body = client.get(INSIGHTS, headers=auth(world["owner"])).json()
    opportunity = next(r for r in body if r["key"] == "opportunity")

    assert opportunity["tone"] == "gold"
    assert "السوق الشمالي" in opportunity["detail_ar"]


def test_opportunity_insight_absent_when_none_reported(client, world, auth):
    body = client.get(INSIGHTS, headers=auth(world["owner"])).json()
    opportunity = next(r for r in body if r["key"] == "opportunity")

    assert opportunity["tone"] == "neutral"


def test_financial_review_insight_flags_missing_reports(
    client, world, auth, make_company
):
    make_company("GAMMA", "شركة جاما")

    body = client.get(INSIGHTS, headers=auth(world["owner"])).json()
    financial = next(r for r in body if r["key"] == "financial_review")

    assert financial["tone"] == "risk"


def test_insights_are_company_scoped(client, world, auth, db):
    """A company user must not see another company named in the insights."""
    alpha = db.get(type(world["alpha"]), world["alpha"].id)
    alpha.health = CompanyHealth.ATTENTION.value
    db.add(alpha)
    db.commit()

    body = client.get(
        "/api/v1/ai/insights?year=2027&month=10",
        headers=auth(world["beta_mgr"]),
    ).json()
    attention = next(r for r in body if r["key"] == "attention")

    assert "ألفا" not in attention["detail_ar"]
