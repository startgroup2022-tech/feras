"""D02: KPI target-versus-actual workflow.

These tests exercise the real service + API + persistence path (no mocks):

* a new definition is **inert** — an unapproved KPI reports no actual and no
  target comparison, so the platform never presents an invented number (D02);
* configuration (target, metric binding, direction) is recorded without
  activating anything;
* activation is the approval record: it stamps who/when and needs both a target
  and a metric binding;
* the actual is resolved live from the same source records the dashboard uses,
  and the variance is favourable-signed (``down`` metrics invert the sign);
* the drill-down returns the source records with no copy;
* everything is company-scoped behind ``kpi.read`` / ``kpi.manage``.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from tests.conftest import MONTH, YEAR


@pytest.fixture
def kpi_world(world, make_user):
    owner_all = make_user(
        "owner.kpi@corp.sa", "holding_owner", [world["alpha"], world["beta"]]
    )
    accountant = make_user(
        "acc.kpi@corp.sa", "accountant", [world["alpha"], world["beta"]]
    )
    data = dict(world)
    data["owner_all"] = owner_all
    data["accountant_all"] = accountant
    return data


def _create_kpi(client, auth, user, **overrides):
    body = {
        "code": "REV-TARGET",
        "name_ar": "هدف الإيراد",
        "data_source": "التقارير الشهرية",
        "calculation_method": "مجموع الإيراد المُعتمد",
        "period_label": "شهري",
        "company_id": None,
        "target_value": "1000000",
        "metric_key": "total_revenue",
    }
    body.update(overrides)
    return client.post("/api/v1/accounting/kpis", json=body, headers=auth(user))


# --------------------------------------------------------------------------
# inert until approved (D02)
# --------------------------------------------------------------------------
def test_new_kpi_is_inert_until_approved(client, kpi_world, auth):
    owner = kpi_world["owner_all"]
    created = _create_kpi(client, auth, owner)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["is_active"] is False
    assert body["approved_at"] is None

    evaluation = client.get(
        f"/api/v1/accounting/kpis/evaluations?year={YEAR}&month={MONTH}",
        headers=auth(owner),
    )
    assert evaluation.status_code == 200, evaluation.text
    row = next(r for r in evaluation.json() if r["code"] == "REV-TARGET")
    # Inert: no invented actual, no invented comparison.
    assert row["status"] == "pending"
    assert row["actual_value"] is None
    assert row["variance"] is None


def test_activation_requires_target_and_metric(client, kpi_world, auth):
    owner = kpi_world["owner_all"]
    kpi = _create_kpi(client, auth, owner, metric_key=None).json()

    response = client.post(
        f"/api/v1/accounting/kpis/{kpi['id']}/active",
        json={"active": True},
        headers=auth(owner),
    )
    assert response.status_code == 422, response.text


def test_activation_records_the_approval(client, kpi_world, auth):
    owner = kpi_world["owner_all"]
    kpi = _create_kpi(client, auth, owner).json()

    activated = client.post(
        f"/api/v1/accounting/kpis/{kpi['id']}/active",
        json={"active": True},
        headers=auth(owner),
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["is_active"] is True
    assert activated.json()["approved_at"] is not None


# --------------------------------------------------------------------------
# target vs actual + variance
# --------------------------------------------------------------------------
def test_actual_is_resolved_from_source_records(client, kpi_world, auth):
    owner = kpi_world["owner_all"]
    kpi = _create_kpi(client, auth, owner, target_value="1000000").json()
    client.post(
        f"/api/v1/accounting/kpis/{kpi['id']}/active",
        json={"active": True},
        headers=auth(owner),
    )

    row = next(
        r
        for r in client.get(
            f"/api/v1/accounting/kpis/evaluations?year={YEAR}&month={MONTH}",
            headers=auth(owner),
        ).json()
        if r["code"] == "REV-TARGET"
    )
    # world: alpha revenue 111111 + beta 999999 = 1111110.
    assert Decimal(row["actual_value"]) == Decimal("1111110")
    assert Decimal(row["variance"]) == Decimal("111110")
    assert row["favourable"] is True
    assert row["status"] == "active"


def test_down_direction_inverts_the_favourable_sign(client, kpi_world, auth):
    owner = kpi_world["owner_all"]
    # An expense target of 0: actual expenses (2.00) are above target, which for
    # a "down" metric is unfavourable.
    kpi = _create_kpi(
        client, auth, owner, code="EXP-TARGET", target_value="0",
        metric_key="total_expenses", direction="down",
    ).json()
    client.post(
        f"/api/v1/accounting/kpis/{kpi['id']}/active",
        json={"active": True},
        headers=auth(owner),
    )

    row = next(
        r
        for r in client.get(
            f"/api/v1/accounting/kpis/evaluations?year={YEAR}&month={MONTH}",
            headers=auth(owner),
        ).json()
        if r["code"] == "EXP-TARGET"
    )
    assert Decimal(row["actual_value"]) == Decimal("2")
    assert Decimal(row["variance"]) == Decimal("-2")
    assert row["favourable"] is False


def test_unknown_metric_key_is_rejected(client, kpi_world, auth):
    owner = kpi_world["owner_all"]
    response = _create_kpi(client, auth, owner, metric_key="not_a_metric")
    assert response.status_code == 422, response.text


# --------------------------------------------------------------------------
# drill-down (no copy)
# --------------------------------------------------------------------------
def test_sources_return_the_records_behind_the_actual(client, kpi_world, auth):
    owner = kpi_world["owner_all"]
    kpi = _create_kpi(client, auth, owner).json()
    client.post(
        f"/api/v1/accounting/kpis/{kpi['id']}/active",
        json={"active": True},
        headers=auth(owner),
    )

    response = client.get(
        f"/api/v1/accounting/kpis/{kpi['id']}/sources?year={YEAR}&month={MONTH}",
        headers=auth(owner),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["actual_value"] == "1111110.00"
    kinds = {s["kind"] for s in body["sources"]}
    assert kinds == {"monthly_report"}
    assert len(body["sources"]) == 2


# --------------------------------------------------------------------------
# scoping / RBAC
# --------------------------------------------------------------------------
def test_company_manager_cannot_manage_kpis(client, kpi_world, auth):
    manager = kpi_world["alpha_mgr"]
    response = _create_kpi(client, auth, manager, company_id=kpi_world["alpha"].id)
    assert response.status_code == 403, response.text


def test_company_scoped_kpi_is_hidden_from_another_company(client, kpi_world, auth):
    owner = kpi_world["owner_all"]
    _create_kpi(client, auth, owner, company_id=kpi_world["alpha"].id)

    listed = client.get(
        "/api/v1/accounting/kpis", headers=auth(kpi_world["beta_mgr"])
    ).json()
    assert all(k["company_id"] != kpi_world["alpha"].id for k in listed)


def test_deactivation_removes_the_actual(client, kpi_world, auth):
    owner = kpi_world["owner_all"]
    kpi = _create_kpi(client, auth, owner).json()
    client.post(
        f"/api/v1/accounting/kpis/{kpi['id']}/active",
        json={"active": True},
        headers=auth(owner),
    )
    client.post(
        f"/api/v1/accounting/kpis/{kpi['id']}/active",
        json={"active": False},
        headers=auth(owner),
    )
    row = next(
        r
        for r in client.get(
            f"/api/v1/accounting/kpis/evaluations?year={YEAR}&month={MONTH}",
            headers=auth(owner),
        ).json()
        if r["code"] == "REV-TARGET"
    )
    assert row["actual_value"] is None
    assert row["status"] == "pending"


# --------------------------------------------------------------------------
# S02/S10 goals-versus-results on the company dashboard
# --------------------------------------------------------------------------
def _activate(client, auth, user, kpi_id):
    response = client.post(
        f"/api/v1/accounting/kpis/{kpi_id}/active",
        json={"active": True},
        headers=auth(user),
    )
    assert response.status_code == 200, response.text


def test_company_dashboard_exposes_goals_versus_results(client, kpi_world, auth):
    """D02 unblocks S02/S10: an active company KPI with a target is a goal."""
    owner = kpi_world["owner_all"]
    alpha = kpi_world["alpha"].id
    kpi = _create_kpi(
        client, auth, owner, company_id=alpha, target_value="1000000"
    ).json()
    _activate(client, auth, owner, kpi["id"])

    dashboard = client.get(
        f"/api/v1/dashboard/holding?year={YEAR}&month={MONTH}", headers=auth(owner)
    ).json()
    row = next(r for r in dashboard["companies_performance"] if r["id"] == alpha)
    goal = next(g for g in row["goals"] if g["code"] == "REV-TARGET")
    assert Decimal(goal["actual_value"]) == Decimal("111111")  # alpha alone
    assert Decimal(goal["target_value"]) == Decimal("1000000")
    assert goal["favourable"] is False


def test_goals_omit_an_inactive_definition(client, kpi_world, auth):
    """An inert draft must not appear as a goal (D02)."""
    owner = kpi_world["owner_all"]
    alpha = kpi_world["alpha"].id
    _create_kpi(client, auth, owner, company_id=alpha, target_value="1000000")

    dashboard = client.get(
        f"/api/v1/dashboard/holding?year={YEAR}&month={MONTH}", headers=auth(owner)
    ).json()
    row = next(r for r in dashboard["companies_performance"] if r["id"] == alpha)
    assert row["goals"] == []


def test_goals_are_company_scoped(client, kpi_world, auth):
    """A company's goals never leak into another company's card."""
    owner = kpi_world["owner_all"]
    alpha = kpi_world["alpha"].id
    beta = kpi_world["beta"].id
    kpi = _create_kpi(
        client, auth, owner, company_id=alpha, target_value="1000000"
    ).json()
    _activate(client, auth, owner, kpi["id"])

    dashboard = client.get(
        f"/api/v1/dashboard/holding?year={YEAR}&month={MONTH}", headers=auth(owner)
    ).json()
    beta_row = next(r for r in dashboard["companies_performance"] if r["id"] == beta)
    assert beta_row["goals"] == []
