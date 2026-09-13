"""Record what Scaleform is drawing, in full, while you move through a screen.

For working out how a screen marks its selection when the reader cannot tell.
Every text field is kept whether or not the reader counts it as shown, with
its whole owner chain: each object's child count, render node data and first
bytes. The whole display tree under the movies showing text is kept too,
since a selection can be marked on a picture that holds no text at all. A
small screenshot is saved with each record while the game is in front, so
which entry was really selected can be checked by eye afterwards.

A record is written whenever the text changes or anything in the display
tree is switched on or off or changes brightness, at most every 0.3 seconds.
Watching the text alone missed ticking a song in the menu music list, which
changes only a picture. It speaks when ready and stops on Alt Q,
rather than guessing when you are done; the prompt work showed that
recorders which decided in advance what to keep, or when to stop, caught
nothing useful.

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
TREE_LIMIT = 8000


def walk_tree(reader: scaleform.ScaleformText, roots) -> dict:
    """Every display object under the movie roots, text or not.

    Pictures such as the stage tiles hold no text, so they never appear in a
    text field's chain; walking down through the child arrays is the only
    way to see them. Each node keeps its children, its own transform
    translation in pixels, its own colour multiplier and flag word.
    """
    nodes = {}
    stack = list(roots)
    while stack and len(nodes) < TREE_LIMIT:
        obj = stack.pop()
        if obj in nodes:
            continue
        kids = reader.children(obj)
        node = reader._node(obj)
        nodes[obj] = {
            "vt": (reader.pm.ptr(obj) or 0) - reader.module_base,
            "kids": kids,
            "t": [node[0][2] / scaleform.TWIPS_PER_PIXEL, node[0][5] / scaleform.TWIPS_PER_PIXEL] if node else None,
            "s": [node[0][0], node[0][4]] if node else None,
            "cx": list(node[1]) if node else None,
            "flags": node[2] if node else None,
        }
        stack.extend(k for k in kids if k not in nodes)
    return nodes


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
    reader.keep_pages_current(stop)
    keys = Hotkeys()
    keys.bind("alt+q", stop.set)
    keys.start()
    if keys.failed:
        print(f"could not register {keys.failed}; is the mod or the watch mode running?")
    speech.say("Recorder ready. Alt Q when you are done.")

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
            now = time.monotonic()
            if now - last_write < MIN_GAP:
                time.sleep(0.05)
                continue
            tree = walk_tree(reader, {it.chain[-1] for it in items if it.chain and it.shown})
            sig = json.dumps([
                [(it.text, round(it.x), round(it.y), [round(t, 2) for t in it.tint], it.hidden, it.depth)
                 for it in items],
                sorted((k, n["flags"], [round(c, 1) for c in n["cx"]] if n["cx"] else None)
                       for k, n in tree.items()),
            ])
            if sig == last_sig:
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
                "tree": {str(k): v for k, v in tree.items()},
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
