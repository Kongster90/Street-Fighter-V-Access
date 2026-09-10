"""Give UE4SS an address for the one function it cannot find in this build.

UE4SS refuses to start unless it can locate StaticConstructObject_Internal,
which it hooks so that mods can be told when the game creates an object. That
function does not exist under that name in Unreal 4.7; it was split out of
plain StaticConstructObject several releases later. So there is nothing for its
pattern to match, and it stops with a fatal error having already found both the
things that were supposed to be hard.

Nothing this project wants needs to know when an object is created. So rather
than reverse engineering 4.7's equivalent, this points UE4SS at a stretch of
padding between two functions: real executable memory that nothing ever calls.
The hook installs into dead space, the scan succeeds, and everything else comes
up. Object construction callbacks silently never fire, which is the whole cost.

Compilers pad between functions with 0xCC, the breakpoint instruction, so a
long run of it is both easy to find and certainly not code. The signature file
cannot hold an address directly, only a byte pattern, so this anchors on the
unique bytes ending the function before the padding and steps forward from the
match.

The game must be running, because its code is encrypted on disk by Steam's DRM
wrapper and only exists in the clear in memory.

Usage:
    python tools/ue4ss_inert_signature.py            find and report
    python tools/ue4ss_inert_signature.py --apply    write the signature file
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access.memory import ProcessMemory, find_pid  # noqa: E402

EXE = "StreetFighterV.exe"
WIN64 = Path(
    r"G:\Steam\steamapps\common\StreetFighterV\StreetFighterV\Binaries\Win64"
)
SIGNATURE = WIN64 / "UE4SS_Signatures" / "StaticConstructObject.lua"

PAD = 0xCC
# This executable pads sparingly: 1,089 runs of sixteen bytes or more across
# 46 MB of code, and none longer than twenty-odd. Twenty is enough room for the
# fourteen byte absolute jump a hook writes, with margin, and short enough that
# there are plenty to choose from.
MIN_PAD = 20
ANCHOR = 20  # bytes of real code before it, as the thing to match on
# Land at the start of the run. Anywhere further in leaves less room for the
# jump than the run has, and the byte before the run is real code we must not
# overwrite.
INTO_PAD = 0

LUA = '''-- Street Fighter V, Unreal Engine 4.7. Written by
-- tools/ue4ss_inert_signature.py; do not edit by hand.
--
-- UE4SS will not start without an address for StaticConstructObject_Internal,
-- which 4.7 does not have: it was split out of StaticConstructObject several
-- releases later, so its pattern has nothing to match and it gives up having
-- already found the name table and the object array.
--
-- This deliberately points it at padding between two functions rather than at
-- any real code. That is executable memory nothing ever calls, so the hook
-- lands in dead space and the rest of UE4SS starts. The cost is that mods are
-- never told when an object is constructed, which nothing here needs.
--
-- The match is the {anchor} bytes ending the function before the padding,
-- which occur exactly once in the module. The padding itself is all one byte
-- repeated and would match in thousands of places.
--
-- Anchor at {exe}+{anchor_off:#x}, padding run of {pad_len} bytes.

function Register()
    return "{pattern}"
end

function OnMatchFound(MatchAddress)
    return MatchAddress + {step}
end
'''


def main() -> None:
    pid = find_pid(EXE, path_contains=r"Binaries\Win64")
    if pid is None:
        raise SystemExit(f"{EXE} is not running. Start the game first.")

    with ProcessMemory(pid) as pm:
        module = next(m for m in pm.modules() if m.name.lower() == EXE.lower())
        text = pm.section(module, ".text")
        if text is None:
            raise SystemExit("no .text section found")
        print(f"{EXE} pid {pid}, .text {text.size:,} bytes at {text.base:#x}")

        blob = pm.read(text.base, text.size)
        if blob is None or len(blob) < text.size // 2:
            raise SystemExit("could not read .text")

        # Search well inside the section, so we are between real functions
        # rather than in whatever sits at either end of it.
        runs = [
            m for m in re.finditer(rb"\xcc{%d,}" % MIN_PAD, blob)
            if text.size * 0.1 < m.start() < text.size * 0.9
        ]
        print(f"{len(runs)} padding runs of {MIN_PAD}+ bytes in the middle of .text")

        for run in runs:
            anchor_at = run.start() - ANCHOR
            anchor = blob[anchor_at : run.start()]
            if anchor.count(bytes([PAD])) or len(set(anchor)) < 6:
                continue  # too close to other padding, or too repetitive to be unique
            if blob.count(anchor) != 1:
                continue
            pad_len = run.end() - run.start()
            break
        else:
            raise SystemExit("found no padding run with a unique anchor before it")

        pattern = " ".join(f"{b:02X}" for b in anchor)
        step = ANCHOR + INTO_PAD
        target = text.base + run.start() + INTO_PAD
        print(f"\nanchor  {EXE}+{anchor_at:#x}, {ANCHOR} bytes, unique in .text")
        print(f"        {pattern}")
        print(f"padding {pad_len} bytes, hook would land at {EXE}+{run.start() + INTO_PAD:#x}")
        print(f"        live address this run {target:#x}")

        text_lua = LUA.format(
            anchor=ANCHOR,
            exe=EXE,
            anchor_off=anchor_at,
            pad_len=pad_len,
            pattern=pattern,
            step=step,
        )

    if "--apply" not in sys.argv:
        print("\nrun again with --apply to write the signature file")
        return

    SIGNATURE.parent.mkdir(parents=True, exist_ok=True)
    SIGNATURE.write_text(text_lua, encoding="utf-8")
    print(f"\nwrote {SIGNATURE}")
    print("restart the game, then read the log with tools/ue4ss_log.py")


if __name__ == "__main__":
    main()
