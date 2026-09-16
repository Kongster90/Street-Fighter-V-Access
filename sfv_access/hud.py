"""Reading the in-match gauges straight off the pixels.

Health, V-Trigger and the Critical Art gauge carry no text at all, so text
recognition can never see them. They are drawn at fixed positions in fixed
colours, which makes measuring them directly both simple and exact.

Every coordinate below was measured from a 1920 by 1080 capture and is scaled
for other resolutions. The layout is separated from the logic so it can be
recalibrated from a fresh snapshot without touching the code.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

BASE_W, BASE_H = 1920, 1080

# Health bars run the full span; P1 empties toward one end and P2 the other,
# so the fill is measured as a share of the whole span rather than from an
# assumed anchor. Rows sit below the PLAYER 1 and CPU labels, which are white
# and would otherwise punch a hole in the measurement.
HEALTH = {
    "p1": (155, 890),
    "p2": (1030, 1765),
}
HEALTH_ROWS = (109, 116)

# Segment centres in fill order. P2's gauges mirror P1's about the screen
# centre, so its segments count down from the outside in.
V_TRIGGER = {
    "p1": (232, 301, 370),
    "p2": (1688, 1619, 1550),
}
V_TRIGGER_ROWS = (973, 982)

# The Critical Art gauge is three stocks for every character.
CRITICAL = {
    "p1": (273, 382, 491),
    "p2": (1428, 1537, 1647),
}
CRITICAL_ROWS = (1007, 1017)


@dataclass
class Hud:
    health_p1: float | None
    health_p2: float | None
    v_trigger_p1: int
    v_trigger_p2: int
    critical_p1: int
    critical_p2: int

    def describe(self, side: str = "both") -> str:
        parts = []
        if side in ("both", "p1"):
            parts.append(self._side("You", self.health_p1, self.v_trigger_p1, self.critical_p1))
        if side in ("both", "p2"):
            parts.append(self._side("Opponent", self.health_p2, self.v_trigger_p2, self.critical_p2))
        return " ".join(parts)

    @staticmethod
    def _side(label: str, health, vt: int, ca: int) -> str:
        hp = "health unknown" if health is None else f"health {round(health * 100)} percent"
        return f"{label}, {hp}, V-Trigger {vt}, Critical {ca} of 3."


def _scaled(value: int, size: int, base: int) -> int:
    return value if size == base else int(round(value * size / base))


def _yellow(block: np.ndarray) -> np.ndarray:
    r = block[..., 0].astype(np.int16)
    g = block[..., 1].astype(np.int16)
    b = block[..., 2].astype(np.int16)
    return (r > 170) & (g > 130) & (b < 160) & ((r - b) > 60)


def _bar_lit(block: np.ndarray) -> np.ndarray:
    """Whether each pixel is part of a health bar's fill.

    The bar is not one colour: it runs from green at the end that empties
    first to yellow at the other, and a damaged bar showed (91, 254, 39) at
    one end and (236, 252, 5) at the other, over a (26, 26, 26) background.
    Counting only the yellow of it called a bar that was 61 percent full 33,
    which is what the user heard on Survival's supplement screen. Green is
    taken as well: strong green, little blue, against that dark background.
    """
    r = block[..., 0].astype(np.int16)
    g = block[..., 1].astype(np.int16)
    b = block[..., 2].astype(np.int16)
    green = (g > 200) & (b < 100) & (r > 60) & ((g - b) > 120)
    return _yellow(block) | green


def _lit_columns(rgb: np.ndarray, span: tuple[int, int]) -> np.ndarray | None:
    h, w = rgb.shape[:2]
    x0 = _scaled(span[0], w, BASE_W)
    x1 = _scaled(span[1], w, BASE_W)
    y0 = _scaled(HEALTH_ROWS[0], h, BASE_H)
    y1 = _scaled(HEALTH_ROWS[1], h, BASE_H)
    if x1 <= x0 or y1 <= y0 or y1 > h or x1 > w:
        return None
    return _bar_lit(rgb[y0:y1, x0:x1]).any(axis=0)


def _longest_run(lit: np.ndarray) -> int:
    best = run = 0
    for on in lit:
        run = run + 1 if on else 0
        best = max(best, run)
    return best


def health_fraction(rgb: np.ndarray, span: tuple[int, int]) -> float | None:
    lit = _lit_columns(rgb, span)
    if lit is None:
        return None
    # Share of columns that are lit, so a partial bar reads correctly whichever
    # end it drains from.
    return float(lit.sum() / lit.size)


def _contiguity(rgb: np.ndarray, span: tuple[int, int]) -> float:
    """How much of the lit area forms one unbroken run.

    A health bar is a single block of colour. Character select and menu artwork
    also put warm tones in these rows, but scattered, so this is what separates
    a real bar from a picture of a fighter.
    """
    lit = _lit_columns(rgb, span)
    if lit is None or lit.sum() == 0:
        return 0.0
    return _longest_run(lit) / float(lit.sum())


def _segment_lit(rgb: np.ndarray, cx: int, rows: tuple[int, int], half: int = 14) -> bool:
    h, w = rgb.shape[:2]
    x = _scaled(cx, w, BASE_W)
    y0 = _scaled(rows[0], h, BASE_H)
    y1 = _scaled(rows[1], h, BASE_H)
    x0, x1 = max(0, x - half), min(w, x + half)
    if x1 <= x0 or y1 <= y0 or y1 > h:
        return False
    block = rgb[y0:y1, x0:x1].astype(np.float32)
    lum = block[..., 0] * 0.299 + block[..., 1] * 0.587 + block[..., 2] * 0.114
    # A charged stock is emphatically bright; an empty slot is a dark outline.
    return float(np.median(lum)) > 150.0


def count_segments(rgb: np.ndarray, centres, rows) -> int:
    """Charged stocks, counted from the outside in until one is empty."""
    total = 0
    for cx in centres:
        if not _segment_lit(rgb, cx, rows):
            break
        total += 1
    return total


def read(rgb: np.ndarray) -> Hud:
    return Hud(
        health_p1=health_fraction(rgb, HEALTH["p1"]),
        health_p2=health_fraction(rgb, HEALTH["p2"]),
        v_trigger_p1=count_segments(rgb, V_TRIGGER["p1"], V_TRIGGER_ROWS),
        v_trigger_p2=count_segments(rgb, V_TRIGGER["p2"], V_TRIGGER_ROWS),
        critical_p1=count_segments(rgb, CRITICAL["p1"], CRITICAL_ROWS),
        critical_p2=count_segments(rgb, CRITICAL["p2"], CRITICAL_ROWS),
    )


def looks_like_match(rgb: np.ndarray) -> bool:
    """Whether real health bars are on screen, meaning a round is in progress."""
    a = health_fraction(rgb, HEALTH["p1"])
    b = health_fraction(rgb, HEALTH["p2"])
    if a is None or b is None or max(a, b) < 0.05:
        return False
    ca = _contiguity(rgb, HEALTH["p1"])
    cb = _contiguity(rgb, HEALTH["p2"])
    return min(ca, cb) >= 0.75
