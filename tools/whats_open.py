"""Which interface screens the game currently has open.

Handy during development: the live object list only contains what is actually
on screen, so this says whether the game is parked where the work needs it.
Reads memory only, so it does not care whether the game window has focus.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access import game, unreal  # noqa: E402
from sfv_access.memory import ProcessMemory, find_pid  # noqa: E402

EXE = "StreetFighterV.exe"


def main() -> None:
    pid = find_pid(EXE, path_contains=r"Binaries\Win64")
    if pid is None:
        print("Street Fighter V is not running.")
        sys.exit(1)

    win = game.find_window()
    focus = "in focus" if (win and win.is_foreground) else "not in focus"
    print(f"pid {pid}, window {focus} (reading memory does not depend on this)")

    with ProcessMemory(pid) as pm:
        main_mod = next(m for m in pm.modules() if m.name.lower() == EXE.lower())
        names = unreal.name_array_from_hint(pm, main_mod.base)
        objects = unreal.object_array_from_hint(pm, names, main_mod.base) if names else None
        if names is None or objects is None:
            print("could not resolve the engine tables at their known offsets")
            sys.exit(2)
        layout = objects.layout

        open_screens = []
        for i in range(objects.num_elements):
            obj = unreal.object_at(pm, objects, i)
            if not obj:
                continue
            cls = unreal.object_class_name(pm, names, obj, layout)
            if not cls or cls in ("Class", "Package", "Function"):
                continue
            if "GFx" not in cls and "Scaleform" not in cls:
                continue
            nm = unreal.object_name(pm, names, obj, layout)
            if not nm or nm.startswith("Default__"):
                continue
            open_screens.append((i, obj, cls, nm))

        players = [r for r in open_screens if r[2].endswith("Player") or "Menu" in r[2]]
        print(f"\n{len(open_screens)} live GFx objects, {len(players)} of them screens:")
        for i, obj, cls, nm in players:
            print(f"  {cls:38s} {nm}")
        if not players:
            print("  none open")


if __name__ == "__main__":
    main()
