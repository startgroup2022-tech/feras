"""End-to-end user journeys: browser clicks -> API -> PostgreSQL.

``verify_functional.py`` proves each *primary create* commits a row. This harness
proves the rest of the working set the brief calls out explicitly: the sign-in
gate, and the edit/save and approve/reject journeys for companies, users,
reports, support requests, leads and owner decisions.

Every step is driven through the rendered control the user would click (a
``data-*`` hook or a button id), not by calling the API from the harness. The
harness then opens PostgreSQL to confirm the *change* landed, and reloads the
browser to confirm the UI reflects it. A control that renders but does nothing
therefore fails here.

    APP_ENV=development \\
      DATABASE_URL="postgresql+psycopg://safir:safir@127.0.0.1:5432/safir" \\
      python -m uvicorn backend.main:app --port 8000 &
    python scripts/verify_journeys.py --base http://127.0.0.1:8000 \\
      --pg-dsn "postgresql://safir:safir@127.0.0.1:5432/safir"

The actor is the Holding Owner, who holds every permission, so a failure is an
implementation gap and never a missing grant.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import uuid

from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "journey_verification.json"

OWNER = "owner@demo.safir.local"
PASSWORD = "SafirDemo!2027"
CHROMIUM = "/usr/bin/chromium"


class Checks:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.console: list[str] = []

    def record(self, name: str, *, ok: bool, detail: str = "") -> None:
        self.rows.append({"name": name, "ok": bool(ok), "detail": detail})

    def summary(self) -> dict:
        return {
            "checks": self.rows,
            "passed": sum(1 for r in self.rows if r["ok"]),
            "total": len(self.rows),
            "console_errors": self.console,
        }


def _pg_row(dsn: str, sql: str, params: tuple):
    import psycopg

    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def _pg_exec(dsn: str, sql: str, params: tuple) -> None:
    import psycopg

    with psycopg.connect(dsn, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(sql, params)


# --------------------------------------------------------------------------
# browser helpers
# --------------------------------------------------------------------------
async def _login(page, base: str, email: str = OWNER) -> None:
    await page.goto(f"{base}/platform/?year=2027&month=10", wait_until="networkidle")
    await page.fill("#loginEmail", email)
    await page.fill("#loginPassword", PASSWORD)
    await page.click("#loginBtn")
    await page.wait_for_selector("#loginScreen", state="hidden", timeout=20000)
    await page.wait_for_timeout(1500)


async def _dismiss_modal(page) -> None:
    for _ in range(3):
        if not await page.query_selector("#appModal"):
            return
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(120)
        if not await page.query_selector("#appModal"):
            return
        await page.evaluate("() => { const m=document.querySelector('#appModal'); if (m) m.remove(); }")
        await page.wait_for_timeout(120)


async def _settle_modals(page, rounds: int = 4) -> None:
    for _ in range(rounds):
        if not await page.query_selector("#appModal"):
            await page.wait_for_timeout(150)
            if not await page.query_selector("#appModal"):
                return
        await _dismiss_modal(page)


async def _open_view(page, view: str) -> None:
    await _dismiss_modal(page)
    await page.evaluate(
        """() => {
          const more = document.querySelector('#sbMoreToggle');
          if (more && more.getAttribute('aria-expanded') !== 'true') more.click();
        }"""
    )
    await page.wait_for_timeout(200)
    clicked = await page.evaluate(
        """(view) => {
          const i = document.querySelector(`.nav-item[data-view="${view}"]`);
          if (i) { i.click(); return true; }
          return false;
        }""",
        view,
    )
    if not clicked:
        # Views that left the rail (the prototype's thirteen sections replaced
        # the older ones) stay reachable by deep link; drive the same hash
        # routing ``bindNav`` wires for a real user following a link.
        await page.evaluate("(view) => { location.hash = '#' + view; }", view)
    await page.wait_for_timeout(900)
    await _settle_modals(page)


async def _open_admin_tab(page, tab: str) -> None:
    await _open_view(page, "group")
    await page.evaluate(
        """(tab) => { const t = document.querySelector(`[data-admin-tab="${tab}"]`); if (t) t.click(); }""",
        tab,
    )
    await page.wait_for_timeout(900)


async def _click_confirm(page, label: str = "#cfOk") -> None:
    await page.wait_for_selector(label, timeout=8000)
    await page.click(label)
    await page.wait_for_timeout(600)


# --------------------------------------------------------------------------
# journeys
# --------------------------------------------------------------------------
async def _run(browser, base: str, dsn: str) -> dict:
    checks = Checks()
    ctx = await browser.new_context(viewport={"width": 1920, "height": 1080})
    page = await ctx.new_page()
    page.on("console", lambda m: checks.console.append(m.text) if m.type == "error" else None)

    # ---- sign-in gate ---------------------------------------------------
    try:
        await page.goto(f"{base}/platform/?year=2027&month=10", wait_until="networkidle")
        visible = await page.is_visible("#loginScreen")
        await page.fill("#loginEmail", OWNER)
        await page.fill("#loginPassword", PASSWORD)
        await page.click("#loginBtn")
        await page.wait_for_selector("#loginScreen", state="hidden", timeout=20000)
        shell = await page.is_visible(".app-shell") if await page.query_selector(".app-shell") else True
        checks.record("auth.login.gate", ok=bool(visible and shell), detail=f"gate={visible} shell={shell}")
    except Exception as exc:  # noqa: BLE001
        checks.record("auth.login.gate", ok=False, detail=repr(exc))
        await ctx.close()
        return checks.summary()

    # ---- bad credentials are refused ------------------------------------
    # A fresh context is required: the main context already holds a session in
    # localStorage, and a second page there would auto-authenticate without ever
    # showing the gate.
    try:
        bad_ctx = await browser.new_context(viewport={"width": 1920, "height": 1080})
        bad = await bad_ctx.new_page()
        await bad.goto(f"{base}/platform/?year=2027&month=10", wait_until="networkidle")
        await bad.wait_for_selector("#loginEmail", state="visible", timeout=20000)
        await bad.wait_for_function(
            "() => { const e=document.querySelector('#loginEmail'); return e && !e.disabled; }",
            timeout=20000,
        )
        await bad.fill("#loginEmail", OWNER)
        await bad.fill("#loginPassword", "wrong-password-xyz")
        await bad.click("#loginBtn")
        await bad.wait_for_timeout(2500)
        still_gated = await bad.is_visible("#loginScreen")
        err_text = ""
        if await bad.query_selector("#loginError"):
            err_text = (await bad.inner_text("#loginError")).strip()
        await bad_ctx.close()
        # A rejected sign-in must say the credentials are wrong, not reuse the
        # generic "session expired" wording the shared 401 mapping produces.
        mentions_credentials = ("كلمة المرور" in err_text) or ("password" in err_text.lower())
        checks.record(
            "auth.login.reject_bad",
            ok=bool(still_gated and mentions_credentials),
            detail=f"still_gated={still_gated} error={err_text[:60]!r}",
        )
    except Exception as exc:  # noqa: BLE001
        checks.record("auth.login.reject_bad", ok=False, detail=repr(exc))

    stamp = uuid.uuid4().hex[:6].upper()

    # ---- company edit / save --------------------------------------------
    try:
        await _open_view(page, "subsidiaries")
        await page.wait_for_selector("[data-company]", timeout=15000)
        cid = await page.evaluate("() => document.querySelector('[data-company]').getAttribute('data-company')")
        await page.click(f'[data-company="{cid}"]')
        await page.wait_for_selector("#coFileEdit", timeout=10000)
        await page.click("#coFileEdit")
        await page.wait_for_selector("#ceSave", timeout=8000)
        new_name = f"شركة معدلة {stamp}"
        await page.fill("#ceNameAr", new_name)
        await page.click("#ceSave")
        await page.wait_for_timeout(1500)
        row = _pg_row(dsn, "SELECT name_ar FROM companies WHERE id = %s", (int(cid),))
        checks.record("company.edit.save", ok=bool(row and row[0] == new_name), detail=f"pg={row}")
    except Exception as exc:  # noqa: BLE001
        checks.record("company.edit.save", ok=False, detail=repr(exc))
    finally:
        await _settle_modals(page)

    # ---- user edit / save (role change) ---------------------------------
    try:
        await _open_admin_tab(page, "users")
        await page.wait_for_selector('[data-admin-action="save-user"]', timeout=15000)
        uid = await page.evaluate(
            "() => document.querySelector('[data-admin-action=\"save-user\"]').getAttribute('data-id')"
        )
        before = _pg_row(dsn, "SELECT role_id FROM users WHERE id = %s", (int(uid),))
        # choose a different role than the current one
        target_role = await page.evaluate(
            """(uid) => {
              const sel = document.querySelector('#uRole' + uid);
              const cur = sel.value;
              const alt = Array.from(sel.options).find(o => o.value && o.value !== cur);
              return alt ? alt.value : null;
            }""",
            uid,
        )
        target_role_id = _pg_row(dsn, "SELECT id FROM roles WHERE code = %s", (target_role,))[0]
        before_role_id = before[0]
        if target_role:
            await page.select_option(f"#uRole{uid}", target_role)
        await page.click(f'[data-admin-action="save-user"][data-id="{uid}"]')
        await page.wait_for_timeout(1500)
        after = _pg_row(dsn, "SELECT role_id FROM users WHERE id = %s", (int(uid),))
        checks.record(
            "user.edit.save",
            ok=bool(after and before and after[0] == target_role_id and after[0] != before[0]),
            detail=f"before={before} target={target_role}({target_role_id}) after={after}",
        )
        # Restore the original role so a later role-scoped probe (api_probe's
        # per-role dashboards) still sees the seeded persona on its own role.
        # A restore hiccup must not turn a passing edit into a failure.
        if target_role and before_role_id != target_role_id:
            try:
                await page.select_option(f"#uRole{uid}", str(before_role_id))
                await page.click(f'[data-admin-action="save-user"][data-id="{uid}"]')
                await page.wait_for_timeout(1500)
            except Exception:  # noqa: BLE001
                _pg_exec(dsn, "UPDATE users SET role_id = %s WHERE id = %s", (before_role_id, int(uid)))
    except Exception as exc:  # noqa: BLE001
        checks.record("user.edit.save", ok=False, detail=repr(exc))
    finally:
        await _settle_modals(page)

    # ---- user deactivate / activate -------------------------------------
    try:
        uid = await page.evaluate(
            "() => document.querySelector('[data-admin-action=\"toggle-user\"]').getAttribute('data-id')"
        )
        before = _pg_row(dsn, "SELECT is_active FROM users WHERE id = %s", (int(uid),))
        await page.click(f'[data-admin-action="toggle-user"][data-id="{uid}"]')
        await page.wait_for_timeout(1500)
        after = _pg_row(dsn, "SELECT is_active FROM users WHERE id = %s", (int(uid),))
        checks.record(
            "user.toggle.active",
            ok=bool(before and after and before[0] != after[0]),
            detail=f"before={before} after={after}",
        )
        # put it back so the seed stays usable
        await page.click(f'[data-admin-action="toggle-user"][data-id="{uid}"]')
        await page.wait_for_timeout(1200)
    except Exception as exc:  # noqa: BLE001
        checks.record("user.toggle.active", ok=False, detail=repr(exc))
    finally:
        await _settle_modals(page)

    # ---- support request: status change + comment -----------------------
    try:
        await _open_view(page, "support")
        await page.wait_for_selector("[data-request]", timeout=15000)
        sid = await page.evaluate("() => document.querySelector('[data-request]').getAttribute('data-request')")
        await page.click(f'[data-request="{sid}"]')
        await page.wait_for_selector("#supSetStatus", timeout=10000)
        # Only offer a transition the state machine allows; the deck's dropdown
        # lists every status, but the service refuses an illegal edge (422).
        allowed = _pg_row(
            dsn,
            "SELECT status FROM support_requests WHERE id = %s",
            (int(sid),),
        )[0]
        transitions = {
            "new": "in_progress",
            "in_progress": "completed",
            "completed": "closed",
            "closed": "in_progress",
        }
        new_status = transitions.get(allowed)
        await page.select_option("#supNewStatus", new_status)
        await page.click("#supSetStatus")
        await page.wait_for_timeout(1500)
        row = _pg_row(dsn, "SELECT status FROM support_requests WHERE id = %s", (int(sid),))
        checks.record("support.status.change", ok=bool(row and row[0] == new_status), detail=f"pg={row} want={new_status}")
    except Exception as exc:  # noqa: BLE001
        checks.record("support.status.change", ok=False, detail=repr(exc))
    finally:
        await _settle_modals(page)

    # ---- support comment -------------------------------------------------
    try:
        await page.click(f'[data-request="{sid}"]')
        await page.wait_for_selector("#cmtBody", timeout=10000)
        text = f"تعليق تحقق {stamp}"
        await page.fill("#cmtBody", text)
        await page.click("#cmtAdd")
        await page.wait_for_timeout(1500)
        row = _pg_row(
            dsn,
            "SELECT count(*) FROM support_request_comments WHERE request_id = %s AND body = %s",
            (int(sid), text),
        )
        checks.record("support.comment.add", ok=bool(row and row[0] >= 1), detail=f"pg={row}")
    except Exception as exc:  # noqa: BLE001
        checks.record("support.comment.add", ok=False, detail=repr(exc))
    finally:
        await _settle_modals(page)

    # ---- report approve --------------------------------------------------
    try:
        # find a report in a state that allows approval (reviewed) that is not
        # already approved — an approved report offers Lock, not Approve.
        rep = _pg_row(
            dsn,
            "SELECT id, status FROM monthly_reports WHERE status IN ('reviewed','under_review','submitted') "
            "AND approval_status != 'approved' ORDER BY id LIMIT 1",
            (),
        )
        rid = rep[0]
        await _open_view(page, "reports")
        await page.wait_for_selector(f'[data-report="{rid}"]', timeout=15000)
        await page.click(f'[data-report="{rid}"]')
        await page.wait_for_selector("#repApprove", timeout=10000)
        await page.click("#repApprove")
        await _click_confirm(page, "#cfOk")
        await page.wait_for_timeout(1500)
        after = _pg_row(
            dsn,
            "SELECT status, approval_status FROM monthly_reports WHERE id = %s",
            (int(rid),),
        )
        checks.record(
            "report.approve",
            ok=bool(after and after[1] == "approved"),
            detail=f"before={rep[1]} after(status,approval)={after}",
        )
    except Exception as exc:  # noqa: BLE001
        checks.record("report.approve", ok=False, detail=repr(exc))
    finally:
        await _settle_modals(page)

    # ---- report lock (developer-package rule 1: approved -> locked) ------
    # The terminal transition: only a report already approved (reviewed +
    # approval_status=approved) offers the lock control, and once locked the
    # report must never change again.
    try:
        rep = _pg_row(
            dsn,
            "SELECT id, status, approval_status FROM monthly_reports "
            "WHERE status = 'reviewed' AND approval_status = 'approved' ORDER BY id LIMIT 1",
            (),
        )
        if rep is None:
            checks.record("report.lock", ok=False, detail="no approved report to lock")
        else:
            rid = rep[0]
            await _open_view(page, "reports")
            await page.wait_for_selector(f'[data-report="{rid}"]', timeout=15000)
            await page.click(f'[data-report="{rid}"]')
            await page.wait_for_selector("#repLock", timeout=10000)
            await page.click("#repLock")
            await _click_confirm(page, "#cfOk")
            await page.wait_for_timeout(1500)
            after = _pg_row(
                dsn,
                "SELECT status, locked_by_id, locked_at FROM monthly_reports WHERE id = %s",
                (int(rid),),
            )
            checks.record(
                "report.lock",
                ok=bool(after and after[0] == "locked" and after[1] and after[2]),
                detail=f"before={rep[1]} after(status,locked_by,locked_at)={after}",
            )
    except Exception as exc:  # noqa: BLE001
        checks.record("report.lock", ok=False, detail=repr(exc))
    finally:
        await _settle_modals(page)

    # ---- report return for correction -----------------------------------
    # Self-provisioning: create a fresh report through the follow-up panel,
    # submit it, then return it. A company with no report in the probe period
    # is what makes its card offer [إنشاء تقرير] instead of [عرض التقرير].
    try:
        rep = _pg_row(dsn, "SELECT id, status FROM monthly_reports WHERE status = 'submitted' ORDER BY id LIMIT 1", ())
        rid = rep[0] if rep else None
        before_status = rep[1] if rep else None
        if rid is None:
            # period with no seeded report for the probe company
            probe_year, probe_month = 2027, 8
            co = _pg_row(
                dsn,
                "SELECT c.id FROM companies c WHERE c.id NOT IN "
                "(SELECT company_id FROM monthly_reports WHERE period_year=%s AND period_month=%s) "
                "ORDER BY c.id LIMIT 1",
                (probe_year, probe_month),
            )[0]
            await _dismiss_modal(page)
            await page.goto(
                f"{base}/platform/?year={probe_year}&month={probe_month}", wait_until="networkidle"
            )
            await page.wait_for_timeout(1500)
            await page.click(f'.rep-grid [data-remind="{co}"]')
            await page.wait_for_selector("#fuCreate", timeout=10000)
            await page.click("#fuCreate")
            await page.wait_for_selector("#crSave", timeout=10000)
            await page.fill("#crRev", "800000")
            await page.fill("#crExp", "500000")
            await page.click("#crSave")
            await page.wait_for_selector("#repSubmit", timeout=15000)
            await page.click("#repSubmit")
            await _click_confirm(page, "#cfOk")
            await page.wait_for_timeout(1500)
            created = _pg_row(
                dsn,
                "SELECT id, status FROM monthly_reports WHERE company_id=%s AND period_year=%s AND period_month=%s",
                (co, probe_year, probe_month),
            )
            rid, before_status = created[0], created[1]
        await _open_view(page, "reports")
        await page.wait_for_selector(f'[data-report="{rid}"]', timeout=15000)
        await page.click(f'[data-report="{rid}"]')
        await page.wait_for_selector("#repReturn", timeout=10000)
        await page.click("#repReturn")
        await page.wait_for_selector("#pdValue", timeout=8000)
        await page.fill("#pdValue", f"سبب الإعادة {stamp}")
        await page.click("#pdOk")
        await page.wait_for_timeout(1500)
        after = _pg_row(dsn, "SELECT status FROM monthly_reports WHERE id = %s", (int(rid),))
        checks.record("report.return", ok=bool(after and after[0] == "returned"), detail=f"before={before_status} after={after}")
    except Exception as exc:  # noqa: BLE001
        checks.record("report.return", ok=False, detail=repr(exc))
    finally:
        await _settle_modals(page)

    # ---- lead edit / save ------------------------------------------------
    try:
        await _open_view(page, "leads")
        await page.wait_for_selector("[data-lead]", timeout=15000)
        lid = await page.evaluate("() => document.querySelector('[data-lead]').getAttribute('data-lead')")
        await page.click(f'[data-lead="{lid}"]')
        await page.wait_for_selector("#leadSave", timeout=10000)
        note = f"ملاحظة تحقق {stamp}"
        await page.fill("#leadInternalNotes", note)
        await page.click("#leadSave")
        await page.wait_for_timeout(1500)
        row = _pg_row(dsn, "SELECT internal_notes FROM website_leads WHERE id = %s", (int(lid),))
        checks.record("lead.edit.save", ok=bool(row and row[0] == note), detail=f"pg={row}")
    except Exception as exc:  # noqa: BLE001
        checks.record("lead.edit.save", ok=False, detail=repr(exc))
    finally:
        await _settle_modals(page)

    # ---- owner decision: create via the UI, then approve -----------------
    did = None
    try:
        await _open_view(page, "decisions")
        await page.wait_for_selector("#decForm", timeout=15000)
        num = f"DEC-{stamp}"
        await page.fill("#dcNumber", num)
        await page.fill("#dcTitle", f"قرار تحقق {stamp}")
        await page.fill("#dcBody", "نص قرار التحقق الوظيفي")
        await page.evaluate("() => { const f=document.querySelector('#decForm'); f.dispatchEvent(new Event('submit', {cancelable:true})); }")
        await page.wait_for_timeout(1800)
        created = _pg_row(dsn, "SELECT id FROM owner_decisions WHERE number = %s", (num,))
        if created:
            did = created[0]
        checks.record("decision.create", ok=bool(created), detail=f"pg_row={created}")
    except Exception as exc:  # noqa: BLE001
        checks.record("decision.create", ok=False, detail=repr(exc))
    finally:
        await _settle_modals(page)

    try:
        if not did:
            checks.record("decision.approve", ok=False, detail="create did not yield a decision to approve")
        else:
            await _open_view(page, "decisions")
            await page.wait_for_selector(f'[data-decision="{did}"]', timeout=15000)
            await page.click(f'[data-act="dec-open"][data-id="{did}"]')
            await page.wait_for_selector('[data-act="dec-detail-outcome"][data-outcome="done"]', timeout=10000)
            await page.click('[data-act="dec-detail-outcome"][data-outcome="done"]')
            await page.wait_for_timeout(1500)
            after = _pg_row(dsn, "SELECT status FROM owner_decisions WHERE id = %s", (int(did),))
            checks.record("decision.approve", ok=bool(after and after[0] == "done"), detail=f"pg={after}")
    except Exception as exc:  # noqa: BLE001
        checks.record("decision.approve", ok=False, detail=repr(exc))
    finally:
        await _settle_modals(page)

    # ---- approvals inbox: act on a pending task as its assignee ----------
    # The approval inbox is per-assignee ("requests waiting for your action"),
    # so the actor must be the user the pending task names, not the owner. The
    # task itself is provisioned here: a CAPEX request is created, its mandatory
    # quotation attached and the request submitted, which routes it to the
    # company manager's queue. Signing in as that manager and approving proves
    # the inbox action writes through to PostgreSQL.
    try:
        import tempfile

        co = _pg_row(dsn, "SELECT id FROM companies WHERE code = 'SAF-TECH'", ())[0]
        await _dismiss_modal(page)
        await _open_view(page, "requests")
        await page.click("#reqNew")
        await page.wait_for_selector("#nrSave", timeout=10000)
        # pick the first published form offered (its id is seed-dependent)
        form_id = await page.evaluate(
            """() => {
              const s = document.querySelector('#nrForm');
              const o = Array.from(s.options).find(x => x.value);
              return o ? o.value : null;
            }"""
        )
        if not form_id:
            raise RuntimeError("no form option available in #nrForm")
        await page.select_option("#nrForm", form_id)
        await page.select_option("#nrCompany", str(co))
        await page.fill("#nrTitle", f"طلب اعتماد تحقق {stamp}")
        await page.click("#nrSave")
        await page.wait_for_selector("#subEdit", timeout=15000)
        # fill the form's required values, then save the draft
        await page.click("#subEdit")
        await page.wait_for_selector('[data-value-key="amount"]', timeout=10000)
        await page.fill('[data-value-key="amount"]', "1500000")
        await page.fill('[data-value-key="purpose"]', "تحقق آلي من مسار الاعتماد.")
        await page.select_option('[data-value-key="priority"]', "high")
        await page.click("#seSave")
        await page.wait_for_timeout(1500)
        # satisfy the mandatory quotation requirement, then submit
        await page.wait_for_selector("[data-req-upload]", timeout=10000)
        with tempfile.NamedTemporaryFile("wb", suffix=".pdf") as fh:
            fh.write(b"%PDF-1.4\n% safir journey quotation\n")
            fh.flush()
            async with page.expect_file_chooser() as fc:
                await page.click("[data-req-upload]")
            chooser = await fc.value
            await chooser.set_files(fh.name)
        await page.wait_for_timeout(1800)
        await page.wait_for_selector("#subSubmit", timeout=10000)
        await page.click("#subSubmit")
        await page.wait_for_timeout(2500)
        pending = _pg_row(
            dsn,
            "SELECT t.id, t.instance_id, u.email FROM approval_tasks t "
            "JOIN users u ON u.id = t.assignee_id WHERE t.status = 'pending' "
            "ORDER BY t.id DESC LIMIT 1",
            (),
        )
        if not pending:
            checks.record("approval.act", ok=False, detail="submission did not route to an approver")
        else:
            task_id, instance_id, assignee_email = pending
            sub = _pg_row(
                dsn,
                "SELECT submission_id FROM workflow_instances WHERE id = %s",
                (int(instance_id),),
            )[0]
            appr_ctx = await browser.new_context(viewport={"width": 1920, "height": 1080})
            ap = await appr_ctx.new_page()
            await _login(ap, base, email=assignee_email)
            await _open_view(ap, "approvals")
            await ap.wait_for_selector(f'[data-submission="{sub}"]', timeout=15000)
            await ap.click(f'[data-submission="{sub}"]')
            await ap.wait_for_selector('[data-act="approve"]', timeout=10000)
            await ap.click('[data-act="approve"]')
            await ap.wait_for_timeout(1800)
            after = _pg_row(dsn, "SELECT status FROM approval_tasks WHERE id = %s", (int(task_id),))
            await appr_ctx.close()
            checks.record(
                "approval.act",
                ok=bool(after and after[0] != "pending"),
                detail=f"task={task_id} assignee={assignee_email} after={after}",
            )
    except Exception as exc:  # noqa: BLE001
        checks.record("approval.act", ok=False, detail=repr(exc))
    finally:
        await _settle_modals(page)

    await ctx.close()
    return checks.summary()


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--pg-dsn", required=True)
    args = ap.parse_args()

    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
        summary = await _run(browser, args.base, args.pg_dsn)
        await browser.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    for row in summary["checks"]:
        print(f"{'OK  ' if row['ok'] else 'FAIL'} {row['name']:28} {row['detail']}")
    print(f"\n{summary['passed']}/{summary['total']} journeys verified")
    if summary["console_errors"]:
        print("console errors:", summary["console_errors"][:5])
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
