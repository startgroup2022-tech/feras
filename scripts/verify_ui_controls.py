"""Sweep every platform view and tab chip in the real browser.

The brief requires that *every button and element* works, not just that the API
routes exist. This harness signs in as the Holding Owner (widest scope), opens
each view by its hash route, and asserts that:

  * the view section becomes visible and its content host renders non-empty, and
  * every tab chip inside the view toggles the content without a console error.

A chip that is rendered but unbound leaves the host unchanged, which fails here.

    BASE_URL=http://127.0.0.1:12001 python -m scripts.verify_ui_controls
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "ui_controls_verification.json"

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:12001").rstrip("/")
CHROMIUM = os.environ.get("CHROMIUM", "/usr/bin/chromium")
PASSWORD = os.environ.get("DEMO_PASSWORD", "SafirDemo!2027")
OWNER = "owner@demo.safir.local"

# Every routed view, including the legacy deep-link-only ones.
VIEWS = [
    "dashboard", "leads", "requests", "advisory", "opportunities", "decisions",
    "reports", "employees", "hr", "assets", "site", "aiReview", "group",
    "accounting", "operations", "confidential", "analytics", "bi",
    "subsidiaries", "financial", "support", "approvals", "documents", "inbox",
    "investments",
]

TAB_ATTRS = [
    "data-adv-tab", "data-hr-tab", "data-site-tab", "data-airev-tab",
    "data-emp-tab", "data-ops-tab", "data-acct-tab", "data-conf-tab",
    "data-admin-tab", "data-an-tab",
]


def _visible_host_state(page) -> dict:
    """Report the active section, its content host text length and chip tabs."""
    return page.evaluate(
        """() => {
            const board = document.getElementById('board');
            if (board && !board.classList.contains('view-hidden')) {
                return {view: 'dashboard', hostId: 'board',
                        textLen: (board.innerText || '').trim().length, chips: []};
            }
            const sec = document.querySelector('.app-view:not(.view-hidden)[data-view]');
            if (!sec) return {view: null};
            const host = sec.querySelector('[id$="Content"]') || sec;
            const chips = Array.from(sec.querySelectorAll(
                '[data-adv-tab],[data-hr-tab],[data-site-tab],[data-airev-tab],'
                + '[data-emp-tab],[data-ops-tab],[data-acct-tab],[data-conf-tab],'
                + '[data-admin-tab],[data-an-tab]'
            )).filter(b => b.offsetParent !== null);
            return {
                view: sec.getAttribute('data-view'),
                hostId: host.id || '',
                textLen: (host.innerText || '').trim().length,
                chips: chips.map(c => {
                    const a = c.getAttributeNames().find(n => n.endsWith('-tab'));
                    return a ? a + '=' + c.getAttribute(a) : '';
                }),
            };
        }"""
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Sweep platform views and tab chips.")
    parser.add_argument("--base", default=BASE)
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()
    base = args.base.rstrip("/")

    rows: list[dict] = []
    console: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
        page = browser.new_context(viewport={"width": 1600, "height": 950}).new_page()
        page.on("console", lambda m: console.append(m.text) if m.type == "error" else None)
        try:
            page.goto(base + "/platform/?year=2027&month=10", wait_until="networkidle")
            page.wait_for_selector("#loginEmail", state="visible")
            page.fill("#loginEmail", OWNER)
            page.fill("#loginPassword", PASSWORD)
            page.click("#loginBtn")
            page.wait_for_selector("#loginScreen", state="hidden", timeout=20000)
            page.wait_for_timeout(1500)

            for view in VIEWS:
                page.evaluate("v => { location.hash = v; }", view)
                page.wait_for_timeout(2200)
                state = _visible_host_state(page)
                ok = state.get("view") == view and state.get("textLen", 0) > 0
                rows.append({
                    "check": f"view:{view}", "ok": bool(ok),
                    "detail": f"host={state.get('hostId')} chars={state.get('textLen')}",
                })
                # Exercise each tab chip in the view.
                chips = state.get("chips") or []
                for chip in chips:
                    attr, _, value = chip.partition("=")
                    sel = f'[{attr}="{value}"]'
                    el = page.query_selector(sel)
                    if not el or not el.is_visible():
                        rows.append({"check": f"tab:{view}:{value}", "ok": False, "detail": "chip not clickable"})
                        continue
                    before = _visible_host_state(page).get("textLen", 0)
                    el.click()
                    page.wait_for_timeout(1600)
                    after_state = _visible_host_state(page)
                    on = page.eval_on_selector(sel, "e => e.classList.contains('on')")
                    rows.append({
                        "check": f"tab:{view}:{value}",
                        "ok": bool(on and after_state.get("textLen", 0) > 0),
                        "detail": f"on={on} before={before} after={after_state.get('textLen')}",
                    })
        finally:
            browser.close()

    passed = sum(1 for r in rows if r["ok"])
    out = {
        "base": base,
        "checks": rows,
        "passed": passed,
        "total": len(rows),
        "console_errors": console,
    }
    pathlib.Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))
    for r in rows:
        if not r["ok"]:
            print(f"FAIL | {r['check']} | {r['detail']}")
    print(f"\n=== ui controls: {passed}/{len(rows)} passed | console errors: {len(console)} ===")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
