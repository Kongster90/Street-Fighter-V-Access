"""List every character code the game has data for.

Each fighter ships a personal data asset named after its code, so the object
list gives the full roster without needing to visit character select. That
turns learning names from an open-ended task into a measurable one.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access import live, unreal  # noqa: E402

OUT = ROOT / "roster.json"

# Assets are named like DA_KEN_Personal or DA_Z25_Personal.
ASSET_PATTERN = re.compile(r"^DA_([A-Z0-9]{2,6})_Personal$", re.IGNORECASE)


def main() -> None:
    session = live.shared()
    if not session.attach():
        print("Street Fighter V is not running.")
        sys.exit(1)

    pm, names, objects = session.pm, session.names, session.objects
    layout = objects.layout

    codes: set[str] = set()
    for obj, name in session.find_by_class("KWCharaPersonalDataAsset", limit=200):
        match = ASSET_PATTERN.match(name)
        if match:
            codes.add(match.group(1).upper())

    if not codes:
        print("no character data assets found; is the game past the title screen?")
        sys.exit(2)

    known = live.load_name_file()["names"]
    missing = sorted(c for c in codes if c not in known)
    stale = sorted(c for c in known if c not in codes)

    OUT.write_text(
        json.dumps({"codes": sorted(codes)}, indent=1), encoding="utf-8"
    )

    print(f"{len(codes)} character codes in the game's data")
    print(f"{len(known)} already named, {len(missing)} still to learn\n")
    print("named:")
    for code in sorted(known):
        print(f"   {code:5s} {known[code]}")
    print("\nstill unnamed:")
    print("   " + ", ".join(missing))
    if stale:
        print(f"\nnamed but not in the roster data, worth a look: {', '.join(stale)}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
