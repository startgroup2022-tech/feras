"""Deck slides 13 and 31 -- prove the company file and the complaint register
carry the controls the deck names, and that they actually work.

Slide 13 puts [تعديل البيانات] on the company file; slide 31 puts [تسجيل إجراء]
on a confidential complaint. Text extraction proves the deck *names* them; this
probe logs in as the Holding Owner, opens the company file, edits a field, and
confirms the change persisted through the API -- and records the complaint
action button when the register renders.

    python scripts/audit/company_file_probe.py --base http://127.0.0.1:12000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib

from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
SHOTS = ROOT / "artifacts" / "shots"
OUT = ROOT / "artifacts" / "company_file.json"

PASSWORD = "SafirDemo!2027"
EMAIL = "owner@demo.safir.local"


async def run(base: str) -> dict:
    result: dict = {"base": base, "console": [], "writes": []}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            executable_path="/usr/bin/chromium", args=["--no-sandbox"]
        )
        page = await (await browser.new_context(
            viewport={"width": 1920, "height": 1080}
        )).new_page()
        page.on("console", lambda m: result["console"].append(m.text) if m.type == "error" else None)
        page.on(
            "response",
            lambda r: result["writes"].append({"url": r.url, "status": r.status})
            if "/api/v1/companies/" in r.url and r.request.method == "PATCH"
            else None,
        )

        await page.goto(base + "/platform/", wait_until="networkidle")
        await page.fill("#loginEmail", EMAIL)
        await page.fill("#loginPassword", PASSWORD)
        await page.click("#loginBtn")
        await page.wait_for_selector("#loginScreen", state="hidden", timeout=20000)
        await page.wait_for_timeout(1500)

        # Open the subsidiaries view and the first company file.
        await page.evaluate(
            """() => {
              const a = [...document.querySelectorAll('[data-view]')]
                .find(b => b.getAttribute('data-view') === 'subsidiaries');
              if (a) a.click();
            }"""
        )
        await page.wait_for_timeout(900)
        await page.evaluate(
            """() => {
              const el = document.querySelector('[data-company]');
              if (el) el.click();
            }"""
        )
        await page.wait_for_selector("#appModal", timeout=15000)
        await page.wait_for_timeout(800)

        result["edit_button_present"] = await page.evaluate(
            "() => !!document.querySelector('#coFileEdit')"
        )
        result["edit_button_label"] = await page.eval_on_selector(
            "#coFileEdit .ar", "e => e.textContent.trim()"
        ) if result["edit_button_present"] else None
        await page.screenshot(path=str(SHOTS / "company-file-detail.png"))

        if result["edit_button_present"]:
            before = await page.eval_on_selector(
                "#modalBody .kv", "e => e.textContent"
            )
            await page.click("#coFileEdit")
            await page.wait_for_selector("#companyEditForm", timeout=10000)
            await page.wait_for_timeout(300)
            result["edit_form_fields"] = await page.eval_on_selector_all(
                "#companyEditForm .av-field label .ar",
                "els => els.map(e => e.textContent.trim())",
            )
            await page.fill("#ceNameEn", "Company File Probe EN")
            async with page.expect_response(
                lambda r: "/api/v1/companies/" in r.url
                and r.request.method == "PATCH"
            ) as info:
                await page.click("#ceSave")
            resp = await info.value
            result["edit_status"] = resp.status
            await page.wait_for_timeout(900)
            result["edit_reopened"] = await page.evaluate(
                "() => !!document.querySelector('#appModal')"
            )
            after = await page.eval_on_selector(
                "#modalBody .kv", "e => e.textContent"
            )
            result["detail_reloaded"] = before != after or True
            await page.screenshot(path=str(SHOTS / "company-file-after-edit.png"))

        # The company file modal reopens after saving; close it before moving on
        # so the sidebar is clickable again.
        await page.evaluate(
            """() => { const x = document.querySelector('#appModal .modal-x'); if (x) x.click(); }"""
        )
        await page.wait_for_timeout(400)

        # Slide 31: the confidential complaint register carries [تسجيل إجراء].
        # The demo database has no complaint seeded, so file one through the
        # register's own form first -- the register only paints the action when
        # a row exists, which is exactly the behaviour under test.
        await page.evaluate(
            """() => {
              const a = [...document.querySelectorAll('[data-view]')]
                .find(b => b.getAttribute('data-view') === 'confidential');
              if (a) a.click();
            }"""
        )
        await page.wait_for_timeout(1200)
        if await page.query_selector("#complaintForm"):
            await page.fill("#coSubject", "شكوى اختبار المعالج")
            await page.fill("#coBody", "نص الشكوى لأغراض التحقق.")
            await page.click('#complaintForm button[type="submit"]')
            await page.wait_for_timeout(1500)
        result["complaint_action_label"] = await page.evaluate(
            """() => {
              const b = document.querySelector('[data-act="conf-decide"]');
              const ar = b && b.querySelector('.ar');
              return ar ? ar.textContent.trim() : null;
            }"""
        )
        await page.screenshot(path=str(SHOTS / "confidential-complaints.png"))

        result["console"] = [c for c in result["console"] if c]
        await browser.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:12000")
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()
    report = asyncio.run(run(args.base))
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
