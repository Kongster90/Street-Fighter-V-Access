"""Check what the reader says about every captured screen.

Expectations come from reading the captures by eye and from the game's own
description line, which names the highlighted entry. Needs no game running.

Only the entry name is asserted. Position and description move around as
recognition improves and are reported for information rather than checked.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access.app import announce  # noqa: E402

SNAPS = ROOT / "snapshots"

# stem -> the entry that is actually highlighted, or None where nothing is.
EXPECTED = {
    "sfv-20260908-224143": "Training",            # main menu
    "sfv-20260908-224251": "Sound Settings",      # options list
    "sfv-20260908-224301": "PLAYER 1 VS PLAYER 2",
    "sfv-20260908-224326": "Favorite Character",  # battle settings, known gap
    "sfv-20260908-224330": "STREET FIGHTER I",    # arcade path select
    "sfv-20260908-224342": "Trials",
    "sfv-20260908-224528": "Restart Battle",      # training pause menu
    "sfv-20260908-224531": "Status",
    "sfv-20260908-224536": "1P Health Gauge",
    "sfv-20260909-090747": "Sound Settings",
    "sfv-20260909-090755": "BGM Volume",          # a slider row
    "sfv-20260909-090822": "Screen Brightness",   # another slider row
    "sfv-20260909-090836": "Pause Menu Display",
    # Volume rows, which were naming the page rather than the setting until
    # bands were grouped and the panel's group preferred over the page list.
    "sfv-20260909-092856": "SFX Volume",
    "sfv-20260909-092901": "Character Voice Volume",
    "sfv-20260909-092904": "Announcer Voice Volume",
    "sfv-20260909-092919": "Adjust Lower HUD Position",
    "sfv-20260909-092922": "Upper HUD Display",
}

# Entries that should also report their current value. Left out where the value
# is a drawn bar whose number the recogniser cannot reach.
EXPECTED_VALUES = {
    "sfv-20260908-224536": "Auto Recover",
    # Drawn level bars, counted rather than read. The levels shown on the other
    # rows of these same captures confirm the numbers.
    "sfv-20260909-092904": "level 8 of 10",
    "sfv-20260909-092856": "level 10 of 10",
    "sfv-20260909-092901": "level 10 of 10",
    "sfv-20260909-090755": "level 1 of 10",
}

# Stage select, which has no highlighted entry and is read by position. The
# names are stylised and come back badly, so these also check that the game's
# own text repairs them: "Ringof PoWer" into "Ring of Power" and
# "Hollif ollyBeatdown" into "Holly Jolly Beatdown".
STAGES = {
    "sfv-20260909-094308": ["The Grid"],
    "sfv-20260909-094315": ["The Grid Alternative"],
    "sfv-20260909-094351": ["Ring of Justice", "Time 14:30", "80 degrees"],
    "sfv-20260909-094359": ["Ring of Power", "Time 20:00", "Weather Clear"],
    "sfv-20260909-094430": ["Metro City Bay Area", "75 degrees"],
    "sfv-20260909-094434": ["Metro City Bay Area", "Time 5:00"],
    "sfv-20260909-094437": ["Holly Jolly Beatdown", "Weather Snowy", "45 degrees"],
    "sfv-20260908-224359": ["The Grid"],
    "sfv-20260908-224410": ["The Grid"],
}

# Screens with no highlighted text at all; these must not invent one.
NO_HIGHLIGHT = {
    "sfv-20260908-224524": "in a match, gauges instead",
    "sfv-20260908-224515": "blank",
    "sfv-20260908-224443": "blank",
    # Caught while the menu was still fading in. Every pixel of the entry is
    # pure grey, from 17 to 153 with red, green and blue equal, so there is no
    # gold anywhere and no colour-based detector can find a highlight. Nothing
    # to fix; the screen simply was not finished drawing.
    "sfv-20260908-224334": "captured mid fade, nothing is gold yet",
}


def load(stem):
    rgb = np.asarray(Image.open(SNAPS / f"{stem}.png").convert("RGB"))
    bgra = np.ascontiguousarray(
        np.dstack([rgb[..., ::-1], np.full(rgb.shape[:2], 255, np.uint8)])
    )
    return rgb, bgra


def main() -> None:
    passed = failed = 0
    print("screens with a highlighted entry:")
    for stem, want in EXPECTED.items():
        if not (SNAPS / f"{stem}.png").exists():
            continue
        rgb, bgra = load(stem)
        said, body, idx, _footer = announce(bgra, rgb)
        got = body[idx].text if idx is not None and idx < len(body) else ""
        ok = want.lower() in said.lower() or want.lower() in got.lower()
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        print(f"  {'ok  ' if ok else 'FAIL'} {stem[-6:]}  want {want!r}")
        if not ok:
            print(f"        said {said[:100]!r}")

    print("\nentries that should report a value:")
    for stem, want in EXPECTED_VALUES.items():
        if not (SNAPS / f"{stem}.png").exists():
            continue
        rgb, bgra = load(stem)
        said, _body, _idx, _footer = announce(bgra, rgb)
        ok = want.lower() in said.lower()
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        print(f"  {'ok  ' if ok else 'FAIL'} {stem[-6:]}  want value {want!r}")
        if not ok:
            print(f"        said {said[:100]!r}")

    print("\nstage select:")
    for stem, wants in STAGES.items():
        if not (SNAPS / f"{stem}.png").exists():
            continue
        rgb, bgra = load(stem)
        said, _body, _idx, _footer = announce(bgra, rgb)
        missing = [w for w in wants if w.lower() not in said.lower()]
        passed, failed = (passed + 1, failed) if not missing else (passed, failed + 1)
        print(f"  {'ok  ' if not missing else 'FAIL'} {stem[-6:]}  {wants[0]!r}")
        if missing:
            print(f"        missing {missing}, said {said[:110]!r}")

    print("\nscreens with nothing highlighted:")
    for stem, why in NO_HIGHLIGHT.items():
        if not (SNAPS / f"{stem}.png").exists():
            continue
        rgb, bgra = load(stem)
        said, _body, idx, _footer = announce(bgra, rgb)
        ok = idx is None
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        print(f"  {'ok  ' if ok else 'FAIL'} {stem[-6:]}  {why}")
        if not ok:
            print(f"        said {said[:100]!r}")

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
