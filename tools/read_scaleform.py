"""Read the interface text straight from the game's memory.

With no arguments, prints every text field showing now, in reading order, with
its stage position and tint. The gold-highlighted ones are marked with an
asterisk, and a dialog's selected button with a plus.

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
POLL = 0.03             # a quick read takes about forty thousandths of a second
PAGE_REFRESH = 1.0      # how often the address space is walked for new blocks
SETTLE = 0.2            # how long a move with nothing selected waits to settle
GROUP_MEMORY = 1.0      # how long a prompt counts as open once its panel is gone
LOG_INTERVAL = 0.25


def phrase(texts: list[str]) -> str:
    """Join pieces into one sentence without doubling their punctuation."""
    out = ""
    for text in (t.strip().replace("\n", " ") for t in texts):
        if not text:
            continue
        if out:
            out += " " if out[-1] in ".?!:" else ". "
        out += text
    return out


def line(it: scaleform.TextItem) -> str:
    r, g, b, a = it.tint
    mark = "*" if it.highlighted else ("+" if it.chosen else " ")
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
    state = {"items": [], "said": ""}

    keys = Hotkeys()
    keys.bind("ctrl+alt+q", stop.set)
    keys.bind("ctrl+alt+r", lambda: speech.say(state["said"] or "Nothing yet."))
    keys.bind("ctrl+alt+a", lambda: speech.say_lines([it.text for it in state["items"]]))
    keys.start()
    if keys.failed:
        print(f"could not register {keys.failed}; is the mod running?")

    # Quick reads look only where text was last found. Keep that list current
    # in the background, since a full sweep takes a third of a second and
    # would hold up every read made while it runs.
    def keep_pages_current():
        while not stop.is_set():
            try:
                reader.refresh_pages()
            except Exception as exc:
                print(f"page refresh failed: {exc}")
            stop.wait(PAGE_REFRESH)

    threading.Thread(target=keep_pages_current, daemon=True).start()

    LOG.parent.mkdir(exist_ok=True)
    speech.say("Reading from memory. Control Alt Q stops.")
    last_shown = None
    last_logged = 0.0
    previous: list = []
    last_key = None
    # A move with nothing selected, such as along the main menu's icon row, is
    # named by what changed with it, and the banner can change a frame after
    # the description. So that kind waits to settle, holding the screen from
    # before the move. A move that selects something is said at once.
    pending = None
    changed_at = 0.0
    # Prompts whose buttons have been seen, each with the panel holding them.
    # One counts as open while its panel still shows anything, such as the
    # question, however long the gap between one answer and the next.
    recent_groups: dict[int, int] = {}
    groups_seen_at = 0.0
    started = time.time()

    with LOG.open("a", encoding="utf-8") as log:
        def say(parts, stamp):
            said = phrase(parts)
            if said and said != state["said"]:
                state["said"] = said
                log.write(f"{stamp} said {said!r}\n")
                log.flush()
                print(f"{stamp} {said}")
                speech.say(said)

        log.write(f"\n=== {_dt.datetime.now():%Y-%m-%d %H:%M:%S} watch started\n")
        while not stop.is_set() and time.time() - started < TIME_LIMIT:
            try:
                items = reader.items(quick=True)
            except Exception as exc:  # the game closing mid-read, most likely
                print(f"read failed: {exc}")
                break
            state["items"] = items
            now = time.monotonic()
            stamp = f"{_dt.datetime.now():%H:%M:%S}"
            shown = [(round(it.x), round(it.y), it.text, it.selected) for it in items]
            if shown != last_shown and now - last_logged >= LOG_INTERVAL:
                last_shown, last_logged = shown, now
                log.write(f"{stamp} screen\n")
                for it in items:
                    log.write(f"    {line(it)}\n")
                log.flush()

            # Button groups seen before this read, so a prompt is only treated
            # as newly opened the first time its buttons turn up.
            if any(panel in it.chain for panel in recent_groups.values() for it in items):
                groups_seen_at = now
            elif recent_groups and now - groups_seen_at > GROUP_MEMORY:
                recent_groups.clear()
            known = frozenset(recent_groups)
            for it in items:
                if it.chosen and it.group in it.chain:
                    at = it.chain.index(it.group)
                    recent_groups[it.group] = it.chain[at + 1] if at + 1 < len(it.chain) else it.group
                    groups_seen_at = now

            key = scaleform.selection_key(items)
            if key != last_key:
                last_key = key
                before = pending if pending is not None else previous
                if any(it.selected for it in items):
                    pending = None
                    say(scaleform.landed_on(before, items, known), stamp)
                else:
                    pending, changed_at = before, now
            elif pending is not None and now - changed_at >= SETTLE:
                say(scaleform.landed_on(pending, items, known), stamp)
                pending = None
            previous = items
            time.sleep(POLL)
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
