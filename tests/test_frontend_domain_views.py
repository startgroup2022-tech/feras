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
CSS = (ROOT / "frontend" / "styles.css").read_text(encoding="utf-8")

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


def test_platform_header_renders_the_admin_logo():
    # The platform header shows the same admin-uploaded Holding logo as the
    # public site, with the static mark as the documented fallback.
    assert 'class="brand-logo" id="brandLogo"' in INDEX
    assert 'id="brandMark"' in INDEX
    assert 'function applyPlatformLogo(' in APP_JS
    assert "/api/v1/public/branding" in APP_JS
    # It must be wired into the post-login boot so it appears on first paint.
    assert "applyPlatformLogo();" in APP_JS


def test_platform_nav_is_responsive_and_never_clipped():
    # The platform nav carries many permission-gated sections; it must wrap and
    # remain fully visible rather than scroll horizontally or clip on desktop.
    nav_rule = re.search(r"\.nav\{[^}]*\}", CSS)
    assert nav_rule, ".nav rule not found"
    rule = nav_rule.group(0)
    assert "flex-wrap:wrap" in rule
    assert "order:3" in rule
    # A fixed header height let the wrapped nav overflow into the page.
    header_rule = re.search(r"\.header-inner\{[^}]*\}", CSS)
    assert header_rule, ".header-inner rule not found"
    assert "min-height" in header_rule.group(0)
    assert "flex-wrap:wrap" in header_rule.group(0)
    # A fixed height (as opposed to min-height) is what clipped the nav.
    assert not re.search(r"(?<!min-)height:62px", header_rule.group(0))


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


def test_bi_view_gate_matches_the_permission_its_endpoint_enforces():
    # `GET /ai/insights` is gated by `dashboard.*`, so the Business Intelligence
    # nav/section must use the same gate. Gating on `ai.*` let a custom role
    # with AI-only access see the view and then receive a 403.
    bi_nav = re.search(
        r'class="nav-item[^"]*"[^>]*data-view="bi"[^>]*data-perm="([^"]+)"', INDEX
    )
    assert bi_nav, "BI nav item not found"
    assert set(bi_nav.group(1).split()) == {"dashboard.holding", "dashboard.company"}

    bi_section = re.search(
        r'<section[^>]*data-view="bi"[^>]*data-perm="([^"]+)"', INDEX
    )
    assert bi_section, "BI section not found"
    assert set(bi_section.group(1).split()) == {"dashboard.holding", "dashboard.company"}

    nav_perm = re.search(r'bi: \[([^\]]+)\]', APP_JS)
    assert nav_perm, "NAV_PERM.bi not found"
    assert set(re.findall(r'"([^"]+)"', nav_perm.group(1))) == {
        "dashboard.holding",
        "dashboard.company",
    }


# --------------------------------------------------------------------------
# Roles & permissions UX + bilingual admin shell
# --------------------------------------------------------------------------


def test_roles_editor_renders_names_descriptions_and_categories():
    # The catalogue is server-described; the editor must surface the bilingual
    # name, the description, the category chips and the raw code as help text.
    for token in (
        "perm-cats",
        "perm-cat-chip",
        'data-admin-action="perm-cat"',
        "perm-name",
        "perm-desc",
        "perm-code",
        "description_ar",
        "description_en",
        "name_ar",
        "name_en",
    ):
        assert token in APP_JS, f"roles editor is missing {token}"


def test_roles_editor_has_search_grouping_select_all_and_counters():
    # Search box, grouped cards, a per-category select-all and the "n / total"
    # counter are the explicit S-spec requirements for this screen.
    assert 'id="permSearch"' in APP_JS
    assert 'class="perm-group"' in APP_JS
    assert 'data-admin-action="perm-selectall"' in APP_JS
    assert "updateGroupCounts" in APP_JS
    assert "updatePermSummary" in APP_JS
    assert "visiblePermCodes" in APP_JS
    # Every group shows the enabled/total count for its category.
    assert "pcount" in APP_JS


def test_roles_editor_flags_sensitive_permissions():
    # `danger` metadata must render a visible sensitive badge, not just colour.
    assert "perm-badge danger" in APP_JS
    assert "pdanger" in APP_JS
    assert 'dual("حساس", "Sensitive")' in APP_JS


def test_sector_admin_tab_is_gated_and_wired():
    tab = re.search(r'data-admin-tab="sectors"[^>]*data-perm="([^"]+)"', INDEX)
    assert tab, "sector admin tab not found"
    assert tab.group(1) == "sector.read"
    assert "sectors: [\"sector.read\"]" in APP_JS
    assert 'tab === "sectors"' in APP_JS
    assert "renderAdminSectors" in APP_JS
    assert "/api/v1/admin/sectors" in APP_JS


def test_position_admin_tab_is_gated_and_wired():
    tab = re.search(r'data-admin-tab="positions"[^>]*data-perm="([^"]+)"', INDEX)
    assert tab, "position admin tab not found"
    assert tab.group(1) == "position.read"
    assert 'positions: ["position.read"]' in APP_JS
    assert 'tab === "positions"' in APP_JS
    assert "renderAdminPositions" in APP_JS
    assert "/api/v1/admin/positions" in APP_JS
    # Writes are gated by position.manage, not by the read permission.
    assert 'has("position.manage")' in APP_JS
    assert 'data-admin-action="save-position"' in APP_JS


def test_motivation_admin_tab_is_gated_and_wired():
    tab = re.search(r'data-admin-tab="motivation"[^>]*data-perm="([^"]+)"', INDEX)
    assert tab, "motivation admin tab not found"
    assert tab.group(1) == "motivation.read"
    assert 'motivation: ["motivation.read"]' in APP_JS
    assert 'tab === "motivation"' in APP_JS
    assert "renderAdminMotivation" in APP_JS
    assert "/api/v1/admin/motivation-texts" in APP_JS
    assert 'has("motivation.manage")' in APP_JS
    assert 'data-admin-action="save-motivation"' in APP_JS


def test_lead_detail_wires_the_independent_manager_note():
    # S13: the lead modal lists manager notes and only offers the composer to a
    # holder of website_lead.manager_note; marketing (read-only) sees the list.
    assert "manager_notes" in APP_JS
    assert "/notes" in APP_JS
    assert 'has("website_lead.manager_note")' in APP_JS
    assert 'dual("ملاحظات المدير", "Manager notes")' in APP_JS
    assert 'id="leadNoteBody"' in APP_JS
    assert 'id="leadNoteAdd"' in APP_JS


def test_language_switch_flips_direction_and_rerenders_admin():
    # The dynamic admin UI must follow the AR/EN switch: `dir` flips between
    # rtl/ltr and the active view (including the admin tab) is re-rendered.
    assert 'html.setAttribute("dir", lang === "ar" ? "rtl" : "ltr")' in APP_JS
    assert "function refreshActiveView" in APP_JS
    assert "renderAdminTab(STATE.adminTab)" in APP_JS
    assert "function applyI18n" in APP_JS


def test_every_has_check_uses_a_real_permission_code():
    unknown = sorted({p for p in re.findall(r'has\("([^"]+)"\)', APP_JS) if p not in ALL_PERMISSIONS})
    assert unknown == [], f"app.js checks unknown permissions: {unknown}"


def test_document_title_follows_the_active_language_and_view():
    # Audit §4: the server-rendered Arabic <title> must be replaced on language
    # switch and kept in sync with the view, including an English brand.
    assert "function applyDocTitle" in APP_JS
    assert "VIEW_TITLES" in APP_JS
    assert "Safir Holding 2027" in APP_JS  # English brand present
    assert re.search(r"applyI18n\(\);\s*\n\s*applyDocTitle\(\);", APP_JS)
    assert re.search(r"applyDocTitle\(\);\s*\n\s*var board", APP_JS)


def test_active_nav_item_is_exposed_to_assistive_tech():
    # Audit §4: aria-current on the active nav item, both in the static boot
    # markup and when navigation happens at runtime.
    assert 'aria-current="page"' in INDEX
    assert 'setAttribute("aria-current", "page")' in APP_JS


def test_toast_region_announces_messages():
    # Audit §4: a persistent aria-live toast region and role=alert for errors.
    assert "function ensureToastRegion" in APP_JS
    assert "ensureToastRegion()" in APP_JS  # created at boot
    assert 'setAttribute("aria-live", "polite")' in APP_JS
    assert 'setAttribute("role", "status")' in APP_JS
    assert 'setAttribute("role", "alert")' in APP_JS

