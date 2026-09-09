"""Save a burst of snapshots while you move through a menu.

Control Alt S saves one screen at a time, which is the right tool when you know
which screen is wrong. It is the wrong tool when a screen reads wrongly only
sometimes, because the interesting frame is the one you cannot know to ask for.

This saves a run of them, spoken cues at each end, so a pass through a menu
yields the frames that go with a trace from `trace_watch.py`.

Each frame is written the same way Control Alt S writes it, a PNG beside a text
dump of every recognised line, so `replay.py`, `show_bands.py` and
`test_screens.py` all read them unchanged.

Usage:
    python tools/grab_screens.py [count] [interval seconds] [lead-in seconds]

The lead-in is how long you get to reach the game and open the screen you want
before it starts. It defaults to eight seconds, which is enough to switch to a
fullscreen game but not to navigate anywhere once you are there.
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
from sfv_access.speech import Speaker  # noqa: E402

SNAPSHOT_DIR = ROOT / "snapshots"


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


def main() -> None:
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    interval = float(sys.argv[2]) if len(sys.argv) > 2 else 1.5
    lead_in = float(sys.argv[3]) if len(sys.argv) > 3 else 8.0

    speech = Speaker()
    cap = _capture.Capture()
    speech.say(
        f"Saving screens in {int(lead_in)} seconds. Switch to the game now "
        "and open the screen you want captured. "
        f"It then takes {count} of them, one every {interval:.0f} seconds, "
        "and says when it is done. Move to a different entry between each."
    )
    # A spoken countdown over the last few seconds, so the start is not a
    # surprise when the console is behind a fullscreen game.
    if lead_in > 4:
        time.sleep(lead_in - 3.0)
        for n in (3, 2, 1):
            speech.say(str(n))
            time.sleep(1.0)
    else:
        time.sleep(lead_in)

    saved = skipped = 0
    for _ in range(count):
        win = game.find_window()
        if win is None or not win.is_foreground:
            skipped += 1
            time.sleep(interval)
            continue
        bgra = cap.frame(max_age=0.0)
        if bgra is None:
            skipped += 1
            time.sleep(interval)
            continue
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        lines = save(bgra, stamp)
        saved += 1
        print(f"[{saved}] sfv-{stamp}  {lines} lines")
        # A short cue rather than a sentence, so it does not run into the next.
        speech.say(str(saved))
        time.sleep(interval)

    cap.close()
    note = f"Saved {saved}."
    if skipped:
        note += f" {skipped} skipped, the game was not in front."
    print(note)
    speech.say(note)
    time.sleep(2.5)


if __name__ == "__main__":
    main()
