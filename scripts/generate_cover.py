#!/usr/bin/env python3
"""
Generate the podcast cover image at docs/cover.png (1400×1400, sRGB).

Required by Apple Podcasts and recommended by Spotify. The RSS feed
references this image via <itunes:image href="..."/>. The Cover is hosted
on GitHub Pages alongside the feed itself, so it's available at:
    https://tnvsh0.github.io/psychiatry-weekly-review/cover.png

Run once (and any time the design needs to change):
    python scripts/generate_cover.py
Then commit `docs/cover.png` so GitHub Pages can serve it.

Design:
  * Deep blue gradient background (top darker, bottom lighter)
  * Stylised brain motif (concentric soft circles, neuron-like)
  * Hebrew title in three layers
  * Small AI-disclosure tagline at the bottom
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:
    print("ERROR: Pillow not installed. pip install Pillow")
    sys.exit(2)

# python-bidi handles the Unicode bidirectional algorithm so Hebrew renders
# right-to-left even though PIL's text engine is LTR-only.
try:
    from bidi.algorithm import get_display
except ImportError:
    print("ERROR: python-bidi not installed. pip install python-bidi")
    sys.exit(2)


def heb(s: str) -> str:
    """Reorder Hebrew (or mixed) text for visually-correct LTR rendering."""
    return get_display(s)


# ── Layout constants ──────────────────────────────────────────────────────────
SIZE = 1400               # square output
TOP_COLOR = (10, 28, 56)  # deep navy
MID_COLOR = (24, 64, 110) # mid blue
BOT_COLOR = (40, 100, 150)  # ocean blue
ACCENT_GOLD = (212, 175, 55)
TEXT_WHITE = (255, 255, 255)
TEXT_MUTED = (180, 195, 215)

# Font search paths — first match wins
FONT_CANDIDATES_BOLD = [
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]
FONT_CANDIDATES_REGULAR = [
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf",
]


def _find_font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    for p in candidates:
        if os.path.exists(p):
            return ImageFont.truetype(p, size=size)
    raise FileNotFoundError(
        f"No suitable font found in: {candidates}. "
        "Install DejaVu Sans or run on a system with Segoe/Arial."
    )


def _gradient_background() -> Image.Image:
    """Vertical three-stop gradient: TOP_COLOR → MID_COLOR → BOT_COLOR."""
    img = Image.new("RGB", (SIZE, SIZE), TOP_COLOR)
    px = img.load()
    half = SIZE // 2
    for y in range(SIZE):
        if y < half:
            t = y / half  # 0..1
            r = int(TOP_COLOR[0] + (MID_COLOR[0] - TOP_COLOR[0]) * t)
            g = int(TOP_COLOR[1] + (MID_COLOR[1] - TOP_COLOR[1]) * t)
            b = int(TOP_COLOR[2] + (MID_COLOR[2] - TOP_COLOR[2]) * t)
        else:
            t = (y - half) / half
            r = int(MID_COLOR[0] + (BOT_COLOR[0] - MID_COLOR[0]) * t)
            g = int(MID_COLOR[1] + (BOT_COLOR[1] - MID_COLOR[1]) * t)
            b = int(MID_COLOR[2] + (BOT_COLOR[2] - MID_COLOR[2]) * t)
        for x in range(SIZE):
            px[x, y] = (r, g, b)
    return img


def _brain_glyph(img: Image.Image) -> None:
    """Soft concentric circles + branching lines, evoking neural tissue."""
    draw = ImageDraw.Draw(img, "RGBA")
    cx, cy = SIZE // 2, SIZE // 2

    # Layered translucent circles (large, subtle)
    for radius, alpha in [(600, 18), (520, 24), (440, 32), (360, 40), (280, 48)]:
        draw.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            outline=(255, 255, 255, alpha),
            width=3,
        )

    # Branching neuron-like strokes radiating from center
    import math
    rng_seed = [
        (0.3, 0.85), (0.7, 0.9), (1.1, 0.95), (1.5, 0.85),
        (1.9, 0.92), (2.3, 0.88), (2.7, 0.95), (3.1, 0.85),
        (3.5, 0.9), (3.9, 0.95), (4.3, 0.88), (4.7, 0.9),
        (5.1, 0.85), (5.5, 0.92), (5.9, 0.88),
    ]
    for theta, len_frac in rng_seed:
        x1 = cx + int(60 * math.cos(theta))
        y1 = cy + int(60 * math.sin(theta))
        x2 = cx + int(620 * len_frac * math.cos(theta))
        y2 = cy + int(620 * len_frac * math.sin(theta))
        draw.line([(x1, y1), (x2, y2)], fill=(255, 255, 255, 25), width=2)
        # Tiny dot at the end (synapse-like)
        draw.ellipse([x2 - 5, y2 - 5, x2 + 5, y2 + 5], fill=(212, 175, 55, 80))


def _draw_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    y: int,
    color: tuple,
    shadow: bool = False,
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    x = (SIZE - text_w) // 2 - bbox[0]
    if shadow:
        draw.text((x + 4, y + 4), text, font=font, fill=(0, 0, 0, 120))
    draw.text((x, y), text, font=font, fill=color)


def render() -> Image.Image:
    img = _gradient_background()
    _brain_glyph(img)

    # Soft vignette — subtle dark edges
    vignette = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    vdraw = ImageDraw.Draw(vignette)
    vdraw.ellipse(
        [-SIZE // 3, -SIZE // 3, SIZE + SIZE // 3, SIZE + SIZE // 3],
        outline=(0, 0, 0, 0),
        width=0,
    )
    img = img.convert("RGBA")

    # Type
    draw = ImageDraw.Draw(img)
    title_font  = _find_font(FONT_CANDIDATES_BOLD, 150)
    title_font2 = _find_font(FONT_CANDIDATES_BOLD, 130)
    sub_font    = _find_font(FONT_CANDIDATES_BOLD,  85)
    en_font     = _find_font(FONT_CANDIDATES_REGULAR, 52)
    tag_font    = _find_font(FONT_CANDIDATES_REGULAR, 38)

    # Title (Hebrew): two lines for visual weight. heb() reorders for RTL.
    _draw_centered(draw, heb("סקירה שבועית"),  title_font,  280, TEXT_WHITE, shadow=True)
    _draw_centered(draw, heb("בפסיכיאטריה"),    title_font2, 460, TEXT_WHITE, shadow=True)

    # Accent line
    line_y = 640
    draw.line([(SIZE // 2 - 220, line_y), (SIZE // 2 + 220, line_y)],
              fill=ACCENT_GOLD, width=6)

    # Hebrew subtitle (gold)
    _draw_centered(draw, heb("ילד ומתבגר"), sub_font, 680, ACCENT_GOLD)

    # English subtitle (muted)
    _draw_centered(draw, "Weekly Psychiatry Review",  en_font, 830, TEXT_MUTED)
    _draw_centered(draw, "Child & Adolescent Edition", en_font, 900, TEXT_MUTED)

    # AI disclosure — small, at the bottom
    _draw_centered(
        draw,
        "AI-generated content · always verify against sources",
        tag_font, 1280, TEXT_MUTED,
    )

    return img.convert("RGB")


def main() -> int:
    out_dir = Path(__file__).resolve().parent.parent / "docs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "cover.png"

    img = render()
    img.save(out_path, format="PNG", optimize=True)
    size_kb = out_path.stat().st_size / 1024
    print(f"Wrote {out_path}  ({SIZE}×{SIZE}, {size_kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
