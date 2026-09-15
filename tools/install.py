"""Install Street Fighter V Access for a player, in one go.

Run by "Install SFV Access.bat" from the unzipped package, with the Python the
package carries. It copies the package to the player's programs folder, sets
Street Fighter V's Steam launch options so the mod starts and closes with the
game, closing Steam for the moment that takes and opening it again, and says
what it did. Everything it prints is plain sentences, since the player hears it
through their screen reader.

Run again from a newer package, it updates the installed copy and keeps the
player's own files: settings, the game's text and the logs.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import winreg
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from sfv_access import game, instance  # noqa: E402
from tools import steam_launch_options as slo  # noqa: E402

TARGET = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Programs" / "SFV Access"
# The player's own files in an installed copy, kept when it is updated.
KEEP = {"settings.json", "strings.json", "pak_key.txt", "snapshots"}
STEAM_CLOSE_WAIT = 90


def say(text: str = "") -> None:
    print(text, flush=True)


def wait_for_enter(prompt: str) -> None:
    try:
        input(prompt)
    except EOFError:
        pass


def copy_package(source: Path, target: Path) -> None:
    """Put the package's files at target, leaving the player's own files alone."""
    target.mkdir(parents=True, exist_ok=True)
    for old in target.iterdir():
        if old.name in KEEP:
            continue
        if old.is_dir():
            shutil.rmtree(old)
        else:
            old.unlink()
    for item in source.iterdir():
        if item.name in KEEP:
            continue
        if item.is_dir():
            shutil.copytree(item, target / item.name, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(item, target / item.name)


def unblock(folder: Path) -> None:
    """Remove the mark Windows puts on downloaded files, so nothing asks before running them."""
    for path in folder.rglob("*"):
        if path.is_file():
            try:
                os.remove(f"{path}:Zone.Identifier")
            except OSError:
                pass


def steam_exe() -> Path | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            return Path(winreg.QueryValueEx(key, "SteamExe")[0])
    except OSError:
        return None


def close_steam() -> bool:
    exe = steam_exe()
    if exe is None:
        return False
    subprocess.Popen([str(exe), "-shutdown"])
    for _ in range(STEAM_CLOSE_WAIT):
        if not slo.steam_running():
            time.sleep(2)   # let it finish writing its files
            return True
        time.sleep(1)
    return not slo.steam_running()


def main() -> int:
    say("Street Fighter V Access installer.")
    say()
    if game.is_running():
        say("Street Fighter V is running. Close the game, then run the installer again.")
        return 1
    if instance.already_running():
        say("Street Fighter V Access is running. Press F10 to close it, then run the installer again.")
        return 1
    try:
        files = slo.config_files()
    except OSError:
        say("Steam was not found on this computer. Install Steam and Street Fighter V first.")
        return 1

    if HERE.resolve() != TARGET.resolve():
        say(f"Copying the mod to {TARGET}. This takes a few seconds.")
        copy_package(HERE, TARGET)
    unblock(TARGET)
    pythonw = TARGET / "python" / "pythonw.exe"
    value = f'"{pythonw}" "{TARGET / slo.LAUNCHER.name}" %command%'

    was_running = slo.steam_running()
    if was_running:
        say()
        say("Steam needs to close for a moment so the game's launch options can be set. "
            "It will open again afterwards.")
        wait_for_enter("Press Enter to close Steam and carry on.")
        say("Closing Steam.")
        if not close_steam():
            say("Steam did not close. Close Steam yourself, then run the installer again.")
            return 1

    outcomes = [slo.change(path, value) for path in files]
    if was_running and steam_exe() is not None:
        subprocess.Popen([str(steam_exe())])
        say("Opening Steam again.")

    say()
    if any(o in ("set", "already") for o in outcomes):
        say("Done. Street Fighter V Access is installed.")
        say("Start Street Fighter V from Steam as usual. The mod starts with the game and closes with it.")
        say("The first time, it sets up the game's text, which takes a few seconds, and says when it is ready.")
        say("In the game, press Alt K to hear the keys.")
    elif "not ours" in outcomes:
        say("Street Fighter V already has launch options in Steam that this installer did not set, "
            "so they were left alone. Clear them on the game's Properties page in Steam, "
            "then run the installer again.")
    else:
        say("Steam has no record of Street Fighter V being played on this account. "
            "Start the game from Steam once, close it, then run the installer again.")
    say()
    wait_for_enter("Press Enter to close this window.")
    # Zero whatever happened: the window has already waited, and the batch
    # file pauses again on anything else.
    return 0


if __name__ == "__main__":
    sys.exit(main())
