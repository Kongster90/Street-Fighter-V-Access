"""Locating the Street Fighter V process and its window."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

EXE_NAME = "StreetFighterV.exe"


@dataclass
class GameWindow:
    hwnd: int
    pid: int
    title: str
    rect: tuple[int, int, int, int]  # left, top, right, bottom, screen coords

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

        found.append(
            GameWindow(
                hwnd=hwnd,
                pid=pid.value,
                title=title,
                rect=(rect.left, rect.top, rect.right, rect.bottom),
            )
        )
        return True

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
