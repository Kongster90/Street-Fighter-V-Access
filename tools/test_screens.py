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

from sfv_access import menu, screens, strings  # noqa: E402
from sfv_access.app import (  # noqa: E402
    _POSITION_CLAUSE,
    _leading_clause,
    announce,
    change_key,
)

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
    "sfv-20260909-164459": ["close the application", "No is selected"],
    "sfv-20260909-164501": ["close the application", "Yes is selected"],
    "sfv-20260909-164505": ["close the application", "Yes is selected"],
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
    # Two answers side by side on one row. Every pair above differs vertically,
    # so all of them passed while the dark map was being split into rows twice
    # over and had no horizontal resolution at all. These are the only captures
    # that can catch that, and they are the case that matters most.
    ("sfv-20260909-164459", "sfv-20260909-164501", "dialog, No to Yes"),
    ("sfv-20260909-164501", "sfv-20260909-164503", "dialog, Yes back to No"),
]
CHANGE_STILL = [
    # The gold pulses hard enough to vanish between these two, 1367 gold pixels
    # against 27, with nothing touched. The loop must not treat that as movement.
    ("sfv-20260909-160500", "sfv-20260909-160502", "one screen, gold mid pulse"),
]

# The position an entry is announced with. It used to count every line
# recognised anywhere on screen, including the panel's own text and whatever
# the artwork yielded, so idling on the main menu produced "Battle Settings, 10
# of 12", then 9 of 11, then 11 of 13, without anything being touched. It
# counts the entry's own column now, which is both stable and what a person
# would say. CFN stands alone in its column, and an entry with no peers is
# announced without a position at all rather than as "1 of 1".
EXPECTED_POSITION = {
    "sfv-20260909-154804": "5 of 6",
    "sfv-20260909-154759": "4 of 6",
    "sfv-20260909-160500": "1 of 2",
}
NO_POSITION = {"sfv-20260909-154806": "CFN has no peers in its column"}

# The world map behind the main menu draws a date and a clock beside its
# cursor. They sit in the content area, so position does not exclude them, and
# they are drawn over a dark marker, which is what the fallback looks for. One
# session announced the clock 511 times, once per minute and again whenever
# recognition read the noise around it differently. Taken from the spoken log
# of that session, plus the entries that must survive the same rule.
MAP_CHROME = [
    "4:55 PM", "m 4:55 PM", "4,' 4:55 PM", "_ v 4:55 PM", "7,\" 4:55 PM",
    "56 P M", "sep 9, 2026", "sep e, 20>6'", "'/,' 4:56 PM", "w 4:55 P",
]
NOT_MAP_CHROME = [
    "Sound", "CFN", "STREET FIGHTER I", "1P Health Gauge", "DLC BGM",
    "PLAYER 1 VS PLAYER 2", "Good Luck Charms", "Arcade Mode Endings",
    "Ryu's Theme (Japan) from Street Fighter II",
]

# A run of captures taken while moving through stage select, in order. Each
# stage should announce itself once.
#
# It did not. Stage select reads correctly, but its detail arrives in pieces:
# one stage read "Time 4:30" and corrected itself to "14:30" on the next look,
# another gained its temperature, and The Grid Alternative produced four
# readings in a row. Every one was announced and every one interrupted the
# last, so what reached the user was a word of each and then nothing. Stages
# seemed not to read at all when in fact they read fine.
STAGE_RUN = sorted(p.stem for p in SNAPS.glob("sfv-20260909-2234*.png")) + sorted(
    p.stem for p in SNAPS.glob("sfv-20260909-2235*.png")
)
# Eight stages were visited. One reading of one of them truncates "The Grid
# Alternative" to "The Grid", which is itself a real stage, so correction
# cannot catch it and it costs one extra announcement.
STAGE_RUN_MAX = 9

# Stage names the reader must refuse, taken verbatim from a session's spoken
# log. These names are outlined type over full-bleed artwork on an animating
# screen, so sitting on one stage produced twelve spellings in six seconds,
# each announced, each cutting off the one before it. A real stage name is in
# the game's own word list and every one of these scored below what correction
# accepts, so they are held back and the next frame gets another go.
BAD_STAGE_NAMES = [
    "ki+aCRiverside", "NWåCkivénSide", "RuvaIzRivers1de",
    "RivåiüRiversidé", "RivåLRiWersidé",
    "Rfvå/ Riveisidé", "Bing•tPriae", "Qing ofiPriae",
    "_ingNof'Prjde", "Weather I Clear", "EWeathe(l Clear",
]
GOOD_STAGE_NAMES = [
    "Rival Riverside", "Ring of Pride", "Ring of Power", "The Grid", "Dojo",
    "Marina of Fortune", "King's Court", "Kasugano Residence",
    "Suzaku Castle at Night", "Flamenco Tavern",
    # Damaged but still repairable, which is the line this must not cross.
    "Ringof PoWer", "Hollif ollyBeatdown",
]

# The conditions are checked through the read key, which includes them. Moving
# through the screen says the name alone: time, temperature and weather do not
# affect play, and three of them after every stage is a lot of talking for
# nothing. STAGE_RUN above replays the moving case and so sees names only.

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

    print("\nthe position an entry is announced with:")
    for stem, want in EXPECTED_POSITION.items():
        if not (SNAPS / f"{stem}.png").exists():
            continue
        rgb, bgra = load(stem)
        said, _body, _idx, _footer = announce(bgra, rgb, with_description=False)
        ok = want in said
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        print(f"  {'ok  ' if ok else 'FAIL'} {stem[-6:]}  want {want!r}")
        if not ok:
            print(f"        said {said[:80]!r}")
    for stem, why in NO_POSITION.items():
        if not (SNAPS / f"{stem}.png").exists():
            continue
        rgb, bgra = load(stem)
        said, _body, _idx, _footer = announce(bgra, rgb, with_description=False)
        ok = " of " not in said
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        print(f"  {'ok  ' if ok else 'FAIL'} {stem[-6:]}  {why}")
        if not ok:
            print(f"        said {said[:80]!r}")

    print("\nthe world map's clock and date are not menu entries:")
    wrong = [t for t in MAP_CHROME if not menu.looks_like_map_chrome(t)]
    wrong += [t for t in NOT_MAP_CHROME if menu.looks_like_map_chrome(t)]
    passed, failed = (passed + 1, failed) if not wrong else (passed, failed + 1)
    print(f"  {'ok  ' if not wrong else 'FAIL'} "
          f"{len(MAP_CHROME)} rejected, {len(NOT_MAP_CHROME)} kept")
    if wrong:
        print(f"        got the wrong answer for {wrong}")

    print("\nidling on one screen must not repeat itself:")
    for a, b, why in CHANGE_STILL:
        if not ((SNAPS / f"{a}.png").exists() and (SNAPS / f"{b}.png").exists()):
            continue
        sa = announce(*load(a)[::-1], with_description=False)[0]
        sb = announce(*load(b)[::-1], with_description=False)[0]
        ok = _POSITION_CLAUSE.sub("", sa) == _POSITION_CLAUSE.sub("", sb)
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        print(f"  {'ok  ' if ok else 'FAIL'} {why}, must read the same both times")
        if not ok:
            print(f"        {sa[:60]!r} then {sb[:60]!r}")

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

    if STAGE_RUN:
        print("\nmoving through stage select, one announcement per stage:")
        last, spoken = "", []
        for stem in STAGE_RUN:
            rgb, bgra = load(stem)
            said, _b, _i, _f = announce(bgra, rgb, with_description=False)
            if not said or said.startswith(("No highlight", "No text")):
                continue
            ident = _leading_clause(_POSITION_CLAUSE.sub("", said))
            if ident == last:
                continue
            last = ident
            spoken.append(ident)
        ok = len(spoken) <= STAGE_RUN_MAX
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        print(f"  {'ok  ' if ok else 'FAIL'} {len(STAGE_RUN)} frames give "
              f"{len(spoken)} announcements, at most {STAGE_RUN_MAX} allowed")
        if not ok:
            for line in spoken:
                print(f"        {line}")

    print("\nstage names the reader must and must not accept:")
    vocab = strings.shared()
    wrong = [t for t in BAD_STAGE_NAMES
             if vocab.correct(t).score >= screens.NAME_CONFIDENCE]
    wrong += [t for t in GOOD_STAGE_NAMES
              if vocab.correct(t).score < screens.NAME_CONFIDENCE]
    passed, failed = (passed + 1, failed) if not wrong else (passed, failed + 1)
    print(f"  {'ok  ' if not wrong else 'FAIL'} "
          f"{len(BAD_STAGE_NAMES)} refused, {len(GOOD_STAGE_NAMES)} accepted")
    if wrong:
        print(f"        got the wrong answer for {wrong}")

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
