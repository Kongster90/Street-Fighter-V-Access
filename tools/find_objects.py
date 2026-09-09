"""Milestone two: find the global object array and read the live object graph.

Run with Street Fighter V already started and sitting in a menu.

    python tools/find_objects.py

Also resolves the static pointer that holds the name table, so the tables can
be found again on the next run without repeating the slow search.
"""

from __future__ import annotations

import collections
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
        print(f"{EXE} is not running.")
        sys.exit(1)

    with ProcessMemory(pid) as pm:
        mods = pm.modules()
        main_mod = next((m for m in mods if m.name.lower() == EXE.lower()), None)
        print(f"pid {pid}, {main_mod.name} base 0x{main_mod.base:x}")

        static = [r for r in (pm.section(main_mod, s) for s in (".data", "_RDATA")) if r]
        regions = pm.regions()

        t0 = time.perf_counter()
        names = unreal.name_array_from_hint(pm, main_mod.base)
        how = "known offset"
        if names is None:
            names = unreal.find_name_array(pm, regions, static_regions=static, verbose=False)
            how = "full search"
        if names is None:
            print("name table not found")
            sys.exit(2)
        print(f"{names.describe()}  [{how}, {time.perf_counter() - t0:.1f} s]")

        # The array itself is heap allocated; the stable reference is the
        # static pointer to it, which survives a restart as a module offset.
        holders = pm.find_pointers_to(names.address, static, limit=4)
        for h in holders:
            print(f"  static GNames pointer at {main_mod.name}+0x{h - main_mod.base:x}")
        if not holders:
            print("  no static pointer found in .data (searching all regions is slower)")

        t1 = time.perf_counter()
        objects = unreal.find_object_array(pm, names, regions, static, verbose=True)
        if objects is None:
            print("object array not found")
            sys.exit(3)
        print(f"{objects.describe()}  [{time.perf_counter() - t1:.1f} s]")
        print(f"  GObjects at {main_mod.name}+0x{objects.address - main_mod.base:x}")

        layout = objects.layout
        print("\nfirst 25 objects:")
        for i in range(25):
            obj = unreal.object_at(pm, objects, i)
            if not obj:
                continue
            print(
                f"  {i:6d}  0x{obj:012x}  "
                f"{unreal.object_class_name(pm, names, obj, layout)!s:28s} "
                f"{unreal.full_object_path(pm, names, obj, layout)}"
            )

        # What kinds of object exist tells us what the interface is built from.
        print("\ncounting classes across the whole array...")
        t2 = time.perf_counter()
        counts: collections.Counter = collections.Counter()
        live = 0
        for i in range(objects.num_elements):
            obj = unreal.object_at(pm, objects, i)
            if not obj:
                continue
            live += 1
            cls = unreal.object_class_name(pm, names, obj, layout)
            if cls:
                counts[cls] += 1
        print(f"  {live:,} live objects in {time.perf_counter() - t2:.1f} s")

        print("\nmost common classes:")
        for cls, n in counts.most_common(25):
            print(f"  {n:7,}  {cls}")

        print("\nuser interface classes:")
        ui = [
            (cls, n)
            for cls, n in counts.items()
            if any(k in cls for k in ("Widget", "Slate", "UMG", "Button", "Slider", "Text"))
        ]
        for cls, n in sorted(ui, key=lambda kv: -kv[1])[:30]:
            print(f"  {n:7,}  {cls}")


if __name__ == "__main__":
    main()
