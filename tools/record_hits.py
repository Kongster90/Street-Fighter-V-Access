"""Record a window round every hit in a fight, to work out what marks an event.

How counter hits and crossups were found (2026-09-30): the player cannot tell
which hits were which, but Training draws a banner for them ("COUNTER",
"CROSS-UP") in the Key Display column, so a frame saved at each hit labels
it, and comparing what was kept round the labelled hits finds the mark.

A hit is a drop in either fighter's health, read from the fighter records
(`fight.Fight`). Every couple of milliseconds this keeps both records' first
`HEAD` bytes and, from each fighter's 3D character (`fight.PAWN_CLASS`), its
location X and Z and its yaw. For each hit it writes the window from `PRE`
before to `POST` after as hit<n>.npz (times, values: per character x, yaw, z
in the order `pawn_codes` gives; heads: both records' bytes), and a frame of
the screen `FRAME_DELAY` after the hit as hit<n>.png. The first frame of a
run comes late, so its banner may already have gone.

    python tools/record_hits.py [name]          record until stop.txt appears in the folder
    python tools/record_hits.py [name] --sheet  lay out every frame's banner area in sheet.png

Writes snapshots/hits-<name>/, kept out of the repository with the rest of
snapshots/: the frames show the player's name and rank. Runs beside the mod.
"""

from __future__ import annotations

import collections
import datetime as dt
import struct
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access import capture, fight, game, live  # noqa: E402

TIME_LIMIT = 25 * 60
PRE, POST = 1.2, 0.6
FRAME_DELAY = 0.15
HEAD = 0x400
BANNER = (60, 560, 420, 630)    # where Training's COUNTER and CROSS-UP banners are drawn, 1920 by 1080


def find_characters(s, codes):
    """[(code, location address, rotation address)] for each character with a costume."""
    out = []
    for obj, _name in s.find_by_class(fight.PAWN_CLASS, limit=8):
        props = s.all_properties(obj)
        costume = s.pm.ptr(obj + props["CostumeData"].offset)
        root = s.pm.ptr(obj + props["RootComponent"].offset)
        if not costume or not root:
            continue
        component = s.all_properties(root)
        out.append(((fight.costume_code(s, costume) or b"").decode(), root + component["RelativeLocation"].offset, root + component["RelativeRotation"].offset))
    return out


def record(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    log_file = out / "log.txt"
    stop_file = out / "stop.txt"
    stop_file.unlink(missing_ok=True)

    def log(text):
        with log_file.open("a", encoding="utf-8") as fh:
            fh.write(f"{dt.datetime.now():%H:%M:%S.%f}"[:-3] + f" {text}\n")

    f = fight.Fight(note=log)
    s = live.shared()
    cam = capture.Capture()
    started = time.monotonic()
    records = characters = codes = None
    ring = collections.deque()
    pending = []
    hits = 0
    last_health = None
    print(f"recording into {out}; create {stop_file.name} there to stop")
    while time.monotonic() - started < TIME_LIMIT and not stop_file.exists():
        if records is None:
            if f.read() is None or not f.records:
                time.sleep(0.5)
                continue
            records = list(f.records)
            codes = [fight.code(fight.Fight._record_code(s.pm, r)) for r in records]
            characters = find_characters(s, codes)
            log(f"records {[hex(r) for r in records]} characters {codes}; "
                f"3D characters {[(c, hex(a)) for c, a, _r in characters]}")
            if len(characters) != 2:
                log("not two characters; looking again")
                records = None
                time.sleep(1)
                continue
            last_health = None
        now = time.monotonic()
        health = []
        for r in records:
            raw = s.pm.read(r + fight.HEALTH, 4)
            health.append(struct.unpack("<i", raw)[0] >> 16 if raw else None)
        if None in health:
            records = None
            continue
        sample = []
        for _code, location, rotation in characters:
            x, _y, z = struct.unpack("<3f", s.pm.read(location, 12))
            sample += [x, s.pm.f32(rotation + 4), z]
        heads = b"".join(s.pm.read(r, HEAD) or bytes(HEAD) for r in records)
        ring.append((now, sample, heads))
        while ring and now - ring[0][0] > PRE + POST + 0.2:
            ring.popleft()
        if last_health is not None:
            for side in (0, 1):
                if health[side] < last_health[side]:
                    hits += 1
                    pending.append({"n": hits, "at": now, "side": side, "frame": True})
                    log(f"hit {hits}: record {side} ({codes[side]}) lost {last_health[side] - health[side]}")
        last_health = health
        for hit in list(pending):
            if hit["frame"] and now - hit["at"] >= FRAME_DELAY and game.in_front():
                hit["frame"] = False
                try:
                    from PIL import Image
                    frame = cam.frame(max_age=0.0)
                    if frame is not None:
                        Image.fromarray(capture.to_rgb(frame)).save(out / f"hit{hit['n']:03d}.png")
                except Exception as exc:
                    log(f"frame failed: {exc!r}")
            if now - hit["at"] >= POST:
                pending.remove(hit)
                window = [(t, v, h) for t, v, h in ring if hit["at"] - PRE <= t <= hit["at"] + POST]
                np.savez(out / f"hit{hit['n']:03d}.npz",
                         times=np.array([t - hit["at"] for t, _v, _h in window]),
                         values=np.array([v for _t, v, _h in window], dtype=float),
                         heads=np.array([np.frombuffer(h, np.uint8) for _t, _v, h in window]),
                         side=hit["side"], defender=codes[hit["side"]],
                         pawn_codes=np.array([c for c, _l, _r in characters]))
        time.sleep(0.002)
    log(f"done, {hits} hits")
    print(f"done, {hits} hits")


def sheet(out: Path) -> None:
    """Every frame's banner area in one image, two to a row, each numbered."""
    from PIL import Image, ImageDraw

    width, height = BANNER[2] - BANNER[0] + 60, BANNER[3] - BANNER[1]
    tiles = []
    for path in sorted(out.glob("hit*.png")):
        tile = Image.new("RGB", (width, height), "black")
        tile.paste(Image.open(path).crop(BANNER), (60, 0))
        ImageDraw.Draw(tile).text((5, height // 3), path.stem[3:], fill="yellow")
        tiles.append(tile)
    if not tiles:
        print("no frames")
        return
    page = Image.new("RGB", (width * 2, height * ((len(tiles) + 1) // 2)), "black")
    for i, tile in enumerate(tiles):
        page.paste(tile, ((i % 2) * width, (i // 2) * height))
    page.save(out / "sheet.png")
    print(f"wrote {out / 'sheet.png'}, {len(tiles)} frames")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    name = args[0] if args else f"{dt.datetime.now():%Y%m%d-%H%M%S}"
    out = ROOT / "snapshots" / f"hits-{name}"
    if "--sheet" in sys.argv:
        sheet(out)
    else:
        record(out)


if __name__ == "__main__":
    main()
