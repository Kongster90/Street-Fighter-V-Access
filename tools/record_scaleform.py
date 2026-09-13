"""Record what Scaleform is drawing, in full, while you move through a screen.

For working out how a screen marks its selection when the reader cannot tell.
Every text field is kept whether or not the reader counts it as shown, with
its whole owner chain: each object's child count, render node data and first
bytes. A small screenshot is saved with each record while the game is in
front, so which entry was really selected can be checked by eye afterwards.

A record is written whenever what is drawn changes, at most every 0.3
seconds. It speaks when ready and stops on Control Alt Q, rather than
guessing when you are done; the prompt work showed that recorders which
decided in advance what to keep, or when to stop, caught nothing useful.

    python tools/record_scaleform.py [name]

Writes `snapshots/scaleform-<name>/records.jsonl` and `frame-NNN.png`.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from sfv_access import capture as _capture  # noqa: E402
from sfv_access import game, scaleform  # noqa: E402
from sfv_access.hotkeys import Hotkeys  # noqa: E402
from sfv_access.speech import Speaker  # noqa: E402

MIN_GAP = 0.3
OBJECT_BYTES = 0x100
NODE_BYTES = 0xC0


def describe_object(reader: scaleform.ScaleformText, obj: int) -> dict:
    pm = reader.pm
    entry = pm.ptr(obj + scaleform.DISPLAY_RENDER_NODE) or 0
    data = pm.ptr(entry + scaleform.RENDER_NODE_DATA) if entry else 0
    node = pm.read(data, NODE_BYTES) if data else None
    return {
        "vt": (pm.ptr(obj) or 0) - reader.module_base,
        "children": pm.u32(obj + scaleform.DISPLAY_CHILD_COUNT),
        "node": node.hex() if node else None,
        "body": (pm.read(obj, OBJECT_BYTES) or b"").hex(),
    }


def main() -> None:
    name = next((a for a in sys.argv[1:] if not a.startswith("-")), time.strftime("%Y%m%d-%H%M%S"))
    out = ROOT / "snapshots" / f"scaleform-{name}"
    out.mkdir(parents=True, exist_ok=True)

    reader = scaleform.attach()
    if reader is None:
        print("Street Fighter V is not running.")
        sys.exit(1)
    speech = Speaker()
    cap = _capture.Capture()
    stop = threading.Event()
    keys = Hotkeys()
    keys.bind("ctrl+alt+q", stop.set)
    keys.start()
    if keys.failed:
        print(f"could not register {keys.failed}; is the mod or the watch mode running?")
    speech.say("Recorder ready. Control Alt Q when you are done.")

    last_sig = None
    last_write = 0.0
    count = 0
    with (out / "records.jsonl").open("w", encoding="utf-8") as log:
        while not stop.is_set():
            try:
                items = reader.items(everything=True, quick=True)
            except Exception as exc:  # the game closing, most likely
                print(f"read failed: {exc}")
                time.sleep(1)
                continue
            sig = json.dumps([
                (it.text, round(it.x), round(it.y), [round(t, 2) for t in it.tint], it.hidden, it.depth)
                for it in items
            ])
            now = time.monotonic()
            if sig == last_sig or now - last_write < MIN_GAP:
                time.sleep(0.05)
                continue
            last_sig, last_write = sig, now
            objects = {}
            for it in items:
                for obj in it.chain:
                    if obj not in objects:
                        objects[obj] = describe_object(reader, obj)
            record = {
                "t": time.time(),
                "items": [
                    {"text": it.text, "x": it.x, "y": it.y, "tint": it.tint, "depth": it.depth,
                     "hidden": it.hidden, "shown": it.shown, "highlighted": it.highlighted,
                     "chosen": it.chosen, "docview": it.docview, "chain": list(it.chain)}
                    for it in items
                ],
                "objects": {str(k): v for k, v in objects.items()},
            }
            win = game.find_window()
            if win is not None and win.is_foreground:
                frame = cap.frame(max_age=0.0)
                if frame is not None:
                    image = Image.fromarray(frame[:, :, [2, 1, 0]]).resize((960, 540))
                    image.save(out / f"frame-{count:03d}.png")
                    record["frame"] = count
            log.write(json.dumps(record) + "\n")
            log.flush()
            count += 1
    keys.stop()
    cap.close()
    print(f"{count} records in {out}")
    speech.say(f"Recorder stopped, {count} records.")
    time.sleep(2)


if __name__ == "__main__":
    main()
