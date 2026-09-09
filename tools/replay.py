"""Replay saved snapshots through the announcement logic.

This is the regression test for the whole pipeline: it prints exactly what the
tool would say on each screen, without needing the game running.
"""

import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access.app import announce  # noqa: E402

SNAPS = ROOT / "snapshots"


def main() -> None:
    stems = sys.argv[1:]
    files = [SNAPS / f"{s}.png" for s in stems] if stems else sorted(SNAPS.glob("*.png"))

    worst = 0.0
    for png in files:
        rgb = np.asarray(Image.open(png).convert("RGB"))
        bgra = np.ascontiguousarray(
            np.dstack([rgb[..., ::-1], np.full(rgb.shape[:2], 255, np.uint8)])
        )
        t0 = time.perf_counter()
        said, body, idx, _footer = announce(bgra, rgb)
        dt = (time.perf_counter() - t0) * 1000
        worst = max(worst, dt)
        print(f"{png.stem}  [{dt:5.0f} ms]")
        print(f"    {said}")
    print(f"\nslowest announcement: {worst:.0f} ms")


if __name__ == "__main__":
    main()
