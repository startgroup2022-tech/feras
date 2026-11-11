"""Phase 4 — the twelve required browser journeys, on PostgreSQL.

Each journey drives the real Chromium UI against a live FastAPI instance and,
for every write, asserts the resulting row in PostgreSQL. A journey that only
"looked" like it worked does not pass: the DB assertion is the verdict.

Run against a running server:

    BASE_URL=http://127.0.0.1:12002 \\
    DATABASE_URL=postgresql+psycopg://safir:safir@127.0.0.1:5433/safir_dev \\
    python -m scripts.verify_e2e_journeys

The twelve journeys:

 1. Owner logs in and creates a subsidiary (company setup wizard).
 2. Owner creates a user and assigns a role.
 3. Company manager submits a monthly report.
 4. Accountant reviews the report financially.
 5. Authorized approver approves and locks the report.
 6. Administrator creates a dynamic financial form and adds a field.
 7. HR creates an employee and processes an employee movement.
 8. Authorized users create an investment (ownership stake) and an asset.
 9. Visitor submits each of the five public forms.
10. Administrator sees and processes those submissions.
11. AI retrieves authorized documents and cites sources.
12. Unauthorized users are blocked from restricted company data.

A final section verifies the Arabic RTL / English LTR switch and a mobile
viewport, which the brief requires alongside the desktop journeys.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import uuid

import psycopg
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "e2e_journeys_verification.json"

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:12002").rstrip("/")
PLATFORM = BASE + "/platform/"
CHROMIUM = os.environ.get("CHROMIUM", "/usr/bin/chromium")
PASSWORD = os.environ.get("DEMO_PASSWORD", "SafirDemo!2027")
OWNER = "owner@demo.safir.local"
MANAGER = "manager.tech@demo.safir.local"
ACCOUNTANT = "accountant@demo.safir.local"

# The harness writes rows, so it must run against a disposable database. The
# SQLAlchemy URL form (``postgresql+psycopg://``) is normalised for psycopg.
_RAW_DSN = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://safir:safir@127.0.0.1:5433/safir_dev"
)
DSN = _RAW_DSN.replace("postgresql+psycopg://", "postgresql://").replace(
    "postgresql+psycopg2://", "postgresql://"
)


class Checks:
    """Collects one verdict per journey (and the supplementary checks)."""

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.console: list[str] = []

    def record(self, name: str, ok: bool, detail: str = "") -> None:
        self.rows.append({"name": name, "ok": bool(ok), "detail": detail})
        print(f"{'PASS' if ok else 'FAIL'} | {name} | {detail}")

    def journey(self, n: int, title: str, ok: bool, detail: str = "") -> None:
        self.record(f"J{n:02d} {title}", ok, detail)


def _pg_row(sql: str, params: tuple = ()):
    with psycopg.connect(DSN, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def _pg_rows(sql: str, params: tuple = ()):
    with psycopg.connect(DSN, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


# --------------------------------------------------------------------------
# browser helpers
# --------------------------------------------------------------------------
def _login(page, email: str, year: int = 2027, month: int = 7) -> None:
    page.goto(f"{PLATFORM}?year={year}&month={month}", wait_until="domcontentloaded")
    page.wait_for_selector("#loginEmail", timeout=25000)
    page.fill("#loginEmail", email)
    page.fill("#loginPassword", PASSWORD)
    page.click("#loginBtn")
    page.wait_for_selector("body.authed", timeout=30000)
    page.wait_for_timeout(1500)


def _open_more(page) -> None:
    toggle = page.query_selector("#sbMoreToggle")
    if toggle and toggle.get_attribute("aria-expanded") != "true":
        toggle.click()
        page.wait_for_timeout(300)


def nav(page, view: str) -> bool:
    """Open a sidebar view, expanding the "Additional tools" group if needed."""
    item = page.query_selector(f'.nav-item[data-view="{view}"]')
    if item and not item.is_visible():
        _open_more(page)
    item = page.query_selector(f'.nav-item[data-view="{view}"]')
    if not item or not item.is_visible():
        return False
    item.click()
    page.wait_for_timeout(1500)
    return True


def _open_admin_tab(page, tab: str) -> bool:
    if not nav(page, "admin"):
        return False
    btn = page.query_selector(f'[data-admin-tab="{tab}"]')
    if not btn:
        return False
    btn.click()
    page.wait_for_timeout(2200)
    return True


def _confirm(page) -> None:
    page.wait_for_selector("#cfOk", timeout=12000)
    page.click("#cfOk")
    page.wait_for_timeout(900)


def _close_modal(page) -> None:
    """Dismiss any open modal so the next sidebar click is not intercepted."""
    for _ in range(4):
        if not page.query_selector("#appModal"):
            return
        x = page.query_selector("#appModal .modal-x")
        if x:
            x.click()
        else:
            page.keyboard.press("Escape")
        page.wait_for_timeout(400)


def _first_option(page, selector: str) -> str | None:
    vals = page.eval_on_selector_all(
        f"{selector} option", "els => els.map(e => e.value).filter(v => v !== '')"
    )
    return vals[0] if vals else None


def _owns_reachable(edges: dict[int, set[int]], start: int, target: int) -> bool:
    """True if ``start`` transitively owns ``target`` (so the reverse would cycle)."""
    seen: set[int] = set()
    stack = [start]
    while stack:
        node = stack.pop()
        for nxt in edges.get(node, ()):  # companies this node owns
            if nxt == target:
                return True
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return False


def _free_period(company_id: int, year: int = 2027, month: int = 7) -> tuple[int, int]:
    """A (year, month) for which the company has no report, so J3 can rerun.

    Month 7 of 2027 is the seeded "current" period and company 1 already owns a
    locked report there; walking forward keeps the journey idempotent across
    repeated runs against the same database.
    """
    for offset in range(0, 24):
        y = year + (month - 1 + offset) // 12
        m = (month - 1 + offset) % 12 + 1
        if not _pg_row(
            "SELECT 1 FROM monthly_reports WHERE company_id = %s "
            "AND period_year = %s AND period_month = %s",
            (company_id, y, m),
        ):
            return y, m
    raise RuntimeError("no free reporting period found")


def _new_context(browser, checks: Checks, *, mobile: bool = False):
    viewport = {"width": 390, "height": 844} if mobile else {"width": 1440, "height": 900}
    ctx = browser.new_context(viewport=viewport)
    page = ctx.new_page()
    page.on(
        "console",
        lambda m: checks.console.append(m.text) if m.type == "error" else None,
    )
    return ctx, page


SHOTS = ROOT / "artifacts" / "e2e_screenshots"


def _shot(page, name: str) -> None:
    """Save the browser state as evidence; a failure to capture is not fatal."""
    try:
        SHOTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=False)
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------
# journeys
# --------------------------------------------------------------------------
def j1_owner_creates_subsidiary(browser, checks: Checks, stamp: str) -> None:
    ctx, page = _new_context(browser, checks)
    name = f"شركة رحلة {stamp}"
    try:
        _login(page, OWNER)
        if not _open_admin_tab(page, "companies"):
            checks.journey(1, "owner creates subsidiary", False, "companies tab unavailable")
            return
        page.wait_for_selector("#companyWizardForm", timeout=10000)
        page.fill("#cwNameAr", name)
        page.fill("#cwCountry", "BH")
        page.fill("#cwRegistration", f"CR-{stamp}")
        page.fill("#cwActivity", "خدمات أعمال")
        page.select_option("#cwSector", _first_option(page, "#cwSector"))
        page.select_option("#cwCurrency", "BHD")
        page.click('[data-wiz="next"]')
        page.wait_for_timeout(700)
        page.fill("#cwOwnership", "100")
        page.fill("#cwCapital", "100000")
        mgr = _first_option(page, "#cwManager")
        if mgr:
            page.select_option("#cwManager", mgr)
        page.fill("#cwTracking", "2027-01-01")
        page.select_option("#cwStatus", "active")
        page.select_option("#cwLanguage", "ar")
        page.click('[data-wiz="next"]')
        page.wait_for_timeout(700)
        page.select_option("#cwTemplate", _first_option(page, "#cwTemplate"))
        page.fill("#cwTemplateDate", "2027-01-01")
        page.select_option("#cwAccessScope", "single_company")
        page.check("#cwConfirm")
        page.click('[data-wiz="activate"]')
        page.wait_for_timeout(4000)
        _shot(page, "j01_subsidiary")
        row = _pg_row(
            "SELECT id, currency, country, status FROM companies WHERE name_ar = %s",
            (name,),
        )
        checks.journey(
            1,
            "owner creates subsidiary",
            bool(row and row[1] == "BHD" and row[2] == "BH"),
            f"pg={row}",
        )
    except Exception as exc:  # noqa: BLE001
        checks.journey(1, "owner creates subsidiary", False, repr(exc))
    finally:
        ctx.close()


def j2_owner_creates_user(browser, checks: Checks, stamp: str) -> None:
    ctx, page = _new_context(browser, checks)
    email = f"e2e.user.{stamp.lower()}@demo.safir.local"
    try:
        _login(page, OWNER)
        if not _open_admin_tab(page, "users"):
            checks.journey(2, "owner creates user", False, "users tab unavailable")
            return
        btn = page.query_selector('[data-admin-action="user-create"]')
        if not btn:
            checks.journey(2, "owner creates user", False, "add-user button absent")
            return
        btn.click()
        page.wait_for_selector("#cuEmail", timeout=10000)
        page.fill("#cuNameAr", f"مستخدم رحلة {stamp}")
        page.fill("#cuEmail", email)
        page.fill("#cuPassword", "Journey!2027")
        page.select_option("#cuRole", "company_manager")
        box = page.query_selector(".cuCompany")
        if box:
            box.check()
        page.click("#cuSave")
        page.wait_for_timeout(3500)
        _shot(page, "j02_user")
        row = _pg_row(
            "SELECT u.id, r.code, u.is_active FROM users u "
            "JOIN roles r ON r.id = u.role_id WHERE u.email = %s",
            (email,),
        )
        checks.journey(
            2,
            "owner creates user",
            bool(row and row[1] == "company_manager" and row[2] is True),
            f"pg={row}",
        )
    except Exception as exc:  # noqa: BLE001
        checks.journey(2, "owner creates user", False, repr(exc))
    finally:
        ctx.close()


def j3_manager_submits_report(browser, checks: Checks, stamp: str) -> dict | None:
    """Manager creates and submits a fresh report; returns id and period."""
    ctx, page = _new_context(browser, checks)
    report_id = None
    company_id = 1
    period: dict | None = None
    try:
        year, month = _free_period(company_id)
        _login(page, MANAGER, year=year, month=month)
        page.wait_for_timeout(1500)
        remind = page.query_selector("[data-remind]")
        if not remind:
            checks.journey(3, "manager submits report", False, "no follow-up button")
            return None
        remind.click()
        page.wait_for_selector("#fuCreate", timeout=10000)
        page.click("#fuCreate")
        page.wait_for_selector("#crRev", timeout=10000)
        page.fill("#crRev", "450000")
        page.fill("#crExp", "310000")
        page.fill("#crNotes", f"تقرير رحلة {stamp}")
        page.click("#crSave")
        page.wait_for_selector("#repSubmit", timeout=15000)
        # The created report is the newest row for the manager's company and
        # period; the UI opened its detail modal, so read the id from the DB
        # rather than reaching into the page's internal state.
        row = _pg_row(
            "SELECT id FROM monthly_reports WHERE company_id = %s "
            "AND period_year = %s AND period_month = %s ORDER BY id DESC LIMIT 1",
            (company_id, year, month),
        )
        report_id = row[0] if row else None
        period = {"year": year, "month": month}
        page.click("#repSubmit")
        _confirm(page)
        page.wait_for_timeout(2500)
        _shot(page, "j03_report_submitted")
        row = _pg_row(
            "SELECT status, revenue, expenses FROM monthly_reports WHERE id = %s",
            (report_id,),
        )
        checks.journey(
            3,
            "manager submits report",
            bool(row and row[0] == "submitted"),
            f"report={report_id} period={year}-{month} pg={row}",
        )
    except Exception as exc:  # noqa: BLE001
        checks.journey(3, "manager submits report", False, repr(exc))
    finally:
        ctx.close()
    return {"id": report_id, "period": period} if report_id else None


def j4_accountant_reviews(browser, checks: Checks, report: dict | None) -> None:
    ctx, page = _new_context(browser, checks)
    try:
        if not report:
            checks.journey(4, "accountant reviews report", False, "no report from J3")
            return
        report_id = report["id"]
        year, month = report["period"]["year"], report["period"]["month"]
        _login(page, ACCOUNTANT, year=year, month=month)
        if not nav(page, "reports"):
            checks.journey(4, "accountant reviews report", False, "reports view unavailable")
            return
        row = page.query_selector(f'[data-report="{report_id}"]')
        if not row:
            checks.journey(4, "accountant reviews report", False, "report row not rendered")
            return
        row.click()
        page.wait_for_selector("#repReview", timeout=12000)
        page.click("#repReview")
        page.wait_for_selector("#frSave", timeout=12000)
        page.fill("#frNotes", f"مراجعة مالية للرحلة {report_id}")
        page.click("#frSave")
        page.wait_for_timeout(3500)
        _shot(page, "j04_financial_review")
        review = _pg_row(
            "SELECT status, is_financially_accurate FROM monthly_report_financial_reviews "
            "WHERE report_id = %s",
            (report_id,),
        )
        rep = _pg_row("SELECT status FROM monthly_reports WHERE id = %s", (report_id,))
        checks.journey(
            4,
            "accountant reviews report",
            bool(review and review[0] == "approved" and rep and rep[0] == "reviewed"),
            f"review={review} report={rep}",
        )
    except Exception as exc:  # noqa: BLE001
        checks.journey(4, "accountant reviews report", False, repr(exc))
    finally:
        ctx.close()


def j5_owner_approves_and_locks(browser, checks: Checks, report: dict | None) -> None:
    ctx, page = _new_context(browser, checks)
    try:
        if not report:
            checks.journey(5, "owner approves and locks", False, "no report from J3")
            return
        report_id = report["id"]
        year, month = report["period"]["year"], report["period"]["month"]
        _login(page, OWNER, year=year, month=month)
        if not nav(page, "reports"):
            checks.journey(5, "owner approves and locks", False, "reports view unavailable")
            return
        row = page.query_selector(f'[data-report="{report_id}"]')
        if not row:
            checks.journey(5, "owner approves and locks", False, "report row not rendered")
            return
        row.click()
        page.wait_for_selector("#repApprove", timeout=12000)
        page.click("#repApprove")
        _confirm(page)
        page.wait_for_timeout(3000)
        page.wait_for_selector("#repLock", timeout=15000)
        page.click("#repLock")
        _confirm(page)
        page.wait_for_timeout(3000)
        _shot(page, "j05_approved_locked")
        row2 = _pg_row(
            "SELECT status, approval_status FROM monthly_reports WHERE id = %s",
            (report_id,),
        )
        checks.journey(
            5,
            "owner approves and locks",
            bool(row2 and row2[0] == "locked" and row2[1] == "approved"),
            f"pg={row2}",
        )
    except Exception as exc:  # noqa: BLE001
        checks.journey(5, "owner approves and locks", False, repr(exc))
    finally:
        ctx.close()


def j6_admin_creates_form(browser, checks: Checks, stamp: str) -> None:
    ctx, page = _new_context(browser, checks)
    code = f"e2e_{stamp.lower()}"
    try:
        _login(page, OWNER)
        if not _open_admin_tab(page, "builder"):
            checks.journey(6, "admin creates dynamic form", False, "builder tab unavailable")
            return
        page.wait_for_selector("#bfCode", timeout=10000)
        page.fill("#bfCode", code)
        page.fill("#bfNameAr", f"نموذج رحلة {stamp}")
        page.fill("#bfNameEn", f"Journey form {stamp}")
        page.select_option("#bfScope", "holding")
        page.click('[data-admin-action="builder-create"]')
        page.wait_for_selector("#afAdd", timeout=12000)
        page.fill("#afKey", "journey_amount")
        page.select_option("#afType", "decimal")
        page.fill("#afLabelAr", "المبلغ المطلوب")
        page.fill("#afLabelEn", "Requested amount")
        page.select_option("#afRequired", "1")
        page.click("#afAdd")
        page.wait_for_timeout(3000)
        _shot(page, "j06_form_builder")
        form = _pg_row("SELECT id, status FROM dynamic_forms WHERE code = %s", (code,))
        field = None
        if form:
            field = _pg_row(
                "SELECT ff.id, ff.field_type FROM form_fields ff "
                "JOIN form_versions fv ON fv.id = ff.form_version_id "
                "WHERE fv.form_id = %s AND ff.key = %s",
                (form[0], "journey_amount"),
            )
        checks.journey(
            6,
            "admin creates dynamic form",
            bool(form and field and field[1] == "decimal"),
            f"form={form} field={field}",
        )
    except Exception as exc:  # noqa: BLE001
        checks.journey(6, "admin creates dynamic form", False, repr(exc))
    finally:
        ctx.close()


def j7_hr_employee_movement(browser, checks: Checks, stamp: str) -> None:
    ctx, page = _new_context(browser, checks)
    emp_name = f"موظف رحلة {stamp}"
    try:
        _login(page, OWNER)
        if not nav(page, "employees"):
            checks.journey(7, "HR employee movement", False, "employees view unavailable")
            return
        page.wait_for_selector("#empForm", timeout=12000)
        page.fill("#eNameAr", emp_name)
        page.fill("#eTitle", "محلل مالي")
        page.fill("#eHire", "2027-02-01")
        page.click('#empForm button[type="submit"]')
        page.wait_for_timeout(3500)
        emp = _pg_row("SELECT id FROM employees WHERE full_name_ar = %s", (emp_name,))
        if not emp:
            checks.journey(7, "HR employee movement", False, "employee not committed")
            return
        page.wait_for_timeout(800)
        row = page.query_selector(f'[data-emp]:has-text("{emp_name}")')
        if not row:
            checks.journey(7, "HR employee movement", False, "employee row not rendered")
            return
        row.click()
        page.wait_for_selector("#movForm", timeout=12000)
        page.select_option("#mvType", "leave")
        page.fill("#mvDate", "2027-07-15")
        page.fill("#mvDays", "5")
        page.fill("#mvReason", "إجازة سنوية")
        page.click('#movForm button[type="submit"]')
        page.wait_for_timeout(3500)
        mov = _pg_row(
            "SELECT id, status FROM employee_movements WHERE employee_id = %s "
            "ORDER BY id DESC LIMIT 1",
            (emp[0],),
        )
        if not mov:
            checks.journey(7, "HR employee movement", False, "movement not committed")
            return
        approve = page.query_selector('[data-act="mov-approve"]')
        if not approve:
            checks.journey(7, "HR employee movement", False, "approve control absent")
            return
        approve.click()
        page.wait_for_timeout(3500)
        _shot(page, "j07_movement")
        after = _pg_row("SELECT status FROM employee_movements WHERE id = %s", (mov[0],))
        checks.journey(
            7,
            "HR employee movement",
            bool(after and after[0] == "approved"),
            f"movement={mov[0]} before={mov[1]} after={after}",
        )
    except Exception as exc:  # noqa: BLE001
        checks.journey(7, "HR employee movement", False, repr(exc))
    finally:
        ctx.close()


def j8_investment_and_asset(browser, checks: Checks, stamp: str) -> None:
    ctx, page = _new_context(browser, checks)
    asset_name = f"أصل رحلة {stamp}"
    try:
        _login(page, OWNER)
        # ---- investment (ownership stake) ----
        if not nav(page, "investments"):
            checks.journey(8, "investment and asset", False, "investments view unavailable")
            return
        page.wait_for_selector("#invAdd", timeout=12000)
        page.click("#invAdd")
        page.wait_for_selector("#invAddForm", timeout=12000)
        # Pick the subsidiary from the options the page itself offers, choosing
        # one that carries no active stake so 75% never trips the "exceeds
        # 100%" rule and the (owner, company, date) key stays unique on reruns.
        owned_opts = page.eval_on_selector_all(
            "#iaOwned option", "els => els.map(e => e.value).filter(v => v)"
        )
        owner_opts = page.eval_on_selector_all(
            "#iaOwner option", "els => els.map(e => e.value).filter(v => v)"
        )
        # Ownership edges (owner -> companies it owns), so the harness never
        # proposes a stake that would close a cycle and be rejected with 409.
        edges: dict[int, set[int]] = {}
        for owner_id, owned_id in (
            _pg_rows("SELECT owner_company_id, owned_company_id FROM ownerships "
                     "WHERE status = 'active' AND owner_company_id IS NOT NULL")
        ):
            edges.setdefault(owner_id, set()).add(owned_id)
        owned = next(
            (
                o
                for o in owned_opts
                if not _pg_row(
                    "SELECT 1 FROM ownerships WHERE owned_company_id = %s "
                    "AND status = 'active' LIMIT 1",
                    (int(o),),
                )
            ),
            owned_opts[0],
        )
        owner = next(
            (
                o
                for o in owner_opts
                if o != owned
                and not _owns_reachable(edges, int(owned), int(o))
            ),
            owner_opts[0],
        )
        page.select_option("#iaOwned", owned)
        page.select_option("#iaOwner", owner)
        page.fill("#iaPct", "75")
        page.fill("#iaFrom", "2027-03-01")
        page.click('#invAddForm button[type="submit"]')
        page.wait_for_timeout(3500)
        # The create modal closes itself on success; only then open the detail.
        if page.query_selector("#appModal"):
            raise RuntimeError("ownership create modal did not close (request failed)")
        own = _pg_row(
            "SELECT id, ownership_percentage FROM ownerships "
            "WHERE owned_company_id = %s AND status = 'active' ORDER BY id DESC LIMIT 1",
            (int(owned),),
        )
        # ---- valuation on the same stake ----
        opened = page.query_selector(f'[data-invest-open="{owned}"]')
        if not opened:
            raise RuntimeError("ownership row not rendered after create")
        opened.click()
        page.wait_for_selector("#invEdit", timeout=12000)
        page.click("#invEdit")
        page.wait_for_selector("#invForm", timeout=12000)
        page.fill("#invOriginal", "500000")
        page.fill("#invBook", "480000")
        page.fill("#invBookDate", "2027-06-30")
        page.fill("#invBookSource", "ميزان مراجعة")
        page.click('#invForm button[type="submit"]')
        page.wait_for_timeout(3000)
        val = _pg_row(
            "SELECT id, original_value, book_value FROM investment_valuations "
            "WHERE owned_company_id = %s",
            (int(owned),),
        )
        # ---- asset ----
        _close_modal(page)
        if not nav(page, "accounting"):
            checks.journey(8, "investment and asset", False, "accounting view unavailable")
            return
        sec = page.query_selector('[data-acct-section-btn="financial_reports"]')
        if sec:
            sec.click()
            page.wait_for_timeout(1200)
        page.eval_on_selector('[data-acct-tab="assets"]', "el => el.click()")
        page.wait_for_selector("#assetForm", timeout=12000)
        page.fill("#atName", asset_name)
        page.fill("#atCost", "250000")
        page.fill("#atCategory", "معدات")
        page.fill("#atDate", "2027-04-01")
        page.click('#assetForm button[type="submit"]')
        page.wait_for_timeout(3500)
        _shot(page, "j08_asset")
        asset = _pg_row("SELECT id, cost FROM assets WHERE name = %s", (asset_name,))
        checks.journey(
            8,
            "investment and asset",
            bool(own and val and asset),
            f"ownership={own} valuation={val} asset={asset}",
        )
    except Exception as exc:  # noqa: BLE001
        checks.journey(8, "investment and asset", False, repr(exc))
    finally:
        ctx.close()


def _submit_public(page, form_selector: str):
    with page.expect_response(
        lambda r: "/api/v1/public/leads/" in r.url and r.request.method == "POST"
    ) as info:
        page.click(f"{form_selector} [data-submit]")
    resp = info.value
    body = {}
    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        pass
    return resp.status, (body or {}).get("reference")


def j9_public_forms(browser, checks: Checks, stamp: str) -> None:
    ctx, page = _new_context(browser, checks)
    results: dict[str, tuple[int, str | None]] = {}
    try:
        page.goto(f"{BASE}/", wait_until="domcontentloaded")
        page.fill("#f-full_name", f"زائر {stamp}")
        page.fill("#f-phone", "+97312345678")
        page.fill("#f-email", f"gs.{stamp.lower()}@example.com")
        page.select_option("#f-service", "formation")
        page.select_option("#f-country", "BH")
        page.fill("#f-message", "طلب من نموذج خدمات المجموعة")
        page.check("#f-consent")
        results["group-service"] = _submit_public(page, 'form[data-form="group-service"]')

        page.goto(f"{BASE}/bahrain/company-formation", wait_until="domcontentloaded")
        page.fill("#f-full_name", f"زائر {stamp}")
        page.fill("#f-nationality", "بحريني")
        page.fill("#f-desired_activity", "تجارة عامة")
        page.fill("#f-email", f"cf.{stamp.lower()}@example.com")
        page.fill("#f-phone", "+97311112222")
        page.fill("#f-number_of_partners", "2")
        page.select_option("#f-investor_type", "individual")
        page.select_option("#f-needs_office", "yes")
        page.check("#f-consent")
        results["company-formation"] = _submit_public(page, 'form[data-form="company-formation"]')

        page.goto(f"{BASE}/saudi/feasibility-study", wait_until="domcontentloaded")
        page.fill("#f-full_name", f"زائر {stamp}")
        page.fill("#f-email", f"fs.{stamp.lower()}@example.com")
        page.fill("#f-phone", "+966500000000")
        page.fill("#f-project_idea", "مشروع تجريبي لدراسة الجدوى")
        page.fill("#f-sector", "التقنية")
        page.select_option("#f-project_stage", "new")
        page.select_option("#f-study_type", "feasibility")
        page.fill("#f-approximate_capital", "500000")
        page.fill("#f-target_city", "الرياض")
        page.check("#f-consent")
        results["feasibility"] = _submit_public(page, 'form[data-form="feasibility"]')

        page.goto(f"{BASE}/bahrain/investment", wait_until="domcontentloaded")
        page.fill("#f-full_name", f"زائر {stamp}")
        page.fill("#f-email", f"inv.{stamp.lower()}@example.com")
        page.fill("#f-phone", "+97333334444")
        page.fill("#f-company_name", "شركة الاستثمار")
        page.fill("#f-investor_profile", "مستثمر فردي")
        page.fill("#f-message", "اهتمام بالاستثمار في السوق البحريني")
        page.check("#f-consent")
        results["investment"] = _submit_public(page, 'form[data-form="investment"]')

        page.goto(f"{BASE}/careers", wait_until="domcontentloaded")
        page.fill("#f-full_name", f"مرشح {stamp}")
        page.fill("#f-phone", "+97355556666")
        page.fill("#f-email", f"cv.{stamp.lower()}@example.com")
        page.select_option("#f-residence_country", "BH")
        page.fill("#f-city", "المنامة")
        page.fill("#f-job_title", "محلل مالي")
        page.fill("#f-years_experience", "5")
        page.fill("#f-message", "أرغب بالانضمام")
        page.set_input_files(
            "#f-cv",
            files=[{"name": "cv.pdf", "mimeType": "application/pdf",
                    "buffer": b"%PDF-1.4 journey cv"}],
        )
        page.check("#f-consent")
        results["careers"] = _submit_public(page, 'form[data-form="careers"]')
        _shot(page, "j09_public_careers")

        detail = []
        all_ok = True
        for key, (status, ref) in results.items():
            pg = _pg_row(
                "SELECT reference, status FROM website_leads WHERE reference = %s",
                (ref,),
            ) if ref else None
            ok = status == 201 and bool(pg)
            all_ok = all_ok and ok
            detail.append(f"{key}:http={status},ref={ref},pg={bool(pg)}")
        checks.journey(9, "visitor submits public forms", all_ok, " | ".join(detail))
    except Exception as exc:  # noqa: BLE001
        checks.journey(9, "visitor submits public forms", False, repr(exc))
    finally:
        ctx.close()


def j10_admin_processes_lead(browser, checks: Checks) -> None:
    ctx, page = _new_context(browser, checks)
    try:
        _login(page, OWNER)
        if not nav(page, "leads"):
            checks.journey(10, "admin processes submission", False, "leads view unavailable")
            return
        page.wait_for_timeout(1500)
        row = page.query_selector("[data-lead]")
        if not row:
            checks.journey(10, "admin processes submission", False, "no lead rows rendered")
            return
        lead_id = int(row.get_attribute("data-lead"))
        row.click()
        page.wait_for_selector("#leadStatusSel", timeout=12000)
        before = _pg_row("SELECT status FROM website_leads WHERE id = %s", (lead_id,))
        page.select_option("#leadStatusSel", "in_progress")
        page.click("#leadSave")
        page.wait_for_timeout(3000)
        _shot(page, "j10_lead")
        after = _pg_row("SELECT status FROM website_leads WHERE id = %s", (lead_id,))
        checks.journey(
            10,
            "admin processes submission",
            bool(after and after[0] == "in_progress"),
            f"lead={lead_id} before={before} after={after}",
        )
    except Exception as exc:  # noqa: BLE001
        checks.journey(10, "admin processes submission", False, repr(exc))
    finally:
        ctx.close()


def j11_ai_knowledge_citations(browser, checks: Checks, stamp: str) -> None:
    ctx, page = _new_context(browser, checks)
    slug = f"e2e-kb-{stamp.lower()}"
    title = f"سياسة المصروفات {stamp}"
    body = f"الحد الأقصى للمصروف النقدي {stamp} هو 10000 دينار بموافقة المالك."
    try:
        _login(page, OWNER)
        if not _open_admin_tab(page, "knowledge"):
            checks.journey(11, "AI knowledge citations", False, "knowledge tab unavailable")
            return
        page.wait_for_selector("#knowledgeForm", timeout=12000)
        page.fill("#knSlug", slug)
        page.fill("#knTitleAr", title)
        page.fill("#knBodyAr", body)
        page.select_option("#knSensitivity", "holding")
        page.click('#knowledgeForm button[type="submit"]')
        page.wait_for_timeout(3500)
        approve = page.query_selector('[data-admin-action="knowledge-approve"]')
        if not approve:
            checks.journey(11, "AI knowledge citations", False, "approve control absent")
            return
        approve.click()
        page.wait_for_timeout(3500)
        doc = _pg_row(
            "SELECT id, status, current_version_id FROM knowledge_documents WHERE slug = %s",
            (slug,),
        )
        chunks = _pg_row(
            "SELECT count(*) FROM knowledge_chunks kc JOIN knowledge_documents kd "
            "ON kd.id = kc.document_id WHERE kd.slug = %s",
            (slug,),
        )
        nav(page, "dashboard")
        page.wait_for_selector("#kbInput", timeout=12000)
        page.fill("#kbInput", f"الحد الأقصى للمصروف النقدي {stamp}")
        page.click("#kbSend")
        page.wait_for_timeout(5000)
        _shot(page, "j11_knowledge_answer")
        answer = page.inner_text("#kbAnswerBody") if page.query_selector("#kbAnswerBody") else ""
        cites = title in answer or slug in answer
        checks.journey(
            11,
            "AI knowledge citations",
            bool(doc and doc[1] == "approved" and doc[2] and chunks
                 and chunks[0] >= 1 and cites),
            f"doc={doc} chunks={chunks} cited={cites} answer={answer[:70]!r}",
        )
    except Exception as exc:  # noqa: BLE001
        checks.journey(11, "AI knowledge citations", False, repr(exc))
    finally:
        ctx.close()


def j12_isolation(browser, checks: Checks) -> None:
    ctx, page = _new_context(browser, checks)
    try:
        _login(page, MANAGER, month=7)
        # The manager's company is 1; company 2 is out of scope and must 404,
        # not 403, so the platform never reveals that the row exists.
        code = page.evaluate(
            "() => window.SafirApi.get('/api/v1/companies/2')"
            ".then(() => 200).catch(e => e.status)"
        )
        rep = page.evaluate(
            "() => window.SafirApi.get('/api/v1/monthly-reports/2')"
            ".then(() => 200).catch(e => e.status)"
        )
        own = page.evaluate(
            "() => window.SafirApi.get('/api/v1/companies/1')"
            ".then(() => 200).catch(e => e.status)"
        )
        inv_nav = page.query_selector('.nav-item[data-view="investments"]')
        inv_hidden = inv_nav is None or not inv_nav.is_visible()
        checks.journey(
            12,
            "unauthorized access blocked",
            bool(code == 404 and rep == 404 and own == 200 and inv_hidden),
            f"company2={code} report2={rep} ownCompany={own} investmentsHidden={inv_hidden}",
        )
    except Exception as exc:  # noqa: BLE001
        checks.journey(12, "unauthorized access blocked", False, repr(exc))
    finally:
        ctx.close()


def locale_and_viewport(browser, checks: Checks) -> None:
    """AR RTL / EN LTR switch and a mobile viewport with no horizontal overflow."""
    ctx, page = _new_context(browser, checks)
    try:
        _login(page, OWNER)
        page.locator('.lang-opt[data-lang="en"]:visible').first.click()
        page.wait_for_timeout(800)
        _shot(page, "locale_en_ltr")
        en_dir = page.evaluate("() => document.documentElement.dir")
        en_lang = page.evaluate("() => document.documentElement.lang")
        page.locator('.lang-opt[data-lang="ar"]:visible').first.click()
        page.wait_for_timeout(800)
        _shot(page, "locale_ar_rtl")
        ar_dir = page.evaluate("() => document.documentElement.dir")
        checks.record(
            "locale.rtl-ltr",
            en_dir == "ltr" and ar_dir == "rtl" and en_lang == "en",
            f"en={en_dir}/{en_lang} ar={ar_dir}",
        )
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(700)
        _shot(page, "viewport_mobile")
        overflow = page.evaluate(
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        checks.record("viewport.mobile-no-overflow", overflow <= 1, f"overflow={overflow}px")
    except Exception as exc:  # noqa: BLE001
        checks.record("locale.rtl-ltr", False, repr(exc))
    finally:
        ctx.close()


def main() -> int:
    global BASE, PLATFORM  # noqa: PLW0603 - CLI override of module defaults
    parser = argparse.ArgumentParser(description="Phase 4 browser journeys on PostgreSQL.")
    parser.add_argument("--base", default=BASE)
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    BASE = args.base.rstrip("/")
    PLATFORM = BASE + "/platform/"

    # Fail fast on the two preconditions: a reachable DB and the demo seed.
    try:
        _pg_row("SELECT 1")
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: cannot reach PostgreSQL at {DSN}: {exc}")
        return 2
    owner = _pg_row("SELECT id FROM users WHERE email = %s", (OWNER,))
    if not owner:
        print(f"FATAL: demo owner {OWNER} is absent; run scripts.seed_demo first.")
        return 2

    stamp = uuid.uuid4().hex[:6].upper()
    checks = Checks()
    print(f"Phase 4 journeys — base={BASE} db={DSN} stamp={stamp}\n")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
        try:
            j1_owner_creates_subsidiary(browser, checks, stamp)
            j2_owner_creates_user(browser, checks, stamp)
            report = j3_manager_submits_report(browser, checks, stamp)
            j4_accountant_reviews(browser, checks, report)
            j5_owner_approves_and_locks(browser, checks, report)
            j6_admin_creates_form(browser, checks, stamp)
            j7_hr_employee_movement(browser, checks, stamp)
            j8_investment_and_asset(browser, checks, stamp)
            j9_public_forms(browser, checks, stamp)
            j10_admin_processes_lead(browser, checks)
            j11_ai_knowledge_citations(browser, checks, stamp)
            j12_isolation(browser, checks)
            locale_and_viewport(browser, checks)
        finally:
            browser.close()

    journeys = [r for r in checks.rows if r["name"].startswith("J")]
    passed = sum(1 for r in checks.rows if r["ok"])
    summary = {
        "base": BASE,
        "dsn": DSN,
        "stamp": stamp,
        "checks": checks.rows,
        "journeys_passed": sum(1 for r in journeys if r["ok"]),
        "journeys_total": len(journeys),
        "passed": passed,
        "total": len(checks.rows),
        "console_errors": checks.console,
    }
    pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.out).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"\n=== journeys: {summary['journeys_passed']}/{summary['journeys_total']} "
        f"| checks: {passed}/{len(checks.rows)} ==="
    )
    if checks.console:
        print(f"console errors: {len(checks.console)}")
    return 0 if passed == len(checks.rows) else 1


if __name__ == "__main__":
    sys.exit(main())
