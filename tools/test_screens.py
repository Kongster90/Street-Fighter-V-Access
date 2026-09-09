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

from sfv_access.app import announce, change_key  # noqa: E402

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
    # The live main menu, which the capture from Monday did not represent. It
    # carries an Arcade entry that one lacks, and its entries sit on a much
    # paler bar: the highlighted row measured 0.30 dark against a threshold of
    # 0.32, so the reader found no highlight at all and said nothing. Half of a
    # traced pass through this menu was silent for that reason.
    "sfv-20260909-154759": "CHALLENGES",
    "sfv-20260909-154802": "ARCADE",
    "sfv-20260909-154804": "Training",
    "sfv-20260909-154806": "CFN",
    "sfv-20260909-154808": "CASUAL MATCH",
    "sfv-20260909-154813": "ARCADE",
    "sfv-20260909-154819": "Battle Settings",
    # The main menu's far left column is icons with no text at all, holding
    # Options, Gallery, the terms and conditions and Exit. These read nothing
    # whatever until the panel across the middle was consulted, because there
    # is no label at the highlight to read and the selected icon is a solid
    # gold tile, which the band builder rejects on purpose as artwork.
    "sfv-20260909-160458": "Gallery",
    "sfv-20260909-160511": "EXIT",
    "sfv-20260909-160504": "LOGIN",
    # The Gallery submenu, whose entries start 126 pixels from the left edge.
    # The band was found and read correctly all along and then thrown away for
    # sitting inside a margin set on the assumption that no menu text does.
    "sfv-20260909-160500": "Arcade Mode Endings",
    "sfv-20260909-160502": "Arcade Mode Endings",
    # This was recorded for a long time as a capture taken mid fade, with
    # nothing gold on it and nothing to fix. It is nothing of the kind. The
    # screen is fully drawn, General Story is plainly highlighted on its dark
    # bar, and the description underneath is the one for General Story. The
    # gold simply was not saturated enough for the colour match, which is the
    # same pulse that made the Gallery submenu intermittent.
    "sfv-20260908-224334": "General Story",
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

# Entries that must NOT report a level. The drawn bar is found by looking at
# fixed columns, and on the main menu those columns hold artwork rather than a
# bar. CFN was announced as "CFN, level 10 of 10". A completely full bar is the
# only reading that cannot be told from a solid block by its shape, so that is
# the case that now has to show its cell boundaries as well.
NO_LEVEL = {
    "sfv-20260909-154806": "CFN is not a slider",
    "sfv-20260909-154815": "CFN is not a slider",
    "sfv-20260909-154759": "CHALLENGES is not a slider",
}

# The description under an entry, which is the widest text on the bottom line.
# The "Top User" badge in the corner is set much larger and is wider than a
# short description, so Exit was announcing that badge instead of its warning.
EXPECTED_DESCRIPTION = {
    "sfv-20260909-160511": "The application will close",
    "sfv-20260909-160458": "View the illustrations",
}

# Confirmation dialogs, where mishearing the answer is expensive: one of these
# asks whether to close the game. The chosen button is a thin gold outline
# round a dark fill, whose edges are too narrow to survive the band builder, so
# these read nothing at all until the fill was used as the signal instead.
DIALOGS = {
    "sfv-20260909-160509": ["close the application", "No is selected"],
    "sfv-20260909-160513": ["Internet Browser", "No is selected"],
}

# What the narration loop watches to decide the screen moved. Reading a screen
# correctly is no use if nothing notices you moved: the confirmation dialogs
# were read on arrival and then stayed silent as the user arrowed between Yes
# and No, because the buttons carry no gold and sit below the panel that was
# being watched. Pairs that must differ, and pairs that must not.
CHANGE_MOVED = [
    ("sfv-20260909-154802", "sfv-20260909-154804", "main menu, Arcade to Training"),
    ("sfv-20260909-092856", "sfv-20260909-092901", "settings, one volume row to the next"),
    ("sfv-20260909-160509", "sfv-20260909-154804", "a dialog opening over the main menu"),
    ("sfv-20260909-160458", "sfv-20260909-160511", "icon column, Gallery to Exit"),
]
CHANGE_STILL = [
    # The gold pulses hard enough to vanish between these two, 1367 gold pixels
    # against 27, with nothing touched. The loop must not treat that as movement.
    ("sfv-20260909-160500", "sfv-20260909-160502", "one screen, gold mid pulse"),
]

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

    print("\nentries whose description must be the right one:")
    for stem, want in EXPECTED_DESCRIPTION.items():
        if not (SNAPS / f"{stem}.png").exists():
            continue
        rgb, bgra = load(stem)
        said, _body, _idx, footer = announce(bgra, rgb)
        ok = want.lower() in footer.lower()
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        print(f"  {'ok  ' if ok else 'FAIL'} {stem[-6:]}  want description {want!r}")
        if not ok:
            print(f"        got {footer[:80]!r}")

    print("\nentries that must not report a level:")
    for stem, why in NO_LEVEL.items():
        if not (SNAPS / f"{stem}.png").exists():
            continue
        rgb, bgra = load(stem)
        said, _body, _idx, _footer = announce(bgra, rgb)
        ok = "level" not in said.lower()
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        print(f"  {'ok  ' if ok else 'FAIL'} {stem[-6:]}  {why}")
        if not ok:
            print(f"        said {said[:100]!r}")

    print("\nnoticing that the screen moved:")
    for a, b, why in CHANGE_MOVED:
        if not ((SNAPS / f"{a}.png").exists() and (SNAPS / f"{b}.png").exists()):
            continue
        ka = change_key(load(a)[0])
        kb = change_key(load(b)[0])
        ok = ka != kb
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        print(f"  {'ok  ' if ok else 'FAIL'} {why}")
    for a, b, why in CHANGE_STILL:
        if not ((SNAPS / f"{a}.png").exists() and (SNAPS / f"{b}.png").exists()):
            continue
        ka = change_key(load(a)[0])
        kb = change_key(load(b)[0])
        ok = ka == kb
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        print(f"  {'ok  ' if ok else 'FAIL'} {why}, must not count as movement")

    print("\nconfirmation dialogs:")
    for stem, wants in DIALOGS.items():
        if not (SNAPS / f"{stem}.png").exists():
            continue
        rgb, bgra = load(stem)
        said, _body, _idx, _footer = announce(bgra, rgb)
        missing = [w for w in wants if w.lower() not in said.lower()]
        passed, failed = (passed + 1, failed) if not missing else (passed, failed + 1)
        print(f"  {'ok  ' if not missing else 'FAIL'} {stem[-6:]}  {wants[0]!r}")
        if missing:
            print(f"        missing {missing}, said {said[:110]!r}")

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
