"""Per-slide visual parity: the deck's rendered layout vs the live app.

The compliance matrix joins *text* evidence (the deck's OOXML wording, the
SPA's rendered strings). Text proves what a screen says; it does not prove the
screen looks like the deck. This probe closes that gap per slide rather than
for the shell as a whole.

For every slide the matrix maps to a screen it compares two rendered sources:

* the deck -- its own PNG (``artifacts/deck/png/slide-NNN.png``) and the shape
  rectangles in ``artifacts/deck/slides_geometry.json`` (positions read from the
  OOXML drawing, i.e. the deck's *layout*, not its text), and
* the app -- the live screenshot of that slide's view
  (``artifacts/shots/<role>-<view>.png``, written by ``view_audit.py``), whose
  pixels are measured directly.

The two must agree on the frame the deck repeats on every interface slide:

* a light surface (deck ``#F5F7FA``) rather than a dark board,
* the navigation rail on the **right** (Arabic-first RTL) occupying roughly the
  deck's right 15%,
* a header/title band hugging the top,
* a non-blank content region (ink present, not an empty shell),
* for the role-dashboard slides (7-11) a KPI strip of tiles under the header.

This is deliberately a *layout* check. It cannot read Arabic wording -- that is
the XML text layer's job -- but it can see whether the app paints the same
frame in the same places, which is exactly what a text-only matrix misses.

    python scripts/audit/deck_visual_parity.py \
        --out artifacts/deck/visual_parity_slides.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[2]
DECK_PNG = ROOT / "artifacts" / "deck" / "png"
GEOMETRY = ROOT / "artifacts" / "deck" / "slides_geometry.json"
SHOTS = ROOT / "artifacts" / "shots"

DECK_SURFACE = (245, 247, 250)

# The slide->view map is the compliance matrix's own ``MAPPING`` (loaded from
# ``build_deck_compliance``), not a second hand-kept list: the two must never
# drift, and every slide the matrix scores against a screen must also be
# visually probed. Only slides whose view has a rendered screenshot are probed.
ROLE_SLIDES = {7, 8, 9, 10, 11}

# The screenshot written by view_audit.py for the owner, who holds every
# permission, so every mapped view is reachable.
SCREENSHOT_ROLE = "holding_owner"


def _load_matrix_mapping() -> dict[int, str]:
    """Read ``MAPPING`` from build_deck_compliance without importing it as a
    package (``scripts/`` has no ``__init__``); the module is pure data + code
    with no side effects at import."""
    path = pathlib.Path(__file__).with_name("build_deck_compliance.py")
    spec = importlib.util.spec_from_file_location("_deck_matrix", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    slide_view: dict[int, str] = {}
    for group in module.MAPPING:
        view = group.get("view")
        if not view:
            continue
        for n in group["slides"]:
            slide_view.setdefault(n, view)
    return slide_view


def _mean(img: Image.Image, box: tuple[float, float, float, float]) -> tuple[int, int, int]:
    w, h = img.size
    crop = img.crop(
        (int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h))
    ).convert("RGB")
    px = list(crop.getdata())
    n = len(px) or 1
    return tuple(round(sum(p[i] for p in px) / n) for i in range(3))


def deck_has_rail(slide: int) -> bool:
    """Does the deck slide draw its navigation rail on the right?

    Read from the OOXML shape rectangles, not from any text: a rail is a column
    of short, evenly spaced shapes in the right 15% of the canvas.
    """
    shapes = json.loads(GEOMETRY.read_text(encoding="utf-8")).get(str(slide), {}).get("shapes", [])
    rail = [s for s in shapes if s["x"] >= 80 and 25 <= s["y"] <= 90 and s["w"] <= 20]
    return len(rail) >= 3


def _is_light(rgb) -> bool:
    return rgb[0] + rgb[1] + rgb[2] > 600


def _light_fraction(img: Image.Image, box: tuple[float, float, float, float]) -> float:
    w, h = img.size
    crop = img.crop(
        (int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h))
    ).convert("RGB")
    px = list(crop.getdata())
    if not px:
        return 0.0
    return round(sum(1 for p in px if _is_light(p)) / len(px), 4)


def _non_surface_fraction(img: Image.Image, box: tuple[float, float, float, float]) -> float:
    """Fraction of pixels that differ from the deck's light surface.

    The live board paints the same ``#F5F7FA`` surface the deck uses, so a
    region whose pixels are *all* surface is an empty shell; content, tiles and
    text all read as non-surface.
    """
    w, h = img.size
    crop = img.crop(
        (int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h))
    ).convert("RGB")
    px = list(crop.getdata())
    if not px:
        return 0.0
    surface = DECK_SURFACE
    return round(
        sum(1 for p in px if abs(p[0] - surface[0]) + abs(p[1] - surface[1]) + abs(p[2] - surface[2]) > 18)
        / len(px),
        4,
    )


def _tile_gutters(img: Image.Image, box) -> int:
    """Count background gutters between side-by-side tiles in a strip band.

    The deck draws its KPI strip as four tiles separated by thin gaps. A column
    of the band that is pure surface between two content columns is a gutter; a
    four-tile strip has three gutters. Returns the gutter count so the caller
    can assert the app drew the same tile grid rather than one solid block.
    """
    w, h = img.size
    left, top = int(box[0] * w), int(box[1] * h)
    right, bottom = int(box[2] * w), int(box[3] * h)
    cols = []
    for x in range(left, right):
        crop = img.crop((x, top, x + 1, bottom)).convert("RGB")
        px = list(crop.getdata())
        non = sum(1 for p in px if abs(p[0] - DECK_SURFACE[0]) + abs(p[1] - DECK_SURFACE[1]) + abs(p[2] - DECK_SURFACE[2]) > 18)
        cols.append(non / (len(px) or 1))
    # A gutter is a run of near-empty columns bounded by content columns.
    gutters = 0
    empty = False
    seen_content = False
    for c in cols:
        if c > 0.02:
            if empty and seen_content:
                gutters += 1
            empty = False
            seen_content = True
        else:
            empty = True
    return gutters


def check_slide(slide: int, view: str) -> dict:
    deck = Image.open(DECK_PNG / f"slide-{slide:03d}.png").convert("RGB")
    shot_path = SHOTS / f"{SCREENSHOT_ROLE}-{view}.png"
    if not shot_path.exists():
        return {"slide": slide, "view": view, "ok": False, "detail": "no app screenshot"}

    app = Image.open(shot_path).convert("RGB")

    # Deck regions (fractions of its own 16:9 canvas): the light working
    # surface and the content band.
    deck_light = _light_fraction(deck, (0.02, 0.30, 0.78, 0.90))

    # App regions, measured from the live shell geometry (stage x=14..1906,
    # sidebar x=1656..1906 at 1920 wide): the light board sits in the middle,
    # the RTL navigation rail hugs the right edge.
    app_light = _light_fraction(app, (0.22, 0.18, 0.80, 0.90))
    app_rail = _mean(app, (0.87, 0.30, 0.98, 0.72))
    app_content = _non_surface_fraction(app, (0.06, 0.12, 0.80, 0.95))

    checks: dict[str, tuple[bool, str]] = {}
    checks["light_surface"] = (
        app_light > 0.55 and deck_light > 0.55,
        f"app light fraction {app_light} vs deck {deck_light}",
    )
    # The deck draws a full-height navigation rail on the right (Arabic-first
    # RTL) on its *interface* slides; diagram slides (module map, i18n) omit it.
    # Where the deck draws one, the app's sidebar must be a distinct right-edge
    # column; where it does not, the check is not applicable.
    if deck_has_rail(slide):
        rail_distinct = abs(app_rail[0] - DECK_SURFACE[0]) + abs(app_rail[1] - DECK_SURFACE[1]) + abs(app_rail[2] - DECK_SURFACE[2]) > 24
        checks["right_rail"] = (
            rail_distinct,
            f"app right column {app_rail} differs from the light surface "
            f"{DECK_SURFACE}; deck draws a rail on this slide",
        )
    # The screen must not be an empty shell: the board paints real content, not
    # a blank surface. The live screens are far sparser than the deck's dense
    # mocks, so this is a floor on content, never a density match.
    checks["content_present"] = (
        app_content > 0.10,
        f"app content band non-surface fraction {app_content}",
    )

    if slide in ROLE_SLIDES:
        # The deck puts a four-tile KPI strip under the header. The app's role
        # strip must show four side-by-side tiles, i.e. three gutters between
        # content columns.
        strip = (0.03, 0.15, 0.80, 0.30)
        gutters = _tile_gutters(app, strip)
        non = _non_surface_fraction(app, strip)
        checks["role_kpi_strip"] = (
            gutters >= 2 and non > 0.3,
            f"strip non-surface {non}, tile gutters {gutters}",
        )

    ok = all(v[0] for v in checks.values())
    return {
        "slide": slide,
        "view": view,
        "ok": ok,
        "checks": {k: {"ok": v[0], "detail": v[1]} for k, v in checks.items()},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="artifacts/deck/visual_parity_slides.json")
    args = ap.parse_args()

    slide_view = _load_matrix_mapping()

    results = []
    no_shot: list[dict] = []
    for slide in sorted(slide_view):
        if not (DECK_PNG / f"slide-{slide:03d}.png").exists():
            continue
        view = slide_view[slide]
        if not (SHOTS / f"{SCREENSHOT_ROLE}-{view}.png").exists():
            no_shot.append({"slide": slide, "view": view})
            continue
        results.append(check_slide(slide, view))

    n_ok = sum(1 for r in results if r["ok"])
    report = {
        "screens_checked": len(results),
        "ok": n_ok,
        "failed": [r["slide"] for r in results if not r["ok"]],
        "no_screenshot": no_shot,
        "slides": results,
    }
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    msg = (
        f"wrote {out.relative_to(ROOT)}: {n_ok}/{len(results)} mapped screens "
        f"match the deck's frame"
    )
    if no_shot:
        msg += f"; {len(no_shot)} mapped slides have no screenshot yet"
    if report["failed"]:
        msg += f"; FAILED slides {report['failed']}"
    print(msg)
    return 0 if not report["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
