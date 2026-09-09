"""Dump the readable state of whatever screens are open.

Shows the properties the game declares itself, with values decoded, for every
live object whose class matches the filters. Use it to hunt for the piece of
state that says which entry is selected.

    python tools/dump_screen_state.py CharaSelect VersionSelect
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access import unreal  # noqa: E402
from sfv_access.memory import ProcessMemory, find_pid  # noqa: E402

EXE = "StreetFighterV.exe"
ENGINE_OWNERS = {"Object", "Actor", "Pawn", "Info", "Controller", "HUD"}


def main() -> None:
    wanted = [a.lower() for a in sys.argv[1:]] or ["charaselect"]

    pid = find_pid(EXE, path_contains=r"Binaries\Win64")
    if pid is None:
        print(f"{EXE} is not running.")
        sys.exit(1)

    with ProcessMemory(pid) as pm:
        main_mod = next(m for m in pm.modules() if m.name.lower() == EXE.lower())
        names = unreal.name_array_from_hint(pm, main_mod.base)
        objects = unreal.object_array_from_hint(pm, names, main_mod.base) if names else None
        if names is None or objects is None:
            print("engine tables not found")
            sys.exit(2)
        layout = objects.layout
        struct_layout = unreal.find_struct_layout(pm, names, objects, verbose=False)
        if struct_layout is None:
            print("class layout not resolved")
            sys.exit(3)

        targets = []
        for i in range(objects.num_elements):
            obj = unreal.object_at(pm, objects, i)
            if not obj:
                continue
            cls = unreal.object_class_name(pm, names, obj, layout)
            nm = unreal.object_name(pm, names, obj, layout)
            if not cls or not nm or nm.startswith("Default__"):
                continue
            if cls in ("Class", "Package", "Function", "ScriptStruct"):
                continue
            if any(w in cls.lower() for w in wanted):
                targets.append((obj, cls, nm))

        print(f"{len(targets)} live objects matching {wanted}\n")
        for obj, cls, nm in targets:
            cls_obj = pm.ptr(obj + layout.class_private)
            props = unreal.class_properties(pm, names, cls_obj, layout, struct_layout)
            own = [p for p in props if p.owner not in ENGINE_OWNERS]
            interesting = [
                p
                for p in own
                if p.type_name
                in (
                    "IntProperty", "ByteProperty", "BoolProperty", "FloatProperty",
                    "StrProperty", "NameProperty", "ArrayProperty",
                )
            ]
            if not interesting:
                continue
            print(f"=== {cls} {nm} at 0x{obj:x} ===")
            for p in interesting:
                value = unreal.read_property(pm, names, obj, p, layout)
                if value is None or value is False or value == 0 or value == "":
                    continue
                extra = ""
                if p.type_name == "ArrayProperty":
                    items = unreal.array_of_objects(pm, names, obj + p.offset, layout, cap=8)
                    if items:
                        extra = "  [" + ", ".join(items[:6]) + "]"
                print(f"  +0x{p.offset:05x} {p.name:34s} {p.type_name:14s} {value}{extra}")
            print()


if __name__ == "__main__":
    main()
