"""The running tool: hotkeys, menu narration, HUD readout, and a review cursor.

Street Fighter V draws its interface with Scaleform straight to the GPU, so
there is no window, control or accessibility tree for NVDA to see.

Menus are narrated from the game's memory first: `memory_narration` reads each
text field's exact text and which one is selected, which needs no recognition
and no game in front. When memory cannot be read, the pixel reader takes over:
menus are recognised and the highlighted entry found by its gold colour. The
gauges carry no text at all, so they are measured directly from the pixels on a
hotkey. F9 switches between memory and the screen by hand.
"""

from __future__ import annotations

import datetime as _dt
import faulthandler
import re
import threading
import time
from pathlib import Path

from . import capture as _capture
from . import game, hud, memory_narration, menu, ocr, scaleform, screens, strings
from .capture import Capture
from .hotkeys import Hotkeys
from .speech import Speaker

SNAPSHOT_DIR = Path(__file__).resolve().parent.parent / "snapshots"
# If one pass of the narration loop takes longer than this, what every thread
# was doing is written to the hang log. Narration going silent with nothing in
# the other logs to say why is what this is for.
HANG_SECONDS = 5.0
HANG_LOG = SNAPSHOT_DIR / "hang-log.txt"

# Plain Alt, at the user's request: fewer keys to press, and Windows claims some
# Control Alt combinations for itself. Quit is F10 and the memory or screen
# switch F9, also their choice; the watch mode and recorder stop on F10 too.
# Every one was checked as free on this machine. Registered globally, these keys are taken from every program while
# the mod runs, so browser and menu shortcuts such as Alt D stop working there.
# Under Control Alt, c, e, l, n, t, space, slash, minus, equals and backslash
# were claimed by other software.
HOTKEYS = {
    "read_screen":   ("alt+r",      "read what is selected"),
    "read_hud":      ("alt+h",      "read health and meters"),
    "read_live":     ("alt+p",      "read the game's own state"),
    "describe":      ("alt+d",      "describe the selected entry"),
    "next_line":     ("alt+down",   "next line"),
    "prev_line":     ("alt+up",     "previous line"),
    "first_line":    ("alt+home",   "first line"),
    "last_line":     ("alt+end",    "last line"),
    "repeat_line":   ("alt+period", "repeat the current line"),
    "read_all":      ("alt+a",      "read the whole screen"),
    "toggle_watch":  ("alt+m",      "turn menu narration on or off"),
    "switch_source": ("f9",         "switch between reading memory and reading the screen"),
    "snapshot":      ("alt+s",      "save a snapshot for calibration"),
    "status":        ("alt+g",      "status"),
    "stop_speech":   ("alt+x",      "stop speaking"),
    "list_keys":     ("alt+k",      "list the keys"),
    "quit":          ("f10",        "quit"),
}

WATCH_INTERVAL = 0.12
# Reading the game's memory costs far more than the colour scan, so screens
# served that way are polled less often. Still quick enough to keep up with a
# cursor moving across the roster.
MEMORY_INTERVAL = 0.35

# The " 5 of 6." a narrated entry ends with. Stripped before comparing one
# announcement with the last, since the count depends on how much text was
# recognised that frame and the entry itself may not have changed at all.
_POSITION_CLAUSE = re.compile(r"\s\d+ of \d+\.\s*$")


def _leading_clause(said: str) -> str:
    """The thing being named, before anything said about it.

    Announcements are a name and then its detail: a stage and its conditions, a
    setting and its description. The name is what identifies the thing; the
    detail arrives in pieces and changes between readings of the same screen.
    """
    head = said.split(".", 1)[0].strip()
    return head or said.strip()


def clean(text: str) -> str:
    """Tidy the recognised text, then snap it to what the game actually says.

    The player-number labels are a recurring mistake: the engine's stylised "1"
    comes back as a capital I, so "1P PAUSE MENU" arrives as "IP PAUSE MENU".
    Those are fixed first because it makes the following step's job easier.

    Then the text is matched against the game's own localisation table, taken
    from the pak files. Every misreading is by definition a string the game
    does not contain, and the right answer is somewhere in that table, so
    "BAÜLE LOUNGE" becomes "BATTLE LOUNGE" and "RANKED MAT H" becomes "RANKED
    MATCH". Anything that cannot be matched closely, such as a player name or a
    score, is left exactly as it was.
    """
    text = re.sub(r"\s+", " ", text).strip(" .,:;|-•")
    text = re.sub(r"\b([12I])P\b", lambda m: ("1" if m.group(1) == "I" else m.group(1)) + "P", text)
    text = re.sub(r"(?<![A-Za-z])I(?=\s*(?:vs\b|VS\b))", "1", text)
    text = re.sub(r"(?<=\bvs )I(?![A-Za-z])", "1", text)

    vocabulary = strings.shared()
    if vocabulary is not None and text:
        match = vocabulary.correct(text)
        if match.changed:
            return match.text
    return text


def announce(bgra, rgb, with_description: bool = True) -> tuple[str, list, int | None, str]:
    """What the tool should say about this frame.

    Kept free of any app state so it can be replayed against saved snapshots,
    which is the only way to test this without the game in front of you.
    Returns the spoken text, the body lines, the selected index and the footer.
    """
    # A menu highlight settles it before the gauges are consulted. The screen
    # settings page draws a sample HUD so its position can be adjusted, and
    # that sample is pixel for pixel a real one, so no measurement of the bars
    # can tell it apart. During an actual round there is no highlighted menu
    # entry, which makes this the reliable way round.
    group = menu.highlight_group(rgb, bgra)
    band = group[0] if group else None
    if band is None and hud.looks_like_match(rgb):
        return hud.read(rgb).describe(), [], None, ""

    items = ocr.reading_order(ocr.read(bgra))
    _header, body, footer_items = menu.split_chrome(items)
    footer = clean(menu.description(footer_items))
    idx = menu.selected_index(body, band) if band else None
    # The world map's clock is not a menu entry, whichever reader lands on it.
    if idx is not None and menu.looks_like_map_chrome(body[idx].text):
        idx = None

    # The voice language grid marks its choice by brightening a tile rather
    # than by gold on a dark bar, so nothing else here can see it and the
    # screen read as silence. Checked before the rest because it recognises
    # itself by its own heading and cannot be confused with anything.
    voice = screens.voice_grid(rgb, items)
    if voice:
        return voice, body, None, footer

    # Stage select carries a highlighted control of its own for the stage
    # setting, which would otherwise be announced instead of the stage. The
    # stage is the point of the screen, so it leads and the control follows.
    stage = screens.stage_select(items, rgb.shape[0], with_conditions=with_description)
    if stage:
        said = clean_phrase(stage)
        if idx is not None:
            label = clean(body[idx].text)
            value = clean(menu.value_from_group(bgra, group))
            said += f" {label}, {value}." if value else f" {label}."
        return said, body, idx, footer

    if idx is not None:
        label = clean(body[idx].text)
        # The value is taken from its own highlighted band first. A volume
        # level is missed entirely when the whole frame is recognised at once,
        # but reads cleanly from the band around it.
        value = (
            clean(menu.value_from_group(bgra, group))
            or clean(menu.value_on_bar(rgb, body, idx, bgra=bgra))
            or clean(menu.value_for(body, idx))
        )
        # A drawn level bar has the last word. Its printed number is often
        # unreadable on the highlighted row, and counting the cells is exact.
        # Worded as a level so it is not confused with the position that
        # follows it: "level 8 of 10" then "12 of 20" is followable by ear,
        # where "8 of 10. 12 of 20" is not.
        level = menu.volume_level(rgb, int(body[idx].y), int(body[idx].y + body[idx].h))
        if level is not None:
            value = f"level {level} of {menu.BAR_CELLS}"
        said = f"{label}, {value}." if value else f"{label}."
        # On a checklist, whether the entry is on or off is the whole point of
        # the screen, and it was the one thing going unsaid. The screen says so
        # itself: only these carry a "select or deselect all" hint, so nothing
        # else has a state read into it.
        if any("deselect" in i.text.lower() for i in items):
            said += " Ticked." if menu.is_ticked(rgb, body[idx]) else " Not ticked."
        # Among the entry's own list, not among every line recognised on the
        # screen: the latter counted panel text and artwork and would not sit
        # still, giving "10 of 12", then "9 of 11", with nothing touched.
        at, total = menu.list_position(body, idx)
        # An entry with no peers is not in a list, so "1 of 1" says nothing.
        if total > 1:
            said += f" {at} of {total}."
        # The description is worth having but it is a whole sentence, and
        # hearing one on every press while moving down a list is exhausting.
        # Moving through a menu leaves it out; asking for a reading includes it,
        # and Alt D says it on its own.
        if footer and with_description:
            said += f" {footer}"
        return said, body, idx, footer

    # A confirmation dialog marks its answer with a dark fill rather than gold
    # lettering, so nothing above finds it. This one leads, because one of them
    # asks whether to close the game and the answer has to be unambiguous.
    asked = screens.dialog_choice(rgb, items)
    if asked:
        question, answer = asked
        said = f"{clean(question)} {clean(answer)} is selected."
        return said, body, None, footer

    # The main menu's left column is icons with no text, holding Options,
    # Gallery, the terms and conditions and Exit. There is no label to find at
    # the highlight, so the game's own panel across the middle is asked instead.
    # Tried only once nothing else has claimed the screen, so it cannot
    # outrank a real highlighted entry.
    title = screens.main_menu_title(bgra)
    if title:
        said = f"{title}."
        if footer and with_description:
            said += f" {footer}"
        return said, body, None, footer

    # Last resort, once no gold has been found anywhere: the gold pulses, and
    # its dim phase falls outside the colour match, so an entry that is really
    # selected can leave no gold at all in a given frame. Its dark bar does not
    # move, so that is what settles it.
    dark = menu.selected_by_dark_bar(rgb, body)
    if dark is not None:
        label = clean(body[dark].text)
        at, total = menu.list_position(body, dark)
        said = f"{label}. {at} of {total}." if total > 1 else f"{label}."
        if footer and with_description:
            said += f" {footer}"
        return said, body, dark, footer

    if not body:
        return "No text found on screen.", body, None, footer
    return f"No highlight found. {len(body)} lines.", body, None, footer


def change_key(rgb):
    """What the narration loop watches to decide the screen has moved.

    Deliberately not the gold. Where the gold sits is the sharpest way to find
    an entry, which is why `announce` uses it, but it is the wrong thing to
    watch: it pulses, appearing and vanishing between frames with nothing
    touched, so a key built on it re-reads the same screen forever. A
    confirmation dialog has none of it at all, which is why arrowing between
    Yes and No used to be silent.

    Whatever is selected is dark, on every screen in the game, so a coarse map
    of the dark areas moves when the selection does and sits still when only
    the artwork is animating. The main menu's icon column is the one thing that
    map cannot separate, since those tiles are identical but for their picture,
    so the panel naming the entry is watched too.

    Kept out here beside `announce` so the test can build the same key the loop
    builds. Deciding what to say and deciding when to say it drifting apart is
    the worst bug this tool has had.
    """
    return screens.title_signature(rgb), menu.dark_signature(rgb)


def clean_phrase(text: str) -> str:
    """Correct a sentence a clause at a time.

    A whole announcement never matches a single line of the game's text, so
    correcting it as one string finds nothing. Its parts do match: a stage name
    and each of its conditions are separate strings in the table.
    """
    pieces = [p.strip() for p in text.split(".") if p.strip()]
    return ". ".join(clean(p) for p in pieces) + "." if pieces else text


class App:
    def __init__(self) -> None:
        self.speech = Speaker()
        self.capture = Capture()
        self.keys = Hotkeys()
        self.lines: list[ocr.TextItem] = []
        self.footer: str = ""
        self.cursor = -1
        self.watching = True
        self._stop = threading.Event()
        self._last_key = None
        self._last_spoken = ""
        self._last_memory_poll = 0.0
        self._last_memory_lines: list[str] = []
        # Narration from memory, preferred whenever the game can be read.
        self.use_memory = True
        self.session = memory_narration.Session()
        self.narrator = memory_narration.Narrator()
        self._hang_file = None

    # -------------------------------------------------------------- lifecycle
    def run(self) -> None:
        for name, (combo, _desc) in HOTKEYS.items():
            self.keys.bind(combo, getattr(self, f"on_{name}"))
        self.keys.start()

        gw = game.find_window()
        if gw:
            where = f"game found, {gw.width} by {gw.height}"
        elif game.is_running():
            where = "game running but minimised"
        else:
            where = "game not running"
        banner = (
            f"Street Fighter 5 access ready. Speech through {self.speech.backend}. "
            f"{where}. Menu narration on, reading the game's memory. "
            "Alt K lists the keys."
        )
        print(banner)
        failed = self.keys.failed
        if len(failed) >= max(2, len(HOTKEYS) // 2):
            # Hotkeys are exclusive per combination, so a second copy of this
            # tool gets nothing. Saying so beats leaving the keys silently dead.
            banner = (
                "Another copy of Street Fighter 5 access is already running, "
                "so the keys did not register. Close the other copy, then start this one again."
            )
            print(banner)
        elif failed:
            extra = "Some keys were taken by another program: " + ", ".join(failed)
            print(extra)
            banner += " " + extra
        self.speech.say(banner)
        self.session.note(f"=== {_dt.datetime.now():%Y-%m-%d} mod started")
        try:
            SNAPSHOT_DIR.mkdir(exist_ok=True)
            self._hang_file = HANG_LOG.open("a", encoding="utf-8")
            self._hang_file.write(f"\n=== {_dt.datetime.now():%Y-%m-%d %H:%M:%S} mod started\n")
            self._hang_file.flush()
        except OSError:
            self._hang_file = None

        threading.Thread(target=self._watch_loop, daemon=True).start()

        try:
            while not self._stop.wait(0.25):
                pass
        except KeyboardInterrupt:
            pass
        finally:
            self.keys.stop()
            self.capture.close()
            self.session.close()

    def _log(self, said: str) -> None:
        """Keep a record of everything announced, for diagnosing later.

        When something reads wrongly in play there is no way to go back and see
        what happened, and describing it from memory loses the detail that
        matters. This costs nothing and makes a real report possible.
        """
        try:
            SNAPSHOT_DIR.mkdir(exist_ok=True)
            stamp = _dt.datetime.now().strftime("%H:%M:%S")
            with (SNAPSHOT_DIR / "spoken-log.txt").open("a", encoding="utf-8") as fh:
                fh.write(f"{stamp}  {said}\n")
        except Exception:
            pass

    # ---------------------------------------------------------------- helpers
    def _frames(self, max_age: float = 0.0):
        bgra = self.capture.frame(max_age=max_age)
        if bgra is None:
            return None, None
        return bgra, _capture.to_rgb(bgra)

    def _refresh_lines(self, bgra) -> tuple[list, str]:
        items = ocr.reading_order(ocr.read(bgra))
        _header, body, footer = menu.split_chrome(items)
        self.lines = body
        self.footer = clean(menu.description(footer))
        return body, self.footer

    def _speak_cursor(self) -> None:
        if not self.lines:
            self.speech.say("Nothing read yet. Press alt R.")
            return
        item = self.lines[self.cursor]
        # Text read from memory is already exact; correcting it could only harm it.
        text = item.text if isinstance(item, scaleform.TextItem) else clean(item.text)
        self.speech.say(f"{text}. {self.cursor + 1} of {len(self.lines)}")

    def _memory_items(self) -> list | None:
        """The text on screen from memory, or None to use the pixel reader instead.

        While narration runs, its latest reading is used rather than reading
        again from this thread. With narration off nothing else is reading, so
        a fresh read is safe.
        """
        if not self.use_memory:
            return None
        if self.watching:
            return self.session.items if self.session.available else None
        return self.session.read()

    # --------------------------------------------------------------- handlers
    def on_read_screen(self) -> None:
        items = self._memory_items()
        if items is not None:
            said = memory_narration.selection_phrase(items)
            foot = scaleform.footer(items)
            story = scaleform.path_story(items) or scaleform.extra_battle_details(items)
            if story:
                # Path select's description line is the same for every path;
                # the story is what the user asked to hear.
                said = memory_narration.phrase([said] + story)
            elif foot is not None and not foot.selected:
                said = memory_narration.phrase([said, foot.text])
            # Stage conditions do not affect play, so moving through stage
            # select leaves them out; asking for a reading includes them.
            details = scaleform.stage_details(items)
            if said and details:
                said = memory_narration.phrase([said] + details)
            _summary_screen, summary = scaleform.screen_summary(items)
            if summary:
                said = memory_narration.phrase([summary, said])
            if said:
                self.lines, self.footer = items, foot.text if foot else ""
                self.cursor = next((i for i, it in enumerate(items) if it.selected), 0)
                print(f"[read] {said}")
                self.speech.say(said)
                return
            # Nothing selected that memory can see, such as stage select: let
            # the pixel reader have a go.

        bgra, rgb = self._frames()
        if rgb is None:
            self.speech.say("Capture failed.")
            return

        said, body, idx, footer = announce(bgra, rgb)
        self.lines, self.footer = body, footer
        self.cursor = idx if idx is not None else (0 if body else -1)
        print(f"[read] {said}")
        self.speech.say(said)

    def on_read_hud(self) -> None:
        _bgra, rgb = self._frames()
        if rgb is None:
            self.speech.say("Capture failed.")
            return
        if not hud.looks_like_match(rgb):
            self.speech.say("No health bars on screen.")
            return
        self.speech.say(hud.read(rgb).describe())

    def on_read_live(self) -> None:
        """Read state out of the game itself rather than off the screen.

        Character select is served this way because the roster is artwork: the
        pixel reader can see the two names and nothing else, while the game
        knows exactly who is highlighted, in which costume and colour.
        """
        from . import live

        session = live.shared()
        if not session.attach():
            self.speech.say("Cannot read the game's memory. Check it is running.")
            return
        said = session.describe_character_select()
        if said:
            print(f"[live] {said}")
            self.speech.say(said)
        else:
            self.speech.say("Nothing readable from the game on this screen yet.")

    def on_describe(self) -> None:
        items = self._memory_items()
        if items is not None:
            foot = scaleform.footer(items)
            if foot is not None:
                self.footer = foot.text
                self.speech.say(foot.text)
                return

        bgra, _rgb = self._frames()
        if bgra is None:
            self.speech.say("Capture failed.")
            return
        self._refresh_lines(bgra)
        self.speech.say(self.footer or "No description shown.")

    def on_read_all(self) -> None:
        items = self._memory_items()
        if items:
            self.lines, self.cursor = items, 0
            self.speech.say_lines([it.text for it in items])
            return

        bgra, _rgb = self._frames()
        if bgra is None:
            self.speech.say("Capture failed.")
            return
        body, _ = self._refresh_lines(bgra)
        if not body:
            self.speech.say("No text found on screen.")
            return
        self.cursor = 0
        self.speech.say_lines([clean(i.text) for i in body])

    def on_next_line(self) -> None:
        if not self.lines:
            self.on_read_screen()
            return
        if self.cursor >= len(self.lines) - 1:
            self.speech.say("Last line.")
            return
        self.cursor += 1
        self._speak_cursor()

    def on_prev_line(self) -> None:
        if not self.lines:
            self.on_read_screen()
            return
        if self.cursor <= 0:
            self.speech.say("First line.")
            return
        self.cursor -= 1
        self._speak_cursor()

    def on_first_line(self) -> None:
        if self.lines:
            self.cursor = 0
            self._speak_cursor()

    def on_last_line(self) -> None:
        if self.lines:
            self.cursor = len(self.lines) - 1
            self._speak_cursor()

    def on_repeat_line(self) -> None:
        self._speak_cursor()

    def on_list_keys(self) -> None:
        self.speech.say(
            " ".join(f"{c.replace('+', ' ')}, {d}." for c, d in HOTKEYS.values())
        )

    def on_stop_speech(self) -> None:
        self.speech.stop()

    def on_status(self) -> None:
        gw = game.find_window()
        if gw is None:
            running = game.is_running()
            self.speech.say(
                "Street Fighter 5 is running but minimised."
                if running
                else "Street Fighter 5 is not running."
            )
            return
        _bgra, rgb = self._frames()
        where = "in a match" if (rgb is not None and hud.looks_like_match(rgb)) else "in menus"
        focus = "in focus" if gw.is_foreground else "not in focus"
        if not self.use_memory:
            source = "reading the screen"
        elif self.session.available:
            source = "reading memory"
        else:
            source = "reading the screen until memory can be read"
        self.speech.say(
            f"Street Fighter 5, {gw.width} by {gw.height}, {focus}, {where}. "
            f"Narration {'on' if self.watching else 'off'}, {source}."
        )

    def on_snapshot(self) -> None:
        from PIL import Image

        bgra, _rgb = self._frames()
        if bgra is None:
            self.speech.say("Capture failed.")
            return
        SNAPSHOT_DIR.mkdir(exist_ok=True)
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        png = SNAPSHOT_DIR / f"sfv-{stamp}.png"
        Image.fromarray(bgra[:, :, [2, 1, 0]]).save(png)

        items = ocr.reading_order(ocr.read(bgra))
        with (SNAPSHOT_DIR / f"sfv-{stamp}.txt").open("w", encoding="utf-8") as fh:
            fh.write(f"frame {bgra.shape[1]}x{bgra.shape[0]}\n")
            for it in items:
                fh.write(f"{it.x:7.0f} {it.y:7.0f} {it.w:6.0f} {it.h:5.0f}  {it.text}\n")
        # The memory reading of the same moment, for comparing the two readers.
        remembered = self._memory_items()
        if remembered:
            with (SNAPSHOT_DIR / f"sfv-{stamp}-memory.txt").open("w", encoding="utf-8") as fh:
                for it in remembered:
                    fh.write(memory_narration.describe(it) + "\n")

        print(f"[snapshot] {png}")
        self.speech.say(f"Snapshot saved, {len(items)} lines of text.")

    def on_toggle_watch(self) -> None:
        self.watching = not self.watching
        self._last_key = None
        self.narrator.reset()
        self.speech.say(f"Menu narration {'on' if self.watching else 'off'}.")

    def on_switch_source(self) -> None:
        """Choose memory or the screen by hand, for screens one reads and the other does not."""
        self.use_memory = not self.use_memory
        self._last_key = None
        self._last_spoken = ""
        self.narrator.reset()
        if not self.use_memory:
            self.speech.say("Reading the screen.")
        elif self.session.available:
            self.speech.say("Reading memory.")
        else:
            self.speech.say("Reading memory once the game can be read, the screen until then.")

    def on_quit(self) -> None:
        self.watching = False
        self.speech.say("Closing Street Fighter 5 access.")
        time.sleep(0.6)
        self._stop.set()

    def _narrate_from_memory(self) -> None:
        """Announce screens the pixel reader cannot see, currently character select.

        Only the side that changed is spoken, because repeating both every time
        the cursor moves is unbearable when one player is already locked in.
        """
        now = time.time()
        if now - self._last_memory_poll < MEMORY_INTERVAL:
            return
        self._last_memory_poll = now

        from . import live

        session = live.shared()
        if not session.attach():
            return
        lines = session.character_select_lines()
        if not lines:
            self._last_memory_lines = []
            return

        changed = [ln for ln in lines if ln not in self._last_memory_lines]
        self._last_memory_lines = lines
        if not changed or len(changed) == len(lines) == 0:
            return
        # On arriving at the screen both sides are new; say both, then only
        # whichever one moves after that.
        said = ". ".join(changed)
        if said == self._last_spoken:
            return
        self._last_spoken = said
        print(f"[live] {said}")
        self._log(said)
        self.speech.say(said)

    # ------------------------------------------------------------------ watch
    def _announce_now(self, bgra, rgb) -> bool:
        """Read this frame and speak it, unless there is nothing worth saying.

        Both narration paths come through here so neither can drift from the
        other. Keeping that in one place is what fixed the worst bug this tool
        has had, where every improvement went into the reading the user never
        heard. Returns whether anything was spoken.
        """
        said, body, idx, footer = announce(bgra, rgb, with_description=False)
        self.lines, self.footer = body, footer
        self.cursor = idx if idx is not None else (0 if body else -1)
        if not said:
            return False
        # Compared without the position, because how many entries were
        # recognised varies frame to frame while the entry itself has not
        # changed. Idling on the main menu otherwise repeated "Battle Settings,
        # 10 of 12", then 9 of 11, then 11 of 13, every few seconds as the
        # artwork animated. A level such as "level 3 of 10" is not at the end
        # and so still counts as a change.
        if said.startswith("No highlight") or said.startswith("No text"):
            return False  # nothing worth saying; wait for the screen to settle

        # Compared on what is being named, not on everything said about it.
        #
        # Stage select is why. It reads correctly but its detail arrives in
        # pieces: one stage read "Time 4:30" and corrected itself to "14:30",
        # another gained its temperature on the second look, and The Grid
        # Alternative produced four readings in a row. Every one of them was
        # announced and every one interrupted the last. Those sentences take
        # several seconds to say and the next arrived within one, so what
        # reached the user was a word of each and then nothing, which is why
        # stages seemed not to read at all when they read fine.
        #
        # The name is the part that holds still, so it decides. Changing a
        # volume still speaks, because the level is part of the first clause.
        identity = _leading_clause(_POSITION_CLAUSE.sub("", said))
        if identity == self._last_spoken:
            return False
        self._last_spoken = identity
        print(f"[watch] {said}")
        self._log(said)
        self.speech.say(said)
        return True

    def _watch_loop(self) -> None:
        """Announce the highlighted entry whenever it moves.

        The gold scan runs every tick to notice movement, which is a few
        milliseconds. Working out what to say is left entirely to `announce`,
        the same function the read key uses.

        Those were two separate paths until it became clear the narration you
        actually hear was using none of the work done on the other one. Every
        improvement to picking the right entry, reading a slider, correcting
        the text against the game's own words and handling stage select lived
        in `announce`, which only ran when a key was pressed, while moving
        through a menu went through a cruder rule that picks whichever patch of
        gold is largest. That is why the tests all passed and the mod still read
        the wrong thing. The scan now only detects that something moved; the
        tested path decides what it is.

        Memory narration now comes first and the pixel path is the fallback,
        used only while memory cannot be read or when switched to by hand. Each
        tick runs one or the other, never both, so they cannot talk over each
        other.
        """
        while not self._stop.is_set():
            if not self.watching:
                time.sleep(WATCH_INTERVAL)
                continue
            started = time.monotonic()
            if self._hang_file is not None:
                faulthandler.dump_traceback_later(HANG_SECONDS, file=self._hang_file)
            try:
                if self.use_memory:
                    items = self.session.read()
                    if self.session.attached_now:
                        self.narrator.reset()
                    if items is not None:
                        self._narrate_memory(items)
                        continue
                self._pixel_tick()
            except Exception as exc:
                print(f"[watch error] {exc}")
                self.session.note(f"watch error: {exc!r}")
                time.sleep(0.5)
            finally:
                if self._hang_file is not None:
                    faulthandler.cancel_dump_traceback_later()
                    took = time.monotonic() - started
                    if took > HANG_SECONDS:
                        self._hang_file.write(
                            f"{_dt.datetime.now():%H:%M:%S} that pass took {took:.1f} s\n")
                        self._hang_file.flush()
                time.sleep(memory_narration.POLL if self.use_memory and self.session.available
                           else WATCH_INTERVAL)

    def _narrate_memory(self, items) -> None:
        """Speak whatever the memory narrator decides this reading lands on."""
        said = self.narrator.step(items, time.monotonic())
        # F9 can land between the read and this point; once the
        # screen has been chosen, memory must not get the last word.
        if not said or not self.use_memory:
            return
        self.session.note(f"said {said!r}")
        print(f"[memory] {said}")
        self._log(said)
        self.speech.say(said)

    def _pixel_tick(self) -> None:
        """One tick of narration from the screen."""
        # Capture is whole-screen, so without this the narrator reads
        # whatever is in front when the game is behind or minimised.
        win = game.find_window()
        if win is None or not win.is_foreground:
            self._last_key = None
            time.sleep(0.4)
            return

        bgra, rgb = self._frames(max_age=WATCH_INTERVAL / 2)
        if rgb is None:
            return

        # Speech cannot keep pace with a round, and the gauges are on a
        # hotkey instead, so narration stands down during a match.
        if hud.looks_like_match(rgb):
            self._last_key = None
            return

        # About three milliseconds of the hundred and twenty between
        # ticks. See `change_key` for why it watches the dark rather
        # than the gold.
        key = change_key(rgb)
        if key == self._last_key:
            return
        self._last_key = key

        if not self._announce_now(bgra, rgb):
            # Character select has no highlighted text to find: the
            # roster is artwork. The game knows who is picked, so ask
            # it instead, at a slower rate since reading memory costs
            # more than the colour scan does.
            self._narrate_from_memory()


def main() -> None:
    App().run()
