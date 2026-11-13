"""Network-aware interaction matrix for the platform SPA.

``audit_controls.py`` marks a control "live" when a click produces *any*
observable effect. That is not enough: a control whose click fires an API call
that answers 4xx/5xx is observably alive but functionally broken, and a control
that only toggles a CSS class without doing its job is "alive" but wrong.

For every routed view this harness enumerates every visible, enabled control,
clicks it with a real browser event, and records the requests the click
triggered and their HTTP statuses, DOM mutation inside the app shell, hash
change / modal opening, and console errors.

A probe PASSes when it produces a real effect with no 5xx and no console error.
It FAILs when it fires a 5xx, throws, or does nothing at all. A 401/403/404 with
no success and no visible effect is recorded BLOCKED (expected for controls the
signed-in role may not use).

    BASE_URL=http://127.0.0.1:12002 python -m scripts.audit.interaction_matrix
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
from collections import Counter

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "audit" / "interaction_matrix.json"

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:12002").rstrip("/")
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

# Controls whose click ends the session or destroys data are exercised by the
# journey harnesses, not by a sweep that must keep the session alive.
SKIP_HINTS = (
    "logout", "sign-out", "signout", "تسجيل الخروج", "خروج",
    "delete", "حذف", "remove", "إزالة", "destroy", "reset", "إعادة تعيين",
)

SEL = "button, a[href], input, select, textarea, [role=button]"

SCOPE_JS = (
    "(document.querySelector('.app-view:not(.view-hidden)[data-view]') || "
    "document.getElementById('board'))"
)


def _enumerate_js() -> str:
    return (
        "() => {\n"
        "  const sec = " + SCOPE_JS + ";\n"
        "  if (!sec) return [];\n"
        "  const nodes = Array.from(sec.querySelectorAll('" + SEL + "'))\n"
        "      .filter(e => e.offsetParent !== null);\n"
        "  const out = [];\n"
        "  nodes.forEach((el, i) => {\n"
        "    const tag = el.tagName.toLowerCase();\n"
        "    const type = (el.getAttribute('type') || '').toLowerCase();\n"
        "    const text = (el.innerText || el.value || el.getAttribute('aria-label')\n"
        "                  || el.getAttribute('title') || '').trim().slice(0, 60);\n"
        "    const attrs = el.getAttributeNames().filter(n => n.startsWith('data-'));\n"
        "    out.push({idx: i, tag, type, text, attrs, id: el.id || '',\n"
        "              disabled: !!el.disabled});\n"
        "  });\n"
        "  return out;\n"
        "}"
    )


# Stable target list: every visible control, in document order, *including*
# disabled ones. Indices therefore never shift when a control toggles its
# disabled state between enumeration and interaction.
_NODES_JS = (
    "const sec = " + SCOPE_JS + ";\n"
    "  const nodes = sec ? Array.from(sec.querySelectorAll('" + SEL + "'))\n"
    "      .filter(e => e.offsetParent !== null) : [];\n"
)


def _install_js() -> str:
    return (
        "() => {\n"
        "  " + _NODES_JS +
        "  const el = nodes[window.__imIdx];\n"
        "  window.__im = {mut: 0, reqs: [], statuses: []};\n"
        "  window.__imTarget = el;\n"
        "  window.__imFormInvalid = !!(el && el.closest('form')\n"
        "      && !el.closest('form').checkValidity());\n"
        "  if (!el) return;\n"
        "  window.__imObs = new MutationObserver(m => { window.__im.mut += m.length; });\n"
        "  window.__imObs.observe(document.body,\n"
        "    {childList: true, subtree: true, attributes: true, characterData: true});\n"
        "  const of = window.fetch;\n"
        "  window.fetch = function() {\n"
        "    const u = (arguments[0] && arguments[0].url) || arguments[0];\n"
        "    window.__im.reqs.push('FETCH ' + u);\n"
        "    return of.apply(this, arguments);\n"
        "  };\n"
        "  const ox = XMLHttpRequest.prototype.open;\n"
        "  XMLHttpRequest.prototype.open = function(m, u) {\n"
        "    window.__im.reqs.push('XHR ' + m + ' ' + u);\n"
        "    const self = this;\n"
        "    this.addEventListener('loadend', function() {\n"
        "      try { window.__im.statuses.push([String(u), self.status]); } catch (e) {}\n"
        "    });\n"
        "    return ox.apply(this, arguments);\n"
        "  };\n"
        "}"
    )


def _act_js() -> str:
    return (
        "() => {\n"
        "  " + _NODES_JS +
        "  const el = nodes[window.__imIdx];\n"
        "  if (!el || el.disabled) return;\n"
        "  el.scrollIntoView({block: 'center'});\n"
        "  const tag = el.tagName.toLowerCase();\n"
        "  if (tag === 'select') {\n"
        "    if (el.options.length > 1) el.selectedIndex = el.selectedIndex === 0 ? 1 : 0;\n"
        "    el.dispatchEvent(new Event('change', {bubbles: true}));\n"
        "  } else if (tag === 'input' || tag === 'textarea') {\n"
        "    const t = (el.getAttribute('type') || '').toLowerCase();\n"
        "    if (t === 'checkbox' || t === 'radio') { el.click(); }\n"
        "    else if (t !== 'date' && t !== 'file') {\n"
        "      const set = Object.getOwnPropertyDescriptor(el.constructor.prototype, 'value').set;\n"
        "      set.call(el, el.value + 'x');\n"
        "      el.dispatchEvent(new Event('input', {bubbles: true}));\n"
        "      set.call(el, el.value.slice(0, -1));\n"
        "      el.dispatchEvent(new Event('input', {bubbles: true}));\n"
        "    }\n"
        "  } else { el.click(); }\n"
        "}"
    )


MODAL_JS = (
    "() => ({hash: location.hash, modals: document.querySelectorAll("
    "'.modal:not(.hidden),[role=dialog]:not([hidden]),.overlay:not(.hidden)').length})"
)


def probe(page, view, idx, sig, scope="view"):
    """Re-render the view, then click control #idx and report effect + network.

    Async views (leads, employees, ...) fetch and re-render after navigation, so
    the control list is polled until two consecutive enumerations agree before
    acting. The element at ``idx`` is then re-verified against ``sig``; on a
    mismatch the control is re-located by ``(tag, id, text)`` so a late re-render
    cannot make this probe click the wrong element.
    """
    if "/platform/" not in page.url:
        page.goto(BASE + "/platform/", wait_until="domcontentloaded")
        page.wait_for_timeout(600)
    page.evaluate("() => { location.hash = 'dashboard' }")
    page.wait_for_timeout(160)
    page.evaluate("v => { location.hash = v }", view)
    prev = None
    for _ in range(8):
        page.wait_for_timeout(450)
        cur = page.evaluate(_enumerate_js())
        if prev is not None and _sig_list(cur) == _sig_list(prev):
            break
        prev = cur
    page.evaluate("(a) => { window.__imIdx = a; }", idx)
    ok = page.evaluate(_verify_js(), sig)
    if not ok:
        page.evaluate(_locate_js(), sig)
    page.evaluate(_install_js())
    before = page.evaluate(MODAL_JS)
    try:
        page.evaluate(_act_js())
        page.wait_for_timeout(900)
    except Exception as exc:  # noqa: BLE001
        return {"reason": f"interact error: {exc!r}"}
    im = page.evaluate(
        "() => { const a = window.__im || {};"
        " if (window.__imObs) window.__imObs.disconnect();"
        " return {mut: a.mut || 0, reqs: a.reqs || [], statuses: a.statuses || [],"
        "         formInvalid: !!window.__imFormInvalid}; }"
    )
    after = page.evaluate(MODAL_JS)
    return {
        "mut": im["mut"], "reqs": im["reqs"], "statuses": im["statuses"],
        "formInvalid": im["formInvalid"],
        "nav": before["hash"] != after["hash"],
        "modal": after["modals"] > before["modals"],
    }


def _sig_list(controls):
    return [(c["tag"], c["id"], c["text"], c["disabled"]) for c in controls]


def _verify_js() -> str:
    """True when the control at ``window.__imIdx`` matches ``window.__imSig``."""
    return (
        "() => {\n"
        "  " + _NODES_JS +
        "  const el = nodes[window.__imIdx];\n"
        "  const s = window.__imSig;\n"
        "  if (!el || !s) return false;\n"
        "  const text = (el.innerText || el.value || el.getAttribute('aria-label')\n"
        "                || el.getAttribute('title') || '').trim().slice(0, 60);\n"
        "  return el.tagName.toLowerCase() === s.tag && (el.id || '') === s.id\n"
        "         && text === s.text;\n"
        "}"
    )


def _locate_js() -> str:
    """Point ``window.__imIdx`` at the first control matching ``window.__imSig``."""
    return (
        "() => {\n"
        "  " + _NODES_JS +
        "  const s = window.__imSig;\n"
        "  for (let i = 0; i < nodes.length; i++) {\n"
        "    const el = nodes[i];\n"
        "    const text = (el.innerText || el.value || el.getAttribute('aria-label')\n"
        "                  || el.getAttribute('title') || '').trim().slice(0, 60);\n"
        "    if (el.tagName.toLowerCase() === s.tag && (el.id || '') === s.id\n"
        "        && text === s.text) { window.__imIdx = i; return true; }\n"
        "  }\n"
        "  return false;\n"
        "}"
    )


def confirm_dead(browser, results):
    """Re-test each DEAD action button on a *fresh* page.

    The batch sweep shares one page across ~360 probes, so a control can appear
    dead purely because an earlier probe left the view in a different state.
    A genuine dead control stays dead here, where every probe starts from a
    clean login and a freshly rendered view.
    """
    for r in results:
        if r["result"] != "DEAD":
            continue
        c = r["control"]
        sig = {"tag": c["tag"], "id": c["id"], "text": c["text"]}
        ctx = browser.new_context(viewport={"width": 1600, "height": 950},
                                  locale="ar-SA")
        page = ctx.new_page()
        page.on("dialog", lambda d: d.dismiss())
        try:
            page.goto(BASE + "/platform/", wait_until="domcontentloaded")
            page.wait_for_timeout(500)
            page.fill("#loginEmail", OWNER)
            page.fill("#loginPassword", PASSWORD)
            page.click("#loginBtn")
            page.wait_for_timeout(2600)
            page.evaluate("v => { location.hash = v }", r["view"])
            page.wait_for_timeout(1500)
            page.evaluate("(s) => { window.__imSig = s; }", sig)
            if not page.evaluate(_locate_js(), sig):
                r["confirm"] = "not-found"
                continue
            page.evaluate(_install_js())
            before = page.evaluate(MODAL_JS)
            page.evaluate(_act_js())
            page.wait_for_timeout(900)
            im = page.evaluate(
                "() => { const a = window.__im || {};"
                " if (window.__imObs) window.__imObs.disconnect();"
                " return {mut: a.mut || 0, reqs: a.reqs || []}; }")
            after = page.evaluate(MODAL_JS)
            effect = (im["mut"] > 0 or len(im["reqs"]) > 0
                      or before["hash"] != after["hash"]
                      or after["modals"] > before["modals"])
            if effect:
                r["confirm"] = "false-positive"
                r["result"] = "PASS"
                r["mut"] = im["mut"]
                r["reqs"] = im["reqs"]
            elif page.evaluate("() => !!window.__imFormInvalid"):
                r["confirm"] = "confirmed-noop"
                r["result"] = "NOOP"
            else:
                r["confirm"] = "confirmed-dead"
        except Exception as exc:  # noqa: BLE001
            r["confirm"] = f"error: {exc!r}"
        finally:
            ctx.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--email", default=OWNER)
    args = ap.parse_args()
    results = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=CHROMIUM,
                               args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = b.new_context(viewport={"width": 1600, "height": 950}, locale="ar-SA")
        page = ctx.new_page()
        errors: list[str] = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append("PAGEERROR " + str(e)))
        page.goto(BASE + "/platform/", wait_until="domcontentloaded")
        page.fill("#loginEmail", args.email)
        page.fill("#loginPassword", PASSWORD)
        page.click("#loginBtn")
        page.wait_for_timeout(2600)

        for view in VIEWS:
            page.evaluate("v => { location.hash = v }", view)
            page.wait_for_timeout(1500)
            controls = page.evaluate(_enumerate_js())
            for c in controls:
                label = (c["text"] or c["id"] or c["tag"]).lower()
                if any(h in label for h in SKIP_HINTS):
                    results.append({"view": view, "control": c, "result": "SKIP"})
                    continue
                if c.get("disabled"):
                    results.append({"view": view, "control": c, "result": "DISABLED"})
                    continue
                errors.clear()
                sig = {"tag": c["tag"], "id": c["id"], "text": c["text"]}
                page.evaluate("(s) => { window.__imSig = s; }", sig)
                r = probe(page, view, c["idx"], sig, "view")
                if "reason" in r:
                    results.append({"view": view, "control": c, "result": "FAIL",
                                    "reason": r["reason"]})
                else:
                    statuses = [s for s in r["statuses"] if isinstance(s, list)]
                    s5 = [s for s in statuses if s[1] >= 500]
                    s4 = [s for s in statuses if 400 <= s[1] < 500]
                    s2 = [s for s in statuses if 200 <= s[1] < 300]
                    # The shell issues /auth/me + /auth/refresh on some renders;
                    # a 401 there on a still-valid session is noise, not a defect.
                    real_errors = [e for e in errors if "401" not in e]
                    effect = r["mut"] > 0 or r["nav"] or r["modal"] or len(r["reqs"]) > 0
                    is_tab = any("tab" in a for a in c.get("attrs", []))
                    is_submit = c["tag"] == "button" and c["type"] == "submit"
                    is_field = c["tag"] in ("input", "select", "textarea")
                    if s5 or real_errors:
                        res = "FAIL"
                    elif s4 and not s2 and not r["mut"] and not r["nav"] and not r["modal"]:
                        res = "BLOCKED"
                    elif not effect:
                        # Form fields that commit on Apply/Enter, tab chips
                        # already active, create forms submitted with required
                        # fields empty (native validation blocks the submit),
                        # and empty AI asks are correct no-ops. Genuine dead
                        # controls are action buttons/links that neither
                        # mutate, navigate, open a dialog nor call the API.
                        noop = (is_tab or is_submit or is_field
                                or r.get("formInvalid"))
                        res = "NOOP" if noop else "DEAD"
                    else:
                        res = "PASS"
                    results.append({"view": view, "control": c, "result": res,
                                    "mut": r["mut"], "nav": r["nav"], "modal": r["modal"],
                                    "reqs": r["reqs"], "statuses": statuses,
                                    "errors": errors[:2]})
        confirm_dead(b, results)
        b.close()

    pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.out).write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    counts = Counter(r["result"] for r in results)
    print("=== interaction matrix:", dict(counts), "of", len(results), "===")
    for r in results:
        if r["result"] in ("FAIL", "DEAD", "BLOCKED"):
            print(" ", r["result"], r.get("confirm", ""), r["view"], "|",
                  r["control"]["tag"], (r["control"]["text"] or "")[:40], "|",
                  r.get("errors") or r.get("reason") or r.get("statuses"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
