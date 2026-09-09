"""Non-interactive check that every piece works. Run before using the tool."""

import time

from sfv_access import game, ocr
from sfv_access.capture import Capture
from sfv_access.hotkeys import parse
from sfv_access.app import HOTKEYS
from sfv_access.speech import Speaker

ok = True


def check(label, fn):
    global ok
    try:
        result = fn()
        print(f"PASS  {label}: {result}")
        return result
    except Exception as exc:
        ok = False
        print(f"FAIL  {label}: {type(exc).__name__}: {exc}")
        return None


sp = check("speech backend", lambda: Speaker().backend)
check("ocr languages", ocr.available_languages)
check("hotkey parsing", lambda: [parse(c) and c for c, _ in HOTKEYS.values()] and "all combos valid")

cap = check("capture device", lambda: Capture())
if cap is not None:
    def grab_and_read():
        t0 = time.perf_counter()
        frame = cap.frame(max_age=0.0)
        t1 = time.perf_counter()
        assert frame is not None, "no frame captured"
        items = ocr.reading_order(ocr.read(frame))
        t2 = time.perf_counter()
        return (
            f"{frame.shape[1]}x{frame.shape[0]}, "
            f"capture {(t1 - t0) * 1000:.0f} ms, ocr {(t2 - t1) * 1000:.0f} ms, "
            f"{len(items)} lines"
        )

    check("capture and ocr", grab_and_read)
    cap.close()

gw = game.find_window()
print(f"INFO  Street Fighter V window: {gw if gw else 'not running'}")

print()
print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
