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

NEW_VIEWS = [
    "employees",
    "operations",
    "decisions",
    "projects",
    "accounting",
    "confidential",
]

NEW_ENDPOINTS = [
    "/api/v1/employees",
    "/api/v1/employees/assessments/list",
    "/api/v1/employees/assessments/",
    "/api/v1/operations/tasks",
    "/api/v1/operations/weekly-reports",
    "/api/v1/operations/campaigns",
    "/api/v1/operations/complaints",
    "/api/v1/operations/advisory-sessions",
    "/api/v1/operations/advisor-reports",
    "/api/v1/operations/owner-decisions",
    "/api/v1/operations/projects",
    "/api/v1/operations/management-briefs",
    "/api/v1/accounting/opening-balances",
    "/api/v1/accounting/accounts",
    "/api/v1/accounting/journals",
    "/api/v1/accounting/trial-balance",
    "/api/v1/accounting/financial-statements",
    "/api/v1/accounting/invoices",
    "/api/v1/accounting/parties",
    "/api/v1/accounting/interbalances",
    "/api/v1/accounting/receivables",
    "/api/v1/accounting/assets",
    "/api/v1/accounting/budgets",
    "/api/v1/accounting/kpis",
    "/api/v1/accounting/policies",
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
        "renderProjectsView",
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


def test_management_brief_tab_is_gated_and_wired():
    # S21: the five-axis BD brief lives under Operations, gated by its read
    # permission, with an authoring form and a submit-to-owner action.
    tab = re.search(r'data-ops-tab="briefs"[^>]*data-perm="([^"]+)"', INDEX)
    assert tab, "management brief ops tab not found"
    assert tab.group(1) == "management_brief.read"
    assert 'briefs: ["management_brief.read"]' in APP_JS
    assert "renderManagementBriefs" in APP_JS
    assert 'has("management_brief.submit")' in APP_JS
    assert 'data-act="brief-submit"' in APP_JS
    for axis in (
        "axis_companies", "axis_projects", "axis_employees",
        "axis_risks", "axis_decisions",
    ):
        assert axis in APP_JS, f"brief form missing {axis}"


def test_report_detail_wires_the_clarification_thread():
    # S02/S09: the report modal lists clarifications linked to the original and
    # offers the composer only to a holder of monthly_report.clarify.
    assert 'id="repClarify"' in APP_JS
    assert "loadClarifications" in APP_JS
    assert "/clarifications" in APP_JS
    assert 'has("monthly_report.clarify")' in APP_JS
    assert 'dual("طلب إيضاح", "Request clarification")' in APP_JS
    assert 'dual("الإيضاحات المرتبطة بالأصل", "Clarifications linked to the original")' in APP_JS


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


def test_s01_priorities_panel_is_present_and_hydrated():
    # S01 Table 12 lists "الأولويات | روابط سجلات | حسب الوصول" as a dashboard
    # field. The panel must exist in the markup and be filled from the live
    # dashboard payload, not from demo content.
    assert 'id="prioritiesList"' in INDEX
    assert "function hydratePriorities(" in APP_JS
    assert "hydratePriorities(data)" in APP_JS
    assert "prioritiesList" in APP_JS


def test_s01_indicator_drilldown_is_wired():
    # S01 AC-01: "فتح تفصيل مؤشر يعرض سجلات مصدره" — opening an indicator shows
    # its source records, and Table 13's عرض التفاصيل must not create a copy.
    assert "function openIndicatorSources(" in APP_JS
    assert "/api/v1/dashboard/indicator/" in APP_JS
    assert "function bindIndicatorDrills(" in APP_JS
    assert "bindIndicatorDrills()" in APP_JS  # called at boot
    # Every KPI tile that has a source indicator carries a drill target.
    for kpi in (
        "companies_count",
        "total_revenue",
        "total_net_result",
        "reports_submitted",
        "companies_requiring_attention",
        "open_support_requests",
    ):
        assert 'data-drill="' + kpi + '"' in INDEX, kpi


def test_role_dashboard_strip_is_wired():
    # Deck slides 7-11: each primary role gets its own KPI strip, not the
    # holding one. The markup carries the container and the bridge renders it
    # from the live role_summary payload.
    assert 'id="roleKpis"' in INDEX
    assert 'id="holdingKpis"' in INDEX
    # The role's own heading/greeting replaces the holding one (deck slides 7-11).
    assert 'id="pageTitle"' in INDEX
    assert 'id="pageSub"' in INDEX
    assert "function hydrateRoleSummary(" in APP_JS
    assert "hydrateRoleSummary(data)" in APP_JS  # called from loadDashboard
    assert "role_summary" in APP_JS
    assert 'byId("pageTitle")' in APP_JS
    assert "summary.title_ar" in APP_JS


def test_d01_accounting_policies_tab_is_wired():
    # D01: an accountant drafts a policy and approves it; a draft is inert.
    # The screen must be reachable, gated by the policy permission, and its
    # renderer must call the real endpoints.
    assert 'data-acct-tab="policies"' in INDEX
    assert 'data-perm="accounting_policy.read"' in INDEX
    assert "function renderPolicies(" in APP_JS
    assert 'tab === "policies"' in APP_JS
    assert "/api/v1/accounting/policies" in APP_JS
    # The tab is listed in the catalogue and mapped to its permission.
    assert '"policies"' in APP_JS
    assert 'policies: ["accounting_policy.read"]' in APP_JS


def test_s02_s10_goals_are_rendered_on_the_company_table():
    # S02/S10: goals-versus-results must be visible, resolved from the API's
    # goals array rather than recomputed in the browser.
    assert "function goalsHtml(" in APP_JS
    assert "goalsHtml(r.goals)" in APP_JS


def test_d11_notification_preferences_panel_is_wired():
    # D11: the notification centre is the base channel; a user can opt into
    # email or mute an event, and the change is persisted server-side.
    assert 'id="inboxPrefsPanel"' in INDEX
    assert 'id="inboxPrefs"' in INDEX
    assert "function renderNotificationPreferences(" in APP_JS
    assert "/api/v1/notifications/preferences" in APP_JS
    # The per-event toggle writes to the preference endpoint.
    assert "/api/v1/notifications/preferences/" in APP_JS
    assert "NOTIF_EVENT_LABEL" in APP_JS


def test_d02_kpi_evaluations_and_sources_are_wired():
    # D02: the KPI tab must show target-versus-actual from the server's
    # evaluation endpoint (not client arithmetic) and let a user drill into the
    # source records behind an actual. Activation writes to the active endpoint.
    assert "function renderKpis(" in APP_JS
    assert "/api/v1/accounting/kpis/evaluations" in APP_JS
    assert "/api/v1/accounting/kpis/" in APP_JS
    assert "/sources" in APP_JS
    assert "function openKpiSources(" in APP_JS
    # Activating/deactivating a KPI records the owner approval server-side.
    assert "/active" in APP_JS
    assert '"kpi-activate"' in APP_JS and '"kpi-deactivate"' in APP_JS
    # The variance is taken from the payload, never recomputed here.
    assert "ev.variance_pct" in APP_JS and "ev.favourable" in APP_JS


def test_every_literal_dual_call_has_both_languages():
    """No untranslated internal string (spec §E, T01).

    ``dual(ar, en)`` is the internal equivalent of the public site's ``_t``.
    A literal call whose English slot is empty, or whose English slot is
    actually Arabic, is a string that never switches language.
    """
    import re

    pattern = re.compile(r'dual\(\s*("(?:[^"\\]|\\.)*")\s*,\s*("(?:[^"\\]|\\.)*")\s*\)')
    arabic = re.compile(r"[\u0600-\u06FF]")
    offenders = []
    for m in pattern.finditer(APP_JS):
        ar = m.group(1).strip('"')
        en = m.group(2).strip('"')
        if en == "" or (arabic.search(en) and not arabic.search(ar)):
            offenders.append(m.group(0))
    assert offenders == [], f"untranslated dual() calls: {offenders[:10]}"


def test_s22_directive_reply_is_wired_to_the_respond_endpoint():
    """S22: the named executor can reply; the control posts to /respond."""
    assert "dec-reply" in APP_JS
    assert "/respond" in APP_JS
    # The reply control is offered only to the executor named on the decision.
    assert "d.executor_user_id === USER.id" in APP_JS
    # The reply is a note, never a status change: the owner alone closes it.
    assert 'post("/api/v1/operations/owner-decisions/" + did + "/respond"' in APP_JS



def test_s23_owner_secret_note_is_wired_to_the_owner_note_endpoint():
    """S23/AC-23: the owner's secret note is saved through its own endpoint.

    The note is only rendered for the confidential owner, and the save posts to
    the dedicated ``/owner-note`` endpoint (which is owner-only server-side).
    """
    assert "ownerNoteForm" in APP_JS
    assert "/owner-note" in APP_JS
    assert 'post("/api/v1/employees/assessments/" + a.id + "/owner-note"' in APP_JS
    # The panel is gated on the confidential owner and a leadership assessment.
    assert 'a.assessment_type === "leadership" && isConfidentialOwner()' in APP_JS


# --------------------------------------------------------------------------
# Executive UX redesign: sidebar shell, simplified nav, attention panel,
# Feedback view.
# --------------------------------------------------------------------------


def test_executive_shell_uses_a_sidebar_with_the_content_area():
    # The brief asks for a dark navy sidebar beside a white content area. The
    # shell must carry the sidebar and keep the board as the content region.
    assert 'class="stage-body with-sidebar"' in INDEX
    assert 'class="sidebar"' in INDEX
    assert '<nav class="sb-nav" id="mainNav">' in INDEX
    assert 'id="board"' in INDEX


def test_sidebar_shows_the_six_primary_sections():
    # The brief names six core sections. They are the sidebar's top level; the
    # operational views live behind the "More" group so the owner sees a short,
    # calm list rather than the full catalogue.
    primary = re.search(r'<nav class="sb-nav" id="mainNav">(.*?)</nav>', INDEX, re.S)
    assert primary, "sidebar primary nav not found"
    for view in ("dashboard", "leads", "requests", "feedback", "projects", "decisions"):
        assert f'data-view="{view}"' in primary.group(1), f"{view} is not a primary section"
    # And the operational views are grouped, still present and still gated.
    more = re.search(r'id="sbMoreItems">(.*?)</div>\s*</div>', INDEX, re.S)
    assert more, "More group not found"
    for view in ("subsidiaries", "reports", "financial", "support", "approvals",
                 "documents", "bi", "analytics", "inbox", "employees",
                 "operations", "accounting", "confidential", "admin"):
        assert f'data-view="{view}"' in more.group(1), f"{view} missing from More group"


def test_every_sidebar_nav_item_keeps_its_permission_gate():
    # Restructuring the nav must never drop a data-perm token: that token is
    # what hides an unusable section from the client.
    sidebar = re.search(r'<aside class="sidebar".*?</aside>', INDEX, re.S)
    assert sidebar, "sidebar not found"
    items = re.findall(r'<div class="nav-item[^"]*"[^>]*data-view="([^"]+)"[^>]*>', sidebar.group(0))
    assert set(items) == set(re.findall(r'"([a-z]+)"', re.search(r"var VIEWS = \[(.*?)\];", APP_JS, re.S).group(1)))
    for item in re.finditer(r'<div class="nav-item[^"]*"[^>]*>', sidebar.group(0)):
        assert "data-perm=" in item.group(0), f"ungated nav item: {item.group(0)[:80]}"


def test_more_group_is_collapsible_and_auto_opens_for_its_views():
    # The group is a real disclosure control (aria-expanded) and opens itself
    # when the active view lives inside it, so a deep link is never hidden.
    assert 'id="sbMoreToggle"' in INDEX
    assert 'aria-expanded="false"' in INDEX
    assert "function bindMoreGroup(" in APP_JS
    assert "function syncMoreGroup(" in APP_JS
    assert "syncMoreGroup(view)" in APP_JS
    assert 'classList.toggle("open")' in APP_JS


def test_attention_panel_uses_the_brief_title_and_direct_actions():
    # Brief §4: a prominent "ماذا يحتاج اهتمامك اليوم؟" with a direct action on
    # every row. The panel must be a real, hydrated section, not a static card.
    assert 'class="attention' in INDEX
    assert "ماذا يحتاج اهتمامك اليوم؟" in INDEX
    assert 'id="attnCount"' in INDEX
    assert "attn-card" in APP_JS
    assert "attn-act" in APP_JS
    # Each priority kind resolves to a concrete destination.
    assert "PRIORITY_ACTION" in APP_JS
    assert "function priorityAction(" in APP_JS


def test_feedback_view_is_gated_rendered_and_wired():
    # Brief §8. The view aggregates existing feedback channels; it must exist as
    # a gated section, have a renderer, be dispatched by loadView, and be listed
    # in VIEWS/NAV_PERM.
    section = re.search(r'<section[^>]*data-view="feedback"[^>]*>', INDEX)
    assert section, "feedback section missing"
    assert 'data-perm="' in section.group(0)
    assert "function renderFeedbackView(" in APP_JS
    assert 'view === "feedback"' in APP_JS
    assert '"feedback"' in APP_JS
    # It reads only endpoints that already exist, each behind its own read perm.
    for endpoint in (
        "/api/v1/operations/weekly-reports",
        "/api/v1/operations/management-briefs",
        "/api/v1/monthly-reports",
    ):
        assert endpoint in APP_JS, f"feedback never reads {endpoint}"
    assert "FB_SOURCES" in APP_JS
    assert 'id="feedbackList"' in INDEX


def test_feedback_nav_gate_matches_the_permissions_its_endpoints_enforce():
    # The view calls weekly-report, management-brief and monthly-report reads;
    # its gate must be exactly those read permissions, or a role could see the
    # section and then get a 403 from one of the calls.
    nav = re.search(
        r'class="nav-item[^"]*"[^>]*data-view="feedback"[^>]*data-perm="([^"]+)"', INDEX
    )
    assert nav, "feedback nav item not found"
    expected = {
        "weekly_report.read_own", "weekly_report.read_all",
        "management_brief.read",
        "monthly_report.read_own", "monthly_report.read_all",
    }
    assert set(nav.group(1).split()) == expected
    nav_perm = re.search(r'feedback: \[(.*?)\]', APP_JS, re.S)
    assert nav_perm, "NAV_PERM.feedback not found"
    assert set(re.findall(r'"([^"]+)"', nav_perm.group(1))) == expected
    section = re.search(r'<section[^>]*data-view="feedback"[^>]*data-perm="([^"]+)"', INDEX)
    assert set(section.group(1).split()) == expected


def test_feedback_renderer_escapes_server_strings():
    # The list mixes server text (summaries, company names) into innerHTML; it
    # must be escaped like every other live renderer.
    body = re.search(r"function fbRowHtml\(r\) \{(.*?)\n  \}", APP_JS, re.S)
    assert body, "fbRowHtml not found"
    assert "escapeHtml(r.title" in body.group(1)
    assert "escapeHtml(r.sub" in body.group(1)


def test_sidebar_sits_on_the_right_in_rtl():
    # The brief puts the rail on the right. RTL flows right-to-left, so the
    # rail needs the lowest order to land there; LTR then mirrors it left.
    rule = re.search(r"\.sidebar\{(.*?)\}", CSS, re.S)
    assert rule, ".sidebar rule not found"
    assert "order:-1" in rule.group(1)
    body = re.search(r"\.stage-body\.with-sidebar\{(.*?)\}", CSS, re.S)
    assert body and "flex-direction:row" in body.group(1)


def test_sidebar_collapses_to_a_drawer_on_narrow_screens():
    # Deck slides 39/89/90 put the rail behind a ☰ button on a phone: the
    # sidebar slides in as an off-canvas drawer over a scrim rather than
    # wrapping into a horizontal bar (which would claim a row per item).
    assert re.search(
        r"@media \(max-width:1180px\)\{[^@]*?\.sidebar\{[^}]*position:fixed",
        CSS, re.S,
    ), "sidebar must become a fixed drawer on narrow screens"
    assert re.search(
        r"@media \(max-width:1180px\)\{[^@]*?body\.nav-open \.sidebar\{transform:translateX\(0\);\}",
        CSS, re.S,
    ), "the drawer must open when body.nav-open is set"
    assert re.search(
        r"@media \(max-width:1180px\)\{[^@]*?\.stage-body\.with-sidebar\{flex-direction:column;\}",
        CSS, re.S,
    ), "sidebar must stack above the content on narrow screens"
    assert re.search(r"<button[^>]*id=\"navToggle\"", INDEX), "header needs the ☰ toggle"
    assert "bindNavDrawer" in APP_JS, "app.js must wire the drawer toggle"


def test_header_no_longer_carries_the_full_top_nav():
    # The 20-item top nav was the core "complicated ERP" problem; it moved into
    # the sidebar. The header keeps a breadcrumb instead.
    header = re.search(r"<header class=\"header\".*?</header>", INDEX, re.S)
    assert header, "header not found"
    assert 'class="nav"' not in header.group(0)
    assert 'id="crumb"' in header.group(0)



# --- Phase 3 functional audit regressions ---------------------------------
#
# An all-role crawl of the 21 views found two panels that fetched an endpoint
# the caller's role could not read, so a legitimate 403 rendered as an empty
# section. Both are now gated on the permission the endpoint enforces.


def _fn_body(name: str) -> str:
    """Return the source of a top-level ``function name(...)`` in app.js."""
    start = APP_JS.index("function " + name + "(")
    nxt = APP_JS.find("\n  function ", start + 1)
    return APP_JS[start : nxt if nxt != -1 else len(APP_JS)]


def test_company_finance_panel_gates_the_report_archive_on_its_permission():
    # marketing holds `dashboard.holding` (group summary) but not
    # `financial_report.read` (report archive); the archive call must be gated.
    body = _fn_body("renderCompanyFinanceComparison")
    assert 'has("financial_report.read")' in body
    assert "softGet(\"/api/v1/accounting/financial-reports\")" in body
    # The unguarded fetch must be gone: every occurrence sits inside the gate.
    assert body.count("/api/v1/accounting/financial-reports") == 1


def test_tasks_registry_gates_the_task_fetch_on_task_read():
    # business_development reaches this tab through `support_request.read_all`
    # but has no `task.read_*`, so the task call must be gated.
    body = _fn_body("renderTasksRegistry")
    assert 'has("task.read_own") || has("task.read_all")' in body
    assert 'softGet("/api/v1/operations/tasks")' in body


def test_optional_panel_fetches_do_not_swallow_server_errors():
    # 52 call sites used to be `get(...).catch(function () { return []; })`,
    # which turned a 500 or a network drop into "no data". softGet must
    # re-surface anything that is not an expected 401/403/404.
    assert "function softGet(" in APP_JS
    body = _fn_body("softGet")
    assert "toast(errText(err), \"err\")" in body
    for expected in ("401", "403", "404"):
        assert expected in body
    assert APP_JS.count(".catch(function () { return []; })") == 0


def test_every_export_stamps_the_period_entity_and_state():
    # Deck slides 130-132: "كل مخرج يحمل: الفترة والجهة والعملة وحالة البيانات
    # وآخر تحديث ومسودة/معتمد ورقم النسخة." The CSV preamble carries the period,
    # the entity, the state and the generation time.
    assert "function exportMeta(" in APP_JS
    meta = _fn_body("exportMeta")
    for token in ("الفترة", "الجهة", "آخر تحديث", "الحالة"):
        assert token in meta, f"export preamble must carry {token}"
    body = _fn_body("exportListCsv")
    assert "exportMeta(key)" in body, "the CSV must be stamped with its metadata"


def test_employee_report_control_is_gated_and_wired():
    # Deck slide 101 names [تقرير الموظفين] beside [موظف جديد] and [فتح الملف].
    assert 'id="empReport"' in APP_JS
    body = _fn_body("renderEmployees")
    assert 'has("employee.read")' in body, "the report is gated on employee.read"
    assert 'exportListCsv("employees", list)' in body


def test_every_role_that_can_open_a_view_can_read_its_primary_endpoint():
    # Guard against the class of bug fixed above: if a view's navigation gate
    # admits a role that cannot read the endpoint the panel fetches, the fetch
    # must be gated behind the permission the endpoint enforces.
    from backend.rbac.permissions import ROLE_PERMISSIONS

    # section -> (nav gate, renderer, endpoint, endpoint permission)
    sections = {
        "subsidiary_finance": (
            ["financial_summary.read_own", "financial_summary.read_all", "dashboard.holding"],
            "renderCompanyFinanceComparison",
            "/api/v1/accounting/financial-reports",
            "financial_report.read",
        ),
        "tasks_requests": (
            [
                "task.read_own",
                "task.read_all",
                "support_request.read_own",
                "support_request.read_all",
            ],
            "renderTasksRegistry",
            "/api/v1/operations/tasks",
            "task.read_own",
        ),
        "knowledge_admin": (
            ["ai.knowledge.read", "ai.admin"],
            "renderAdminKnowledge",
            "/api/v1/ai/knowledge/proposals",
            "ai.knowledge.manage",
        ),
    }
    for role, perms in ROLE_PERMISSIONS.items():
        for section, (gate, renderer, endpoint, perm) in sections.items():
            if not any(p in perms for p in gate):
                continue  # role cannot open the section at all
            if perm in perms:
                continue  # role may read the endpoint directly
            # Otherwise the renderer must not fetch it unconditionally.
            body = _fn_body(renderer)
            guard = 'has("%s")' % perm
            assert guard in body, (
                f"{role} can open {section} but lacks {perm}; {renderer} "
                f"fetches {endpoint} unguarded and would 403"
            )


def test_phase3_knowledge_base_admin_tab_is_gated_and_wired():
    """Phase 3: the RAG knowledge base has a real admin surface.

    The tab is reachable only with a knowledge/admin permission, its renderer
    calls the real knowledge endpoints (not a stub), and the provider/usage
    monitor is fetched only by an ``ai.admin`` holder.
    """
    tab = re.search(r'data-admin-tab="knowledge"[^>]*data-perm="([^"]+)"', INDEX)
    assert tab, "knowledge admin tab not found"
    for token in tab.group(1).split():
        assert token in ALL_PERMISSIONS, f"unknown permission on knowledge tab: {token}"
    assert '"knowledge"' in APP_JS
    assert 'knowledge: ["ai.knowledge.read", "ai.admin"]' in APP_JS
    body = _fn_body("renderAdminKnowledge")
    assert "/api/v1/ai/knowledge/documents" in body
    assert "/api/v1/ai/knowledge/proposals" in body
    assert 'has("ai.admin")' in body
    assert 'has("ai.knowledge.write")' in body


def test_phase3_knowledge_assistant_is_wired_to_its_scope():
    """The knowledge assistant posts to the dedicated /ai/knowledge scope.

    It is a separate surface from the figures assistant, its answer and sources
    are escaped, and the box is gated on ``ai.knowledge.ask``.
    """
    assert 'id="kbAsk"' in INDEX
    assert 'data-perm="ai.knowledge.ask"' in INDEX
    assert "function askKnowledge(" in APP_JS
    assert 'post("/api/v1/ai/knowledge", { question: question })' in APP_JS
    body = _fn_body("askKnowledge")
    assert "escapeHtml(data.answer" in body
    assert "escapeHtml(s.excerpt" in body
    assert "bindKnowledgeAskBox" in APP_JS


def test_employee_restricted_tab_matches_the_deck_slide_103():
    """The employee file carries the deck's restricted-fields tab.

    The tab is gated on the same ``employee.salary.read`` permission as the
    salary block, and it names the fields the deck lists: identity/residence
    (masked), work location, wage effective date, document links and the
    localization inclusion decision with its reason and applied rule.
    """
    body = _fn_body("employeeDetail")
    assert 'has("employee.salary.read")' in body
    for label in (
        "الهوية أو الإقامة",
        "موقع العمل",
        "تاريخ نفاذ البيانات",
        "المستندات أو الروابط الأساسية",
        "يحتسب ضمن التوطين؟",
        "سبب عدم الاحتساب",
        "الوظيفة المحتسبة",
        "قاعدة الاحتساب المطبقة",
        "المراجع وتاريخ القرار",
    ):
        assert label in body, f"restricted field label missing: {label}"
    # The masked identity number comes from the server payload.
    assert "e.national_id_masked" in body


def test_localization_board_carries_target_rule_and_below_target_alert():
    """Deck slide 105: the board shows the current rate, the target, the applied
    calculation rule, and a below-target follow-up flag; the target/rule are
    editable administration data (slide 106)."""
    body = _fn_body("renderLocalizationBoard")
    assert 'dual("المستهدف", "Target")' in body
    assert 'dual("قاعدة الاحتساب", "Calculation rule")' in body
    assert "localization_target_pct" in body
    assert "Below target" in body
    assert "data-loc-edit" in APP_JS
    edit = _fn_body("openLocalizationEdit")
    assert 'patch("/api/v1/companies/"' in edit
    assert "localization_target_pct" in edit


def test_investment_detail_reads_the_valuation_model_not_a_placeholder():
    """Deck slides 108/109: the detail shows the recorded figures and the yes/no
    valuation; when no valuation is recorded it says so rather than showing a
    zero, and the editor writes to the valuation endpoint."""
    body = _fn_body("openInvestment")
    assert "/api/v1/admin/investment-valuations/" in body
    assert "has_valuation" in body
    assert "No approved valuation" in body
    assert 'has("investment.manage")' in body
    # The old "await an approved valuation model" placeholder is gone.
    assert "تنتظر نموذج تقييم" not in APP_JS
    edit = _fn_body("openInvestmentEdit")
    assert 'patch("/api/v1/admin/investment-valuations/"' in edit
    assert "book_value" in edit
    assert "valuation_reference" in edit


def test_investment_register_carries_the_deck_slide_107_actions():
    """Deck slide 107 names [إضافة استثمار], [فتح التفاصيل], [رفع قرار] and
    [تقرير المحفظة] on the ownership/investment register. Each action appears
    only when the role holds the permission the endpoint it calls enforces, and
    the portfolio report exports the register the caller is already reading."""
    body = _fn_body("loadInvestmentPortfolio")
    assert "portfolioActionsHtml()" in body
    assert "bindPortfolioActions(list)" in body
    # The register carries the deck's own list machinery (slides 134-136):
    # search + filters + paging over the rows the caller may already read.
    assert 'applyListFilters(rows, "investments", spec)' in body
    assert 'renderPaged(listHost, "investments", list' in body
    assert '{ key: "q", type: "search"' in body

    acts = _fn_body("portfolioActionsHtml")
    assert 'dual("إضافة استثمار", "Add investment")' in acts
    assert 'dual("رفع قرار", "Raise decision")' in acts
    assert 'dual("تقرير المحفظة", "Portfolio report")' in acts
    # gated on the permission each action's endpoint enforces
    assert 'has("ownership.manage")' in acts
    assert 'has("owner_decision.manage")' in acts

    create = _fn_body("openInvestmentCreate")
    assert 'post("/api/v1/admin/ownerships"' in create
    decision = _fn_body("openPortfolioDecision")
    assert 'post("/api/v1/operations/owner-decisions"' in decision

    bind = _fn_body("bindPortfolioActions")
    assert 'exportListCsv("investments", rows)' in bind


def test_admin_users_carries_the_deck_slide_37_add_user_control():
    """Deck slide 37 names [إضافة مستخدم] on the Users & Permissions screen.
    The control appears only for a role that holds ``user.manage`` (the
    permission the POST /api/v1/users endpoint enforces) and opens a form that
    posts the deck's fields to that endpoint."""
    users = _fn_body("renderAdminUsers")
    assert 'dual("إضافة مستخدم", "Add user")' in users
    assert 'has("user.manage")' in users
    assert 'data-admin-action="user-create"' in users

    form = _fn_body("openCreateUserForm")
    assert 'post("/api/v1/users"' in form
    for fld in ("full_name_ar", "full_name_en", "role_code", "company_ids", "password"):
        assert fld in form, f"create-user payload missing {fld}"

    # The action is wired into the admin dispatcher.
    assert 'action === "user-create"' in APP_JS


# --- Deck slides 7-11: the board must not stack two strips in one area ------
#
# An all-role browser sweep of the live board found two overlap bugs, both
# invisible to a text-only check because each element's *own* box is correct:
#
#  1. ``#roleKpis`` and ``#holdingKpis`` both claim grid-area "kpis". Exactly
#     one is meant to be visible, but ``.kpis{display:grid}`` outranks the UA
#     ``[hidden]`` rule, so the hidden strip painted on top of the visible one
#     (``elementsFromPoint`` returned ``holdingKpis`` over ``roleKpis``).
#  2. ``#roleSection`` and ``#smartBriefSection`` both carried ``.role-section``
#     and therefore both claimed grid-area "role"; for a company manager (who
#     sees both) they overlapped on the exact same 1602x73 box.


def test_hidden_kpi_strip_does_not_render():
    # A class that sets display must not beat [hidden], or the hidden strip
    # paints over the visible one.
    assert re.search(r"\.kpis\[hidden\]\{display:none;\}", CSS), \
        ".kpis[hidden] must force display:none"
    assert re.search(r"\.role-kpis\[hidden\]\{display:none;\}", CSS)


def test_role_sections_share_one_grid_band_and_never_both_claim_the_area():
    # The two role sections are wrapped in a single band that owns grid-area
    # "role"; the sections themselves must not claim a grid area, or two
    # visible siblings overlap.
    assert re.search(r"\.role-band\{[^}]*grid-area:role", CSS), \
        ".role-band must own grid-area role"
    assert not re.search(r"\.role-section\{[^}]*grid-area", CSS), \
        ".role-section must not claim a grid area of its own"
    band = re.search(r'<div class="role-band[^"]*"[^>]*id="roleBand">(.*?)</div>\s*\n\s*<!-- =+ KPI STRIP', INDEX, re.S)
    assert band, "role band not found in index.html"
    assert 'id="roleSection"' in band.group(1)
    assert 'id="smartBriefSection"' in band.group(1)


def test_role_band_collapses_when_both_sections_are_hidden():
    # The band is a grid child; when neither section is visible it must not
    # leave an empty row on the board.
    assert re.search(
        r"\.role-band:not\(:has\(\.role-section:not\(\[hidden\]\)\)\)\{display:none;\}",
        CSS,
    ), "the role band must collapse when it holds no visible section"


# --- Deck lists: renderPaged must not wipe the panel header -----------------
#
# ``renderPaged(host, ...)`` sets ``host.innerHTML`` to the rows. When the same
# element that carries the panel chrome (title, [عميل محتمل]/[موظف جديد]/... add
# button) is passed as ``host``, the first render deletes that chrome -- the
# list still shows rows, so a text check passes, but the deck's named action is
# gone. Each of these views must render its rows into a dedicated child, not
# into the panel element itself.


def test_paged_domain_lists_do_not_overwrite_their_panel_header():
    for key, host_id in [
        ("leads", "leadList"),
        ("employees", "empList"),
        ("tasks", "taskList"),
        ("campaigns", "campaignList"),
        ("decisions", "decList"),
        ("projects", "projList"),
    ]:
        # The rows go into an element with the id the panel created...
        assert re.search(
            r"renderPaged\(byId\(\"%s\"\)" % host_id, APP_JS
        ), f"{key} must page into #{host_id}, not the panel element"
        # ...and that id is created inside the panel body alongside the action.
        assert re.search(
            r'panel\([^;]*?' + re.escape('id="%s"' % host_id), APP_JS, re.S
        ), f"{key}: the panel body must contain #{host_id}"
        # Passing the panel element itself would erase the header on re-render.
        assert not re.search(
            r"renderPaged\(host, \"%s\"" % key, APP_JS
        ), f"{key} must not page into the panel element (header would be lost)"
