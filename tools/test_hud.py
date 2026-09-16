"""Check the health bar reading against bars painted in the game's own colours.

The bar is not one colour. Read live from Survival's supplement screen on
2026-09-15, a damaged bar ran from (91, 254, 39) at the end that empties first
to (236, 252, 5) at the other, on a (26, 26, 26) background, and counting only
the yellow of it called a bar 60 percent full 33 percent. Needs no game.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access import hud  # noqa: E402

ok = True


def check(label, condition, detail=""):
    global ok
    if condition:
        print(f"PASS  {label}{(': ' + detail) if detail else ''}")
    else:
        ok = False
        print(f"FAIL  {label}{(': ' + detail) if detail else ''}")


GREEN_END = (91, 254, 39)
YELLOW_END = (236, 252, 5)
GOLD = (235, 213, 90)      # the bar as the fight's own display draws it
BACKGROUND = (26, 26, 26)


def screen(share: float, colours=(GREEN_END, YELLOW_END)) -> np.ndarray:
    """A 1920 by 1080 frame with player one's bar `share` full.

    It empties from the left, as the game's does, and its fill runs from the
    first colour to the second across the lit part.
    """
    rgb = np.zeros((hud.BASE_H, hud.BASE_W, 3), dtype=np.uint8)
    x0, x1 = hud.HEALTH["p1"]
    y0, y1 = hud.HEALTH_ROWS
    rgb[y0:y1, x0:x1] = BACKGROUND
    lit = round((x1 - x0) * share)
    for n in range(lit):
        at = x1 - lit + n
        mix = n / max(lit - 1, 1)
        rgb[y0:y1, at] = [round(a + (b - a) * mix) for a, b in zip(*colours)]
    return rgb


for share in (1.0, 0.6, 0.33, 0.0):
    read = hud.health_fraction(screen(share), hud.HEALTH["p1"])
    check(f"a bar {round(share * 100)} percent full reads as itself, green end and all",
          abs(read - share) <= 0.01, f"{round(read * 100)} percent")

read = hud.health_fraction(screen(0.6, colours=(GOLD, GOLD)), hud.HEALTH["p1"])
check("a bar in the gold the fight's own display uses still reads",
      abs(read - 0.6) <= 0.01, f"{round(read * 100)} percent")

check("an empty screen has no bars on it", not hud.looks_like_match(screen(0.0)))

print()
print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
