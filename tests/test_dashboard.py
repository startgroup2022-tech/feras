"""Holding executive dashboard: KPI aggregation and attention surfacing."""

from __future__ import annotations

from backend.db.models.enums import SupportStatus

HOLDING = "/api/v1/dashboard/holding?year=2027&month=10"


def test_holding_kpis_aggregate_the_group(client, world, auth):
    body = client.get(HOLDING, headers=auth(world["owner"])).json()

    kpis = body["kpis"]
    assert body["scope"] == "holding"
    assert kpis["companies_count"] == 2
    assert kpis["reports_submitted"] == 2
    assert kpis["total_revenue"] == "1111110.00"
    assert kpis["total_expenses"] == "2.00"
    assert kpis["total_net_result"] == "1111108.00"


def test_drafts_are_excluded_from_group_totals(client, world, auth):
    client.post(
        "/api/v1/monthly-reports",
        headers=auth(world["alpha_mgr"]),
        json={
            "company_id": world["alpha"].id,
            "period_year": 2027,
            "period_month": 11,
            "revenue": "5000000",
            "expenses": "1",
        },
    )

    body = client.get(HOLDING, headers=auth(world["owner"])).json()

    # The 5,000,000 draft for another month must not leak into October.
    assert body["kpis"]["total_revenue"] == "1111110.00"


def test_missing_reports_are_listed(client, world, auth, make_company):
    gamma = make_company("GAMMA", "شركة جاما")

    body = client.get(HOLDING, headers=auth(world["owner"])).json()

    assert body["kpis"]["reports_submitted"] == 2
    assert body["kpis"]["reports_missing"] == 1
    assert [c["code"] for c in body["companies_missing_report"]] == ["GAMMA"]


def test_open_support_requests_are_counted(client, world, auth):
    body = client.get(HOLDING, headers=auth(world["owner"])).json()

    assert body["kpis"]["open_support_requests"] == 2


def test_closed_requests_are_not_counted_as_open(client, world, auth, db):
    from backend.db.models.support import SupportRequest

    request = db.get(SupportRequest, world["alpha_req"].id)
    request.status = SupportStatus.CLOSED.value
    db.add(request)
    db.commit()

    body = client.get(HOLDING, headers=auth(world["owner"])).json()

    assert body["kpis"]["open_support_requests"] == 1


# --------------------------------------------------------------------------
# companies requiring attention
# --------------------------------------------------------------------------
def test_attention_flags_low_health_company(client, world, auth, make_company):
    make_company("SICKCO", "شركة متعثرة", health="attention")

    body = client.get(HOLDING, headers=auth(world["owner"])).json()

    attention = body["companies_requiring_attention"]
    assert body["kpis"]["companies_requiring_attention"] == 1
    assert attention[0]["code"] == "SICKCO"
    assert attention[0]["reason"] == "مؤشر صحة الشركة منخفض"


def test_attention_flags_reported_major_problems(client, world, auth, make_company, make_report):
    delta = make_company("DELTA", "شركة دلتا", health="stable")
    make_report(delta, major_problems="تأخر تحصيل الذمم المدينة")

    body = client.get(HOLDING, headers=auth(world["owner"])).json()

    attention = body["companies_requiring_attention"]
    assert len(attention) == 1
    assert attention[0]["code"] == "DELTA"
    assert attention[0]["reason"] == "تأخر تحصيل الذمم المدينة"


def test_attention_includes_requested_support(client, world, auth, db, make_company, make_report):
    delta = make_company("DELTA", "شركة دلتا", health="attention")
    report = make_report(delta)
    report.support_required = "دعم في التسويق الرقمي"
    db.add(report)
    db.commit()

    body = client.get(HOLDING, headers=auth(world["owner"])).json()

    attention = body["companies_requiring_attention"][0]
    assert attention["support_required"] == "دعم في التسويق الرقمي"


def test_healthy_companies_are_not_flagged(client, world, auth):
    body = client.get(HOLDING, headers=auth(world["owner"])).json()

    assert body["companies_requiring_attention"] == []


# --------------------------------------------------------------------------
# company-scoped dashboard
# --------------------------------------------------------------------------
def test_company_dashboard_is_scoped(client, world, auth):
    body = client.get(
        f"/api/v1/dashboard/company/{world['alpha'].id}?year=2027&month=10",
        headers=auth(world["alpha_mgr"]),
    ).json()

    assert body["scope"] == "company"
    assert body["company_id"] == world["alpha"].id
    assert body["kpis"]["total_revenue"] == "111111.00"
    assert [c["code"] for c in body["companies"]] == ["ALPHA"]


def test_dashboard_defaults_to_the_current_period(client, world, auth):
    body = client.get("/api/v1/dashboard/holding", headers=auth(world["owner"])).json()

    assert "period_year" in body and "period_month" in body


def test_manager_cannot_open_the_holding_dashboard(client, world, auth):
    assert client.get(HOLDING, headers=auth(world["alpha_mgr"])).status_code == 403


def test_marketing_can_open_the_holding_dashboard(client, auth, make_user):
    marketer = make_user("mkt@corp.sa", "marketing")

    assert client.get(HOLDING, headers=auth(marketer)).status_code == 200
