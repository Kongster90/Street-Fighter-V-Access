"""Locating the Street Fighter V process and its window."""

from __future__ import annotations

import ctypes
from contextlib import contextmanager
from ctypes import wintypes
from dataclasses import dataclass

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

EXE_NAME = "StreetFighterV.exe"

# Asking Windows for positions as a program that knows about display scaling.
# The mod does not declare that it does, so with scaling at 150 percent, usual
# on a laptop, every position it asks for comes back shrunk to two thirds,
# while the capture is in the screen's own pixels.
_PER_MONITOR_AWARE_V2 = -4
try:
    user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
except AttributeError:      # older than Windows 10's anniversary update
    pass

# The game draws a 16 by 9 picture whatever shape its window is, and fills
# the rest with black: a tester's 1920 by 1200 screen had 60 rows of it above
# and below. Everything read off the picture is measured from the picture.
PICTURE_ASPECT = (16, 9)


@contextmanager
def _screen_pixels():
    """Positions asked for inside this come back in the screen's own pixels."""
    try:
        old = user32.SetThreadDpiAwarenessContext(_PER_MONITOR_AWARE_V2)
    except AttributeError:
        old = None
    try:
        yield
    finally:
        if old:
            user32.SetThreadDpiAwarenessContext(old)


def picture_box(client: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Where the game's picture is drawn inside `client`, as left, top, width, height.

    Centred, as wide or as tall as the space allows: black bars above and
    below on a screen taller than 16 by 9, at the sides on a wider one.
    """
    left, top, right, bottom = client
    width, height = right - left, bottom - top
    across, down = PICTURE_ASPECT
    if width * down > height * across:
        pw, ph = round(height * across / down), height
    else:
        pw, ph = width, round(width * down / across)
    return (left + (width - pw) // 2, top + (height - ph) // 2, pw, ph)


@dataclass
class GameWindow:
    hwnd: int
    pid: int
    title: str
    rect: tuple[int, int, int, int]  # left, top, right, bottom, screen coords
    # The part the game draws in, without a window's title bar and borders,
    # in the same coordinates. The whole window when it fills the screen.
    client: tuple[int, int, int, int] = (0, 0, 0, 0)

    @property
    def picture(self) -> tuple[int, int, int, int]:
        """Where the game's 16 by 9 picture sits on screen: left, top, width, height."""
        return picture_box(self.client)

    @property
    def width(self) -> int:
        return self.rect[2] - self.rect[0]

    @property
    def height(self) -> int:
        return self.rect[3] - self.rect[1]

    @property
    def is_foreground(self) -> bool:
        return user32.GetForegroundWindow() == self.hwnd


def in_front() -> bool:
    """Whether the window in front belongs to the game.

    Asked several times a second by the hotkeys, so it looks at the one window
    rather than enumerating them all as `find_window` does.
    """
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return bool(pid.value) and _process_name(pid.value).lower() == EXE_NAME.lower()


def _process_name(pid: int) -> str:
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        size = wintypes.DWORD(260)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value.rsplit("\\", 1)[-1]
        return ""
    finally:
        kernel32.CloseHandle(h)


def find_window(exe_name: str = EXE_NAME) -> GameWindow | None:
    """The game's top-level visible window, or None if it is not running."""
    found: list[GameWindow] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if _process_name(pid.value).lower() != exe_name.lower():
            return True

        length = user32.GetWindowTextLengthW(hwnd)
        title = ""
        if length:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value

        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        if (rect.right - rect.left) < 200 or (rect.bottom - rect.top) < 200:
            return True  # skip helper and splash windows

        inside = wintypes.RECT()
        corner = wintypes.POINT(0, 0)
        if user32.GetClientRect(hwnd, ctypes.byref(inside)) and                 user32.ClientToScreen(hwnd, ctypes.byref(corner)):
            client = (corner.x, corner.y, corner.x + inside.right, corner.y + inside.bottom)
        else:
            client = (rect.left, rect.top, rect.right, rect.bottom)

        found.append(
            GameWindow(
                hwnd=hwnd,
                pid=pid.value,
                title=title,
                rect=(rect.left, rect.top, rect.right, rect.bottom),
                client=client,
            )
        )
        return True

    with _screen_pixels():
        user32.EnumWindows(callback, 0)
    if not found:
        return None
    # Largest window wins if the game ever shows more than one.
    return max(found, key=lambda gw: gw.width * gw.height)


def is_running(exe_name: str = EXE_NAME) -> bool:
    """Whether the game process exists, regardless of its window.

    A minimised window reports an off-screen rectangle and is filtered out by
    `find_window`, so asking about the window would report the game as gone
    when it is running perfectly well and its memory is still readable.
    """
    from .memory import find_pid

    return find_pid(exe_name, path_contains=r"Binaries\Win64") is not None
