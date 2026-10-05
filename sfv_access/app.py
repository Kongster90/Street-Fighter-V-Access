"""The running tool: hotkeys, menu narration, fight sounds, and a review cursor.

Street Fighter V draws its interface with Scaleform straight to the GPU, so
there is no window, control or accessibility tree for NVDA to see.

Everything is read from the game's memory: `memory_narration` reads each text
field's exact text and which one is selected, which needs no recognition and no
game in front, and `fight` reads the fighters' records for the gauges and
sounds. Reading the screen, recognising its text and finding the gold, was the
fallback until 2026-10-04, when every screen read from memory and the user
asked for it to go.
"""

from __future__ import annotations

import datetime as _dt
import faulthandler
import os
import sys
import threading
import time
import traceback
from pathlib import Path

from . import capture as _capture
from . import beeps, buttons, fight, game, gametext, instance, memory_narration, pads, scaleform
from .capture import Capture
from .hotkeys import Hotkeys
from .speech import Speaker

SNAPSHOT_DIR = Path(__file__).resolve().parent.parent / "snapshots"
# If one pass of the narration loop takes longer than this, where it is stuck
# is written to the hang log (see `_watch_stalls`). Narration going silent with nothing in
# the other logs to say why is what this is for. The user hears a pass of a
# couple of seconds as the speech stopping and then naming whatever they have
# reached, the entries passed through in between never read, so the threshold
# is well under the five seconds it began at.
HANG_SECONDS = 2.0
# Shorter passes than that are still worth a line, with what the read did, to
# show how often the loop falls behind a player moving through a menu.
SLOW_SECONDS = 0.8
HANG_LOG = SNAPSHOT_DIR / "hang-log.txt"
# Whatever kills the mod, written down however it was started: from the
# desktop shortcut an error reached only the console window, and started with
# the game it reached console-log.txt, which each launch empties.
CRASH_LOG = SNAPSHOT_DIR / "crash-log.txt"
NEWLINE = chr(10)

# Plain Alt, at the user's request: fewer keys to press, and Windows claims some
# Control Alt combinations for itself. Quit is F10, also their choice; the
# watch mode and recorder stop on F10 too.
# Every one was checked as free on this machine. They are registered only
# while the game is in front (see `hotkeys.Hotkeys`): held for as long as the
# mod ran, they took Alt D and the rest from every other program.
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
    "button_names":  ("alt+b",      "name buttons as Xbox, PlayStation or keyboard"),
    "button_hints":  ("alt+c",      "say what the buttons on screen do"),
    "subtitles":     ("alt+t",      "story subtitles off, on, or speaker names only"),
    "beeps_louder":  ("f5",         "health beeps louder"),
    "beeps_quieter": ("shift+f5",   "health beeps quieter"),
    "counter_louder":  ("f6",       "counter hit sound louder"),
    "counter_quieter": ("shift+f6", "counter hit sound quieter"),
    "crossup_louder":  ("f7",       "crossup sound louder"),
    "crossup_quieter": ("shift+f7", "crossup sound quieter"),
    "snapshot":      ("alt+s",      "save a snapshot for calibration"),
    "status":        ("alt+g",      "status"),
    "stop_speech":   ("alt+x",      "stop speaking"),
    "list_keys":     ("alt+k",      "list the keys"),
    "quit":          ("f10",        "quit"),
}

# How long the narration loop waits between tries while the game cannot be read.
WAIT_INTERVAL = 0.12
# Said by a read key while the game's memory cannot be read.
CANNOT_READ = "Cannot read the game yet."
# How often the fighters' health is looked at for the warning beeps while a
# fight shows, and how long to leave it after the fighters could not be found.
FIGHT_POLL = 0.1
FIGHT_RETRY = 3.0
# How often a fight's counter hit marks are looked at. Two small reads; the
# sound is for following up on the hit, so it should come as it lands.
COUNTER_POLL = 0.01
# How often the game's window is looked up to find where its picture is.
# Looking costs a walk over every window, and the window rarely moves.
PICTURE_RECHECK = 1.0

# Started with the game from Steam (see start_with_game.pyw), the mod closes
# when the game does. It waits this long for the game to appear at all, and
# closes once the game has been gone this long. Either of the game's two
# processes counts, and the small launcher starts the real one before it exits,
# so there is no gap between them to wait out.
GAME_WAIT_SECONDS = 180.0
GAME_GONE_SECONDS = 3.0

class GameWatch:
    """When a mod started with the game should close.

    Kept apart from the thread that asks, so the test can drive it with its own
    clock.
    """

    def __init__(self, started: float) -> None:
        self.started = started
        self.last_seen: float | None = None

    def step(self, running: bool, now: float) -> str | None:
        """None to carry on, or why to close: "closed" or "never started"."""
        if running:
            self.last_seen = now
            return None
        if self.last_seen is None:
            return "never started" if now - self.started >= GAME_WAIT_SECONDS else None
        return "closed" if now - self.last_seen >= GAME_GONE_SECONDS else None


class App:
    def __init__(self, with_game: bool = False) -> None:
        # Started by Steam alongside the game, and so to close with it.
        self.with_game = with_game
        self.speech = Speaker()
        self.capture = Capture()
        # The keys are the mod's only while the game is in front, so Alt D and
        # the rest do what they normally do in every other program.
        self.keys = Hotkeys(active=game.in_front, on_taken=self._keys_taken)
        self._taken_said: list[str] = []
        self.lines: list[scaleform.TextItem] = []
        self.footer: str = ""
        self.cursor = -1
        self.watching = True
        self._stop = threading.Event()
        self.session = memory_narration.Session()
        # Survival's health between stages, read from the run rather than
        # measured off the bar, which read 0 on a screen not shaped like ours.
        self.survival_health = memory_narration.SurvivalHealth(note=self.session.note)
        # The fight's gauges for Alt H, read from the fighters' records, and
        # which side is the player's.
        self.fight = fight.Fight(note=self.session.note, names=lambda: scaleform.fight_player_one(
            self.session.items if self.session.available else None))
        # Beeps as each fighter's health drops past a level, player 1 on the left.
        self.health_levels = [beeps.Levels(), beeps.Levels()]
        self.beeper: beeps.Player | None = None
        self._beeper_lock = threading.Lock()   # the health beeps and counter hits share it
        self.narrator = memory_narration.Narrator(subtitles=buttons.subtitle_mode(),
                                                 health=self.survival_health.read,
                                                 health_known=self.survival_health.known,
                                                 side=self.fight.side)
        # Button Preview: each button said as it is pressed, while it is open.
        self.presses = pads.PressWatcher(self._on_preview_press)
        self._hang_file = None
        self._crash_file = None
        # When the narration loop's current pass began, None between passes,
        # and which thread runs it: what `_watch_stalls` looks at.
        self._pass_started: float | None = None
        self._watch_thread_id: int | None = None
        # Where the game's picture sits on screen, and when that was asked.
        self._box: tuple[int, int, int, int] | None = None
        self._box_checked = float("-inf")

    # -------------------------------------------------------------- lifecycle
    def run(self) -> None:
        instance.claim()
        for name, (combo, _desc) in HOTKEYS.items():
            self.keys.bind(combo, getattr(self, f"on_{name}"))
        self.keys.start()

        gw = game.find_window()
        if self.with_game:
            # Steam starts the mod a moment before the game, so this would
            # always say the game is not running.
            where = ""
        elif gw:
            where = f"game found, {gw.width} by {gw.height}. "
        elif game.is_running():
            where = "game running but minimised. "
        else:
            where = "game not running. "
        banner = (
            f"Street Fighter 5 access ready. Speech through {self.speech.backend}. "
            f"{where}Menu narration on, reading the game's memory. "
            "Alt K lists the keys."
        )
        print(banner)
        self.speech.say(banner)
        self.session.note(f"=== {_dt.datetime.now():%Y-%m-%d} mod started")
        try:
            SNAPSHOT_DIR.mkdir(exist_ok=True)
            self._hang_file = HANG_LOG.open("a", encoding="utf-8")
            self._hang_file.write(f"\n=== {_dt.datetime.now():%Y-%m-%d %H:%M:%S} mod started\n")
            self._hang_file.flush()
        except OSError:
            self._hang_file = None
        self._install_crash_log()

        threading.Thread(target=self._watch_loop, daemon=True).start()
        threading.Thread(target=self._watch_stalls, daemon=True).start()
        threading.Thread(target=self._watch_fight, daemon=True).start()
        threading.Thread(target=self._watch_counters, daemon=True).start()
        self.presses.start()
        if self.with_game:
            threading.Thread(target=self._follow_game, daemon=True).start()

        try:
            while not self._stop.wait(0.25):
                pass
        except KeyboardInterrupt:
            pass
        finally:
            self.presses.stop()
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
    def _frame(self):
        """The game's picture as BGRA for a snapshot, or None if capture failed.

        Capture is of the whole screen, and the game's picture is only the
        same thing when it is full screen at a 16 by 9 size, so the picture is
        cut out first: a tester's 1920 by 1200 screen had black bars above and
        below it.
        """
        bgra = self.capture.frame()
        if bgra is None:
            return None
        box = self._picture_box()
        return _capture.crop(bgra, box) if box is not None else bgra

    def _picture_box(self) -> tuple[int, int, int, int] | None:
        """Where the game's picture is on screen, looked up at most once a second.

        Each change is written to the screen log, which testers send, since
        a wrong reading on someone else's machine is otherwise a mystery.
        """
        now = time.monotonic()
        if now - self._box_checked < PICTURE_RECHECK:
            return self._box
        self._box_checked = now
        window = game.find_window()
        box = None if window is None else window.picture
        if box != self._box and window is not None:
            self.session.note(
                f"game window {window.client}, picture {box[2]} by {box[3]} at {box[0]}, {box[1]}")
        self._box = box
        return box

    def _speak_cursor(self) -> None:
        if not self.lines:
            self.speech.say("Nothing read yet. Press alt R.")
            return
        self.speech.say(f"{self.lines[self.cursor].text}. {self.cursor + 1} of {len(self.lines)}")

    def _memory_items(self) -> list | None:
        """The text on screen from memory, or None while the game cannot be read.

        While narration runs, its latest reading is used rather than reading
        again from this thread. With narration off nothing else is reading, so
        a fresh read is safe.
        """
        if self.watching:
            return self.session.items if self.session.available else None
        return self.session.read()

    # --------------------------------------------------------------- handlers
    def on_read_screen(self) -> None:
        items = self._memory_items()
        if items is not None:
            said = memory_narration.phrase(scaleform.name_login([memory_narration.selection_phrase(items)], items))
            foot = scaleform.footer(items)
            story = (scaleform.path_story(items) or scaleform.extra_battle_details(items)
                     or scaleform.notice_details(items) or scaleform.survival_details(items)
                     or scaleform.survival_result(items))
            question = scaleform.prompt_message(items)
            entry = scaleform.text_entry(items)
            chapter = scaleform.story_chapter(items, with_note=True)
            message = scaleform.message_log_entry(items)
            matchup = scaleform.matchup_details(items)
            profile_page = scaleform.profile_page_details(items)
            timeline = scaleform.timeline_entry(items)
            mission = (scaleform.mission_entry(items, brief=False)
                       or scaleform.tournament_entry(items, brief=False))
            trial = scaleform.trial_preview(items)
            purchase = scaleform.purchase_details(items)
            scene = scaleform.story_scene_controls(items)
            scene_controls = scene[1] if scene else (
                self.narrator.story_controls if not any(it.selected for it in items) else None)
            if message and entry is None:
                # What the message says, then when it arrived.
                said = memory_narration.phrase([message[0], message[1]])
            elif timeline and entry is None:
                # A CFN timeline entry: who and what, then when.
                said = memory_narration.phrase([timeline[1], timeline[2]])
            elif matchup and entry is None:
                # A Fighter Profile's match-up, then the figures for it.
                said = memory_narration.phrase(matchup)
            elif profile_page and entry is None:
                # Any other Fighter Profile page: its name, then its figures.
                said = memory_narration.phrase(profile_page)
            elif scene_controls and entry is None:
                # A story scene: the line showing, then the scene's buttons.
                line = scaleform.subtitle(items)
                said = memory_narration.phrase(([memory_narration.phrase(list(line))] if line else [])
                                               + [f"{scaleform.STORY_CONTROLS}. {scene_controls}"])
            elif purchase and entry is None:
                # The shop's purchase prompt: question, price, balances, button.
                said = memory_narration.phrase(purchase[0] + [purchase[1]])
            elif trial and trial[1] and entry is None:
                # A trial tile: its number and the combo beside it.
                said = trial[1]
            elif mission and entry is None:
                # A mission in full, then the description line, which names
                # the modes it counts in.
                said = memory_narration.phrase(
                    mission + ([foot.text] if foot is not None and not foot.selected else []))
            elif chapter and entry is None:
                # A story chapter, then the fighter's profile beside it.
                said = memory_narration.phrase([chapter] + scaleform.story_profile(items))
            elif entry is not None:
                # What has been typed, spelled out, since a name heard as a
                # word does not say how it is written.
                said = memory_narration.phrase([entry[0], scaleform.entry_value_words(entry[1])])
            elif story:
                # Path select's description line is the same for every path;
                # the story is what the user asked to hear.
                said = memory_narration.phrase([said] + story)
            elif question:
                # A prompt's message, then its answer, as when it opened.
                said = memory_narration.phrase(question + [said])
            elif foot is not None and not foot.selected:
                said = memory_narration.phrase([said, foot.text])
            # Costume Settings: whose rows these are, and what square does.
            owner = scaleform.row_owner(items)
            if owner and said and not said.startswith(owner):
                said = memory_narration.phrase([owner, said])
            costume = scaleform.costume_hint(items)
            if costume and said:
                said = memory_narration.phrase([said, costume])
            # Stage conditions do not affect play, so moving through stage
            # select leaves them out; asking for a reading includes them.
            details = scaleform.stage_details(items)
            if said and details:
                said = memory_narration.phrase([said] + details)
            _summary_screen, summary = scaleform.screen_summary(
                items, self.narrator.health_words(), buttons.fighter_id(), self.narrator.player_side)
            prize = scaleform.fortune_detail(items) or scaleform.tournament_details(items)
            if prize:
                # A reading's prize the cursor is on, with its description,
                # without the shop's list behind it.
                said = prize
            elif summary:
                said = memory_narration.phrase([summary, said])
            layout = scaleform.preview_summary(items)
            if layout:
                # Button Preview: the whole layout, button by button.
                said = layout
            keys = scaleform.keyboard_details(items, self.session.saved_layout_bytes)
            mapping = scaleform.keyboard_prompt(items)
            if mapping:
                # Redo keyboard mapping: the step you are on.
                said = scaleform.keyboard_prompt_words(mapping, True)
            elif keys:
                # Keyboard Settings: each key and what it does.
                said = memory_narration.phrase(keys)
            attack = scaleform.attack_data(items)
            if not said and attack is not None:
                # In Training with nothing selected: the last attack in full.
                said = memory_narration.phrase(scaleform.attack_details(attack))
            controls = scaleform.replay_controls(items)
            words = controls[1] if controls else self.narrator.replay_controls
            if words and scaleform.in_replay(items) and not any(it.shown and it.highlighted for it in items):
                # In a replay: its controls, each button named, after anything
                # else; as last seen, the line showing for five seconds only.
                # Not in its pause menu, where they would only be in the way.
                said = memory_narration.phrase([said, words]) if said else words
            self.lines, self.footer = items, foot.text if foot else ""
            self.cursor = next((i for i, it in enumerate(items) if it.selected), 0)
            said = said or "Nothing selected."
            print(f"[read] {said}")
            self.speech.say(said)
            return
        self.speech.say(CANNOT_READ)

    def on_read_hud(self) -> None:
        """Both fighters' health, V-Trigger and Critical Art, from the game's records.

        Measured off the bars on screen, this read a full bar as 83 percent
        and nothing at all on a screen not shaped 16 by 9. Outside a fight
        the records keep the last fight's numbers.
        """
        gauges = self.fight.read()
        if gauges is None:
            self.speech.say("Cannot read the fight.")
            return
        first, second = gauges
        items = self.session.items if self.session.available else None
        if items and scaleform.in_replay(items):
            # A replay is nobody's fight: player 1 first, by number.
            self.speech.say(fight.describe(first, second, fight.REPLAY_SIDES))
            return
        # Player 1's first. The player's side as the battle's settings have
        # it, or as the narrator saw it chosen when they cannot be read.
        side = self.fight.side()
        if side is None:
            side = self.narrator.player_side
        mine, theirs = (second, first) if side == 1 else (first, second)
        self.speech.say(fight.describe(mine, theirs))

    def on_read_live(self) -> None:
        """Read state out of the game itself rather than off the screen.

        Character select from the game's objects: who each side has
        highlighted, in which costume and colour.
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
        if items is None:
            self.speech.say(CANNOT_READ)
            return
        foot = scaleform.footer(items)
        if foot is None:
            self.speech.say("No description shown.")
            return
        self.footer = foot.text
        self.speech.say(foot.text)

    def on_read_all(self) -> None:
        items = self._memory_items()
        if items is None:
            self.speech.say(CANNOT_READ)
            return
        if not items:
            self.speech.say("No text on screen.")
            return
        self.lines, self.cursor = items, 0
        self.speech.say_lines([it.text for it in items])

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
        items = self.session.items if self.session.available else None
        where = ("in a replay" if items and scaleform.in_replay(items)
                 else "in a match" if items and scaleform.fight_on_screen(items) else "in menus")
        focus = "in focus" if gw.is_foreground else "not in focus"
        source = "reading memory" if self.session.available else "waiting to read the game's memory"
        self.speech.say(
            f"Street Fighter 5, {gw.width} by {gw.height}, {focus}, {where}. "
            f"Narration {'on' if self.watching else 'off'}, {source}."
        )

    def on_snapshot(self) -> None:
        """A picture of the game and what memory reads at that moment, to check one against the other."""
        from PIL import Image

        bgra = self._frame()
        if bgra is None:
            self.speech.say("Capture failed.")
            return
        SNAPSHOT_DIR.mkdir(exist_ok=True)
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        png = SNAPSHOT_DIR / f"sfv-{stamp}.png"
        Image.fromarray(bgra[:, :, [2, 1, 0]]).save(png)
        remembered = self._memory_items() or []
        with (SNAPSHOT_DIR / f"sfv-{stamp}-memory.txt").open("w", encoding="utf-8") as fh:
            for it in remembered:
                fh.write(memory_narration.describe(it) + "\n")
        print(f"[snapshot] {png}")
        self.speech.say(f"Snapshot saved, {len(remembered)} lines of text.")

    def on_toggle_watch(self) -> None:
        self.watching = not self.watching
        self.narrator.reset()
        self.speech.say(f"Menu narration {'on' if self.watching else 'off'}.")

    def on_button_hints(self) -> None:
        """The buttons the screen's hints name, and what each does, in the chosen naming style."""
        items = self._memory_items()
        if items is None:
            self.speech.say(CANNOT_READ)
            return
        hints = scaleform.button_hints(items)
        if not hints:
            # A story scene's or a replay's hint shows for a moment only.
            kept = self.narrator.story_controls or (self.narrator.replay_controls
                                                    if scaleform.in_replay(items) else None)
            hints = [kept] if kept else []
        said = memory_narration.phrase(hints) if hints else "No buttons shown on this screen."
        print(f"[buttons] {said}")
        self.speech.say(said)

    def on_button_names(self) -> None:
        """Name buttons the way the player's controller or keyboard does, remembered between runs."""
        chosen = buttons.next_style()
        self.speech.say(f"Button names: {buttons.STYLE_WORDS[chosen]}.")

    def on_subtitles(self) -> None:
        """Story scenes' subtitles off, on, or the speaker's name alone, remembered between runs."""
        self.narrator.subtitles = buttons.next_subtitle_mode()
        self.speech.say(f"{buttons.SUBTITLE_WORDS[self.narrator.subtitles]}.")

    def on_beeps_louder(self) -> None:
        self._change_beeps(beeps.VOLUME_STEP)

    def on_beeps_quieter(self) -> None:
        self._change_beeps(-beeps.VOLUME_STEP)

    def _change_beeps(self, step: int) -> None:
        """Set the health beeps' volume, say it, and play one at it to hear."""
        volume = buttons.change_beep_volume(step)
        self.speech.say(f"Beeps {volume} percent." if volume else "Beeps off.")
        if volume:
            self._beep(beeps.sound(beeps.LEVELS[0][0], None, volume))

    def on_counter_louder(self) -> None:
        self._change_counter(beeps.VOLUME_STEP)

    def on_counter_quieter(self) -> None:
        self._change_counter(-beeps.VOLUME_STEP)

    def _change_counter(self, step: int) -> None:
        """Set the counter hit sound's volume, say it, and play it at that volume to hear."""
        volume = buttons.change_counter_volume(step)
        self.speech.say(f"Counter hits {volume} percent." if volume else "Counter hits off.")
        if volume:
            self._beep(beeps.counter_sound(None, volume))

    def on_crossup_louder(self) -> None:
        self._change_crossup(beeps.VOLUME_STEP)

    def on_crossup_quieter(self) -> None:
        self._change_crossup(-beeps.VOLUME_STEP)

    def _change_crossup(self, step: int) -> None:
        """Set the crossup sound's volume, say it, and play it at that volume to hear."""
        volume = buttons.change_crossup_volume(step)
        self.speech.say(f"Crossups {volume} percent." if volume else "Crossups off.")
        if volume:
            self._beep(beeps.crossup_sound(None, volume))

    def on_quit(self) -> None:
        self._close("Closing Street Fighter 5 access.")

    def _close(self, said: str) -> None:
        self.watching = False
        print(said)
        self.speech.say(said)
        time.sleep(0.6)
        self._stop.set()

    def _follow_game(self) -> None:
        """Close when the game does, for a mod started with it from Steam.

        Left running, the mod would keep its Alt keys from every other program
        until closed by hand, and the next start with the game would find it
        still there.
        """
        watch = GameWatch(time.monotonic())
        while not self._stop.wait(1.0):
            why = watch.step(game.is_running(), time.monotonic())
            if why == "closed":
                self.session.note("game closed, so the mod is closing")
                self._close("Closing Street Fighter 5 access.")
            elif why == "never started":
                self.session.note("game never started, so the mod is closing")
                self._close("Street Fighter 5 did not start. Closing Street Fighter 5 access.")

    def _watch_loop(self) -> None:
        """Speak whatever memory narration finds each time the screen moves.

        While the game cannot be read, before it has drawn any text or after
        it has closed, the loop waits and tries again; nothing is read off the
        screen any more.
        """
        self._watch_thread_id = threading.get_ident()
        while not self._stop.is_set():
            if not self.watching:
                time.sleep(WAIT_INTERVAL)
                continue
            started = time.monotonic()
            self._pass_started = started
            try:
                items = self.session.read()
                if self.session.attached_now:
                    self.narrator.reset()
                if items is not None:
                    # A new copy has none of the game's text until it is
                    # recovered from the game, once, in the background,
                    # after the game has drawn its first text.
                    gametext.ensure(self._say_and_log, self.session.note)
                    self._narrate_memory(items)
                else:
                    self.presses.active.clear()
            except Exception as exc:
                print(f"[watch error] {exc}")
                self.session.note(f"watch error: {exc!r}")
                time.sleep(0.5)
            finally:
                self._pass_started = None
                if self._hang_file is not None:
                    took = time.monotonic() - started
                    if took > SLOW_SECONDS:
                        self._hang_file.write(
                            f"{_dt.datetime.now():%H:%M:%S} that pass took {took:.1f} s"
                            f" ({self.session.last_read})\n")
                        self._hang_file.flush()
                time.sleep(memory_narration.POLL if self.session.available else WAIT_INTERVAL)

    def _watch_fight(self) -> None:
        """Beep as either fighter's health drops past a level, while a fight shows.

        The fight is known by its display's labels over the health bars, read
        from memory with everything else, so nothing is searched for in the
        menus. Player 1's beeps are in the left speaker, player 2's in the
        right, as their bars are on screen. See `beeps`.
        """
        retry_at = 0.0
        while not self._stop.wait(FIGHT_POLL):
            items = self.session.items if self.session.available else None
            if not items or not scaleform.fight_running(items):
                for levels in self.health_levels:
                    levels.reset()
                continue
            now = time.monotonic()
            if now < retry_at:
                continue
            try:
                gauges = self.fight.read()
            except Exception as exc:
                self.session.note(f"fight: beeps could not read the fight: {exc!r}")
                gauges = None
            if gauges is None:
                retry_at = now + FIGHT_RETRY
                continue
            if not self.fight.certain:
                # Which record is whose is a guess for the moment, as while
                # the settings are rewritten between Survival's stages: a
                # guess that swapped the two would sound as a sudden drop.
                for levels in self.health_levels:
                    levels.reset()
                continue
            for side, (levels, g) in enumerate(zip(self.health_levels, gauges)):
                level = levels.update(g.health / g.health_most)
                volume = buttons.beep_volume()
                if level is not None and volume > 0:
                    self._beep(beeps.sound(level, side, volume))

    def _watch_counters(self) -> None:
        """Sound a counter hit, and a crossup, as it lands, in the speaker of whoever landed it.

        The mark is in the record of the fighter hit, so player 2 being hit is
        player 1's counter, heard on the left. Its own loop, and only the two
        marks read, since `_watch_fight` looks only every tenth of a second
        and the sound is for following up on the hit. A crush counter is left
        to the game's own sound, at the user's request. See `fight.Fight.counters`.
        A crossup has no mark: a hit is one when it opens a combo (`Marks.combo`
        is 1; after one, the defender reels facing away for the rest of the
        combo, and every hit of it lands from behind) and lands from behind
        (`fight.crossup`), judged by where the fighters stood
        at this reading and the one before, on a defender who has not just been
        turned round (`fight.Turns`) and whose record does not mark the hit a
        throw (`Marks.thrown`). Each has its own volume, F6 and F7.
        """
        before: list[fight.Marks] | None = None
        placed_before = None   # where the fighters stood at the last reading, for `fight.crossup`
        turns = fight.Turns()  # when each last turned round, which a throw makes them do
        while not self._stop.wait(COUNTER_POLL):
            items = self.session.items if self.session.available else None
            marks = None
            if items and scaleform.fight_running(items):
                try:
                    marks = self.fight.counters()
                except Exception as exc:
                    self.session.note(f"fight: counter hits could not be read: {exc!r}")
            if marks is None:
                before = placed_before = None
                continue
            placed = self._placements()
            now = time.monotonic()
            turns.update(placed, now)
            # The first reading of a fight only notes where things stand.
            if before is not None:
                for side, (now_marks, was) in enumerate(zip(marks, before)):
                    volume = buttons.counter_volume()
                    if now_marks.counter and not was.counter and not now_marks.crush and volume > 0:
                        self._beep(beeps.counter_sound(1 - side, volume))
                    if now_marks.health < was.health:
                        crossup_volume = buttons.crossup_volume()
                        if (now_marks.combo == 1 and crossup_volume > 0 and not now_marks.thrown
                                and turns.steady(side, now)
                                and fight.crossup(side, placed_before, placed)):
                            self._beep(beeps.crossup_sound(1 - side, crossup_volume))
            before, placed_before = marks, placed

    def _placements(self):
        try:
            return self.fight.placements()
        except Exception as exc:
            self.session.note(f"fight: positions could not be read: {exc!r}")
            return None

    def _beep(self, data: bytes) -> None:
        with self._beeper_lock:
            if self.beeper is None:
                self.beeper = beeps.Player()
        self.beeper.play(data)

    def _keys_taken(self, failed: list[str]) -> None:
        """Say which keys another program owns, once for each different set.

        The keys are only taken up when the game comes to the front, so this is
        where a clash is found out, rather than at start as it used to be.
        """
        if failed == self._taken_said:
            return
        self._taken_said = list(failed)
        if len(failed) >= max(2, len(HOTKEYS) // 2):
            # Hotkeys are exclusive per combination, so a second copy of this
            # tool gets nothing. Saying so beats leaving the keys silently dead.
            said = ("Another copy of Street Fighter 5 access is already running, "
                    "so the keys did not register. Close the other copy, then start this one again.")
        else:
            said = "Some keys were taken by another program: " + ", ".join(failed)
        print(said)
        self.speech.say(said)

    def _watch_stalls(self) -> None:
        """Write where the narration loop is stuck, once for each pass that runs long.

        Until 2026-09-16 faulthandler's timed dump did this, and it was the
        likely cause of a tester's crashes: it reads every thread's stack
        without the interpreter's lock while those threads carry on, which
        Python's own documentation warns can crash the process. On a slower
        machine than the user's, passes ran past HANG_SECONDS 112 times, and
        three of six sessions ended partway through writing a dump. This takes
        only the stuck thread's stack, and with the lock held.
        """
        reported = None
        while not self._stop.wait(0.5):
            started = self._pass_started
            if started is None or started == reported or self._hang_file is None:
                continue
            if time.monotonic() - started < HANG_SECONDS:
                continue
            reported = started
            frame = sys._current_frames().get(self._watch_thread_id)
            if frame is None:
                continue
            try:
                self._hang_file.write(
                    f"{_dt.datetime.now():%H:%M:%S} a pass has run {time.monotonic() - started:.1f} s, at:{NEWLINE}"
                    + "".join(traceback.format_stack(frame)))
                self._hang_file.flush()
            except (OSError, ValueError):
                pass

    def _install_crash_log(self) -> None:
        """Write whatever kills the mod to crash-log.txt.

        faulthandler covers a crash in native code, where Python never gets to
        say anything, and dumps every thread then, when the process is going
        anyway. The hooks cover an error nothing caught, on any thread. What
        they write is also still shown wherever it would have been.
        """
        try:
            SNAPSHOT_DIR.mkdir(exist_ok=True)
            self._crash_file = CRASH_LOG.open("a", encoding="utf-8")
            self._crash_file.write(f"{NEWLINE}=== {_dt.datetime.now():%Y-%m-%d %H:%M:%S} mod started{NEWLINE}")
            self._crash_file.flush()
        except OSError:
            self._crash_file = None
            return
        faulthandler.enable(file=self._crash_file, all_threads=True)

        def record(where: str, kind, value, tb) -> None:
            try:
                self._crash_file.write(f"{_dt.datetime.now():%H:%M:%S} uncaught error {where}{NEWLINE}"
                                       + "".join(traceback.format_exception(kind, value, tb)))
                self._crash_file.flush()
            except (OSError, ValueError):
                pass

        main_hook, thread_hook = sys.excepthook, threading.excepthook

        def on_main(kind, value, tb):
            record("on the main thread", kind, value, tb)
            main_hook(kind, value, tb)

        def on_thread(args):
            name = args.thread.name if args.thread is not None else "a thread"
            record(f"in {name}", args.exc_type, args.exc_value, args.exc_traceback)
            thread_hook(args)

        sys.excepthook, threading.excepthook = on_main, on_thread

    def _say_and_log(self, said: str) -> None:
        print(said)
        self._log(said)
        self.speech.say(said)

    def _on_preview_press(self, number: int) -> None:
        said = scaleform.press_words(number, self.session.key_config_bytes)
        self._log(said)
        self.speech.say(said)

    def _narrate_memory(self, items) -> None:
        """Speak whatever the memory narrator decides this reading lands on."""
        if scaleform.preview_open(items) and self.watching:
            self.presses.active.set()
        else:
            self.presses.active.clear()
        said = self.narrator.step(items, time.monotonic())
        if not said:
            return
        self.session.note(f"said {said!r}")
        print(f"[memory] {said}")
        self._log(said)
        self.speech.say(said)

def main() -> None:
    App(with_game="--with-game" in sys.argv[1:]).run()
    # Quit promptly once F10 has closed everything. Speech, capture and the
    # hotkey pump sit in native calls on their own threads, and waiting on
    # the interpreter to wind those down could leave the console open with
    # nothing to say why. Every log is already written and closed.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)
