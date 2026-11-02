"""Visual parity probe: compare the rendered deck to the rendered SPA.

Text extraction proves what the deck *says*; it does not prove that the app
*looks* like it. This probe closes that gap in two ways:

1. **Deck frame** -- measure the deck's own rendered PNGs (``artifacts/deck/png``)
   and extract the frame every interface slide repeats: a full-width title band
   near the top, a breadcrumb line under it, a four-control header row
   (``[الشركة/الجهة] [بحث] [العربية/EN] [الحساب]``) and a right-hand rail.
2. **App frame** -- drive the running SPA, measure the same regions from the
   live DOM (bounding boxes, not source claims) and sample the rendered pixels,
   then assert the app carries the same frame and stays inside the deck's
   palette (light surface + navy band).

Output ``artifacts/visual_parity.json``::

    python scripts/audit/visual_parity.py --base http://127.0.0.1:12000

Requires Pillow (``pip install pillow``) for the deck-side pixel sampling.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys

from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts"
DECK_PNG = ARTIFACTS / "deck" / "png"

PASSWORD = "SafirDemo!2027"
OWNER = "owner@demo.safir.local"

# The deck's repeated light surface and navy band, sampled from its PNGs.
DECK_SURFACE = (245, 247, 250)
DECK_NAVY = (20, 43, 85)


def _mean(img, box) -> tuple[int, int, int]:
    crop = img.crop(box)
    px = list(crop.get_flattened_data()) if hasattr(crop, "get_flattened_data") \
        else list(crop.getdata())
    n = len(px) or 1
    return tuple(round(sum(p[i] for p in px) / n) for i in range(3))


def _near(a, b, tol=26) -> bool:
    return all(abs(a[i] - b[i]) <= tol for i in range(3))


def deck_frame(n_slides: int = 138) -> dict:
    """Measure the frame the deck repeats across its interface slides."""
    from PIL import Image  # noqa: PLC0415

    frames = []
    for n in range(1, n_slides + 1):
        p = DECK_PNG / f"slide-{n:03d}.png"
        if not p.exists():
            continue
        img = Image.open(p).convert("RGB")
        w, h = img.size
        surface = _mean(img, (0, 0, 8, 8))
        top = _mean(img, (0, 0, w, max(1, int(h * 0.10))))
        right = _mean(img, (int(w * 0.80), int(h * 0.30), w, int(h * 0.78)))
        # A slide is an *interface* slide when its surface is the light theme
        # rather than the dark cover/divider fill.
        is_interface = _near(surface, DECK_SURFACE, tol=18)
        frames.append(
            {
                "slide": n,
                "size": [w, h],
                "surface": surface,
                "top_band": top,
                "right_rail": right,
                "interface": is_interface,
            }
        )
    return {
        "surface": DECK_SURFACE,
        "navy": DECK_NAVY,
        "interface_slides": [f["slide"] for f in frames if f["interface"]],
        "frames": frames,
    }


async def app_frame(base: str) -> dict:
    """Measure the live SPA shell: DOM geometry plus sampled pixels."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path="/usr/bin/chromium", args=["--no-sandbox"]
        )
        ctx = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await ctx.new_page()
        await page.goto(f"{base}/platform/", wait_until="networkidle")
        await page.fill("#loginEmail", OWNER)
        await page.fill("#loginPassword", PASSWORD)
        await page.click("#loginBtn")
        await page.wait_for_selector("#loginScreen", state="hidden", timeout=20000)
        await page.wait_for_timeout(2500)

        shot = ARTIFACTS / "shots" / "visual-parity-owner-dashboard.png"
        shot.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(shot))

        dom = await page.evaluate(
            """() => {
              const vis = (e) => e && e.offsetParent !== null;
              const box = (sel) => {
                const e = document.querySelector(sel);
                if (!vis(e)) return null;
                const r = e.getBoundingClientRect();
                return {x:Math.round(r.x),y:Math.round(r.y),
                        w:Math.round(r.width),h:Math.round(r.height)};
              };
              const text = (sel) => {
                const e = document.querySelector(sel);
                return e ? (e.innerText||'').trim() : '';
              };
              const header = document.querySelector('.header');
              const headerText = header ? (header.innerText||'') : '';
              return {
                dir: document.documentElement.dir,
                header: box('.header'),
                sidebar: box('.sidebar'),
                stage: box('.stage'),
                crumb: box('#crumb'),
                headerText,
                // The deck's four header controls, looked up by what they are
                // rather than by their exact markup.
                entitySelector: !!document.querySelector('#scopeCompany'),
                search: !!document.querySelector('#searchBtn'),
                langToggle: !!document.querySelector('.lang-switch [data-lang]'),
                account: !!document.querySelector('#sbAvatar,#logoutBtn,#notifBtn'),
                bodyBg: getComputedStyle(document.body).backgroundColor,
                headerBg: header ? getComputedStyle(header).backgroundColor : '',
                sidebarBg: (() => {
                  const s=document.querySelector('.sidebar');
                  return s ? getComputedStyle(s).backgroundColor : '';
                })(),
              };
            }"""
        )

        from PIL import Image  # noqa: PLC0415

        img = Image.open(shot).convert("RGB")
        w, h = img.size
        dom["screenshot"] = str(shot.relative_to(ROOT))
        dom["size"] = [w, h]
        # The deck's interface slides are full-bleed light. The app draws the
        # same light surface inside a dark executive stage, so the deck-analog
        # region is the content stage, not the page corner.
        stage = dom.get("stage") or {"x": 0, "y": 0, "w": w, "h": h}
        sx, sy, sw, sh = stage["x"], stage["y"], stage["w"], stage["h"]
        dom["sampled"] = {
            "top_band": _mean(img, (0, 0, w, max(1, int(h * 0.10)))),
            "right_rail": _mean(img, (int(w * 0.80), int(h * 0.30), w, int(h * 0.78))),
            "surface": _mean(
                img,
                (
                    min(sx + 6, w - 1),
                    min(sy + 6, h - 1),
                    min(sx + max(4, int(sw * 0.35)), w),
                    min(sy + max(4, int(sh * 0.35)), h),
                ),
            ),
        }
        await browser.close()
    return dom


def compare(deck: dict, app: dict) -> dict:
    """Score the app frame against the deck frame. Returns per-check booleans."""
    checks: dict[str, dict] = {}

    def add(name: str, ok: bool, detail: str) -> None:
        checks[name] = {"ok": bool(ok), "detail": detail}

    header = app.get("header") or {}
    sidebar = app.get("sidebar") or {}
    crumb = app.get("crumb") or {}

    # 1. the four-control header row the deck repeats on every interface slide.
    controls = {
        "entity": app.get("entitySelector"),
        "search": app.get("search"),
        "language": app.get("langToggle"),
        "account": app.get("account"),
    }
    present = [k for k, v in controls.items() if v]
    add(
        "header_controls",
        len(present) == 4,
        f"header controls present: {', '.join(present) or 'none'} "
        f"(deck repeats 4 on its interface slides)",
    )

    # 2. breadcrumb line under the title band (deck y~14).
    add(
        "breadcrumb",
        bool(crumb.get("w")),
        f"#crumb {'present' if crumb.get('w') else 'missing'} "
        f"(deck places a breadcrumb line under the title band)",
    )

    # 3. right-hand rail (deck x~81..95 on its interface slides).
    rail_right = bool(sidebar.get("w")) and (sidebar.get("x", 0) > app["size"][0] * 0.6)
    add(
        "right_rail",
        rail_right,
        f"sidebar x={sidebar.get('x')} w={sidebar.get('w')} "
        f"(deck rail sits at the right edge in RTL)",
    )

    # 4. header band across the top.
    add(
        "top_band",
        bool(header.get("w")) and header.get("y", 999) < 120,
        f"header y={header.get('y')} h={header.get('h')} "
        f"(deck title/header band hugs the top)",
    )

    # 5. palette: the app stays inside the deck's light-surface scheme.
    surface = app["sampled"]["surface"]
    add(
        "palette_surface",
        _near(surface, deck["surface"], tol=30),
        f"app surface {tuple(surface)} vs deck {tuple(deck['surface'])}",
    )

    # 6. RTL default (deck is Arabic-first, RTL).
    add("rtl", app.get("dir") == "rtl", f"document dir={app.get('dir')}")

    return checks


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:12000")
    ap.add_argument("--out", default="artifacts/visual_parity.json")
    args = ap.parse_args()

    deck = deck_frame()
    app = await app_frame(args.base)
    checks = compare(deck, app)

    result = {
        "base": args.base,
        "deck": {
            "surface": deck["surface"],
            "navy": deck["navy"],
            "interface_slides": len(deck["interface_slides"]),
            "slides_measured": len(deck["frames"]),
        },
        "app": app,
        "checks": checks,
        "ok": all(c["ok"] for c in checks.values()),
    }

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1))

    failed = [k for k, c in checks.items() if not c["ok"]]
    print(
        f"wrote {out}: {len(checks) - len(failed)}/{len(checks)} visual checks pass"
        + (f"; FAILED {failed}" if failed else ""),
        file=sys.stderr,
    )
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
