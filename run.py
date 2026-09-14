"""Entry point. Run with: .venv\\Scripts\\python.exe run.py"""

import sys

# Menu text can contain characters the legacy console codepage cannot encode,
# and an exception from print() would take the tool down with it. Started with
# the game, output goes to snapshots/console-log.txt instead of a console, and
# is written line by line so the log holds everything up to a crash.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass

from sfv_access.app import main

if __name__ == "__main__":
    main()
