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
