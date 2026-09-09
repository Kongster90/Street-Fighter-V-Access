"""Milestone one: find Unreal's global name table in the running game.

Run with Street Fighter V already started and sitting in a menu.

    python tools/find_names.py

On success it prints where the table is and dumps a sample of names. That is
the point at which every object in the game becomes identifiable by name, and
everything else in the injection work builds on it.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access import unreal  # noqa: E402
from sfv_access.memory import ProcessMemory, find_pid  # noqa: E402

EXE = "StreetFighterV.exe"


def main() -> None:
    pid = find_pid(EXE, path_contains=r"Binaries\Win64")
    if pid is None:
        print(f"{EXE} is not running. Start the game and get to a menu, then try again.")
        sys.exit(1)
    print(f"{EXE} is pid {pid}")

    with ProcessMemory(pid) as pm:
        mods = pm.modules()
        print(f"{len(mods)} modules loaded")
        main_mod = next((m for m in mods if m.name.lower() == EXE.lower()), None)
        if main_mod is None:
            print("could not find the game's own module")
            sys.exit(1)
        print(f"  {main_mod.name} base 0x{main_mod.base:x} size 0x{main_mod.size:x}")

        static = []
        for sec in (".data", ".rdata", "_RDATA"):
            r = pm.section(main_mod, sec)
            if r:
                print(f"  section {sec:8s} 0x{r.base:x} size 0x{r.size:x}")
                static.append(r)

        regions = pm.regions()
        readable = sum(r.size for r in regions)
        print(f"{len(regions)} readable regions, {readable / 1e9:.2f} GB")

        t0 = time.perf_counter()
        found = unreal.find_name_array(pm, regions, static_regions=static)
        dt = time.perf_counter() - t0

        if found is None:
            print(f"\nname table not found after {dt:.1f} s")
            print("The layout hypotheses in sfv_access/unreal.py need widening.")
            sys.exit(2)

        print(f"\nFOUND in {dt:.1f} s")
        print(f"  {found.describe()}")
        print(f"  offset from module base: 0x{found.address - main_mod.base:x}")

        print("\nfirst 40 names:")
        for i in range(40):
            name = unreal.read_name(pm, found, i)
            if name is not None:
                print(f"  {i:5d}  {name}")

        print("\nsampled across the table:")
        step = max(1, found.num_elements // 20)
        for i in range(0, found.num_elements, step):
            name = unreal.read_name(pm, found, i)
            if name:
                print(f"  {i:6d}  {name}")

        # Names carrying the game's own prefix confirm this is the real table
        # rather than a lookalike from the engine's editor leftovers.
        hits = 0
        for i in range(0, min(found.num_elements, 40000), 7):
            name = unreal.read_name(pm, found, i)
            if name and any(k in name for k in ("SF", "Kiwi", "Battle", "Widget", "UMG")):
                if hits < 25:
                    print(f"  game name: {i:6d}  {name}")
                hits += 1
        print(f"\n{hits} game-specific names in the sampled range")


if __name__ == "__main__":
    main()
