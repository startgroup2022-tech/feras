"""Inventory the running SPA: every view and tab, its heading and its controls.

Grounds the deck compliance matrix in what the app actually renders rather than
what the source claims. Run against a locally served, seeded instance::

    python scripts/audit/app_inventory.py --base http://127.0.0.1:12000 \
        --out artifacts/app_inventory.json

It signs in as the holding owner (widest scope) so every view is reachable, then
records per view/tab: the rendered heading, button/select/input counts, table row
count, and whether a filter bar / pager is present.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import re
import sys

from playwright.async_api import async_playwright

PASSWORD = "SafirDemo!2027"
OWNER = "owner@demo.safir.local"

VIEWS = [
    "dashboard", "leads", "requests", "feedback", "projects", "decisions",
    "subsidiaries", "reports", "financial", "investments", "support",
    "approvals", "documents", "bi", "analytics", "inbox", "employees",
    "operations", "accounting", "confidential", "admin",
]
TAB_GROUPS = {
    "employees": ("data-emp-tab", "#empContent"),
    "operations": ("data-ops-tab", "#opsContent"),
    "accounting": ("data-acct-tab", "#acctContent"),
    "confidential": ("data-conf-tab", "#confContent"),
    "admin": ("data-admin-tab", "#adminContent"),
    "analytics": ("data-an-tab", "#anContent"),
}


async def snapshot(page, section: str) -> dict:
    return await page.evaluate(
        """(sel) => {
          const root = document.querySelector(sel);
          if (!root) return null;
          const txt = (root.innerText || '').trim();
          const lines = txt.split('\\n').map(s=>s.trim()).filter(Boolean);
          const vis = (e) => e.offsetParent !== null;
          return {
            heading: lines[0] || '',
            second: lines[1] || '',
            chars: txt.length,
            buttons: [...root.querySelectorAll('button')].filter(vis).length,
            selects: [...root.querySelectorAll('select')].filter(vis).length,
            inputs: [...root.querySelectorAll('input,textarea')].filter(vis).length,
            rows: root.querySelectorAll('.av-row, tbody tr').length,
            filterbar: root.querySelectorAll('[data-filterbar], .list-filters, [id^="listFilter-"]').length,
            pager: root.querySelectorAll('[data-pager], .pager').length,
            savedFilter: /حفظ المرشح|Save filter/i.test(txt),
            exportBtn: /تصدير النتائج|Export results/i.test(txt),
            empty: /لا توجد|لا بيانات|no data|empty/i.test(txt),
            loading: /جارٍ|loading/i.test(txt) && txt.length < 200,
          };
        }""",
        section,
    )


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:12000")
    ap.add_argument("--out", default="artifacts/app_inventory.json")
    ap.add_argument("--lang", default="ar", choices=["ar", "en"])
    args = ap.parse_args()

    inv: dict = {"base": args.base, "lang": args.lang, "views": {}}
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path="/usr/bin/chromium", args=["--no-sandbox"]
        )
        ctx = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await ctx.new_page()
        await page.goto(f"{args.base}/platform/", wait_until="networkidle")
        await page.fill("#loginEmail", OWNER)
        await page.fill("#loginPassword", PASSWORD)
        await page.click("#loginBtn")
        await page.wait_for_selector("#loginScreen", state="hidden", timeout=20000)
        await page.wait_for_timeout(2500)
        if await page.locator("#sbMoreToggle").count():
            if await page.eval_on_selector("#sbMoreToggle", "e=>e.getAttribute('aria-expanded')") != "true":
                await page.click("#sbMoreToggle")
                await page.wait_for_timeout(400)

        for view in VIEWS:
            try:
                await page.click(f'.nav-item[data-view="{view}"]', timeout=5000)
            except Exception:
                await page.evaluate("v => { location.hash = v; }", view)
            await page.wait_for_timeout(1600)
            section = "#board" if view == "dashboard" else f"#view-{view}"
            entry = {"main": await snapshot(page, section), "tabs": {}}
            if view in TAB_GROUPS:
                attr, host = TAB_GROUPS[view]
                if view == "accounting":
                    secs = await page.eval_on_selector_all(
                        "[data-acct-section-btn]", "els=>els.map(e=>e.getAttribute('data-acct-section-btn'))")
                    for s in secs:
                        sel = f'[data-acct-section-btn="{s}"]'
                        if await page.is_visible(sel):
                            await page.click(sel); await page.wait_for_timeout(400)
                tabs = await page.eval_on_selector_all(
                    f"[{attr}]", "(els,a)=>els.map(e=>e.getAttribute(a))", attr)
                for t in tabs:
                    sel = f'[{attr}="{t}"]'
                    if view == "accounting" and not await page.is_visible(sel):
                        s = await page.eval_on_selector(sel, "e=>e.getAttribute('data-acct-section')")
                        if s and await page.is_visible(f'[data-acct-section-btn="{s}"]'):
                            await page.click(f'[data-acct-section-btn="{s}"]'); await page.wait_for_timeout(500)
                    if not await page.is_visible(sel):
                        entry["tabs"][t] = {"unreachable": True}; continue
                    try:
                        await page.click(sel, timeout=6000)
                    except Exception:
                        entry["tabs"][t] = {"unreachable": True}; continue
                    await page.wait_for_timeout(1400)
                    entry["tabs"][t] = await snapshot(page, host)
            inv["views"][view] = entry
            print(f"  inventoried {view} ({len(entry['tabs'])} tabs)", file=sys.stderr)
        await browser.close()

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(inv, ensure_ascii=False, indent=1))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
