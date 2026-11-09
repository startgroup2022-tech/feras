"""Public website submission journeys: browser -> API -> PostgreSQL.

The internal-platform journeys are covered by ``verify_functional.py`` and
``verify_journeys.py``. This harness covers the *other* half of the brief: the
five approved public submission forms and the administrative processing that
follows them.

Every submission is driven through the real rendered control a visitor would
use (``fill``/``select_option``/``check`` on the field ids the renderer emits),
then the resulting row is read back from PostgreSQL to prove the write landed.
A form that renders but does nothing therefore fails here.

    APP_ENV=development \\
      DATABASE_URL="postgresql+psycopg://safir:safir@127.0.0.1:5432/safir" \\
      python -m uvicorn backend.main:app --port 12000 &
    python scripts/verify_public_forms.py --base http://127.0.0.1:12000 \\
      --pg-dsn "postgresql://safir:safir@127.0.0.1:5432/safir"

The five forms (plus the multi-step business listing) are:

1. group-service   (home / ar home)
2. company-formation (a market/service page)
3. feasibility     (a market/service page)
4. investment      (a market/service page)
5. careers         (multipart, carries a CV)
6. business-listing (six-step wizard, multipart)

Administrative processing is verified afterwards: the owner opens the Leads
view, opens a freshly submitted lead and changes its status through the UI, and
the new status is read back from PostgreSQL.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import pathlib
import sys
import uuid

from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "public_forms_verification.json"

OWNER = "owner@demo.safir.local"
PASSWORD = "SafirDemo!2027"
CHROMIUM = "/usr/bin/chromium"


def _pg_connect(dsn: str):
    import psycopg

    return psycopg.connect(dsn)


def _pg_row(dsn: str, sql: str, params: tuple):
    with _pg_connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()


class Checks:
    def __init__(self) -> None:
        self.results: list[dict] = []

    def record(self, name: str, *, ok: bool, detail: str = "") -> None:
        self.results.append({"name": name, "ok": bool(ok), "detail": detail})

    def summary(self) -> dict:
        passed = sum(1 for r in self.results if r["ok"])
        return {
            "results": self.results,
            "passed": passed,
            "failed": len(self.results) - passed,
        }


async def _submit_and_read(page, form_selector: str, reference_prefix: str, dsn: str, checks: Checks, name: str):
    """Click submit on ``form_selector`` and read the reference the UI shows."""
    form = await page.query_selector(form_selector)
    if form is None:
        checks.record(name, ok=False, detail=f"form {form_selector} not rendered")
        return None
    async with page.expect_response(
        lambda r: "/api/v1/public/leads/" in r.url and r.request.method == "POST"
    ) as info:
        await page.click(f"{form_selector} [data-submit]")
    response = await info.value
    status = response.status
    try:
        body = await response.json()
    except Exception:  # noqa: BLE001
        body = {}
    reference = (body or {}).get("reference")
    row = None
    if reference:
        row = _pg_row(
            dsn,
            "SELECT reference, service_type, status FROM website_leads WHERE reference = %s",
            (reference,),
        )
    checks.record(
        name,
        ok=status == 201 and bool(row) and str(row[0]).startswith(reference_prefix),
        detail=f"http={status} ref={reference} pg={row}",
    )
    return reference


async def _run(browser, base: str, dsn: str) -> dict:
    checks = Checks()
    ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
    page = await ctx.new_page()
    stamp = uuid.uuid4().hex[:6]
    mail = f"visitor.{stamp}@example.com"

    # -- 1. group-service (home page) -------------------------------------
    try:
        await page.goto(f"{base}/", wait_until="networkidle")
        await page.fill("#f-full_name", f"زائر {stamp}")
        await page.fill("#f-phone", "+97312345678")
        await page.fill("#f-email", mail)
        await page.select_option("#f-service", "formation")
        await page.select_option("#f-country", "BH")
        await page.fill("#f-message", "طلب من نموذج خدمات المجموعة")
        await page.check("#f-consent")
        await _submit_and_read(
            page, 'form[data-form="group-service"]', "SAF-GS", dsn, checks, "public.group-service"
        )
    except Exception as exc:  # noqa: BLE001
        checks.record("public.group-service", ok=False, detail=repr(exc))

    # -- 2. company-formation (Bahrain market page) -----------------------
    try:
        await page.goto(f"{base}/bahrain/company-formation", wait_until="networkidle")
        await page.fill("#f-full_name", f"زائر {stamp}")
        await page.fill("#f-nationality", "بحريني")
        await page.fill("#f-desired_activity", "تجارة عامة")
        await page.fill("#f-email", f"cf.{stamp}@example.com")
        await page.fill("#f-phone", "+97311112222")
        await page.fill("#f-number_of_partners", "2")
        await page.select_option("#f-investor_type", "individual")
        await page.select_option("#f-needs_office", "yes")
        await page.check("#f-consent")
        await _submit_and_read(
            page, 'form[data-form="company-formation"]', "SAF-CF", dsn, checks, "public.company-formation"
        )
    except Exception as exc:  # noqa: BLE001
        checks.record("public.company-formation", ok=False, detail=repr(exc))

    # -- 3. feasibility (Saudi market page) -------------------------------
    try:
        await page.goto(f"{base}/saudi/feasibility-study", wait_until="networkidle")
        await page.fill("#f-full_name", f"زائر {stamp}")
        await page.fill("#f-email", f"fs.{stamp}@example.com")
        await page.fill("#f-phone", "+966500000000")
        await page.fill("#f-project_idea", "مشروع تجريبي لدراسة الجدوى")
        await page.fill("#f-sector", "التقنية")
        await page.select_option("#f-project_stage", "new")
        await page.select_option("#f-study_type", "feasibility")
        await page.fill("#f-approximate_capital", "500000")
        await page.fill("#f-target_city", "الرياض")
        await page.check("#f-consent")
        await _submit_and_read(
            page, 'form[data-form="feasibility"]', "SAF-FS", dsn, checks, "public.feasibility"
        )
    except Exception as exc:  # noqa: BLE001
        checks.record("public.feasibility", ok=False, detail=repr(exc))

    # -- 4. investment (market page) --------------------------------------
    try:
        await page.goto(f"{base}/bahrain/investment", wait_until="networkidle")
        await page.fill("#f-full_name", f"زائر {stamp}")
        await page.fill("#f-email", f"inv.{stamp}@example.com")
        await page.fill("#f-phone", "+97333334444")
        await page.fill("#f-company_name", "شركة الاستثمار")
        await page.fill("#f-investor_profile", "مستثمر فردي")
        await page.fill("#f-message", "اهتمام بالاستثمار في السوق البحريني")
        await page.check("#f-consent")
        await _submit_and_read(
            page, 'form[data-form="investment"]', "SAF-IN", dsn, checks, "public.investment"
        )
    except Exception as exc:  # noqa: BLE001
        checks.record("public.investment", ok=False, detail=repr(exc))

    # -- 5. careers (multipart CV) ----------------------------------------
    try:
        await page.goto(f"{base}/careers", wait_until="networkidle")
        await page.fill("#f-full_name", f"مرشح {stamp}")
        await page.fill("#f-phone", "+97355556666")
        await page.fill("#f-email", f"cv.{stamp}@example.com")
        await page.select_option("#f-residence_country", "BH")
        await page.fill("#f-city", "المنامة")
        await page.fill("#f-job_title", "محلل مالي")
        await page.fill("#f-years_experience", "5")
        await page.fill("#f-message", "أرغب بالانضمام")
        await page.set_input_files(
            "#f-cv", files=[{"name": "cv.pdf", "mimeType": "application/pdf", "buffer": b"%PDF-1.4 test cv"}]
        )
        await page.check("#f-consent")
        await _submit_and_read(
            page, 'form[data-form="careers"]', "SAF-CV", dsn, checks, "public.careers"
        )
    except Exception as exc:  # noqa: BLE001
        checks.record("public.careers", ok=False, detail=repr(exc))

    # -- 6. business-listing (six-step wizard, multipart) -----------------
    try:
        await page.goto(f"{base}/list-your-business", wait_until="networkidle")
        wiz = 'form[data-form="business-listing"]'
        # step 1 country
        await page.check(f'{wiz} input[name="market"][value="bahrain"]')
        await page.click(f"{wiz} [data-next]")
        await page.wait_for_timeout(200)
        # step 2 capacity
        await page.check(f'{wiz} input[name="applicant_capacity"][value="owner"]')
        await page.click(f"{wiz} [data-next]")
        await page.wait_for_timeout(200)
        # step 3 opportunity type
        await page.check(f'{wiz} input[name="opportunity_type"][value="full_sale"]')
        await page.click(f"{wiz} [data-next]")
        await page.wait_for_timeout(200)
        # step 4 business details
        await page.fill("#f-full_name", f"بائع {stamp}")
        await page.fill("#f-company_name", "شركة معروضة")
        await page.fill("#f-sector", "تجارة")
        await page.fill("#f-business_age_years", "7")
        await page.fill("#f-email", f"bl.{stamp}@example.com")
        await page.fill("#f-phone", "+97377778888")
        await page.fill("#f-description", "شركة قائمة للبيع")
        await page.click(f"{wiz} [data-next]")
        await page.wait_for_timeout(200)
        # step 5 desired outcome
        await page.fill("#f-value_min", "100000")
        await page.fill("#f-value_max", "500000")
        await page.fill("#f-desired_outcome", "بيع كامل")
        await page.click(f"{wiz} [data-next]")
        await page.wait_for_timeout(200)
        # step 6 review + consent + submit
        await page.check("#f-consent")
        await _submit_and_read(page, wiz, "SAF-BL", dsn, checks, "public.business-listing")
    except Exception as exc:  # noqa: BLE001
        checks.record("public.business-listing", ok=False, detail=repr(exc))

    # -- 7. administrative processing: owner changes a lead status --------
    try:
        await page.goto(f"{base}/platform/?year=2027&month=10", wait_until="networkidle")
        await page.fill("#loginEmail", OWNER)
        await page.fill("#loginPassword", PASSWORD)
        await page.click("#loginBtn")
        await page.wait_for_selector("#loginScreen", state="hidden", timeout=20000)
        await page.wait_for_timeout(1500)
        await page.click('.nav-item[data-view="leads"]')
        await page.wait_for_timeout(2000)
        # Open the first lead row and change its status.
        row = await page.query_selector("[data-lead]")
        if row is None:
            checks.record("admin.lead.process", ok=False, detail="no lead rows rendered")
        else:
            lead_id = await row.get_attribute("data-lead")
            await row.click()
            await page.wait_for_selector("#leadStatusSel", timeout=10000)
            before = _pg_row(dsn, "SELECT status FROM website_leads WHERE id = %s", (int(lead_id),))
            await page.select_option("#leadStatusSel", "in_progress")
            async with page.expect_response(
                lambda r: f"/api/v1/leads/{lead_id}" in r.url and r.request.method == "PATCH"
            ) as info:
                await page.click("#leadSave")
            status = (await info.value).status
            await page.wait_for_timeout(1000)
            after = _pg_row(dsn, "SELECT status FROM website_leads WHERE id = %s", (int(lead_id),))
            checks.record(
                "admin.lead.process",
                ok=status == 200 and bool(after) and after[0] == "in_progress",
                detail=f"lead={lead_id} http={status} before={before} after={after}",
            )
    except Exception as exc:  # noqa: BLE001
        checks.record("admin.lead.process", ok=False, detail=repr(exc))

    await ctx.close()
    return checks.summary()


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:12000")
    parser.add_argument("--pg-dsn", required=True)
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
        data = await _run(browser, args.base, args.pg_dsn)
        await browser.close()

    pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    for r in data["results"]:
        mark = "OK  " if r["ok"] else "FAIL"
        print(f"{mark} {r['name']:<28} {r['detail']}")
    print(f"\n{data['passed']}/{len(data['results'])} public-form journeys verified")
    return 0 if data["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
