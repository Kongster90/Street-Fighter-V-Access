"""Check the stall report and the crash log, without the game or the mod's keys.

A thread is made to hang past the threshold, and another to die of an error
nothing catches. The stall must be written once, naming where the loop is
stuck, and the error must reach crash-log.txt. The stall report used to be
faulthandler's timed dump of every thread, which a tester's slower machine
triggered 112 times and died partway through three of.
"""

from __future__ import annotations

import faulthandler
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access import app  # noqa: E402

ok = True


def check(label, condition, detail=""):
    global ok
    if condition:
        print(f"PASS  {label}{(': ' + detail) if detail else ''}")
    else:
        ok = False
        print(f"FAIL  {label}{(': ' + detail) if detail else ''}")


with tempfile.TemporaryDirectory() as tmp:
    app.SNAPSHOT_DIR = Path(tmp)
    app.CRASH_LOG = Path(tmp) / "crash-log.txt"
    app.HANG_SECONDS = 0.6
    mod = app.App.__new__(app.App)
    mod._stop = threading.Event()
    mod._hang_file = (Path(tmp) / "hang-log.txt").open("a", encoding="utf-8")
    mod._crash_file = None
    mod._pass_started = None
    mod._watch_thread_id = None

    def stuck_in_a_slow_read():
        mod._watch_thread_id = threading.get_ident()
        mod._pass_started = time.monotonic()
        time.sleep(2.0)
        mod._pass_started = None

    worker = threading.Thread(target=stuck_in_a_slow_read)
    watcher = threading.Thread(target=mod._watch_stalls, daemon=True)
    worker.start()
    watcher.start()
    worker.join()
    time.sleep(0.6)
    mod._stop.set()
    mod._hang_file.close()
    hang = (Path(tmp) / "hang-log.txt").read_text(encoding="utf-8")
    check("a pass running long is written down with where it is stuck",
          "a pass has run" in hang and "stuck_in_a_slow_read" in hang,
          hang.splitlines()[0] if hang else "nothing written")
    check("and written once, not again every half second", hang.count("a pass has run") == 1,
          f"{hang.count('a pass has run')} reports")

    saved_main, saved_thread = sys.excepthook, threading.excepthook
    try:
        mod._install_crash_log()

        def dies():
            raise RuntimeError("the reader fell over")

        doomed = threading.Thread(target=dies, name="narration")
        doomed.start()
        doomed.join()
        mod._crash_file.flush()
        crash = app.CRASH_LOG.read_text(encoding="utf-8")
        check("an error nothing caught reaches crash-log.txt, with the thread and the traceback",
              "uncaught error in narration" in crash and "the reader fell over" in crash
              and "Traceback" in crash, crash.strip().splitlines()[-1] if crash.strip() else "nothing written")
        check("the log marks each start, so a crash can be told from the next session",
              "mod started" in crash)
    finally:
        sys.excepthook, threading.excepthook = saved_main, saved_thread
        faulthandler.disable()
        if mod._crash_file is not None:
            mod._crash_file.close()

print()
print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
