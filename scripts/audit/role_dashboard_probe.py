"""Deck slides 7-11 -- prove each role renders its own dashboard strip.

The compliance matrix reads the API, which proves the *payload* differs. This
probe proves the *rendered page* differs: it signs in as each primary role,
screenshots the dashboard at 1920x1080, and records which strip is visible
(``#roleKpis`` versus the holding ``#holdingKpis``) and the tile labels.

    python scripts/audit/role_dashboard_probe.py --base http://127.0.0.1:12000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib

from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
SHOTS = ROOT / "artifacts" / "shots"
OUT = ROOT / "artifacts" / "role_dashboards.json"
PASSWORD = "SafirDemo!2027"

ROLES = [
    ("holding_owner", "owner@demo.safir.local"),
    ("business_development", "bd@demo.safir.local"),
    ("company_manager", "manager.tech@demo.safir.local"),
    ("designer", "design@demo.safir.local"),
    ("marketing", "marketing@demo.safir.local"),
    ("accountant", "accountant@demo.safir.local"),
]


async def _probe_role(browser, base: str, role: str, email: str) -> dict:
    ctx = await browser.new_context(viewport={"width": 1920, "height": 1080})
    page = await ctx.new_page()
    errors: list[str] = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

    await page.goto(f"{base}/platform/?year=2027&month=10", wait_until="networkidle")
    await page.fill("#loginEmail", email)
    await page.fill("#loginPassword", PASSWORD)
    await page.click("#loginBtn")
    try:
        await page.wait_for_selector("#loginScreen", state="hidden", timeout=15000)
    except Exception:
        await ctx.close()
        return {"role": role, "error": "login failed", "console": errors[-5:]}
    await page.wait_for_timeout(2500)

    shot = SHOTS / f"role-dashboard-{role}.png"
    SHOTS.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(shot))

    role_hidden = await page.eval_on_selector(
        "#roleKpis", "e => e.hidden"
    ) if await page.locator("#roleKpis").count() else None
    holding_hidden = await page.eval_on_selector(
        "#holdingKpis", "e => e.hidden"
    ) if await page.locator("#holdingKpis").count() else None
    role_text = await page.eval_on_selector(
        "#roleKpis", "e => e.innerText", strict=False
    ) if await page.locator("#roleKpis").count() else ""
    # Read the tile labels from the label nodes rather than parsing innerText,
    # which interleaves values and units with the labels.
    labels = await page.eval_on_selector_all(
        "#roleKpis .kpi-lbl .ar", "els => els.map(e => e.textContent.trim())"
    ) if await page.locator("#roleKpis .kpi-lbl .ar").count() else []
    page_title = await page.eval_on_selector(
        "#pageTitle .ar", "e => e.textContent.trim()", strict=False
    ) if await page.locator("#pageTitle .ar").count() else ""
    greeting = await page.eval_on_selector(
        "#pageSub .ar", "e => e.textContent.trim()", strict=False
    ) if await page.locator("#pageSub .ar").count() else ""
    # The deck draws the role tiles as one row across the content width, so
    # record the strip's box and column count, not just the labels.
    strip = await page.evaluate(
        """() => {
          const e = document.querySelector('#roleKpis');
          if (!e || e.hidden) return null;
          const r = e.getBoundingClientRect();
          const cols = getComputedStyle(e).gridTemplateColumns.split(' ').length;
          return {x: Math.round(r.x), y: Math.round(r.y),
                  w: Math.round(r.width), h: Math.round(r.height), cols};
        }"""
    )

    await ctx.close()
    return {
        "role": role,
        "role_strip_visible": role_hidden is False,
        "holding_strip_visible": holding_hidden is False,
        "role_strip_labels": labels,
        "page_title": page_title,
        "greeting": greeting,
        "strip_box": strip,
        "role_strip_text": (role_text or "").strip().replace("\n", " | "),
        "console_errors": errors,
        "screenshot": str(shot.relative_to(ROOT)),
    }


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:12000")
    args = ap.parse_args()

    results: dict[str, dict] = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            executable_path="/usr/bin/chromium", args=["--no-sandbox"]
        )
        for role, email in ROLES:
            print(f"probing {role} ...")
            results[role] = await _probe_role(browser, args.base, role, email)
        await browser.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=1, ensure_ascii=False))
    print(f"wrote {OUT}")
    for role, r in results.items():
        print(f"  {role}: role_strip={r.get('role_strip_visible')} "
              f"holding_strip={r.get('holding_strip_visible')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
