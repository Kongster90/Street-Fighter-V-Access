"""Record SFVR's netplay panel on every change, quietly, beside the running mod.

    .venv\Scripts\python.exe tools\record_netplay.py <name> [minutes]

Writes snapshots\<name>\records.jsonl, one line per change of SFVR's frame:
every line of text with its place, colour, alpha and window, and the focused
item's id, window and rectangle; and a frame per change (at most one each
0.4 s) while the game is in front. It holds no keys and says nothing. Stop it
by creating snapshots\<name>\STOP, or let the minutes run out (20 by
default). Made on 1 November 2026 to learn the panel; see `sfv_access/netplay`.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from sfv_access import capture, game, netplay  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out = ROOT / "snapshots" / sys.argv[1]
    out.mkdir(parents=True, exist_ok=True)
    minutes = float(sys.argv[2]) if len(sys.argv) > 2 else 20
    reader = netplay.PanelReader(note=print)
    cap = capture.Capture()
    end = time.time() + minutes * 60
    last_key, last_png, n = None, 0.0, 0
    with (out / "records.jsonl").open("a", encoding="utf-8") as log:
        while time.time() < end and not (out / "STOP").exists():
            reading = reader.read()
            if reading is None:
                time.sleep(1.0)
                continue
            key = (reading.focus_id, reading.focus, reading.checked, tuple(r.text for r in reading.runs))
            if key != last_key:
                last_key, n = key, n + 1
                record = {"n": n, "time": dt.datetime.now().strftime("%H:%M:%S.%f")[:-3],
                          "frame": reading.frame, "focus_id": reading.focus_id,
                          "focus_window": reading.focus_window, "focus": reading.focus,
                          "focused": [r.text for r in reading.focused()], "checked": reading.checked,
                          "runs": [{k: (round(v, 1) if isinstance(v, float) else v) for k, v in asdict(r).items()}
                                   for r in reading.runs]}
                if game.in_front() and time.time() - last_png > 0.4:
                    bgra = cap.frame()
                    window = game.find_window()
                    if bgra is not None:
                        if window is not None:
                            bgra = capture.crop(bgra, window.picture)
                        Image.fromarray(bgra[:, :, [2, 1, 0]]).save(out / f"{n:04d}.png")
                        record["png"] = f"{n:04d}.png"
                        last_png = time.time()
                log.write(json.dumps(record) + "\n")
                log.flush()
                print(n, record["time"], record["focused"], len(reading.runs), "lines")
            time.sleep(0.05)
    print("done", n)


if __name__ == "__main__":
    main()
