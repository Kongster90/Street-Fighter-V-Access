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
# How long a summary screen's sentence must hold still before it is said. The
# VS screen's stage name arrived a read after the rest, and the sentence was
# said without it and then again with it.
SUMMARY_SETTLE = 0.4
# A trial's steps are said again on a restart, but not twice for one: the
# restart notice can come and go while it shows.
TRIAL_RESTART_GAP = 3.0
# How long both of Training's frame counters must stand at 0 before an attack's
# result is said. Between a combo's hits the other side's counter never rests.
ATTACK_SETTLE = 0.25
# When player 1's frame text has gone away, as it does through special moves
# and long combos, the values holding still this long is taken as the end. In
# the log the frame text came back about a second after a long combo's last hit.
ATTACK_SETTLE_UNCOUNTED = 2.0
RETRY = 3.0            # how often to look for the game while not attached
ALIVE_CHECK = 1.0      # how often to confirm the attached game is still there
# The block list is refreshed once a second in the background. If that falls
# this far behind, for whatever reason, refresh it here instead: a stalled
# refresh once left stage select silent for the rest of a session.
STALE_PAGES = 4.0
EMPTY_CHECK = 2.0      # how long quick reads find nothing before a full search checks
# Arcade's result screen offers the next opponent beside one of these. Two
# opponents read as a gold menu; before the final stage, with one opponent,
# nothing on it was shown and nothing was said. Until that screen has been
# seen, the log describes what the reader finds there.
ARCADE_MARKERS = ("NEXT STAGE", "FINAL STAGE")
ARCADE_NOTE_AGAIN = 2.0
WIDE_SWEEP_EVERY = 60.0   # at most this often; a sweep of every readable region takes ~20 s
MAX_EXTRA_PAGES = 32


def _reason(it) -> str:
    """Why a text is not counted as showing."""
    if it.depth < 2:
        return "not attached"
    if not it.rooted:
        return "cut loose from its movie"
    if it.hidden:
        return "parent hidden"
    if it.tint[3] <= 0.01:
        return "transparent"
    if not it.on_stage:
        return "off the stage"
    if scaleform.is_placeholder(it.text):
        return "placeholder"
    return "other"


def _reasons(items) -> str:
    """Why each text is not counted as showing, grouped, with examples."""
    groups: dict[str, list[str]] = {}
    for it in items:
        groups.setdefault(_reason(it), []).append(it.text.replace("\n", " ")[:30])
    return "; ".join(f"{why} {len(texts)}: {scaleform._unique(texts)[:8]}"
                     for why, texts in groups.items()) or "none"


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
        if it.note:
            parts.append(it.note)
        elif it.unavailable:
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
        # A summary screen's sentence, once said, is not said again while the
        # screen stays, however its parts flicker.
        self.summary_said = ""
        self.summary_seen_at = 0.0
        self.summary_pending = ""
        self.summary_since = 0.0
        self.summary_held: list[str] = []
        self.restarted_at = float("-inf")
        # A short introduction, said once as its button is reached: see `step`.
        self.intro_said = ""
        # The game's short message last said, and when it last showed.
        self.toast_said = ""
        self.toast_seen_at = 0.0
        # What a text entry field held at the last reading, None while not typing.
        self.entry_value: str | None = None
        # Training's attack data: its values at the last reading, whether an
        # attack has landed since the last report, whether the other side's
        # frame counter was running, and since when both counters stood at 0.
        self.attack_values = None
        self.attack_pending = False
        self.attack_other_running = False
        self.attack_still_since: float | None = None
        self.attack_changed_at = 0.0
        self.said = ""

    def step(self, items: list[scaleform.TextItem], now: float) -> str:
        """The sentence to speak for this reading, or an empty string."""
        if scaleform.trial_restarted(self.previous, items) and now - self.restarted_at > TRIAL_RESTART_GAP:
            self.restarted_at = now
            # Both, or the unchanged list is refused as a repeat of what was just said.
            self.summary_said = self.said = ""
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

        # The result and VS screens arrive in pieces with nothing selected, and
        # saying what changed would read them out one by one. Each gets one
        # sentence instead, when complete; a menu on them reads as any menu.
        summary_screen, summary = scaleform.screen_summary(items)
        if summary_screen:
            self.summary_seen_at = now
            if not any(it.selected for it in items):
                parts, self.pending = None, None
            if (summary or "") != self.summary_pending:
                self.summary_pending, self.summary_since = summary or "", now
            if summary and summary != self.summary_said:
                if now - self.summary_since >= SUMMARY_SETTLE:
                    # Anything selected while it settled comes after it, once:
                    # the final stage's opponent card arrives with FINAL STAGE.
                    held = [p for p in self.summary_held + (parts or []) if p not in summary]
                    self.summary_said, self.summary_held = summary, []
                    parts = [summary] + scaleform._unique(held)
                else:
                    self.summary_held += parts or []
                    parts = None
        elif (self.summary_said or self.summary_held) and now - self.summary_seen_at > GROUP_MEMORY:
            self.summary_said, self.summary_held = "", []

        # Screens introduced once, as their button is reached: an Extra Battle's
        # event before BEGIN BATTLE, a notice's list before Close. Notices
        # follow one another with Close in the same place, so a new list with
        # its Close still selected is introduced too, though Close did not move.
        intro, button = phrase(scaleform.extra_battle_details(items, brief=True)), scaleform.EXTRA_BATTLE_BUTTON
        if not intro:
            intro, button = phrase(scaleform.notice_details(items, brief=True)), scaleform.NOTICE_BUTTON
        if not intro:
            self.intro_said = ""
        elif intro != self.intro_said:
            reached = parts and button in (p.strip() for p in parts)
            # Only for notices: an Extra Battle's brief carries its time
            # remaining, which would be said again each time it changed.
            still_on = (button == scaleform.NOTICE_BUTTON and self.intro_said
                        and any(it.selected and it.text.strip() == button for it in items))
            if reached or still_on:
                self.intro_said = intro
                parts = [intro] + (parts if reached else [button])

        # Typing into a field selects nothing either. Arriving says the prompt
        # before the instructions; each change says the characters typed or
        # deleted, the same character twice being news both times.
        entry = scaleform.text_entry(items)
        if entry is None:
            self.entry_value = None
        else:
            prompt, value = entry
            foot = scaleform.footer(items)
            # What a move onto the screen would name is said here instead,
            # once and in order, whichever read it arrives on.
            known = {prompt, value, foot.text if foot else ""}
            parts = [p for p in (parts or []) if p not in known]
            if self.entry_value is None:
                parts = [prompt] + ([scaleform.spoken_footer(foot.text)] if foot else []) + parts
            elif value != self.entry_value:
                parts.append(scaleform.typed_words(self.entry_value, value))
                self.said = ""
            self.entry_value = value

        # Training's attack data, said once each attack or combo is over: when
        # an attack has landed and both frame counters have stood at 0 a
        # moment, so a combo's hits are not said one by one.
        data = scaleform.attack_data(items)
        if data is None:
            self.attack_values, self.attack_pending, self.attack_still_since = None, False, None
            self.attack_other_running = False
        else:
            own_running, other_running = bool(data.counter), bool(data.other_counter)
            if self.attack_values is not None:
                if data.values != self.attack_values:
                    self.attack_pending = True
                    self.attack_changed_at = now
                # The same attack landing again leaves the values as they
                # were; the other side's counter starting while this side's
                # attack runs is what shows it landed.
                elif other_running and own_running and not self.attack_other_running:
                    self.attack_pending = True
                    self.attack_changed_at = now
            self.attack_values, self.attack_other_running = data.values, other_running
            # Only a counter showing 0 is at rest. Through special moves and
            # long combos both frame texts go away entirely, and taking that
            # for rest said "3 hits", "5 hits", "6 hits" through one combo.
            if data.counter == 0 and not other_running:
                if self.attack_still_since is None:
                    self.attack_still_since = now
            else:
                self.attack_still_since = None
            quiet = now - self.attack_changed_at
            counted = self.attack_still_since is not None and now - self.attack_still_since >= ATTACK_SETTLE
            uncounted = data.counter is None and not other_running and quiet >= ATTACK_SETTLE_UNCOUNTED
            if self.attack_pending and quiet >= ATTACK_SETTLE and (counted or uncounted):
                self.attack_pending = False
                parts = (parts or []) + [scaleform.attack_summary(data)]
                self.said = ""   # the same result again is a new attack

        # The game's short messages select nothing, so they are said as they
        # appear: once while they show, and again if the same one comes back,
        # as pressing X on the shop's Special again does.
        message = scaleform.toast(items)
        if message is None:
            if self.toast_said and now - self.toast_seen_at > GROUP_MEMORY:
                self.toast_said = ""
        else:
            if message != self.toast_said:
                self.toast_said = message
                self.said = ""   # the same message again is news, not a repeat
                if message not in (parts or []):
                    parts = (parts or []) + [message]
            self.toast_seen_at = now

        said = phrase(parts or [])
        if said and said != self.said:
            self.said = said
            return said
        return ""


KEY_CONFIG_CLASS = "WSKeyConfigGFxPlayer"
KEY_CONFIG_EDITED = 0x477   # the layout being edited; +0x467 holds the one the screen opened with
KEY_CONFIG_MOVIE = 0x318    # GFxMovie, set only on the instance showing


class KeyConfig:
    """The button layout the Controller Setting screen holds, edits included.

    The screen's game object has to be found among some 150,000 objects, which
    takes several seconds, so that is done once on a thread of its own, and the
    object is remembered for as long as its bytes still make sense.
    """

    def __init__(self) -> None:
        self.obj: int | None = None
        self._thread: threading.Thread | None = None

    def read(self) -> bytes | None:
        from . import live

        session = live.shared()
        if self.obj is not None and session.attached:
            config = session.pm.read(self.obj + KEY_CONFIG_EDITED, scaleform.KEY_CONFIG_FUNCTIONS + 1)
            if scaleform.key_config_valid(config):
                return config
            self.obj = None
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._find, daemon=True)
            self._thread.start()
        return None

    def _find(self) -> None:
        from . import live

        session = live.shared()
        try:
            if not session.attach():
                return
            for obj, _name in session.find_by_class(KEY_CONFIG_CLASS):
                config = session.pm.read(obj + KEY_CONFIG_EDITED, scaleform.KEY_CONFIG_FUNCTIONS + 1)
                if session.pm.ptr(obj + KEY_CONFIG_MOVIE) and scaleform.key_config_valid(config):
                    self.obj = obj
                    return
            session.invalidate()
        except Exception:
            pass


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
        self._wide_thread: threading.Thread | None = None
        self._next_wide_sweep = 0.0
        self.attached_now = False   # set when a read has just attached or reattached
        self._pictures_noted: set[str] = set()
        self._arcade_marker: str | None = None
        self._arcade_seen_at = 0.0
        self._arcade_notes = 0
        self.key_config = KeyConfig()

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
        if scaleform.on_controller_setting(items):
            try:
                scaleform.mark_controller_buttons(items, self.key_config.read())
            except Exception as exc:   # the buttons are extra; the rows still read without them
                self.note(f"key config: read failed: {exc!r}")
        self.items = items
        if self._log_screens:
            self._log_screen(items, now)
            new_pictures = self.reader.unknown_pictures - self._pictures_noted
            if new_pictures:
                # Command pictures with no words yet: the name says what to add
                # to scaleform.input_words, as cmd_2 and punch_h did.
                self._pictures_noted |= new_pictures
                self.note(f"pictures in text with no words: {sorted(new_pictures)}")
            try:
                self._note_arcade_offer(items, now)
            except Exception as exc:   # a diagnostic must never cost the narration
                self.note(f"arcade offer: note failed: {exc!r}")
        return items

    def _note_arcade_offer(self, items, now: float) -> None:
        """On Arcade's result screen, log what the reader makes of the opponent on offer.

        Twice per visit: when NEXT STAGE or FINAL STAGE appears, and a little
        later, since the cards can arrive after it. Every fighter's name that is
        not counted as showing is described with why, and each object above it.
        """
        # The fight's own bar says FINAL STAGE too, so only on a result screen.
        marker = next((it for it in items if it.text.strip() in ARCADE_MARKERS), None)
        if marker is not None and not scaleform.on_results(items):
            marker = None
        if marker is None:
            self._arcade_marker, self._arcade_notes = None, 0
            return
        if marker.text.strip() != self._arcade_marker:
            self._arcade_marker, self._arcade_seen_at, self._arcade_notes = marker.text.strip(), now, 0
        if self._arcade_notes >= 2 or (self._arcade_notes == 1 and now - self._arcade_seen_at < ARCADE_NOTE_AGAIN):
            return
        self._arcade_notes += 1
        try:
            every = self.reader.items(everything=True, quick=True)
        except Exception as exc:
            self.note(f"arcade offer: read failed: {exc!r}")
            return
        names = scaleform.fighter_names()
        movie = marker.chain[-1] if marker.chain else None
        shown = [it.text.strip() for it in items if it.text.strip() in names]
        lines = [f"arcade offer ({marker.text.strip()}, note {self._arcade_notes}): names shown {shown}"]
        for it in every:
            text = it.text.strip()
            in_movie = movie is not None and it.chain and it.chain[-1] == movie
            if it.shown or not text or not (text in names or in_movie):
                continue
            lines.append(
                f"    {'NAME ' if text in names else ''}{text[:30]!r} ({it.x:.0f},{it.y:.0f}) "
                f"why {_reason(it)}, tint {[round(t, 2) for t in it.tint]} depth {it.depth} "
                f"up {self.reader.chain_states(it.chain)}")
        self.note("\n".join(lines))

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
            self._start_wide_sweep(now)
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

    def _start_wide_sweep(self, now: float) -> None:
        """Look for text beyond the usual pages, in the background, and log it.

        Both reads can find nothing while text is on screen: back on stage
        select after character select they did for most of a minute. A loading
        screen does the same honestly, so this is only a diagnosis unless it
        finds text showing; then those regions are read from then on.
        """
        if now < self._next_wide_sweep or (self._wide_thread and self._wide_thread.is_alive()):
            return
        self._next_wide_sweep = now + WIDE_SWEEP_EVERY
        reader, stop = self.reader, self._stop

        def run():
            started = time.monotonic()
            try:
                leftovers = [it for it in reader.items(everything=True)
                             if it.text.strip() and not it.shown]
                # Written straight away: if the screen's text is here but judged
                # hidden or transparent, this says so without waiting for the sweep.
                self.note(f"blind: text found but not counted as showing: {_reasons(leftovers)}")
                found = reader.wide_sweep(stop)
            except Exception as exc:
                self.note(f"wide sweep failed: {exc!r}")
                return
            showing = []
            for region, views in found:
                texts = []
                for view in views:
                    text = reader.field_text(view)
                    placed = reader.place(view) if text else None
                    if not placed:
                        continue
                    chain, x, y, tint, hidden, rooted = placed
                    item = scaleform.TextItem(text, x, y, tint, len(chain), view, chain, hidden=hidden,
                                              rooted=rooted)
                    if item.shown:
                        texts.append(text)
                if texts:
                    showing.append((region, texts))
            self.note(
                f"blind for {time.monotonic() - (self._empty_since or started):.0f} s: wide sweep "
                f"took {time.monotonic() - started:.1f} s, found DocViews in {len(found)} other "
                f"regions, {len(showing)} with text showing"
                + "".join(f"; region {r.base:#x} size {r.size:#x} protect {r.protect:#x}: {t[:6]}"
                          for r, t in showing)
            )
            for region, _texts in showing:
                if all(page.base != region.base for page in reader.extra_pages):
                    reader.extra_pages.append(region)
            del reader.extra_pages[:-MAX_EXTRA_PAGES]

        self._wide_thread = threading.Thread(target=run, daemon=True)
        self._wide_thread.start()

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
