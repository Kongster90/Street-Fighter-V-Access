"""Beeps as a fighter's health drops past set levels, player 1 on the left and player 2 on the right.

Asked for by the user on 2026-09-28, in their words: "A higher beep at 75%,
another highish beep at 50%, a lower beep at 25%, then maybe 2 short low
beeps at 10%", each side in its own speaker, once per crossing. A level
sounds as health drops below it and not again until health has gone back
above it, as it does at the start of the next round. A combo that drops
past several levels at once sounds only the lowest, the news that matters.

The tones are made here, as sound data, and played by Windows beside the
game's own sound and the screen reader's speech.
"""

from __future__ import annotations

import io
import math
import queue
import struct
import threading
import wave

RATE = 44100
# The beeps' volume in percent, F5 and Shift F5 in steps of `VOLUME_STEP`,
# kept in the settings. It is heard, not measured: the level is the square
# of the share, so each step sounds much the same size. The first beeps,
# which the user found "a bit loud", were 59 percent on this scale, and 50
# still was; they asked for 40 to start and steps of 5 "for more control".
VOLUME_DEFAULT = 40
VOLUME_STEP = 5
FADE = 0.005          # seconds of fade at each end of a tone, so it does not click
GAP = 0.06            # seconds between the tones of one warning

# Each level: the share of health, and its tones as (pitch in hertz, seconds).
LEVELS = (
    (0.75, ((1047, 0.11),)),
    (0.50, ((784, 0.11),)),
    (0.25, ((523, 0.13),)),
    (0.10, ((392, 0.07), (392, 0.07))),
)
REARM = 0.02          # back above a level by this much before it can sound again


def loudness(volume: int) -> float:
    """The peak of a tone, 0 to 1, for a volume in percent."""
    return (max(0, min(100, volume)) / 100) ** 2


def sound(level: float, side: int | None, volume: int = VOLUME_DEFAULT) -> bytes:
    """A level's warning as WAV data: the left speaker for side 0, the right for 1, both for None."""
    tones = dict(LEVELS)[level]
    peak = loudness(volume)
    frames = bytearray()
    for n, (pitch, seconds) in enumerate(tones):
        if n:
            frames += b"\x00\x00\x00\x00" * int(GAP * RATE)
        count = int(seconds * RATE)
        fade = max(1, int(FADE * RATE))
        for i in range(count):
            envelope = min(1.0, i / fade, (count - 1 - i) / fade)
            sample = int(32767 * peak * envelope * math.sin(2 * math.pi * pitch * i / RATE))
            frames += struct.pack("<hh", sample if side != 1 else 0, sample if side != 0 else 0)
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
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
