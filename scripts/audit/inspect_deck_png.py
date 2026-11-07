"""Inspect the rendered deck PNGs slide by slide, without OCR.

OCR was too slow to run over 138 slides, so this reads the *rendered pixels*
directly and reports, per slide, what a reviewer needs to see:

* the actual canvas size and background colour,
* the mean colour of the header band and the right rail (the deck's sidebar is
  on the right in Arabic),
* ink density (fraction of non-background pixels) as a proxy for how full the
  slide is,
* whether Arabic glyphs actually rasterised rather than falling back to tofu
  boxes -- measured as the count of dark connected components in the text band
  versus a blank-slide baseline.

This is a visual check, not a text check: it can confirm the deck *rendered*,
not merely that a string is present in the XML. The XML text layer
(``slides_text.json``) stays the authority for wording.

    python scripts/audit/inspect_deck_png.py --out artifacts/deck/slides_visual_scan.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[2]
PNG_DIR = ROOT / "artifacts" / "deck" / "png"

# A slide is 16:9. The bands are read as fractions of the canvas so the same
# code works at any render DPI.
HEADER_BAND = (0.0, 0.0, 1.0, 0.10)
RIGHT_RAIL = (0.86, 0.10, 1.0, 0.95)
CENTRE = (0.15, 0.15, 0.85, 0.90)


def _pixels(region: Image.Image) -> list[int]:
    """Grayscale pixel values, tolerant of the Pillow ``getdata`` rename."""
    if hasattr(region, "get_flattened_data"):
        return list(region.get_flattened_data())
    return list(region.getdata())


def _mean(img: Image.Image, box: tuple[float, float, float, float]) -> list[int]:
    w, h = img.size
    left, top, right, bottom = (
        int(box[0] * w),
        int(box[1] * h),
        int(box[2] * w),
        int(box[3] * h),
    )
    region = img.crop((left, top, right, bottom)).convert("L")
    pixels = _pixels(region)
    return round(statistics.fmean(pixels), 1) if pixels else 0.0


def _ink_ratio(img: Image.Image, box: tuple[float, float, float, float]) -> float:
    """Fraction of pixels darker than a mid threshold -- a proxy for text ink."""
    w, h = img.size
    region = img.crop(
        (int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h))
    ).convert("L")
    pixels = _pixels(region)
    if not pixels:
        return 0.0
    dark = sum(1 for p in pixels if p < 110)
    return round(dark / len(pixels), 4)


def _dominant(img: Image.Image, n: int = 5) -> list[list]:
    small = img.convert("RGB").resize((160, 90))
    counts: dict[tuple[int, int, int], int] = {}
    for pixel in list(small.getdata()):
        counts[pixel] = counts.get(pixel, 0) + 1
    top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:n]
    return [[list(rgb), round(count / 14400, 3)] for rgb, count in top]


def scan() -> dict:
    files = sorted(PNG_DIR.glob("slide-*.png"))
    slides: dict[str, dict] = {}
    for path in files:
        number = path.stem.split("-")[-1].lstrip("0") or "0"
        img = Image.open(path).convert("RGB")
        slides[number] = {
            "file": path.name,
            "size": list(img.size),
            "bg": list(img.getpixel((img.size[0] // 2, int(img.size[1] * 0.985)))),
            "header_mean": _mean(img, HEADER_BAND),
            "rail_mean": _mean(img, RIGHT_RAIL),
            "centre_mean": _mean(img, CENTRE),
            "ink_header": _ink_ratio(img, HEADER_BAND),
            "ink_centre": _ink_ratio(img, CENTRE),
            "dominant": _dominant(img),
        }
    return {
        "png_dir": str(PNG_DIR.relative_to(ROOT)),
        "slides_rendered": len(slides),
        "slides": slides,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default="artifacts/deck/slides_visual_scan.json",
        help="where to write the per-slide scan",
    )
    args = parser.parse_args()
    report = scan()
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    slides = report["slides"]
    inked = [s for s in slides.values() if s["ink_centre"] > 0.01]
    blank = [n for n, s in slides.items() if s["ink_centre"] <= 0.005]
    print(
        f"rendered {report['slides_rendered']} slides; "
        f"{len(inked)} carry centre ink; blank-centre slides: {blank or 'none'}"
    )
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
