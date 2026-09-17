"""System-wide hotkeys, held only while they are wanted.

RegisterHotKey is handled by the window manager, so these keep working while
Street Fighter V has focus, including in fullscreen.  Registration and the
message pump must live on the same thread, so this class owns one; handlers
run on a separate worker so a slow read never stalls the pump.

A registered hotkey is taken from every program, so while the mod ran, Alt D
stopped reaching the browser's address bar and Alt R and the rest did nothing
anywhere else. Given `active`, the pump registers the keys only while it holds
(the mod passes "the game is in front") and gives them back as soon as it does
not, looking every `CHECK_MS`.
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
PM_NOREMOVE = 0x0000
PM_REMOVE = 0x0001
QS_ALLINPUT = 0x04FF
# How often the pump asks whether the keys are wanted. A key pressed straight
# after switching to the game waits at most this long to work.
CHECK_MS = 200

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
    def __init__(self, active=None, on_taken=None) -> None:
        # Called on the pump thread; the keys are held only while it is true.
        # None holds them for as long as the pump runs, as the tools want.
        self._active = active
        self._held = False
        # Told, on the worker, which combos another program owned each time
        # the keys are taken up and some could not be.
        self._on_taken = on_taken
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

    def _hold(self) -> None:
        self._failed = []
        for i, (combo, (mods, vk)) in enumerate(self._bindings.items(), start=1):
            if user32.RegisterHotKey(None, i, mods, vk):
                self._ids[i] = combo
            else:
                self._failed.append(combo)
        if self._failed and self._on_taken is not None:
            failed = list(self._failed)
            self._jobs.put(lambda: self._on_taken(failed))
        self._held = True

    def _release(self) -> None:
        for hk_id in self._ids:
            user32.UnregisterHotKey(None, hk_id)
        self._ids.clear()
        self._held = False

    def _wanted(self) -> bool:
        try:
            return bool(self._active())
        except Exception:
            return self._held   # keep things as they are rather than flap

    def _pump(self) -> None:
        self._tid = kernel_thread_id()
        msg = wintypes.MSG()
        # Make this thread's message queue now, so a stop posted before the
        # first wait is not lost.
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_NOREMOVE)
        if self._active is None:
            self._hold()
        self._ready.set()

        while not self._stop.is_set():
            if self._active is not None:
                wanted = self._wanted()
                if wanted and not self._held:
                    self._hold()
                elif not wanted and self._held:
                    self._release()
            user32.MsgWaitForMultipleObjects(0, None, False, CHECK_MS, QS_ALLINPUT)
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                if msg.message == WM_QUIT:
                    self._stop.set()
                    break
                if msg.message == WM_HOTKEY:
                    combo = self._ids.get(msg.wParam)
                    if combo:
                        self._jobs.put(self._handlers[combo])

        self._release()


def kernel_thread_id() -> int:
    return ctypes.WinDLL("kernel32", use_last_error=True).GetCurrentThreadId()
