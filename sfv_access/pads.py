"""Which buttons the player is pressing, read straight from Windows.

For Button Preview, where the game shows what a button does as it is pressed
and draws it only as pictures. XInput gives every connected controller's
buttons to any program, the game in front or not, and GetAsyncKeyState gives
the keyboard's keys; so a press can be said without reading the game at all.
Each press is reported as a pad key number (see `buttons`), the numbers the
game's key configuration uses, so the layout can say what it does.
"""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes

from . import buttons

POLL = 0.01
TRIGGER_DOWN = 100          # of 255
STICK_DOWN = 16000          # of 32767

# XInput's button bits, as pad key numbers.
XINPUT_BITS = {0x0001: 0, 0x0002: 1, 0x0004: 2, 0x0008: 3, 0x0010: 14, 0x0020: 15, 0x0040: 12, 0x0080: 13,
               0x0100: 8, 0x0200: 9, 0x1000: 6, 0x2000: 7, 0x4000: 4, 0x8000: 5}
LEFT_TRIGGER, RIGHT_TRIGGER = 10, 11

# Unreal's key names, as the keyboard bindings file writes them, to virtual keys.
VIRTUAL_KEYS = {
    "Comma": 0xBC, "Period": 0xBE, "Slash": 0xBF, "Semicolon": 0xBA, "Apostrophe": 0xDE, "Backslash": 0xDC,
    "LeftBracket": 0xDB, "RightBracket": 0xDD, "Hyphen": 0xBD, "Equals": 0xBB, "Tilde": 0xC0,
    "Enter": 0x0D, "Escape": 0x1B, "SpaceBar": 0x20, "Tab": 0x09, "BackSpace": 0x08,
    "LeftShift": 0xA0, "RightShift": 0xA1, "LeftControl": 0xA2, "RightControl": 0xA3, "LeftAlt": 0xA4, "RightAlt": 0xA5,
    "Up": 0x26, "Down": 0x28, "Left": 0x25, "Right": 0x27, "Insert": 0x2D, "Delete": 0x2E, "Home": 0x24, "End": 0x23,
    "PageUp": 0x21, "PageDown": 0x22,
    "NumPadZero": 0x60, "NumPadOne": 0x61, "NumPadTwo": 0x62, "NumPadThree": 0x63, "NumPadFour": 0x64,
    "NumPadFive": 0x65, "NumPadSix": 0x66, "NumPadSeven": 0x67, "NumPadEight": 0x68, "NumPadNine": 0x69,
    "Zero": 0x30, "One": 0x31, "Two": 0x32, "Three": 0x33, "Four": 0x34, "Five": 0x35, "Six": 0x36,
    "Seven": 0x37, "Eight": 0x38, "Nine": 0x39,
}


def virtual_key(name: str) -> int | None:
    if len(name) == 1 and name.isalnum():
        return ord(name.upper())
    if len(name) >= 2 and name[0] == "F" and name[1:].isdigit():
        return 0x6F + int(name[1:])
    return VIRTUAL_KEYS.get(name)


class _Gamepad(ctypes.Structure):
    _fields_ = [("wButtons", wintypes.WORD), ("bLeftTrigger", ctypes.c_ubyte), ("bRightTrigger", ctypes.c_ubyte),
                ("sThumbLX", ctypes.c_short), ("sThumbLY", ctypes.c_short),
                ("sThumbRX", ctypes.c_short), ("sThumbRY", ctypes.c_short)]


class _State(ctypes.Structure):
    _fields_ = [("dwPacketNumber", wintypes.DWORD), ("Gamepad", _Gamepad)]


def _xinput():
    for name in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
        try:
            return ctypes.WinDLL(name)
        except OSError:
            continue
    return None


def pad_held(state: _State) -> set[int]:
    """The pad key numbers one controller state holds down."""
    pad = state.Gamepad
    held = {number for bit, number in XINPUT_BITS.items() if pad.wButtons & bit}
    if pad.bLeftTrigger >= TRIGGER_DOWN:
        held.add(LEFT_TRIGGER)
    if pad.bRightTrigger >= TRIGGER_DOWN:
        held.add(RIGHT_TRIGGER)
    if pad.sThumbLY >= STICK_DOWN:
        held.add(0)
    if pad.sThumbLY <= -STICK_DOWN:
        held.add(1)
    if pad.sThumbLX <= -STICK_DOWN:
        held.add(2)
    if pad.sThumbLX >= STICK_DOWN:
        held.add(3)
    return held


class PressWatcher:
    """Calls `on_press(number)` for each button newly pressed, while `active` is set."""

    def __init__(self, on_press) -> None:
        self.on_press = on_press
        self.active = threading.Event()
        self._stop = threading.Event()
        self._xinput = _xinput()
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def held(self) -> set[int]:
        held: set[int] = set()
        if self._xinput is not None:
            for index in range(4):
                state = _State()
                if self._xinput.XInputGetState(index, ctypes.byref(state)) == 0:
                    held |= pad_held(state)
        slots = {slot: number for number, slot in buttons.KEYBOARD_SLOT.items()}
        for slot, key in buttons.keyboard_keys().items():
            vk = virtual_key(key)
            if vk is not None and slot in slots and self._user32.GetAsyncKeyState(vk) & 0x8000:
                held.add(slots[slot])
        return held

    def _run(self) -> None:
        before: set[int] | None = None
        while not self._stop.is_set():
            if not self.active.wait(0.25):
                before = None
                continue
            try:
                now = self.held()
            except Exception:
                now = set()
            # Whatever is already held as watching starts, such as the button
            # that opened the preview, is not a press.
            if before is None:
                before = now
            for number in sorted(now - before):
                try:
                    self.on_press(number)
                except Exception:
                    pass
            before = now
            time.sleep(POLL)
