"""Replay character select traffic against the name learner.

Needs no game running. The first scenario is the exact situation that produced
a table where six different codes had all been learned as KEN: player two
parked on Ken while player one moves along the roster.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import learn_names as LN  # noqa: E402
from sfv_access import live  # noqa: E402
from sfv_access.speech import Speaker  # noqa: E402

# Point the learner at a scratch file before anything touches it. An earlier
# version of this test wrote to and then deleted the real table, destroying a
# roster that had taken a session in the game to build.
SCRATCH = ROOT / "snapshots" / "test-character-names.json"
live.NAME_MAP_FILE = SCRATCH
LN.live.NAME_MAP_FILE = SCRATCH

# Likewise keep test runs out of the real learning log, which is read for
# diagnosis; test traffic in there is noise that looks like real sessions.
LN.LOG = ROOT / "snapshots" / "test-learn-log.txt"


class Silent(Speaker):
    """Stands in for speech so the test says nothing out loud."""

    def __init__(self) -> None:
        self.said: list[str] = []

    def say(self, text, interrupt=True):
        self.said.append(text)

    def stop(self):
        pass


def hold(codes, shown, ticks):
    """Hold one selection still for `ticks` reads.

    Must exceed the learner's confirmation threshold, which is deliberately
    high enough to outlast the gap where the name and the model disagree.
    """
    assert ticks > LN.CONFIRMATIONS, "hold shorter than the confirmation threshold"
    return [(dict(codes), dict(shown))] * ticks


def run(label, script, expect_link, expect_names) -> bool:
    # Each scenario starts from an empty scratch table, or later runs inherit
    # names learned by earlier ones.
    assert live.NAME_MAP_FILE == SCRATCH, "refusing to run against the real table"
    SCRATCH.parent.mkdir(exist_ok=True)
    if SCRATCH.exists():
        SCRATCH.unlink()
    learner = LN.Learner(Silent())
    for codes, shown in script:
        learner.observe(codes, shown)
        learner.consider(codes, shown)
        time.sleep(0.02)

    link_ok = expect_link is None or learner.link == expect_link
    names_ok = learner.names == expect_names
    print(f"{'PASS' if link_ok and names_ok else 'FAIL'}  {label}")
    print(f"        link {learner.link}, player one on the {learner.player_one_side} side")
    print(f"        learned {learner.names}")
    if not names_ok:
        print(f"        expected {expect_names}")
    learner.close()
    return link_ok and names_ok


def main() -> None:
    results = []

    script = []
    script += hold({"neg": "KEN", "pos": "GUL"}, {"left": "GUILE", "right": "KEN"}, 6)
    script += hold({"neg": "KEN", "pos": "CMY"}, {"left": "CAMMY", "right": "KEN"}, 6)
    script += hold({"neg": "KEN", "pos": "Z25"}, {"left": "ZEKU", "right": "KEN"}, 6)
    script += hold({"neg": "KEN", "pos": "RSD"}, {"left": "RASHID", "right": "KEN"}, 6)
    results.append(
        run(
            "player two parked on Ken while player one moves along the roster",
            script,
            {"pos": "left", "neg": "right"},
            {"GUL": "GUILE", "KEN": "KEN", "CMY": "CAMMY", "Z25": "ZEKU", "RSD": "RASHID"},
        )
    )

    script = []
    script += hold({"pos": "KEN", "neg": "GUL"}, {"right": "GUILE", "left": "KEN"}, 6)
    script += hold({"pos": "KEN", "neg": "CMY"}, {"right": "CAMMY", "left": "KEN"}, 6)
    script += hold({"pos": "KEN", "neg": "Z25"}, {"right": "ZEKU", "left": "KEN"}, 6)
    results.append(
        run(
            "the same thing mirrored, to prove no side is assumed",
            script,
            {"neg": "right", "pos": "left"},
            {"GUL": "GUILE", "KEN": "KEN", "CMY": "CAMMY", "Z25": "ZEKU"},
        )
    )

    script = []
    script += hold({"neg": "KEN", "pos": "GUL"}, {"left": "GUILE", "right": "KEN"}, 6)
    script += hold({"neg": "KEN", "pos": "ALX"}, {"left": "KEN", "right": "KEN"}, 6)
    results.append(
        run(
            "a name that already belongs to another character is refused",
            script,
            None,
            {"GUL": "GUILE", "KEN": "KEN"},
        )
    )

    # A recorded entry must not be quietly replaced. Four characters were
    # overwritten between sessions and their old names vanished silently.
    script = []
    # A move first, so the sides link; then the name alone changes under a
    # code that is already recorded, which is the conflict being tested.
    script += hold({"neg": "KEN", "pos": "GUL"}, {"left": "GUILE", "right": "KEN"}, 6)
    script += hold({"neg": "KEN", "pos": "Z41"}, {"left": "ROSE", "right": "KEN"}, 6)
    script += hold({"neg": "KEN", "pos": "Z41"}, {"left": "AKUMA", "right": "KEN"}, 6)
    results.append(
        run(
            "an existing entry is kept, and the disagreement reported",
            script,
            None,
            {"GUL": "GUILE", "Z41": "ROSE", "KEN": "KEN"},
        )
    )

    # "ROS" arrived while ROSE was on screen; a name that is the start of one
    # already recorded is a partial read, not a new character.
    script = []
    script += hold({"neg": "KEN", "pos": "Z41"}, {"left": "ROSE", "right": "KEN"}, 6)
    script += hold({"neg": "KEN", "pos": "Z39"}, {"left": "ROS", "right": "KEN"}, 6)
    script += hold({"neg": "KEN", "pos": "Z33"}, {"left": "PO SO", "right": "KEN"}, 6)
    # Fragments from the middle or end of a name, as seen in the real log:
    # KEN read as EN, GILL as ILL, AKUMA as KUMA.
    script += hold({"neg": "KEN", "pos": "Z36"}, {"left": "OSE", "right": "KEN"}, 6)
    results.append(
        run(
            "partly recognised names are refused",
            script,
            None,
            {"Z41": "ROSE", "KEN": "KEN"},
        )
    )

    if SCRATCH.exists():
        SCRATCH.unlink()

    print()
    print("ALL SCENARIOS PASSED" if all(results) else "SOME SCENARIOS FAILED")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
