"""Check text correction against mistakes seen in real captures.

The left column is what the recogniser actually produced on this machine; the
right is what the game really says. Needs no game running.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access import strings  # noqa: E402

# Misreadings taken from the snapshot dumps, paired with the truth.
CASES = [
    ("BAÜLE LOUNGE", "BATTLE LOUNGE"),
    ("RANKED MAT H", "RANKED MATCH"),
    ("CASUAL MATC", "CASUAL MATCH"),
    ("BATTLE SETTINGS", "BATTLE SETTINGS"),
    ("CHALLENGES", "CHALLENGES"),
    ("TRAINING", "TRAINING"),
    ("Sound Settings", "Sound Settings"),
    ("Graphics Settings", "Graphics Settings"),
    ("Demonstrations", "Demonstrations"),
    ("Extra Battle", "Extra Battle"),
    ("PLAYER I VS PLAYER 2", "PLAYER 1 VS PLAYER 2"),
    ("Restart Battle", "Restart Battle"),
    ("Version Select", "Version Select"),
    ("Character / Stage Select", "Character / Stage Select"),
    ("Frame Advantage in Color", "Frame Advantage in Color"),
    ("HARA ER SELECT", "CHARACTER SELECT"),
    ("STAGE SELECT", "STAGE SELECT"),
]

# Things that must not be rewritten: they are not game strings at all.
#
# "Temperature 800 F" is the exception that proves the number rule. It matches
# the bare word "Temperature" closely enough to win, and correcting to it would
# throw the reading's value away. A correction may restore a number the reading
# missed, as the PLAYER 1 case above does, but it may never discard one.
LEAVE_ALONE = [
    "Dengster",
    "Rank 153684",
    "6178 LP",
    "319290",
    "sep 8, 2026",
    "10:43 PM",
    "Temperature 800 F",
]


def main() -> None:
    t0 = time.perf_counter()
    vocab = strings.shared()
    if vocab is None:
        print("strings.json missing. Run tools/extract_strings.py first.")
        sys.exit(1)
    print(f"{len(vocab.entries):,} distinct lines indexed in {time.perf_counter() - t0:.1f} s\n")

    good = bad = 0
    for read, truth in CASES:
        t = time.perf_counter()
        match = vocab.correct(read)
        ms = (time.perf_counter() - t) * 1000
        ok = match.text.upper() == truth.upper()
        good, bad = (good + 1, bad) if ok else (good, bad + 1)
        flag = "ok  " if ok else "MISS"
        note = "" if match.text == read else f"  (was {read!r})"
        print(f"  {flag} {match.text!r:34s} score {match.score:.2f} {ms:5.1f} ms{note}")
        if not ok:
            print(f"        expected {truth!r}")

    print(f"\n{good} corrected or kept correctly, {bad} wrong\n")

    print("must be left alone:")
    kept = 0
    for text in LEAVE_ALONE:
        match = vocab.correct(text)
        safe = match.text == text
        kept += safe
        print(f"  {'ok  ' if safe else 'CHANGED'} {text!r} -> {match.text!r} ({match.score:.2f})")

    print(f"\n{kept}/{len(LEAVE_ALONE)} left alone")
    sys.exit(0 if bad == 0 and kept == len(LEAVE_ALONE) else 1)


if __name__ == "__main__":
    main()
