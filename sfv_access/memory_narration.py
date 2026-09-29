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
import struct
import threading
import time
import traceback
from pathlib import Path

from . import buttons, scaleform

LOG = Path(__file__).resolve().parent.parent / "snapshots" / "scaleform-log.txt"
LOG_LIMIT = 5 * 1024 * 1024   # rotated to .old beyond this
LOG_INTERVAL = 0.25

POLL = 0.03            # a quick read takes forty to seventy thousandths of a second
SETTLE = 0.2           # how long a move with nothing selected waits to settle
# The main menu's banner can take an icon's name a moment after the description
# line changes; later than this, with the description unchanged, it is an advert.
BANNER_CATCHUP = 1.0
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
# Survival's health, for the supplement screen's sentence, is the run's own
# number read from memory (`SurvivalHealth`), there the moment the fight ends.
# It used to be measured off the bar still drawn behind the screen, which
# meant waiting for the bar to fill and its shine to pass, lost the sentence
# when the player moved on first, and said 0 percent on a tester's 1920 by
# 1200 screen. The sentence waits this long for a first reading, then goes
# without one: finding the run takes a second or two the first time.
HEALTH_CAP = 3.0
# A Health Recovery bought on the supplement screen, or a Battle Item that
# restores health, is applied as the next stage starts, the moment the player
# says Yes to starting it (18:45:22 on 2026-09-28, 645 to 975 of 975), not
# when it is chosen. A rise in the run's health this soon after leaving those
# screens is said as "Health now at 100 percent", at the user's request.
HEALTH_RISE = 0.005
HEALTH_RISE_WINDOW = 15.0
# On Survival's Battle Items screen the entries are things whose names say
# nothing about what they do, so the description line follows the name by
# itself after this long, at the user's request, rather than waiting for the
# read key. Moving on before it is due drops it.
DESCRIBE_AFTER = 0.5
CONTROLS_HINT = "Press Alt B to cycle through button styles."
# If arriving on Controller Setting names nothing, the hint is said alone after this.
CONTROLS_HINT_WAIT = 0.6
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


phrase = scaleform.phrase


def describe(it: scaleform.TextItem) -> str:
    """One text field as a log line: selection mark, position, tint, text."""
    r, g, b, a = it.tint
    mark = "*" if it.highlighted else ("+" if it.chosen else " ")
    state = "" if it.shown else "  (not shown)"
    return (
        f"{mark} ({it.x:7.1f},{it.y:7.1f}) tint {r:.2f} {g:.2f} {b:.2f} {a:.2f}  "
        f"{it.text[:90]!r}{state}"
    )


def _only_the_description_moved(before: list, items: list) -> bool:
    """Whether the description line is the only thing that changed, and it names an entry.

    True on a menu of pictures such as CFN's, where there is nothing else to
    wait for; false where a banner or anything else changed with it, which is
    what settling is for.
    """
    foot = scaleform.footer(items)
    if foot is None or not scaleform.entry_title(foot.text):
        return False
    was = {scaleform._where(it) for it in before}
    return all(it is foot for it in items if scaleform._where(it) not in was)


def selection_phrase(items: list[scaleform.TextItem]) -> str:
    """What is selected now, with a tick or unavailability, for the read key."""
    parts = []
    for it in scaleform.left_to_right_rows([it for it in items if it.selected]):
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

    def __init__(self, subtitles: bool = False, health=None, health_known=None) -> None:
        # Whether story scenes' subtitles are said: the player's choice, kept across resets.
        self.subtitles = subtitles
        # Asked for a health reading on the one screen that wants one, or None.
        self.health = health
        # The same reading, but only if the run has been found already, so
        # asking it anywhere costs nothing and starts no search. See HEALTH_RISE.
        self.health_known = health_known
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
        # The health read as the supplement screen showing now arrived, which
        # its sentence carries, when it was first asked for, and whether the
        # sentence has stopped waiting for it.
        self.health_value: float | None = None
        self.health_first_at = 0.0
        self.health_settled = False
        # The health as the supplement and Battle Items screens last had it,
        # and when they were last showing, to hear a recovery being applied.
        self.health_armed: float | None = None
        self.health_armed_at = 0.0
        # Which side the player fights on, 0 the left: chosen in Versus's
        # list against the CPU, found by Fighter ID online, the left anywhere
        # else. The VS screen and the read key for the fight both need it.
        self.player_side = 0
        # Battle Items: the entry whose description line is owed, when it was
        # named, and whether it has been given. See `DESCRIBE_AFTER`.
        self.described_key = None
        self.described_at = 0.0
        self.described_said = True
        # A short introduction, said once as its button is reached: see `step`.
        self.intro_said = ""
        # The newest chat entry in the lounge, once it has been heard or
        # counted as history. None away from a lounge.
        self.chat_said: str | None = None
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
        # Controller Setting's hint: when this visit began, whether the hint
        # has been said, and when the screen last showed.
        self.controls_arrived_at: float | None = None
        self.controls_hinted = False
        self.controls_seen_at = 0.0
        self.preview_hinted = False
        self.preview_seen_at = 0.0
        self.keyboard_hinted = False
        self.keyboard_seen_at = 0.0
        # Redo keyboard mapping: the instruction last said, and the key column then.
        self.mapping_prompt: str | None = None
        self.mapping_rows: list[str] | None = None
        self.subtitle_said: tuple[str, str] | None = None
        # A replay's controls in words, as last seen while the replay lasts,
        # and whether this replay has had them said.
        self.replay_controls: str | None = None
        self.controls_announced = False
        # CFN's timeline entry at the last read, and the one last said.
        self.timeline_seen = None
        self.timeline_said = None
        # The description line, and when it last changed, so an advert in the
        # main menu's banner can be told from a move.
        self.footer_text: str | None = None
        self.footer_changed_at = 0.0
        self.said = ""

    def health_words(self) -> str | None:
        """"Health 95 percent", as read when the supplement screen arrived, for the read key too."""
        if not self.health_settled or self.health_value is None:
            return None
        return f"Health {round(self.health_value * 100)} percent"

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
        # What the main menu's banner showed a read ago; see the adverts below.
        was_banner = scaleform.banner_texts(self.previous)
        key = scaleform.selection_key(items)
        if key != self.last_key:
            self.last_key = key
            before = self.pending if self.pending is not None else self.previous
            if any(it.selected for it in items):
                self.pending = None
                parts = scaleform.landed_on(before, items, known)
            elif _only_the_description_moved(before, items):
                # CFN's entries are pictures, so its description line is the
                # whole move and arrives in one piece. Waiting to settle, which
                # is there for a move whose parts come a frame apart, only put
                # half a second between the user's press and the speech.
                self.pending = None
                parts = scaleform.landed_on(before, items, known)
            else:
                self.pending, self.changed_at = before, now
        elif self.pending is not None and now - self.changed_at >= SETTLE:
            parts = scaleform.landed_on(self.pending, items, known)
            self.pending = None
        self.previous = items

        # The main menu's banner rotating through adverts is not a move: a move
        # changes the description line too, and the banner catches up with it
        # within a moment, where an advert comes with the description as it was.
        # With the cursor on the banner itself each advert changes the
        # description too; there an advert following an advert is no move.
        foot = scaleform.footer(items)
        foot_text = foot.text if foot else None
        if foot_text != self.footer_text:
            self.footer_text, self.footer_changed_at = foot_text, now
        if parts:
            banner = scaleform.banner_texts(items)
            if banner and all(" ".join(p.split()) in banner for p in parts):
                settled = now - self.footer_changed_at > BANNER_CATCHUP
                rotating = (bool(was_banner) and not was_banner & scaleform.MAIN_MENU_NAMES
                            and not banner & scaleform.MAIN_MENU_NAMES)
                if settled or rotating:
                    parts = None

        # A message says what it says; when it arrived is on the read key.
        message = scaleform.message_log_entry(items)
        if message and parts:
            parts = [message[0] if " ".join(p.split()).endswith(message[0]) else p for p in parts]
        # A replay's controls, when they appear, with the buttons named; kept
        # for the read key while the replay lasts, the line lasting five seconds.
        # Said the first time the line appears in a replay, whether or not a
        # move comes with it (mid-replay none did, and it went unsaid), and
        # not again until another replay: said at every resume, pause and
        # change of speed it was too much, the user found (2026-09-23).
        controls = scaleform.replay_controls(items)
        if controls:
            self.replay_controls = controls[1]
            parts = [p for p in (parts or []) if " ".join(p.split()) != controls[0]] or None
            if not self.controls_announced:
                self.controls_announced = True
                parts = (parts or []) + [controls[1]]
                self.said = ""
        elif not scaleform.in_replay(items):
            self.replay_controls = None
            self.controls_announced = False
        # So does an entry in CFN's timeline: who and what, the date on the read
        # key. An entry is said whole whenever the cursor lands on another,
        # once it has held for a read, since saying what changed left out the
        # player when two entries in a row were the same player's, the event
        # when it was the same event, and everything when only the date
        # differed (2026-09-23).
        timeline = scaleform.timeline_entry(items)
        seen, self.timeline_seen = self.timeline_seen, timeline
        if timeline is None:
            self.timeline_said = None
        else:
            known = timeline[3] | (seen[3] if seen else frozenset())
            parts = [p for p in (parts or []) if " ".join(p.split()) not in known] or None
            if timeline == seen and timeline != self.timeline_said:
                self.timeline_said = timeline
                parts = [timeline[1]] + (parts or [])
                self.said = ""

        # A character's story chapter is said as a sentence rather than its
        # pieces in screen order, which put "VS" after the opponent's name.
        chapter = scaleform.story_chapter(items)
        if chapter and parts:
            pieces = scaleform.story_chapter_texts(items) | {"Unavailable"}
            if any(" ".join(p.split()) in pieces for p in parts):
                parts = [chapter] + [p for p in parts if " ".join(p.split()) not in pieces]

        # The result and VS screens arrive in pieces with nothing selected, and
        # saying what changed would read them out one by one. Each gets one
        # sentence instead, when complete; a menu on them reads as any menu.
        # Whose game this is, learnt from the main menu's card and kept in the
        # settings, so an online VS screen can tell the player's side from
        # their opponent's. Only worth writing once.
        card = scaleform.player_card(items)
        if card and card != buttons.fighter_id():
            buttons.remember_fighter_id(card)

        # Survival's supplement screen is the one whose sentence carries the
        # health taken into the next stage, read from the run. See HEALTH_CAP.
        on_supplements = scaleform.on_survival_supplements(items)
        if not on_supplements:
            self.health_value, self.health_first_at = None, 0.0
            self.health_settled = self.health is None
            # The run is made as its tips screen shows, before the first
            # fight: asking then finds it in time for the first stage's sentence.
            if self.health is not None and scaleform.survival_tips(items):
                self.health()
        elif self.health is not None and not self.health_settled:
            self.health_first_at = self.health_first_at or now
            self.health_value = self.health()
            self.health_settled = (self.health_value is not None
                                   or now - self.health_first_at >= HEALTH_CAP)
        me = buttons.fighter_id()
        choice = scaleform.versus_side_choice(items)
        if choice is not None:
            self.player_side = choice
        elif scaleform.main_menu_selected(items):
            self.player_side = 0
        mine = scaleform.versus_my_side(items, me)
        if mine is not None:
            self.player_side = mine
        health = self.health_words()
        summary_screen, summary = scaleform.screen_summary(items, health, me, self.player_side)
        # Nothing is said about the screen until the reading is in: with it
        # inside the sentence, saying it early means saying it twice.
        if on_supplements and not self.health_settled:
            summary = None
        # A recovery being applied as the next stage starts. See HEALTH_RISE.
        if self.health_known is not None:
            level = self.health_known()
            if on_supplements or scaleform.on_battle_items(items):
                if level is not None:
                    self.health_armed, self.health_armed_at = level, now
            elif self.health_armed is not None and level is not None:
                if now - self.health_armed_at > HEALTH_RISE_WINDOW or level < self.health_armed - HEALTH_RISE:
                    self.health_armed = None
                elif level > self.health_armed + HEALTH_RISE:
                    self.health_armed = None
                    parts = (parts or []) + [f"Health now at {round(level * 100)} percent"]
        if summary_screen:
            self.summary_seen_at = now
            if not any(it.selected for it in items):
                parts, self.pending = None, None
            if (summary or "") != self.summary_pending:
                self.summary_pending, self.summary_since = summary or "", now
            # A tips screen's tip arrives whole, and can be gone in a tenth of a second.
            settle = 0.0 if scaleform.tips_screen(items)[1] else SUMMARY_SETTLE
            if summary and summary != self.summary_said:
                if now - self.summary_since >= settle:
                    # Anything selected while it settled comes after it, once:
                    # the final stage's opponent card arrives with FINAL STAGE.
                    # Left out only when it is one of the summary's own
                    # sentences: matched as part of one, the card's REWARD went
                    # missing after a score line starting "REWARD 26890".
                    sentences = {" ".join(x.split()) for x in summary.split(". ")}
                    held = [p for p in self.summary_held + (parts or [])
                            if " ".join(p.split()).rstrip(".") not in sentences and p != summary]
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
        # The bumpers move between Extra Battle's events without moving the
        # selection off BEGIN BATTLE, so a different event is named where it
        # stands, by its title alone; the read key gives the rest.
        details = scaleform.extra_battle_details(items)
        brief = scaleform.extra_battle_brief(details)
        intro, button = phrase(brief), scaleform.EXTRA_BATTLE_BUTTON
        # What marks one event as another is the whole panel bar its deadline,
        # which counts down while the same event shows. The brief alone was not
        # enough: the crossover costume events share a title, fee, difficulty
        # and conditions, and differ in their rewards further down, so moving
        # between two of them said nothing and sounded like a hang.
        held, moved_on = phrase([s for s in details if not s.startswith(scaleform.EXTRA_BATTLE_DEADLINE)]), brief[:1]
        if not intro:
            intro, button = phrase(scaleform.notice_details(items, brief=True)), scaleform.NOTICE_BUTTON
            held, moved_on = intro, [intro, button]
        if not intro:
            self.intro_said = ""
        elif held != self.intro_said:
            reached = parts and button in (p.strip() for p in parts)
            still_on = self.intro_said and any(it.selected and it.text.strip() == button for it in items)
            if reached:
                self.intro_said = held
                parts = [intro] + parts
            elif still_on:
                self.intro_said = held
                parts = moved_on

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

        # Opening Controller Setting says, once per visit, how to change the
        # button names, after the row arrived on; the user asked for it.
        if scaleform.on_controller_setting(items):
            if self.controls_arrived_at is None:
                self.controls_arrived_at, self.controls_hinted = now, False
            self.controls_seen_at = now
            if not self.controls_hinted and (parts or now - self.controls_arrived_at >= CONTROLS_HINT_WAIT):
                self.controls_hinted = True
                parts = (parts or []) + [CONTROLS_HINT]
                self.said = ""
        elif self.controls_arrived_at is not None and now - self.controls_seen_at > GROUP_MEMORY:
            self.controls_arrived_at = None

        # Redo keyboard mapping: each step's instruction as it comes, with the
        # key just assigned before it, in place of the lit row's "-". The
        # note on skipping directions is said at the first step only.
        prompt = scaleform.keyboard_prompt(items)
        if prompt is not None:
            rows = scaleform.keyboard_rows(items)
            assigned = [scaleform.key_words(new) for old, new in zip(self.mapping_rows or [], rows)
                        if old == scaleform.KEYBOARD_UNSET and new != scaleform.KEYBOARD_UNSET]
            parts = [p for p in (parts or []) if p.strip() != scaleform.KEYBOARD_UNSET]
            if prompt != self.mapping_prompt:
                parts = assigned + [scaleform.keyboard_prompt_words(prompt, self.mapping_prompt is None)]
                self.said = ""
            elif assigned:
                parts = assigned
                self.said = ""
            self.mapping_prompt, self.mapping_rows = prompt, rows
            self.keyboard_hinted = True   # the hint about Alt R would only get in the way here
        elif self.mapping_prompt is not None:
            rows = scaleform.keyboard_rows(items)
            assigned = [scaleform.key_words(new) for old, new in zip(self.mapping_rows or [], rows)
                        if old == scaleform.KEYBOARD_UNSET and new != scaleform.KEYBOARD_UNSET]
            if assigned:
                parts = assigned + (parts or [])
            self.mapping_prompt, self.mapping_rows = None, None

        # Keyboard Settings points to Alt R for its key list, once per visit.
        if scaleform.keyboard_rows(items):
            if not self.keyboard_hinted and parts:
                self.keyboard_hinted = True
                parts = parts + [scaleform.KEYBOARD_HINT]
                self.said = ""
            self.keyboard_seen_at = now
        elif self.keyboard_hinted and now - self.keyboard_seen_at > GROUP_MEMORY:
            self.keyboard_hinted = False

        # Button Preview says how to use it on opening; presses are said by the
        # app as they happen, from the controller and keyboard themselves.
        if scaleform.preview_open(items):
            # Its close hint, a text that changed with the screen, is in the
            # line below already.
            parts = [p for p in (parts or []) if p.strip() != scaleform.PREVIEW_CLOSE] or None
            if not self.preview_hinted:
                self.preview_hinted = True
                parts = (parts or []) + [scaleform.preview_hint()]
                self.said = ""
            self.preview_seen_at = now
        elif self.preview_hinted and now - self.preview_seen_at > GROUP_MEMORY:
            self.preview_hinted = False

        # A story scene's subtitles, speaker and line, as each line comes, if
        # the player has them on; never otherwise, whatever else would name them.
        line = scaleform.subtitle(items)
        if line is not None:
            parts = [p for p in (parts or []) if " ".join(p.split()) not in line] or None
            if line != self.subtitle_said and self.subtitles:
                parts = (parts or []) + [phrase(list(line))]
                self.said = ""
            self.subtitle_said = line

        # A lounge's chat selects nothing either. What is already in the log
        # on arriving is history; what appears after that is said, oldest of
        # the new entries first.
        chat = scaleform.lounge_chat(items)
        if not chat:
            self.chat_said = None
        elif self.chat_said is None:
            self.chat_said = chat[0]
        elif chat[0] != self.chat_said:
            fresh = chat[:chat.index(self.chat_said)] if self.chat_said in chat else chat[:1]
            self.chat_said = chat[0]
            parts = (parts or []) + list(reversed(fresh))

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

        # Battle Items: what the item does, a moment after its name.
        if not scaleform.on_battle_items(items):
            self.described_key, self.described_said = None, True
        elif parts:
            self.described_key, self.described_at, self.described_said = key, now, False
        elif not self.described_said and self.described_key == key and now - self.described_at >= DESCRIBE_AFTER:
            foot = scaleform.footer(items)
            self.described_said = True
            if foot is not None and not foot.selected and foot.text.strip():
                parts = [scaleform.spoken_footer(foot.text)]

        said = phrase(parts or [])
        if said and said != self.said:
            self.said = said
            return said
        return ""


SURVIVAL_CLASS = "SurvivalIterationState"
# Where a Survival run keeps the player's health between stages: the health,
# then the most it can be, both whole numbers, in memory the game does not
# describe. Found on 2026-09-28 by logging the run while the user played, and
# checked against the bar: 645 of 975 after one stage, which the bar read as
# 66 percent; back to 975 on buying Health Recovery High; 711 after the next,
# 73 percent. Beside them sit the total score (+0x400), the total before the
# last stage (+0x404) and the run's time in frames (+0x3FC).
SURVIVAL_VITAL = 0x408
SURVIVAL_VITAL_MAX = 0x40C
SURVIVAL_VITAL_LIMIT = 3000     # no fighter has anything like this much


def survival_share(raw: bytes | None) -> float | None:
    """Health as a share of the most it can be, from the run's two numbers, or None."""
    if not raw or len(raw) < 8:
        return None
    vital, most = struct.unpack_from("<2i", raw)
    if not (0 < most <= SURVIVAL_VITAL_LIMIT and 0 <= vital <= most):
        return None
    return vital / most


class SurvivalHealth:
    """Player one's health in a Survival run, read from the run itself.

    The run's game object is found once in the background, as `KeyConfig`'s
    is, and from then on a reading is one small read. Asked for away from
    Survival it finds nothing and says so once in the screen log.
    """

    def __init__(self, note=None) -> None:
        self.obj: int | None = None
        self._thread: threading.Thread | None = None
        self._note = note or (lambda text: None)
        self._last_note = ""

    def _say_once(self, text: str) -> None:
        if text != self._last_note:
            self._last_note = text
            self._note(text)

    def _current(self) -> tuple[float | None, bool]:
        """The reading, and whether the run is known; forgets a run that has gone."""
        from . import live

        session = live.shared()
        if self.obj is None or not session.attached:
            return None, False
        # Still the run, and not memory given to something else since.
        cls = session.class_address(SURVIVAL_CLASS)
        if cls is not None and session.pm.ptr(self.obj + session.objects.layout.class_private) == cls:
            return survival_share(session.pm.read(self.obj + SURVIVAL_VITAL, 8)), True
        self.obj = None
        return None, False

    def read(self) -> float | None:
        """The run's health, starting a search for the run if it is not known."""
        share, found = self._current()
        if found:
            return share
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._find, daemon=True)
            self._thread.start()
        return None

    def known(self) -> float | None:
        """The run's health if the run is known already; never starts a search."""
        return self._current()[0]

    def _find(self) -> None:
        from . import live, unreal

        session = live.shared()
        try:
            if not session.attach():
                self._say_once("survival health: could not attach to the game's objects")
                return
            for obj, _name in session.find_by_class(SURVIVAL_CLASS):
                path = unreal.full_object_path(session.pm, session.names, obj, session.objects.layout)
                if "Default__" in path:
                    continue
                self.obj = obj
                self._say_once(f"survival health: found {path} at {obj:#x}")
                return
            self._say_once("survival health: no run found")
            session.invalidate()
        except Exception as exc:
            self._say_once(f"survival health: search failed: {exc!r}")


KEY_CONFIG_CLASS = "WSKeyConfigGFxPlayer"
KEY_CONFIG_EDITED = 0x477   # the layout being edited; +0x467 holds the one the screen opened with
KEY_CONFIG_MOVIE = 0x318    # GFxMovie, set only on the instance showing


class KeyConfig:
    """The button layout the Controller Setting screen holds, edits included.

    The screen's game object has to be found among some 150,000 objects, which
    takes several seconds, so that is done once on a thread of its own, and the
    object is remembered for as long as its bytes still make sense.
    """

    def __init__(self, note=None) -> None:
        self.obj: int | None = None
        self._thread: threading.Thread | None = None
        self._note = note or (lambda text: None)
        self._last_note = ""

    def _say_once(self, text: str) -> None:
        if text != self._last_note:
            self._last_note = text
            self._note(text)

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
                self._say_once("key config: could not attach to the game's objects")
                return
            found = session.find_by_class(KEY_CONFIG_CLASS)
            for obj, name in found:
                config = session.pm.read(obj + KEY_CONFIG_EDITED, scaleform.KEY_CONFIG_FUNCTIONS + 1)
                if session.pm.ptr(obj + KEY_CONFIG_MOVIE) and scaleform.key_config_valid(config):
                    self.obj = obj
                    self._say_once(f"key config: found {name} at {obj:#x}")
                    return
            self._say_once(f"key config: {len(found)} instances, none showing with a layout"
                           + ("" if found else "; class or name not found yet, looked again after a while"))
            session.invalidate()
        except Exception as exc:
            self._say_once(f"key config: search failed: {exc!r}")


class SavedLayout:
    """Player 1's saved button layout, from the profile, for screens away from Controller Setting.

    `KWUserProfileDetails.KeyConfigData`, the struct `KWKeyConfigs`, on the
    profile the game saves (`...GameProgressSave.UserProfileDataSave.
    MainUserProfileDetails`); copies of the same object under class defaults
    hold the defaults, so the path picks the real one.
    """

    PROFILE_CLASS = "KWUserProfileDetails"

    def __init__(self, note=None) -> None:
        self.obj: int | None = None
        self.offset: int | None = None
        self._thread: threading.Thread | None = None
        self._note = note or (lambda text: None)

    def read(self) -> bytes | None:
        from . import live

        session = live.shared()
        if self.obj is not None and self.offset is not None and session.attached:
            config = session.pm.read(self.obj + self.offset, scaleform.KEY_CONFIG_FUNCTIONS + 1)
            if scaleform.key_config_valid(config):
                return config
            self.obj = None
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._find, daemon=True)
            self._thread.start()
        return None

    def _find(self) -> None:
        from . import live, unreal

        session = live.shared()
        try:
            if not session.attach():
                return
            for obj, name in session.find_by_class(self.PROFILE_CLASS, limit=64):
                if name != "MainUserProfileDetails":
                    continue
                path = unreal.full_object_path(session.pm, session.names, obj, session.objects.layout)
                if "Default__" in path:
                    continue
                prop = session.properties(obj).get("KeyConfigData")
                if prop is None:
                    continue
                self.offset, self.obj = prop.offset, obj
                self._note(f"saved layout: found {path} at {obj:#x}+{prop.offset:#x}")
                return
            self._note("saved layout: no saved profile found")
        except Exception as exc:
            self._note(f"saved layout: search failed: {exc!r}")


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
        self.last_read = "no read yet"   # what the last read did, for the hang log
        self._pictures_noted: set[str] = set()
        self._arcade_marker: str | None = None
        self._arcade_seen_at = 0.0
        self._arcade_notes = 0
        self.key_config = KeyConfig(note=self.note)
        self.key_config_bytes: bytes | None = None   # the layout at the last read of Controller Setting
        self.saved_layout = SavedLayout(note=self.note)
        self.saved_layout_bytes: bytes | None = None   # the saved layout at the last read of Keyboard Settings

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
            kind = "quick read"
            if time.monotonic() - self.reader.pages_refreshed_at > STALE_PAGES:
                self.reader.refresh_pages()
                kind = "quick read after a block refresh"
            items = self.reader.items(quick=True)
            if items:
                self._empty_since, self._use_full = None, False
            elif self._use_full:
                # Quick reads are still missing what a full search found: keep
                # searching in full, slower but not silent, until they recover.
                items = self.reader.items()
                kind = "full search"
                self._use_full = bool(items)
            elif self._seen_text:
                items = self._check_empty(now)
                kind = "empty check"
                self._use_full = bool(items)
            # What the loop's slow passes were doing, for the hang log.
            self.last_read = f"{kind}, {len(items or [])} texts"
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
                self.key_config_bytes = self.key_config.read()
                scaleform.mark_controller_buttons(items, self.key_config_bytes)
            except Exception as exc:   # the buttons are extra; the rows still read without them
                self.note(f"key config: read failed: {exc!r}")
        elif scaleform.keyboard_rows(items) or any(scaleform.PAD_MARK_OPEN in it.text for it in items):
            try:
                self.saved_layout_bytes = self.saved_layout.read()
            except Exception as exc:
                self.note(f"saved layout: read failed: {exc!r}")
        scaleform.fill_pad_marks(items, self.saved_layout_bytes)
        scaleform.name_keyboard_step(items, self.saved_layout_bytes)
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
