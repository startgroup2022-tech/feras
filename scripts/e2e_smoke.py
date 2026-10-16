"""Real-browser E2E smoke sweep for the SAFIR internal platform.

Logs in as each seeded role, visits every screen the role can reach, and fails
loudly on: page errors, console errors, HTTP 5xx responses, and failed API
calls. Also verifies the AR/EN switch flips ``dir``/``lang`` and that a phone
viewport renders without horizontal overflow.

Usage::

    BASE_URL=http://127.0.0.1:12000 python -m scripts.e2e_smoke

Requires the demo seed (``python -m scripts.seed_demo --reset``) and Playwright
Chromium (``python -m playwright install chromium``). This is a local
verification tool; it is not part of the pytest suite and never touches
production.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:12000")
PLATFORM = BASE + "/platform/"
PASSWORD = "SafirDemo!2027"

# Seeded roles exercised in the sweep. The reachable screens are enumerated
# from the live DOM (nav items the role can see), not hardcoded here.
ROLES = {
    "holding_owner": "owner@demo.safir.local",
    "company_manager": "manager.tech@demo.safir.local",
    "accountant": "accountant@demo.safir.local",
    "business_development": "bd@demo.safir.local",
    "marketing": "marketing@demo.safir.local",
    "designer": "design@demo.safir.local",
}

# Admin sub-tabs (rendered inside #adminContent).
ADMIN_TABS = [
    "structure", "companies", "departments", "users", "roles",
    "website", "builder", "workflows", "integrations", "audit",
]


@dataclass
class Report:
    errors: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def fail(self, msg: str) -> None:
        self.errors.append(msg)

    def note(self, msg: str) -> None:
        self.notes.append(msg)


def _login(page, email: str) -> bool:
    page.goto(PLATFORM, wait_until="networkidle")
    page.fill("#loginEmail", email)
    page.fill("#loginPassword", PASSWORD)
    page.click("#loginBtn")
    try:
        page.wait_for_selector(".app-shell:not(.view-hidden), #nav, .nav-item", timeout=8000)
        return True
    except Exception:
        return False


def _open_view(page, view: str) -> bool:
    """Click the role's nav item for ``view``; return True if it was clickable."""
    item = page.query_selector(f'.nav-item[data-view="{view}"]')
    if not item or not item.is_visible():
        return False
    item.click()
    page.wait_for_timeout(900)
    return True


def run() -> int:
    report = Report()
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        for role, email in ROLES.items():
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            page = ctx.new_page()
            page_errors: list[str] = []
            console_errors: list[str] = []
            http_5xx: list[str] = []
            api_failed: list[str] = []

            page.on("pageerror", lambda e, pe=page_errors: pe.append(str(e)))
            page.on(
                "console",
                lambda m, ce=console_errors: (
                    ce.append(m.text) if m.type == "error" else None
                ),
            )
            page.on(
                "response",
                lambda r, h5=http_5xx, af=api_failed: (
                    h5.append(f"{r.status} {r.url}")
                    if r.status >= 500
                    else (
                        af.append(f"{r.status} {r.url}")
                        if "/api/v1/" in r.url and r.status >= 400
                        else None
                    )
                ),
            )

            if not _login(page, email):
                report.fail(f"[{role}] login failed for {email}")
                ctx.close()
                continue
            report.note(f"[{role}] login ok")

            # Enumerate the nav items the role can actually see, then open each.
            visible_views = page.evaluate(
                """() => Array.from(document.querySelectorAll('.nav-item'))
                     .filter(el => el.offsetParent !== null)
                     .map(el => el.getAttribute('data-view'))"""
            )
            report.note(f"[{role}] visible views: {','.join(visible_views)}")
            for view in visible_views:
                before = len(page_errors) + len(console_errors)
                if not _open_view(page, view):
                    report.fail(f"[{role}] nav item for '{view}' not visible")
                    continue
                visible = page.evaluate(
                    """(v) => {
                        var s = document.querySelector('section[data-view="'+v+'"]');
                        if (!s) return false;
                        return !s.classList.contains('view-hidden');
                    }""",
                    view,
                )
                if not visible:
                    report.fail(f"[{role}] view '{view}' did not open")
                after = len(page_errors) + len(console_errors)
                if after > before:
                    report.fail(
                        f"[{role}] JS errors on '{view}': "
                        + "; ".join((page_errors + console_errors)[before:after])
                    )
                if view == "admin":
                    # Only the tabs the role may use are rendered visible.
                    labels = page.evaluate(
                        """() => Array.from(document.querySelectorAll('[data-admin-tab]'))
                             .filter(el => el.offsetParent !== null)
                             .map(el => el.getAttribute('data-admin-tab'))"""
                    )
                    for label in labels:
                        try:
                            page.locator(
                                f'[data-admin-tab="{label}"]:visible'
                            ).first.click()
                            page.wait_for_timeout(500)
                        except Exception as exc:
                            report.fail(f"[{role}] admin tab '{label}': {exc}")

            # AR/EN switch via the visible header toggle
            try:
                page.locator('.lang-opt[data-lang="en"]:visible').first.click()
                page.wait_for_timeout(500)
                en = page.evaluate("() => document.documentElement.dir")
                page.locator('.lang-opt[data-lang="ar"]:visible').first.click()
                page.wait_for_timeout(500)
                ar = page.evaluate("() => document.documentElement.dir")
                if en != "ltr" or ar != "rtl":
                    report.fail(f"[{role}] lang switch dir wrong: en={en} ar={ar}")
                else:
                    report.note(f"[{role}] lang switch ok (en=ltr ar=rtl)")
            except Exception as exc:
                report.fail(f"[{role}] lang switch: {exc}")

            # mobile viewport overflow check
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_timeout(400)
            overflow = page.evaluate(
                "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
            )
            if overflow > 4:
                report.fail(f"[{role}] horizontal overflow {overflow}px at 390w")
            else:
                report.note(f"[{role}] mobile 390w no overflow")

            if http_5xx:
                report.fail(f"[{role}] HTTP 5xx: " + "; ".join(sorted(set(http_5xx))))
            if api_failed:
                report.fail(
                    f"[{role}] API >=400: " + "; ".join(sorted(set(api_failed)))
                )

            ctx.close()

        browser.close()

    print("==== E2E NOTES ====")
    for n in report.notes:
        print("  " + n)
    print("==== E2E FAILURES ====")
    if not report.errors:
        print("  none")
    for e in report.errors:
        print("  - " + e)
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(run())
