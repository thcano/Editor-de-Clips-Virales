"""Genera el icono .ico del ejecutable a partir de un dibujo simple.

Uso:
    .venv\\Scripts\\python.exe packaging\\make_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

OUTPUT = Path(__file__).resolve().parent / "viralclip.ico"

BG = (15, 23, 42, 255)
PANEL = (30, 41, 59, 255)
ACCENT = (34, 211, 238, 255)
LIGHT = (226, 232, 240, 255)
SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def build_icon(size: int = 256) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    scale = size / 256

    def box(left: float, top: float, right: float, bottom: float) -> tuple[int, int, int, int]:
        return (
            round(left * scale),
            round(top * scale),
            round(right * scale),
            round(bottom * scale),
        )

    draw.rounded_rectangle(box(8, 8, 248, 248), radius=round(48 * scale), fill=BG)
    draw.rounded_rectangle(box(24, 56, 232, 200), radius=round(28 * scale), fill=PANEL)
    draw.polygon(
        [
            (round(104 * scale), round(88 * scale)),
            (round(104 * scale), round(168 * scale)),
            (round(176 * scale), round(128 * scale)),
        ],
        fill=ACCENT,
    )
    draw.rounded_rectangle(box(44, 72, 52, 184), radius=round(4 * scale), fill=LIGHT)
    draw.rounded_rectangle(box(204, 72, 212, 184), radius=round(4 * scale), fill=LIGHT)
    return image


def main() -> int:
    image = build_icon()
    image.save(OUTPUT, format="ICO", sizes=SIZES)
    print(f"Icono generado: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
