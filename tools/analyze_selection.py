"""Measure how the highlighted menu entry differs from the rest.

Across every menu in Street Fighter V the selected entry is drawn as a near
black bar with gold text, while the others sit on a light background with dark
text.  This prints the numbers behind that so the thresholds are chosen from
evidence rather than guessed.
"""

import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access import ocr  # noqa: E402

SNAPS = ROOT / "snapshots"


def luminance(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


def side_bands(rgb: np.ndarray, item, pad: int = 55, gap: int = 12):
    """Pixels immediately left and right of the glyphs, inside the same row."""
    h, w = rgb.shape[:2]
    y0, y1 = int(max(0, item.y)), int(min(h, item.y + item.h))
    if y1 <= y0:
        return None
    lx0, lx1 = int(max(0, item.x - gap - pad)), int(max(0, item.x - gap))
    rx0, rx1 = int(min(w, item.x + item.w + gap)), int(min(w, item.x + item.w + gap + pad))
    parts = []
    if lx1 > lx0:
        parts.append(rgb[y0:y1, lx0:lx1])
    if rx1 > rx0:
        parts.append(rgb[y0:y1, rx0:rx1])
    if not parts:
        return None
    return np.concatenate([p.reshape(-1, 3) for p in parts], axis=0)


def goldness(rgb: np.ndarray, item) -> float:
    """How gold the brightest glyph pixels are: positive means gold, not white."""
    h, w = rgb.shape[:2]
    y0, y1 = int(max(0, item.y)), int(min(h, item.y + item.h))
    x0, x1 = int(max(0, item.x)), int(min(w, item.x + item.w))
    if y1 <= y0 or x1 <= x0:
        return 0.0
    box = rgb[y0:y1, x0:x1].reshape(-1, 3).astype(np.float32)
    lum = luminance(box)
    bright = box[lum >= np.percentile(lum, 92)]
    if bright.size == 0:
        return 0.0
    r, g, b = bright[:, 0].mean(), bright[:, 1].mean(), bright[:, 2].mean()
    return float((r + g) / 2 - b)


def main() -> None:
    stems = sys.argv[1:]
    files = [SNAPS / f"{s}.png" for s in stems] if stems else sorted(SNAPS.glob("*.png"))
    for png in files:
        rgb = np.asarray(Image.open(png).convert("RGB"))
        bgra = np.dstack([rgb[..., ::-1], np.full(rgb.shape[:2], 255, np.uint8)])
        items = ocr.reading_order(ocr.read(np.ascontiguousarray(bgra)))
        if not items:
            continue
        print(f"===== {png.stem} =====")
        print(f"{'bg med':>7} {'bg p90':>7} {'gold':>6}  text")
        for it in items:
            band = side_bands(rgb, it)
            if band is None:
                continue
            lum = luminance(band.astype(np.float32))
            print(
                f"{np.median(lum):7.0f} {np.percentile(lum, 90):7.0f} "
                f"{goldness(rgb, it):6.0f}  {it.text[:58]}"
            )
        print()


if __name__ == "__main__":
    main()
