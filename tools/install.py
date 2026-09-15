"""Install Street Fighter V Access for a player, in one go.

Run by "Install SFV Access.bat" from the unzipped package, with the Python the
package carries. It copies the package to the player's programs folder, puts a
shortcut to the start script on their desktop, and asks whether the mod should
start with the game. Saying yes sets Street Fighter V's Steam launch options,
closing Steam for the moment that takes and opening it again. Everything it
prints is plain sentences, since the player hears it through their screen
reader.

The question is there because the launch options are the part that can go
wrong: the first tester's game would not log into its server when Steam
started it through the mod, though it was fine when they started the mod
themselves. Saying no leaves Steam alone, and the desktop shortcut starts the
mod whenever they want it, before or after the game.

Run again from a newer package, it updates the installed copy and keeps the
player's own files: settings, the game's text and the logs. Answering the
question differently the second time changes the launch options to match, so
either answer can be undone by running it again.
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
START_SCRIPT = "Start SFV Access.bat"
SHORTCUT = "Street Fighter V Access.lnk"


def say(text: str = "") -> None:
    print(text, flush=True)


def wait_for_enter(prompt: str) -> None:
    try:
        input(prompt)
    except EOFError:
        pass


def ask_yes_no(question: str, default: bool = True) -> bool:
    """Yes or no from the player. Enter alone, or no answer at all, takes the default."""
    while True:
        try:
            answer = input(f"{question} Type yes or no, then press Enter. ").strip().lower()
        except EOFError:
            return default
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        say("Please answer yes or no.")


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


def desktop_folder() -> Path:
    """The player's desktop, which OneDrive and the like may have moved."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
        ) as key:
            return Path(os.path.expandvars(winreg.QueryValueEx(key, "Desktop")[0]))
    except OSError:
        return Path.home() / "Desktop"


def make_shortcut(target: Path) -> Path | None:
    """A desktop shortcut to the start script, or None if one could not be made."""
    link = desktop_folder() / SHORTCUT
    try:
        import win32com.client  # part of the package, beside the mod's own Python

        shortcut = win32com.client.Dispatch("WScript.Shell").CreateShortCut(str(link))
        shortcut.TargetPath = str(target)
        shortcut.WorkingDirectory = str(target.parent)
        shortcut.Description = "Start Street Fighter V Access"
        shortcut.Save()
        return link
    except Exception:
        return None


def remove_shortcut() -> None:
    try:
        (desktop_folder() / SHORTCUT).unlink()
    except OSError:
        pass


def ours_set(files: list[Path]) -> bool:
    """Whether any Steam user's launch options are ones this mod wrote."""
    for path in files:
        try:
            with path.open(encoding="utf-8", newline="") as fh:
                text = fh.read()
            if slo.is_ours(slo.launch_options(text)):
                return True
        except (OSError, LookupError, ValueError):
            continue
    return False


def change_launch_options(files: list[Path], value: str | None, purpose: str) -> list[str] | None:
    """Set the launch options to value, or take ours out with None.

    Steam rewrites the file it keeps them in when it exits, so it is closed for
    the moment the change takes and started again afterwards. Returns what
    happened to each Steam user on this machine, or None if Steam would not
    close, which the caller reports in its own words.
    """
    was_running = slo.steam_running()
    if was_running:
        say()
        say(f"Steam needs to close for a moment so the game's launch options can be {purpose}. "
            "It will open again afterwards.")
        wait_for_enter("Press Enter to close Steam and carry on.")
        say("Closing Steam.")
        if not close_steam():
            return None
    outcomes = [slo.change(path, value) for path in files]
    if was_running and steam_exe() is not None:
        subprocess.Popen([str(steam_exe())])
        say("Opening Steam again.")
    return outcomes


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

    link = make_shortcut(TARGET / START_SCRIPT)
    say()
    if link is not None:
        say("There is now a Street Fighter V Access shortcut on your desktop, which starts the mod.")
    else:
        say("A desktop shortcut could not be made. To start the mod, "
            f"run {TARGET / START_SCRIPT}.")

    say()
    say("The mod can also start by itself every time you play, by setting Street Fighter V's "
        "launch options in Steam. That is one less thing to do, but on some computers the game "
        "then cannot log into its server, in which case run this installer again and answer no.")
    with_game = ask_yes_no("Start the mod with the game?")

    say()
    pythonw = TARGET / "python" / "pythonw.exe"
    value = f'"{pythonw}" "{TARGET / slo.LAUNCHER.name}" %command%' if with_game else None
    # Answering no when nothing of ours is set leaves Steam alone entirely,
    # which spares the player closing it.
    if with_game or ours_set(files):
        outcomes = change_launch_options(files, value, "set" if with_game else "changed back")
        if outcomes is None:
            say("Steam did not close. Close Steam yourself, then run the installer again.")
            return 1
    else:
        outcomes = []

    say()
    if not with_game:
        if "removed" in outcomes:
            say("Done. Street Fighter V Access is installed, and it no longer starts with the game.")
        else:
            say("Done. Street Fighter V Access is installed, and Steam has been left as it was.")
        say("Start the mod from the desktop shortcut, before or after you start the game.")
        say("The first time, it sets up the game's text, which takes a few seconds, and says when it is ready.")
        say("It keeps running until you press F10, so press F10 when you have finished playing.")
        say("In the game, press Alt K to hear the keys.")
    elif any(o in ("set", "already") for o in outcomes):
        say("Done. Street Fighter V Access is installed.")
        say("Start Street Fighter V from Steam as usual. The mod starts with the game and closes with it.")
        say("The first time, it sets up the game's text, which takes a few seconds, and says when it is ready.")
        say("In the game, press Alt K to hear the keys.")
    elif "not ours" in outcomes:
        say("Street Fighter V already has launch options in Steam that this installer did not set, "
            "so they were left alone. The mod is installed, and the desktop shortcut starts it. "
            "To have it start with the game, clear those launch options on the game's Properties "
            "page in Steam, then run the installer again.")
    else:
        say("The mod is installed, and the desktop shortcut starts it. Steam has no record of "
            "Street Fighter V being played on this account, so it could not be made to start with "
            "the game. Start the game from Steam once, close it, then run the installer again.")
    say()
    wait_for_enter("Press Enter to close this window.")
    # Zero whatever happened: the window has already waited, and the batch
    # file pauses again on anything else.
    return 0


if __name__ == "__main__":
    sys.exit(main())
