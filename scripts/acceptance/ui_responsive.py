"""Phase 4 section 4 — UI, responsiveness and RTL/LTR acceptance.

Phase 3's ``scripts/audit/view_audit.py`` already walked all 21 views as all 7
roles at 1920×1080. This pass answers a narrower but complementary question:
does the shell stay usable and correctly directed at laptop/tablet/mobile
widths, in both languages, without the document overflowing its frame?

Signals recorded per (view, language, viewport):

* the view rendered content (not a blank panel or a console error);
* ``documentElement`` does not overflow horizontally (the classic RTL/mobile
  bug where an absolutely-positioned sidebar pushes the page wide);
* the document direction matches the active language;
* navigation stays present.

Run: ``python -m scripts.acceptance.ui_responsive --base http://127.0.0.1:12099``
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys

from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts" / "phase4"
PASSWORD = "SafirDemo!2027"
OWNER = "owner@demo.safir.local"

# The full 21-view sidebar, in navigation order — the same list Phase 3's
# ``scripts/audit/view_audit.py`` walks, so the two passes cover the same
# surface at different widths.
VIEWS = [
    "dashboard", "leads", "requests", "feedback", "projects", "decisions",
    "subsidiaries", "reports", "financial", "investments", "support",
    "approvals", "documents", "bi", "analytics", "inbox", "employees",
    "operations", "accounting", "confidential", "admin",
]

VIEWPORTS = {
    "desktop-1920": (1920, 1080),
    "laptop-1440": (1440, 900),
    "tablet-834": (834, 1112),
    "mobile-390": (390, 844),
}

LANGS = ["ar", "en"]

RESULTS: list[tuple[str, str, str]] = []


def record(name, ok, detail=""):
    RESULTS.append((name, "PASS" if ok else "FAIL", detail))


async def _login(page, base):
    await page.goto(base + "/platform/", wait_until="domcontentloaded")
    await page.wait_for_timeout(500)
    if await page.locator("#loginEmail").count():
        await page.fill("#loginEmail", OWNER)
        await page.fill("#loginPassword", PASSWORD)
        await page.click("#loginBtn")
        await page.wait_for_timeout(2000)


async def _open_view(page, view):
    """Click the sidebar entry for ``view`` (the SPA is an IIFE, so the
    internal ``loadView`` is not reachable from the page context).

    On a phone the rail lives in the ☰ drawer (deck slides 39/89/90), so the
    drawer is opened first when the toggle is visible."""
    toggle = page.locator("#navToggle")
    if await toggle.count() and await toggle.is_visible():
        if not await page.evaluate("() => document.body.classList.contains('nav-open')"):
            await toggle.click()
            await page.wait_for_timeout(350)
    item = page.locator(f'.nav-item[data-view="{view}"]').first
    if await item.count():
        try:
            await item.click(timeout=3000)
            await page.wait_for_timeout(800)
            return
        except Exception:
            pass
    # Fall back to the hash route the SPA itself uses.
    await page.goto(f"{page.url.split('#')[0]}#{view}",
                    wait_until="domcontentloaded")
    await page.wait_for_timeout(800)


async def _set_lang(page, lang):
    """Click the *platform* language toggle (the login screen keeps a hidden
    duplicate, which is what an unscoped selector would otherwise hit)."""
    btn = page.locator(f'.lang-switch [data-lang="{lang}"]').first
    if not await btn.count():
        btn = page.locator(f'.lang-opt[data-lang="{lang}"]').last
    if await btn.count():
        try:
            await btn.click(timeout=2000)
        except Exception:
            pass
    await page.wait_for_timeout(500)
    return await page.evaluate(
        "() => document.documentElement.getAttribute('dir')")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:12099")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    print(f"Phase 4 UI/responsiveness against {args.base}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=not args.headed,
            executable_path="/usr/bin/chromium",
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        for vp_name, (w, h) in VIEWPORTS.items():
            ctx = await browser.new_context(
                viewport={"width": w, "height": h}, locale="ar-SA")
            page = await ctx.new_page()
            errors: list[str] = []
            page.on("console", lambda m: errors.append(m.text)
                    if m.type == "error" else None)
            await _login(page, args.base)
            for lang in LANGS:
                await _set_lang(page, lang)
                for view in VIEWS:
                    errors.clear()
                    await _open_view(page, view)
                    label = f"{vp_name}/{lang}/{view}"
                    try:
                        info = await page.evaluate(
                            """() => {
                                const de = document.documentElement;
                                return {
                                  dir: de.getAttribute('dir')
                                       || getComputedStyle(de).direction,
                                  overflowX: de.scrollWidth - de.clientWidth,
                                  text: (document.body.innerText || '').trim().length,
                                  navVisible: !!document.querySelector(
                                      'nav, aside, .sidebar'),
                                };
                            }"""
                        )
                        want_dir = "rtl" if lang == "ar" else "ltr"
                        ok = (info["dir"] == want_dir
                              and info["overflowX"] <= 2
                              and info["text"] > 200
                              and info["navVisible"]
                              and not errors)
                        detail = (f"dir={info['dir']} overflowX={info['overflowX']} "
                                  f"chars={info['text']} nav={info['navVisible']} "
                                  f"consoleErrors={len(errors)}")
                        record(label, ok, detail)
                        if not ok:
                            await page.screenshot(
                                path=str(ARTIFACTS / f"FAIL-{vp_name}-{lang}-{view}.png"),
                                full_page=True)
                    except Exception as e:  # noqa: BLE001
                        record(label, False, f"{type(e).__name__}: {e}")
            await ctx.close()
        await browser.close()

    out = ARTIFACTS / "ui_responsive.json"
    out.write_text(json.dumps(
        [{"case": n, "status": s, "detail": d} for n, s, d in RESULTS],
        ensure_ascii=False, indent=2))
    passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
    failed = len(RESULTS) - passed
    print(f"\n=== ui/responsive: {passed} passed, {failed} failed of {len(RESULTS)} ===")
    for n, s, d in RESULTS:
        if s == "FAIL":
            print(f"  FAIL {n}: {d}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
