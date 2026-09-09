"""Crop regions out of a snapshot so they can be inspected closely.

Usage:
    python tools/crop.py <snapshot-stem> <left> <top> <right> <bottom> [outname] [scale]
"""

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SNAPS = ROOT / "snapshots"
OUT = ROOT / "snapshots" / "crops"


def main() -> None:
    stem = sys.argv[1]
    l, t, r, b = (int(v) for v in sys.argv[2:6])
    name = sys.argv[6] if len(sys.argv) > 6 else f"{stem}-{l}_{t}_{r}_{b}"
    scale = float(sys.argv[7]) if len(sys.argv) > 7 else 1.0

    src = SNAPS / f"{stem}.png"
    if not src.exists():
        matches = sorted(SNAPS.glob(f"*{stem}*.png"))
        if not matches:
            raise SystemExit(f"no snapshot matching {stem}")
        src = matches[0]

    img = Image.open(src).convert("RGB").crop((l, t, r, b))
    if scale != 1.0:
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / f"{name}.png"
    img.save(dest)
    print(f"{dest}  {img.width}x{img.height}")


if __name__ == "__main__":
    main()
