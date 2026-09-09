"""Milestone three: work out the class layout and read a live screen's properties.

Run with the game on the screen you care about.

    python tools/find_properties.py [ClassNameSubstring]
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
    want = sys.argv[1].lower() if len(sys.argv) > 1 else "charaselect"

    pid = find_pid(EXE, path_contains=r"Binaries\Win64")
    if pid is None:
        print(f"{EXE} is not running.")
        sys.exit(1)

    with ProcessMemory(pid) as pm:
        main_mod = next(m for m in pm.modules() if m.name.lower() == EXE.lower())
        names = unreal.name_array_from_hint(pm, main_mod.base)
        objects = unreal.object_array_from_hint(pm, names, main_mod.base) if names else None
        if names is None or objects is None:
            print("engine tables not found at their known offsets")
            sys.exit(2)
        layout = objects.layout
        print(objects.describe())

        t0 = time.perf_counter()
        struct_layout = unreal.find_struct_layout(pm, names, objects)
        if struct_layout is None:
            print("could not determine the class layout")
            sys.exit(3)
        print(f"class layout: {struct_layout.label()}  [{time.perf_counter() - t0:.1f} s]")

        # Live instances of whatever screen was asked for.
        targets = []
        for i in range(objects.num_elements):
            obj = unreal.object_at(pm, objects, i)
            if not obj:
                continue
            cls = unreal.object_class_name(pm, names, obj, layout)
            nm = unreal.object_name(pm, names, obj, layout)
            if not cls or not nm or nm.startswith("Default__"):
                continue
            if cls in ("Class", "Package", "Function"):
                continue
            if want in cls.lower():
                targets.append((i, obj, cls, nm))

        if not targets:
            print(f"\nno live instance whose class contains {want!r}")
            sys.exit(4)

        print(f"\n{len(targets)} live instances matching {want!r}")
        index, obj, cls, nm = targets[0]
        print(f"reading {cls} {nm} at 0x{obj:x}\n")

        cls_obj = pm.ptr(obj + layout.class_private)
        props = unreal.class_properties(pm, names, cls_obj, layout, struct_layout)

        # Everything inherited from Actor and below is engine plumbing. What
        # the game declares itself is where the interface data lives.
        ENGINE = {"Object", "Actor", "Pawn", "Info", "Controller", "HUD"}
        own = [p for p in props if p.owner not in ENGINE]

        print(f"{len(props)} properties total, {len(own)} declared by the game:")
        for p in own:
            raw = pm.read(obj + p.offset, 16) or b""
            extra = ""
            if p.type_name in ("StrProperty", "ArrayProperty"):
                ptr = pm.ptr(obj + p.offset)
                count = pm.i32(obj + p.offset + 8)
                extra = f"  -> data 0x{ptr or 0:x} count {count}"
                if p.type_name == "StrProperty" and ptr and count and 0 < count < 512:
                    extra += f"  {pm.wstring(ptr, count)!r}"
            elif p.type_name == "ObjectProperty":
                target = pm.ptr(obj + p.offset)
                if target:
                    extra = (
                        f"  -> {unreal.object_class_name(pm, names, target, layout)} "
                        f"{unreal.object_name(pm, names, target, layout)}"
                    )
            elif p.type_name == "NameProperty":
                idx = pm.i32(obj + p.offset)
                if idx is not None and idx >= 0:
                    extra = f"  -> {unreal.read_name(pm, names, idx)!r}"
            elif p.type_name in ("IntProperty", "ByteProperty"):
                extra = f"  = {pm.i32(obj + p.offset)}"
            elif p.type_name == "FloatProperty":
                extra = f"  = {pm.f32(obj + p.offset)}"
            elif p.type_name == "BoolProperty":
                extra = f"  = {bool(pm.u8(obj + p.offset))}"
            print(
                f"  +0x{p.offset:05x}  {p.type_name:20s} {p.name:34s} "
                f"[{p.owner}] {raw[:8].hex()}{extra}"
            )


if __name__ == "__main__":
    main()
