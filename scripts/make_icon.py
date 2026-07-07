"""Генерация иконки atomspectra-waterfall-esp32 (256x256 PNG → .ico)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)


VIRIDIS = [(68, 1, 84), (72, 40, 120), (62, 74, 137), (49, 104, 142),
           (38, 130, 142), (31, 158, 137), (53, 183, 121), (109, 205, 89),
           (180, 222, 44), (253, 231, 37)]


def _color(t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    p = t * (len(VIRIDIS) - 1)
    i = int(p)
    f = p - i
    j = min(i + 1, len(VIRIDIS) - 1)
    a, b = VIRIDIS[i], VIRIDIS[j]
    return (int(a[0] + (b[0] - a[0]) * f),
            int(a[1] + (b[1] - a[1]) * f),
            int(a[2] + (b[2] - a[2]) * f))


def _intensity(x: float, r: float) -> float:
    peaks = [(0.28, 0.05, 1.0), (0.55, 0.04, 0.85), (0.78, 0.03, 0.6)]
    val = 0.05
    drift = 0.02 * (r - 0.5)
    for cx, sig, amp in peaks:
        d = (x - (cx + drift)) / sig
        val += amp * pow(2.71828, -0.5 * d * d)
    return min(1.0, val)


def _paint_waterfall(img: Image.Image) -> None:
    W, H = img.size
    px = img.load()
    for y in range(H):
        r = y / (H - 1)
        for x in range(W):
            t = _intensity(x / (W - 1), r)
            c = _color(t)
            px[x, y] = (c[0], c[1], c[2], 255)


def _frame(img: Image.Image) -> None:
    W, H = img.size
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W - 1, H - 1), outline=(20, 30, 50, 255), width=3)


def main() -> None:
    base = Image.new("RGBA", (256, 256))
    _paint_waterfall(base)
    _frame(base)
    png = ASSETS / "icon.png"
    ico = ASSETS / "icon.ico"
    base.save(png, "PNG")
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
             (128, 128), (256, 256)]
    base.save(ico, sizes=sizes)
    print(f"PNG: {png}")
    print(f"ICO: {ico}")


if __name__ == "__main__":
    main()
