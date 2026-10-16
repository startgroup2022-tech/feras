"""S09 AC-09 -- the monthly report shows the status of its linked financial part.

The spec (Table 42) requires the report's "الجزء المالي" to be a *read link* to
the F-03 financial summary "مع حالته" (with its status). AC-09 spells the rule
out: sending the report while the accountant is still reviewing must show the
financial part's status, and the figures are drawn from F-03 -- never copied
into the report.

These tests exercise the real API: the report's ``financial_part`` reflects the
company's financial period for the same year/month, is absent (``no_data``) when
no summary exists, and never leaks another company's period.
"""

from __future__ import annotations

from backend.db.models.enums import FinancialSummaryStatus

YEAR, MONTH = 2027, 12
PDF = b"%PDF-1.4 bank statement"


def _create_report(client, world, auth, *, year=YEAR, month=MONTH, company=None):
    body = {
        "company_id": (company or world["alpha"]).id,
        "period_year": year,
        "period_month": month,
        "revenue": "100000",
        "expenses": "60000",
        "net_result": "40000",
    }
    response = client.post("/api/v1/monthly-reports", headers=auth(world["alpha_mgr"]), json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _create_financial(client, world, auth, *, year=YEAR, month=MONTH):
    response = client.post(
        "/api/v1/financial/summaries",
        headers=auth(world["alpha_mgr"]),
        json={
            "company_id": world["alpha"].id,
            "period_year": year,
            "period_month": month,
            "submitted_revenue": "1000",
            "submitted_expenses": "600",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_report_without_a_financial_summary_reports_no_data(client, world, auth):
    report = _create_report(client, world, auth)

    fetched = client.get(
        f"/api/v1/monthly-reports/{report['id']}", headers=auth(world["alpha_mgr"])
    ).json()

    assert fetched["financial_part"]["status"] == "no_data"
    assert fetched["financial_part"]["effective_version"] is None
    assert fetched["financial_part"]["current_version"] is None


def test_report_shows_the_current_draft_status_of_its_financial_part(client, world, auth):
    report = _create_report(client, world, auth)
    version = _create_financial(client, world, auth)

    fetched = client.get(
        f"/api/v1/monthly-reports/{report['id']}", headers=auth(world["alpha_mgr"])
    ).json()

    part = fetched["financial_part"]
    assert part["status"] == FinancialSummaryStatus.DRAFT.value
    assert part["current_version"]["id"] == version["id"]
    assert part["current_version"]["version_number"] == 1
    # No approved version yet, so the effective slot is honestly empty.
    assert part["effective_version"] is None


def test_submitting_the_report_while_the_accountant_reviews_shows_the_status(
    client, world, auth, tmp_path, monkeypatch
):
    """AC-09: the report sent while the accountant waits shows the F-03 status."""
    report = _create_report(client, world, auth)
    version = _create_financial(client, world, auth)

    from backend.core.config import settings

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    client.post(
        f"/api/v1/financial/summaries/{version['id']}/bank-statement",
        headers=auth(world["alpha_mgr"]),
        files={"file": ("statement.pdf", PDF, "application/pdf")},
    )
    submitted = client.post(
        f"/api/v1/financial/summaries/{version['id']}/submit",
        headers=auth(world["alpha_mgr"]),
    )
    assert submitted.status_code == 200, submitted.text

    # The manager sends the report while the accountant is still reviewing.
    sent = client.post(
        f"/api/v1/monthly-reports/{report['id']}/submit", headers=auth(world["alpha_mgr"])
    )
    assert sent.status_code == 200, sent.text
    assert sent.json()["financial_part"]["status"] == FinancialSummaryStatus.SUBMITTED.value


def test_financial_part_never_leaks_another_companys_summary(client, world, auth):
    # A financial summary exists for beta, not for alpha's report period.
    beta_version = client.post(
        "/api/v1/financial/summaries",
        headers=auth(world["beta_mgr"]),
        json={
            "company_id": world["beta"].id,
            "period_year": YEAR,
            "period_month": 11,
            "submitted_revenue": "1",
            "submitted_expenses": "1",
        },
    )
    assert beta_version.status_code == 201, beta_version.text

    alpha_report = _create_report(client, world, auth, month=11)
    fetched = client.get(
        f"/api/v1/monthly-reports/{alpha_report['id']}", headers=auth(world["alpha_mgr"])
    ).json()

    # alpha has no summary for 2027-11; beta's must not appear.
    assert fetched["financial_part"]["status"] == "no_data"


def test_reader_without_financial_permission_gets_no_financial_part(client, world, auth, make_user):
    report = _create_report(client, world, auth)
    _create_financial(client, world, auth)

    # Marketing reads every report but holds no financial-summary permission, so
    # the F-03 slot is not even serialised.
    marketing = make_user("mkt@corp.sa", "marketing")
    fetched = client.get(
        f"/api/v1/monthly-reports/{report['id']}", headers=auth(marketing)
    )
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["financial_part"] is None

    # The accountant does hold financial read and sees the linked status.
    as_accountant = client.get(
        f"/api/v1/monthly-reports/{report['id']}", headers=auth(world["accountant"])
    )
    assert as_accountant.status_code == 200, as_accountant.text
    assert as_accountant.json()["financial_part"]["status"] == FinancialSummaryStatus.DRAFT.value
