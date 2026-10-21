"""Draw the 1200×630 link-preview image of one FundsXML release page.

Same look as ``frontend/public/og-image.png``: dark slate, sky accent, Manrope
(SIL Open Font License, vendored in ``tools/fonts/`` so every machine draws the
same pixels). Used by ``build_fundsxml_pages.py``; needs Pillow (dev extra).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = Path(__file__).resolve().parent / "fonts"
WIDTH, HEIGHT = 1200, 630
BG = "#0f172a"
ACCENT = "#38bdf8"
TEXT = "#f8fafc"
MUTED = "#94a3b8"
BOX = "#1e293b"
LEFT = 90


@dataclass(frozen=True)
class Stat:
    value: str
    label: str


def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / f"Manrope-{weight}.ttf"), size)


def _fit(draw: ImageDraw.ImageDraw, text: str, weight: str, size: int, width: int) -> ImageFont.FreeTypeFont:
    """The largest font up to ``size`` in which ``text`` fits ``width`` pixels."""
    while size > 12 and draw.textlength(text, font=_font(weight, size)) > width:
        size -= 1
    return _font(weight, size)


def render(path: Path, tag: str, subtitle: str, stats: list[Stat], footer: str) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 18, HEIGHT), fill=ACCENT)
    inner = WIDTH - 2 * LEFT

    draw.text((LEFT, 62), "FundsXML schema release", font=_font("Regular", 32), fill=ACCENT)
    draw.text((LEFT, 112), f"FundsXML {tag}", font=_fit(draw, f"FundsXML {tag}", "Bold", 96, inner), fill=TEXT)
    draw.text((LEFT, 240), subtitle, font=_fit(draw, subtitle, "Regular", 36, inner), fill=MUTED)

    gap = 24
    box_w = (inner - gap * (len(stats) - 1)) // len(stats)
    top, bottom = 330, 500
    for i, stat in enumerate(stats):
        x = LEFT + i * (box_w + gap)
        draw.rounded_rectangle((x, top, x + box_w, bottom), radius=10, fill=BOX, outline=ACCENT, width=2)
        draw.text((x + 24, top + 28), stat.value, font=_fit(draw, stat.value, "Bold", 64, box_w - 48), fill=TEXT)
        draw.text((x + 24, top + 112), stat.label, font=_fit(draw, stat.label, "Regular", 26, box_w - 48), fill=MUTED)

    draw.text((LEFT, 560), footer, font=_font("Regular", 34), fill=ACCENT)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Flat colours and anti-aliased text: 64 colours look the same at a third of the size.
    image.quantize(64).save(path, optimize=True)
