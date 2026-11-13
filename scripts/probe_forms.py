"""Probe every inline form for empty-submit faults.

For each routed view, find each ``<form>`` and click its submit control while the
form is empty. A 4xx response means the client let an invalid payload through,
which surfaces to the user as a console error. The reference prototype prevents
this with ``required`` markers on every mandatory field.

    BASE_URL=http://127.0.0.1:12001 python -m scripts.probe_forms
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "forms_probe.json"

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:12001").rstrip("/")
CHROMIUM = os.environ.get("CHROMIUM", "/usr/bin/chromium")
PASSWORD = os.environ.get("DEMO_PASSWORD", "SafirDemo!2027")
OWNER = "owner@demo.safir.local"

VIEWS = [
    "dashboard", "leads", "requests", "advisory", "opportunities", "decisions",
    "reports", "employees", "hr", "assets", "site", "aiReview", "group",
    "accounting", "operations", "confidential", "analytics", "bi",
    "subsidiaries", "financial", "support", "approvals", "documents", "inbox",
    "investments",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=BASE)
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()
    base = args.base.rstrip("/")

    rows: list[dict] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
        page = browser.new_context(viewport={"width": 1600, "height": 950}).new_page()
        bad: list = []
        page.on("response", lambda r: bad.append(
            {"status": r.status, "method": r.request.method, "url": r.url}
        ) if r.status >= 400 and "/api/" in r.url else None)
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
                forms = page.evaluate(
                    """() => Array.from(document.querySelectorAll('.app-view:not(.view-hidden) form'))
                        .map((f, i) => ({i, id: f.id || '', cls: f.className}))"""
                )
                for f in forms:
                    sel = f"#{f['id']}" if f["id"] else None
                    if not sel:
                        continue
                    btn = page.query_selector(sel + " button[type=submit], " + sel + " button:not([type])")
                    if not btn:
                        continue
                    if page.evaluate("(s)=>{const f=document.querySelector(s);return f && !f.offsetParent;}", sel):
                        continue
                    bad.clear()
                    try:
                        btn.click(timeout=4000)
                    except Exception as exc:  # noqa: BLE001
                        rows.append({"view": view, "form": sel, "error": repr(exc)[:120]})
                        continue
                    page.wait_for_timeout(1200)
                    rows.append({"view": view, "form": sel,
                                 "empty_submit_4xx": list(bad)})
        finally:
            browser.close()

    faults = [r for r in rows if r.get("empty_submit_4xx")]
    pathlib.Path(args.out).write_text(json.dumps({"rows": rows, "faults": faults},
                                                 ensure_ascii=False, indent=2))
    for r in rows:
        if r.get("empty_submit_4xx"):
            for b in r["empty_submit_4xx"]:
                print(f"FAULT | {r['view']:12s} | {r['form']:22s} | {b['status']} {b['method']} {b['url']}")
    print(f"\n=== forms probed: {len(rows)} | empty-submit faults: {len(faults)} ===")
    return 0 if not faults else 1


if __name__ == "__main__":
    sys.exit(main())
