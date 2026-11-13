"""Deck slides 50-52 -- prove the company setup wizard works in the browser.

Text extraction proves the deck *names* a three-step wizard; it does not prove
the app *renders* one or that its steps behave. This probe signs in as the
Holding Owner, opens الجهات / الشركات, and drives the wizard end to end at
1920x1080: it records the three step labels, walks step 1 -> 2 -> 3, fills the
required fields, activates the company, and confirms the row was created with
the wizard's own fields persisted (not just accepted then dropped).

    python scripts/audit/company_wizard_probe.py --base http://127.0.0.1:12000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import uuid

from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
SHOTS = ROOT / "artifacts" / "shots"
OUT = ROOT / "artifacts" / "company_wizard.json"
PASSWORD = "SafirDemo!2027"
OWNER = "owner@demo.safir.local"


async def _run(browser, base: str) -> dict:
    result: dict = {"steps": [], "actions": [], "console": [], "created": None}
    ctx = await browser.new_context(viewport={"width": 1920, "height": 1080})
    page = await ctx.new_page()
    page.on(
        "console",
        lambda m: result["console"].append(m.text) if m.type == "error" else None,
    )
    result["writes"] = []

    def _record(request):
        if request.method in ("POST", "PATCH", "PUT"):
            result["writes"].append({"method": request.method, "url": request.url})

    page.on("request", _record)

    await page.goto(f"{base}/platform/?year=2027&month=10", wait_until="networkidle")
    await page.fill("#loginEmail", OWNER)
    await page.fill("#loginPassword", PASSWORD)
    await page.click("#loginBtn")
    await page.wait_for_selector("#loginScreen", state="hidden", timeout=15000)
    await page.wait_for_timeout(1500)

    # Open the companies administration tab. The admin rail is rendered once the
    # admin view is active; navigate there, then click the companies tab.
    await page.evaluate(
        """() => {
          const nav = [...document.querySelectorAll('[data-view]')];
          const admin = nav.find(b => b.getAttribute('data-view') === 'admin');
          if (admin) admin.click();
        }"""
    )
    await page.wait_for_timeout(800)
    await page.evaluate(
        """() => {
          const tab = document.querySelector('[data-admin-tab="companies"]');
          if (tab) tab.click();
        }"""
    )
    await page.wait_for_selector("#companyWizard", timeout=15000)
    await page.wait_for_timeout(400)

    SHOTS.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(SHOTS / "company-wizard-step1.png"))

    # The deck's step rail (slides 50-52) replaces a row of step pills.
    result["rail_step"] = await page.eval_on_selector(
        "#companyWizard #cwRailStep .ar", "e => e.textContent.trim()"
    )
    result["rail_name"] = await page.eval_on_selector(
        "#companyWizard #cwRailName .ar", "e => e.textContent.trim()"
    )
    result["actions"] = await page.eval_on_selector_all(
        "#companyWizard .co-wiz-actions button .ar",
        "els => els.map(e => e.textContent.trim())",
    )
    # Every field label the deck names across slides 50-52 must be on screen.
    # Substring match, because the app suffixes "(عربي)" / "*" to a few labels.
    pane_labels = await page.eval_on_selector_all(
        "#companyWizard .co-wiz-pane label .ar",
        "els => els.map(e => e.textContent.trim())",
    )
    deck_labels = {
        "50": ["الاسم القانوني", "الاسم التجاري", "الدولة", "رقم التسجيل", "النشاط",
               "القطاع", "العملة الأساسية", "السنة المالية"],
        "51": ["نسبة ملكية القابضة", "رأس المال", "تاريخ الاستثمار", "مدير الشركة",
               "بدء المتابعة", "حالة الشركة", "المستخدمون المرتبطون", "اللغة"],
        "52": ["نموذج القطاع", "المؤشرات المختارة", "مستوى الوصول", "مراجعة الإعداد",
               "تاريخ نفاذ القالب", "إقرار المراجعة"],
    }
    result["deck_label_parity"] = {
        slide: {
            label: any(label in rendered for rendered in pane_labels)
            for label in labels
        }
        for slide, labels in deck_labels.items()
    }
    result["missing_deck_labels"] = [
        f"{slide}:{label}"
        for slide, found in result["deck_label_parity"].items()
        for label, ok in found.items()
        if not ok
    ]
    # The deck lays each step out as a two-column grid read right-to-left, so
    # the *order* of the labels is part of the parity, not just their presence.
    pane_order = await page.evaluate(
        """() => {
          const out = {};
          for (const n of [1, 2, 3]) {
            const pane = document.querySelector(
              `#companyWizard .co-wiz-pane[data-pane="${n}"]`);
            out[n] = pane
              ? [...pane.querySelectorAll('label .ar')].map(e => e.textContent.trim())
              : [];
          }
          return out;
        }"""
    )
    result["pane_order"] = pane_order

    def _norm(text: str) -> str:
        # The rendered label carries the deck's own "*" marker and may append a
        # hint after an em dash; the deck cell carries the marker too. Compare
        # the words, not the punctuation.
        return text.replace("*", "").split("—")[0].split("–")[0].strip()

    result["deck_order_parity"] = {
        slide: [_norm(x) for x in labels] == [_norm(x) for x in pane_order[str(idx)]]
        for idx, (slide, labels) in enumerate(deck_labels.items(), start=1)
    }
    result["order_mismatch"] = [
        slide for slide, ok in result["deck_order_parity"].items() if not ok
    ]

    def pane_visible(n: int) -> str:
        return (
            "() => { const p = document.querySelector("
            f"'#companyWizard .co-wiz-pane[data-pane=\"{n}\"]');"
            " return p ? !p.hidden : null; }"
        )

    result["pane1_visible_on_open"] = await page.evaluate(pane_visible(1))

    # Deck slides 50-52 place the step rail at the right edge (RTL) and the
    # form to its left. Measure the live boxes rather than trusting the markup.
    boxes = await page.evaluate(
        """() => {
          const b = (sel) => {
            const e = document.querySelector(sel);
            if (!e) return null;
            const r = e.getBoundingClientRect();
            return {x: Math.round(r.x), w: Math.round(r.width)};
          };
          const fields = [...document.querySelectorAll(
            '#companyWizard .co-wiz-pane[data-pane="1"] .av-field'
          )].map((f) => Math.round(f.getBoundingClientRect().width));
          return {dir: document.documentElement.dir,
                  rail: b('.co-wiz-rail'), form: b('.co-wiz-form'),
                  fieldWidths: fields};
        }"""
    )
    result["rail_box"] = boxes["rail"]
    result["form_box"] = boxes["form"]
    result["rail_on_right"] = bool(
        boxes["dir"] == "rtl"
        and boxes["rail"] and boxes["form"]
        and boxes["rail"]["x"] > boxes["form"]["x"]
    )
    # The deck's form is a two-column grid, not one full-width column.
    widths = boxes["fieldWidths"]
    result["two_column_grid"] = bool(
        len(widths) >= 4 and len(set(widths)) <= 3
        and min(widths) < max(widths) * 0.75
    )

    code = "PW-" + uuid.uuid4().hex[:6].upper()

    # Step 1 -- identity & sector (deck slide 50). The English name is not a
    # deck field on this screen (only "الاسم القانوني *" is shown), so it is
    # left blank: the company is created with an Arabic name alone.
    await page.fill("#cwNameAr", "شركة اختبار المعالج")
    await page.fill("#cwCountry", "SA")
    await page.fill("#cwRegistration", "CR-9999")
    await page.fill("#cwActivity", "أنشطة برمجية")
    sector_value = await page.evaluate(
        """() => {
          const s = document.querySelector('#cwSector');
          return s && s.options.length ? s.options[0].value : '';
        }"""
    )
    await page.select_option("#cwSector", sector_value)

    # Deck slide 52: saving a draft must not create access or investments.
    await page.click('#companyWizard [data-wiz="draft"]')
    await page.wait_for_timeout(700)
    result["draft_writes"] = [w["url"] for w in result["writes"]]
    result["draft_created_no_access"] = not any(
        ("company-access" in w["url"]) or ("ownerships" in w["url"])
        for w in result["writes"]
    )

    await page.click('#companyWizard [data-wiz="next"]')
    await page.wait_for_timeout(300)
    result["pane2_visible_after_next"] = await page.evaluate(pane_visible(2))

    # Step 2 -- ownership & monitoring.
    await page.fill("#cwCapital", "1000000")
    await page.fill("#cwOwnership", "100")
    await page.fill("#cwTracking", "2027-01-01")
    await page.select_option("#cwStatus", "active")
    await page.select_option("#cwLanguage", "ar")
    # Pick a real manager (deck slide 51: "مدير الشركة *").
    manager_value = await page.evaluate(
        """() => {
          const sel = document.querySelector('#cwManager');
          return sel && sel.options.length ? sel.options[0].value : '';
        }"""
    )
    if manager_value:
        await page.select_option("#cwManager", manager_value)
    result["manager_selected"] = manager_value
    await page.click('#companyWizard [data-wiz="next"]')
    await page.wait_for_timeout(300)
    result["pane3_visible_after_next"] = await page.evaluate(pane_visible(3))
    result["rail_step_on_3"] = await page.eval_on_selector(
        "#companyWizard #cwRailStep .ar", "e => e.textContent.trim()"
    )
    result["review_rows"] = await page.eval_on_selector_all(
        "#cwReview .co-wiz-rrow span .ar", "els => els.map(e => e.textContent.trim())"
    )
    # Slide 52: "مراجعة الإعداد: الدولة والعملة والمدير والدورية".
    result["review_has_deck_rows"] = all(
        any(want in r for r in result["review_rows"])
        for want in ("الدولة والعملة", "المدير", "الدورية")
    )
    await page.screenshot(path=str(SHOTS / "company-wizard-step3.png"))

    # Step 3 -- template & activation. A draft was already saved in step 1, so
    # activation PATCHes it; capture whichever company write lands.
    async with page.expect_response(
        lambda r: "/api/v1/companies" in r.url
        and r.request.method in ("POST", "PATCH")
    ) as resp_info:
        template_value = await page.evaluate(
            """() => {
              const s = document.querySelector('#cwTemplate');
              return s && s.options.length ? s.options[0].value : '';
            }"""
        )
        await page.select_option("#cwTemplate", template_value)
        await page.fill("#cwTemplateDate", "2027-01-01")
        await page.select_option("#cwAccessScope", "single_company")
        await page.check("#cwConfirm")
        await page.click('#companyWizard [data-wiz="activate"]')
    resp = await resp_info.value
    result["create_status"] = resp.status
    body = await resp.json()
    result["activation_writes"] = [w["url"] for w in result["writes"]]
    result["created"] = {
        "id": body.get("id"),
        "name_ar": body.get("name_ar"),
        "activity": body.get("activity"),
        "capital_amount": body.get("capital_amount"),
        "fiscal_year_start_month": body.get("fiscal_year_start_month"),
        "template_effective_from": body.get("template_effective_from"),
        "access_scope": body.get("access_scope"),
        "status": body.get("status"),
    }

    await page.wait_for_timeout(1200)
    result["company_rows_contain_new"] = await page.evaluate(
        f"""() => document.body.innerText.includes({body.get('name_ar')!r})"""
    )
    await page.screenshot(path=str(SHOTS / "company-wizard-after-activate.png"))

    await ctx.close()
    return result


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:12000")
    args = ap.parse_args()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            executable_path="/usr/bin/chromium", args=["--no-sandbox"]
        )
        try:
            data = await _run(browser, args.base)
        finally:
            await browser.close()
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
