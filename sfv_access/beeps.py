"""Beeps as a fighter's health drops past set levels, player 1 on the left and player 2 on the right.

Asked for by the user on 2026-09-28, in their words: "A higher beep at 75%,
another highish beep at 50%, a lower beep at 25%, then maybe 2 short low
beeps at 10%", each side in its own speaker, once per crossing. A level
sounds as health drops below it and not again until health has gone back
above it, as it does at the start of the next round. A combo that drops
past several levels at once sounds only the lowest, the news that matters.

The tones are made here, as sound data, and played by Windows beside the
game's own sound and the screen reader's speech. They were plain sine tones
until 2026-09-30, when the user picked a xylophone from eleven styles: each
note its pitch with a softer partial three times higher that dies away
first, and a fast fall. They then asked for it three semitones lower than
the first beeps, so the levels are A, E, A and E where they were C, G, C, G.

A counter hit has a sound of its own, in the speaker on the side of whoever
landed it, at a volume of its own (F6 and Shift F6). The user chose a click
and a short high tone from five on 2026-09-30, for being quick: "anything
longer and I may not be able to react in time to follow up on the counter
hit". The same evening they made their own in Reaper, `sounds/counter_hit.wav`
(0.2 s, sounding from its second millisecond), and that is played, its two
channels made one; the click is kept for when the file cannot be read. A
crush counter sounds nothing; the game's own sound for one says it.
"""

from __future__ import annotations

import functools
import io
import math
import queue
import random
import struct
import threading
import wave
from pathlib import Path

RATE = 44100
COUNTER_FILE = Path(__file__).resolve().parent / "sounds" / "counter_hit.wav"
# The beeps' volume in percent, F5 and Shift F5 in steps of `VOLUME_STEP`,
# kept in the settings. It is heard, not measured: the level is the square
# of the share, so each step sounds much the same size. The first beeps,
# which the user found "a bit loud", were 59 percent on this scale, and 50
# still was; they asked for 40 to start and steps of 5 "for more control".
VOLUME_DEFAULT = 40
VOLUME_STEP = 5
FADE = 0.005          # seconds of fade at each end of a tone, so it does not click
GAP = 0.06            # seconds between the tones of one warning

# Each level: the share of health, and its notes as (pitch in hertz, seconds).
LEVELS = (
    (0.75, ((880, 0.18),)),
    (0.50, ((659, 0.18),)),
    (0.25, ((440, 0.18),)),
    (0.10, ((330, 0.1), (330, 0.1))),
)
# A xylophone note: how fast it rises, how fast it falls (the time to fall to
# about a third), and the same for its partial three times higher, which is
# this much of its loudness; then a short fade at the end.
NOTE_RISE, NOTE_FALL = 0.001, 0.05
PARTIAL, PARTIAL_SHARE = 3, 0.4
PARTIAL_RISE, PARTIAL_FALL = 0.0005, 0.02
NOTE_RELEASE = 0.01
REARM = 0.02          # back above a level by this much before it can sound again
# The counter hit's sound: a click of noise, then a short high tone.
COUNTER_CLICK = 0.006       # seconds of click, fading out
COUNTER_CLICK_SHARE = 0.6   # its loudest, as a share of the tone's
COUNTER_PITCH, COUNTER_TONE = 2637, 0.05
COUNTER_VOLUME_DEFAULT = 40


def loudness(volume: int) -> float:
    """The peak of a tone, 0 to 1, for a volume in percent."""
    return (max(0, min(100, volume)) / 100) ** 2


def _frame(sample: int, side: int | None) -> bytes:
    return struct.pack("<hh", sample if side != 1 else 0, sample if side != 0 else 0)


def _tone(pitch: float, seconds: float, peak: float, side: int | None) -> bytearray:
    frames = bytearray()
    count = int(seconds * RATE)
    fade = max(1, int(FADE * RATE))
    for i in range(count):
        envelope = min(1.0, i / fade, (count - 1 - i) / fade)
        frames += _frame(int(32767 * peak * envelope * math.sin(2 * math.pi * pitch * i / RATE)), side)
    return frames


def _xylophone(pitch: float, seconds: float) -> list[float]:
    """One note, as samples of no particular scale."""
    count = int(seconds * RATE)
    release = int(NOTE_RELEASE * RATE)
    out = []
    for i in range(count):
        t = i / RATE
        body = min(1.0, t / NOTE_RISE) * math.exp(-t / NOTE_FALL) * math.sin(2 * math.pi * pitch * t)
        bright = (PARTIAL_SHARE * min(1.0, t / PARTIAL_RISE) * math.exp(-t / PARTIAL_FALL)
                  * math.sin(2 * math.pi * PARTIAL * pitch * t))
        tail = min(1.0, (count - i) / release)
        out.append((body + bright) * tail)
    return out


@functools.lru_cache(maxsize=32)
def sound(level: float, side: int | None, volume: int = VOLUME_DEFAULT) -> bytes:
    """A level's warning as WAV data: the left speaker for side 0, the right for 1, both for None.

    Kept once made, so a warning costs no time making it.
    """
    samples: list[float] = []
    for n, (pitch, seconds) in enumerate(dict(LEVELS)[level]):
        if n:
            samples += [0.0] * int(GAP * RATE)
        samples += _xylophone(pitch, seconds)
    scale = 32767 * loudness(volume) / (max(abs(s) for s in samples) or 1.0)
    frames = bytearray()
    for s in samples:
        frames += _frame(int(scale * s), side)
    return _wav(frames)


def recorded(path: Path) -> tuple[list[float], int] | None:
    """A PCM WAV file's samples, its channels made one and its loudest at 1, and
    its rate; None if it cannot be read."""
    try:
        with wave.open(str(path)) as w:
            channels, width, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
            raw = w.readframes(w.getnframes())
    except (OSError, EOFError, wave.Error):
        return None
    if not channels or width not in (1, 2, 3, 4):
        return None
    if width == 1:
        values = [b - 128 for b in raw]
    else:
        values = [int.from_bytes(raw[i:i + width], "little", signed=True)
                  for i in range(0, len(raw) - width + 1, width)]
    samples = [sum(values[i:i + channels]) / channels for i in range(0, len(values) - channels + 1, channels)]
    peak = max((abs(s) for s in samples), default=0)
    return ([s / peak for s in samples], rate) if peak else None


@functools.lru_cache(maxsize=16)
def counter_sound(side: int | None, volume: int = COUNTER_VOLUME_DEFAULT) -> bytes:
    """The counter hit's sound as WAV data, in the speaker of `side`, the one who landed it:
    the user's recording if it can be read, otherwise a click and a short high tone.

    Kept once made, so a counter hit costs no time making it.
    """
    peak = loudness(volume)
    voice = recorded(COUNTER_FILE)
    if voice is not None:
        samples, rate = voice
        frames = bytearray()
        for s in samples:
            frames += _frame(int(32767 * peak * s), side)
        return _wav(frames, rate)
    noise = random.Random(3)
    count = int(COUNTER_CLICK * RATE)
    click = [noise.gauss(0, 1) * (1 - i / count) for i in range(count)]
    scale = COUNTER_CLICK_SHARE / max(abs(c) for c in click)
    frames = bytearray()
    for c in click:
        frames += _frame(int(32767 * peak * scale * c), side)
    frames += _tone(COUNTER_PITCH, COUNTER_TONE, peak, side)
    return _wav(frames)


def _wav(frames: bytes, rate: int = RATE) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return out.getvalue()


class Levels:
    """Which levels one fighter's health is below, and which to sound as it moves."""

    def __init__(self) -> None:
        # None until the first reading of a fight, which only notes where
        # health stands: joining a fight halfway is not a drop.
        self.below: set[float] | None = None

    def reset(self) -> None:
        self.below = None

    def update(self, share: float) -> float | None:
        """The level to sound for this reading, or None."""
        levels = [level for level, _tones in LEVELS]
        if self.below is None:
            self.below = {level for level in levels if share < level}
            return None
        self.below -= {level for level in self.below if share >= level + REARM}
        crossed = [level for level in levels if share < level and level not in self.below]
        self.below |= set(crossed)
        return min(crossed) if crossed else None


class Player:
    """Plays warnings one after another on a thread of its own, so nothing waits on them."""

    def __init__(self) -> None:
        self._queue: queue.Queue[bytes] = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def play(self, data: bytes) -> None:
        self._queue.put(data)

    def _run(self) -> None:
        import winsound

        while True:
            data = self._queue.get()
            try:
                winsound.PlaySound(data, winsound.SND_MEMORY | winsound.SND_NODEFAULT)
            except Exception:
                pass
