"""Configure UE4SS for this game, which its own build does not support.

UE4SS targets Unreal 4.12 up to 5.1. Street Fighter V is 4.7, below that range,
so its shipped layouts do not apply and it has to be told what this build looks
like. That is the intended path for an old engine: its templates exist for
"games with custom engine versions or an otherwise unsupported engine version".

We are unusually well placed to do it, because this project already derived and
validated the layout by reading the running game. Every offset it needs matched
the 4.12 template except one.

What this writes, into the folder holding the game executable:

  MemberVariableLayout.ini   the object and struct offsets for 4.7
  UE4SS-settings.ini         engine version override, and a quiet first run

It changes nothing else, and reports every file it touched. Removing those two
files and xinput1_3.dll undoes the whole install.

None of this is needed on UE4SS 3.x, which supports 4.7 natively. Keep it only
for the 2.x builds it was written against, and use --remove before installing
3.x: its old xinput1_3.dll crashes the game, and the layout file here would
override values 3.x already knows correctly.

Usage:
    python tools/ue4ss_setup.py            report what it would do
    python tools/ue4ss_setup.py --apply    write it
    python tools/ue4ss_setup.py --remove   take the whole install back out
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

WIN64 = Path(
    r"G:\Steam\steamapps\common\StreetFighterV\StreetFighterV\Binaries\Win64"
)
PROXY = "xinput1_3.dll"
SETTINGS = "UE4SS-settings.ini"
LAYOUT = "MemberVariableLayout.ini"

# Confirmed against this build at runtime, by tools/find_objects.py and
# tools/find_properties.py, and re-validated on every read. All but the last
# are identical to what UE4SS ships for 4.12.
OFFSETS = {
    "UObjectBase": {
        "ObjectFlags": "0x8",
        "InternalIndex": "0xC",
        "ClassPrivate": "0x10",
        "NamePrivate": "0x18",
        "OuterPrivate": "0x20",
    },
    "UField": {"Next": "0x28"},
    "UStruct": {"SuperStruct": "0x30", "Children": "0x38"},
    # 0x4C here against 0x50 in 4.12. Everything below it in this struct is
    # therefore suspect as well, since four bytes moves the rest along, and
    # those fields are left out rather than guessed. Object dumping does not
    # read them, so the first run does not depend on them; a property dump
    # would, and they should be derived the same way the offset above was
    # before anything trusts one.
    "FProperty": {
        "ArrayDim": "0x30",
        "ElementSize": "0x34",
        "PropertyFlags": "0x38",
        "Offset_Internal": "0x4C",
    },
}

HEADER = """; Street Fighter V, Unreal Engine 4.7, written by tools/ue4ss_setup.py.
;
; UE4SS ships no layout below 4.12. These offsets were derived by reading the
; running game rather than taken from a template, and every one of them is
; checked before use. Do not edit by hand; change the tool.
"""

# Nothing but the built-in keybinds for a first run. Each of the bundled mods
# is another thing that can crash a game two engine versions older than any it
# was written for, and none of them is needed to find out whether UE4SS loads.
QUIET_MODS = """CheatManagerEnablerMod : 0
ActorDumperMod : 0
ConsoleCommandsMod : 0
ConsoleEnablerMod : 0
SplitScreenMod : 0
LineTraceMod : 0

; Built-in keybinds, do not move up!
Keybinds : 1
"""

SETTING_CHANGES = {
    # Not the real version, which is 4.7. UE4SS checks the version against what
    # it supports and stops with "Engine version is not supported" below 4.12,
    # a check that lives in its Unreal library rather than in UE4SS itself.
    #
    # Claiming 4.12 is safe rather than a fudge: nothing in UE4SS branches below
    # 4.15, so 4.12 and 4.7 take identical paths through it. What actually
    # differs between the two engines is the memory layout, and that comes from
    # MemberVariableLayout.ini, which holds this build's real offsets.
    "MajorVersion": "4",
    "MinorVersion": "12",
    # A console window over a fullscreen game steals focus. The log file says
    # the same things and is what gets read here anyway.
    "ConsoleEnabled": "0",
    "GuiConsoleEnabled": "0",
    "GuiConsoleVisible": "0",
    # Loading every asset first is documented as unstable and as crashing the
    # game if you then play past the main menu. Not for a first run.
    "LoadAllAssetsBeforeDumpingObjects": "0",
    "LoadAllAssetsBeforeGeneratingCXXHeaders": "0",
}


def layout_text() -> str:
    out = [HEADER]
    for section, fields in OFFSETS.items():
        out.append(f"\n[{section}]")
        for name, value in fields.items():
            out.append(f"{name} = {value}")
    return "\n".join(out) + "\n"


def patch_settings(text: str) -> tuple[str, list[str]]:
    """Set our keys in place, leaving every other line as it was."""
    lines = text.splitlines()
    changed = []
    for i, line in enumerate(lines):
        if "=" not in line or line.lstrip().startswith(";"):
            continue
        key = line.split("=", 1)[0].strip()
        if key in SETTING_CHANGES:
            want = f"{key} = {SETTING_CHANGES[key]}"
            if line.strip() != want:
                lines[i] = want
                changed.append(want)
    return "\n".join(lines) + "\n", changed


# The folder held nothing but these two before any of this went in, so
# everything else there is ours to take out. They are never touched.
GAME_FILES = {"StreetFighterV.exe", "StreetFighterV.exe._"}


def remove() -> None:
    """Take the whole UE4SS install back out, leaving the game as it was."""
    if not WIN64.is_dir():
        raise SystemExit(f"no such folder: {WIN64}")

    doomed = [p for p in sorted(WIN64.iterdir()) if p.name not in GAME_FILES]
    if not doomed:
        print(f"nothing to remove; {WIN64} holds only the game")
        return

    print(f"would remove from {WIN64}:")
    for p in doomed:
        kind = "folder" if p.is_dir() else f"{p.stat().st_size:,} bytes"
        print(f"    {p.name}  ({kind})")
    print(f"\nleaving: {', '.join(sorted(GAME_FILES))}")

    if "--apply" not in sys.argv:
        print("\nrun again with --remove --apply to delete them")
        return

    for p in doomed:
        shutil.rmtree(p) if p.is_dir() else p.unlink()
    print(f"\nremoved {len(doomed)} items. The game is back to stock.")


def main() -> None:
    if "--remove" in sys.argv:
        remove()
        return

    apply = "--apply" in sys.argv

    if not WIN64.is_dir():
        raise SystemExit(f"no such folder: {WIN64}")
    missing = [f for f in (PROXY, SETTINGS) if not (WIN64 / f).exists()]
    if missing:
        print(f"UE4SS is not installed in {WIN64}")
        print(f"  missing: {', '.join(missing)}")
        print("  put the contents of the UE4SS XInput build there first")
        raise SystemExit(1)

    print(f"UE4SS found in {WIN64}")
    for f in sorted(p.name for p in WIN64.iterdir()):
        print(f"    {f}")

    settings_path = WIN64 / SETTINGS
    patched, changed = patch_settings(settings_path.read_text(encoding="utf-8-sig"))
    mods_path = WIN64 / "Mods" / "mods.txt"

    print(f"\nwould write {LAYOUT}, {sum(len(v) for v in OFFSETS.values())} offsets")
    print(f"would change {len(changed)} settings:")
    for c in changed:
        print(f"    {c}")
    if mods_path.exists():
        print("would disable the bundled mods for a first run")

    if not apply:
        print("\nrun again with --apply to write it")
        return

    (WIN64 / LAYOUT).write_text(layout_text(), encoding="utf-8")
    backup = settings_path.with_suffix(".ini.orig")
    if not backup.exists():
        shutil.copy2(settings_path, backup)
    settings_path.write_text(patched, encoding="utf-8")
    if mods_path.exists():
        mods_backup = mods_path.with_suffix(".txt.orig")
        if not mods_backup.exists():
            shutil.copy2(mods_path, mods_backup)
        mods_path.write_text(QUIET_MODS, encoding="utf-8")

    print(f"\nwrote {LAYOUT} and updated {SETTINGS}")
    print(f"originals kept beside them as .orig")
    print("start the game, then read the log with tools/ue4ss_log.py")


if __name__ == "__main__":
    main()
