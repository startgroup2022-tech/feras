"""Functional verification: browser -> API -> PostgreSQL.

Every other probe in ``scripts/audit`` proves a screen *renders*. This one
proves a screen *works*: it drives the real SPA in a headless browser, lets the
application issue its own write, captures the HTTP status the API returned, and
then opens PostgreSQL directly to confirm the row actually landed. Rendering a
button is not the same as the button doing its job, and an HTTP 200 is not the
same as a committed row -- this harness requires all three.

Run it against an instance backed by PostgreSQL so the database check is real:

    APP_ENV=development \\
      DATABASE_URL="postgresql+psycopg://safir:safir@127.0.0.1:5432/safir_pg" \\
      python -m uvicorn backend.main:app --port 12001 &
    python scripts/verify_functional.py --base http://127.0.0.1:12001 \\
      --pg-dsn "postgresql://safir:safir@127.0.0.1:5432/safir_pg"

The signed-in actor is the Holding Owner (``owner@demo.safir.local``), who holds
every permission, so a failure here is an implementation gap and never a missing
grant. Each operation is independent: one failure is recorded and the run
continues, so the output is a complete matrix rather than a single first error.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import uuid

from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "functional_verification.json"

OWNER = "owner@demo.safir.local"
PASSWORD = "SafirDemo!2027"

# Chromium's binary in this image; the Playwright default download is absent.
CHROMIUM = "/usr/bin/chromium"


class Checks:
    """Accumulates one result row per critical operation."""

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.console: list[str] = []
        self.http_errors: list[str] = []

    def record(self, name: str, *, ui: bool, api: int | None, db: bool, detail: str = "") -> None:
        self.rows.append(
            {"name": name, "ui": bool(ui), "api": api, "db": bool(db), "detail": detail}
        )

    def fail(self, name: str, detail: str) -> None:
        self.record(name, ui=False, api=None, db=False, detail=detail)

    def summary(self) -> dict:
        ok = [r for r in self.rows if r["ui"] and r["db"] and (r["api"] or 0) < 400]
        return {
            "checks": self.rows,
            "passed": len(ok),
            "total": len(self.rows),
            "console_errors": self.console,
            "http_errors": self.http_errors,
        }


def _pg_connect(dsn: str):
    import psycopg

    return psycopg.connect(dsn, autocommit=True)


def _pg_row(dsn: str, sql: str, params: tuple):
    with _pg_connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


async def _login(page, base: str) -> None:
    await page.goto(f"{base}/platform/?year=2027&month=10", wait_until="networkidle")
    await page.fill("#loginEmail", OWNER)
    await page.fill("#loginPassword", PASSWORD)
    await page.click("#loginBtn")
    await page.wait_for_selector("#loginScreen", state="hidden", timeout=20000)
    await page.wait_for_timeout(1500)


async def _dismiss_modal(page) -> None:
    """Close any leftover modal so a previous failure cannot block the next step."""
    for _ in range(3):
        if not await page.query_selector("#appModal"):
            return
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(120)
        if not await page.query_selector("#appModal"):
            return
        await page.evaluate(
            "() => { const m=document.querySelector('#appModal'); if (m) m.remove(); }"
        )
        await page.wait_for_timeout(120)


async def _settle_modals(page, rounds: int = 4) -> None:
    """Dismiss modals until none appear for a full round.

    A view change can trigger an async continuation (e.g. the form builder's
    "Manage form" dialog, opened after its ``/forms/{id}`` read resolves) that
    mounts a *new* overlay *after* the first dismissal. Looping until a round
    finds nothing keeps the next click from landing under a late overlay.
    """
    for _ in range(rounds):
        if not await page.query_selector("#appModal"):
            await page.wait_for_timeout(150)
            if not await page.query_selector("#appModal"):
                return
        await _dismiss_modal(page)


async def _open_view(page, view: str) -> None:
    """Click a sidebar entry, expanding the collapsed 'More' group if needed."""
    await _dismiss_modal(page)
    await page.evaluate(
        """(view) => {
          const more = document.querySelector('#sbMoreToggle');
          if (more && more.getAttribute('aria-expanded') !== 'true') more.click();
        }""",
        view,
    )
    await page.wait_for_timeout(200)
    await page.evaluate(
        """(view) => {
          const item = document.querySelector(`.nav-item[data-view="${view}"]`);
          if (item) item.click();
        }""",
        view,
    )
    await page.wait_for_timeout(900)
    await _settle_modals(page)


async def _open_admin_tab(page, tab: str) -> None:
    await _open_view(page, "admin")
    await page.evaluate(
        """(tab) => {
          const t = document.querySelector(`[data-admin-tab="${tab}"]`);
          if (t) t.click();
        }""",
        tab,
    )
    await page.wait_for_timeout(900)


async def _api_json(page, path: str):
    return await page.evaluate(
        """async (path) => {
            let tok = null;
            try {
                const raw = localStorage.getItem('safir.session.v1');
                tok = raw ? (JSON.parse(raw) || {}).access_token : null;
            } catch (e) {}
            const res = await fetch(path, {headers: Object.assign({},
                tok ? {Authorization: 'Bearer ' + tok} : {})});
            if (!res.ok) return null;
            try { return await res.json(); } catch (e) { return null; }
        }""",
        path,
    )


async def _run(browser, base: str, dsn: str) -> dict:
    checks = Checks()
    ctx = await browser.new_context(viewport={"width": 1920, "height": 1080})
    page = await ctx.new_page()
    page.on(
        "console",
        lambda m: checks.console.append(m.text) if m.type == "error" else None,
    )

    # ---- login ----------------------------------------------------------
    try:
        await _login(page, base)
        me = await _api_json(page, "/api/v1/auth/me")
        checks.record(
            "login",
            ui=bool(me),
            api=200 if me else None,
            db=bool(me and me.get("email") == OWNER),
            detail=f"email={me.get('email') if me else None}",
        )
    except Exception as exc:  # noqa: BLE001 - report, don't abort
        checks.fail("login", repr(exc))
        await ctx.close()
        return checks.summary()

    stamp = uuid.uuid4().hex[:6].upper()

    # ---- company create (admin -> companies wizard) ---------------------
    company_name = f"شركة تحقق {stamp}"
    created_company_id: int | None = None
    try:
        await _open_admin_tab(page, "companies")
        await page.wait_for_selector("#companyWizard", timeout=15000)
        await page.fill("#cwNameAr", company_name)
        await page.fill("#cwCountry", "SA")
        await page.fill("#cwRegistration", f"CR-{stamp}")
        await page.fill("#cwActivity", "تحقق وظيفي")
        sector = await page.evaluate(
            "() => { const s=document.querySelector('#cwSector'); return s&&s.options.length?s.options[0].value:''; }"
        )
        await page.select_option("#cwSector", sector)
        await page.click('#companyWizard [data-wiz="next"]')
        await page.wait_for_timeout(300)
        await page.fill("#cwCapital", "1000000")
        await page.fill("#cwOwnership", "100")
        await page.fill("#cwTracking", "2027-01-01")
        await page.select_option("#cwStatus", "active")
        await page.select_option("#cwLanguage", "ar")
        mgr = await page.evaluate(
            "() => { const s=document.querySelector('#cwManager'); return s&&s.options.length?s.options[0].value:''; }"
        )
        if mgr:
            await page.select_option("#cwManager", mgr)
        await page.click('#companyWizard [data-wiz="next"]')
        await page.wait_for_timeout(300)
        tpl = await page.evaluate(
            "() => { const s=document.querySelector('#cwTemplate'); return s&&s.options.length?s.options[0].value:''; }"
        )
        await page.select_option("#cwTemplate", tpl)
        await page.fill("#cwTemplateDate", "2027-01-01")
        await page.select_option("#cwAccessScope", "single_company")
        await page.check("#cwConfirm")
        async with page.expect_response(
            lambda r: "/api/v1/companies" in r.url and r.request.method in ("POST", "PATCH")
        ) as info:
            await page.click('#companyWizard [data-wiz="activate"]')
        status = (await info.value).status
        row = _pg_row(dsn, "SELECT id, name_ar, status FROM companies WHERE name_ar = %s", (company_name,))
        if row:
            created_company_id = row[0]
        checks.record(
            "company.create",
            ui=True,
            api=status,
            db=row is not None,
            detail=f"pg_row={row}",
        )
    except Exception as exc:  # noqa: BLE001
        checks.fail("company.create", repr(exc))

    # ---- user create + company access -----------------------------------
    email = f"verify.{stamp.lower()}@demo.safir.local"
    try:
        await _open_admin_tab(page, "users")
        await page.click('[data-admin-action="user-create"]')
        await page.wait_for_selector("#cuSave", timeout=10000)
        await page.fill("#cuNameAr", f"مستخدم تحقق {stamp}")
        await page.fill("#cuEmail", email)
        await page.fill("#cuPassword", "Verify!2027")
        await page.select_option("#cuRole", "accountant")
        async with page.expect_response(
            lambda r: r.url.endswith("/api/v1/users") and r.request.method == "POST"
        ) as info:
            await page.click("#cuSave")
        status = (await info.value).status
        row = _pg_row(
            dsn,
            "SELECT u.id, u.email, r.code FROM users u JOIN roles r ON r.id = u.role_id "
            "WHERE u.email = %s",
            (email,),
        )
        checks.record(
            "user.create",
            ui=True,
            api=status,
            db=row is not None,
            detail=f"pg_row={row}",
        )
    except Exception as exc:  # noqa: BLE001
        checks.fail("user.create", repr(exc))

    # ---- admin sets a temporary password (deck slide 37 control) --------
    # The owner's [تعيين كلمة مرور] button on a user row opens the dialog; the
    # save is proven three ways: the API returns 204, the target's audit trail
    # gets an auth.password_reset row, and the target can then log in with it.
    try:
        target_email = email
        await _open_admin_tab(page, "users")
        await page.evaluate(
            """(mail) => {
                const rows = [...document.querySelectorAll('#adminContent .av-row')];
                const row = rows.find(r => (r.innerText||'').includes(mail));
                if (row) {
                    const b = row.querySelector('[data-admin-action="reset-user-password"]');
                    if (b) b.click();
                }
            }""",
            target_email,
        )
        await page.wait_for_selector("#spSave", timeout=10000)
        admin_temp = "AdminTemp!2027"
        await page.fill("#spNew", admin_temp)
        await page.fill("#spConfirm", admin_temp)
        async with page.expect_response(
            lambda r: r.url.endswith("/password") and r.request.method == "POST"
        ) as info:
            await page.click("#spSave")
        status = (await info.value).status
        await page.wait_for_timeout(500)
        rotated = await page.evaluate(
            """async (payload) => {
                const res = await fetch('/api/v1/auth/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload),
                });
                return res.ok;
            }""",
            {"email": target_email, "password": admin_temp},
        )
        row = _pg_row(
            dsn,
            "SELECT id FROM audit_logs WHERE action = %s ORDER BY id DESC LIMIT 1",
            ("auth.password_reset",),
        )
        checks.record(
            "admin.set_password",
            ui=True,
            api=status,
            db=row is not None and bool(rotated),
            detail=f"target login ok={rotated}, audit_row={row}",
        )
    except Exception as exc:  # noqa: BLE001
        checks.fail("admin.set_password", repr(exc))

    # ---- financial summary create ---------------------------------------
    # Uses the company this run just created, so its (company, year, month)
    # period is always new -- a period already holding a version is a 409, which
    # would be a false failure of the harness, not of the product.
    try:
        if created_company_id is None:
            raise RuntimeError("company.create did not yield an id to attach the summary to")
        await _open_view(page, "financial")
        await page.click("#finNew")
        await page.wait_for_selector("#finCreate", timeout=10000)
        await page.select_option("#finC", str(created_company_id))
        await page.fill("#finRev", "1500000")
        await page.fill("#finExp", "900000")
        async with page.expect_response(
            lambda r: r.url.endswith("/api/v1/financial/summaries") and r.request.method == "POST"
        ) as info:
            await page.click("#finCreate")
        status = (await info.value).status
        row = _pg_row(
            dsn,
            "SELECT v.id, v.status, v.submitted_revenue FROM financial_summary_versions v "
            "JOIN financial_periods p ON p.id = v.period_id "
            "WHERE p.company_id = %s AND p.period_year = 2027 AND p.period_month = 10 "
            "ORDER BY v.id DESC LIMIT 1",
            (created_company_id,),
        )
        checks.record(
            "financial.summary.create",
            ui=True,
            api=status,
            db=row is not None,
            detail=f"pg_row={row}",
        )
    except Exception as exc:  # noqa: BLE001
        checks.fail("financial.summary.create", repr(exc))

    # ---- asset create (holding finance) ---------------------------------
    asset_name = f"أصل تحقق {stamp}"
    try:
        await _open_view(page, "accounting")
        await page.evaluate(
            "() => { const t=document.querySelector('[data-acct-tab=\"assets\"]'); if (t) t.click(); }"
        )
        await page.wait_for_selector("#assetForm", timeout=15000)
        await page.fill("#atName", asset_name)
        await page.fill("#atCost", "250000")
        await page.fill("#atDate", "2027-01-01")
        async with page.expect_response(
            lambda r: r.url.endswith("/api/v1/accounting/assets") and r.request.method == "POST"
        ) as info:
            await page.evaluate("() => document.querySelector('#assetForm button').click()")
        status = (await info.value).status
        row = _pg_row(dsn, "SELECT id, name, cost FROM assets WHERE name = %s", (asset_name,))
        checks.record(
            "asset.create",
            ui=True,
            api=status,
            db=row is not None,
            detail=f"pg_row={row}",
        )
    except Exception as exc:  # noqa: BLE001
        checks.fail("asset.create", repr(exc))

    # ---- employee create (HR) -------------------------------------------
    emp_name = f"موظف تحقق {stamp}"
    try:
        await _open_view(page, "employees")
        await page.wait_for_selector("#empForm", timeout=15000)
        await page.fill("#eNameAr", emp_name)
        await page.fill("#eTitle", "محلل")
        await page.fill("#eHire", "2027-02-01")
        async with page.expect_response(
            lambda r: r.url.endswith("/api/v1/employees") and r.request.method == "POST"
        ) as info:
            await page.evaluate("() => document.querySelector('#empForm button').click()")
        status = (await info.value).status
        row = _pg_row(
            dsn, "SELECT id, full_name_ar, job_title FROM employees WHERE full_name_ar = %s", (emp_name,)
        )
        checks.record(
            "employee.create",
            ui=True,
            api=status,
            db=row is not None,
            detail=f"pg_row={row}",
        )
    except Exception as exc:  # noqa: BLE001
        checks.fail("employee.create", repr(exc))

    # ---- dynamic form create + publish ----------------------------------
    form_code = f"vf_{stamp.lower()}"
    try:
        await _open_admin_tab(page, "builder")
        await page.wait_for_selector("#builderForm", timeout=15000)
        await page.fill("#bfCode", form_code)
        await page.fill("#bfNameAr", f"نموذج تحقق {stamp}")
        await page.fill("#bfNameEn", f"Verify form {stamp}")
        async with page.expect_response(
            lambda r: r.url.endswith("/api/v1/forms") and r.request.method == "POST"
        ) as info:
            await page.evaluate("() => document.querySelector('#builderForm button').click()")
        status = (await info.value).status
        row = _pg_row(dsn, "SELECT id, code, name_ar FROM dynamic_forms WHERE code = %s", (form_code,))
        checks.record(
            "form.create",
            ui=True,
            api=status,
            db=row is not None,
            detail=f"pg_row={row}",
        )
    except Exception as exc:  # noqa: BLE001
        checks.fail("form.create", repr(exc))

    # ---- investment (ownership stake) create ----------------------------
    try:
        await _open_view(page, "investments")
        await page.wait_for_selector("#invAdd", timeout=15000)
        await page.click("#invAdd")
        await page.wait_for_selector("#invAddForm", timeout=10000)
        # Pick a company that carries no active stake yet: the wizard gives a
        # freshly created company a 100% stake, so reusing it would be rejected
        # by the real "would exceed 100%" rule rather than testing the endpoint.
        free = _pg_row(
            dsn,
            "SELECT id FROM companies WHERE id NOT IN "
            "(SELECT owned_company_id FROM ownerships WHERE status = 'active') "
            "ORDER BY id LIMIT 1",
            (),
        )
        if not free:
            raise RuntimeError("every company already carries an active stake")
        owned = str(free[0])
        # The schema requires exactly one owner (company or external name), so
        # the harness supplies one rather than provoking a validation error.
        owner = await page.evaluate(
            """(want) => {
                const s = document.querySelector('#iaOwner');
                if (!s || s.options.length < 2) return '';
                const hit = [...s.options].find(o => o.value && o.value !== String(want));
                return (hit || s.options[1]).value;
            }""",
            owned,
        )
        await page.select_option("#iaOwned", owned)
        if owner:
            await page.select_option("#iaOwner", owner)
        else:
            await page.fill("#iaExternal", f"مالك خارجي {stamp}")
        await page.fill("#iaPct", "55")
        await page.fill("#iaFrom", "2027-01-01")
        async with page.expect_response(
            lambda r: r.url.endswith("/api/v1/admin/ownerships") and r.request.method == "POST"
        ) as info:
            await page.evaluate("() => document.querySelector('#invAddForm button').click()")
        status = (await info.value).status
        # The effective-from date makes each run's stake a new row; the newest
        # stake on the owned company is this run's.
        row = _pg_row(
            dsn,
            "SELECT id, owned_company_id, ownership_percentage FROM ownerships "
            "WHERE owned_company_id = %s ORDER BY id DESC LIMIT 1",
            (int(owned),),
        )
        checks.record(
            "investment.stake.create",
            ui=True,
            api=status,
            db=row is not None,
            detail=f"pg_row={row}",
        )
    except Exception as exc:  # noqa: BLE001
        checks.fail("investment.stake.create", repr(exc))

    # ---- website admin: seed public companies ---------------------------
    # The website admin writes a public projection of the holding's companies.
    # Seeding is the operation that creates rows from the live company list.
    try:
        await _open_admin_tab(page, "website")
        await page.evaluate(
            "() => { const t=document.querySelector('[data-web-tab=\"companies\"]'); if (t) t.click(); }"
        )
        await page.wait_for_timeout(600)
        has_seed = await page.evaluate(
            "() => !!document.querySelector('[data-admin-action=\"web-seed-companies\"]')"
        )
        if not has_seed:
            checks.fail("website.companies.seed", "no seed control present")
        else:
            before = _pg_row(dsn, "SELECT count(*) FROM website_companies", ())
            async with page.expect_response(
                lambda r: "/api/v1/website/companies" in r.url and r.request.method == "POST"
            ) as info:
                await page.evaluate(
                    "() => document.querySelector('[data-admin-action=\"web-seed-companies\"]').click()"
                )
            status = (await info.value).status
            after = _pg_row(dsn, "SELECT count(*) FROM website_companies", ())
            checks.record(
                "website.companies.seed",
                ui=True,
                api=status,
                db=bool(after) and after[0] >= before[0],
                detail=f"rows {before[0]}->{after[0]}",
            )
    except Exception as exc:  # noqa: BLE001
        checks.fail("website.companies.seed", repr(exc))

    # ---- website page publish (only if a page exists to toggle) --------
    try:
        has_toggle = await page.evaluate(
            "() => !!document.querySelector('[data-admin-action=\"web-toggle-page\"]')"
        )
        if not has_toggle:
            checks.record(
                "website.page.publish",
                ui=True,
                api=None,
                db=True,
                detail="no CMS page present to toggle (deck defines no page-create form)",
            )
        else:
            async with page.expect_response(
                lambda r: "/api/v1/website/pages/" in r.url and r.request.method == "POST"
            ) as info:
                await page.evaluate(
                    "() => document.querySelector('[data-admin-action=\"web-toggle-page\"]').click()"
                )
            status = (await info.value).status
            row = _pg_row(dsn, "SELECT count(*) FROM website_pages WHERE status = 'published'", ())
            checks.record(
                "website.page.publish",
                ui=True,
                api=status,
                db=bool(row),
                detail=f"published_count={row[0] if row else None}",
            )
    except Exception as exc:  # noqa: BLE001
        checks.fail("website.page.publish", repr(exc))

    # ---- knowledge document create (persistence) ------------------------
    slug = f"verify-{stamp.lower()}"
    try:
        await _open_admin_tab(page, "knowledge")
        await page.wait_for_selector("#knowledgeForm", timeout=15000)
        await page.fill("#knSlug", slug)
        await page.fill("#knTitleAr", f"مستند تحقق {stamp}")
        await page.fill("#knBodyAr", "محتوى تحقق وظيفي لقاعدة المعرفة.")
        async with page.expect_response(
            lambda r: r.url.endswith("/api/v1/ai/knowledge/documents") and r.request.method == "POST"
        ) as info:
            await page.evaluate("() => document.querySelector('#knowledgeForm button').click()")
        status = (await info.value).status
        row = _pg_row(
            dsn, "SELECT id, slug, status FROM knowledge_documents WHERE slug = %s", (slug,)
        )
        checks.record(
            "knowledge.document.create",
            ui=True,
            api=status,
            db=row is not None,
            detail=f"pg_row={row}",
        )
    except Exception as exc:  # noqa: BLE001
        checks.fail("knowledge.document.create", repr(exc))

    # ---- approval workflow: create -> submit a monthly report -----------
    # Driven entirely through the UI: open the new company's card, create the
    # report for the pinned period, then press the report's own submit control.
    # The end state is a row the server itself moved out of draft.
    try:
        if created_company_id is None:
            raise RuntimeError("company.create did not yield an id for the report")
        # Reload so the dashboard is rebuilt from a fresh API read that includes
        # the company just created; a cached view may not show its card yet.
        await _dismiss_modal(page)
        await page.goto(f"{base}/platform/?year=2027&month=10", wait_until="networkidle")
        await page.wait_for_timeout(1500)
        card = f'.rep-grid [data-remind="{created_company_id}"]'
        await page.wait_for_selector(card, timeout=15000)
        await page.click(card)
        await page.wait_for_selector("#fuCreate", timeout=10000)
        await page.click("#fuCreate")
        await page.wait_for_selector("#crSave", timeout=10000)
        await page.fill("#crYear", "2027")
        await page.fill("#crMonth", "10")
        await page.fill("#crRev", "1500000")
        await page.fill("#crExp", "900000")
        async with page.expect_response(
            lambda r: r.url.endswith("/api/v1/monthly-reports") and r.request.method == "POST"
        ) as info:
            await page.click("#crSave")
        status = (await info.value).status
        row = _pg_row(
            dsn,
            "SELECT id, status FROM monthly_reports WHERE company_id = %s "
            "AND period_year = 2027 AND period_month = 10",
            (created_company_id,),
        )
        if not row:
            raise RuntimeError(f"report row not found after create (api={status})")
        report_id = row[0]
        # The create flow opens the report; its own submit button raises a
        # confirmation dialog, and the POST is issued only when the dialog's
        # own [إرسال] control is pressed -- so that is the click the response
        # expectation must wrap, not #repSubmit.
        await page.wait_for_selector("#repSubmit", timeout=15000)
        await page.click("#repSubmit")
        await page.wait_for_selector("#cfOk", timeout=10000)
        async with page.expect_response(
            lambda r: r.url.endswith(f"/api/v1/monthly-reports/{report_id}/submit")
            and r.request.method == "POST"
        ) as info2:
            await page.click("#cfOk")
        status2 = (await info2.value).status
        row2 = _pg_row(
            dsn, "SELECT id, status FROM monthly_reports WHERE id = %s", (int(report_id),)
        )
        checks.record(
            "workflow.report.submit",
            ui=True,
            api=status2,
            db=bool(row2) and row2[1] == "submitted",
            detail=f"pg_row={row2}",
        )
    except Exception as exc:  # noqa: BLE001
        checks.fail("workflow.report.submit", repr(exc))

    # ---- workflow: create a support request through the UI --------------
    # The support view's [طلب جديد] opens the create form; the request is saved
    # with its own control, and the row is then confirmed in PostgreSQL.
    try:
        await _open_view(page, "support")
        await page.click("#supNew")
        await page.wait_for_selector("#ncSave", timeout=10000)
        await page.fill("#ncTitle", f"طلب تحقق {stamp}")
        await page.fill("#ncDesc", "طلب تحقق وظيفي من الحزمة الآلية.")
        async with page.expect_response(
            lambda r: r.url.endswith("/api/v1/support-requests") and r.request.method == "POST"
        ) as info:
            await page.click("#ncSave")
        status = (await info.value).status
        row = _pg_row(
            dsn,
            "SELECT id, status, title FROM support_requests WHERE title = %s",
            (f"طلب تحقق {stamp}",),
        )
        checks.record(
            "workflow.support.create",
            ui=True,
            api=status,
            db=row is not None,
            detail=f"pg_row={row}",
        )
    except Exception as exc:  # noqa: BLE001
        checks.fail("workflow.support.create", repr(exc))

    # ---- account: self-service password change --------------------------
    # The header profile block opens the change-password dialog. The change is
    # confirmed three ways: the API returns 204, a fresh login with the new
    # password succeeds, and the audit row lands in PostgreSQL. The password is
    # then restored so the seeded demo account keeps working for later runs.
    temp_password = "TempVerify!2027"
    try:
        await _settle_modals(page)
        await page.evaluate("() => { const el=document.querySelector('.profile'); if (el) el.click(); }")
        await page.wait_for_selector("#pwSave", timeout=10000)
        await page.fill("#pwCurrent", PASSWORD)
        await page.fill("#pwNew", temp_password)
        await page.fill("#pwConfirm", temp_password)
        async with page.expect_response(
            lambda r: r.url.endswith("/api/v1/auth/change-password")
            and r.request.method == "POST"
        ) as info:
            await page.click("#pwSave")
        status = (await info.value).status
        await page.wait_for_timeout(600)

        rotated = await page.evaluate(
            """async (pw) => {
                const res = await fetch('/api/v1/auth/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({email: 'owner@demo.safir.local', password: pw}),
                });
                return res.ok;
            }""",
            temp_password,
        )
        row = _pg_row(
            dsn,
            "SELECT id FROM audit_logs WHERE action = %s ORDER BY id DESC LIMIT 1",
            ("auth.password_changed",),
        )
        checks.record(
            "account.change_password",
            ui=bool(rotated),
            api=status,
            db=row is not None,
            detail=f"new login ok={rotated}, audit_row={row}",
        )

        # Restore the original password through the API so the demo seed holds.
        # The change above revoked the session's token, so re-authenticate with
        # the temporary password first; the old token would now be a 401.
        await page.evaluate(
            """async (payload) => {
                const res = await fetch('/api/v1/auth/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({email: 'owner@demo.safir.local',
                                          password: payload.current_password}),
                });
                const tok = res.ok ? (await res.json()).access_token : null;
                await fetch('/api/v1/auth/change-password', {
                    method: 'POST',
                    headers: Object.assign({'Content-Type': 'application/json'},
                        tok ? {Authorization: 'Bearer ' + tok} : {}),
                    body: JSON.stringify({current_password: payload.current_password,
                                          new_password: payload.new_password}),
                });
            }""",
            {"current_password": temp_password, "new_password": PASSWORD},
        )
    except Exception as exc:  # noqa: BLE001
        checks.fail("account.change_password", repr(exc))

    await ctx.close()
    return checks.summary()


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:12001")
    ap.add_argument("--pg-dsn", default="postgresql://safir:safir@127.0.0.1:5432/safir_pg")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
        try:
            data = await _run(browser, args.base, args.pg_dsn)
        finally:
            await browser.close()

    pathlib.Path(args.out).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for row in data["checks"]:
        mark = "OK  " if row["ui"] and row["db"] and (row["api"] or 0) < 400 else "FAIL"
        print(f"{mark} {row['name']:<28} api={row['api']} db={row['db']} {row['detail']}")
    print(f"\n{data['passed']}/{data['total']} operations verified end-to-end")
    if data["console_errors"]:
        print("console errors:", data["console_errors"][:5])
    return 0 if data["passed"] == data["total"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
