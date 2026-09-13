"""Speech output through Prism.

Prism (github.com/ethindp/prism, the `prismatoid` package) puts NVDA, JAWS,
ZoomText and the other Windows screen readers behind one interface, and falls
back to OneCore and then SAPI when none is running. It chooses the best one
available itself and talks to NVDA directly, so nothing needs to sit beside
run.py.

Announcements are serialised on a worker thread so a long read can be cut off
by the next hotkey without blocking the caller.
"""

from __future__ import annotations

import queue
import threading


class PrismVoice:
    """Prism's best available backend, rebuilt when its screen reader goes away.

    A backend is bound to the screen reader it found at creation, and keeps
    failing if that screen reader exits, so a failure gets one fresh choice
    and one retry before it is reported.
    """

    def __init__(self) -> None:
        from prism import Context

        self._ctx = Context()
        self._connect()

    def _connect(self) -> None:
        # create_best rather than acquire_best, which would hand back the cached
        # backend still bound to the screen reader that has just gone.
        self._backend = self._ctx.create_best()
        self.name = f"Prism ({self._backend.name})"

    def speak(self, text: str, interrupt: bool) -> None:
        from prism import PrismError

        # Prism refuses empty text and embedded nulls, which a string read out
        # of the game's memory can carry.
        text = text.replace("\x00", "")
        if not text:
            return
        # output rather than speak, so a braille display gets it as well.
        try:
            self._backend.output(text, interrupt)
        except PrismError:
            self._connect()
            self._backend.output(text, interrupt)

    def silence(self) -> None:
        self._backend.stop()


class Speaker:
    """Speech on a dedicated thread.

    Everything touching Prism runs on one thread and nothing else does. Its
    backends are not thread-safe, and creating one initialises COM as a
    single-threaded apartment on whichever thread calls it, which then stops
    Desktop Duplication from setting the apartment model it needs. Confining it
    to this thread settles both problems.
    """

    def __init__(self) -> None:
        self.notes: list[str] = []
        self._voice: PrismVoice | None = None
        self._q: queue.Queue = queue.Queue()
        self._ready = threading.Event()
        threading.Thread(target=self._pump, daemon=True).start()
        self._ready.wait(10.0)
        for note in self.notes:
            print(f"[speech] {note}")

    @property
    def backend(self) -> str:
        self._ready.wait(10.0)
        return self._voice.name if self._voice else "none"

    def say(self, text: str, interrupt: bool = True) -> None:
        """Queue `text`. With interrupt=True, drop anything still pending."""
        if not text:
            return
        if interrupt:
            self._drain()
        self._q.put(("say", text, interrupt))

    def say_lines(self, lines, interrupt: bool = True) -> None:
        """Queue several lines separately so each can be cut off."""
        lines = [ln for ln in lines if ln]
        if not lines:
            return
        if interrupt:
            self._drain()
        for i, line in enumerate(lines):
            self._q.put(("say", line, interrupt and i == 0))

    def stop(self) -> None:
        self._drain()
        self._q.put(("silence", "", False))

    def _drain(self) -> None:
        while True:
            try:
                self._q.get_nowait()
            except queue.Empty:
                return

    def _pump(self) -> None:
        try:
            self._voice = PrismVoice()
        except Exception as exc:
            self.notes.append(f"Prism unavailable: {exc}")
        finally:
            self._ready.set()

        while True:
            kind, text, interrupt = self._q.get()
            try:
                if self._voice is None:
                    if kind == "say":
                        print(f"[speech] {text}")
                elif kind == "say":
                    self._voice.speak(text, interrupt)
                else:
                    self._voice.silence()
            except Exception as exc:  # never let a speech error kill the loop
                print(f"[speech error] {exc}: {text}")
