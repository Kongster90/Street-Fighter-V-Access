"""Read what UE4SS said when the game started.

UE4SS writes its log beside the DLL that loaded it, which for the XInput build
is the folder holding the game executable. On a game two engine versions older
than anything UE4SS targets, this log is the whole diagnosis: whether it loaded
at all, whether its byte patterns found the engine's object array and name
functions, and what it thinks the engine version is.

Usage:
    python tools/ue4ss_log.py            the interesting lines
    python tools/ue4ss_log.py --all      everything
"""

from __future__ import annotations

import sys
from pathlib import Path

WIN64 = Path(
    r"G:\Steam\steamapps\common\StreetFighterV\StreetFighterV\Binaries\Win64"
)

# What matters on an unsupported engine version: the version it settled on, the
# addresses its scanning found or failed to find, and anything that went wrong.
KEYWORDS = (
    "error", "fail", "unsupported", "not found", "exception", "crash",
    "version", "guobjectarray", "gmalloc", "fname", "aob", "scan",
    "offset", "layout", "override", "loaded", "starting", "done",
)


def main() -> None:
    logs = sorted(WIN64.glob("*.log"), key=lambda p: -p.stat().st_mtime)
    if not logs:
        print(f"no log in {WIN64}")
        print("UE4SS either did not load, or did not get far enough to write one.")
        print("Turn ConsoleEnabled back on in UE4SS-settings.ini to see it try.")
        raise SystemExit(1)

    path = logs[0]
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    print(f"{path.name}, {len(lines)} lines, {path.stat().st_size:,} bytes\n")

    if "--all" in sys.argv:
        print(text)
        return

    shown = 0
    for line in lines:
        if any(k in line.lower() for k in KEYWORDS):
            print(f"  {line}")
            shown += 1
    print(f"\n{shown} of {len(lines)} lines matched. Pass --all for the rest.")


if __name__ == "__main__":
    main()
