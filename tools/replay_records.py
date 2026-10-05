"""Replay a recording from `tools/record_screens.py` through the narrator.

    .venv\\Scripts\\python.exe tools\\replay_records.py snapshots\\<name>\\records.jsonl

Rebuilds each record's shown texts (place, tint, selection mark, note, chain
and the part's name) and steps a `memory_narration.Narrator` through them a
tenth of a second at a time, as the mod reads, printing what it would say
with the seconds since the first record. The texts are as the recording took
them, so a change to how the reader itself names or reads them (Fight Money,
pictures) is not replayed; a change to the narrator or to scaleform's rules
over the items is. Used on 2026-10-04 to check Fighting Chance's prompt,
cutscene and prizes against the user's own readings before they heard them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access import memory_narration as mn, scaleform as sf  # noqa: E402


def load(path: Path) -> list[tuple[float, list[sf.TextItem]]]:
    readings = []
    for line in path.open(encoding="utf-8"):
        record = json.loads(line)
        hours, minutes, rest = record["time"][:2], record["time"][2:4], record["time"][4:]
        at = int(hours) * 3600 + int(minutes) * 60 + float(rest)
        items = []
        for shown in record["shown"]:
            chain = tuple(int(c, 16) for c in shown.get("chain", [])) or (1, 2)
            items.append(sf.TextItem(shown["text"], shown["x"], shown["y"], tuple(shown["tint"]), len(chain),
                                     chain=chain, chosen=shown["mark"] == "+", part=shown["part"],
                                     note=shown["note"]))
        sf.name_amounts(items)
        readings.append((at, items))
    return readings


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    readings = load(Path(sys.argv[1]))
    narrator = mn.Narrator()
    start = readings[0][0]
    for index, (at, items) in enumerate(readings):
        until = readings[index + 1][0] if index + 1 < len(readings) else at + 1
        now = at
        while now < until:
            said = narrator.step(items, now)
            if said:
                print(f"{now - start:7.1f}  {said}")
            now += 0.1


if __name__ == "__main__":
    main()
