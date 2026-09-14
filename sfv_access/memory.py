"""Reading another process's memory.

This is the foundation for finding Unreal's name and object tables inside the
running game. Reads are done from outside rather than from injected code
because a wrong pointer then returns a failed read instead of crashing the
game, and the mapping work that comes out of it transfers unchanged to an
injected library later.

Street Fighter V's executable is wrapped in Steam's DRM, so its code is only
decrypted in memory. Nothing here can be derived from the file on disk.
"""

from __future__ import annotations

import ctypes
import struct
from ctypes import wintypes
from dataclasses import dataclass

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
LIST_MODULES_ALL = 0x03

MEM_COMMIT = 0x1000
PAGE_GUARD = 0x100
PAGE_NOACCESS = 0x01
READABLE = 0x02 | 0x04 | 0x20 | 0x40 | 0x80  # R, RW, XR, XRW, XWC


class MEMORY_BASIC_INFORMATION64(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_ulonglong),
        ("AllocationBase", ctypes.c_ulonglong),
        ("AllocationProtect", wintypes.DWORD),
        ("__alignment1", wintypes.DWORD),
        ("RegionSize", ctypes.c_ulonglong),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("__alignment2", wintypes.DWORD),
    ]


class MODULEINFO(ctypes.Structure):
    _fields_ = [
        ("lpBaseOfDll", ctypes.c_void_p),
        ("SizeOfImage", wintypes.DWORD),
        ("EntryPoint", ctypes.c_void_p),
    ]


kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.ReadProcessMemory.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_size_t),
]
kernel32.VirtualQueryEx.restype = ctypes.c_size_t
kernel32.VirtualQueryEx.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    ctypes.POINTER(MEMORY_BASIC_INFORMATION64),
    ctypes.c_size_t,
]

# Without these, ctypes narrows module handles to int and overflows on x64.
psapi.EnumProcessModulesEx.restype = wintypes.BOOL
psapi.EnumProcessModulesEx.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(wintypes.HMODULE),
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    wintypes.DWORD,
]
psapi.GetModuleBaseNameW.restype = wintypes.DWORD
psapi.GetModuleBaseNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.HMODULE,
    wintypes.LPWSTR,
    wintypes.DWORD,
]
psapi.GetModuleInformation.restype = wintypes.BOOL
psapi.GetModuleInformation.argtypes = [
    wintypes.HANDLE,
    wintypes.HMODULE,
    ctypes.POINTER(MODULEINFO),
    wintypes.DWORD,
]


@dataclass(frozen=True)
class Region:
    base: int
    size: int
    protect: int

    @property
    def end(self) -> int:
        return self.base + self.size


@dataclass(frozen=True)
class Module:
    name: str
    base: int
    size: int

    @property
    def end(self) -> int:
        return self.base + self.size


class ProcessMemory:
    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.handle = kernel32.OpenProcess(
            PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid
        )
        if not self.handle:
            raise OSError(
                f"OpenProcess failed for pid {pid}: {ctypes.get_last_error()}. "
                "Run as the same user as the game."
            )

    def close(self) -> None:
        if self.handle:
            kernel32.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ------------------------------------------------------------------ reads
    def read(self, address: int, size: int) -> bytes | None:
        if address <= 0 or size <= 0:
            return None
        buf = ctypes.create_string_buffer(size)
        got = ctypes.c_size_t(0)
        ok = kernel32.ReadProcessMemory(
            self.handle, ctypes.c_void_p(address), buf, size, ctypes.byref(got)
        )
        if not ok or got.value == 0:
            return None
        return buf.raw[: got.value]

    def u8(self, a: int) -> int | None:
        b = self.read(a, 1)
        return b[0] if b else None

    def u32(self, a: int) -> int | None:
        b = self.read(a, 4)
        return struct.unpack("<I", b)[0] if b and len(b) == 4 else None

    def i32(self, a: int) -> int | None:
        b = self.read(a, 4)
        return struct.unpack("<i", b)[0] if b and len(b) == 4 else None

    def u64(self, a: int) -> int | None:
        b = self.read(a, 8)
        return struct.unpack("<Q", b)[0] if b and len(b) == 8 else None

    ptr = u64

    def f32(self, a: int) -> float | None:
        b = self.read(a, 4)
        return struct.unpack("<f", b)[0] if b and len(b) == 4 else None

    def cstring(self, a: int, limit: int = 256) -> str | None:
        b = self.read(a, limit)
        if not b:
            return None
        end = b.find(b"\0")
        return b[: end if end >= 0 else len(b)].decode("utf-8", "replace")

    def wstring(self, a: int, limit: int = 256) -> str | None:
        b = self.read(a, limit * 2)
        if not b:
            return None
        end = len(b)
        for i in range(0, len(b) - 1, 2):
            if b[i] == 0 and b[i + 1] == 0:
                end = i
                break
        return b[:end].decode("utf-16-le", "replace")

    # ---------------------------------------------------------------- mapping
    def modules(self) -> list[Module]:
        needed = wintypes.DWORD()
        arr = (wintypes.HMODULE * 1024)()
        if not psapi.EnumProcessModulesEx(
            self.handle, arr, ctypes.sizeof(arr), ctypes.byref(needed), LIST_MODULES_ALL
        ):
            return []
        count = min(needed.value // ctypes.sizeof(wintypes.HMODULE), 1024)
        out = []
        for i in range(count):
            name = ctypes.create_unicode_buffer(260)
            psapi.GetModuleBaseNameW(self.handle, arr[i], name, 260)
            info = MODULEINFO()
            if psapi.GetModuleInformation(
                self.handle, arr[i], ctypes.byref(info), ctypes.sizeof(info)
            ):
                out.append(Module(name.value, info.lpBaseOfDll or 0, info.SizeOfImage))
        return out

    def regions(self, max_size: int = 1 << 31) -> list[Region]:
        """Committed, readable, non-guard regions."""
        out: list[Region] = []
        addr = 0
        mbi = MEMORY_BASIC_INFORMATION64()
        while addr < 0x7FFFFFFFFFFF:
            got = kernel32.VirtualQueryEx(
                self.handle, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)
            )
            if not got:
                break
            if (
                mbi.State == MEM_COMMIT
                and (mbi.Protect & READABLE)
                and not (mbi.Protect & PAGE_GUARD)
                and mbi.RegionSize <= max_size
            ):
                out.append(Region(mbi.BaseAddress, mbi.RegionSize, mbi.Protect))
            nxt = mbi.BaseAddress + mbi.RegionSize
            if nxt <= addr:
                break
            addr = nxt
        return out

    def section(self, module: Module, name: str) -> Region | None:
        """One PE section of a loaded module, read from its in-memory headers."""
        head = self.read(module.base, 0x1000)
        if not head or head[:2] != b"MZ":
            return None
        pe = struct.unpack_from("<I", head, 0x3C)[0]
        if pe + 24 > len(head) or head[pe : pe + 4] != b"PE\0\0":
            return None
        nsec = struct.unpack_from("<H", head, pe + 6)[0]
        optsize = struct.unpack_from("<H", head, pe + 20)[0]
        want = name.encode().ljust(8, b"\0")
        for i in range(nsec):
            off = pe + 24 + optsize + i * 40
            if off + 40 > len(head):
                break
            if head[off : off + 8] == want:
                vsize, vaddr = struct.unpack_from("<II", head, off + 8)
                return Region(module.base + vaddr, vsize, 0)
        return None

    # ---------------------------------------------------------------- searching
    def find_bytes(
        self, needle: bytes, regions: list[Region], limit: int = 64, align: int = 1
    ) -> list[int]:
        """Every address in `regions` holding `needle`."""
        hits: list[int] = []
        chunk = 1 << 22
        overlap = len(needle) - 1
        for r in regions:
            addr = r.base
            while addr < r.end:
                size = min(chunk, r.end - addr)
                buf = self.read(addr, size)
                if buf:
                    start = 0
                    while True:
                        i = buf.find(needle, start)
                        if i < 0:
                            break
                        found = addr + i
                        if align == 1 or found % align == 0:
                            hits.append(found)
                            if len(hits) >= limit:
                                return hits
                        start = i + 1
                addr += size - overlap if size > overlap else size
        return hits

    def find_pointers_to(
        self, target: int, regions: list[Region], limit: int = 64
    ) -> list[int]:
        """Every 8-byte-aligned address holding the value `target`."""
        return self.find_bytes(struct.pack("<Q", target), regions, limit=limit, align=8)


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def process_path(pid: int) -> str:
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(h)


def list_processes(exe_name: str) -> list[tuple[int, str]]:
    """Every running process matching an executable name, with its full path."""
    count = 4096
    arr = (wintypes.DWORD * count)()
    needed = wintypes.DWORD()
    if not psapi.EnumProcesses(arr, ctypes.sizeof(arr), ctypes.byref(needed)):
        return []
    out = []
    for i in range(needed.value // ctypes.sizeof(wintypes.DWORD)):
        pid = arr[i]
        if not pid:
            continue
        path = process_path(pid)
        if path and path.rsplit("\\", 1)[-1].lower() == exe_name.lower():
            out.append((pid, path))
    return out


def find_pid(exe_name: str, path_contains: str | None = None, require_path: bool = False) -> int | None:
    """Process id for an executable, narrowed by a path fragment.

    Street Fighter V ships two executables with the same name: a small launcher
    in the install root and the real game under Binaries\\Win64. Matching on
    name alone picks the launcher, whose memory holds nothing of interest.

    Without `require_path` a name match is taken when nothing matches the
    path. Anything that will read the game's memory must require it: the
    launcher starts a moment before the game, and the mod, looking for the game
    again after it restarted, attached to the launcher and read nothing for
    the rest of the session.
    """
    matches = list_processes(exe_name)
    if not matches:
        return None
    if path_contains:
        narrowed = [m for m in matches if path_contains.lower() in m[1].lower()]
        if narrowed or require_path:
            matches = narrowed
    return matches[0][0] if matches else None
