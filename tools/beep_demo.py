"""Play the health warning beeps, to hear them without a fight.

Each level in turn, 75, 50, 25 and 10 percent, first for player 1 in the
left speaker and then for player 2 in the right, at the volume F5 and
Shift F5 last set. Needs no game.

    .venv\\Scripts\\python.exe tools\\beep_demo.py
"""

from __future__ import annotations

import sys
import time
import winsound
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access import beeps, buttons  # noqa: E402

for side in (0, 1):
    for level, _tones in beeps.LEVELS:
        winsound.PlaySound(beeps.sound(level, side, buttons.beep_volume()),
                           winsound.SND_MEMORY | winsound.SND_NODEFAULT)
        time.sleep(0.5)
    time.sleep(1.0)
