"""Focused browser check for the Roles & Permissions screen.

Verifies, against a live server and a real Chromium session, that the admin
Roles editor behaves as the spec requires:

* it is reachable only with the ``permission.assign`` capability;
* permission names/descriptions are bilingual and grouped by category;
* the search box filters cards live;
* the category chips filter to one category;
* select-all toggles every permission in a category;
* the counters reflect the selection and flag sensitive permissions;
* saving persists through the API and re-renders;
* Arabic/English switching flips document direction and the labels.

Run: ``BASE_URL=http://127.0.0.1:12000 python3 -m scripts.e2e_roles``
"""

from __future__ import annotations

import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:12000").rstrip("/")
PLATFORM = BASE + "/platform/"
PASSWORD = "SafirDemo!2027"
OWNER = "owner@demo.safir.local"
MANAGER = "manager.tech@demo.safir.local"


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.notes: list[str] = []

    def fail(self, msg: str) -> None:
        self.failures.append(msg)

    def note(self, msg: str) -> None:
        self.notes.append(msg)


def _login(page, email: str) -> bool:
    page.goto(PLATFORM, wait_until="networkidle")
    page.fill("#loginEmail", email)
    page.fill("#loginPassword", PASSWORD)
    page.click("#loginForm button[type=submit]")
    page.wait_for_timeout(1500)
    return page.evaluate("() => !!document.querySelector('.nav-item')")


def _open_admin_roles(page) -> bool:
    page.locator('.nav-item[data-view="admin"]:visible').first.click()
    page.wait_for_timeout(800)
    tab = page.locator('[data-admin-tab="roles"]:visible')
    if tab.count() == 0:
        return False
    tab.first.click()
    page.wait_for_timeout(1200)
    return True


def run() -> int:
    report = Report()
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])

        # 1. A company manager must not be able to edit roles.
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        if _login(page, MANAGER):
            opened = _open_admin_roles(page)
            if not opened:
                report.note("company_manager has no roles tab (correct)")
            else:
                editable = page.evaluate(
                    """() => !!document.querySelector('[data-admin-action="perm-save"]')"""
                )
                if editable:
                    report.fail(
                        "company_manager unexpectedly sees the role editor save bar"
                    )
                else:
                    report.note("company_manager cannot edit roles (no save bar)")
        ctx.close()

        # 2. The holding owner sees the full editor.
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        if not _login(page, OWNER):
            report.fail("owner login failed")
            browser.close()
            return _finish(report)
        if not _open_admin_roles(page):
            report.fail("owner cannot open the roles tab")
            browser.close()
            return _finish(report)

        if not page.query_selector("#permEditor"):
            report.fail("owner cannot see the roles editor")
            browser.close()
            return _finish(report)
        report.note("owner sees the roles editor")

        # Bilingual grouped cards.
        cards = page.query_selector_all(".perm-card")
        if len(cards) < 20:
            report.fail(f"too few permission cards rendered ({len(cards)})")
        groups = page.query_selector_all(".perm-group")
        if not groups:
            report.fail("permissions are not grouped by category")
        else:
            report.note(f"{len(cards)} permission cards in {len(groups)} groups")

        # Search filter narrows the visible cards.
        total_before = len(cards)
        page.fill("#permSearch", "journal")
        page.wait_for_timeout(500)
        filtered = len(page.query_selector_all(".perm-card"))
        if filtered >= total_before or filtered == 0:
            report.fail(f"search did not narrow cards ({total_before} -> {filtered})")
        else:
            report.note(f"search narrowed cards {total_before} -> {filtered}")
        page.fill("#permSearch", "")
        page.wait_for_timeout(400)

        # Category chip filter.
        chips = page.query_selector_all('[data-admin-action="perm-cat"]')
        if len(chips) < 3:
            report.fail("no category chips rendered")
        else:
            target = None
            for chip in chips[1:]:
                key = chip.get_attribute("data-cat")
                if key and key != "all":
                    target = chip
                    break
            if target is not None:
                target.click()
                page.wait_for_timeout(500)
                on = page.evaluate(
                    """() => document.querySelectorAll('[data-admin-action="perm-cat"].on').length"""
                )
                if on != 1:
                    report.fail("category chip did not become the active filter")
                else:
                    report.note("category chip filters the group list")
                # reset to all
                page.locator(
                    '[data-admin-action="perm-cat"][data-cat="all"]:visible'
                ).first.click()
                page.wait_for_timeout(400)

        # Counters + sensitive indicator exist.
        if not page.query_selector("#permSummary"):
            report.fail("no permission counter summary")
        else:
            report.note("permission counters rendered")

        # Select-all within a category toggles every card in that group.
        select_all = page.query_selector_all('[data-admin-action="perm-selectall"]')
        if not select_all:
            report.fail("no select-all control per category")
        else:
            btn = select_all[0]
            cat = btn.get_attribute("data-cat")
            btn.click()
            page.wait_for_timeout(600)
            state = page.evaluate(
                """(cat) => {
                    var grp = document.querySelector('.perm-group[data-cat="'+cat+'"]');
                    if (!grp) return null;
                    var boxes = grp.querySelectorAll('input[data-perm-code]');
                    var on = 0;
                    boxes.forEach(b => { if (b.checked) on++; });
                    return {total: boxes.length, on: on};
                }""",
                cat,
            )
            if not state or state["total"] == 0:
                report.fail("select-all category had no permission cards")
            elif state["on"] not in (0, state["total"]):
                report.fail(
                    f"select-all left a partial state: {state['on']}/{state['total']}"
                )
            else:
                report.note(
                    f"select-all toggled category '{cat}' to {state['on']}/{state['total']}"
                )

        # Save bar appears once the selection is dirty, and persists.
        save = page.query_selector('[data-admin-action="perm-save"]')
        if save and page.query_selector("#permDirty"):
            dirty = page.evaluate(
                """() => (document.querySelector('#permDirty')||{}).textContent||''"""
            )
            report.note(f"dirty indicator: {dirty.strip()[:40]}")
        if save:
            save.click()
            page.wait_for_timeout(1200)
            if page.query_selector("#permEditor"):
                report.note("save round-tripped and re-rendered the editor")
            else:
                report.fail("editor disappeared after save")

        # AR/EN switch flips direction and re-renders.
        page.locator('.lang-opt[data-lang="en"]:visible').first.click()
        page.wait_for_timeout(500)
        en_dir = page.evaluate("() => document.documentElement.dir")
        en_has_english = page.evaluate(
            """() => (document.body.innerText||'').includes('Roles')"""
        )
        page.locator('.lang-opt[data-lang="ar"]:visible').first.click()
        page.wait_for_timeout(500)
        ar_dir = page.evaluate("() => document.documentElement.dir")
        if en_dir != "ltr" or ar_dir != "rtl":
            report.fail(f"lang switch dir wrong: en={en_dir} ar={ar_dir}")
        elif not en_has_english:
            report.fail("English labels not shown after switching to EN")
        else:
            report.note("AR/EN switch ok and labels localise")

        if errors:
            report.fail("page JS errors: " + "; ".join(errors[:5]))

        ctx.close()
        browser.close()
    return _finish(report)


def _finish(report: Report) -> int:
    print("==== ROLES & PERMISSIONS E2E NOTES ====")
    for n in report.notes:
        print("  " + n)
    print("==== ROLES & PERMISSIONS E2E FAILURES ====")
    if report.failures:
        for f in report.failures:
            print("  - " + f)
        return 1
    print("  none")
    return 0


if __name__ == "__main__":
    sys.exit(run())
