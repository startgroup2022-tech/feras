"""Collect every visible control label the running SPA renders, then report
which deck-named controls have no counterpart.

The compliance matrix can say a view "renders (N chars)" without proving the
deck's *named* buttons are on it. This pass walks every view and tab as the
Holding Owner, records the Arabic label of every visible button / link / field
label, and diffs that against the bracketed controls in the deck's text layer.

    python scripts/audit/control_labels.py --base http://127.0.0.1:12000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import re

from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "control_labels.json"

PASSWORD = "SafirDemo!2027"
OWNER = "owner@demo.safir.local"
# Every other seeded role that owns a deck screen (slides 7-11, 18-24, 34).
ROLE_ACCOUNTS = [
    "manager.tech@demo.safir.local",
    "accountant@demo.safir.local",
    "bd@demo.safir.local",
    "marketing@demo.safir.local",
    "design@demo.safir.local",
    "consultant@demo.safir.local",
]

VIEWS = [
    "dashboard", "leads", "requests", "feedback", "projects", "decisions",
    "subsidiaries", "reports", "financial", "investments", "support",
    "approvals", "documents", "bi", "analytics", "inbox", "employees",
    "operations", "accounting", "confidential", "admin",
]

# Deck tokens that are not app controls: the static header/period chips and the
# "▾" menu affordances, plus words the deck uses as a column header, not an
# action. Excluded so the diff stays a list of genuine candidates.
NON_CONTROL = {
    "عربي ▾", "العربية / EN", "الشركة / الجهة", "نطاق التكليف ▾",
    "إجراء رئيسي", "نص/سؤال", "رابط خارجي", "نص اختياري",
}

COLLECT = """() => {
  const vis = (e) => e.offsetParent !== null && !e.closest('[hidden]');
  const out = [];
  document.querySelectorAll(
    'button, a.btn-solid, a.btn-outline, a.btn, a.btn-ghost, a.lf-btn, .retry-btn, ' +
    'label .ar, .av-field > label, th, ' +
    'option, .sec-title, .tab, [data-tab], h3, .co-wiz-railnote'
  ).forEach((e) => {
    if (!vis(e)) return;
    const t = (e.innerText || e.textContent || '').replace(/\\s+/g, ' ').trim();
    if (t) out.push(t);
  });
  // Icon-only controls (the header magnifier, the account menu) carry their
  // label in an attribute rather than as text; read those too, otherwise the
  // deck's [بحث] / [حساب] would look absent when they are painted.
  document.querySelectorAll('[title],[aria-label],[data-title-ar],[data-title-en]').forEach((e) => {
    if (!vis(e)) return;
    ['title', 'aria-label', 'data-title-ar', 'data-title-en'].forEach((a) => {
      const v = (e.getAttribute(a) || '').replace(/\\s+/g, ' ').trim();
      if (v) out.push(v);
    });
  });
  return out;
}"""


async def run(base: str, out: pathlib.Path, *, wait: float = 0.45,
              max_rows: int = 6) -> dict:
    labels: set[str] = set()
    per_view: dict[str, int] = {}

    def flush() -> None:
        # Persist after every view so a slow crawl still leaves a usable
        # artifact instead of only the in-memory set.
        out.write_text(
            json.dumps({"labels": sorted(labels), "per_view": per_view},
                       ensure_ascii=False, indent=1),
            encoding="utf-8",
        )

    async def crawl(page, langs, tag: str) -> None:
        # Deck slide 5 shows the English labels; an AR-only pass would score
        # them missing because the `.en` spans are hidden in Arabic. The owner
        # pass therefore crawls both directions; the role passes crawl Arabic
        # only, because the deck's role screens (slides 7-11, 19, 24, 34) are
        # drawn in Arabic and the English twins are already proven by the owner
        # sweep.
        for lang in langs:
            await page.evaluate(
                """(l) => { const b = document.querySelector('[data-lang="' + l + '"]'); if (b) b.click(); }""",
                lang,
            )
            await page.wait_for_timeout(int(wait * 1000))
            for view in VIEWS:
                await page.evaluate(
                    """(v) => {
                      const a = [...document.querySelectorAll('[data-view]')]
                        .find(b => b.getAttribute('data-view') === v);
                      if (a) a.click();
                    }""",
                    view,
                )
                await page.wait_for_timeout(int(wait * 1000))
                found = await page.evaluate(COLLECT)
                labels.update(found)
                per_view[f"{tag}{lang}:{view}"] = len(found)
                flush()
                print(f"  {tag}{lang}:{view}: {len(found)}", flush=True)
                # Sweep this view's tabs, if it has any.
                tabs = await page.evaluate(
                    """() => [...document.querySelectorAll('[data-tab],[data-admin-tab],' +
                       '[data-acct-tab],[data-emp-tab],[data-ops-tab],[data-conf-tab],' +
                       '[data-an-tab]')].map(e =>
                         e.getAttribute('data-tab') || e.getAttribute('data-admin-tab') ||
                         e.getAttribute('data-acct-tab') || e.getAttribute('data-emp-tab') ||
                         e.getAttribute('data-ops-tab') || e.getAttribute('data-conf-tab') ||
                         e.getAttribute('data-an-tab'))"""
                )
                for tab in tabs:
                    if not tab:
                        continue
                    await page.evaluate(
                        """(t) => {
                          const sel = '[data-tab="' + t + '"], [data-admin-tab="' + t +
                            '"], [data-acct-tab="' + t + '"], [data-emp-tab="' + t +
                            '"], [data-ops-tab="' + t + '"], [data-conf-tab="' + t +
                            '"], [data-an-tab="' + t + '"]';
                          const b = document.querySelector(sel);
                          if (b) b.click();
                        }""",
                        tab,
                    )
                    await page.wait_for_timeout(int(wait * 1000))
                    labels.update(await page.evaluate(COLLECT))
                # A list row opens a detail modal whose named controls (slide
                # 28's [اعتماد]/[رفض], slide 20's [تسليم رابط], slide 15's
                # [تحديث الحالة]) are not on the list itself. Open *every* row
                # that carries a JSON payload, collect the modal, then close it,
                # so a control that lives on the second row is not missed.
                for _ in range(max_rows):
                    opened = await page.evaluate(
                        """() => {
                          // Detail openers: rows keyed by an entity id or a
                          // JSON payload. Both forms are on real list rows, so
                          // match either -- the id form is what the decision,
                          // report and support lists use.
                          const OPENERS = ['data-company','data-decision','data-doc',
                            'data-fb-source','data-invest-co','data-lead','data-opp',
                            'data-report','data-request','data-submission','data-kpi-open'];
                          const rows = [...document.querySelectorAll('.av-row')];
                          for (const r of rows) {
                            const hasJson = r.getAttributeNames().some(
                              n => n.startsWith('data-') && (r.getAttribute(n) || '').startsWith('{'));
                            const hasOpener = OPENERS.some(n => r.hasAttribute(n));
                            if ((hasJson || hasOpener) && !r.hasAttribute('data-probed')) {
                              r.setAttribute('data-probed','1'); r.click(); return true;
                            }
                          }
                          return false;
                        }"""
                    )
                    if not opened:
                        break
                    await page.wait_for_timeout(int(wait * 1000))
                    labels.update(await page.evaluate(COLLECT))
                    # Sweep any tabs the detail itself renders before closing.
                    inner_tabs = await page.evaluate(
                        """() => [...document.querySelectorAll(
                           '.modal [data-tab], .modal [data-admin-tab]')].map(e =>
                             e.getAttribute('data-tab') || e.getAttribute('data-admin-tab'))"""
                    )
                    for it in inner_tabs:
                        if not it:
                            continue
                        await page.evaluate(
                            """(t) => {
                              const b = document.querySelector(
                                '.modal [data-tab="' + t + '"], .modal [data-admin-tab="' + t + '"]');
                              if (b) b.click();
                            }""",
                            it,
                        )
                        await page.wait_for_timeout(int(wait * 700))
                        labels.update(await page.evaluate(COLLECT))
                    await page.evaluate(
                        """() => { const x = document.querySelector('.modal-x'); if (x) x.click(); }"""
                    )
                    await page.wait_for_timeout(int(wait * 700))
                # Clear the probe marks so the next view starts clean.
                await page.evaluate(
                    """() => document.querySelectorAll('[data-probed]').forEach(
                        e => e.removeAttribute('data-probed'))"""
                )
                flush()

    async def sign_in(page, email: str) -> None:
        await page.goto(base + "/platform/", wait_until="networkidle")
        await page.fill("#loginEmail", email)
        await page.fill("#loginPassword", PASSWORD)
        await page.click("#loginBtn")
        await page.wait_for_selector("#loginScreen", state="hidden", timeout=20000)
        await page.wait_for_timeout(int(wait * 2600))

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            executable_path="/usr/bin/chromium", args=["--no-sandbox"]
        )
        ctx = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await ctx.new_page()
        await page.goto(base + "/platform/", wait_until="networkidle")
        # The sign-in screen is a deck screen too (slide 6), so collect its
        # controls before authenticating.
        labels.update(await page.evaluate(COLLECT))
        await page.fill("#loginEmail", OWNER)
        await page.fill("#loginPassword", PASSWORD)
        await page.click("#loginBtn")
        await page.wait_for_selector("#loginScreen", state="hidden", timeout=20000)
        await page.wait_for_timeout(int(wait * 2600))
        await crawl(page, ("ar", "en"), "owner/")
        await ctx.close()

        # The remaining seeded roles own screens the owner never sees: the
        # specialist's task workspace (slide 20), the accountant's review
        # (slide 24), the manager's report form (slides 18/22/23), the advisor's
        # workspace (slide 34). A role-gated control is present, not missing,
        # so the crawl has to hold each role's session to score it.
        for email in ROLE_ACCOUNTS:
            rctx = await browser.new_context(viewport={"width": 1920, "height": 1080})
            rpage = await rctx.new_page()
            try:
                await sign_in(rpage, email)
                await crawl(rpage, ("ar",), email.split("@")[0] + "/")
            finally:
                await rctx.close()
        await browser.close()
    return {"labels": sorted(labels), "per_view": per_view}


def deck_tokens() -> dict[str, list[str]]:
    deck = json.loads((ROOT / "artifacts/deck/slides_text.json").read_text())
    toks: dict[str, list[str]] = {}
    for n, v in deck.items():
        text = json.dumps(v, ensure_ascii=False)
        for m in re.findall(r"\[([^\[\]]{2,40})\]", text):
            t = m.strip()
            if t and t not in NON_CONTROL:
                toks.setdefault(t, []).append(n)
    return toks


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="http://127.0.0.1:12000")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--timeout", type=int, default=1500)
    ap.add_argument("--roles", default="", help="comma-separated role emails; empty = all seeded roles")
    ap.add_argument("--owner-only", action="store_true", help="skip the role sweeps")
    ap.add_argument("--wait", type=float, default=0.45, help="settle delay per step, seconds")
    ap.add_argument("--max-rows", type=int, default=6, help="detail modals opened per view")
    args = ap.parse_args()
    global ROLE_ACCOUNTS
    if args.owner_only:
        ROLE_ACCOUNTS = []
    elif args.roles:
        ROLE_ACCOUNTS = [r.strip() for r in args.roles.split(",") if r.strip()]
    out = pathlib.Path(args.out)
    try:
        report = asyncio.run(asyncio.wait_for(
            run(args.base, out, wait=args.wait, max_rows=args.max_rows),
            timeout=args.timeout,
        ))
    except (TimeoutError, Exception) as exc:  # noqa: BLE001 - partial crawl is still useful
        # The run() writes the artifact after every view, so a timeout still
        # leaves the labels collected so far. Re-read it rather than failing.
        if not out.exists():
            raise
        print(f"crawl stopped early ({type(exc).__name__}); using partial artifact")
        report = json.loads(out.read_text(encoding="utf-8"))

    rendered = report["labels"]
    blob = "\n".join(rendered)
    toks = deck_tokens()
    # A control the browser probe (scripts/audit/deck_controls_probe.py) drives
    # into a gated data state is verified there, not here: the crawl stays in
    # the seeded demo state, so a task in `new` or an opportunity still in
    # study never paints its action. Cross-reference the probe so those six
    # tokens are not re-reported as missing.
    dc_path = ROOT / "artifacts" / "deck_controls.json"
    probed = set()
    if dc_path.exists():
        for entry in (json.loads(dc_path.read_text()).get("controls") or {}).values():
            if entry.get("ok") and entry.get("deck_label"):
                probed.add(entry["deck_label"])

    def probe_covers(token: str) -> bool:
        # Slide 20 also draws the compact [بدء] beside [بدء التنفيذ]; the two are
        # the same action, so a verified label covers a token it contains (or
        # that contains it) when the shorter side is still a real word.
        return any(
            (token in p or p in token) and min(len(token), len(p)) >= 3
            for p in probed
        )

    missing = {
        t: ns for t, ns in toks.items()
        if not probe_covers(t)
        # A deck control counts as present when the app renders the token itself
        # or a phrase that contains its leading noun (the app often uses a
        # shorter label, e.g. deck "إضافة ملاحظة" vs app "إضافة").
        and t not in blob and not any(
            t.split()[0] in r for r in rendered if len(t.split()[0]) > 3
        )
    }
    report["deck_tokens"] = len(toks)
    report["missing_tokens"] = missing
    out = pathlib.Path(args.out)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"collected {len(rendered)} distinct labels across {len(report['per_view'])} views")
    print(f"deck controls: {len(toks)}; no counterpart found: {len(missing)}")
    for t, ns in sorted(missing.items(), key=lambda kv: -len(kv[1])):
        print(f"  [{t}]  slides {','.join(ns[:8])}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
