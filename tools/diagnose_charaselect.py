"""Capture one moment of character select, from both memory and the screen.

Saves a picture alongside what memory reports, so the two can be compared
directly instead of guessing which fighter belongs to which side.

Run it with the game in front on character select. It takes one sample and
exits, so it does not matter that the console is behind the game.
"""

from __future__ import annotations

import datetime as _dt
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from sfv_access import game, live, ocr  # noqa: E402
from sfv_access.capture import Capture  # noqa: E402
from sfv_access.speech import Speaker  # noqa: E402

OUT = ROOT / "snapshots"


def main() -> None:
    speech = Speaker()
    session = live.shared()
    if not session.attach():
        speech.say("Street Fighter 5 is not running.")
        sys.exit(1)

    speech.say("Taking one sample in three seconds. Keep character select in front.")
    time.sleep(3.0)

    win = game.find_window()
    foreground = bool(win and win.is_foreground)

    cap = Capture()
    frame = cap.frame(max_age=0.0)
    fighters = session.character_select()
    cap.close()

    if frame is None:
        speech.say("Capture failed.")
        sys.exit(2)

    OUT.mkdir(exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    png = OUT / f"charaselect-{stamp}.png"
    Image.fromarray(frame[:, :, [2, 1, 0]]).save(png)

    items = ocr.reading_order(ocr.read(frame))
    report = {
        "game_in_front": foreground,
        "side_order_setting": session.side_order,
        "fighters_from_memory": [
            {"code": f.code, "world_y": f.y, "costume": f.costume, "colour": f.color}
            for f in fighters
        ],
        "large_text_on_screen": [
            {"text": it.text, "x": round(it.x), "y": round(it.y), "height": round(it.h)}
            for it in items
            if it.h >= 30
        ],
    }
    txt = OUT / f"charaselect-{stamp}.json"
    txt.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(report, indent=1, ensure_ascii=False))
    print(f"\nsaved {png}\nsaved {txt}")
    speech.say(
        f"Sample taken. {len(fighters)} fighters from memory, "
        f"{len(report['large_text_on_screen'])} large pieces of text on screen."
    )
    time.sleep(2.0)


if __name__ == "__main__":
    main()
