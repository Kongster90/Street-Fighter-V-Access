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

# How sure the reader has to be that a stage name is a real one. The same
# threshold correction uses, because it is the same question: is this a string
# the game contains. Real names score 1.00; the misreadings seen in play scored
# 0.48 to 0.77.
NAME_CONFIDENCE = 0.78


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


# A confirmation dialog puts its choices side by side on one row, in the middle
# of the screen, over a light modal panel.
DIALOG_ROW = (0.55, 0.75)  # share of frame height the buttons sit within
DIALOG_WORDS = 18  # a choice is a word or two, not a sentence


def dialog_choice(rgb, items) -> tuple[str, str] | None:
    """The question a dialog is asking and which answer is selected.

    Worth its own reader because getting it wrong is expensive: one of these
    asks whether to close the game, and it is the only screen where mishearing
    the answer loses whatever you were doing.

    The selected button is drawn as a thin gold outline around a dark fill,
    which the band builder cannot see. Its left and right edges are separate
    runs of gold a few pixels wide with nothing between them, so they are split
    apart and then dropped for being too narrow. The fill is the better signal
    anyway: these dialogs sit on a pale panel, so the chosen answer is simply
    the dark one.
    """
    height, width = rgb.shape[:2]
    row = [
        it
        for it in items
        if DIALOG_ROW[0] * height <= it.cy <= DIALOG_ROW[1] * height
        and 0 < len(it.text.strip()) <= DIALOG_WORDS
    ]
    if len(row) < 2:
        return None
    # Buttons are side by side, so they share a row; anything else is not a
    # pair of choices.
    row.sort(key=lambda it: it.x)
    top = min(row, key=lambda it: it.cy)
    row = [it for it in row if abs(it.cy - top.cy) <= 0.02 * height]
    if len(row) < 2:
        return None

    darkness = []
    for it in row:
        y0, y1 = int(it.y - it.h), int(it.y + 2 * it.h)
        x0, x1 = int(it.x - it.w), int(it.x + 2 * it.w)
        patch = rgb[max(0, y0) : min(height, y1), max(0, x0) : min(width, x1)]
        darkness.append((patch.max(axis=2) < 105).mean() if patch.size else 0.0)

    order = sorted(range(len(row)), key=lambda i: -darkness[i])
    best, rest = order[0], order[1]
    # One clearly dark answer among pale ones. Anything less is not a dialog.
    if darkness[best] < 0.35 or darkness[best] - darkness[rest] < 0.25:
        return None

    # The question is the widest line above the buttons.
    above = [it for it in items if it.cy < top.cy - 0.02 * height and it.text.strip()]
    question = max(above, key=lambda it: it.w).text.strip() if above else ""
    return question, row[best].text.strip()


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


def stage_select(
    items: list[ocr.TextItem], height: int, with_conditions: bool = True
) -> str | None:
    """A description of the stage on offer, or None if this is not that screen.

    Identified by its conditions rather than its heading. The heading is
    stylised and comes back as anything from "STAGESELECT" to "ST -", while
    Time, Temperature and Weather are plain text and always present.

    Those conditions identify the screen but are left out of what is spoken
    while moving through it: they do not affect play, and hearing three of them
    after every stage name is a lot of talking for nothing. Asking for a
    reading includes them.
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

    # The name has to be a stage the game contains, or nothing is said.
    #
    # These names are outlined type over full-bleed artwork and the screen
    # animates, so a stage that is read cleanly one frame is read differently
    # the next. Sitting on Rival Riverside produced twelve spellings in six
    # seconds, among them "RuvaIzRivers1de" and "RfvåII!kiüeFSid", each a
    # different string, each announced, each cutting off the one before it.
    # Ring of Pride did the same. The names were never wrong for long; they
    # were just never quiet.
    #
    # The game's own word list settles it. A real stage name is in there, and
    # every one of those spellings scored below what correction accepts, so
    # they are dropped and the next frame gets another go. This also stops
    # "Weather I Clear" being announced as though it were a stage.
    name = stage.text.strip()
    if len(name) < 3:
        return None
    vocabulary = strings.shared()
    if vocabulary is not None:
        match = vocabulary.correct(name)
        if match.score < NAME_CONFIDENCE:
            return None
        name = match.text

    parts = [name]
    if with_conditions:
        for name, value in attributes:
            # An unset condition shows as a question mark; saying "Weather
            # question mark" is worse than leaving it out.
            if value and value not in ("?", "-"):
                parts.append(f"{name} {value}")
    return ". ".join(parts) + "."
