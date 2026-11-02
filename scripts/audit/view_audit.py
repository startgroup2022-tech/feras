"""Phase 3 — functional audit harness for the 21 application views.

Logs in as each organizational role, walks every view, and records what a
reviewer needs to judge it: whether the section rendered, whether it rendered
*empty*, every failing HTTP response, every console error, and a screenshot.

Run it against a locally served app::

    APP_ENV=development DATABASE_URL="sqlite:///./safir_dev.db" \\
        python -m uvicorn backend.main:app --port 12000 &
    python scripts/audit/view_audit.py --base http://127.0.0.1:12000

It writes ``artifacts/view_audit.json`` plus PNGs under ``artifacts/shots/``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import re
import sys

from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts"
SHOTS = ARTIFACTS / "shots"

PASSWORD = "SafirDemo!2027"

# The 21 views, in sidebar order. ``nav`` is the sidebar entry to click;
# ``dashboard`` renders inline rather than as its own #view-* section.
VIEWS = [
    "dashboard", "leads", "requests", "feedback", "projects", "decisions",
    "subsidiaries", "reports", "financial", "investments", "support",
    "approvals", "documents", "bi", "analytics", "inbox", "employees",
    "operations", "accounting", "confidential", "admin",
]

# The seven spec roles (SAFIR_ROLE_PERMISSION_MATRIX.md §1).
ROLES = [
    ("holding_owner", "owner@demo.safir.local"),
    ("business_development", "bd@demo.safir.local"),
    ("company_manager", "manager.tech@demo.safir.local"),
    ("accountant", "accountant@demo.safir.local"),
    ("marketing", "marketing@demo.safir.local"),
    ("designer", "design@demo.safir.local"),
    ("external_consultant", "consultant@demo.safir.local"),
]

LOADING = re.compile(r"(loading|جارٍ|يتم التحميل)", re.I)

# Views whose content is split into tabs. ``(attr, host)`` -- the button
# attribute that selects a tab, and the container the tab renders into.
TAB_GROUPS = {
    "employees": ("data-emp-tab", "#empContent"),
    "operations": ("data-ops-tab", "#opsContent"),
    "accounting": ("data-acct-tab", "#acctContent"),
    "confidential": ("data-conf-tab", "#confContent"),
    "admin": ("data-admin-tab", "#adminContent"),
    "analytics": ("data-an-tab", "#anContent"),
}

# Views whose own sub-navigation swaps the primary body.
SUBVIEW_GROUPS = {
    "leads": ("data-lead-view", ["leads", "opportunities"]),
}


def _view_html_ids(html: str) -> list[str]:
    """Views that own a real ``#view-*`` section, straight from the markup."""
    return re.findall(r'class="app-view[^"]*"\s+id="(view-[^"]+)"', html)


async def audit_role(
    browser, base: str, role: str, email: str, *, lang="ar", viewport=None
) -> dict:
    vp = viewport or {"width": 1920, "height": 1080}
    ctx = await browser.new_context(viewport=vp)
    page = await ctx.new_page()

    bad_http: list[dict] = []
    console_errors: list[str] = []
    page.on(
        "response",
        lambda r: bad_http.append({"status": r.status, "url": r.url})
        if r.status >= 400
        else None,
    )
    page.on(
        "console",
        lambda m: console_errors.append(m.text)
        if m.type == "error"
        else None,
    )

    await page.goto(f"{base}/platform/", wait_until="networkidle")
    await page.fill("#loginEmail", email)
    await page.fill("#loginPassword", PASSWORD)
    await page.click("#loginBtn")
    try:
        await page.wait_for_selector("#loginScreen", state="hidden", timeout=15000)
    except Exception:
        return {"role": role, "error": "login failed", "console": console_errors[-5:]}
    await page.wait_for_timeout(2500)

    # Language is persisted per browser context, so a fresh context always
    # starts in Arabic (the spec default). Switch only when asked.
    if lang != "ar":
        await page.evaluate("(l) => localStorage.setItem('safir.lang.v1', l)", lang)
        await page.reload(wait_until="networkidle")
        await page.wait_for_timeout(2500)

    # On a phone the rail is a ☰ drawer (deck slides 39/89/90); open it so the
    # entries are clickable. On desktop the toggle is hidden and this is a no-op.
    async def _ensure_drawer():
        toggle = page.locator("#navToggle")
        if await toggle.count() and await toggle.is_visible():
            if not await page.evaluate(
                "() => document.body.classList.contains('nav-open')"
            ):
                await toggle.click()
                await page.wait_for_timeout(350)

    await _ensure_drawer()

    # The sidebar hides 15 of the 21 entries inside a collapsed "More"
    # group, so open it before asking what RBAC let this role see.
    if await page.locator("#sbMoreToggle").count():
        expanded = await page.eval_on_selector(
            "#sbMoreToggle", "e => e.getAttribute('aria-expanded')"
        )
        if expanded != "true":
            await page.click("#sbMoreToggle")
            await page.wait_for_timeout(500)

    await _ensure_drawer()

    visible_nav = await page.eval_on_selector_all(
        ".nav-item",
        "els => els.filter(e => e.offsetParent !== null).map(e => e.dataset.view)",
    )

    result: dict = {
        "role": role,
        "visible_nav": visible_nav,
        "views": {},
        "console_errors": [],
        "bad_http": [],
    }

    for view in VIEWS:
        before_http = len(bad_http)
        before_console = len(console_errors)
        shown = view in visible_nav
        entry: dict = {"nav_visible": shown}

        if shown:
            await _ensure_drawer()
            try:
                await page.click(f'.nav-item[data-view="{view}"]', timeout=5000)
            except Exception:
                # Some views are only reachable by hash (e.g. deep links).
                await page.evaluate("v => { location.hash = v; }", view)
            await page.wait_for_timeout(1800)

            section = "#board" if view == "dashboard" else f"#view-{view}"
            text = await page.eval_on_selector(
                section, "e => e.innerText", strict=False
            ) if await page.locator(section).count() else ""
            text = (text or "").strip()

            entry["chars"] = len(text)
            entry["empty"] = len(text) < 40
            entry["still_loading"] = bool(LOADING.search(text)) and len(text) < 200
            entry["snippet"] = text[:200].replace("\n", " | ")
            entry["sections"] = await page.locator(f"{section} .av-row, {section} tbody tr").count()

            await page.screenshot(path=str(SHOTS / f"{role}-{view}.png"), full_page=True)

            # Tabbed views render one panel at a time; a tab that throws or
            # returns nothing is invisible to a single-view crawl.
            if view in TAB_GROUPS:
                attr, host = TAB_GROUPS[view]
                # Accounting nests sub-tabs under a section row; open each
                # section so its sub-tabs become clickable.
                sections = await page.eval_on_selector_all(
                    "[data-acct-section-btn]",
                    "els => els.map(e => e.getAttribute('data-acct-section-btn'))",
                ) if view == "accounting" else []
                if sections:
                    for sec in sections:
                        ssel = f'[data-acct-section-btn="{sec}"]'
                        if await page.is_visible(ssel):
                            await page.click(ssel)
                            await page.wait_for_timeout(600)
                tabs = await page.eval_on_selector_all(
                    f"[{attr}]", "(els, a) => els.map(e => e.getAttribute(a))", attr
                )
                entry["tabs"] = {}
                for tab in tabs:
                    sel = f'[{attr}="{tab}"]'
                    if view == "accounting" and not await page.is_visible(sel):
                        sec = await page.eval_on_selector(
                            sel, "e => e.getAttribute('data-acct-section')"
                        )
                        if sec:
                            ssel = f'[data-acct-section-btn="{sec}"]'
                            if await page.is_visible(ssel):
                                await page.click(ssel)
                                await page.wait_for_timeout(700)
                    # Secondary tabs only exist once their parent panel is
                    # open; skip the ones this pass cannot reach rather than
                    # aborting the whole crawl.
                    if not await page.is_visible(sel):
                        entry["tabs"][tab] = {"unreachable": True}
                        continue
                    h0, c0 = len(bad_http), len(console_errors)
                    try:
                        await page.click(sel, timeout=8000)
                    except Exception:
                        entry["tabs"][tab] = {"unreachable": True}
                        continue
                    await page.wait_for_timeout(1500)
                    ttext = (await page.eval_on_selector(host, "e => e.innerText") or "").strip()
                    entry["tabs"][tab] = {
                        "chars": len(ttext),
                        "empty": len(ttext) < 40,
                        "still_loading": bool(LOADING.search(ttext)) and len(ttext) < 200,
                        "snippet": ttext[:160].replace("\n", " | "),
                        "http_errors": bad_http[h0:],
                        "console_errors": console_errors[c0:],
                    }
                    await page.screenshot(
                        path=str(SHOTS / f"{role}-{view}-{tab}.png"), full_page=True
                    )

            if view in SUBVIEW_GROUPS:
                attr, subs = SUBVIEW_GROUPS[view]
                entry["subviews"] = {}
                for sub in subs:
                    ssel = f'[{attr}="{sub}"]'
                    if not await page.is_visible(ssel):
                        entry["subviews"][sub] = {"unreachable": True}
                        continue
                    h0, c0 = len(bad_http), len(console_errors)
                    await page.click(ssel, timeout=8000)
                    await page.wait_for_timeout(1500)
                    stext = (await page.eval_on_selector(f"#view-{view}", "e => e.innerText") or "").strip()
                    entry["subviews"][sub] = {
                        "chars": len(stext),
                        "empty": len(stext) < 40,
                        "snippet": stext[:160].replace("\n", " | "),
                        "http_errors": bad_http[h0:],
                        "console_errors": console_errors[c0:],
                    }
                    await page.screenshot(
                        path=str(SHOTS / f"{role}-{view}-{sub}.png"), full_page=True
                    )
        else:
            # A hidden view must not leak content to a role that lacks the perm.
            section = f"#view-{view}"
            if await page.locator(section).count():
                vis = await page.eval_on_selector(
                    section, "e => e.offsetParent !== null"
                )
                entry["hidden_but_visible"] = bool(vis)

        entry["new_http_errors"] = bad_http[before_http:]
        entry["new_console_errors"] = console_errors[before_console:]
        result["views"][view] = entry

    result["bad_http"] = bad_http
    result["console_errors"] = console_errors
    await ctx.close()
    return result


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:12000")
    ap.add_argument("--roles", default="", help="comma-separated role codes")
    ap.add_argument("--lang", default="ar", choices=["ar", "en"])
    ap.add_argument("--viewport", default="1920x1080")
    args = ap.parse_args()

    ARTIFACTS.mkdir(exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)

    wanted = {r.strip() for r in args.roles.split(",") if r.strip()}
    roles = [r for r in ROLES if not wanted or r[0] in wanted]

    out = {"base": args.base, "views": VIEWS, "roles": {}}
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path="/usr/bin/chromium", args=["--no-sandbox"]
        )
        for role, email in roles:
            print(f"auditing {role} ...", file=sys.stderr)
            w, h = (int(x) for x in args.viewport.split("x"))
            out["roles"][role] = await audit_role(
                browser, args.base, role, email,
                lang=args.lang, viewport={"width": w, "height": h},
            )
        await browser.close()

    out["lang"] = args.lang
    out["viewport"] = args.viewport
    (ARTIFACTS / "view_audit.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2)
    )
    print(f"wrote {ARTIFACTS / 'view_audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
