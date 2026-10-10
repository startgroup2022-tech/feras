"""Execution 02: financial summary, accountant approval and correction engine.

Covers the spec sections that carry acceptance criteria: the state machine
(14.1), the calculation rules (15.1), role separation (S05/S06/S08), the
effective-version reporting rule (S10) and the bank-statement security (F-03).
"""

from __future__ import annotations

import pytest

from backend.db.models.enums import FinancialSummaryStatus

YEAR, MONTH = 2027, 10

PDF = b"%PDF-1.4 bank statement"


def _create(client, auth, world, *, company=None, year=YEAR, month=MONTH, **figures):
    body = {"company_id": (company or world["alpha"]).id, "period_year": year, "period_month": month}
    body.update(figures)
    return client.post("/api/v1/financial/summaries", headers=auth(world["alpha_mgr"]), json=body)


def _upload(client, auth, user, version_id, tmp_path, monkeypatch, data=PDF):
    from backend.core.config import settings

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    return client.post(
        f"/api/v1/financial/summaries/{version_id}/bank-statement",
        headers=auth(user),
        files={"file": ("statement.pdf", data, "application/pdf")},
    )


# --------------------------------------------------------------------------
# lifecycle
# --------------------------------------------------------------------------
def test_manager_creates_a_draft(client, financial_world, auth):
    world = financial_world
    response = _create(client, auth, world, submitted_revenue="1000", submitted_expenses="600")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == FinancialSummaryStatus.DRAFT.value
    assert body["version_number"] == 1
    assert body["company_id"] == world["alpha"].id


def test_cannot_create_a_second_summary_for_the_same_month(client, financial_world, auth):
    world = financial_world
    _create(client, auth, world)
    again = _create(client, auth, world)
    assert again.status_code == 409


def test_manager_cannot_create_for_another_company(client, financial_world, auth):
    world = financial_world
    response = _create(client, auth, world, company=world["beta"])
    assert response.status_code == 403


def test_submission_requires_a_bank_statement(client, financial_world, auth):
    world = financial_world
    version = _create(client, auth, world, submitted_revenue="100", submitted_expenses="50").json()

    response = client.post(
        f"/api/v1/financial/summaries/{version['id']}/submit", headers=auth(world["alpha_mgr"])
    )
    assert response.status_code == 422


def test_submit_then_accountant_approves(client, financial_world, auth, tmp_path, monkeypatch):
    world = financial_world
    version = _create(client, auth, world, submitted_revenue="1000", submitted_expenses="600").json()
    _upload(client, auth, world["alpha_mgr"], version["id"], tmp_path, monkeypatch)

    submitted = client.post(
        f"/api/v1/financial/summaries/{version['id']}/submit", headers=auth(world["alpha_mgr"])
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == FinancialSummaryStatus.SUBMITTED.value

    approved = client.post(
        f"/api/v1/financial/summaries/{version['id']}/approve", headers=auth(world["accountant"])
    )
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["status"] == FinancialSummaryStatus.APPROVED.value
    # Original entered figures are preserved, never overwritten.
    assert body["submitted_revenue"] == "1000.00"
    assert body["submitted_expenses"] == "600.00"


def test_accountant_cannot_edit_the_manager_figures(client, financial_world, auth, tmp_path, monkeypatch):
    world = financial_world
    version = _create(client, auth, world, submitted_revenue="1000", submitted_expenses="600").json()
    _upload(client, auth, world["alpha_mgr"], version["id"], tmp_path, monkeypatch)
    client.post(f"/api/v1/financial/summaries/{version['id']}/submit", headers=auth(world["alpha_mgr"]))

    # The accountant holds no update permission on the summary itself.
    response = client.patch(
        f"/api/v1/financial/summaries/{version['id']}",
        headers=auth(world["accountant"]),
        json={"submitted_revenue": "1"},
    )
    assert response.status_code == 403


def test_return_requires_a_note(client, financial_world, auth, tmp_path, monkeypatch):
    world = financial_world
    version = _create(client, auth, world, submitted_revenue="10", submitted_expenses="5").json()
    _upload(client, auth, world["alpha_mgr"], version["id"], tmp_path, monkeypatch)
    client.post(f"/api/v1/financial/summaries/{version['id']}/submit", headers=auth(world["alpha_mgr"]))

    response = client.post(
        f"/api/v1/financial/summaries/{version['id']}/return",
        headers=auth(world["accountant"]),
        json={"note": "   "},
    )
    assert response.status_code == 422


def test_return_then_resubmit_keeps_a_single_version(client, financial_world, auth, tmp_path, monkeypatch):
    world = financial_world
    version = _create(client, auth, world, submitted_revenue="100", submitted_expenses="50").json()
    _upload(client, auth, world["alpha_mgr"], version["id"], tmp_path, monkeypatch)
    client.post(f"/api/v1/financial/summaries/{version['id']}/submit", headers=auth(world["alpha_mgr"]))

    returned = client.post(
        f"/api/v1/financial/summaries/{version['id']}/return",
        headers=auth(world["accountant"]),
        json={"note": "أضف كشف البنك لشهر أكتوبر"},
    )
    assert returned.status_code == 200
    assert returned.json()["status"] == FinancialSummaryStatus.CORRECTION_REQUIRED.value
    assert returned.json()["return_note"].startswith("أضف كشف")

    # The manager edits in place and resubmits: still a single version.
    client.patch(
        f"/api/v1/financial/summaries/{version['id']}",
        headers=auth(world["alpha_mgr"]),
        json={"submitted_revenue": "120"},
    )
    resubmitted = client.post(
        f"/api/v1/financial/summaries/{version['id']}/submit", headers=auth(world["alpha_mgr"])
    )
    assert resubmitted.status_code == 200
    assert resubmitted.json()["version_number"] == 1
    assert resubmitted.json()["return_note"] is None

    pending = client.get("/api/v1/financial/summaries/pending", headers=auth(world["accountant"])).json()
    assert len([p for p in pending if p["period_id"] == resubmitted.json()["period_id"]]) == 1


def test_double_approve_is_rejected(client, financial_world, auth, tmp_path, monkeypatch):
    world = financial_world
    version = _create(client, auth, world, submitted_revenue="10", submitted_expenses="5").json()
    _upload(client, auth, world["alpha_mgr"], version["id"], tmp_path, monkeypatch)
    client.post(f"/api/v1/financial/summaries/{version['id']}/submit", headers=auth(world["alpha_mgr"]))
    client.post(f"/api/v1/financial/summaries/{version['id']}/approve", headers=auth(world["accountant"]))

    again = client.post(
        f"/api/v1/financial/summaries/{version['id']}/approve", headers=auth(world["accountant"])
    )
    assert again.status_code == 409


def test_draft_cannot_be_approved(client, financial_world, auth):
    world = financial_world
    version = _create(client, auth, world, submitted_revenue="10", submitted_expenses="5").json()
    response = client.post(
        f"/api/v1/financial/summaries/{version['id']}/approve", headers=auth(world["accountant"])
    )
    assert response.status_code == 409


# --------------------------------------------------------------------------
# calculation rules (section 15.1)
# --------------------------------------------------------------------------
def test_mandatory_calculation_example(client, financial_world, auth):
    """1000 revenue, 600 expense; 50 expense INCLUDED, 20 expense ADDED,
    200 transfer (OTHER). Effective = 620 expenses, result 380."""
    world = financial_world
    version = _create(client, auth, world, submitted_revenue="1000", submitted_expenses="600").json()
    vid = version["id"]

    for item in (
        {"name_ar": "بند مشمول", "name_en": "Included expense", "amount": "50", "kind": "expense", "inclusion_rule": "included"},
        {"name_ar": "بند مضاف", "name_en": "Added expense", "amount": "20", "kind": "expense", "inclusion_rule": "added"},
        {"name_ar": "تحويل", "name_en": "Transfer", "amount": "200", "kind": "other", "inclusion_rule": "added"},
    ):
        assert client.post(
            f"/api/v1/financial/summaries/{vid}/items", headers=auth(world["alpha_mgr"]), json=item
        ).status_code == 201

    detail = client.get(f"/api/v1/financial/summaries/{vid}", headers=auth(world["alpha_mgr"])).json()
    assert detail["effective_expenses"] == "620.00"
    assert detail["effective_revenue"] == "1000.00"  # the transfer is not revenue
    assert detail["calculated_result"] == "380.00"


def test_included_item_is_not_double_counted(client, financial_world, auth):
    world = financial_world
    version = _create(client, auth, world, submitted_revenue="1000", submitted_expenses="600").json()
    client.post(
        f"/api/v1/financial/summaries/{version['id']}/items",
        headers=auth(world["alpha_mgr"]),
        json={"name_ar": "مشمول", "name_en": "Included", "amount": "50", "kind": "expense", "inclusion_rule": "included"},
    )
    detail = client.get(f"/api/v1/financial/summaries/{version['id']}", headers=auth(world["alpha_mgr"])).json()
    assert detail["effective_expenses"] == "600.00"


def test_added_revenue_increases_the_result(client, financial_world, auth):
    world = financial_world
    version = _create(client, auth, world, submitted_revenue="100", submitted_expenses="40").json()
    client.post(
        f"/api/v1/financial/summaries/{version['id']}/items",
        headers=auth(world["alpha_mgr"]),
        json={"name_ar": "إيراد إضافي", "name_en": "Extra revenue", "amount": "10", "kind": "revenue", "inclusion_rule": "added"},
    )
    detail = client.get(f"/api/v1/financial/summaries/{version['id']}", headers=auth(world["alpha_mgr"])).json()
    assert detail["effective_revenue"] == "110.00"
    assert detail["calculated_result"] == "70.00"


def test_closing_balances_are_independent_of_the_result(client, financial_world, auth):
    world = financial_world
    version = _create(
        client, auth, world,
        submitted_revenue="1000", submitted_expenses="1200",
        closing_bank_balance="700", closing_cash_balance="30",
    ).json()
    detail = client.get(f"/api/v1/financial/summaries/{version['id']}", headers=auth(world["alpha_mgr"])).json()
    assert detail["calculated_result"] == "-200.00"  # a loss is legitimate
    assert detail["calculated_total_cash"] == "730.00"


def test_cross_currency_item_is_rejected(client, financial_world, auth):
    world = financial_world
    version = _create(client, auth, world, submitted_revenue="1000", submitted_expenses="600").json()
    response = client.post(
        f"/api/v1/financial/summaries/{version['id']}/items",
        headers=auth(world["alpha_mgr"]),
        json={"name_ar": "بند", "name_en": "Item", "amount": "5", "kind": "expense", "inclusion_rule": "added", "currency": "USD"},
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------
# historical correction engine
# --------------------------------------------------------------------------
def test_correction_links_to_original_and_preserves_it(client, financial_world, auth, tmp_path, monkeypatch):
    world = financial_world
    version = _create(client, auth, world, submitted_revenue="1000", submitted_expenses="600").json()
    _upload(client, auth, world["alpha_mgr"], version["id"], tmp_path, monkeypatch)
    client.post(f"/api/v1/financial/summaries/{version['id']}/submit", headers=auth(world["alpha_mgr"]))
    client.post(f"/api/v1/financial/summaries/{version['id']}/approve", headers=auth(world["accountant"]))

    correction = client.post(
        f"/api/v1/financial/periods/{version['period_id']}/corrections",
        headers=auth(world["alpha_mgr"]),
    )
    assert correction.status_code == 201, correction.text
    body = correction.json()
    assert body["version_number"] == 2
    assert body["corrects_version_id"] == version["id"]
    assert body["status"] == FinancialSummaryStatus.DRAFT.value

    # The original approved version is unchanged.
    original = client.get(f"/api/v1/financial/summaries/{version['id']}", headers=auth(world["accountant"])).json()
    assert original["status"] == FinancialSummaryStatus.APPROVED.value
    assert original["submitted_revenue"] == "1000.00"


def test_effective_version_only_moves_when_the_correction_is_approved(client, financial_world, auth, tmp_path, monkeypatch):
    world = financial_world
    version = _create(client, auth, world, submitted_revenue="1000", submitted_expenses="600").json()
    _upload(client, auth, world["alpha_mgr"], version["id"], tmp_path, monkeypatch)
    client.post(f"/api/v1/financial/summaries/{version['id']}/submit", headers=auth(world["alpha_mgr"]))
    client.post(f"/api/v1/financial/summaries/{version['id']}/approve", headers=auth(world["accountant"]))

    correction = client.post(
        f"/api/v1/financial/periods/{version['period_id']}/corrections",
        headers=auth(world["alpha_mgr"]),
    ).json()
    # Before the correction is approved, the original stays effective: the
    # report must not count two versions.
    report_before = client.get(
        f"/api/v1/financial/report?year={YEAR}&month={MONTH}", headers=auth(world["owner"])
    ).json()
    alpha_row = next(r for r in report_before["companies"] if r["company_id"] == world["alpha"].id)
    assert alpha_row["effective_version_id"] == version["id"]

    client.patch(
        f"/api/v1/financial/summaries/{correction['id']}",
        headers=auth(world["alpha_mgr"]),
        json={"submitted_revenue": "2000"},
    )
    _upload(client, auth, world["alpha_mgr"], correction["id"], tmp_path, monkeypatch)
    client.post(f"/api/v1/financial/summaries/{correction['id']}/submit", headers=auth(world["alpha_mgr"]))
    client.post(f"/api/v1/financial/summaries/{correction['id']}/approve", headers=auth(world["accountant"]))

    report_after = client.get(
        f"/api/v1/financial/report?year={YEAR}&month={MONTH}", headers=auth(world["owner"])
    ).json()
    alpha_row = next(r for r in report_after["companies"] if r["company_id"] == world["alpha"].id)
    assert alpha_row["effective_version_id"] == correction["id"]
    # Exactly one effective version contributes: 2000, not 3000.
    assert report_after["totals"]["effective_revenue"] == "2000.00"


# --------------------------------------------------------------------------
# role separation and isolation
# --------------------------------------------------------------------------
def test_business_development_reads_but_cannot_edit(client, financial_world, auth, tmp_path, monkeypatch):
    world = financial_world
    version = _create(client, auth, world, submitted_revenue="1000", submitted_expenses="600").json()
    _upload(client, auth, world["alpha_mgr"], version["id"], tmp_path, monkeypatch)

    # BD may read the summary.
    assert client.get(
        f"/api/v1/financial/summaries/{version['id']}", headers=auth(world["bd"])
    ).status_code == 200
    # But may not edit it, submit it, or open the private bank statement.
    assert client.patch(
        f"/api/v1/financial/summaries/{version['id']}", headers=auth(world["bd"]), json={"submitted_revenue": "1"}
    ).status_code == 403
    detail = client.get(f"/api/v1/financial/summaries/{version['id']}", headers=auth(world["alpha_mgr"])).json()
    attachment_id = detail["bank_attachments"][0]["id"]
    assert client.get(
        f"/api/v1/financial/summaries/{version['id']}/bank-statement/{attachment_id}",
        headers=auth(world["bd"]),
    ).status_code == 403


def test_manager_cannot_see_another_companys_summary(client, financial_world, auth):
    world = financial_world
    version = _create(client, auth, world, submitted_revenue="10", submitted_expenses="5").json()
    # beta's manager asking for alpha's summary gets a 404 (IDOR protection).
    assert client.get(
        f"/api/v1/financial/summaries/{version['id']}", headers=auth(world["beta_mgr"])
    ).status_code == 404
    assert client.post(
        f"/api/v1/financial/summaries/{version['id']}/approve", headers=auth(world["beta_mgr"])
    ).status_code == 403


def test_accountant_holds_no_create_permission(client, financial_world, auth):
    world = financial_world
    response = _create(client, auth, world, submitted_revenue="10", submitted_expenses="5")
    assert response.status_code == 201  # created by the manager
    # The accountant cannot create a summary for a company they do not manage.
    response = client.post(
        "/api/v1/financial/summaries",
        headers=auth(world["accountant"]),
        json={"company_id": world["beta"].id, "period_year": YEAR, "period_month": 11},
    )
    assert response.status_code == 403


# --------------------------------------------------------------------------
# bank statement security
# --------------------------------------------------------------------------
def test_bank_statement_is_downloadable_by_the_accountant(client, financial_world, auth, tmp_path, monkeypatch):
    world = financial_world
    version = _create(client, auth, world, submitted_revenue="10", submitted_expenses="5").json()
    _upload(client, auth, world["alpha_mgr"], version["id"], tmp_path, monkeypatch)
    detail = client.get(f"/api/v1/financial/summaries/{version['id']}", headers=auth(world["alpha_mgr"])).json()
    attachment_id = detail["bank_attachments"][0]["id"]

    response = client.get(
        f"/api/v1/financial/summaries/{version['id']}/bank-statement/{attachment_id}",
        headers=auth(world["accountant"]),
    )
    assert response.status_code == 200
    assert response.content == PDF


def test_bank_statement_storage_key_is_never_exposed(client, financial_world, auth, tmp_path, monkeypatch):
    world = financial_world
    version = _create(client, auth, world, submitted_revenue="10", submitted_expenses="5").json()
    _upload(client, auth, world["alpha_mgr"], version["id"], tmp_path, monkeypatch)
    detail = client.get(f"/api/v1/financial/summaries/{version['id']}", headers=auth(world["alpha_mgr"])).json()
    assert "storage_key" not in detail["bank_attachments"][0]


def test_disallowed_bank_statement_type_is_rejected(client, financial_world, auth):
    world = financial_world
    version = _create(client, auth, world, submitted_revenue="10", submitted_expenses="5").json()
    response = client.post(
        f"/api/v1/financial/summaries/{version['id']}/bank-statement",
        headers=auth(world["alpha_mgr"]),
        files={"file": ("evil.exe", b"MZ", "application/x-msdownload")},
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------
# reporting classification
# --------------------------------------------------------------------------
def test_report_classifies_each_status(client, financial_world, auth, tmp_path, monkeypatch):
    world = financial_world
    # alpha: draft; beta: submitted.
    _create(client, auth, world, submitted_revenue="10", submitted_expenses="5")
    beta_version = client.post(
        "/api/v1/financial/summaries",
        headers=auth(world["beta_mgr"]),
        json={"company_id": world["beta"].id, "period_year": YEAR, "period_month": MONTH, "submitted_revenue": "20", "submitted_expenses": "8"},
    ).json()
    _upload(client, auth, world["beta_mgr"], beta_version["id"], tmp_path, monkeypatch)
    client.post(
        f"/api/v1/financial/summaries/{beta_version['id']}/submit", headers=auth(world["beta_mgr"])
    )

    report = client.get(
        f"/api/v1/financial/report?year={YEAR}&month={MONTH}", headers=auth(world["owner"])
    ).json()
    by_company = {r["company_id"]: r for r in report["companies"]}
    assert by_company[world["alpha"].id]["status"] == "draft"
    assert by_company[world["beta"].id]["status"] == "submitted"
    assert report["counts"]["draft"] == 1
    assert report["counts"]["submitted"] == 1
    assert report["counts"]["approved"] == 0


def test_approved_figure_flows_to_the_effective_report(client, financial_world, auth, tmp_path, monkeypatch):
    world = financial_world
    version = _create(client, auth, world, submitted_revenue="1000", submitted_expenses="600").json()
    _upload(client, auth, world["alpha_mgr"], version["id"], tmp_path, monkeypatch)
    client.post(f"/api/v1/financial/summaries/{version['id']}/submit", headers=auth(world["alpha_mgr"]))
    client.post(f"/api/v1/financial/summaries/{version['id']}/approve", headers=auth(world["accountant"]))

    report = client.get(
        f"/api/v1/financial/report?year={YEAR}&month={MONTH}", headers=auth(world["owner"])
    ).json()
    assert report["counts"]["approved"] == 1
    assert report["totals"]["effective_revenue"] == "1000.00"
    assert report["totals"]["calculated_result"] == "400.00"


# --------------------------------------------------------------------------
# notification and audit
# --------------------------------------------------------------------------
def test_submission_notifies_the_accountant(client, financial_world, auth, tmp_path, monkeypatch, db):
    world = financial_world
    version = _create(client, auth, world, submitted_revenue="10", submitted_expenses="5").json()
    _upload(client, auth, world["alpha_mgr"], version["id"], tmp_path, monkeypatch)
    client.post(f"/api/v1/financial/summaries/{version['id']}/submit", headers=auth(world["alpha_mgr"]))

    from backend.db.models import Notification
    from backend.db.models.enums import NotificationType

    rows = db.query(Notification).filter(
        Notification.type == NotificationType.FINANCIAL_SUMMARY_SUBMITTED.value
    ).all()
    assert {r.recipient_id for r in rows} == {world["accountant"].id, world["owner"].id}


def test_workflow_actions_are_audited(client, financial_world, auth, tmp_path, monkeypatch, db):
    world = financial_world
    from backend.db.models import AuditLog
    from backend.db.models.audit_actions import AuditAction

    version = _create(client, auth, world, submitted_revenue="10", submitted_expenses="5").json()
    _upload(client, auth, world["alpha_mgr"], version["id"], tmp_path, monkeypatch)
    client.post(f"/api/v1/financial/summaries/{version['id']}/submit", headers=auth(world["alpha_mgr"]))
    client.post(f"/api/v1/financial/summaries/{version['id']}/approve", headers=auth(world["accountant"]))

    actions = {r.action for r in db.query(AuditLog).all()}
    assert AuditAction.FINANCIAL_SUMMARY_CREATED in actions
    assert AuditAction.FINANCIAL_SUMMARY_SUBMITTED in actions
    assert AuditAction.FINANCIAL_SUMMARY_APPROVED in actions


def test_review_actions_history_records_every_transition(client, financial_world, auth, tmp_path, monkeypatch, db):
    world = financial_world
    from backend.db.models import FinancialReviewAction

    version = _create(client, auth, world, submitted_revenue="10", submitted_expenses="5").json()
    _upload(client, auth, world["alpha_mgr"], version["id"], tmp_path, monkeypatch)
    client.post(f"/api/v1/financial/summaries/{version['id']}/submit", headers=auth(world["alpha_mgr"]))
    client.post(
        f"/api/v1/financial/summaries/{version['id']}/return",
        headers=auth(world["accountant"]),
        json={"note": "correct it"},
    )
    client.post(f"/api/v1/financial/summaries/{version['id']}/submit", headers=auth(world["alpha_mgr"]))
    client.post(f"/api/v1/financial/summaries/{version['id']}/approve", headers=auth(world["accountant"]))

    actions = [r.action for r in db.query(FinancialReviewAction).order_by(FinancialReviewAction.id).all()]
    assert actions == ["submitted", "returned", "resubmitted", "approved"]
