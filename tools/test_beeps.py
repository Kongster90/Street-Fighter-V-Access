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

import tempfile  # noqa: E402

from sfv_access import beeps, buttons, scaleform as sf  # noqa: E402

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


# F5 and Shift F5: the volume in percent, heard rather than measured, so the
# tone's peak is the square of the share; 0 is silence.
loud, _r, _s = channels(beeps.sound(0.75, 0, 100))
half, _r, _s = channels(beeps.sound(0.75, 0, 50))
quiet, _r, _s = channels(beeps.sound(0.75, 0, 0))
check("a volume of 50 percent is a quarter of full strength, and 0 is silent",
      abs(max(half) / max(loud) - 0.25) < 0.01 and not any(quiet), f"{max(half)} of {max(loud)}")
left, right, _ = channels(beeps.sound(0.75, None, 50))
check("the beep that answers F5 is in both speakers", any(left) and left == right)
saved = buttons.SETTINGS, buttons._settings
with tempfile.TemporaryDirectory() as folder:
    buttons.SETTINGS, buttons._settings = Path(folder) / "settings.json", None
    start = buttons.beep_volume()
    steps = [buttons.change_beep_volume(-beeps.VOLUME_STEP) for _ in range(10)]
    buttons._settings = None                       # as the next run would, from the file
    kept = buttons.beep_volume()
    top = [buttons.change_beep_volume(beeps.VOLUME_STEP) for _ in range(22)][-1]
buttons.SETTINGS, buttons._settings = saved
check("the volume starts at 40, goes down 5 at a time to 0 and no further, and is remembered",
      start == 40 and steps == [35, 30, 25, 20, 15, 10, 5, 0, 0, 0] and kept == 0 and top == 100,
      repr((start, steps, kept, top)))

# The counter hit: player 1's counter in the left speaker, quick, at its own volume.
left, right, counter_seconds = channels(beeps.counter_sound(0))
check("player 1's counter hit is in the left speaker only", any(left) and not any(right))
left, right, _ = channels(beeps.counter_sound(1))
check("player 2's in the right", any(right) and not any(left))
voice = beeps.recorded(beeps.COUNTER_FILE)
check("the user's recording, 24-bit stereo, reads as one channel at its full height",
      voice is not None and voice[1] == 44100 and max(abs(s) for s in voice[0]) == 1.0
      and abs(len(voice[0]) / voice[1] - 0.202) < 0.002, repr(voice[1:] if voice else voice))
left, _r, _s = channels(beeps.counter_sound(0))
onset = next(i for i, s in enumerate(left) if abs(s) > 0.01 * max(map(abs, left))) / 44100
check("and is what plays, sounding within its first 3 ms",
      abs(counter_seconds - 0.202) < 0.002 and onset < 0.003,
      f"{counter_seconds * 1000:.0f} ms, sounding from {onset * 1000:.1f} ms")
silent, _r, _s = channels(beeps.counter_sound(0, 0))
check("at 0 it is silent", not any(silent))
check("once made it is kept, not made again", beeps.counter_sound(0, 40) is beeps.counter_sound(0, 40))
kept_file = beeps.COUNTER_FILE
beeps.COUNTER_FILE = Path(tempfile.gettempdir()) / "no-such-counter-hit.wav"
beeps.counter_sound.cache_clear()
left, right, click_seconds = channels(beeps.counter_sound(0))
beeps.COUNTER_FILE = kept_file
beeps.counter_sound.cache_clear()
check("without the recording, a click and a short tone, still in the left speaker",
      click_seconds < 0.06 and any(left) and not any(right), f"{click_seconds * 1000:.0f} ms")

# A crossup: its own sound in the speaker of whoever landed it, at its own volume (F7).
left, right, crossup_seconds = channels(beeps.crossup_sound(0))
check("the user's crossup recording is what plays, in the speaker of whoever landed it",
      abs(crossup_seconds - 0.336) < 0.002 and any(left) and not any(right), f"{crossup_seconds * 1000:.0f} ms")
with tempfile.TemporaryDirectory() as folder:
    buttons.SETTINGS, buttons._settings = Path(folder) / "settings.json", None
    counter_before = buttons.counter_volume()
    crossup_start = buttons.crossup_volume()
    crossup_after = buttons.change_crossup_volume(beeps.VOLUME_STEP)
    buttons._settings = None
    kept = buttons.crossup_volume(), buttons.counter_volume()
buttons.SETTINGS, buttons._settings = saved
check("its volume starts at 40, moves 5 at a time, is remembered, and leaves the counter hit's alone",
      crossup_start == 40 and crossup_after == 45 and kept == (45, counter_before),
      repr((crossup_start, crossup_after, kept)))
kept_crossup = beeps.CROSSUP_FILE
beeps.CROSSUP_FILE = Path(tempfile.gettempdir()) / "no-such-crossup.wav"
beeps.crossup_sound.cache_clear()
left, right, crossup_seconds = channels(beeps.crossup_sound(1))
check("without a recording, a crossup by player 2 is two quick tones in the right speaker only",
      any(right) and not any(left) and crossup_seconds < 0.1, f"{crossup_seconds * 1000:.0f} ms")
check("and it is not the counter hit's sound", beeps.crossup_sound(1) != beeps.counter_sound(1))
beeps.CROSSUP_FILE = beeps.COUNTER_FILE    # any readable recording stands in for the user's own
beeps.crossup_sound.cache_clear()
left, right, recorded_seconds = channels(beeps.crossup_sound(0))
check("a recording, when there is one, is what plays", abs(recorded_seconds - 0.202) < 0.002 and any(left)
      and not any(right), f"{recorded_seconds * 1000:.0f} ms")
beeps.CROSSUP_FILE = kept_crossup
beeps.crossup_sound.cache_clear()
with tempfile.TemporaryDirectory() as folder:
    buttons.SETTINGS, buttons._settings = Path(folder) / "settings.json", None
    beep_before = buttons.beep_volume()
    counter_start = buttons.counter_volume()
    counter_after = buttons.change_counter_volume(-beeps.VOLUME_STEP)
    buttons._settings = None
    kept = buttons.counter_volume(), buttons.beep_volume()
buttons.SETTINGS, buttons._settings = saved
check("its volume starts at 40, moves 5 at a time, is remembered, and leaves the beeps' alone",
      counter_start == 40 and counter_after == 35 and kept == (35, beep_before), repr((counter_start, counter_after, kept)))


def label(text, x, y=90.0):
    return sf.TextItem(text, x, y, (1.0, 1.0, 1.0, 1.0), 4)


check("a fight's display is known by the labels over both health bars",
      sf.fight_on_screen([label("CPU", 167), label("PLAYER 1", 1834)])
      and sf.fight_on_screen([label("PLAYER 1", 167), label("PLAYER 2", 1834)]))
check("one label, or labels elsewhere, is not a fight",
      not sf.fight_on_screen([label("PLAYER 1", 167)])
      and not sf.fight_on_screen([label("CPU", 729, 371), label("PLAYER 1", 1121, 477)])
      and not sf.fight_on_screen([]))
# Online only the player's own bar is labelled (2026-09-29, Battle Lounge).
check("online, YOU over either bar alone is a fight",
      sf.fight_on_screen([label("YOU", 167), label("Rank 30462", 174, 122)])
      and sf.fight_on_screen([label("YOU", 1834)]))
check("the Battle Lounge's status on that row, or YOU over a fighter, is not a fight",
      not sf.fight_on_screen([label("MENU", 190)])
      and not sf.fight_on_screen([label("STANDBY", 190)])
      and not sf.fight_on_screen([label("YOU", 394, 557), label("P1\n", 394, 557)])
      and not sf.fight_on_screen([label("YOU", 631, 77)]))
check("the fighters named over the health bars, a fighter's name only",
      sf.fight_names([sf.TextItem("NASH", 1233, 122, (1, 1, 1, 1), 4, part="player_name_right"),
                      sf.TextItem("Rank 6398", 174, 122, (1, 1, 1, 1), 4, part="player_name_left")])
      == (None, "NASH"))
check("a replay counts as a fight for the sounds, by its version line",
      sf.fight_running([label("Rank 6398", 174, 122), label("Ver. 07.010", 960, 174)])
      and not sf.fight_on_screen([label("Rank 6398", 174, 122), label("Ver. 07.010", 960, 174)])
      and not sf.fight_running([label("Rank 6398", 174, 122)]))

print()
print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
