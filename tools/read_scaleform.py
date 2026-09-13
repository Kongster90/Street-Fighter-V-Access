"""Read the interface text straight from the game's memory.

With no arguments, prints every text field showing now, in reading order, with
its stage position and tint, and marks the highlighted ones with an asterisk.

    python tools/read_scaleform.py            what is showing
    python tools/read_scaleform.py --all      leftovers and hidden fields too
    python tools/read_scaleform.py --watch    speak the highlight as it moves

The watch mode is for trying this in play. It speaks the highlighted text each
time it changes, and writes every change of what is showing to
`snapshots/scaleform-log.txt`, which is what to read afterwards to see how a
screen came out. Control Alt R repeats the highlight, Control Alt A reads
everything showing, Control Alt Q stops. Run it instead of the mod, not
alongside it, or the two talk over each other.
"""

from __future__ import annotations

import datetime as _dt
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access import scaleform  # noqa: E402

LOG = ROOT / "snapshots" / "scaleform-log.txt"
TIME_LIMIT = 30 * 60


def line(it: scaleform.TextItem) -> str:
    r, g, b, a = it.tint
    mark = "*" if it.highlighted else " "
    state = "" if it.shown else "  (not shown)"
    return (
        f"{mark} ({it.x:7.1f},{it.y:7.1f}) tint {r:.2f} {g:.2f} {b:.2f} {a:.2f}  "
        f"{it.text[:90]!r}{state}"
    )


def print_once(reader: scaleform.ScaleformText, everything: bool) -> None:
    t0 = time.perf_counter()
    items = reader.items(everything=everything)
    dt = time.perf_counter() - t0
    print(f"{len(items)} text fields in {dt:.2f} s")
    for it in items:
        print(line(it))


def watch(reader: scaleform.ScaleformText) -> None:
    from sfv_access.hotkeys import Hotkeys
    from sfv_access.speech import Speaker

    speech = Speaker()
    stop = threading.Event()
    state = {"items": []}

    def highlighted_phrase(items):
        return ". ".join(it.text.replace("\n", " ") for it in items if it.highlighted)

    keys = Hotkeys()
    keys.bind("ctrl+alt+q", stop.set)
    keys.bind("ctrl+alt+r", lambda: speech.say(highlighted_phrase(state["items"]) or "Nothing highlighted."))
    keys.bind("ctrl+alt+a", lambda: speech.say_lines([it.text for it in state["items"]]))
    keys.start()
    if keys.failed:
        print(f"could not register {keys.failed}; is the mod running?")

    LOG.parent.mkdir(exist_ok=True)
    speech.say("Reading from memory. Control Alt Q stops.")
    last_shown = None
    last_phrase = None
    started = time.time()
    with LOG.open("a", encoding="utf-8") as log:
        log.write(f"\n=== {_dt.datetime.now():%Y-%m-%d %H:%M:%S} watch started\n")
        while not stop.is_set() and time.time() - started < TIME_LIMIT:
            try:
                items = reader.items()
            except Exception as exc:  # the game closing mid-read, most likely
                print(f"read failed: {exc}")
                break
            state["items"] = items
            stamp = f"{_dt.datetime.now():%H:%M:%S}"
            shown = [(round(it.x), round(it.y), it.text, it.highlighted) for it in items]
            if shown != last_shown:
                last_shown = shown
                log.write(f"{stamp} screen\n")
                for it in items:
                    log.write(f"    {line(it)}\n")
                log.flush()
            phrase = highlighted_phrase(items)
            if phrase != last_phrase:
                last_phrase = phrase
                log.write(f"{stamp} said {phrase!r}\n")
                log.flush()
                print(f"{stamp} {phrase}")
                if phrase:
                    speech.say(phrase)
            time.sleep(0.1)
        log.write(f"=== {_dt.datetime.now():%H:%M:%S} watch stopped\n")
    speech.say("Stopped.")
    keys.stop()
    time.sleep(1.5)


def main() -> None:
    reader = scaleform.attach()
    if reader is None:
        print("Street Fighter V is not running.")
        sys.exit(1)
    if "--watch" in sys.argv:
        watch(reader)
    else:
        print_once(reader, everything="--all" in sys.argv)


if __name__ == "__main__":
    main()
