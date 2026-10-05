"""Record every change of screen from memory beside the running mod, quietly.

    .venv\\Scripts\\python.exe tools\\record_screens.py <name> [minutes]

Writes snapshots\\<name>\\records.jsonl, one line per change of what is
showing: each shown text with its place, tint, selection mark, note, chain and
the instance names up its chain, and every hidden text with why it is hidden;
and a frame per change (at most one each 0.4 s) while the game is in front.
It holds no keys and says nothing, so it runs beside the mod while the user
plays. Stop it by creating snapshots\\<name>\\STOP, or let the minutes run out
(20 by default). `tools/replay_records.py` replays a recording through the
narrator.

Used throughout 2026-10-04 and 05 (the shop's Fighting Chance, CFN, story
mode): the chains and names are what let a screen's parts be told apart
afterwards, and the frames settle what was really drawn.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from sfv_access import capture, game, memory_narration as mn, scaleform as sf  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out = ROOT / "snapshots" / sys.argv[1]
    out.mkdir(parents=True, exist_ok=True)
    minutes = float(sys.argv[2]) if len(sys.argv) > 2 else 20
    reader = sf.attach()
    if reader is None:
        print("the game is not running")
        sys.exit(2)
    stop = threading.Event()
    reader.refresh_pages()
    reader.keep_pages_current(stop)
    cap = capture.Capture()
    last_key, last_frame, n = None, 0.0, 0
    pending = None   # a record still owed a frame
    end = time.time() + minutes * 60
    with (out / "records.jsonl").open("a", encoding="utf-8") as log:
        while time.time() < end and not (out / "STOP").exists():
            try:
                every = reader.items(everything=True, quick=True)
            except Exception as exc:
                print("read failed", exc)
                time.sleep(0.5)
                continue
            shown = [it for it in every if it.shown]
            key = tuple((it.text, round(it.x), round(it.y), it.selected) for it in shown)
            if key != last_key:
                last_key = key
                n += 1
                stamp = dt.datetime.now().strftime("%H%M%S.%f")[:-3]
                record = {
                    "n": n, "time": stamp,
                    "shown": [{"text": it.text, "x": round(it.x, 1), "y": round(it.y, 1),
                               "tint": [round(c, 2) for c in it.tint], "part": it.part,
                               "mark": "*" if it.highlighted else ("+" if it.chosen else ""), "note": it.note,
                               "chain": [hex(o) for o in it.chain],
                               "names": [reader.object_name(o) for o in it.chain[:8]]}
                              for it in shown],
                    "hidden": [[it.text[:80], mn._reason(it), round(it.x), round(it.y)]
                               for it in every if not it.shown and it.text.strip() and it.depth >= 2],
                }
                log.write(json.dumps(record, ensure_ascii=False) + "\n")
                log.flush()
                pending = (n, stamp)
            if pending is not None and time.time() - last_frame > 0.4:
                window = game.find_window()
                if window is not None and window.is_foreground:
                    try:
                        frame = cap.frame()
                        Image.fromarray(frame[..., [2, 1, 0]]).save(out / f"{pending[0]:04d}-{pending[1]}.png")
                        last_frame = time.time()
                    except Exception as exc:
                        print("capture failed", exc)
                pending = None
            time.sleep(0.1)
    stop.set()
    print("records", n)


if __name__ == "__main__":
    main()
