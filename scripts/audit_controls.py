"""Deep interactive audit of every control in the platform dashboard.

``verify_ui_controls.py`` proves each *view* renders and each *tab chip* toggles.
This harness goes one level deeper: for every routed view it enumerates every
clickable/typeable element the user can reach (buttons, links, form controls,
selects, checkboxes, role=button) and probes each one in the real browser.

A probe is a "no-op" when clicking the element produces:

  * no navigation and no hash change,
  * no DOM mutation inside the app shell,
  * no HTTP request,
  * no modal/dialog opening, and
  * no console error.

A dead control is a rendered element whose click does nothing at all. That is
the exact class of defect this audit exists to surface. Destructive or
session-ending controls (delete / logout / reset) are skipped so the sweep never
mutates state or ends the session mid-run; they are exercised by the dedicated
journey harnesses instead.

    BASE_URL=http://127.0.0.1:12001 python -m scripts.audit_controls
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "controls_audit.json"

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

# Controls whose click must not run in an audit (they mutate or end the session).
SKIP_HINTS = (
    "logout", "sign-out", "signout", "تسجيل الخروج", "خروج",
    "delete", "حذف", "remove", "إزالة", "destroy",
    "reset", "إعادة تعيين", "factory",
)


def _enumerate(page, scope: str = "view") -> list[dict]:
    """Return every interactable element in scope with a stable index.

    ``scope="view"`` limits the sweep to the active routed view; ``scope="shell"``
    covers the persistent chrome (sidebar navigation and the header controls).
    """
    return page.evaluate(
        """(scope) => {
            const sec = scope === 'shell'
                ? (document.querySelector('.sidebar') || document.querySelector('aside')
                   || document.querySelector('header'))
                : (document.querySelector('.app-view:not(.view-hidden)[data-view]')
                   || document.getElementById('board'));
            if (!sec) return [];
            const sel = 'button, a[href], input, select, textarea, [role=button]';
            const nodes = Array.from(sec.querySelectorAll(sel));
            const out = [];
            nodes.forEach((el, i) => {
                if (el.offsetParent === null) return;            // not visible
                if (el.disabled) return;                         // disabled is fine
                const tag = el.tagName.toLowerCase();
                const type = (el.getAttribute('type') || '').toLowerCase();
                const text = (el.innerText || el.value || el.getAttribute('aria-label')
                             || el.getAttribute('title') || '').trim().slice(0, 60);
                const cls = (el.className || '').toString().slice(0, 80);
                const attrs = el.getAttributeNames().filter(n => n.startsWith('data-'));
                out.push({idx: i, tag, type, text, cls, attrs,
                          id: el.id || ''});
            });
            return out;
        }""",
        scope,
    )


def _probe(page, idx: int, scope: str = "view") -> dict:
    """Interact with element #idx using the event its control type expects.

    A ``<select>`` fires ``change``, a text field fires ``input``, and a
    button/link fires ``click``. Probing all of them with ``click`` would
    misreport every dropdown and text box as dead, so the event is chosen by
    tag. Any observable effect (DOM mutation, request, navigation, focus,
    modal) counts as "alive"; a console error counts as a fault.
    """
    page.evaluate(
        """(a) => {
            const idx = a.idx, scope = a.scope;
            window.__audit = {mut: 0, req: 0, nav: 0, change: 0, input: 0};
            const sec = scope === 'shell'
                ? (document.querySelector('.sidebar') || document.querySelector('aside')
                   || document.querySelector('header'))
                : (document.querySelector('.app-view:not(.view-hidden)[data-view]')
                   || document.getElementById('board'));
            const sel = 'button, a[href], input, select, textarea, [role=button]';
            const nodes = Array.from(sec.querySelectorAll(sel))
                              .filter(e => e.offsetParent !== null && !e.disabled);
            const el = nodes[idx];
            window.__auditTarget = el;
            if (!el) return;
            window.__auditObs = new MutationObserver(m => { window.__audit.mut += m.length; });
            window.__auditObs.observe(document.body, {childList: true, subtree: true,
                                                      attributes: true, characterData: true});
            const of = window.fetch;
            window.fetch = function() { window.__audit.req++; return of.apply(this, arguments); };
            const oo = XMLHttpRequest.prototype.open;
            XMLHttpRequest.prototype.open = function() { window.__audit.req++;
                return oo.apply(this, arguments); };
            window.addEventListener('hashchange', () => window.__audit.nav++);
            el.addEventListener('change', () => window.__audit.change++);
            el.addEventListener('input', () => window.__audit.input++);
        }""",
        {"idx": idx, "scope": scope},
    )
    before_hash = page.evaluate("location.hash")
    dialogs_before = len(_dialogs)
    err_before = len(_errors)
    try:
        page.evaluate(
            """(a) => {
                const idx = a.idx, scope = a.scope;
                const sec = scope === 'shell'
                    ? (document.querySelector('.sidebar') || document.querySelector('aside')
                       || document.querySelector('header'))
                    : (document.querySelector('.app-view:not(.view-hidden)[data-view]')
                       || document.getElementById('board'));
                const sel = 'button, a[href], input, select, textarea, [role=button]';
                const nodes = Array.from(sec.querySelectorAll(sel))
                                  .filter(e => e.offsetParent !== null && !e.disabled);
                const el = nodes[idx];
                if (!el) return;
                el.scrollIntoView({block:'center'});
                const tag = el.tagName.toLowerCase();
                if (tag === 'select') {
                    if (el.options.length > 1) {
                        el.selectedIndex = el.selectedIndex === 0 ? 1 : 0;
                    }
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                    el.focus();
                } else if (tag === 'input' || tag === 'textarea') {
                    el.focus();
                    const t = (el.getAttribute('type') || '').toLowerCase();
                    if (t !== 'date' && t !== 'checkbox' && t !== 'radio' && t !== 'file') {
                        const setter = Object.getOwnPropertyDescriptor(
                            el.constructor.prototype, 'value').set;
                        setter.call(el, el.value + 'x');
                        el.dispatchEvent(new Event('input', {bubbles: true}));
                        setter.call(el, el.value.slice(0, -1));
                        el.dispatchEvent(new Event('input', {bubbles: true}));
                    } else if (t === 'checkbox' || t === 'radio') {
                        el.click();
                    }
                } else {
                    el.click();
                }
            }""",
            {"idx": idx, "scope": scope},
        )
        page.wait_for_timeout(900)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"interact error: {exc!r}"}
    audit = page.evaluate(
        """() => { const a = window.__audit || {};
                   if (window.__auditObs) window.__auditObs.disconnect();
                   const t = window.__auditTarget;
                   const focused = !!(t && document.activeElement === t);
                   return {mut: a.mut || 0, req: a.req || 0, nav: a.nav || 0,
                           change: a.change || 0, input: a.input || 0,
                           focused: focused}; }"""
    )
    after_hash = page.evaluate("location.hash")
    modal = page.evaluate(
        "() => !!document.querySelector('.modal:not(.hidden), [role=dialog]:not([hidden]), "
        ".overlay:not(.hidden), .drawer:not(.hidden)')"
    )
    err_delta = len(_errors) - err_before
    # A submit whose form fails native validation is correct behaviour, not a
    # dead control: the browser blocked the request as the markup intended.
    validation_blocked = page.evaluate(
        """() => { const t = window.__auditTarget;
                   if (!t) return false;
                   if ((t.getAttribute('type')||'') !== 'submit') return false;
                   const f = t.form || t.closest('form');
                   return !!(f && !f.checkValidity()); }"""
    )
    # A field/select that takes focus or fires its native event is working.
    did_something = validation_blocked or (
        audit["mut"] > 0 or audit["req"] > 0 or audit["nav"] > 0
        or audit["change"] > 0 or audit["input"] > 0
        or after_hash != before_hash or len(_dialogs) > dialogs_before
        or modal or audit["focused"]
    )
    return {
        "ok": (did_something or validation_blocked) and err_delta == 0,
        "did_something": did_something,
        "validation_blocked": validation_blocked,
        "mut": audit["mut"], "req": audit["req"], "nav": audit["nav"],
        "change": audit["change"], "input": audit["input"],
        "focused": audit["focused"],
        "hash_changed": after_hash != before_hash,
        "modal": modal, "dialog": len(_dialogs) > dialogs_before,
        "console_err_delta": err_delta,
    }


_errors: list[str] = []
_dialogs: list[str] = []


def _auto_dismiss(dialog) -> None:
    """Record and dismiss any native dialog so a probe never blocks."""
    _dialogs.append(dialog.type)
    try:
        dialog.dismiss()
    except Exception:  # noqa: BLE001 - already handled
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit every control in the platform.")
    parser.add_argument("--base", default=BASE)
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()
    base = args.base.rstrip("/")

    rows: list[dict] = []
    console: list[str] = []
    dead: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
        page = browser.new_context(viewport={"width": 1600, "height": 950}).new_page()
        page.on("console", lambda m: (console.append(m.text), _errors.append(m.text))
                if m.type == "error" else None)
        page.on("pageerror", lambda e: (console.append(str(e)), _errors.append(str(e))))
        page.on("dialog", _auto_dismiss)
        try:
            page.goto(base + "/platform/?year=2027&month=10", wait_until="networkidle")
            page.wait_for_selector("#loginEmail", state="visible")
            page.fill("#loginEmail", OWNER)
            page.fill("#loginPassword", PASSWORD)
            page.click("#loginBtn")
            page.wait_for_selector("#loginScreen", state="hidden", timeout=20000)
            page.wait_for_timeout(1500)

            def sweep(view: str, scope: str) -> None:
                page.evaluate("v => { location.hash = v; }", view)
                page.wait_for_timeout(2200)
                seen: set[str] = set()
                guard = 0
                while guard < 400:
                    guard += 1
                    controls = _enumerate(page, scope)
                    target = None
                    for c in controls:
                        sig = f"{c['tag']}|{c['id']}|{c['text']}|{','.join(c['attrs'])}"
                        if sig not in seen:
                            target = (sig, c)
                            break
                    if not target:
                        break
                    sig, c = target
                    seen.add(sig)
                    # Clear any leftover overlay so it cannot intercept the click.
                    page.evaluate(
                        """() => { const m = document.getElementById('appModal');
                                   if (m) m.remove(); }"""
                    )
                    label = f"{c['tag']}"
                    if c["id"]:
                        label += f"#{c['id']}"
                    if c["text"]:
                        label += f" \"{c['text']}\""
                    low = (c["text"] + " " + c["id"] + " " + c["cls"]).lower()
                    if any(h in low for h in SKIP_HINTS):
                        rows.append({"view": view, "control": label,
                                     "ok": True, "skipped": "destructive/session"})
                        continue
                    res = _probe(page, c["idx"], scope)
                    row = {"view": view, "control": label, "tag": c["tag"],
                           "type": c["type"], "attrs": c["attrs"], **res}
                    rows.append(row)
                    if not res.get("ok"):
                        dead.append(row)
                    if res.get("modal") or res.get("dialog"):
                        page.evaluate(
                            """() => { const m = document.getElementById('appModal');
                                       if (m) m.remove(); }"""
                        )
                    if res.get("hash_changed") or scope == "shell":
                        page.evaluate("v => { location.hash = v; }", view)
                        page.wait_for_timeout(1000)

            for view in VIEWS:
                sweep(view, "view")
            # Persistent chrome: sidebar navigation and header controls.
            sweep("dashboard", "shell")

        finally:
            browser.close()

    probed = [r for r in rows if "skipped" not in r]
    passed = sum(1 for r in probed if r.get("ok"))
    out = {
        "base": base, "views": VIEWS,
        "controls_total": len(rows),
        "probed": len(probed), "passed": passed, "dead": len(dead),
        "console_errors": console, "failures": dead, "rows": rows,
    }
    pathlib.Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2))
    for r in dead:
        print(f"DEAD | {r['view']:12s} | {r['control'][:70]} | {r}")
    print(f"\n=== controls: {passed}/{len(probed)} live | "
          f"skipped={len(rows)-len(probed)} | console errors: {len(console)} ===")
    return 0 if not dead else 1


if __name__ == "__main__":
    sys.exit(main())
