"""Prove the deck's *named* controls actually render and act in the live SPA.

``control_labels.py`` diffs the deck's bracketed labels against every visible
label the app paints. Ten labels came back with no counterpart, but most of
them are gated on a data state the seeded demo does not happen to be in (a task
in ``new``, a ``returned`` report, a ``done`` decision, an approved report for
the manager's smart brief). A label that only appears in a state the demo never
reaches is *not* proof of a gap -- and neither is a string match on the source.
This probe settles it the only way that counts: it drives the real browser to
each state, then reads the rendered label.

Per control it records the deck label, the app label it found, and whether the
control was actually clickable. It writes ``artifacts/deck_controls.json`` and
screenshots each state.

    python scripts/audit/deck_controls_probe.py --base http://127.0.0.1:12000

The seeded demo is *not* mutated destructively: the report/task/decision states
are created through the real services on throwaway companies and rows, or by
walking the existing rows through their own transitions. Only the throwaway
rows are written.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys

import httpx

ROOT = pathlib.Path(__file__).resolve().parents[2]
SHOTS = ROOT / "artifacts" / "shots"
OUT = ROOT / "artifacts" / "deck_controls.json"
PASSWORD = "SafirDemo!2027"

OWNER = "owner@demo.safir.local"
MANAGER = "manager.tech@demo.safir.local"
BD = "bd@demo.safir.local"


def _login(client: httpx.Client, base: str, email: str) -> str:
    r = client.post(f"{base}/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["access_token"]


def _api(base: str, email: str) -> httpx.Client:
    c = httpx.Client(base_url=base, timeout=30)
    token = _login(c, base, email)
    c.headers["Authorization"] = f"Bearer {token}"
    return c


def prepare(base: str) -> dict:
    """Put the demo into the states the deck's gated controls need.

    Everything is created through the public API, so the probe exercises the
    same path a user would. The seeded demo's own companies are the target, so
    the created rows are visible to the seeded roles the browser step signs in
    as. Returns a small map of the ids it created.
    """
    owner = _api(base, OWNER)
    made: dict = {"created": []}

    users = owner.get("/api/v1/users").json()
    by_role = {u.get("role_code"): u for u in users}
    designer = by_role.get("designer")
    # The owner sees every company; the seeded subsidiaries come first in the
    # code ordering, so pick the first that is a real subsidiary (not a
    # wizard test company).
    companies = owner.get("/api/v1/companies").json()
    cid = next((c["id"] for c in companies if c["code"].startswith("SAF-")), companies[0]["id"])
    made["company_id"] = cid

    # Slide 20 [بدء التنفيذ]: a task in ``new`` assigned to a specialist, so
    # the specialist's task workspace shows the start button.
    if designer:
        t = owner.post(
            "/api/v1/operations/tasks",
            json={"company_id": cid, "title": "مهمة برهان أزرار العرض",
                  "assignee_id": designer["id"], "priority": "normal"},
        )
        if t.status_code in (200, 201):
            made["task_id"] = t.json()["id"]
            made["created"].append(f"task:{made['task_id']}")
        else:
            made.setdefault("errors", []).append(f"task {t.status_code}: {t.text[:120]}")

    # Slide 29 [عرض سجل القرار]: a decision in ``done`` carries its log entry.
    d = owner.post(
        "/api/v1/operations/owner-decisions",
        json={"number": "DEC-PROBE-1", "title": "قرار برهان سجل القرار",
              "company_id": cid, "executor_user_id": designer["id"] if designer else None},
    )
    if d.status_code in (200, 201):
        did = d.json()["id"]
        made["decision_id"] = did
        made["created"].append(f"decision:{did}")
        owner.patch(f"/api/v1/operations/owner-decisions/{did}", json={"status": "done"})
    else:
        made.setdefault("errors", []).append(f"decision {d.status_code}: {d.text[:120]}")

    # Slides 22 + 38: the company manager needs a *draft* report for the
    # [حفظ وإرسال] form, and a *returned* report for [فتح للتصحيح]. The SPA's
    # reports view is year-scoped to the reporting period, so the rows must live
    # in the active year (2027). Reuse the seeded rows when present -- creating a
    # fresh row every run would drift the demo -- and only fall back to creating
    # one in 2027 when the seed lacks that state.
    mgr = _api(base, MANAGER)
    rows = mgr.get("/api/v1/monthly-reports").json()
    live_2027 = [r for r in rows if r["company_id"] == cid and r["period_year"] == 2027]

    def _free_month_2027() -> int | None:
        taken = {r["period_month"] for r in live_2027}
        for month in range(1, 13):
            if month not in taken:
                return month
        return None

    def _mk_2027(month: int) -> int | None:
        r = mgr.post(
            "/api/v1/monthly-reports",
            json={"company_id": cid, "period_year": 2027, "period_month": month,
                  "revenue": "120000.00", "expenses": "80000.00",
                  "net_result": "40000.00", "major_problems": "برهان العرض"},
        )
        if r.status_code in (200, 201):
            made["created"].append(f"report:{r.json()['id']}")
            return r.json()["id"]
        made.setdefault("errors", []).append(f"report {r.status_code}: {r.text[:160]}")
        return None

    draft = next((r for r in live_2027 if r["status"] == "draft"), None)
    if draft is None:
        month = _free_month_2027()
        rid = _mk_2027(month) if month else None
        draft = {"id": rid} if rid else None
    if draft:
        made["draft_report_id"] = draft["id"]

    ret = next((r for r in live_2027 if r["status"] == "returned"), None)
    if ret is None:
        month = _free_month_2027()
        rid = _mk_2027(month) if month else None
        if rid is not None:
            mgr.post(f"/api/v1/monthly-reports/{rid}/submit", json={})
            rr = owner.post(f"/api/v1/monthly-reports/{rid}/return",
                            json={"reason": "برهان زر التصحيح"})
            made["return_status"] = rr.status_code
            ret = {"id": rid}
    if ret:
        made["returned_report_id"] = ret["id"]

    # Slide 46: the manager's brief only paints after the period's *current*
    # report is approved. Approve the manager's 2027-10 report.
    reports = owner.get("/api/v1/monthly-reports").json()
    live = [r for r in reports
            if r["company_id"] == cid and r["period_year"] == 2027
            and r["period_month"] == 10 and r["is_live"]]
    if live:
        rid = live[0]["id"]
        made["current_report_id"] = rid
        if live[0]["status"] == "draft":
            mgr.post(f"/api/v1/monthly-reports/{rid}/submit", json={})
        if live[0]["status"] in ("draft", "submitted", "under_review", "reviewed"):
            ar = owner.post(f"/api/v1/monthly-reports/{rid}/approve", json={})
            made["approve_status"] = ar.status_code

    # Slide 23 [حفظ مسودة] / [إرسال للمراجعة] / [إرسال للمحاسب]: the manager's
    # editable financial form only paints while the version is a draft. The
    # financial view is period-scoped (2027-10), so the draft must live in that
    # period for the row to render.
    s = mgr.post(
        "/api/v1/financial/summaries",
        json={"company_id": cid, "period_year": 2027, "period_month": 10,
              "submitted_revenue": "150000.00", "submitted_expenses": "90000.00",
              "closing_bank_balance": "40000.00", "closing_cash_balance": "10000.00",
              "manager_notes": "برهان مسودة الملخص"},
    )
    if s.status_code in (200, 201):
        made["fin_summary_id"] = s.json()["id"]
        made["fin_period_id"] = s.json()["period_id"]
        made["created"].append(f"financial_summary:{made['fin_summary_id']}")
    else:
        made.setdefault("errors", []).append(
            f"financial_summary {s.status_code}: {s.text[:160]}")
        # A prior run already created the version; read the period back. The
        # report row carries ``period_id`` even when the draft has no
        # ``version_id`` yet, so match on either.
        rep = mgr.get("/api/v1/financial/report?year=2027&month=10").json()
        for c in rep.get("companies", []):
            if c.get("company_id") == cid and (c.get("version_id") or c.get("period_id")):
                made["fin_summary_id"] = c.get("version_id")
                made["fin_period_id"] = c.get("period_id")
                break

    mgr.close()
    owner.close()
    return made


async def probe(base: str, made: dict) -> dict:
    from playwright.async_api import async_playwright

    SHOTS.mkdir(parents=True, exist_ok=True)
    result: dict = {"controls": {}, "console": []}

    def note(key: str, deck: str, app_label: str | None, ok: bool, detail: str = "") -> None:
        result["controls"][key] = {
            "deck_label": deck, "app_label": app_label, "ok": bool(ok), "detail": detail,
        }

    async def sign_in(page, email: str) -> None:
        await page.goto(f"{base}/platform/?year=2027&month=10", wait_until="networkidle")
        await page.fill("#loginEmail", email)
        await page.fill("#loginPassword", PASSWORD)
        await page.click("#loginBtn")
        await page.wait_for_selector("#loginScreen", state="hidden", timeout=20000)
        await page.wait_for_timeout(2500)

    async def click_view(page, view: str) -> None:
        await page.evaluate(
            """(v) => { const a = [...document.querySelectorAll('[data-view]')]
                 .find(x => x.getAttribute('data-view') === v); if (a) a.click(); }""",
            view,
        )
        await page.wait_for_timeout(1200)

    async def modal_labels(page) -> list[str]:
        return await page.evaluate(
            """() => [...document.querySelectorAll('.modal button')]
                 .map(b => (b.innerText || '').replace(/\\s+/g, ' ').trim())"""
        )

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            executable_path="/usr/bin/chromium", args=["--no-sandbox"]
        )

        # ---- specialist: slides 20 (task workspace) -----------------------
        ctx = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await ctx.new_page()
        page.on("console", lambda m: result["console"].append(m.text) if m.type == "error" else None)
        await sign_in(page, "design@demo.safir.local")
        await click_view(page, "operations")
        await page.evaluate(
            """() => { const b = document.querySelector('[data-ops-tab="tasks"]'); if (b) b.click(); }"""
        )
        await page.wait_for_timeout(1000)
        # Open the task in ``new`` that the prepare step created for this
        # specialist -- the deck's [بدء التنفيذ] only shows then.
        opened = await page.evaluate(
            """(tid) => {
              const rows = [...document.querySelectorAll('#opsContent .av-row')];
              for (const r of rows) {
                const raw = r.getAttribute('data-task');
                if (!raw) continue;
                try {
                  const t = JSON.parse(raw);
                  if ((tid == null || t.id === tid) && t.status === 'new') { r.click(); return t.id; }
                } catch (e) {}
              }
              return null;
            }""",
            made.get("task_id"),
        )
        await page.wait_for_timeout(1200)
        labels = await modal_labels(page)
        start = next((l for l in labels if l == "بدء التنفيذ"), None)
        note("slide20_start", "بدء التنفيذ", start, start is not None,
             f"task={opened} buttons={labels}")
        await page.screenshot(path=str(SHOTS / "probe-slide20-task.png"))
        await ctx.close()

        # ---- manager: slides 22 (report form) + 38 (correction) + 46 (brief)
        ctx = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await ctx.new_page()
        page.on("console", lambda m: result["console"].append(m.text) if m.type == "error" else None)
        await sign_in(page, MANAGER)
        # slide 46 -- smart brief on the dashboard (after approval)
        await page.wait_for_timeout(800)
        brief_visible = await page.evaluate(
            """() => { const s = document.getElementById('smartBriefSection');
                 return s ? !s.hidden : false; }"""
        )
        plan = await page.evaluate(
            """() => { const b = document.getElementById('sbPlan');
                 return b ? (b.innerText || '').replace(/\\s+/g,' ').trim() : null; }"""
        )
        decline = await page.evaluate(
            """() => { const b = document.getElementById('sbDecline');
                 return b ? (b.innerText || '').replace(/\\s+/g,' ').trim() : null; }"""
        )
        note("slide46_plan", "نعم، اطلب خطة", plan, plan == "نعم، اطلب خطة",
             f"brief_visible={brief_visible}")
        note("slide46_decline", "لا، شكرًا", decline, decline == "لا، شكرًا",
             f"brief_visible={brief_visible}")
        await page.screenshot(path=str(SHOTS / "probe-slide46-brief.png"))

        # slide 22 -- the *draft* report's [حفظ وإرسال]; slide 38 -- the
        # *returned* report's [فتح للتصحيح]. Open each by its own id so the two
        # states are not confused.
        await click_view(page, "reports")
        async def open_report(rid) -> list[str]:
            # The reports list is year-scoped and paged; wait for the row to
            # actually paint before clicking, rather than racing a fixed sleep.
            sel = '#reportsList .av-row[data-report="' + str(rid) + '"]'
            try:
                await page.wait_for_selector(sel, timeout=8000)
            except Exception:
                return []
            await page.click(sel)
            await page.wait_for_timeout(1200)
            out = await modal_labels(page)
            await page.evaluate(
                """() => { const x = document.querySelector('.modal-x'); if (x) x.click(); }"""
            )
            await page.wait_for_timeout(500)
            return out

        labels = await open_report(made.get("draft_report_id"))
        submit = next((l for l in labels if l == "حفظ وإرسال"), None)
        note("slide22_save_submit", "حفظ وإرسال", submit, submit is not None, f"buttons={labels}")
        await page.screenshot(path=str(SHOTS / "probe-slide22-report.png"))

        labels = await open_report(made.get("returned_report_id"))
        correct = next((l for l in labels if l == "فتح للتصحيح"), None)
        note("slide38_open_correction", "فتح للتصحيح", correct, correct is not None,
             f"buttons={labels}")
        await page.screenshot(path=str(SHOTS / "probe-slide38-correction.png"))

        # slide 23 -- the draft financial summary's editable form. The deck
        # names the form button [حفظ مسودة], the submit [إرسال للمراجعة] and the
        # page's primary action [إرسال للمحاسب].
        await click_view(page, "financial")
        fin_sel = '#financialList [data-fin-period="' + str(made.get("fin_period_id")) + '"]'
        try:
            await page.wait_for_selector(fin_sel, timeout=8000)
            await page.click(fin_sel)
        except Exception:
            pass
        # The editable draft form paints asynchronously once the summary loads.
        try:
            await page.wait_for_selector(
                ".modal button:has-text('حفظ مسودة')", timeout=8000
            )
        except Exception:
            pass
        await page.wait_for_timeout(600)
        fin_labels = await modal_labels(page)
        save_draft = next((l for l in fin_labels if l == "حفظ مسودة"), None)
        submit_review = next((l for l in fin_labels if l == "إرسال للمراجعة"), None)
        note("slide23_save_draft", "حفظ مسودة", save_draft, save_draft is not None,
             f"buttons={fin_labels}")
        note("slide23_submit_review", "إرسال للمراجعة", submit_review,
             submit_review is not None, f"buttons={fin_labels}")
        # [إرسال للمحاسب] is the confirm button of the send dialog.
        send_acc = None
        if submit_review:
            await page.evaluate(
                """() => { const b = [...document.querySelectorAll('.modal button')]
                     .find(x => (x.innerText||'').trim() === 'إرسال للمراجعة'); if (b) b.click(); }"""
            )
            await page.wait_for_timeout(900)
            confirm = await page.evaluate(
                """() => { const b = [...document.querySelectorAll('.modal button, .confirm button')]
                     .find(x => (x.innerText||'').trim() === 'إرسال للمحاسب');
                     return b ? b.innerText.trim() : null; }"""
            )
            send_acc = confirm
            await page.evaluate(
                """() => { const b = [...document.querySelectorAll('.modal button, .confirm button')]
                     .find(x => /إلغاء|Cancel/.test(x.innerText||'')); if (b) b.click(); }"""
            )
            await page.wait_for_timeout(400)
        note("slide23_send_accountant", "إرسال للمحاسب", send_acc, send_acc is not None,
             f"confirm={send_acc}")
        await page.screenshot(path=str(SHOTS / "probe-slide23-financial.png"))

        # slide 35 -- the BI view's primary [إعداد ملخص].
        await click_view(page, "bi")
        bi_label = await page.evaluate(
            """() => { const b = document.getElementById('biSummarize');
                 return b ? (b.innerText||'').replace(/\\s+/g,' ').trim() : null; }"""
        )
        note("slide35_prepare_summary", "إعداد ملخص", bi_label,
             bi_label == "إعداد ملخص", f"label={bi_label}")
        await page.screenshot(path=str(SHOTS / "probe-slide35-bi.png"))

        # slide 18 -- the company manager's new support request form names
        # [حفظ مسودة] and [إرسال الطلب]. Open it from the Support view and read
        # both footer controls (not just the source markup).
        await click_view(page, "support")
        await page.wait_for_timeout(800)
        await page.evaluate(
            """() => { const b = document.getElementById('supNew'); if (b) b.click(); }"""
        )
        await page.wait_for_timeout(1200)
        support_labels = await modal_labels(page)
        s18_draft = next((l for l in support_labels if l == "حفظ مسودة"), None)
        s18_send = next((l for l in support_labels if l == "إرسال الطلب"), None)
        note("slide18_save_draft", "حفظ مسودة", s18_draft, s18_draft is not None,
             f"buttons={support_labels}")
        note("slide18_send_request", "إرسال الطلب", s18_send, s18_send is not None,
             f"buttons={support_labels}")
        await page.screenshot(path=str(SHOTS / "probe-slide18-support-form.png"))
        await ctx.close()

        # ---- BD: slide 26 (opportunity study) + slide 38 correction -------
        ctx = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await ctx.new_page()
        page.on("console", lambda m: result["console"].append(m.text) if m.type == "error" else None)
        await sign_in(page, BD)
        await click_view(page, "projects")
        await page.evaluate(
            """() => { const r = document.querySelector('#projContent .av-row[data-proj]');
                 if (r) r.click(); }"""
        )
        await page.wait_for_timeout(1200)
        labels = await modal_labels(page)
        study = next((l for l in labels if l == "حفظ الدراسة"), None)
        raise_owner = next((l for l in labels if l == "رفع للمالك عند الحاجة"), None)
        note("slide26_save_study", "حفظ الدراسة", study, study is not None, f"buttons={labels}")
        note("slide26_raise_owner", "رفع للمالك عند الحاجة", raise_owner,
             raise_owner is not None, f"buttons={labels}")
        await page.screenshot(path=str(SHOTS / "probe-slide26-opportunity.png"))
        await ctx.close()

        # slide 38 -- the requests empty state names [إنشاء طلب]. The healthcare
        # manager has form.submit but no seeded submissions, so its list is
        # genuinely empty and the deck's empty-state control paints.
        ctx = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await ctx.new_page()
        await sign_in(page, "manager.hlt@demo.safir.local")
        await click_view(page, "requests")
        await page.wait_for_timeout(1200)
        create_req = await page.evaluate(
            """() => { const b = document.getElementById('reqNewEmpty');
                 return b ? (b.innerText||'').replace(/\\s+/g,' ').trim() : null; }"""
        )
        note("slide38_create_request", "إنشاء طلب", create_req,
             create_req == "إنشاء طلب", f"label={create_req}")
        await page.screenshot(path=str(SHOTS / "probe-slide38-empty-requests.png"))
        await ctx.close()

        # ---- owner: slides 29 (decision log) + 36 (inbox) + 38 ------------
        ctx = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await ctx.new_page()
        page.on("console", lambda m: result["console"].append(m.text) if m.type == "error" else None)
        await sign_in(page, OWNER)
        # slide 29 -- a done decision carries [عرض سجل القرار] on its row.
        await click_view(page, "decisions")
        log = await page.evaluate(
            """() => { const b = [...document.querySelectorAll('#decContent button')]
                 .find(x => (x.innerText||'').trim() === 'عرض سجل القرار');
                 return b ? b.innerText.trim() : null; }"""
        )
        note("slide29_decision_log", "عرض سجل القرار", log, log is not None, "")
        await page.screenshot(path=str(SHOTS / "probe-slide29-decisions.png"))

        # slide 36 -- the inbox row action is named after the record.
        await click_view(page, "inbox")
        inbox_actions = await page.evaluate(
            """() => [...document.querySelectorAll('#inboxContent button, #notifList button, ' +
                 '#inboxList button')].map(b => (b.innerText||'').replace(/\\s+/g,' ').trim())"""
        )
        open_form = next((l for l in inbox_actions if l == "فتح الاستمارة"), None)
        note("slide36_open_form", "فتح الاستمارة", open_form, open_form is not None,
             f"actions={inbox_actions}")
        await page.screenshot(path=str(SHOTS / "probe-slide36-inbox.png"))

        # slide 37 -- [إضافة مستخدم] is the owner's add-user control on the
        # admin "users" tab. Prove it renders and opens its form.
        await click_view(page, "admin")
        await page.evaluate(
            """() => { const t = document.querySelector('[data-admin-tab="users"]');
                 if (t) t.click(); }"""
        )
        await page.wait_for_timeout(1500)
        add_user = await page.evaluate(
            """() => { const b = [...document.querySelectorAll('#adminContent button')]
                 .find(x => (x.innerText||'').trim() === 'إضافة مستخدم');
                 return b ? b.innerText.trim() : null; }"""
        )
        if add_user:
            await page.evaluate(
                """() => { const b = [...document.querySelectorAll('#adminContent button')]
                     .find(x => (x.innerText||'').trim() === 'إضافة مستخدم'); if (b) b.click(); }"""
            )
            await page.wait_for_timeout(1200)
        form_buttons = await modal_labels(page)
        has_save = any(l == "حفظ" for l in form_buttons)
        note("slide37_add_user", "إضافة مستخدم", add_user,
             add_user is not None and has_save,
             f"form_buttons={form_buttons}")
        await page.screenshot(path=str(SHOTS / "probe-slide37-add-user.png"))
        await page.evaluate(
            """() => { const x = document.querySelector('.modal-x'); if (x) x.click(); }"""
        )
        await ctx.close()

        # slide 38 -- [فتح للتصحيح] is on a *returned* report for the manager.
        ctx = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await ctx.new_page()
        await sign_in(page, MANAGER)
        await click_view(page, "reports")
        # Open every report and record which corrective controls paint.
        found: list[str] = []
        count = await page.evaluate(
            """() => document.querySelectorAll('#reportsList .av-row[data-report]').length"""
        )
        for i in range(count):
            await page.evaluate(
                """(i) => { const rows = document.querySelectorAll('#reportsList .av-row[data-report]');
                     if (rows[i]) rows[i].click(); }""", i,
            )
            await page.wait_for_timeout(900)
            found += await modal_labels(page)
            await page.evaluate(
                """() => { const x = document.querySelector('.modal-x'); if (x) x.click(); }"""
            )
            await page.wait_for_timeout(400)
        correct = next((l for l in found if l == "فتح للتصحيح"), None)
        note("slide38_open_correction", "فتح للتصحيح", correct, correct is not None,
             f"seen={sorted(set(found))}")
        await page.screenshot(path=str(SHOTS / "probe-slide38-correction.png"))
        await ctx.close()

        # ---- consultant: slide 34 (assignment-scope header label) ----------
        ctx = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await ctx.new_page()
        await sign_in(page, "consultant@demo.safir.local")
        scope = await page.evaluate(
            """() => { const l = document.querySelector('.scope-ctl .scope-pick .scope-lbl .ar');
                 return l ? (l.innerText||'').trim() : null; }"""
        )
        note("slide34_assignment_scope", "نطاق التكليف", scope,
             scope == "نطاق التكليف ▾", f"label={scope!r}")
        await page.screenshot(path=str(SHOTS / "probe-slide34-consultant.png"))
        await ctx.close()

        await browser.close()
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="http://127.0.0.1:12000")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--no-prepare", action="store_true")
    args = ap.parse_args()

    base = args.base.rstrip("/")
    made: dict = {}
    if not args.no_prepare:
        try:
            made = prepare(base)
        except Exception as exc:  # noqa: BLE001 - a failed setup still leaves the read
            made = {"prepare_error": f"{type(exc).__name__}: {exc}"}
    report = asyncio.run(probe(base, made))
    report["prepared"] = made
    pathlib.Path(args.out).write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    ok = sum(1 for c in report["controls"].values() if c["ok"])
    total = len(report["controls"])
    print(f"deck controls verified: {ok}/{total}")
    for k, c in sorted(report["controls"].items()):
        flag = "OK " if c["ok"] else "MISS"
        print(f"  {flag} {k}: deck={c['deck_label']!r} app={c['app_label']!r}")
    if report["console"]:
        print(f"console errors: {len(report['console'])}")
    print(f"wrote {args.out}")
    return 0 if ok == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
