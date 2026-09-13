"""System-wide hotkeys.

RegisterHotKey is handled by the window manager, so these keep working while
Street Fighter V has focus, including in fullscreen.  Registration and the
message pump must live on the same thread, so this class owns one; handlers
run on a separate worker so a slow read never stalls the pump.
"""

from __future__ import annotations

import ctypes
import queue
import threading
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

_MODS = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
}

_KEYS = {
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "space": 0x20, "enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "tab": 0x09, "backspace": 0x08, "delete": 0x2E, "insert": 0x2D,
    "comma": 0xBC, "period": 0xBE, "slash": 0xBF, "semicolon": 0xBA,
    "minus": 0xBD, "equals": 0xBB, "grave": 0xC0,
    "lbracket": 0xDB, "rbracket": 0xDD, "backslash": 0xDC, "quote": 0xDE,
}
for _i in range(1, 25):
    _KEYS[f"f{_i}"] = 0x6F + _i
for _i in range(10):
    _KEYS[f"numpad{_i}"] = 0x60 + _i


def parse(combo: str) -> tuple[int, int]:
    """'alt+r' -> (modifier mask, virtual key code)."""
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    if not parts:
        raise ValueError(f"empty hotkey: {combo!r}")
    mods = 0
    for p in parts[:-1]:
        if p not in _MODS:
            raise ValueError(f"unknown modifier {p!r} in {combo!r}")
        mods |= _MODS[p]
    key = parts[-1]
    if key in _KEYS:
        vk = _KEYS[key]
    elif len(key) == 1:
        vk = ord(key.upper())
    else:
        raise ValueError(f"unknown key {key!r} in {combo!r}")
    return mods | MOD_NOREPEAT, vk


class Hotkeys:
    def __init__(self) -> None:
        self._bindings: dict[str, tuple[int, int]] = {}
        self._handlers: dict[str, callable] = {}
        self._ids: dict[int, str] = {}
        self._failed: list[str] = []
        self._jobs: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._tid = 0
        self._ready = threading.Event()
        self._stop = threading.Event()

    def bind(self, combo: str, handler) -> None:
        self._bindings[combo] = parse(combo)
        self._handlers[combo] = handler

    @property
    def failed(self) -> list[str]:
        """Combos another program already owns."""
        return list(self._failed)

    def start(self) -> None:
        threading.Thread(target=self._worker, daemon=True).start()
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()
        self._ready.wait(5.0)

    def stop(self) -> None:
        self._stop.set()
        if self._tid:
            user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
        self._jobs.put(None)

    # ---------------------------------------------------------------- internals
    def _worker(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            try:
                job()
            except Exception as exc:
                print(f"[hotkey handler error] {exc}")

    def _pump(self) -> None:
        self._tid = kernel_thread_id()
        for i, (combo, (mods, vk)) in enumerate(self._bindings.items(), start=1):
            if user32.RegisterHotKey(None, i, mods, vk):
                self._ids[i] = combo
            else:
                self._failed.append(combo)
        self._ready.set()

        msg = wintypes.MSG()
        while not self._stop.is_set():
            got = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if got in (0, -1):
                break
            if msg.message == WM_HOTKEY:
                combo = self._ids.get(msg.wParam)
                if combo:
                    self._jobs.put(self._handlers[combo])

        for hk_id in self._ids:
            user32.UnregisterHotKey(None, hk_id)


def kernel_thread_id() -> int:
    return ctypes.WinDLL("kernel32", use_last_error=True).GetCurrentThreadId()
