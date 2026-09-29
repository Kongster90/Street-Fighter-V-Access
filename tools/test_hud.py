"""Check the health bar reading against bars painted in the game's own colours.

The bar is not one colour. Read live from Survival's supplement screen on
2026-09-15, a damaged bar ran from (91, 254, 39) at the end that empties first
to (236, 252, 5) at the other, on a (26, 26, 26) background, and counting only
the yellow of it called a bar 60 percent full 33 percent. Needs no game.

The game's picture is not always the whole screen. A tester's game at 1920 by
1200 drew its 16 by 9 picture with black bars above and below, and Survival
said "Health 0 percent" after every stage, so the bars are also read here off
screens shaped like theirs, with the picture cut out as the mod does.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access import capture, game, hud  # noqa: E402

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


def desktop(picture: np.ndarray, size: tuple[int, int], box) -> np.ndarray:
    """A whole screen `size` wide and tall with the game's picture drawn in `box`.

    The picture is scaled to the box's size by picking pixels, and whatever
    of it falls off the screen is lost, as it would be.
    """
    left, top, width, height = box
    ys = (np.arange(height) * picture.shape[0] / height).astype(int)
    xs = (np.arange(width) * picture.shape[1] / width).astype(int)
    drawn = picture[ys][:, xs]
    out = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    x0, y0 = max(0, left), max(0, top)
    x1, y1 = min(size[0], left + width), min(size[1], top + height)
    out[y0:y1, x0:x1] = drawn[y0 - top:y1 - top, x0 - left:x1 - left]
    return out


check("a game filling a 16 by 9 screen is its own picture",
      game.picture_box((0, 0, 1920, 1080)) == (0, 0, 1920, 1080))
check("a 1920 by 1200 screen has its picture 60 rows down",
      game.picture_box((0, 0, 1920, 1200)) == (0, 60, 1920, 1080))
check("a wide screen has its picture in the middle",
      game.picture_box((0, 0, 2560, 1080)) == (320, 0, 1920, 1080))
whole = screen(0.6)
check("cutting the whole screen out of itself leaves it alone",
      capture.crop(whole, (0, 0, 1920, 1080)) is whole)

tall = desktop(screen(0.6), (1920, 1200), game.picture_box((0, 0, 1920, 1200)))
missed = hud.health_fraction(tall, hud.HEALTH["p1"])
check("measured off the whole 1920 by 1200 screen, the bar is missed, as the tester heard",
      missed == 0.0, f"{round(missed * 100)} percent")
read = hud.health_fraction(capture.crop(tall, game.picture_box((0, 0, 1920, 1200))),
                           hud.HEALTH["p1"])
check("measured off the picture on a 1920 by 1200 screen, the bar reads as itself",
      abs(read - 0.6) <= 0.01, f"{round(read * 100)} percent")

# A 1280 by 720 window with its title bar, on a 1920 by 1080 screen.
client = (8, 31, 8 + 1280, 31 + 720)
windowed = desktop(screen(0.6), (1920, 1080), game.picture_box(client))
read = hud.health_fraction(capture.crop(windowed, game.picture_box(client)), hud.HEALTH["p1"])
check("a bar in a smaller window with a title bar reads as itself",
      abs(read - 0.6) <= 0.02, f"{round(read * 100)} percent")

# A 1920 by 1200 window pushed down past the bottom of a 1920 by 1200 screen.
client = (0, 200, 1920, 1400)
pushed = desktop(screen(0.6), (1920, 1200), game.picture_box(client))
cut = capture.crop(pushed, game.picture_box(client))
read = hud.health_fraction(cut, hud.HEALTH["p1"])
check("a window partly off the screen keeps its picture the right size",
      cut.shape[:2] == (1080, 1920), f"{cut.shape[1]} by {cut.shape[0]}")
check("and its bar, still on screen, reads as itself",
      abs(read - 0.6) <= 0.01, f"{round(read * 100)} percent")

check("a picture on another screen leaves the frame whole",
      capture.crop(whole, (1920, 0, 1920, 1080)) is whole)

print()
print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
