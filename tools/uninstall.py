"""Take Street Fighter V Access back out of Steam's launch options.

Run by "Uninstall SFV Access.bat" in the installed folder. It closes Steam for
the moment that takes, as the installer does, and then says where the folder
is, for the player to delete if they want to.
"""

from __future__ import annotations

import subprocess
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
    was_running = slo.steam_running()
    if was_running:
        say("Steam needs to close for a moment so the game's launch options can be changed back. "
            "It will open again afterwards.")
        install.wait_for_enter("Press Enter to close Steam and carry on.")
        if not install.close_steam():
            say("Steam did not close. Close Steam yourself, then run this again.")
            install.wait_for_enter("Press Enter to close this window.")
            return 0
    outcomes = [slo.change(path, None) for path in slo.config_files()]
    if was_running and install.steam_exe() is not None:
        subprocess.Popen([str(install.steam_exe())])
        say("Opening Steam again.")
    say()
    if "removed" in outcomes or all(o in ("already", "no game") for o in outcomes):
        say("Street Fighter V will now start without the mod.")
        say(f"To remove the mod's files too, delete this folder: {HERE}")
    else:
        say("The game's launch options were not set by this mod, so they were left alone.")
    say()
    install.wait_for_enter("Press Enter to close this window.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
