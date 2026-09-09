"""Check highlight detection against every snapshot, and time it."""

import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access import menu, ocr  # noqa: E402

SNAPS = ROOT / "snapshots"


def main() -> None:
    stems = sys.argv[1:]
    files = [SNAPS / f"{s}.png" for s in stems] if stems else sorted(SNAPS.glob("*.png"))

    for png in files:
        rgb = np.asarray(Image.open(png).convert("RGB"))
        bgra = np.ascontiguousarray(
            np.dstack([rgb[..., ::-1], np.full(rgb.shape[:2], 255, np.uint8)])
        )

        t0 = time.perf_counter()
        band = menu.highlight_band(rgb)
        t1 = time.perf_counter()

        if band is None:
            print(f"{png.stem}  no highlight            ({(t1 - t0) * 1000:5.1f} ms scan)")
            continue

        # Recognise only the highlighted strip, which is the fast path.
        t2 = time.perf_counter()
        strip_items = ocr.read(menu.strip(bgra, band))
        t3 = time.perf_counter()
        text = " ".join(i.text for i in strip_items) or "(unreadable)"

        full = ocr.reading_order(ocr.read(bgra))
        _, body, footer = menu.split_chrome(full)
        idx = menu.selected_index(body, band)
        pos = f"{idx + 1} of {len(body)}" if idx is not None else "position unknown"

        print(
            f"{png.stem}  {text!r:34s} {pos:16s} "
            f"(scan {(t1 - t0) * 1000:4.1f} ms, strip ocr {(t3 - t2) * 1000:5.1f} ms, "
            f"density {band.density:.2f})"
        )
        desc = menu.description(footer)
        if desc:
            print(f"{'':22s}  -> {desc[:88]}")


if __name__ == "__main__":
    main()
