"""Save snapshots while you move through the menus.

Alt S saves one screen at a time, which is the right tool when you know
which screen is wrong. It is the wrong tool for a calibration pass, where the
point is to cover a lot of screens and the interesting frame is often one you
could not have known to ask for.

Two modes. By default it saves one frame every time the selection moves, which
is what you want for walking through menus: one frame per thing you land on, no
duplicates of a screen you sat on, and nothing to time. Pass an interval to get
the older behaviour of a frame every so many seconds instead, which is what to
use when a single screen misbehaves on its own.

Each frame is written the same way Alt S writes it, a PNG beside a text
dump of every recognised line, so `replay.py`, `show_bands.py` and
`test_screens.py` all read them unchanged.

Usage:
    python tools/grab_screens.py [count] [lead-in seconds]
    python tools/grab_screens.py [count] [lead-in seconds] --every 2
"""

from __future__ import annotations

import datetime as _dt
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from sfv_access import capture as _capture  # noqa: E402
from sfv_access import game, ocr  # noqa: E402
from sfv_access.app import WATCH_INTERVAL, change_key  # noqa: E402
from sfv_access.speech import Speaker  # noqa: E402

SNAPSHOT_DIR = ROOT / "snapshots"
# However long the pass runs, stop eventually rather than sit there forever.
TIME_LIMIT = 15 * 60


def save(bgra, stamp: str) -> int:
    """Write one frame the way the snapshot hotkey does. Returns line count."""
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    Image.fromarray(bgra[:, :, [2, 1, 0]]).save(SNAPSHOT_DIR / f"sfv-{stamp}.png")
    items = ocr.reading_order(ocr.read(bgra))
    with (SNAPSHOT_DIR / f"sfv-{stamp}.txt").open("w", encoding="utf-8") as fh:
        fh.write(f"frame {bgra.shape[1]}x{bgra.shape[0]}\n")
        for it in items:
            fh.write(f"{it.x:7.0f} {it.y:7.0f} {it.w:6.0f} {it.h:5.0f}  {it.text}\n")
    return len(items)


def count_in(speech: Speaker, lead_in: float) -> None:
    """Spoken countdown, since the console is behind a fullscreen game."""
    if lead_in > 4:
        time.sleep(lead_in - 3.0)
        for n in (3, 2, 1):
            speech.say(str(n))
            time.sleep(1.0)
    else:
        time.sleep(lead_in)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    every = None
    if "--every" in sys.argv:
        at = sys.argv.index("--every")
        every = float(sys.argv[at + 1])
        args = [a for a in args if a != sys.argv[at + 1]]

    count = int(args[0]) if args else 20
    lead_in = float(args[1]) if len(args) > 1 else 20.0

    speech = Speaker()
    cap = _capture.Capture()
    how = (
        f"one every {every:.0f} seconds"
        if every
        else "one each time you move to something new"
    )
    speech.say(
        f"Saving up to {count} screens, {how}. Starting in {int(lead_in)} seconds. "
        "Switch to the game now. It counts each one and says when it is done."
    )
    count_in(speech, lead_in)

    saved = 0
    last = None
    started = time.time()
    settling = 0

    while saved < count and time.time() - started < TIME_LIMIT:
        time.sleep(every if every else WATCH_INTERVAL)
        win = game.find_window()
        if win is None or not win.is_foreground:
            continue
        bgra = cap.frame(max_age=0.0)
        if bgra is None:
            continue

        if every is None:
            key = change_key(_capture.to_rgb(bgra))
            if key == last:
                settling = 0
                continue
            # One more tick before saving, so the frame is of the screen as it
            # settled rather than mid animation.
            if settling == 0:
                settling = 1
                last = key
                continue
            settling = 0
            last = key

        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        lines = save(bgra, stamp)
        saved += 1
        print(f"[{saved}] sfv-{stamp}  {lines} lines")
        # A bare number rather than a sentence, so it does not run into the next.
        speech.say(str(saved))

    cap.close()
    note = f"Saved {saved}."
    print(note)
    speech.say(note)
    time.sleep(2.5)


if __name__ == "__main__":
    main()
