"""Recover the character code to name mapping from the game's own data.

Hovering over the roster and reading names off the screen has been the only way
to build this table, and it is slow and it goes wrong quietly. The game turns
out to carry a better answer in its own files.

`Content/Chara/DA_VTriggerNameAsset` and `DA_VSkillNameAsset` list, for every
playable character, the character code followed by the localisation hashes of
its two V-Trigger or V-Skill names. Those hashes resolve against the extracted
string table, so the paks alone give code to move name for all 45 characters,
with the game running or not.

A move name is not a character name, and the step from one to the other is the
only part of this that comes from outside the game: NAMED_BY_VTRIGGER below
says which character owns which V-Trigger. Two checks keep that honest.

Every name it produces must appear verbatim in the game's own string table,
which is the same test the screen learner applies. And where the screen learner
has already recorded a code, the two must agree; disagreements are reported
rather than resolved, exactly as `learn_names.py` refuses to overwrite quietly.

This writes a proposal to `snapshots/character_names.proposed.json` and stops,
because some of its entries contradict what hovering recorded and that is a
decision for a person. Passing --apply writes the real table, keeping a copy of
what was there first.

Usage:
    python tools/names_from_data.py
    python tools/names_from_data.py --apply
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.extract_strings import PAKS, load_key, read_file, read_index  # noqa: E402

VTRIGGER_ASSET = "DA_VTriggerNameAsset"
VSKILL_ASSET = "DA_VSkillNameAsset"

STRINGS_FILE = ROOT / "strings.json"
NAME_FILE = ROOT / "character_names.json"
PROPOSAL = ROOT / "snapshots" / "character_names.proposed.json"
BACKUP = ROOT / "snapshots" / "character_names.before-data.json"

_ASCII = re.compile(rb"[\x20-\x7e]{3,}")
_HASH = re.compile(r"^[0-9A-F]{32}$")
_CODE = re.compile(r"^[A-Z0-9]{3}$")

# Which character owns which V-Trigger. This is the one piece of knowledge that
# does not come out of the game files, so each entry is keyed on the first
# V-Trigger name, which is unique across the roster, and every name it yields is
# checked against the game's string table before it is offered.
#
# Three of these look wrong and are not. Capcom's internal codes use the
# Japanese names, which the western release swaps: the dictator is Vega in
# Japan, the claw fighter is Balrog, and the boxer is Bison. So VEG is M. Bison,
# BLR is Vega and BSN is Balrog. The rule in `learn_names.py` that a code should
# read as the initials of its name rejects all three, which is why hovering
# could never have learned them.
NAMED_BY_VTRIGGER = {
    "DENJIN RENKI": "RYU",
    "HEAT RUSH": "KEN",
    "RENKIKO": "CHUN-LI",
    "DELTA DRIVE": "CAMMY",
    "ENJOY TIME": "BIRDIE",
    "TORRENT OF POWER": "NECALLI",
    "YSAAR": "RASHID",
    "SPARK SHOW": "LAURA",
    "GUREN NO KATA": "KARIN",
    "SONIC MOVE": "NASH",
    "YOGA BURNER": "DHALSIM",
    "CYCLONE LARIAT": "ZANGIEF",
    "C'MON NADESHIKO!": "R. MIKA",
    "DOKUNOMU": "F.A.N.G",
    "RAGE SHIFT": "ALEX",
    "SOLID PUNCHER": "GUILE",
    "ROKUSHAKU HOROKUDAMA": "IBUKI",
    "FENG SHUI ENGINE alpha": "JURI",
    "AEGIS REFLECTOR": "URIEN",
    "PSYCHO POWER": "M. BISON",
    "BLOODY KISS": "VEGA",
    "CRAZY RUSH": "BALROG",
    "DIAMOND DUST": "KOLIN",
    "DOHATSU SHOTEN": "AKUMA",
    "PSYCHO CANNON": "ED",
    "WISDOM OF THOTH": "MENAT",
    "MAX POWER": "ABIGAIL",
    "BUSHINRYU SHINGEKIKO": "ZEKU",
    "HARU ARASHI": "SAKURA",
    "JUNGLE DYNAMO": "BLANKA",
    "STAERKEN": "FALKE",
    "SIDE ARM": "CODY",
    "MAXIMUM PRESIDENT": "G",
    "TIGER CHARGE": "SAGAT",
    "TAIGYAKU MUDO": "KAGE",
    "POISON COCKTAIL": "POISON",
    "ONIGAWARA": "E. HONDA",
    "BURNING FIGHT": "LUCIA",
    "PRIMAL FIRE": "GILL",
    "TANDEN IGNITION": "SETH",
    "HAOH GADOKEN": "DAN",
    "SOUL DIMENSION": "ROSE",
    "MANRIKITAN": "ORO",
    "OTOKO NO SENAKA": "AKIRA",
    "FULLY ARMED": "LUKE",
}


def _asset_words(fragment: str) -> list[str]:
    """The readable strings held in the first pak asset matching `fragment`."""
    key = load_key()
    for pak in sorted(PAKS.glob("*.pak")):
        _mount, entries = read_index(pak)
        for entry in entries:
            if fragment in entry.name:
                data = read_file(pak, entry, key)
                return [m.group().decode() for m in _ASCII.finditer(data)]
    raise SystemExit(f"{fragment} is not in the paks")


def moves_by_code(fragment: str, strings: dict[str, str]) -> dict[str, list[str]]:
    """Character code to its move names, read out of one name asset.

    The asset stores a code, then alternating localisation hash and readable
    text id for each of that character's two moves, then the next code.
    """
    out: dict[str, list[str]] = {}
    code: str | None = None
    for word in _asset_words(fragment):
        if _HASH.match(word):
            if code is not None and word in strings:
                out[code].append(strings[word])
        elif _CODE.match(word):
            code = word
            out.setdefault(code, [])
    return out


def main() -> None:
    strings = json.loads(STRINGS_FILE.read_text(encoding="utf-8"))["strings"]
    vocabulary = {v.strip().upper() for v in strings.values()}

    vtriggers = moves_by_code(VTRIGGER_ASSET, strings)
    vskills = moves_by_code(VSKILL_ASSET, strings)
    print(f"{len(vtriggers)} characters carry V-Trigger names in the game's data")

    named: dict[str, str] = {}
    unknown: list[str] = []
    for code, moves in sorted(vtriggers.items()):
        who = NAMED_BY_VTRIGGER.get(moves[0]) if moves else None
        if who is None:
            unknown.append(f"{code}: {' | '.join(moves) or 'no moves listed'}")
        elif who.upper() not in vocabulary:
            unknown.append(f"{code}: {who} is not a string the game contains")
        else:
            named[code] = who

    if unknown:
        print(f"\n{len(unknown)} could not be named:")
        for line in unknown:
            print("  ", line)

    recorded = json.loads(NAME_FILE.read_text(encoding="utf-8"))
    old = recorded["names"]
    agree = sorted(c for c in named if old.get(c) == named[c])
    clash = sorted(c for c in named if c in old and old[c] != named[c])
    fresh = sorted(c for c in named if c not in old)

    print(f"\n{len(named)} named from the game's data, all verbatim in its string table")
    print(f"{len(agree)} agree with what hovering already learned")
    print(f"{len(fresh)} are new: {', '.join(fresh)}")

    if clash:
        print(f"\n{len(clash)} contradict the recorded table. Nothing is overwritten.")
        for code in clash:
            moves = " and ".join(vtriggers[code][:2])
            skills = " and ".join(vskills.get(code, [])[:2])
            print(f"   {code}  recorded {old[code]}, data says {named[code]}")
            print(f"        V-Trigger {moves}")
            if skills:
                print(f"        V-Skill   {skills}")
            landed = [c for c, n in named.items() if n == old[code]]
            if landed:
                print(f"        {old[code]} belongs to {', '.join(landed)} in the data")

    keep = {c: n for c, n in old.items() if c not in named}
    proposal = {
        "player_one_side": recorded["player_one_side"],
        "names": dict(sorted({**keep, **named}.items())),
    }
    PROPOSAL.write_text(json.dumps(proposal, indent=1) + "\n", encoding="utf-8")
    print(f"\nproposal written to {PROPOSAL.relative_to(ROOT)}")
    print(f"{len(proposal['names'])} characters, against {len(old)} recorded")

    if "--apply" not in sys.argv:
        print("\nrun again with --apply to write it to the real table")
        return

    BACKUP.write_text(json.dumps(recorded, indent=1) + "\n", encoding="utf-8")
    NAME_FILE.write_text(json.dumps(proposal, indent=1) + "\n", encoding="utf-8")
    print(f"\nwrote {NAME_FILE.name}, keeping the old one at {BACKUP.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
