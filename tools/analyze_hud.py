"""Locate the in-match gauges by scanning for their coloured runs."""

import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SNAPS = ROOT / "snapshots"


def runs(mask_row: np.ndarray, min_len: int):
    out, start = [], None
    for x, on in enumerate(mask_row):
        if on and start is None:
            start = x
        elif not on and start is not None:
            if x - start >= min_len:
                out.append((start, x))
            start = None
    if start is not None and len(mask_row) - start >= min_len:
        out.append((start, len(mask_row)))
    return out


def report(rgb, y0, y1, mask_fn, label, min_len, rows_step=2):
    print(f"--- {label} (rows {y0} to {y1}) ---")
    for y in range(y0, y1, rows_step):
        row = mask_fn(rgb[y])
        found = runs(row, min_len)
        if found:
            spans = "  ".join(f"{a}-{b} (w{b - a})" for a, b in found)
            print(f"  y={y:4d}  {spans}")


def yellow(row):
    r, g, b = row[:, 0].astype(int), row[:, 1].astype(int), row[:, 2].astype(int)
    return (r > 170) & (g > 130) & (b < 160) & (r - b > 60)


def cyanish(row):
    r, g, b = row[:, 0].astype(int), row[:, 1].astype(int), row[:, 2].astype(int)
    return (b > 170) & (g > 160) & (b - r > 10)


def reddish(row):
    r, g, b = row[:, 0].astype(int), row[:, 1].astype(int), row[:, 2].astype(int)
    return (r > 140) & (r - g > 55) & (r - b > 55)


def main():
    stem = sys.argv[1] if len(sys.argv) > 1 else "sfv-20260908-224524"
    rgb = np.asarray(Image.open(SNAPS / f"{stem}.png").convert("RGB"))
    print(f"{stem}  {rgb.shape[1]}x{rgb.shape[0]}\n")
    report(rgb, 88, 132, yellow, "health bars (yellow)", 120, rows_step=4)
    print()
    report(rgb, 130, 156, yellow, "stun bars (yellow)", 60, rows_step=3)
    print()
    report(rgb, 955, 1000, reddish, "V-trigger segments (red)", 30, rows_step=4)
    print()
    report(rgb, 995, 1045, cyanish, "critical art segments (cyan/white)", 30, rows_step=4)


if __name__ == "__main__":
    main()
