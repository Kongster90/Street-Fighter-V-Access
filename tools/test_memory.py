"""Check the process-memory layer against this very process.

Reading ourselves exercises every part of it, and the expected answers are
known, so a failure here is a bug in the reader rather than a wrong guess about
the game.
"""

import ctypes
import os
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access.memory import ProcessMemory  # noqa: E402

ok = True


def check(label, condition, detail=""):
    global ok
    if condition:
        print(f"PASS  {label}{(': ' + detail) if detail else ''}")
    else:
        ok = False
        print(f"FAIL  {label}{(': ' + detail) if detail else ''}")


# A distinctive value to go looking for in our own heap.
MARKER = b"SFV_ACCESS_MEMORY_PROBE_7f3a91c4"
holder = bytearray(MARKER)

with ProcessMemory(os.getpid()) as pm:
    mods = pm.modules()
    check("module enumeration", len(mods) > 3, f"{len(mods)} modules")

    exe = next((m for m in mods if m.name.lower().endswith("python.exe")), None)
    check("found python.exe", exe is not None, exe.name if exe else "missing")

    if exe:
        head = pm.read(exe.base, 2)
        check("read PE header", head == b"MZ", repr(head))

        text = pm.section(exe, ".text")
        check(
            "locate .text section",
            text is not None and text.size > 0,
            f"base 0x{text.base:x} size 0x{text.size:x}" if text else "not found",
        )

    # Scalar reads against a buffer whose address and contents we know.
    probe = ctypes.create_string_buffer(struct.pack("<IQf", 0xDEADBEEF, 0x1122334455667788, 1.5))
    addr = ctypes.addressof(probe)
    check("read u32", pm.u32(addr) == 0xDEADBEEF, hex(pm.u32(addr) or 0))
    check("read u64", pm.u64(addr + 4) == 0x1122334455667788, hex(pm.u64(addr + 4) or 0))
    check("read f32", abs((pm.f32(addr + 12) or 0) - 1.5) < 1e-6)

    text_probe = ctypes.create_string_buffer(b"hello world")
    check("read c string", pm.cstring(ctypes.addressof(text_probe)) == "hello world")

    wide = ctypes.create_unicode_buffer("wide text")
    check("read wide string", pm.wstring(ctypes.addressof(wide)) == "wide text")

    check("bad address returns None", pm.read(0x10, 8) is None)

    regions = pm.regions()
    total = sum(r.size for r in regions)
    check("region walk", len(regions) > 10, f"{len(regions)} regions, {total / 1e6:.0f} MB readable")

    # Byte search across the whole address space, which is the operation the
    # name-table hunt depends on.
    t0 = time.perf_counter()
    hits = pm.find_bytes(MARKER, regions, limit=4)
    dt = time.perf_counter() - t0
    check("byte search finds the marker", len(hits) >= 1, f"{len(hits)} hits in {dt:.1f} s")

    if hits:
        back = pm.read(hits[0], len(MARKER))
        check("search hit reads back", back == MARKER)

        # Pointer search, limited to the region holding the marker to keep it quick.
        holding = [r for r in regions if r.base <= hits[0] < r.end]
        ptrs = pm.find_pointers_to(hits[0], holding, limit=4)
        print(f"INFO  pointers to the marker within its own region: {len(ptrs)}")

print()
print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
