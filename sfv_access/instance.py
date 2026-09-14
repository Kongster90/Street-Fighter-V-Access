"""Telling from outside whether a copy of the mod is already running.

Hotkeys refuse a second copy, but only once it has started, spoken and found
its keys taken. Starting with the game has to know before starting anything, so
the mod holds a named mutex for as long as it runs and `start_with_game.pyw`
looks for it. Windows removes the mutex when the last process holding it exits,
however that happens.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.OpenMutexW.restype = wintypes.HANDLE
kernel32.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

NAME = "Local\\StreetFighterVAccess"
SYNCHRONIZE = 0x00100000

# Handles this process holds, kept open until it exits.
_held: dict[str, int] = {}


def claim(name: str = NAME) -> None:
    """Mark this process as a running copy until it exits."""
    if name not in _held:
        _held[name] = kernel32.CreateMutexW(None, False, name)


def already_running(name: str = NAME) -> bool:
    """Whether some process, this one included, has claimed the name."""
    handle = kernel32.OpenMutexW(SYNCHRONIZE, False, name)
    if not handle:
        return False
    kernel32.CloseHandle(handle)
    return True
