"""Screen capture via the Desktop Duplication API (bettercam).

Desktop Duplication is used rather than GDI because Street Fighter V renders
through Direct3D; BitBlt and PrintWindow return black frames for it.

grab() yields None when the desktop has not changed since the previous call,
so the last good frame is cached and returned instead.
"""

from __future__ import annotations

import threading
import time

import numpy as np


def to_rgb(bgra: np.ndarray) -> np.ndarray:
    """Drop alpha and put the channels in RGB order for the analysis code."""
    return np.ascontiguousarray(bgra[:, :, 2::-1])


def crop(frame: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    """The part of a whole-screen frame inside `box`: left, top, width, height.

    Used to cut the game's picture out of the screen, so everything measured
    off it lands where it would on a game filling a 16 by 9 screen. Where the
    box runs off the screen, as a window pushed partly past its edge can, the
    missing part is black and the rest stays in its place. A box not on this
    screen at all leaves the frame whole, as it was before boxes were known.
    """
    left, top, width, height = box
    h, w = frame.shape[:2]
    if (left, top, width, height) == (0, 0, w, h):
        return frame
    x0, y0 = max(0, left), max(0, top)
    x1, y1 = min(w, left + width), min(h, top + height)
    if x1 <= x0 or y1 <= y0:
        return frame
    if (x0, y0, x1, y1) == (left, top, left + width, top + height):
        return np.ascontiguousarray(frame[y0:y1, x0:x1])
    out = np.zeros((height, width) + frame.shape[2:], dtype=frame.dtype)
    out[y0 - top:y1 - top, x0 - left:x1 - left] = frame[y0:y1, x0:x1]
    return out


class Capture:
    def __init__(self, output_idx: int | None = None) -> None:
        import bettercam

        self._cam = bettercam.create(output_idx=output_idx, output_color="BGRA")
        self._last: np.ndarray | None = None
        self._last_time = 0.0
        self._lock = threading.Lock()

    @property
    def width(self) -> int:
        return self._cam.width

    @property
    def height(self) -> int:
        return self._cam.height

    def frame(self, max_age: float = 0.05, timeout: float = 0.35) -> np.ndarray | None:
        """Freshest full-screen BGRA frame, or None if nothing was ever captured.

        Returns the cached frame if it is younger than `max_age` seconds.
        """
        with self._lock:
            now = time.perf_counter()
            if self._last is not None and (now - self._last_time) < max_age:
                return self._last

            deadline = now + timeout
            while True:
                got = self._cam.grab()
                if got is not None:
                    self._last = np.ascontiguousarray(got)
                    self._last_time = time.perf_counter()
                    return self._last
                if time.perf_counter() >= deadline:
                    # Static screen: nothing new to hand back, reuse what we have.
                    return self._last
                time.sleep(0.008)

    def region(self, box, max_age: float = 0.05) -> np.ndarray | None:
        """Crop (left, top, right, bottom) out of the freshest frame."""
        f = self.frame(max_age=max_age)
        if f is None:
            return None
        l, t, r, b = (int(v) for v in box)
        h, w = f.shape[:2]
        l, t = max(0, l), max(0, t)
        r, b = min(w, r), min(h, b)
        if r <= l or b <= t:
            return None
        return np.ascontiguousarray(f[t:b, l:r])

    def close(self) -> None:
        try:
            self._cam.release()
        except Exception:
            pass
