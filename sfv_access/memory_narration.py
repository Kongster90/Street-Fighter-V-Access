"""Narration from the game's memory: when to speak, and staying attached.

`scaleform.py` reads what is on screen and `scaleform.landed_on` decides what a
move lands on. This holds the rest, which used to live only in the watch mode
of `tools/read_scaleform.py`: telling a move from a screen that is merely
animating, remembering a prompt across the instant between its answers, and
keeping hold of the game as it closes and restarts. The mod and the watch mode
both run through here, so what is tried in the watch mode is what the mod says.

The handover's worst bug was narration living in two places and the improved
one going unheard. `Narrator` is the one place for memory narration; the pixel
reader in `app.announce` stays as the fallback for when memory cannot be read.
"""

from __future__ import annotations

import bisect
import datetime as _dt
import threading
import time
import traceback
from pathlib import Path

from . import scaleform

LOG = Path(__file__).resolve().parent.parent / "snapshots" / "scaleform-log.txt"
LOG_LIMIT = 5 * 1024 * 1024   # rotated to .old beyond this
LOG_INTERVAL = 0.25

POLL = 0.03            # a quick read takes forty to seventy thousandths of a second
SETTLE = 0.2           # how long a move with nothing selected waits to settle
GROUP_MEMORY = 1.0     # how long a prompt counts as open once its panel is gone
RETRY = 3.0            # how often to look for the game while not attached
ALIVE_CHECK = 1.0      # how often to confirm the attached game is still there
# The block list is refreshed once a second in the background. If that falls
# this far behind, for whatever reason, refresh it here instead: a stalled
# refresh once left stage select silent for the rest of a session.
STALE_PAGES = 4.0
EMPTY_CHECK = 2.0      # how long quick reads find nothing before a full search checks


def phrase(texts: list[str]) -> str:
    """Join pieces into one sentence without doubling their punctuation."""
    out = ""
    for text in (t.strip().replace("\n", " ") for t in texts):
        if not text:
            continue
        if out:
            out += " " if out[-1] in ".?!:" else ". "
        out += text
    return out


def describe(it: scaleform.TextItem) -> str:
    """One text field as a log line: selection mark, position, tint, text."""
    r, g, b, a = it.tint
    mark = "*" if it.highlighted else ("+" if it.chosen else " ")
    state = "" if it.shown else "  (not shown)"
    return (
        f"{mark} ({it.x:7.1f},{it.y:7.1f}) tint {r:.2f} {g:.2f} {b:.2f} {a:.2f}  "
        f"{it.text[:90]!r}{state}"
    )


def selection_phrase(items: list[scaleform.TextItem]) -> str:
    """What is selected now, with a tick or unavailability, for the read key."""
    parts = []
    for it in items:
        if not it.selected:
            continue
        parts.append(it.text)
        if it.unavailable:
            parts.append("Unavailable")
        elif it.ticked is not None:
            parts.append(scaleform.tick_word(it.ticked))
    return phrase(scaleform._unique(parts))


class Narrator:
    """Decides, read by read, whether the screen has moved and what to say.

    Pure state with the clock passed in, so a sequence of readings can be
    replayed through it in a test.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.previous: list = []
        self.last_key = None
        # A move with nothing selected, such as along the main menu's icon row,
        # is named by what changed with it, and the banner can change a frame
        # after the description. So that kind waits to settle, holding the
        # screen from before the move. A move that selects something is said
        # at once.
        self.pending = None
        self.changed_at = 0.0
        # Prompts whose buttons have been seen, each with the panel holding
        # them. One counts as open while its panel still shows anything, such
        # as the question, however long the gap between one answer and the next.
        self.recent_groups: dict[int, int] = {}
        self.groups_seen_at = 0.0
        self.said = ""

    def step(self, items: list[scaleform.TextItem], now: float) -> str:
        """The sentence to speak for this reading, or an empty string."""
        if any(panel in it.chain for panel in self.recent_groups.values() for it in items):
            self.groups_seen_at = now
        elif self.recent_groups and now - self.groups_seen_at > GROUP_MEMORY:
            self.recent_groups.clear()
        known = frozenset(self.recent_groups)
        for it in items:
            if it.chosen and it.group in it.chain:
                at = it.chain.index(it.group)
                self.recent_groups[it.group] = it.chain[at + 1] if at + 1 < len(it.chain) else it.group
                self.groups_seen_at = now

        parts = None
        key = scaleform.selection_key(items)
        if key != self.last_key:
            self.last_key = key
            before = self.pending if self.pending is not None else self.previous
            if any(it.selected for it in items):
                self.pending = None
                parts = scaleform.landed_on(before, items, known)
            else:
                self.pending, self.changed_at = before, now
        elif self.pending is not None and now - self.changed_at >= SETTLE:
            parts = scaleform.landed_on(self.pending, items, known)
            self.pending = None
        self.previous = items

        said = phrase(parts or [])
        if said and said != self.said:
            self.said = said
            return said
        return ""


class Session:
    """The memory reader, kept attached to the game across it closing and opening.

    `read` returns the text on screen, or None whenever memory cannot be used:
    the game is not running, or it is but no text has ever been found in it,
    which is what a game update moving the reader's offsets would look like.
    Callers fall back to the pixel reader on None.
    """

    def __init__(self, log_screens: bool = True) -> None:
        self.reader: scaleform.ScaleformText | None = None
        self.items: list[scaleform.TextItem] = []
        self._stop: threading.Event | None = None
        self._next_attempt = 0.0
        self._next_alive_check = 0.0
        self._seen_text = False
        self._log_screens = log_screens
        self._last_logged = 0.0
        self._last_shown = None
        self._empty_since: float | None = None
        self._next_full_check = 0.0
        self._use_full = False
        self.attached_now = False   # set when a read has just attached or reattached

    @property
    def available(self) -> bool:
        return self.reader is not None and self._seen_text

    def close(self) -> None:
        if self._stop is not None:
            self._stop.set()
        if self.reader is not None:
            try:
                self.reader.pm.close()
            except Exception:
                pass
        self.reader, self._stop, self.items, self._seen_text = None, None, [], False

    def _attach(self, now: float) -> None:
        if now < self._next_attempt:
            return
        self._next_attempt = now + RETRY
        reader = scaleform.attach()
        if reader is None:
            return
        self.reader = reader
        self._stop = threading.Event()
        reader.keep_pages_current(self._stop)
        self._next_alive_check = now + ALIVE_CHECK
        self.attached_now = True

    def _still_there(self, now: float) -> bool:
        if now < self._next_alive_check:
            return True
        self._next_alive_check = now + ALIVE_CHECK
        head = self.reader.pm.read(self.reader.module_base, 2)
        return head == b"MZ"

    def read(self, now: float | None = None) -> list[scaleform.TextItem] | None:
        now = time.monotonic() if now is None else now
        self.attached_now = False
        if self.reader is None:
            self._attach(now)
            if self.reader is None:
                return None
        if not self._still_there(now):
            self.close()
            self._next_attempt = now + RETRY
            return None
        try:
            if time.monotonic() - self.reader.pages_refreshed_at > STALE_PAGES:
                self.reader.refresh_pages()
            items = self.reader.items(quick=True)
            if items:
                self._empty_since, self._use_full = None, False
            elif self._use_full:
                # Quick reads are still missing what a full search found: keep
                # searching in full, slower but not silent, until they recover.
                items = self.reader.items()
                self._use_full = bool(items)
            elif self._seen_text:
                items = self._check_empty(now)
                self._use_full = bool(items)
        except Exception as exc:
            self.note(f"read failed, detaching: {exc!r}\n" + traceback.format_exc())
            self.close()
            self._next_attempt = now + RETRY
            return None
        if items:
            self._seen_text = True
        if not self._seen_text:
            return None
        self.items = items
        if self._log_screens:
            self._log_screen(items, now)
        return items

    def _check_empty(self, now: float) -> list:
        """A quick read found nothing: make sure a full search agrees.

        Most of the time it does, on a loading screen. Stage select after
        character select was the exception: the mod went silent there for the
        rest of a session while a fresh reader found its text at once. So once
        nothing has been found for a while, search everything, speak from that
        if it finds text, and write down why the quick read missed it.
        """
        if self._empty_since is None:
            self._empty_since = now
            return []
        if now - self._empty_since < EMPTY_CHECK or now < self._next_full_check:
            return []
        self._next_full_check = now + EMPTY_CHECK
        full = self.reader.items()
        if not full:
            return []
        known = {page.base for page in self.reader._scaleform_pages or []}
        pages = sorted(self.reader.heap_pages(), key=lambda page: page.base)
        starts = [page.base for page in pages]
        missing = set()
        for it in full:
            at = bisect.bisect_right(starts, it.docview) - 1
            if at >= 0 and pages[at].base not in known:
                missing.add((pages[at].base, pages[at].size))
        age = time.monotonic() - self.reader.pages_refreshed_at
        self.note(
            f"quick read found nothing for {now - self._empty_since:.1f} s but a full "
            f"search found {len(full)} texts, e.g. {[it.text for it in full[:3]]}; block "
            f"list {age:.1f} s old with {len(known)} blocks; the text is in "
            f"{len(missing)} blocks it lacks, sizes {sorted({hex(size) for _b, size in missing})}"
        )
        self.reader.refresh_pages()
        return full

    # ------------------------------------------------------------------ logging
    def _write(self, text: str) -> None:
        try:
            LOG.parent.mkdir(exist_ok=True)
            if LOG.exists() and LOG.stat().st_size > LOG_LIMIT:
                LOG.replace(LOG.with_suffix(".txt.old"))
            with LOG.open("a", encoding="utf-8") as fh:
                fh.write(text)
        except OSError:
            pass

    def _log_screen(self, items, now: float) -> None:
        shown = [(round(it.x), round(it.y), it.text, it.selected) for it in items]
        if shown == self._last_shown or now - self._last_logged < LOG_INTERVAL:
            return
        self._last_shown, self._last_logged = shown, now
        stamp = f"{_dt.datetime.now():%H:%M:%S}"
        self._write(f"{stamp} screen\n" + "".join(f"    {describe(it)}\n" for it in items))

    def note(self, text: str) -> None:
        """Record something in the screen log, such as what was said."""
        self._write(f"{_dt.datetime.now():%H:%M:%S} {text}\n")
