"""Walk up the call graph from a confirmed address to find object construction.

Earlier attempts guessed at the answer and tested the guesses, which cost a
crash each. This works the other way: from an address UE4SS located for us,
follow who calls it, and who calls them.

Registering a new object has to reach `FUObjectHashTables::Get`, because an
object is hashed so it can later be found by name. The chain above it is fixed
by the engine:

    construction -> allocation -> the object base -> hashing -> Get

So construction sits three or four calls above that function, and the layers
between are narrow. Walking up from a known point beats guessing downwards.

The part that makes this work where the previous attempt did not is knowing
where functions begin. Looking for compiler padding was unreliable, because
this binary does not pad consistently. But every address that a `call`
instruction targets is by definition the start of a function, and there are
tens of thousands of those, so the function containing any address is the
nearest such target at or before it. That boundary set is derived from the
code rather than guessed at.

Reads memory only. The game must be running.

Usage:
    python tools/walk_callers.py [levels]
"""

from __future__ import annotations

import bisect
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access.memory import ProcessMemory, find_pid  # noqa: E402

EXE = "StreetFighterV.exe"
# Located by UE4SS's own scan on this build, so not a guess.
HASH_TABLES_GET = 0x11B7370
# Slots 5 to 8 of the calling convention. 4.7 declares construction with eight
# arguments, so its call sites fill all four.
SLOTS = (0x20, 0x28, 0x30, 0x38)
WINDOW = 96


def main() -> None:
    levels = int(sys.argv[1]) if len(sys.argv) > 1 else 4

    pid = find_pid(EXE, path_contains=r"Binaries\Win64")
    if pid is None:
        raise SystemExit(f"{EXE} is not running. Start the game first.")

    with ProcessMemory(pid) as pm:
        module = next(m for m in pm.modules() if m.name.lower() == EXE.lower())
        text = pm.section(module, ".text")
        blob = pm.read(text.base, text.size)
        if not blob:
            raise SystemExit("could not read .text")
        a = np.frombuffer(blob, dtype=np.uint8)
        tb = text.base - module.base

        sites = np.flatnonzero(a[:-5] == 0xE8)
        disp = (
            a[sites + 1].astype(np.int64)
            | (a[sites + 2].astype(np.int64) << 8)
            | (a[sites + 3].astype(np.int64) << 16)
            | (a[sites + 4].astype(np.int64) << 24)
        )
        disp = np.where(disp >= 1 << 31, disp - (1 << 32), disp)
        targets = sites + 5 + disp
        keep = (targets >= 0) & (targets < len(blob) - 8)
        sites, targets = sites[keep].tolist(), targets[keep].tolist()
        print(f"{len(sites):,} calls, {len(set(targets)):,} distinct targets")

        # Every called address starts a function. That is the boundary set.
        starts = sorted(set(targets))
        print(f"{len(starts):,} function starts derived from call targets")

        def containing(offset: int) -> int | None:
            i = bisect.bisect_right(starts, offset) - 1
            return starts[i] if i >= 0 else None

        callers_of: dict[int, Counter] = {}
        for s, t in zip(sites, targets):
            owner = containing(s)
            if owner is not None and owner != t:
                callers_of.setdefault(t, Counter())[owner] += 1

        def stack_slots(fn: int) -> float:
            """How many stack argument slots this function's call sites fill."""
            ss = [s for s, t in zip(sites, targets) if t == fn][:16]
            if not ss:
                return 0.0
            return sum(
                sum(1 for off in SLOTS
                    if bytes([0x44, 0x24, off]) in blob[max(0, s - WINDOW):s])
                for s in ss
            ) / len(ss)

        level = {HASH_TABLES_GET - tb: 0}
        frontier = [HASH_TABLES_GET - tb]
        for depth in range(1, levels + 1):
            nxt = []
            for fn in frontier:
                for owner in callers_of.get(fn, ()):
                    if owner not in level:
                        level[owner] = depth
                        nxt.append(owner)
            frontier = nxt
            print(f"  level {depth}: {len(frontier):,} functions")

        print("\nCandidates three or four calls above the hash tables whose own")
        print("call sites fill the four stack slots an eight argument function")
        print("needs. Construction should be among these.\n")

        rows = []
        for fn, depth in level.items():
            if depth < 3:
                continue
            n = len(callers_of.get(fn, ()))
            if n < 3:
                continue
            slots = stack_slots(fn)
            if slots >= 2.5:
                rows.append((slots, n, depth, fn))
        rows.sort(reverse=True)

        for slots, n, depth, fn in rows[:20]:
            off = tb + fn
            head = " ".join(f"{b:02X}" for b in blob[fn : fn + 8])
            print(f"  +{off:#09x}  live {module.base + off:#x}  depth {depth}  "
                  f"{n:5d} callers  {slots:.2f} slots  {head}")
        if not rows:
            print("  none; try more levels")


if __name__ == "__main__":
    main()
