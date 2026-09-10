"""Find Unreal 4.7's object construction function in this build.

UE4SS needs the address of the function that constructs objects. It cannot find
it here, because it looks for `StaticConstructObject_Internal`, which arrived
several engine releases after 4.7, and because it locates it via a call inside
`UUserWidget::InitializeInputComponent`, a class this engine version predates.
Pointing it at inert padding does not work: it calls the function rather than
merely hooking it, and calling padding executes a breakpoint and stops the game.

So the real one has to be found. The method is the one that found this
project's other landmarks, which is to follow references from something certain
rather than to match byte patterns that were written for other builds:

1. Constructing an object must register it in the global object array, whose
   address this project already knows. Every instruction in the code that
   refers to that array is found by checking, at every offset, whether the four
   bytes there are a displacement that lands on it.
2. Each reference is inside some function. MSVC pads between functions with
   0xCC, so walking back to the end of the previous padding run gives the
   function's first byte.
3. Those functions are the low-level allocation machinery. What calls them is
   the layer above. Every `call` instruction reaching each one is counted.

Construction is called from everywhere a UObject is made, so among the
candidates it is the one with by far the most callers, while the allocation
function beneath it has few. That ratio is the identification, and it is
reported rather than assumed so it can be judged rather than trusted.

Reads memory only, and changes nothing. The game must be running, with or
without UE4SS: its code is encrypted on disk and readable only in memory.

Usage:
    python tools/find_construct.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access.memory import ProcessMemory, find_pid  # noqa: E402

EXE = "StreetFighterV.exe"
# The array head this project reads, and the struct wrapping it. Code touching
# either is worth following.
TARGETS = (0x3978730, 0x3978720)
PAD = 0xCC
MAX_BACK = 0x4000  # how far back to look for the start of a function


def references_to(blob: bytes, text_va: int, target_va: int) -> list[int]:
    """Offsets whose next four bytes are a displacement landing on `target_va`.

    Deliberately not a disassembler. Every RIP-relative access encodes its
    displacement the same way, relative to the end of the instruction, so
    checking every offset finds them all whatever the opcode, at the cost of
    the occasional coincidence. A wrong hit here costs a candidate to discard,
    not a wrong answer, because everything after this is corroborated.

    Done as array arithmetic rather than a loop. There are 46 million offsets
    and four instruction lengths to consider at each, which a Python loop does
    not finish in any useful time. Rearranged, the test is that the
    displacement plus the offset equals a constant, so each pass is one
    comparison over the whole section.
    """
    a = np.frombuffer(blob, dtype=np.uint8)
    n = len(a) - 4
    out: list[int] = []
    # In chunks, because the intermediate arrays are eight bytes per input byte
    # and the section is large enough for that to matter.
    step = 1 << 22
    for base in range(0, n, step):
        end = min(base + step, n)
        chunk = a[base : end + 4]
        disp = (
            chunk[:-4].astype(np.int64)
            | (chunk[1:-3].astype(np.int64) << 8)
            | (chunk[2:-2].astype(np.int64) << 16)
            | (chunk[3:-1].astype(np.int64) << 24)
        )
        disp = np.where(disp >= 1 << 31, disp - (1 << 32), disp)
        index = np.arange(base, base + len(disp), dtype=np.int64)
        # text_va + i + 4 + tail + disp == target_va
        want = target_va - text_va - 4
        total = disp + index
        for tail in (0, 1, 2, 4):
            for hit in np.flatnonzero(total == want - tail):
                out.append(int(base + hit))
    return sorted(set(out))


def function_start(blob: bytes, at: int) -> int | None:
    """Walk back to the first byte after the previous run of padding."""
    run = 0
    for i in range(at, max(0, at - MAX_BACK), -1):
        if blob[i] == PAD:
            run += 1
            if run >= 4:
                return i + run
        else:
            run = 0
    return None


def call_targets(blob: bytes, text_va: int) -> Counter:
    """Where every `call rel32` in the section points, counted.

    Built once and looked up, rather than scanning the whole section again per
    candidate. `E8` also appears inside other instructions and inside data, so
    some of these counts are noise; that matters little, because what is being
    compared is one function called from thousands of places against others
    called from a handful.
    """
    a = np.frombuffer(blob, dtype=np.uint8)
    sites = np.flatnonzero(a[:-5] == 0xE8)
    disp = (
        a[sites + 1].astype(np.int64)
        | (a[sites + 2].astype(np.int64) << 8)
        | (a[sites + 3].astype(np.int64) << 16)
        | (a[sites + 4].astype(np.int64) << 24)
    )
    disp = np.where(disp >= 1 << 31, disp - (1 << 32), disp)
    return Counter((sites + 5 + disp).tolist())


def main() -> None:
    pid = find_pid(EXE, path_contains=r"Binaries\Win64")
    if pid is None:
        raise SystemExit(f"{EXE} is not running. Start the game first.")

    with ProcessMemory(pid) as pm:
        module = next(m for m in pm.modules() if m.name.lower() == EXE.lower())
        text = pm.section(module, ".text")
        blob = pm.read(text.base, text.size)
        if not blob:
            raise SystemExit("could not read .text")
        print(f"{EXE} pid {pid}, base {module.base:#x}, .text {text.size:,} bytes")

        starts: Counter[int] = Counter()
        for target in TARGETS:
            va = module.base + target
            refs = references_to(blob, text.base, va)
            print(f"\n{EXE}+{target:#x}: {len(refs)} references")
            for r in refs:
                fn = function_start(blob, r)
                if fn is not None:
                    starts[fn] += 1

        if not starts:
            raise SystemExit("no functions found touching the object array")

        calls = call_targets(blob, text.base)
        print(f"\n{len(starts)} distinct functions touch it. Their callers:\n")
        rows = sorted(
            ((calls.get(fn, 0), fn, refs) for fn, refs in starts.items()),
            reverse=True,
        )

        for n, fn, refs in rows[:20]:
            off = (text.base - module.base) + fn
            print(f"  {EXE}+{off:#09x}   live {module.base + off:#x}   "
                  f"{n:5d} callers, {refs} reference{'s' if refs > 1 else ''}")

        print("\nThe construction function is called from everywhere a UObject is")
        print("made, so expect it to have far more callers than the allocation")
        print("machinery beneath it. Check that the top of this list stands well")
        print("clear of the rest before believing any of it.")


if __name__ == "__main__":
    main()
