"""Find the character names in the extracted localisation table.

If the table keys them by the same internal code the game reports in memory,
the whole OCR learning exercise becomes unnecessary: the mapping can simply be
read.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

STRINGS = ROOT / "strings.json"
ROSTER = ROOT / "roster.json"


def main() -> None:
    strings: dict[str, str] = json.loads(STRINGS.read_text(encoding="utf-8"))["strings"]
    try:
        codes = set(json.loads(ROSTER.read_text(encoding="utf-8"))["codes"])
    except Exception:
        codes = set()
    print(f"{len(strings):,} strings, {len(codes)} known character codes\n")

    # Namespaces are the first path element of the key.
    spaces: dict[str, int] = {}
    for key in strings:
        spaces[key.split("/", 1)[0]] = spaces.get(key.split("/", 1)[0], 0) + 1
    interesting = {
        ns: n
        for ns, n in spaces.items()
        if any(w in ns.lower() for w in ("chara", "name", "player", "fighter", "select"))
    }
    print("namespaces that look character related:")
    for ns, n in sorted(interesting.items(), key=lambda kv: -kv[1])[:15]:
        print(f"  {n:6,}  {ns}")

    # Keys that mention a code we already know about.
    print("\nkeys containing a known character code, with short values:")
    shown = 0
    for key, value in strings.items():
        if len(value) > 24 or "\n" in value:
            continue
        found = [c for c in codes if re.search(rf"(?<![A-Z0-9]){re.escape(c)}(?![A-Z0-9])", key, re.I)]
        if not found:
            continue
        print(f"  {key[:70]:70s} -> {value!r}")
        shown += 1
        if shown >= 40:
            print("  ...")
            break
    if not shown:
        print("  none")

    # Failing that, look for the names themselves and report how they are keyed.
    print("\nhow known display names are keyed:")
    for want in ("ZANGIEF", "CHUN-LI", "BIRDIE", "KARIN", "NASH", "AKUMA", "MENAT"):
        hits = [(k, v) for k, v in strings.items() if v.strip().upper() == want]
        for key, value in hits[:3]:
            print(f"  {value:10s} {key}")
        if not hits:
            print(f"  {want:10s} (no exact match)")


if __name__ == "__main__":
    main()
