"""Check the health warning beeps: when each level sounds, and that each side has its own speaker.

The levels are the user's (2026-09-28): 75, 50 and 25 percent, then two short
low beeps at 10, player 1 in the left speaker and player 2 in the right, once
per crossing. Needs no game, and plays nothing.
"""

from __future__ import annotations

import io
import struct
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access import beeps, scaleform as sf  # noqa: E402

ok = True


def check(label, condition, detail=""):
    global ok
    if condition:
        print(f"PASS  {label}{(': ' + detail) if detail else ''}")
    else:
        ok = False
        print(f"FAIL  {label}{(': ' + detail) if detail else ''}")


def run(shares):
    levels = beeps.Levels()
    return [levels.update(s) for s in shares]


heard = run([1.0, 0.8, 0.74, 0.70, 0.49, 0.30, 0.24, 0.12, 0.09, 0.0])
check("a fight going down sounds each level once, as it is passed",
      heard == [None, None, 0.75, None, 0.5, None, 0.25, None, 0.1, None], repr(heard))
heard = run([1.0, 0.8, 0.3])
check("a combo past several levels sounds only the lowest", heard == [None, None, 0.5], repr(heard))
heard = run([0.4, 0.3, 0.2])
check("joining a fight halfway sounds nothing for levels already passed",
      heard == [None, None, 0.25], repr(heard))
heard = run([1.0, 0.749, 0.751, 0.748, 1.0, 0.7])
check("hovering at a level sounds it once; a new round's full health sounds it again",
      heard == [None, 0.75, None, None, None, 0.75], repr(heard))
levels = beeps.Levels()
levels.update(1.0)
levels.update(0.6)
levels.reset()
check("after the fight, the next one starts afresh", levels.update(0.6) is None and levels.update(0.45) == 0.5)


def channels(data):
    with wave.open(io.BytesIO(data)) as w:
        frames = w.readframes(w.getnframes())
        assert w.getnchannels() == 2 and w.getsampwidth() == 2
        seconds = w.getnframes() / w.getframerate()
    samples = struct.unpack(f"<{len(frames) // 2}h", frames)
    return samples[0::2], samples[1::2], seconds


left, right, _ = channels(beeps.sound(0.75, 0))
check("player 1's beep is in the left speaker only", any(left) and not any(right))
left, right, _ = channels(beeps.sound(0.25, 1))
check("player 2's beep is in the right speaker only", any(right) and not any(left))
_l, _r, one = channels(beeps.sound(0.5, 0))
_l, _r, two = channels(beeps.sound(0.1, 0))
check("10 percent is two short beeps with a gap, the others one",
      len(dict(beeps.LEVELS)[0.1]) == 2 and two > one, f"{one:.2f} s and {two:.2f} s")
pitches = [dict(beeps.LEVELS)[level][0][0] for level in (0.75, 0.5, 0.25, 0.1)]
check("the lower the health, the lower the pitch", pitches == sorted(pitches, reverse=True), repr(pitches))


def label(text, x, y=90.0):
    return sf.TextItem(text, x, y, (1.0, 1.0, 1.0, 1.0), 4)


check("a fight's display is known by the labels over both health bars",
      sf.fight_on_screen([label("CPU", 167), label("PLAYER 1", 1834)])
      and sf.fight_on_screen([label("PLAYER 1", 167), label("PLAYER 2", 1834)]))
check("one label, or labels elsewhere, is not a fight",
      not sf.fight_on_screen([label("PLAYER 1", 167)])
      and not sf.fight_on_screen([label("CPU", 729, 371), label("PLAYER 1", 1121, 477)])
      and not sf.fight_on_screen([]))

print()
print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
