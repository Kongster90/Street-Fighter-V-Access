"""Report the character name table and how far it can be trusted.

Needs no game running. Codes made of letters are usually initials of the
displayed name, so those check themselves. Season characters use codes like
Z31 which cannot be checked that way, and are listed separately rather than
being presented as equally certain.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access.live import code_matches_name, load_name_file  # noqa: E402


def main() -> None:
    data = load_name_file()
    names = data["names"]
    side = data["player_one_side"]

    if not names:
        print("No characters recorded yet. Run tools/learn_names.py.")
        return

    print(f"player one stands on the {side} side")
    print(f"{len(names)} characters recorded\n")

    confirmed = sorted((c, n) for c, n in names.items() if c.isalpha() and code_matches_name(c, n))
    contradictory = sorted(
        (c, n) for c, n in names.items() if c.isalpha() and not code_matches_name(c, n)
    )
    unchecked = sorted((c, n) for c, n in names.items() if not c.isalpha())

    print(f"self-confirming, the code reads as initials of the name ({len(confirmed)}):")
    for code, name in confirmed:
        print(f"   {code:5s} {name}")

    if contradictory:
        print(f"\ncontradictory, worth re-learning ({len(contradictory)}):")
        for code, name in contradictory:
            print(f"   {code:5s} {name}")

    print(f"\nnot checkable this way, season codes ({len(unchecked)}):")
    for code, name in unchecked:
        print(f"   {code:5s} {name}")

    seen: dict[str, list[str]] = {}
    for code, name in names.items():
        seen.setdefault(name, []).append(code)
    clashes = {n: c for n, c in seen.items() if len(c) > 1}
    print(f"\nnames claimed by more than one character: {clashes or 'none'}")


if __name__ == "__main__":
    main()
