"""Take Street Fighter V Access back out of Steam and off the desktop.

Run by "Uninstall SFV Access.bat" in the installed folder. It removes the
desktop shortcut, and the game's launch options if the mod set them, closing
Steam for the moment that takes as the installer does. A player who answered
no to starting with the game has no launch options to change, so Steam is left
alone and never has to close. It then says where the folder is, for the player
to delete if they want to.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from sfv_access import game, instance  # noqa: E402
from tools import install, steam_launch_options as slo  # noqa: E402


def main() -> int:
    say = install.say
    say("Street Fighter V Access uninstaller.")
    say()
    # Every way out waits for Enter itself and returns 0, so the batch file
    # does not pause a second time.
    if game.is_running() or instance.already_running():
        say("Close Street Fighter V first, then run this again.")
        install.wait_for_enter("Press Enter to close this window.")
        return 0
    install.remove_shortcut()
    files = slo.config_files()
    outcomes: list[str] = []
    if install.ours_set(files):
        result = install.change_launch_options(files, None, "changed back")
        if result is None:
            say("Steam did not close. Close Steam yourself, then run this again.")
            install.wait_for_enter("Press Enter to close this window.")
            return 0
        outcomes = result
    say()
    if "removed" in outcomes or not outcomes:
        say("The desktop shortcut is gone and Street Fighter V will now start without the mod.")
        say(f"To remove the mod's files too, delete this folder: {HERE}")
    else:
        say("The game's launch options were not set by this mod, so they were left alone.")
    say()
    install.wait_for_enter("Press Enter to close this window.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
