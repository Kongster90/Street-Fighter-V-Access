"""Start Street Fighter V Access with the game, from Steam's launch options.

Steam runs a game's launch options as a command, putting the game's own
command where they say %command%. `tools/steam_launch_options.py --apply` sets
Street Fighter V's to run this with the pythonw.exe beside the Python that ran
it, the virtual environment's in a development copy and the bundled one in a
copy installed for players:

    "<that Python's folder>\\pythonw.exe" "<this folder>\\start_with_game.pyw" %command%

It starts the mod unless a copy is already running, then starts the game and
waits for it, so Steam sees the game running for as long as it really is.

Nothing here opens a window. pythonw has no console, and the mod runs under it
too, printing to snapshots/console-log.txt, so the game comes up in front as
it always did. The mod is told --with-game, which makes it close when the game
does rather than keep the Alt keys from every other program.

Started without a game command, as by double-clicking, it only starts the mod,
which then stays open like one started from `Start SFV Access.bat`.
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from sfv_access import instance  # noqa: E402

# The mod runs under the Python that runs this, without a console.
PYTHONW = Path(sys.executable).with_name("pythonw.exe")
LOG = HERE / "snapshots" / "console-log.txt"


def start_mod(with_game: bool) -> None:
    if instance.already_running():
        return
    LOG.parent.mkdir(exist_ok=True)
    command = [str(PYTHONW), str(HERE / "run.py")] + (["--with-game"] if with_game else [])
    with LOG.open("wb") as log:
        subprocess.Popen(command, cwd=HERE, stdin=subprocess.DEVNULL,
                         stdout=log, stderr=subprocess.STDOUT)


def main() -> int:
    game = sys.argv[1:]
    try:
        start_mod(with_game=bool(game))
    except Exception:
        pass  # the game starts whatever happens to the mod
    if not game:
        return 0
    return subprocess.call(game)


if __name__ == "__main__":
    sys.exit(main())
