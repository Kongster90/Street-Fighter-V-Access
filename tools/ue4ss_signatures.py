"""Write the signature files UE4SS 3.x needs for this game.

UE4SS 3.0.1 detects Unreal 4.7 by itself and finds the allocator, the name
constructor and the name-to-string function unaided. Three things it cannot
find, and this supplies all three.

  GUObjectArray                 the engine's global object array
  StaticConstructObject_Internal  object construction
  FText::FText(FString&&)         text construction

The first is real and must be right. This project located the object array by
following references from an object guaranteed to exist, and has been reading
it all along. UE4SS wants the FUObjectArray that wraps that array rather than
the array itself, which sits 0x10 earlier: the example script UE4SS ships for
this signature ends by subtracting exactly that, and the four integers in front
of the array head here match the fields the engine keeps there.

The other two do not exist in 4.7. Object construction was split out of
StaticConstructObject several releases later, and this FText constructor came
later still, so there is nothing for either pattern to match. Neither is needed
by anything this project wants, so both are pointed at padding between two
functions: real executable memory that nothing calls. Their hooks land in dead
space. If UE4SS ever does call one, it will execute a breakpoint instruction
and the game will stop, which is the risk being taken knowingly.

A signature file holds a byte pattern, not an address, so each one matches on
bytes that occur exactly once in the module and steps from there to its target.

The game must be running: its code is encrypted on disk by Steam's DRM wrapper
and exists in the clear only in memory.

Usage:
    python tools/ue4ss_signatures.py            find and report
    python tools/ue4ss_signatures.py --apply    write the three files
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
def signature_dir() -> Path:
    """Where this build keeps its signature scripts.

    3.0.1 put everything loose beside the game executable. The experimental
    build puts it in a `ue4ss` folder next to it instead, with only the loader
    DLL left outside, so the working directory moves with it.
    """
    nested = WIN64 / "ue4ss"
    root = nested if (nested / "UE4SS-settings.ini").exists() else WIN64
    return root / "UE4SS_Signatures"

# The object array this project found and validated, and the wrapper UE4SS
# wants, which begins four integers earlier.
OBJECT_ARRAY = 0x3978730
GUOBJECTARRAY = OBJECT_ARRAY - 0x10

PAD = 0xCC
MIN_PAD = 20  # room for the fourteen byte jump a hook writes
ANCHOR = 20

LUA = '''-- Street Fighter V, Unreal Engine 4.7. Written by
-- tools/ue4ss_signatures.py; do not edit by hand.
--
{why}
--
-- Matches {anchor} bytes at {exe}+{anchor_off:#x}, which occur exactly once in
-- the module, then steps {step:+#x} to reach {exe}+{target_off:#x}.

function Register()
    return "{pattern}"
end

function OnMatchFound(MatchAddress)
    return MatchAddress + {step}
end
'''

# A signature file may instead return the address at file scope, which skips
# the scan entirely. That matters because the scan is the part failing: the
# same pattern that UE4SS accepts for one symbol it reports as never matching
# for these two, and they are looked for in a second pass whose code is in a
# submodule that cannot be cloned.
#
# The cost is that this address is absolute. The executable has ASLR on with
# high entropy, so its base moves, and while Windows keeps one base per image
# until it reboots, this file is stale after that and must be written again.
LUA_LITERAL = '''-- Street Fighter V, Unreal Engine 4.7. Written by
-- tools/ue4ss_signatures.py; do not edit by hand.
--
{why}
--
-- Returned at file scope rather than scanned for, which UE4SS documents as the
-- alternative to Register and OnMatchFound. The scan is what fails for this
-- symbol, so this route avoids it.
--
-- {exe}+{target_off:#x}, with the module based at {base:#x} when this was
-- written. THAT BASE MOVES: the executable has ASLR, so after a reboot this
-- address is wrong and the file has to be written again. Run
-- tools/ue4ss_signatures.py --apply with the game up, then restart it.

return {target:#x}
'''

WHY_OBJECTS = """-- The engine's global object array. UE4SS cannot find it in this build, but
-- this project can: tools/find_objects.py locates it by looking for the one
-- object that is its own class, the UClass named Class, a self-reference
-- nothing else shares. The address below is that array less 0x10, which is
-- where the struct wrapping it begins. UE4SS's own shipped example for this
-- signature ends by subtracting the same 0x10."""

WHY_INERT = """-- {name} does not exist in Unreal 4.7; it arrived several releases later, so
-- UE4SS's pattern has nothing to match and it refuses to start without one.
-- Nothing this project wants needs it, so this points at padding between two
-- functions rather than at code. The hook lands in dead space and everything
-- else comes up. Should UE4SS ever call it, this will stop the game."""


def find_anchors(blob: bytes, size: int, count: int):
    """Padding runs with a unique run of real code in front of them."""
    out = []
    for run in re.finditer(rb"\xcc{%d,}" % MIN_PAD, blob):
        if not size * 0.1 < run.start() < size * 0.9:
            continue
        at = run.start() - ANCHOR
        anchor = blob[at : run.start()]
        if bytes([PAD]) in anchor or len(set(anchor)) < 6:
            continue
        if blob.count(anchor) != 1:
            continue
        out.append((at, anchor, run.start(), run.end() - run.start()))
        if len(out) == count:
            break
    return out


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
        print(f"{EXE} pid {pid}, .text {text.size:,} bytes")

        # The second anchor, not the first. Both are unique in .text, but on
        # the run where each signature had its own, only the second was
        # accepted; the first was reported as never matching. Whatever the
        # reason, the one that demonstrably works is the one to build on.
        anchors = find_anchors(blob, text.size, 2)
        if len(anchors) < 2:
            raise SystemExit(f"only found {len(anchors)} usable anchors, need 2")

        # One anchor for all three, each stepping to its own target.
        #
        # They had an anchor each at first, and only the construction one was
        # accepted: the other two were reported as not matching at all. Sharing
        # the anchor that demonstrably matches removes the pattern as a
        # variable, so if those two still fail it is about the symbol rather
        # than about the bytes being looked for.
        text_base_off = text.base - module.base
        at, anchor, pad_at, _pad_len = anchors[1]
        anchor_off = text_base_off + at
        pad_off = text_base_off + pad_at

        # The symbol whose scan UE4SS accepts keeps its scan, because a byte
        # pattern is base-independent and survives a reboot. The two it refuses
        # return their address at file scope instead, which is the documented
        # alternative and skips the scanning that is what fails for them.
        files = [
            (
                "StaticConstructObject.lua",
                WHY_INERT.format(name="StaticConstructObject_Internal"),
                "scan",
                anchor_off,
                pad_off,
            ),
            ("GUObjectArray.lua", WHY_OBJECTS, "literal", None, GUOBJECTARRAY),
        ]

        written = []
        for filename, why, how, at, target_off in files:
            if how == "scan":
                body = LUA.format(
                    why=why,
                    anchor=ANCHOR,
                    exe=EXE,
                    anchor_off=at,
                    step=target_off - at,
                    target_off=target_off,
                    pattern=" ".join(f"{b:02X}" for b in anchor),
                )
                how_text = f"scanned, anchor {EXE}+{at:#x}, step {target_off - at:+#x}"
            else:
                body = LUA_LITERAL.format(
                    why=why,
                    exe=EXE,
                    target_off=target_off,
                    base=module.base,
                    target=module.base + target_off,
                )
                how_text = "returned at file scope, absolute, stale after a reboot"
            written.append((filename, body))
            print(f"\n{filename}")
            print(f"    {how_text}")
            print(f"    target {EXE}+{target_off:#x}, live {module.base + target_off:#x}")

    if "--apply" not in sys.argv:
        print("\nrun again with --apply to write them")
        return

    sig_dir = signature_dir()
    sig_dir.mkdir(parents=True, exist_ok=True)
    for filename, body in written:
        (sig_dir / filename).write_text(body, encoding="utf-8")
    print(f"\nwrote {len(written)} files to {sig_dir}")
    print("restart the game, then read the log with tools/ue4ss_log.py")


if __name__ == "__main__":
    main()
