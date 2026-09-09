"""Check the learned character names against the game's own text.

The names were read off the screen by recognition, which makes mistakes. The
localisation table is the game's own copy of every string it can draw, so a
learned name that appears there verbatim is confirmed by a source that knows
nothing about what was on screen. One that does not appear is a misreading.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access import live  # noqa: E402

STRINGS = ROOT / "strings.json"


def load_vocabulary() -> set[str]:
    """Every short single-line string the game can display, upper-cased."""
    data = json.loads(STRINGS.read_text(encoding="utf-8"))["strings"]
    return {
        v.strip().upper()
        for v in data.values()
        if v.strip() and "\n" not in v and len(v.strip()) <= 24
    }


def main() -> None:
    if not STRINGS.exists():
        print("strings.json is missing. Run tools/extract_strings.py first.")
        sys.exit(1)

    vocabulary = load_vocabulary()
    names = live.load_name_file()["names"]
    print(f"{len(vocabulary):,} short strings in the game's text")
    print(f"{len(names)} learned names to check\n")

    confirmed = sorted(c for c, n in names.items() if n.upper() in vocabulary)
    missing = sorted(c for c, n in names.items() if n.upper() not in vocabulary)

    print(f"confirmed by the game's own text ({len(confirmed)}):")
    for code in confirmed:
        print(f"   {code:5s} {names[code]}")

    if missing:
        print(f"\nnot found in the game's text, so probably misread ({len(missing)}):")
        for code in missing:
            near = sorted(
                (v for v in vocabulary if v.startswith(names[code].upper()[:3])),
                key=len,
            )[:4]
            print(f"   {code:5s} {names[code]!r}   nearest: {near}")
    else:
        print("\nevery learned name appears in the game's own text")


if __name__ == "__main__":
    main()
