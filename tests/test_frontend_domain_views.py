"""Frontend contract tests for the holding-business domain views.

The internal platform is a dependency-free, vanilla-JS single page. There is no
bundler or JS test runner in the image, so these tests assert the *contract*
between the frontend and the backend instead of executing the DOM:

* every new view exists as a section with a ``data-view`` and a permission gate,
* the navigation catalogue and the view list stay in sync with the markup,
* every ``data-perm`` token is a permission code the backend actually defines
  (so a typo can never silently hide or expose a screen),
* every domain renderer and its API endpoint is present in ``app.js``.

These are static, fast and deterministic, and they fail loudly if the frontend
drifts from the RBAC catalogue or from the mounted API routes.
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.rbac.permissions import ALL_PERMISSIONS

ROOT = Path(__file__).resolve().parent.parent
APP_JS = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
INDEX = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")

NEW_VIEWS = ["employees", "operations", "decisions", "accounting", "confidential"]

NEW_ENDPOINTS = [
    "/api/v1/employees",
    "/api/v1/employees/assessments/list",
    "/api/v1/employees/assessments/",
    "/api/v1/operations/tasks",
    "/api/v1/operations/weekly-reports",
    "/api/v1/operations/campaigns",
    "/api/v1/operations/complaints",
    "/api/v1/operations/advisory-sessions",
    "/api/v1/operations/owner-decisions",
    "/api/v1/accounting/opening-balances",
    "/api/v1/accounting/accounts",
    "/api/v1/accounting/journals",
    "/api/v1/accounting/invoices",
    "/api/v1/accounting/assets",
    "/api/v1/accounting/budgets",
    "/api/v1/accounting/kpis",
    "/api/v1/confidential-access/grants",
]


def _data_perms(html: str) -> list[str]:
    codes: list[str] = []
    for match in re.finditer(r'data-perm="([^"]+)"', html):
        codes.extend(match.group(1).split())
    return codes


def test_every_new_view_section_is_gated():
    for view in NEW_VIEWS:
        section = re.search(
            r'<section[^>]*data-view="' + view + r'"[^>]*>', INDEX
        )
        assert section, f"missing section for view {view}"
        assert 'data-perm="' in section.group(0), f"view {view} has no permission gate"


def test_every_new_nav_item_is_gated():
    for view in NEW_VIEWS:
        item = re.search(
            r'class="nav-item[^"]*"[^>]*data-view="' + view + r'"[^>]*>', INDEX
        )
        assert item, f"missing nav item for view {view}"
        assert 'data-perm="' in item.group(0)


def test_view_and_nav_catalogues_include_the_new_views():
    for view in NEW_VIEWS:
        assert f'"{view}"' in APP_JS, f"VIEWS/NAV_PERM missing {view}"
        assert f"{view}:" in APP_JS or f'"{view}":' in APP_JS


def test_every_data_perm_token_is_a_real_permission_code():
    unknown = sorted({c for c in _data_perms(INDEX) if c not in ALL_PERMISSIONS})
    assert unknown == [], f"index.html references unknown permissions: {unknown}"


def test_every_domain_renderer_is_defined():
    for name in (
        "renderEmployeesView",
        "renderOperationsView",
        "renderDecisionsView",
        "renderAccountingView",
        "renderConfidentialView",
    ):
        assert f"function {name}(" in APP_JS, f"{name} is not defined"


def test_every_domain_endpoint_is_referenced():
    for endpoint in NEW_ENDPOINTS:
        assert endpoint in APP_JS, f"app.js never calls {endpoint}"


def test_domain_views_are_wired_into_loadview():
    load_view = re.search(r"function loadView\(view\) \{(.*?)\n  \}", APP_JS, re.S)
    assert load_view, "loadView not found"
    body = load_view.group(1)
    for view in NEW_VIEWS:
        assert f'view === "{view}"' in body, f"loadView does not dispatch {view}"


def test_sensitive_actions_are_permission_gated_in_the_client():
    # The client must not offer a control it cannot use. Each of these calls
    # sits behind an explicit `has(...)` check (server-side enforcement is the
    # real boundary; this only prevents dead controls).
    for perm in (
        "employee.manage",
        "assessment.approve",
        "task.create",
        "campaign.manage",
        "owner_decision.manage",
        "journal.post",
        "journal.reverse",
        "budget.approve",
        "opening_balance.approve",
        "complaint.decide",
        "confidential_access.manage",
    ):
        assert f'has("{perm}")' in APP_JS, f"{perm} is never checked in the client"


def test_employee_salary_is_hidden_without_the_salary_permission():
    # A regression here would leak pay data into the employee list/detail.
    assert 'has("employee.salary.read")' in APP_JS


def test_confidential_grant_requires_an_expiry():
    # D04: a delegated grant is only valid with a mandatory expiry.
    assert "cgExpires" in APP_JS
    assert "expires_at" in APP_JS
