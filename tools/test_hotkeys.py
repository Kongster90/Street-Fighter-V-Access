"""Check that the hotkeys are held only while they are wanted.

Uses a combination nobody presses, Control Alt Shift F23, and a switch this
test flips in place of "the game is in front". Whether the pump holds the key
is seen from outside: registering the same combination here fails while the
pump has it and works once it has let go.
"""

from __future__ import annotations

import ctypes
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access import hotkeys  # noqa: E402

ok = True


def check(label, condition, detail=""):
    global ok
    if condition:
        print(f"PASS  {label}{(': ' + detail) if detail else ''}")
    else:
        ok = False
        print(f"FAIL  {label}{(': ' + detail) if detail else ''}")


COMBO = "ctrl+alt+shift+f23"
PROBE_ID = 0xBEEF


def held_elsewhere() -> bool:
    """Whether some thread other than this one holds COMBO right now."""
    mods, vk = hotkeys.parse(COMBO)
    if hotkeys.user32.RegisterHotKey(None, PROBE_ID, mods, vk):
        hotkeys.user32.UnregisterHotKey(None, PROBE_ID)
        return False
    return True


def settle():
    time.sleep(hotkeys.CHECK_MS / 1000 * 3)


game_in_front = False
keys = hotkeys.Hotkeys(active=lambda: game_in_front)
keys.bind(COMBO, lambda: None)
keys.start()
try:
    settle()
    check("with the game not in front, the key is left for other programs", not held_elsewhere())
    game_in_front = True
    settle()
    check("switching to the game takes the key up", held_elsewhere())
    game_in_front = False
    settle()
    check("switching away gives it back", not held_elsewhere())
    game_in_front = True
    settle()
    check("and switching back takes it again", held_elsewhere())
finally:
    keys.stop()
    time.sleep(0.5)
check("stopping lets it go for good", not held_elsewhere())

always = hotkeys.Hotkeys()
always.bind(COMBO, lambda: None)
always.start()
try:
    settle()
    check("without a condition, as the tools use it, the key is held from the start", held_elsewhere())
finally:
    always.stop()
    time.sleep(0.5)

print()
print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
