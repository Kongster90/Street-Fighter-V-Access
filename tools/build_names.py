"""Build the character name table straight from the game's own text.

This replaces the learning process entirely. The localisation table keys each
character's display name by the same internal code the preview models report in
memory, as `ID_CMN_Char_E_<CODE>`, so the mapping can be read rather than
inferred from the screen.

Compares the result against whatever was learned by hovering, which is a real
check on both: the learner had no access to this table, and this table knows
nothing about what was on screen.

    python tools/build_names.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access import live  # noqa: E402

STRINGS = ROOT / "strings.json"
KEY_PATTERN = re.compile(r"ID_CMN_Char_[A-Z]_([A-Z0-9]{2,6})$", re.IGNORECASE)


def main() -> None:
    if not STRINGS.exists():
        print("strings.json is missing. Run tools/extract_strings.py first.")
        sys.exit(1)
    strings: dict[str, str] = json.loads(STRINGS.read_text(encoding="utf-8"))["strings"]

    extracted: dict[str, str] = {}
    for key, value in strings.items():
        match = KEY_PATTERN.search(key)
        if not match:
            continue
        name = value.strip()
        if not name or "\n" in name or len(name) > 24:
            continue
        code = match.group(1).upper()
        # Several keys exist per character; keep the first non-empty reading.
        extracted.setdefault(code, name)

    print(f"{len(extracted)} character names read from the game's own text\n")

    existing = live.load_name_file()
    learned = existing["names"]
    side = existing["player_one_side"]

    agree = [c for c in learned if c in extracted and learned[c] == extracted[c]]
    differ = [c for c in learned if c in extracted and learned[c] != extracted[c]]
    only_learned = [c for c in learned if c not in extracted]

    print(f"of {len(learned)} learned by hovering: {len(agree)} agree, {len(differ)} differ")
    for code in sorted(differ):
        print(f"   {code:5s} hovering said {learned[code]!r}, the game says {extracted[code]!r}")
    for code in sorted(only_learned):
        print(f"   {code:5s} learned as {learned[code]!r}, absent from the table")

    live.save_name_file(extracted, side)
    print(f"\nwrote {len(extracted)} names, player one on the {side} side")
    for code, name in sorted(extracted.items()):
        print(f"   {code:5s} {name}")


if __name__ == "__main__":
    main()
