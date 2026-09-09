"""Text recognition using the OCR engine built into Windows.

Windows.Media.Ocr needs no external binary and handles a full 1080p frame in
roughly 120 ms, which is fast enough to narrate a menu on demand.  It returns
per-word bounding boxes, and those coordinates are what later lets us work out
which menu entry is highlighted.
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass

import numpy as np

from winrt.windows.globalization import Language
from winrt.windows.graphics.imaging import (
    BitmapAlphaMode,
    BitmapPixelFormat,
    SoftwareBitmap,
)
from winrt.windows.media.ocr import OcrEngine

_local = threading.local()


@dataclass(frozen=True)
class TextItem:
    text: str
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


def _engine() -> OcrEngine:
    eng = getattr(_local, "engine", None)
    if eng is None:
        eng = OcrEngine.try_create_from_language(Language("en-US"))
        if eng is None:
            eng = OcrEngine.try_create_from_user_profile_languages()
        if eng is None:
            raise RuntimeError(
                "No Windows OCR language pack is installed. Add English under "
                "Settings, Time and language, Language and region."
            )
        _local.engine = eng
    return eng


def available_languages() -> list[str]:
    return [l.language_tag for l in OcrEngine.available_recognizer_languages]


def _to_bitmap(bgra: np.ndarray) -> SoftwareBitmap:
    h, w = bgra.shape[:2]
    buf = bgra.copy()
    buf[:, :, 3] = 255  # Desktop Duplication leaves alpha undefined
    return SoftwareBitmap.create_copy_with_alpha_from_buffer(
        buf.tobytes(), BitmapPixelFormat.BGRA8, w, h, BitmapAlphaMode.IGNORE
    )


def _upscale(bgra: np.ndarray, factor: int) -> np.ndarray:
    if factor <= 1:
        return bgra
    return np.ascontiguousarray(np.repeat(np.repeat(bgra, factor, axis=0), factor, axis=1))


def read(
    bgra: np.ndarray,
    origin: tuple[int, int] = (0, 0),
    scale: int | None = None,
) -> list[TextItem]:
    """OCR a BGRA image.

    `origin` is added to every coordinate, so a cropped region can report
    absolute screen positions.  `scale` upscales before recognition, which
    markedly improves small text; it is chosen automatically when omitted.
    """
    if bgra is None or bgra.size == 0:
        return []

    h, w = bgra.shape[:2]
    if scale is None:
        scale = 3 if h < 90 else 2 if h < 260 else 1
    # Stay under the engine's 10000 px limit.
    while scale > 1 and (max(h, w) * scale) > 9500:
        scale -= 1

    img = _upscale(bgra, scale)
    bitmap = _to_bitmap(img)

    async def _run():
        return await _engine().recognize_async(bitmap)

    result = asyncio.run(_run())

    ox, oy = origin
    items: list[TextItem] = []
    for line in result.lines:
        words = list(line.words)
        if not words:
            continue
        x0 = min(wd.bounding_rect.x for wd in words)
        y0 = min(wd.bounding_rect.y for wd in words)
        x1 = max(wd.bounding_rect.x + wd.bounding_rect.width for wd in words)
        y1 = max(wd.bounding_rect.y + wd.bounding_rect.height for wd in words)
        items.append(
            TextItem(
                text=line.text,
                x=x0 / scale + ox,
                y=y0 / scale + oy,
                w=(x1 - x0) / scale,
                h=(y1 - y0) / scale,
            )
        )
    return items


def boost(bgra: np.ndarray, low_pct: float = 60.0, high_pct: float = 99.5) -> np.ndarray:
    """Rework pale lettering sitting over busy artwork into plain dark on light.

    Character select draws each name in outlined type over a full-bleed picture
    of the fighter, and the recogniser reads it badly or not at all: KEN came
    back as EN, GILL as ILL, RYU as CRY. Discarding everything below the top of
    the brightness range leaves the lettering and little else, and inverting it
    gives the dark-on-light the engine is happiest with. On the captures to
    hand this turns unreadable names into correct ones.
    """
    lum = bgra[:, :, :3].astype(np.float32).mean(axis=2)
    lo = float(np.percentile(lum, low_pct))
    hi = float(np.percentile(lum, high_pct))
    if hi <= lo:
        return bgra
    stretched = np.clip((lum - lo) / (hi - lo), 0.0, 1.0)
    grey = ((1.0 - stretched) * 255).astype(np.uint8)
    return np.ascontiguousarray(
        np.dstack([grey, grey, grey, np.full(grey.shape, 255, np.uint8)])
    )


def reading_order(items: list[TextItem], row_tolerance: float = 12.0) -> list[TextItem]:
    """Sort top to bottom, then left to right within a row."""
    out = sorted(items, key=lambda t: (t.y, t.x))
    rows: list[list[TextItem]] = []
    for it in out:
        if rows and abs(it.y - rows[-1][0].y) <= row_tolerance:
            rows[-1].append(it)
        else:
            rows.append([it])
    flat: list[TextItem] = []
    for row in rows:
        flat.extend(sorted(row, key=lambda t: t.x))
    return flat
