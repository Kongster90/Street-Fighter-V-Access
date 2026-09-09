"""Readers for screens that do not work like a menu.

Stage select has no highlighted entry to find. It shows one stage at a time,
filling the screen with artwork, with the name across the middle and the
conditions beneath it. So it is read by position rather than by looking for a
highlight, and the name is repaired against the game's own text, which turns
"Ringof PoWer" into "Ring of Power" and "Hollif ollyBeatdown" into "Holly Jolly
Beatdown".
"""

from __future__ import annotations

import re

import numpy as np

from . import ocr, strings

# The name sits across the middle of the screen; the conditions run beneath it.
# Given as a share of the frame so other resolutions work unchanged.
NAME_BAND = (0.40, 0.55)
ATTRIBUTE_BAND = (0.50, 0.60)
ATTRIBUTE_WORDS = ("time", "temperature", "weather")

_SEPARATOR = re.compile(r"^\s*(time|temperature|weather)\s*[|Il1!:]*\s*", re.IGNORECASE)


# The degree sign comes back as a zero, so 80 degrees reads as "800 F". Stage
# temperatures are two digits, which makes the trailing zero unambiguous.
_DEGREES = re.compile(r"^(\d{2})0\s*([FC])$", re.IGNORECASE)


# The main menu names the current choice in large type in a panel across the
# middle. Given as fractions of the frame so other resolutions work unchanged.
TITLE_BOX = (0.406, 0.398, 0.781, 0.500)  # left, top, right, bottom
# Titles measure 39 to 49 pixels tall on a 1080 frame while ordinary menu rows
# measure 18, so height alone separates them with room to spare.
TITLE_MIN_HEIGHT = 0.028


def _title_crop(frame: np.ndarray) -> np.ndarray:
    height, width = frame.shape[:2]
    left, top, right, bottom = TITLE_BOX
    return np.ascontiguousarray(
        frame[int(top * height) : int(bottom * height), int(left * width) : int(right * width)]
    )


def main_menu_title(bgra: np.ndarray) -> str | None:
    """The name of the highlighted main menu entry, read from its own panel.

    The far left of the main menu is a column of icons with no text at all,
    holding Options, Gallery, the terms and conditions and Exit. Nothing can
    read a label there because there is no label; the game puts the name in the
    panel across the middle instead, and that panel is drawn for every entry.

    It is also the only way those four are announced at all. The selected icon
    is a solid gold tile, and the band builder rejects solid blocks on purpose,
    since that is how it tells lettering from artwork.

    Returns None unless the panel holds one piece of large type, which is what
    keeps this from firing on an ordinary settings row.
    """
    items = [i for i in ocr.read(_title_crop(bgra)) if i.text.strip()]
    if not items:
        return None
    tallest = max(items, key=lambda i: i.h)
    if tallest.h < TITLE_MIN_HEIGHT * bgra.shape[0]:
        return None
    text = tallest.text.strip()
    if len(text) < 2:
        return None
    vocabulary = strings.shared()
    return vocabulary.correct(text).text if vocabulary else text


def title_signature(rgb: np.ndarray) -> bytes:
    """A cheap summary of the title panel, for noticing that it changed.

    The narration loop decides whether to re-read by watching where the
    highlight sits, which cannot work for the icon column: those entries put no
    gold anywhere the loop looks, so moving between them leaves its measurement
    untouched and it never re-reads. Watching the panel itself covers them, and
    pooling it to a coarse grid costs well under a millisecond.
    """
    crop = _title_crop(rgb)
    if crop.size == 0:
        return b""
    grey = crop.mean(axis=2)
    rows = np.array_split(grey, 6, axis=0)
    grid = [np.array_split(r, 16, axis=1) for r in rows]
    return bytes(int(c.mean()) >> 4 for row in grid for c in row if c.size)


def _attribute(text: str) -> tuple[str, str] | None:
    """Split "Weather I Clear" into its name and its value."""
    match = _SEPARATOR.match(text)
    if not match:
        return None
    value = text[match.end() :].strip(" |Il!:-•").strip()
    degrees = _DEGREES.match(value)
    if degrees:
        scale = "Fahrenheit" if degrees.group(2).upper() == "F" else "Celsius"
        value = f"{degrees.group(1)} degrees {scale}"
    return match.group(1).capitalize(), value


def stage_select(items: list[ocr.TextItem], height: int) -> str | None:
    """A description of the stage on offer, or None if this is not that screen.

    Identified by its conditions rather than its heading. The heading is
    stylised and comes back as anything from "STAGESELECT" to "ST -", while
    Time, Temperature and Weather are plain text and always present.
    """
    attributes: list[tuple[str, str]] = []
    for item in items:
        if not (ATTRIBUTE_BAND[0] * height <= item.cy <= ATTRIBUTE_BAND[1] * height):
            continue
        found = _attribute(item.text)
        if found:
            attributes.append(found)

    names = {name for name, _ in attributes}
    if len(names) < 2:
        return None

    candidates = [
        item
        for item in items
        if NAME_BAND[0] * height <= item.cy <= NAME_BAND[1] * height
        and _attribute(item.text) is None
        and any(c.isalpha() for c in item.text)
    ]
    if not candidates:
        return None
    stage = max(candidates, key=lambda i: i.h * i.w)

    parts = [stage.text.strip()]
    for name, value in attributes:
        # An unset condition shows as a question mark; saying "Weather
        # question mark" is worse than leaving it out.
        if value and value not in ("?", "-"):
            parts.append(f"{name} {value}")
    return ". ".join(parts) + "."
