"""Map how Street Fighter V actually builds its interface.

Reads the live object graph and reports which interface framework is in use,
which classes exist for it, and which instances are alive right now.

    python tools/dump_objects.py [substring ...]
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
    wanted = [a.lower() for a in sys.argv[1:]]
    pid = find_pid(EXE, path_contains=r"Binaries\Win64")
    if pid is None:
        print(f"{EXE} is not running.")
        sys.exit(1)

    with ProcessMemory(pid) as pm:
        main_mod = next(m for m in pm.modules() if m.name.lower() == EXE.lower())
        names = unreal.name_array_from_hint(pm, main_mod.base)
        if names is None:
            print("name table not found at the known offset; run tools/find_names.py")
            sys.exit(2)
        objects = unreal.object_array_from_hint(pm, names, main_mod.base)
        if objects is None:
            print("object list not found at the known offset; run tools/find_objects.py")
            sys.exit(3)
        print(names.describe())
        print(objects.describe())
        layout = objects.layout

        # One pass, holding on to what each object is and what it is called.
        t0 = time.perf_counter()
        rows = []
        for i in range(objects.num_elements):
            obj = unreal.object_at(pm, objects, i)
            if not obj:
                continue
            cls = unreal.object_class_name(pm, names, obj, layout)
            nm = unreal.object_name(pm, names, obj, layout)
            if cls and nm:
                rows.append((i, obj, cls, nm))
        print(f"read {len(rows):,} objects in {time.perf_counter() - t0:.1f} s\n")

        by_class: collections.Counter = collections.Counter(r[2] for r in rows)

        # Which interface framework is actually in use, by live instance count.
        print("interface framework, counted by live instances:")
        families = {
            "Scaleform GFx": ("GFx", "Scaleform"),
            "UMG widgets": ("UserWidget", "TextBlock", "ProgressBar", "Slider", "CanvasPanel"),
            "Slate": ("Slate",),
        }
        for label, keys in families.items():
            n = sum(c for cls, c in by_class.items() if any(k in cls for k in keys))
            kinds = sum(1 for cls in by_class if any(k in cls for k in keys))
            print(f"  {label:16s} {n:6,} instances across {kinds} classes")

        # Class objects tell us what the game defines, instances what it uses.
        print("\nGFx classes defined by the game:")
        gfx_classes = sorted({nm for _i, _o, cls, nm in rows if cls == "Class" and "GFx" in nm})
        for nm in gfx_classes[:40]:
            print(f"  {nm}")
        print(f"  ({len(gfx_classes)} total)")

        # A name beginning Default__ is the class default object, which exists
        # whether or not the screen is open. Everything else is really running.
        # Filter on the class an object belongs to, not its own name, or every
        # UClass describing a GFx player is mistaken for a running screen.
        gfx_all = [
            (i, o, cls, nm)
            for i, o, cls, nm in rows
            if ("GFx" in cls or "Scaleform" in cls) and cls not in ("Class", "Package", "Function")
        ]
        cdos = [r for r in gfx_all if r[3].startswith("Default__")]
        live = [r for r in gfx_all if not r[3].startswith("Default__")]

        print(f"\n{len(cdos)} GFx class defaults, {len(live)} live GFx instances")
        print("\nlive GFx instances, which is what is on screen now:")
        for i, obj, cls, nm in live[:40]:
            path = unreal.full_object_path(pm, names, obj, layout)
            print(f"  {i:7d}  0x{obj:012x}  {cls:36s} {path}")
        if not live:
            print("  none; the menus may not be open yet")

        if wanted:
            print(f"\nobjects matching {wanted}:")
            shown = 0
            for i, obj, cls, nm in rows:
                blob = f"{cls} {nm}".lower()
                if any(w in blob for w in wanted):
                    path = unreal.full_object_path(pm, names, obj, layout)
                    print(f"  {i:7d}  0x{obj:012x}  {cls:34s} {path}")
                    shown += 1
                    if shown >= 60:
                        print("  ...")
                        break


if __name__ == "__main__":
    main()
