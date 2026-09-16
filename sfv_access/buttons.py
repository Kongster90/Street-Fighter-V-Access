"""How controller buttons are named when the mod says them.

The game knows every button by its Xbox position, the pad key numbers of its
key configuration (X 4, Y 5, A 6, B 7, left bumper 8, right bumper 9, left
trigger 10, right trigger 11, stick presses 12 and 13, Start 14, Back 15).
A player on a PlayStation pad or a keyboard knows them by other names, so the
mod says them in the style the player chose with Alt B, remembered in
settings.json beside run.py.

Keyboard names come from the game's own keyboard bindings, which it saves in
Input2.ini under [AssignKeyboard] as KeyboardKeys_0 to 15. Their order was
worked out from the defaults the user knows, light, medium and heavy punch on
G, H and J and the kicks on B, N and M, against the controller defaults:
up, down, right, left, then A, B, X, Y, left bumper, right bumper, left
trigger, right trigger, left and right stick press, Start, Back.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

SETTINGS = Path(__file__).resolve().parent.parent / "settings.json"
INPUT_INI = Path(os.environ.get("LOCALAPPDATA", "")) / "StreetFighterV" / "Saved" / "Config" / "WindowsNoEditor" / "Input2.ini"

STYLES = ("xbox", "playstation", "keyboard")
STYLE_WORDS = {"xbox": "Xbox buttons", "playstation": "PlayStation buttons", "keyboard": "keyboard keys"}

XBOX = {0: "up", 1: "down", 2: "left", 3: "right", 4: "X", 5: "Y", 6: "A", 7: "B",
        8: "left bumper", 9: "right bumper", 10: "left trigger", 11: "right trigger",
        12: "left stick press", 13: "right stick press", 14: "Start", 15: "Back"}
PLAYSTATION = {0: "up", 1: "down", 2: "left", 3: "right", 4: "square", 5: "triangle", 6: "cross", 7: "circle",
               8: "L1", 9: "R1", 10: "L2", 11: "R2", 12: "L3", 13: "R3", 14: "Options", 15: "Share"}
# Which KeyboardKeys_ entry is bound to each pad key number.
KEYBOARD_SLOT = {0: 0, 1: 1, 3: 2, 2: 3, 6: 4, 7: 5, 4: 6, 5: 7, 8: 8, 9: 9, 10: 10, 11: 11,
                 12: 12, 13: 13, 14: 14, 15: 15}
NONE = "none"
UNASSIGNED = 17

_settings: dict | None = None
_keyboard: tuple[Path, float, dict[int, str]] | None = None


def _load() -> dict:
    global _settings
    if _settings is None:
        try:
            _settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _settings = {}
    return _settings


def style() -> str:
    chosen = _load().get("button_names")
    return chosen if chosen in STYLES else STYLES[0]


def _save(name: str, value) -> None:
    settings = _load()
    settings[name] = value
    try:
        SETTINGS.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except OSError:
        pass


def next_style() -> str:
    """Move to the next naming style, save it, and return it."""
    chosen = STYLES[(STYLES.index(style()) + 1) % len(STYLES)]
    _save("button_names", chosen)
    return chosen


# Story scenes' subtitles live in the same settings file: off unless the player
# turns them on, since the story voices are often in English.
def subtitles_on() -> bool:
    return _load().get("subtitles") is True


def toggle_subtitles() -> bool:
    """Turn subtitles on or off, save it, and return whether they are on."""
    on = not subtitles_on()
    _save("subtitles", on)
    return on


# The player's own Fighter ID, learnt from the main menu's card and kept so
# that an online VS screen can tell their side from their opponent's. Online
# that screen names both sides and nothing on it says which is which.
def fighter_id() -> str | None:
    name = _load().get("fighter_id")
    return name if isinstance(name, str) and name.strip() else None


def remember_fighter_id(name: str) -> None:
    if name.strip() and name.strip() != fighter_id():
        _save("fighter_id", name.strip())


def key_words(key: str) -> str:
    """An Unreal key name as said: "LeftShift" as "Left Shift", "SpaceBar" as "Space Bar"."""
    return re.sub(r"(?<=[a-z])(?=[A-Z0-9])", " ", key)


def keyboard_keys(path: Path | None = None) -> dict[int, str]:
    """KeyboardKeys_ entries from the game's saved keyboard bindings, read again when the file changes."""
    global _keyboard
    # Looked up when called, not when defined, so a test pointing INPUT_INI at a
    # scratch file really reads that and not the player's own bindings.
    path = path or INPUT_INI
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return {}
    if _keyboard is None or _keyboard[:2] != (path, stamp):
        keys: dict[int, str] = {}
        section = None
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line.startswith("["):
                    section = line
                elif section == "[AssignKeyboard]":
                    m = re.fullmatch(r"KeyboardKeys_(\d+)=(.+)", line)
                    if m:
                        keys[int(m.group(1))] = m.group(2).strip()
        except OSError:
            return {}
        _keyboard = (path, stamp, keys)
    return _keyboard[2]


def name(number: int, chosen: str | None = None) -> str:
    """A pad key number in the chosen style."""
    if number == UNASSIGNED:
        return NONE
    chosen = chosen or style()
    if chosen == "playstation":
        return PLAYSTATION.get(number, f"button {number}")
    if chosen == "keyboard":
        key = keyboard_keys().get(KEYBOARD_SLOT.get(number, -1))
        if key:
            return key_words(key)
    return XBOX.get(number, f"button {number}")
