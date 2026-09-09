"""Record what the narration loop sees, tick by tick, while you move a menu.

Menu narration reads wrongly in play in a way no saved snapshot reproduces,
because a snapshot is one settled frame and the fault is about timing. This
runs the same stages the watch loop runs, at the same rate, and writes down
what each tick saw instead of speaking it.

It speaks only a cue at the start and one at the end, so it can be used without
watching the console. Move through the menu normally while it runs.

Nothing here touches the real narration. Close the mod first, or run this
alongside it and accept that both are capturing.

Usage:
    python tools/trace_watch.py [seconds]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access import capture as _capture  # noqa: E402
from sfv_access import game, hud, menu  # noqa: E402
from sfv_access.app import WATCH_INTERVAL, announce  # noqa: E402
from sfv_access.speech import Speaker  # noqa: E402

TRACE = ROOT / "snapshots" / "watch-trace.txt"


def main() -> None:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 25.0
    speech = Speaker()
    cap = _capture.Capture()

    # Long enough to leave the console and bring a fullscreen game to the
    # front, since ticks while the game is behind are thrown away.
    speech.say(
        "Tracing starts in eight seconds. Switch to the game now. "
        f"It then records for {int(seconds)} seconds while you move through "
        "the menu, and says when it is done."
    )
    time.sleep(8.0)

    rows: list[str] = []
    last_key = None
    started = time.perf_counter()
    ticks = 0

    while time.perf_counter() - started < seconds:
        time.sleep(WATCH_INTERVAL)
        ticks += 1
        at = time.perf_counter() - started
        try:
            win = game.find_window()
            if win is None or not win.is_foreground:
                rows.append(f"{at:6.2f}  game not in front")
                continue

            t0 = time.perf_counter()
            bgra = cap.frame(max_age=WATCH_INTERVAL / 2)
            if bgra is None:
                rows.append(f"{at:6.2f}  no frame")
                continue
            rgb = _capture.to_rgb(bgra)
            grab_ms = (time.perf_counter() - t0) * 1000

            if hud.looks_like_match(rgb):
                rows.append(f"{at:6.2f}  looks like a match, standing down")
                last_key = None
                continue

            t0 = time.perf_counter()
            band = menu.highlight_band(rgb)
            band_ms = (time.perf_counter() - t0) * 1000
            if band is None:
                rows.append(f"{at:6.2f}  no highlight  (grab {grab_ms:.0f}, band {band_ms:.0f})")
                last_key = None
                continue

            key = (band.top // 4, band.left // 8, band.right // 8)
            moved = key != last_key
            last_key = key

            # The live loop only speaks when the position changed, but trace
            # every tick: what it would have skipped is the interesting part.
            t0 = time.perf_counter()
            said, body, idx, _footer = announce(bgra, rgb, with_description=False)
            say_ms = (time.perf_counter() - t0) * 1000

            mark = "SPEAKS" if moved else "  ...  "
            rows.append(
                f"{at:6.2f}  {mark}  top={band.top:4d} l={band.left:4d} r={band.right:4d}"
                f"  idx={idx}  grab {grab_ms:3.0f} band {band_ms:3.0f} announce {say_ms:4.0f}"
                f"  | {said}"
            )
        except Exception as exc:
            rows.append(f"{at:6.2f}  error {exc!r}")

    cap.close()
    TRACE.write_text(
        f"{ticks} ticks over {seconds:.0f} s, interval {WATCH_INTERVAL}\n\n"
        + "\n".join(rows)
        + "\n",
        encoding="utf-8",
    )
    speech.say("Tracing done.")
    print(f"wrote {TRACE}")
    time.sleep(2.0)


if __name__ == "__main__":
    main()
