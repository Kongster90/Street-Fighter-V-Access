"""Pull the game's own English text out of its pak files, by hand.

The mod does this by itself the first time it finds the game without
strings.json; see `sfv_access/gametext.py`. This needs the key saved by
tools/find_pak_key.py and the game running, to find where it is installed.

Writes strings.json next to the project.

    python tools/extract_strings.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access import gametext  # noqa: E402


def main() -> None:
    try:
        key = bytes.fromhex(gametext.KEY_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        print("No key: run tools/find_pak_key.py first, with the game running.")
        sys.exit(1)
    game = gametext.running_game()
    if game is None:
        print(f"{gametext.EXE} is not running, so where it is installed is not known. Start it first.")
        sys.exit(1)
    _pid, paks = game
    strings = gametext.extract_strings(paks, key)
    gametext.write_strings(strings)
    print(f"{len(strings):,} strings written to {gametext.STRINGS_FILE}")
    values = list(strings.values())
    for probe in ("RANKED", "TRAINING", "ZEKU", "Health Gauge"):
        print(f"  {probe!r}: {[v for v in values if probe.lower() in v.lower()][:3]}")


if __name__ == "__main__":
    main()
