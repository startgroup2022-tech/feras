"""Role dashboards (S01 / deck slides 7-11).

Spec §7 S01: "لكل دور ملخص من سجلاته فقط" -- each role's dashboard summarises
only the records it may read. These tests pin that each primary role gets its
own tile set (not the holding strip), that the tiles come from real rows, and
that a company-scoped manager never sees another company's figures.
"""

from __future__ import annotations

from datetime import date, timedelta

from backend.db.models.enums import LeadStatus, TaskLifecycleStatus
from backend.db.models.operations import Task
from backend.db.models.website import WebsiteLead

HOLDING = "/api/v1/dashboard/holding?year=2027&month=10"
COMPANY = "/api/v1/dashboard/company/{cid}?year=2027&month=10"


def _keys(summary: dict) -> list[str]:
    return [kpi["key"] for kpi in summary["kpis"]]


def _values(summary: dict) -> dict[str, str]:
    return {kpi["key"]: kpi["value"] for kpi in summary["kpis"]}


def _make_lead(db, *, status: str, reference: str) -> WebsiteLead:
    lead = WebsiteLead(
        reference=reference,
        source="website",
        market="bahrain",
        service_type="general",
        locale="ar",
        full_name="عميل محتمل",
        email="lead@example.com",
        consent_given=True,
        status=status,
        priority="normal",
        created_at=date(2027, 10, 5),
    )
    db.add(lead)
    db.commit()
    return lead


def test_owner_gets_the_holding_role_summary(client, world, auth):
    body = client.get(HOLDING, headers=auth(world["owner"])).json()

    summary = body["role_summary"]
    assert summary is not None
    assert _keys(summary) == [
        "profit_trend",
        "operating_cash",
        "liquidity_risk",
        "pending_decisions",
    ]
    # The deck's slide-7 heading and greeting line, not the holding one.
    assert summary["title_ar"] == "لوحة القيادة للمجموعة"
    assert summary["greeting_ar"].startswith("مرحبًا المالك")


def test_company_manager_summary_is_company_scoped(client, world, auth):
    body = client.get(
        COMPANY.format(cid=world["alpha"].id), headers=auth(world["alpha_mgr"])
    ).json()

    summary = body["role_summary"]
    assert summary is not None
    # The deck's fourth manager tile (prospective clients) is gated on
    # ``website_lead.read``, which the company_manager role deliberately does
    # not hold (see test_company_manager_cannot_see_website_leads). The tile is
    # therefore absent rather than faked, and appears automatically if that
    # boundary is ever relaxed.
    assert _keys(summary) == ["month_result", "cash_balance", "support_requests"]
    # The manager's own report (net 111110) drives the month result; beta's
    # 999998 must never leak into the company tile.
    assert _values(summary)["month_result"] == "0.1"


def test_manager_support_tile_counts_only_its_own_company(client, world, auth):
    body = client.get(
        COMPANY.format(cid=world["alpha"].id), headers=auth(world["alpha_mgr"])
    ).json()
    # alpha has one open request; beta's must not be added.
    assert _values(body["role_summary"])["support_requests"] == "1"


def test_specialist_summary_counts_own_tasks_only(client, world, auth, db, make_user):
    designer = make_user("design@corp.sa", "designer")
    db.add(
        Task(
            company_id=world["alpha"].id,
            title="تصميم",
            status=TaskLifecycleStatus.IN_PROGRESS.value,
            priority="normal",
            assignee_id=designer.id,
            due_date=date.today() - timedelta(days=2),
        )
    )
    # Someone else's task must not appear on the designer's strip.
    db.add(
        Task(
            company_id=world["alpha"].id,
            title="مهمة أخرى",
            status=TaskLifecycleStatus.IN_PROGRESS.value,
            priority="normal",
            assignee_id=world["owner"].id,
        )
    )
    db.commit()

    body = client.get(HOLDING, headers=auth(designer)).json()
    summary = body["role_summary"]
    assert summary is not None
    assert _keys(summary) == [
        "my_open_tasks",
        "overdue",
        "awaiting_info",
        "completed_month",
    ]
    assert _values(summary)["my_open_tasks"] == "1"
    assert _values(summary)["overdue"] == "1"


def test_sales_summary_reflects_the_lead_funnel(client, world, auth, db, make_user):
    marketing = make_user("marketing@corp.sa", "marketing")
    _make_lead(db, status=LeadStatus.NEW.value, reference="L-NEW")
    _make_lead(db, status=LeadStatus.QUALIFIED.value, reference="L-QUAL")

    body = client.get(HOLDING, headers=auth(marketing)).json()
    summary = body["role_summary"]
    assert summary is not None
    assert _keys(summary) == [
        "new_leads",
        "awaiting_contact",
        "qualified_leads",
        "follow_up_week",
    ]
    assert _values(summary)["qualified_leads"] == "1"
    assert _values(summary)["awaiting_contact"] == "1"


def test_bd_summary_has_its_own_tile_set(client, world, auth, make_user):
    bd = make_user("bd@corp.sa", "business_development")

    body = client.get(HOLDING, headers=auth(bd)).json()
    summary = body["role_summary"]
    assert summary is not None
    assert _keys(summary) == [
        "awaiting_assignment",
        "tasks_in_progress",
        "active_opportunities",
        "reports_follow_up",
    ]


def test_roles_without_a_deck_dashboard_keep_the_holding_strip(client, world, auth):
    # The accountant has no slide in the deck's role set; the strip stays.
    body = client.get(HOLDING, headers=auth(world["accountant"])).json()
    assert body["role_summary"] is None
