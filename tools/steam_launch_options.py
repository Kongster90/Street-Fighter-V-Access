"""Set Street Fighter V's Steam launch options to start the mod with the game.

Steam keeps a game's launch options, the box on its Properties page, in the
user's localconfig.vdf, at UserLocalConfigStore, Software, Valve, Steam, apps,
310950, LaunchOptions. Steam reads that file when it starts and writes it back
when it exits, so an edit made while Steam runs is lost; this refuses to write
while steam.exe is running. Close Steam, apply, start Steam again.

What it sets runs `start_with_game.pyw`, which starts the mod and then the game.
It changes that one value and nothing else in the file, keeps a copy of the
file as it was before the first change, and will not replace launch options it
did not write.

Usage:
    python tools/steam_launch_options.py            show what is set and what --apply would set
    python tools/steam_launch_options.py --apply    set it
    python tools/steam_launch_options.py --remove   take it back out
"""

from __future__ import annotations

import os
import re
import sys
import winreg
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access.memory import list_processes  # noqa: E402

APP_ID = "310950"
BLOCK = ("UserLocalConfigStore", "Software", "Valve", "Steam", "apps", APP_ID)
KEY = "LaunchOptions"
LAUNCHER = ROOT / "start_with_game.pyw"
# pythonw.exe beside the Python running this: the virtual environment's in a
# development copy, the bundled one in a copy installed for players.
PYTHONW = Path(sys.executable).with_name("pythonw.exe")
# Keep that Python to the mod's own packages: -E ignores PYTHONPATH and the
# like, -s the player's own per-user packages, either of which could put a
# different version of a package ahead of the mod's.
ISOLATE = ("-E", "-s")
OURS = f'"{PYTHONW}" {" ".join(ISOLATE)} "{LAUNCHER}" %command%'
BACKUP_SUFFIX = ".before-sfv-access"

# A quoted string with its escapes, a brace, a comment or whitespace. Steam
# quotes every key and value in this file.
_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])|(//[^\n]*)|(\s+)', re.S)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _unescape(value: str) -> str:
    return re.sub(r"\\(.)", r"\1", value)


def _find(text: str) -> tuple[int, str, tuple[int, int] | None]:
    """The game's block and its launch options, located in the file's text.

    Returns where the block's opening brace ends, the indentation its entries
    use, and the span of the whole LaunchOptions line if there is one.
    """
    path: list[str] = []
    pending: tuple[str, int] | None = None
    block_end = None
    indent = ""
    found = None
    pos = 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if m is None:
            raise ValueError(f"cannot read the file at character {pos}")
        pos = m.end()
        if m.group(1) is not None:
            if pending is None:
                pending = (_unescape(m.group(1)), m.start())
                continue
            key, key_start = pending
            pending = None
            here = tuple(p.lower() for p in path)
            if block_end is not None and here == tuple(b.lower() for b in BLOCK) and key.lower() == KEY.lower():
                line_start = text.rfind("\n", 0, key_start) + 1
                line_end = text.find("\n", m.end())
                found = (line_start, len(text) if line_end < 0 else line_end + 1)
        elif m.group(2) == "{":
            path.append(pending[0] if pending else "")
            pending = None
            if tuple(p.lower() for p in path) == tuple(b.lower() for b in BLOCK):
                block_end = m.end()
                line_start = text.rfind("\n", 0, m.start()) + 1
                indent = re.match(r"[ \t]*", text[line_start:]).group(0) + "\t"
        elif m.group(2) == "}":
            if not path:
                raise ValueError("a closing brace with nothing open")
            path.pop()
    if block_end is None:
        raise LookupError("Street Fighter V has no entry in this file; launch it from Steam once first")
    return block_end, indent, found


def launch_options(text: str) -> str | None:
    """The game's launch options, or None when none are set."""
    _end, _indent, found = _find(text)
    if found is None:
        return None
    line = text[found[0]:found[1]]
    values = [m.group(1) for m in _TOKEN.finditer(line) if m.group(1) is not None]
    return _unescape(values[1]) if len(values) > 1 else ""


def with_launch_options(text: str, value: str) -> str:
    """The file's text with the game's launch options set to value."""
    end, indent, found = _find(text)
    line = f'{indent}"{KEY}"\t\t"{_escape(value)}"\n'
    if found is not None:
        return text[:found[0]] + line + text[found[1]:]
    return text[:end] + "\n" + line.rstrip("\n") + text[end:]


def without_launch_options(text: str) -> str:
    """The file's text with the game's launch options taken out."""
    _end, _indent, found = _find(text)
    if found is None:
        return text
    return text[:found[0]] + text[found[1]:]


def is_ours(value: str | None) -> bool:
    return value is not None and LAUNCHER.name.lower() in value.lower()


def config_files() -> list[Path]:
    """Every Steam user's localconfig.vdf on this machine."""
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
        steam = Path(winreg.QueryValueEx(key, "SteamPath")[0])
    return sorted((steam / "userdata").glob("*/config/localconfig.vdf"))


def steam_running() -> bool:
    return bool(list_processes("steam.exe"))


def change(path: Path, value: str | None) -> str:
    """Set one user's launch options to value, or take ours out with None.

    Returns what happened: "set", "removed", "already", "not ours" (other
    launch options were there and are left alone) or "no game" (this Steam
    user has never launched Street Fighter V).
    """
    with path.open(encoding="utf-8", newline="") as fh:
        text = fh.read()
    try:
        current = launch_options(text)
    except LookupError:
        return "no game"
    if value is not None:
        if current and not is_ours(current):
            return "not ours"
        new = with_launch_options(text, value)
    else:
        if not current:
            return "already"
        if not is_ours(current):
            return "not ours"
        new = without_launch_options(text)
    if new == text:
        return "already"
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    if not backup.exists():
        backup.write_bytes(path.read_bytes())
    temp = path.with_name(path.name + ".sfv-access-writing")
    with temp.open("w", encoding="utf-8", newline="") as fh:
        fh.write(new)
    os.replace(temp, path)
    return "set" if value is not None else "removed"


def main() -> int:
    apply = "--apply" in sys.argv
    remove = "--remove" in sys.argv
    if (apply or remove) and steam_running():
        print("Steam is running. Close Steam first: it rewrites this file when it exits, "
              "which would undo the change.")
        return 1

    status = 0
    for path in config_files():
        if not (apply or remove):
            with path.open(encoding="utf-8", newline="") as fh:
                text = fh.read()
            try:
                current = launch_options(text)
            except LookupError as exc:
                print(f"{path}: {exc}")
                continue
            print(f"{path}")
            print(f"  launch options now: {current if current else '(none)'}")
            print(f"  --apply would set: {OURS}")
            continue
        outcome = change(path, OURS if apply else None)
        print(f"{path}: {outcome}")
        if outcome == "not ours":
            print("  Left alone: these launch options were not set by this tool. "
                  "Clear them on the game's Properties page, or add this there yourself:")
            print(f"  {OURS}")
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
