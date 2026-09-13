"""Read the interface text straight from the game's memory.

With no arguments, prints every text field showing now, in reading order, with
its stage position and tint. The gold-highlighted ones are marked with an
asterisk, and entries selected some other way with a plus.

    python tools/read_scaleform.py            what is showing
    python tools/read_scaleform.py --all      leftovers and hidden fields too
    python tools/read_scaleform.py --watch    speak the selection as it moves

The watch mode speaks through the same narration the mod uses,
`sfv_access.memory_narration`, without the mod's pixel fallback or its other
keys. It is the quickest way to try a change to memory narration in play. Every
change of what is showing is written to `snapshots/scaleform-log.txt`, as the
mod does too. Alt R repeats the last thing said, Alt A reads
everything showing, F10 stops. Run it instead of the mod, not
alongside it, or the two talk over each other and fight over the keys.
"""

from __future__ import annotations

import datetime as _dt
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access import memory_narration, scaleform  # noqa: E402

TIME_LIMIT = 30 * 60


def print_once(reader: scaleform.ScaleformText, everything: bool) -> None:
    t0 = time.perf_counter()
    items = reader.items(everything=everything)
    dt = time.perf_counter() - t0
    print(f"{len(items)} text fields in {dt:.2f} s")
    for it in items:
        print(memory_narration.describe(it))


def watch() -> None:
    from sfv_access.hotkeys import Hotkeys
    from sfv_access.speech import Speaker

    speech = Speaker()
    stop = threading.Event()
    session = memory_narration.Session()
    narrator = memory_narration.Narrator()

    keys = Hotkeys()
    keys.bind("f10", stop.set)
    keys.bind("alt+r", lambda: speech.say(narrator.said or "Nothing yet."))
    keys.bind("alt+a", lambda: speech.say_lines([it.text for it in session.items]))
    keys.start()
    if keys.failed:
        print(f"could not register {keys.failed}; is the mod running?")

    speech.say("Reading from memory. F10 stops.")
    session.note(f"=== {_dt.datetime.now():%Y-%m-%d} watch started")
    started = time.time()
    while not stop.is_set() and time.time() - started < TIME_LIMIT:
        items = session.read()
        if session.attached_now:
            narrator.reset()
        if items is not None:
            said = narrator.step(items, time.monotonic())
            if said:
                session.note(f"said {said!r}")
                print(f"{_dt.datetime.now():%H:%M:%S} {said}")
                speech.say(said)
        time.sleep(memory_narration.POLL)
    session.note("=== watch stopped")
    session.close()
    speech.say("Stopped.")
    keys.stop()
    time.sleep(1.5)


def main() -> None:
    if "--watch" in sys.argv:
        watch()
        return
    reader = scaleform.attach()
    if reader is None:
        print("Street Fighter V is not running.")
        sys.exit(1)
    print_once(reader, everything="--all" in sys.argv)


if __name__ == "__main__":
    main()
