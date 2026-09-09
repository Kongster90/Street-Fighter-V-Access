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

from . import ocr

# The name sits across the middle of the screen; the conditions run beneath it.
# Given as a share of the frame so other resolutions work unchanged.
NAME_BAND = (0.40, 0.55)
ATTRIBUTE_BAND = (0.50, 0.60)
ATTRIBUTE_WORDS = ("time", "temperature", "weather")

_SEPARATOR = re.compile(r"^\s*(time|temperature|weather)\s*[|Il1!:]*\s*", re.IGNORECASE)


# The degree sign comes back as a zero, so 80 degrees reads as "800 F". Stage
# temperatures are two digits, which makes the trailing zero unambiguous.
_DEGREES = re.compile(r"^(\d{2})0\s*([FC])$", re.IGNORECASE)


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
