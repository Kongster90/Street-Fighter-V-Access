"""Show every gold band the reader considers on a screen, and why one wins.

    python tools/show_bands.py <snapshot-stem>
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access import menu, ocr  # noqa: E402

SNAPS = ROOT / "snapshots"


def main() -> None:
    stem = sys.argv[1]
    matches = sorted(SNAPS.glob(f"*{stem}*.png"))
    if not matches:
        raise SystemExit(f"no snapshot matching {stem}")
    path = matches[0]

    rgb = np.asarray(Image.open(path).convert("RGB"))
    bgra = np.ascontiguousarray(
        np.dstack([rgb[..., ::-1], np.full(rgb.shape[:2], 255, np.uint8)])
    )
    width = rgb.shape[1]

    raw = menu.gold_bands(rgb)
    print(f"{path.name}: {len(raw)} bands before filtering\n")
    print(f"{'y':>12} {'x':>12} {'px':>7} {'dens':>5} {'bar':>5} {'edge':>5}  text")
    for band in sorted(raw, key=lambda b: -b.pixels):
        at_edge = band.left < menu.EDGE_MARGIN or band.right > width - menu.EDGE_MARGIN
        items = ocr.read(menu.strip(bgra, band))
        text = " ".join(i.text for i in items).strip()
        print(
            f"{band.top:5d}-{band.bottom:<6d} {band.left:5d}-{band.right:<6d} "
            f"{band.pixels:7d} {band.density:5.2f} "
            f"{menu.bar_width(rgb, band):5d} {'yes' if at_edge else 'no':>5}  {text!r}"
        )

    chosen = menu.highlight_band(rgb, bgra)
    if chosen is None:
        print("\nchosen: none")
        return
    items = ocr.read(menu.strip(bgra, chosen))
    print(
        f"\nchosen: y {chosen.top}-{chosen.bottom} x {chosen.left}-{chosen.right} "
        f"-> {' '.join(i.text for i in items)!r}"
    )


if __name__ == "__main__":
    main()
