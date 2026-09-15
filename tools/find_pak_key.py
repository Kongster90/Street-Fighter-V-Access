"""Recover the pak encryption key from the running game, by hand.

The mod does this by itself the first time it finds the game without
strings.json; see `sfv_access/gametext.py` for how. This prints the search as
it goes, and with --heap also sweeps the heap if the executable's own data
holds no key, which is slow.

    python tools/find_pak_key.py [--heap]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access import gametext  # noqa: E402
from sfv_access.memory import ProcessMemory  # noqa: E402


def main() -> None:
    game = gametext.running_game()
    if game is None:
        print(f"{gametext.EXE} is not running.")
        sys.exit(1)
    pid, paks = game
    block, name = gametext.sample_block(paks)
    print(f"paks: {paks}")
    print(f"testing against {name}")
    print(f"ciphertext: {block[:16].hex()}\n")

    t0 = time.perf_counter()

    def progress(key_len, label, done, total):
        if label != "heap" or done % 2000 == 0:
            print(f"  {key_len * 8}-bit keys: {label} searched ({done:,}/{total:,}), {time.perf_counter() - t0:.0f} s")

    with ProcessMemory(pid) as pm:
        hit = gametext.find_key(pm, block, heap="--heap" in sys.argv, progress=progress)
    if hit is None:
        print(f"\nnot found in {time.perf_counter() - t0:.0f} s")
        sys.exit(1)
    where, key, out = hit
    print(f"\nFOUND at 0x{where:x} in {time.perf_counter() - t0:.1f} s")
    print(f"  key       : {key.hex()}")
    print(f"  as text   : {key!r}")
    print(f"  plaintext : {out!r}")
    gametext.KEY_FILE.write_text(key.hex(), encoding="utf-8")
    print(f"  saved to  : {gametext.KEY_FILE}")


if __name__ == "__main__":
    main()
