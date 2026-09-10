"""Measure how many arguments a function takes, by disassembling it.

Every previous attempt inferred a function's arity from its call sites, by
looking for writes to the stack slots the caller fills. That is indirect, and
it is where the search kept going wrong: a caller may fill slots for a
different call, or set them up further back than the window looked.

This reads it from the function itself. On this calling convention the first
four arguments arrive in registers and the rest are already on the caller's
stack, above the return address. So inside the callee, after it has adjusted
the stack, the fifth argument onwards appear at fixed positions relative to the
frame. Counting the distinct ones a function reads gives its arity directly.

Unreal 4.7 declares:

  UObject* StaticConstructObject(UClass*, UObject* Outer, FName, EObjectFlags,
                                 UObject* Template, bool, FObjectInstancingGraph*, bool)

Eight arguments, so four read off the stack. Combined with sitting a few calls
above `FUObjectHashTables::Get`, which UE4SS located on this build and is
therefore not a guess, that should be a small enough set to act on.

Reads memory only. The game must be running.

Usage:
    python tools/find_construct_arity.py [levels]
"""

from __future__ import annotations

import bisect
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from capstone import CS_ARCH_X86, CS_MODE_64, Cs
from capstone.x86 import X86_OP_MEM, X86_REG_RSP

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access.memory import ProcessMemory, find_pid  # noqa: E402

EXE = "StreetFighterV.exe"
HASH_TABLES_GET = 0x11B7370  # confirmed by UE4SS's own scan on this build
MAX_FUNC = 0x2000


def incoming_stack_args(md: Cs, code: bytes, at: int) -> tuple[int, int]:
    """Distinct incoming stack arguments read, and the frame size.

    The frame is whatever the function subtracts from the stack pointer plus
    the registers it pushes. Above that sit the return address and then the
    caller's argument slots, so a read at frame + 8 + 0x20 is the fifth
    argument, + 0x28 the sixth, and so on.
    """
    frame = 0
    pushes = 0
    slots: set[int] = set()
    started = False

    for insn in md.disasm(code, at):
        if insn.mnemonic == "push" and not started:
            pushes += 8
            continue
        if insn.mnemonic == "sub" and insn.op_str.startswith("rsp,"):
            try:
                frame += int(insn.op_str.split(",")[1].strip(), 0)
            except ValueError:
                pass
            started = True
            continue
        if insn.mnemonic in ("ret", "jmp") and slots:
            break
        started = True
        for op in insn.operands:
            if op.type != X86_OP_MEM or op.mem.base != X86_REG_RSP:
                continue
            # Argument five sits just past the frame and the return address.
            rel = op.mem.disp - (frame + pushes + 8)
            if 0x20 <= rel <= 0x60 and rel % 8 == 0:
                slots.add(rel)
    return len(slots), frame + pushes


def main() -> None:
    levels = int(sys.argv[1]) if len(sys.argv) > 1 else 6

    pid = find_pid(EXE, path_contains=r"Binaries\Win64")
    if pid is None:
        raise SystemExit(f"{EXE} is not running. Start the game first.")

    md = Cs(CS_ARCH_X86, CS_MODE_64)
    md.detail = True

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
        starts = sorted(set(targets))
        ncall = Counter(targets)
        print(f"{len(sites):,} calls, {len(starts):,} function starts")

        def containing(offset: int) -> int | None:
            i = bisect.bisect_right(starts, offset) - 1
            return starts[i] if i >= 0 else None

        callers_of: dict[int, set] = {}
        for s, t in zip(sites, targets):
            owner = containing(s)
            if owner is not None and owner != t:
                callers_of.setdefault(t, set()).add(owner)

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
        print(f"{len(level):,} functions within {levels} calls of the hash tables\n")

        rows = []
        for fn, depth in level.items():
            if depth < 2:
                continue
            end = min(fn + MAX_FUNC, len(blob))
            args, frame = incoming_stack_args(md, blob[fn:end], text.base + fn)
            if args >= 3:
                rows.append((args, ncall[fn], depth, frame, fn))
        rows.sort(reverse=True)

        print("Functions reading three or more incoming stack arguments.")
        print("Construction reads four. Most callers first within each arity.\n")
        for args, n, depth, frame, fn in rows[:24]:
            off = tb + fn
            head = " ".join(f"{b:02X}" for b in blob[fn : fn + 6])
            print(f"  +{off:#09x}  live {module.base + off:#x}  "
                  f"{args} stack args  depth {depth}  {n:5d} callers  "
                  f"frame {frame:#x}  {head}")
        if not rows:
            print("  none found; try more levels")


if __name__ == "__main__":
    main()
