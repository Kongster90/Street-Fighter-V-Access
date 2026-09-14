"""What Scaleform is drawing, read straight out of the running game.

The interface is Scaleform GFx, which keeps its text and its display tree well
away from anything Unreal describes, so the object reader in `unreal.py` cannot
see it. The pixel reader rebuilds the screen from a picture. This reads the real
thing instead: each text field's exact text, where it sits, the colour it is
tinted, and which one is selected. No recognition, so no misreadings, and it
does not need the game in front.

How it is found, all confirmed against this build:

- Every text field owns a DocView, whose first eight bytes point at its class's
  function table inside the executable. That address is the same for every
  DocView, so sweeping the heap for it finds every text field at once.
  Scaleform allocates from small read-write pages, about 360 MB of them, and
  the sweep takes a third of a second.
- The DocView holds the StyledText, which holds the paragraphs, each a pointer
  to UTF-16 text and a length that counts the terminator.
- The DocView also points at a listener, and 0x98 bytes before the listener
  sits a pointer back to the text field that owns it. On the main menu the
  listener happens to live inside the field, 0x2F0 in, and the first version
  of this reader relied on that. Dialogs, the header and the profile panel
  allocate it separately, anywhere up to megabytes away, which is why the Exit
  prompt read as nothing. From the field, every display object points at its
  parent and at its render node, and the node's data holds a 2 by 4 transform
  in twips and a colour transform. Each also keeps an array of its children,
  sixteen bytes an entry, with the count beside it.
- Multiplying the transforms and colours from the field up to the root gives
  the position on the 1920 by 1080 stage and the tint the text is drawn with.

Two ways of marking a selection, each found by recording memory while the user
moved and keeping what followed the selection:

- A menu entry is tinted by the multiplier 1.0, 0.89, 0.549, which is RGB 255,
  227, 140, the gold the pixel reader already looks for. Unselected entries on
  the main menu sit at 0.27 grey.
- A dialog's buttons are not tinted. The selected one is drawn with a gold
  outline and a dark fill, which in memory is four more children on the
  button, with its label moved one level further down inside them. The
  labels themselves stay plain, so the choice is read off the buttons'
  structure by comparing each with its neighbours.

DocViews from screens that have closed stay in the heap until overwritten. They
fail the walk to a render node, or come out detached, hidden or transparent,
and are dropped unless asked for. Hidden means a parent's render node has its
visible bit clear. The text field's own bit does not count: it is clear on the
Exit prompt's question while the question is on screen, whereas a date line
that never shows on the main menu is hidden by the container above it.
"""

from __future__ import annotations

import json
import math
import re
import struct
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .memory import ProcessMemory, find_pid

EXE = "StreetFighterV.exe"
GAME_PATH_HINT = r"Binaries\Win64"

# Function tables, as offsets into the executable.
DOCVIEW_VTABLE = 0x34C8568
STYLED_TEXT_VTABLE = 0x34C8530

# Field offsets, 64-bit.
DOCVIEW_TEXT = 0x10          # StyledText*
DOCVIEW_LISTENER = 0x20      # listener belonging to the owning text field
DOCVIEW_SIZE = 0x88          # two floats, the text box's width and height in twips
LISTENER_OWNER = -0x98       # pointer to that field, relative to the listener
TEXT_PARAGRAPHS = 0x18       # array of Paragraph*
TEXT_PARAGRAPH_COUNT = 0x20
PARAGRAPH_CHARS = 0x00       # UTF-16 text, then its length counting the terminator
PARAGRAPH_SIZE = 0x08
PARAGRAPH_RUNS = 0x20        # format runs: start, length, TextFormat*, each 0x18 bytes
PARAGRAPH_RUN_COUNT = 0x28
RUN_STRIDE = 0x18
FORMAT_IMAGE = 0x30          # the picture drawn in place of the run's character, if any
IMAGE_URL = 0x50             # String, a pointer tagged in its low two bits
STRING_SIZE = 0x00           # its data: length (top bit a flag), refcount, then the chars
STRING_CHARS = 0x0C
MAX_RUNS = 64
DISPLAY_PARENT = 0x38
DISPLAY_RENDER_NODE = 0x48
DISPLAY_CHILDREN = 0xD8      # array of children, an object pointer per entry
DISPLAY_CHILD_COUNT = 0xE0
DISPLAY_CHILD_STRIDE = 16
RENDER_NODE_DATA = 0x10
NODE_FLAGS = 0x0A            # u16; bit 0 set while visible, for parents at least
NODE_MATRIX = 0x10           # 2 by 4 floats: sx, shx, 0, tx / shy, sy, 0, ty
NODE_CXFORM = 0x50           # multiply r, g, b, a then add r, g, b, a
NODE_BOUNDS = 0x70           # two rectangles of four floats, its approximate bounds

NODE_VISIBLE = 0x0001
# A movie's root carries these in its flag word, 0x1801 while showing and
# 0x1800 while hidden. A screen that closes can leave a subtree cut loose from
# its movie with its render state intact: after each Versus match the previous
# result screen stayed behind whole, looking shown, and was read in place of the
# new one. Its top object has no parent and flags of 0 or 1. In the recordings
# every one of 6,105 texts on screen hung from a root with these bits.
MOVIE_ROOT_FLAGS = 0x1800
TWIPS_PER_PIXEL = 20.0
STAGE_WIDTH, STAGE_HEIGHT = 1920, 1080

HIGHLIGHT_TINT = (1.0, 0.89, 0.549)
TINT_TOLERANCE = 0.05
UNAVAILABLE_GREY = 0.6

# Labels longer than this are not answers on a button. It keeps the choice rule
# off the banner, whose date line and title sit side by side like two buttons.
CHOICE_TEXT_LIMIT = 24
# A prompt's chosen button has its outline and fill as extra children, six in
# all, with its label inside a layer, two levels under the row holding it.
CHOSEN_BUTTON_CHILDREN = 6
LONE_BUTTON_NESTING = 2
# A grid's selected tile has to be this much brighter, as the sum of its red,
# green and blue times its alpha, than the next brightest. The Favorite
# Character grid gives 3.0 against 2.25. Its text box must also be the same
# size as most of the others', which a heading above a list of entries is not.
BRIGHT_GROUP_MIN = 3
BRIGHTNESS_MARGIN = 0.3

# Layout placeholders the game leaves in its templates, such as the run of
# lower-case w inside every prompt and the capital Ws on the Training loading
# screen. They are never drawn, and their render state cannot tell them apart
# from the prompt's question, whose own node is marked hidden in just the same
# way while it shows. So they are recognised by what they say.
PLACEHOLDER_MIN_LENGTH = 8
PLACEHOLDER_W_SHARE = 0.8


def is_placeholder(text: str) -> bool:
    letters = [c for c in text if not c.isspace()]
    if len(letters) < PLACEHOLDER_MIN_LENGTH:
        return False
    return sum(c in "wW" for c in letters) >= PLACEHOLDER_W_SHARE * len(letters)

# The line describing the selected entry, which every menu with the shared
# footer draws at (110, 992).
FOOTER_TOP = 960
FOOTER_RIGHT = 400
# More changed text than this at once is a new screen, not a move onto one thing.
MOVE_TEXT_LIMIT = 3

PAGE_READWRITE = 0x04
# Scaleform's pages are all well under this. Larger read-write regions are
# engine and driver allocations with nothing of the interface in them.
HEAP_PAGE_LIMIT = 0x100000
# Scaleform takes memory from the system in whole 64 KB chunks plus one 4 KB
# page: 0x11000, 0x21000, 0x31000. Every text field seen lives in a block of
# that shape, and there are only several hundred, about 70 MB against 360 MB
# for every page, so a quick read sweeps those alone.
SCALEFORM_CHUNK = 0x10000
SCALEFORM_EXTRA = 0x1000
# How often to walk the address space for blocks Scaleform has newly taken.
PAGE_REFRESH = 1.0

MAX_PARAGRAPHS = 512
MAX_PARAGRAPH_CHARS = 4096
MAX_DEPTH = 40
MAX_CHILDREN = 4096


@dataclass
class TextItem:
    text: str
    x: float                 # stage pixels, the text field's origin
    y: float
    tint: tuple[float, float, float, float]   # effective colour multiplier
    depth: int               # the field plus each parent above it
    docview: int = 0
    chain: tuple[int, ...] = ()   # the field, then each parent up to the root
    chosen: bool = False     # the selected button of a group, by structure
    group: int = 0           # the container holding that group of buttons
    hidden: bool = False     # a parent is switched off
    box: tuple[float, float] = (0.0, 0.0)   # the text box's width and height in pixels
    slot: int = 0            # the picture tile this text names, when it names one
    ticked: bool | None = None   # a checklist entry's box, when it has one
    rooted: bool = True      # the chain ends at a movie's root, not a subtree cut loose from one

    @property
    def highlighted(self) -> bool:
        return all(abs(c - h) <= TINT_TOLERANCE for c, h in zip(self.tint, HIGHLIGHT_TINT))

    @property
    def selected(self) -> bool:
        return self.highlighted or self.chosen

    @property
    def unavailable(self) -> bool:
        """Drawn in the plain 0.6 grey this interface gives what cannot be chosen:
        songs in the menu music list that are not yours, and Replay Saved
        Status in the Training pause menu before there is a replay."""
        r, g, b, _a = self.tint
        return abs(r - UNAVAILABLE_GREY) <= TINT_TOLERANCE and abs(r - g) < 0.02 and abs(r - b) < 0.02

    @property
    def on_stage(self) -> bool:
        return 0 <= self.x < STAGE_WIDTH and 0 <= self.y < STAGE_HEIGHT

    @property
    def shown(self) -> bool:
        """Attached to a movie, not hidden, not transparent, on the stage, and real text."""
        return (
            self.depth >= 2
            and self.rooted
            and not self.hidden
            and self.tint[3] > 0.01
            and self.on_stage
            and bool(self.text.strip())
            and not is_placeholder(self.text)
        )


def footer(items: list[TextItem]) -> TextItem | None:
    """The description line under the menu, if this screen has one."""
    return next((it for it in items if it.y >= FOOTER_TOP and it.x < FOOTER_RIGHT), None)


def selection_key(items: list[TextItem]):
    """What changes when the cursor moves, and does not change on its own.

    The selected text is the usual sign. It is not enough by itself: the main
    menu's icon row, Options, Gallery, Message Log, Login and Exit, carries no
    text, so moving along it selects nothing readable. The description line
    changes either way, while the adverts that rotate in the banner change
    neither.
    """
    foot = footer(items)
    return (
        tuple((it.text, it.slot, it.ticked) for it in items if it.selected),
        foot.text if foot else None,
    )


def _where(it: TextItem):
    # The tile counts as well as the text: two locked stages side by side are
    # both named "???", and moving between them is still a move.
    return (round(it.x), round(it.y), it.text, it.slot)


def _unique(texts: list[str]) -> list[str]:
    """Each text once, in order. Some screens draw a title in three layers."""
    seen = set()
    return [t for t in texts if not (t in seen or seen.add(t))]


def landed_on(
    before: list[TextItem], after: list[TextItem], recent_groups: frozenset = frozenset()
) -> list[str]:
    """What to say for a move from the `before` screen to the `after` one.

    Whatever has newly become selected. Only newly: a prompt opened from the
    Training pause menu leaves Go to Main Menu gold behind it, and that is not
    news. When a group of buttons appears that was not there before, the rest
    of the panel holding it comes first, which is how a prompt's question gets
    read as it opens. The question can appear a moment before its buttons, so
    it is read whether or not it is new; the other buttons are left out.

    With nothing newly selected, silence if something still is, or if a prompt
    has just closed: the button hints that come back then are not a move.
    Otherwise the text that changed with the move, which is how an icon gets
    its name: the banner switches to OPTIONS or EXIT as the icon is reached.
    Failing that, the description line, but only if it changed. Between one
    button losing the selection and the next gaining it, neither label exists
    for a moment, and that is not worth saying anything about.

    `recent_groups` are button groups a caller has seen lately. A read that
    lands in that moment between buttons would otherwise make the prompt look
    newly opened on the next move, and its question would be read again.
    """
    old = {_where(it) for it in before}
    was_lit = {_where(it): it.ticked for it in before if it.selected}
    lit = [it for it in after if it.selected]
    # Ticking the entry you are on changes nothing but its box, so that is
    # said on its own, without the name you already heard.
    toggled = [it for it in lit if _where(it) in was_lit and it.ticked is not None
               and was_lit[_where(it)] is not None and was_lit[_where(it)] != it.ticked]
    if toggled:
        return [tick_word(it.ticked) for it in toggled[:1]]
    fresh = [it for it in lit if _where(it) not in was_lit]
    if fresh:
        old_groups = {it.group for it in before if it.chosen} | set(recent_groups)
        new_groups = {it.group for it in fresh if it.chosen and it.group not in old_groups}
        panels = set()
        for it in fresh:
            if it.group in new_groups and it.group in it.chain:
                at = it.chain.index(it.group)
                if at + 1 < len(it.chain):
                    panels.add(it.chain[at + 1])
        intro = [
            it.text
            for it in after
            if not it.selected
            and panels.intersection(it.chain)
            and not new_groups.intersection(it.chain)
        ]
        named = []
        seen = set(intro)
        for it in fresh:
            if it.text in seen:
                continue
            seen.add(it.text)
            named.append(it.text)
            if it.unavailable:
                named.append("Unavailable")   # its tick cannot be changed, so it goes unsaid
            elif it.ticked is not None:
                named.append(tick_word(it.ticked))
        return _unique(intro) + named
    if lit or recent_groups or any(it.chosen for it in before):
        return []
    foot = footer(after)
    changed = [it.text for it in after if it is not foot and _where(it) not in old]
    if 0 < len(changed) <= MOVE_TEXT_LIMIT:
        return _unique(changed)
    was = footer(before)
    if foot and (was is None or was.text != foot.text):
        return [foot.text]
    return []


# ------------------------------------------------------------------ checklists
#
# The menu music list is a checklist. Each song's row holds four parts: its
# background, the highlight bar, the holder of its name, and to the left of
# the name a tick box. The box holds two parts, the second of which holds
# three when the song is ticked and two when it is not: the tick itself is
# removed. Recorded while one song was unticked and ticked back and the whole
# list was unticked and ticked again, with the screenshots agreeing each time.

TICKED_PARTS = 3
UNTICKED_PARTS = 2
CHECKLIST_SAMPLE = 12


def tick_word(ticked: bool) -> str:
    return "Ticked" if ticked else "Not ticked"


def _tick_box(children, parts, skip=None):
    """A row's tick box and the part inside it that holds the tick, if it has one.

    The shape is common, a bare shape and a holder, and the Sound Settings tabs
    and volume rows have it too. What sets the tick box apart is inside the
    holder: two bare shapes, the box itself, and when ticked a third part with
    something in it, the tick.
    """
    for part in parts:
        if part == skip:
            continue
        inside = children(part)
        if len(inside) != 2 or children(inside[0]):
            continue
        marks = children(inside[1])
        if len(marks) not in (TICKED_PARTS, UNTICKED_PARTS):
            continue
        if children(marks[0]) or children(marks[1]):
            continue
        if len(marks) == TICKED_PARTS and not children(marks[2]):
            continue
        return part, inside[1]
    return None


def tick_state(children, x_of, chain) -> bool | None:
    """Whether the checklist entry whose label has this chain is ticked.

    None unless the label's row has a tick box to the left of the label, and
    at least two other rows in the same list have one too, so a row that
    merely happens to be built alike on some other screen is not read as a
    checklist.
    """
    if len(chain) < 4:
        return None
    holder, row, rows = chain[1], chain[2], chain[3]
    found = _tick_box(children, children(row), skip=holder)
    if found is None:
        return None
    box, marks = found
    box_x, label_x = x_of(box), x_of(holder)
    if box_x is None or label_x is None or box_x >= label_x:
        return None
    alike = sum(
        1 for other in children(rows)[:CHECKLIST_SAMPLE]
        if other != row and _tick_box(children, children(other)) is not None
    )
    if alike < 2:
        return None
    return len(children(marks)) == TICKED_PARTS


# ----------------------------------------------------------------- picture grids
#
# The Favorite Stage grid is pictures: eighteen tiles of seven parts each, with
# no text on any of them, and a label under the grid naming the stage the
# cursor is on. On the selected tile the picture is at full brightness and a
# yellow outline is switched on; on every other tile the picture is dimmed to
# 0.4 and the outline is off. The label is the nearest text to the grid in the
# display tree, five levels apart, where the category tab above is seven.
#
# These work on callables rather than on the reader so a recording can be
# replayed through them: `children(obj)` lists an object's children, and
# `appearance(obj)` gives its own colour multiplier and flag word, or None.

GRID_MIN_TILES = 4
SHORT_LIST_ROWS = 2   # a list's highlight bar is read from this many rows, strictly below four
# The pause menu's Command List, recognised by its note, and its move rows:
# sixteen parts in play, each part a background and a holder.
COMMAND_LIST_NOTE = "All commands assume the character is facing right."
MOVE_ROW_MIN_PARTS = 8
MOVE_ROW_PART_CHILDREN = 2
GRID_SEARCH_LIMIT = 6000
# The walk runs on the thread that keeps the block list current, so it must not
# run long. While a screen is torn down its objects can point into garbage, and
# an unbounded walk stalled that thread: back on stage select after character
# select, its text sat in new blocks the list never learned about, and memory
# narration went silent.
GRID_WALK_SECONDS = 0.25
GRID_NAME_REACH = 6


def _remembering(children):
    """`children`, reading each object's list once however often it is asked."""
    known: dict[int, list[int]] = {}

    def kids(obj):
        if obj not in known:
            known[obj] = children(obj)
        return known[obj]

    return kids


def grid_tiles(children, obj, minimum: int = GRID_MIN_TILES) -> list[int]:
    """The tiles of `obj` if it is a grid: `minimum` or more children with the same number of parts."""
    inside = children(obj)
    if len(inside) < minimum:
        return []
    parts = [len(children(k)) for k in inside]
    usual = max(set(parts), key=parts.count)
    tiles = [k for k, n in zip(inside, parts) if n == usual]
    return tiles if usual >= 2 and len(tiles) >= minimum else []


def find_grids(children, roots, limit: int = GRID_SEARCH_LIMIT,
               seconds: float = GRID_WALK_SECONDS) -> dict[int, list[int]]:
    """Containers holding four or more tiles built alike, by number of parts."""
    kids = _remembering(children)
    grids = {}
    stack = list(roots)
    seen = set()
    deadline = time.monotonic() + seconds
    while stack and len(seen) < limit and time.monotonic() < deadline:
        obj = stack.pop()
        if obj in seen:
            continue
        seen.add(obj)
        stack.extend(kids(obj))
        tiles = grid_tiles(kids, obj)
        if tiles:
            grids[obj] = tiles
    return grids


def selected_tile(children, appearance, tiles) -> int | None:
    """The one tile drawn differently from all the others, if it is the brighter."""
    looks = {}
    for tile in tiles:
        parts = []
        for part in children(tile):
            seen = appearance(part)
            parts.append(None if seen is None else (round(seen[0][0], 2), round(seen[0][3], 2), seen[1] & NODE_VISIBLE))
        looks[tile] = tuple(parts)
    kinds = sorted(set(looks.values()), key=lambda k: list(looks.values()).count(k), reverse=True)
    if len(kinds) != 2:
        return None
    usual, odd = kinds
    tally = list(looks.values())
    if tally.count(odd) != 1 or tally.count(usual) < GRID_MIN_TILES - 1:
        return None

    def presence(look):
        return sum(p[0] * p[1] + p[2] for p in look if p is not None)

    if presence(odd) <= presence(usual):
        return None
    return next(tile for tile, look in looks.items() if look == odd)


def highlighted_row(children, appearance, rows) -> int | None:
    """The one row of a list whose highlight bar is switched on.

    In the menu music list every row has the same parts, and the second, the
    highlight bar, is visible on the row the cursor is on and hidden on every
    other. The songs that cannot be chosen are never gold, so this is the only
    sign of the cursor on them. Only visibility is compared, part by part,
    since the rows also differ in tint: some names are grey and some are not.

    A short list, two or three rows, is held to more: every part but one must
    be alike in visibility on every row. The command list's Normal Throw
    section has two moves, sixteen parts a row, and only the third part, on
    only the row the cursor is on, differs; with so few rows, any one part
    that happens to differ would otherwise be taken for the cursor.
    """
    if len(rows) < SHORT_LIST_ROWS:
        return None
    parts = [children(row) for row in rows]
    width = len(parts[0])
    if width < 2 or any(len(p) != width for p in parts):
        return None
    looks = []
    for index in range(width):
        shown = []
        for row, row_parts in zip(rows, parts):
            seen = appearance(row_parts[index])
            if seen is None:
                break
            shown.append(bool(seen[1] & NODE_VISIBLE))
        else:
            looks.append(shown)
            continue
        looks.append(None)
    if len(rows) < GRID_MIN_TILES:
        differing = [shown for shown in looks if shown is None or len(set(shown)) > 1]
        if len(differing) != 1 or differing[0] is None or differing[0].count(True) != 1:
            return None
        return rows[differing[0].index(True)]
    for shown in looks:
        if shown is not None and shown.count(True) == 1:
            return rows[shown.index(True)]
    return None


def name_for_grid(grid_and_parents: list[int], items: list[TextItem]) -> TextItem | None:
    """The shown text nearest a grid in the display tree, within reach."""
    best = None
    for it in items:
        if not it.shown or grid_and_parents[0] in it.chain:
            continue
        for level, obj in enumerate(it.chain):
            if obj in grid_and_parents:
                distance = level + grid_and_parents.index(obj)
                if distance <= GRID_NAME_REACH and (best is None or distance < best[0]):
                    best = (distance, it)
                break
    return best[1] if best else None


# ----------------------------------------------------------------- stage select
#
# Stage select shows one stage at a time, so nothing on it is gold or otherwise
# selected, and narration that waits for a selection to move said nothing. The
# screen names itself by its conditions, each a label and value in one text:
# "Weather | Clear", "Time | 10:30", "Temperature | 77°F". The stage name is
# drawn twice beside them, and the heading twice above. Of the other texts, the
# stage is the one nearest the conditions in the display tree.

STAGE_CONDITIONS = ("Weather", "Time", "Temperature")
STAGE_CONDITION_MARK = "|"


def stage_condition(text: str) -> tuple[str, str] | None:
    """("Time", "10:30") for a stage condition's text, else None."""
    label, mark, value = text.partition(STAGE_CONDITION_MARK)
    if not mark or label.strip() not in STAGE_CONDITIONS:
        return None
    return label.strip(), value.strip()


def _tree_distance(a: tuple[int, ...], b: tuple[int, ...]) -> int | None:
    """Steps from one object up to the nearest ancestor they share, and down to the other."""
    at = {obj: level for level, obj in enumerate(b)}
    for level, obj in enumerate(a):
        if obj in at:
            return level + at[obj]
    return None


def stage_on_offer(items: list[TextItem]) -> TextItem | None:
    """The stage name on stage select, or None if this is not that screen."""
    shown = [it for it in items if it.shown]
    conditions = [it for it in shown if stage_condition(it.text)]
    if len({stage_condition(it.text)[0] for it in conditions}) < 2:
        return None
    best = None
    for it in shown:
        if stage_condition(it.text) or not it.text.strip():
            continue
        for condition in conditions:
            distance = _tree_distance(it.chain, condition.chain)
            if distance is not None and (best is None or distance < best[0]):
                best = (distance, it)
    return best[1] if best else None


def stage_details(items: list[TextItem]) -> list[str]:
    """Each stage condition as a phrase, leaving out ones not yet known.

    An unset condition shows as a question mark, and "Weather question mark" is
    worse than saying nothing. The degree sign is put in words, since a screen
    reader may say it as a symbol or not at all.
    """
    out = []
    for it in items:
        found = stage_condition(it.text) if it.shown else None
        if not found:
            continue
        label, value = found
        value = " ".join(value.replace("°", " degrees ").split())
        if value and value not in ("?", "-"):
            out.append(f"{label} {value}")
    return _unique(out)


# ------------------------------------------------------------- character select
#
# Character select's roster is pictures, and nothing memory can see marks the
# cursor on it. What follows the cursor is the fighter's name in the side
# panel, drawn once and then twice more in layers, and the other side's name
# likewise: moving through the roster in the log went CODY, ZEKU, KOLIN, URIEN,
# BLANKA, LUCIA with nothing selected. So on that screen the names are the
# selection, and a move is a name changing. The screen is recognised by its
# heading, and a name by being one of the fighters the game has.
#
# Nothing else in that screen's movie counts as selected unless it is gold.
# The cursor tags, "1P", "2P" and "CPU", sit in a holder beside the heading's,
# deeper and with more children, and while only one tag shows the pair has the
# shape of a prompt's two buttons with the tag chosen. So moves said "CPU.
# Unavailable" whenever player one's blinking tag was off, "1P" or "2P" in a
# two player match, and "CPU" after each name while picking the CPU's fighter.
# The costume and version panels that follow a pick are gold, and read as any
# menu does.

CHARACTER_SELECT_HEADING = "CHARACTER SELECT"
ROSTER_FILE = Path(__file__).resolve().parent.parent / "character_names.json"
_fighters: frozenset[str] | None = None


def fighter_names() -> frozenset[str]:
    """Every fighter's name as the game writes it, from the roster recovered from its files."""
    global _fighters
    if _fighters is None:
        try:
            data = json.loads(ROSTER_FILE.read_text(encoding="utf-8"))
            _fighters = frozenset(data["names"].values())
        except (OSError, ValueError, KeyError, AttributeError):
            _fighters = frozenset()
    return _fighters


def mark_fighters(items: list[TextItem]) -> None:
    """On character select, make the fighters' names the selection and nothing else there.

    Gold is left alone, and so is anything in another movie, such as a prompt
    drawn over the screen.
    """
    shown = [it for it in items if it.shown]
    heading = next((it for it in shown if it.text.strip() == CHARACTER_SELECT_HEADING), None)
    if heading is None:
        return
    movie = heading.chain[-1] if heading.chain else None
    names = fighter_names()
    for it in shown:
        if it.text.strip() in names:
            it.chosen = True
        elif it.chosen and it.chain and it.chain[-1] == movie:
            it.chosen, it.group, it.slot = False, 0, 0


# ---------------------------------------------------------------- match result
#
# After a Versus match the result screen gives each side a column of its own:
# the player ("PLAYER 1", "CPU"), "WIN" or "LOSE" drawn in layers, and "Wins"
# and "Win Streak", each holding its number beside it. Below, outside either
# column, are "Win Ratio" and two percentages whose positions do not say whose
# is whose: after player one won the first match of a session, "0.00%" was
# drawn left of "100.00%". So a percentage goes to the side whose wins it
# agrees with, and is left unsaid if neither assignment agrees.
#
# The columns animate in over about ten seconds before the Results Menu, the
# first thing on the screen that is really selected. A fading copy of "LOSE"
# was taken for a selection meanwhile and read out as the result when player
# one had won, so only gold counts on that screen.

RESULT_HEADING = "RESULT"
RESULT_OUTCOMES = ("WIN", "LOSE")
RESULT_VERBS = {"WIN": "wins", "LOSE": "loses"}
# Said first whichever side won and wherever it stands, at the user's request.
RESULT_PLAYER_ONE = "PLAYER 1"
RESULT_WINS = "Wins"
RESULT_STREAK = "Win Streak"
RATIO_TOLERANCE = 0.01   # the game shows two decimals
_WHOLE_NUMBER = re.compile(r"^\d+$")
_PERCENTAGE = re.compile(r"^(\d+(?:\.\d+)?)%$")


def _results_movie(shown: list[TextItem]) -> int | None:
    """The movie showing a match result, or None if this is not that screen."""
    heading = next((it for it in shown if it.text.strip() == RESULT_HEADING and it.chain), None)
    if heading is None:
        return None
    movie = heading.chain[-1]
    if not any(it.text.strip() in RESULT_OUTCOMES and it.chain and it.chain[-1] == movie for it in shown):
        return None
    return movie


def on_results(items: list[TextItem]) -> bool:
    return _results_movie([it for it in items if it.shown]) is not None


def mark_results(items: list[TextItem]) -> None:
    """On the result screen, nothing in its movie is selected unless it is gold."""
    shown = [it for it in items if it.shown]
    movie = _results_movie(shown)
    for it in shown:
        if movie is not None and it.chosen and it.chain and it.chain[-1] == movie:
            it.chosen, it.group, it.slot = False, 0, 0


def _percent_words(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def result_summary(items: list[TextItem]) -> str | None:
    """The result and both sides' records, player one first, once all of them are showing.

    "PLAYER 1 loses. Wins 2 to 1. Win streak 0 to 1. Win ratio 66.67 to 33.33 percent."
    None away from the result screen, and while its columns are still arriving.
    """
    shown = [it for it in items if it.shown]
    movie = _results_movie(shown)
    if movie is None:
        return None
    shown = [it for it in shown if it.chain and it.chain[-1] == movie]
    outcomes: dict[tuple[int, int], TextItem] = {}
    for it in shown:
        if it.text.strip() in RESULT_OUTCOMES:
            outcomes.setdefault((round(it.x), round(it.y)), it)
    sides = sorted(outcomes.values(), key=lambda it: it.x)
    if len(sides) != 2:
        return None

    def side_of(it: TextItem) -> int | None:
        """The side whose outcome is nearest in the tree; None if both are as near."""
        near = [(d, i) for i, side in enumerate(sides)
                if (d := _tree_distance(it.chain, side.chain)) is not None]
        if not near:
            return None
        best = min(near)
        return best[1] if [d for d, _i in near].count(best[0]) == 1 else None

    players: list[tuple[int, str] | None] = [None, None]
    wins: list[int | None] = [None, None]
    streaks: list[int | None] = [None, None]
    known = {RESULT_HEADING, RESULT_WINS, RESULT_STREAK, *RESULT_OUTCOMES}
    for it in shown:
        text = it.text.strip()
        if text in (RESULT_WINS, RESULT_STREAK):
            side = side_of(it)
            value = next((v.text.strip() for v in shown
                          if v is not it and len(v.chain) > 1 and len(it.chain) > 1
                          and v.chain[1] == it.chain[1] and _WHOLE_NUMBER.match(v.text.strip())), None)
            if side is not None and value is not None:
                (wins if text == RESULT_WINS else streaks)[side] = int(value)
        elif text and text not in known and not _WHOLE_NUMBER.match(text) and not _PERCENTAGE.match(text):
            side = side_of(it)
            if side is not None:
                distance = _tree_distance(it.chain, sides[side].chain)
                if players[side] is None or distance < players[side][0]:
                    players[side] = (distance, text)
    if None in players or None in wins or None in streaks:
        return None

    ratio = None
    percentages = {(round(it.x), round(it.y)): float(m[1])
                   for it in shown if (m := _PERCENTAGE.match(it.text.strip()))}
    if len(percentages) == 2:
        a, b = percentages.values()
        total = wins[0] + wins[1]
        if a == b:
            ratio = (a, b)
        elif total:
            expected = 100 * wins[0] / total
            if abs(a - expected) <= RATIO_TOLERANCE and abs(b - (100 - expected)) <= RATIO_TOLERANCE:
                ratio = (a, b)
            elif abs(b - expected) <= RATIO_TOLERANCE and abs(a - (100 - expected)) <= RATIO_TOLERANCE:
                ratio = (b, a)

    results = [side.text.strip() for side in sides]
    names = [player[1] for player in players]
    first = names.index(RESULT_PLAYER_ONE) if RESULT_PLAYER_ONE in names else 0
    second = 1 - first
    if sorted(results) == ["LOSE", "WIN"]:
        parts = [f"{names[first]} {RESULT_VERBS[results[first]]}"]
    else:
        parts = [f"{names[i]} {RESULT_VERBS.get(results[i], results[i].lower())}" for i in (first, second)]
    parts.append(f"Wins {wins[first]} to {wins[second]}")
    parts.append(f"Win streak {streaks[first]} to {streaks[second]}")
    if ratio is not None:
        parts.append(f"Win ratio {_percent_words(ratio[first])} to {_percent_words(ratio[second])} percent")
    return ". ".join(parts) + "."


# ------------------------------------------------------------------- VS screen
#
# Before each fight the VS screen shows, in one panel, both fighters' names
# (drawn once and then in layers), each side's V-Skill and V-Trigger as label
# and value ("II - BIRDIE TIME") in a holder of their own, the stage's name
# alone directly in the panel, and player one's level, LP, rank and title.
# Nothing on it is selected, so it was silent. Version select shows both
# sides' V-Skill and V-Trigger too, under its heading and with a gold row.
#
# The user asked for the opponent and their version numbers, not names, and
# the stage. The opponent is the right-hand side: player one was on the left
# in Arcade, Versus and Training alike.

ARCADE_FINAL_STAGE = "FINAL STAGE"
PATH_SELECT_PROMPT = "Please select a path."
VERSUS_LABELS = ("V-Skill", "V-TRIGGER")
VERSUS_WORDS = {"V-Skill": "V-Skill", "V-TRIGGER": "V-Trigger"}
VERSION_NUMERALS = {"I": 1, "II": 2, "III": 3}
VERSION_SELECT_HEADING = "VERSION SELECT"
STRINGS_FILE = Path(__file__).resolve().parent.parent / "strings.json"
_game_strings: frozenset[str] | None = None


def game_strings() -> frozenset[str]:
    """Every string the game can display, from its own localisation table."""
    global _game_strings
    if _game_strings is None:
        try:
            _game_strings = frozenset(json.loads(STRINGS_FILE.read_text(encoding="utf-8"))["strings"].values())
        except (OSError, ValueError, KeyError, AttributeError):
            _game_strings = frozenset()
    return _game_strings


def _versus_panel(shown: list[TextItem]) -> int | None:
    """The panel holding the VS screen, or None if this is not that screen."""
    if any(it.highlighted or it.text.strip() in (CHARACTER_SELECT_HEADING, VERSION_SELECT_HEADING)
           for it in shown):
        return None
    labels = [it for it in shown if it.text.strip() in VERSUS_LABELS and it.chain]
    if sorted(it.text.strip() for it in labels) != sorted(VERSUS_LABELS * 2):
        return None
    common = set(labels[0].chain)
    for it in labels[1:]:
        common &= set(it.chain)
    return next((obj for obj in labels[0].chain if obj in common), None)


def mark_versus(items: list[TextItem]) -> None:
    """On the VS screen, nothing in its panel is selected."""
    shown = [it for it in items if it.shown]
    panel = _versus_panel(shown)
    for it in shown:
        if panel is not None and it.chosen and panel in it.chain:
            it.chosen, it.group, it.slot = False, 0, 0


def versus_summary(items: list[TextItem]) -> str | None:
    """"Opponent, ABIGAIL, V-Skill 1, V-Trigger 1. Metro City Bay Area." on the VS screen.

    None away from it, and until both fighters' names show. A version whose
    value does not start with a numeral is said by name; a stage that is not
    one text alone in the panel, and a string the game has, is left out.
    """
    shown = [it for it in items if it.shown]
    panel = _versus_panel(shown)
    if panel is None:
        return None
    names = fighter_names()
    fighters = sorted((it for it in shown if it.text.strip() in names and panel in it.chain), key=lambda it: it.x)
    if not fighters or fighters[-1].x - fighters[0].x < STAGE_WIDTH / 4:
        return None
    parts = [f"Opponent, {fighters[-1].text.strip()}"]
    for label in VERSUS_LABELS:
        right = max((it for it in shown if it.text.strip() == label), key=lambda it: it.x)
        value = next((v.text.strip() for v in shown
                      if v is not right and len(v.chain) > 1 and len(right.chain) > 1
                      and v.chain[1] == right.chain[1] and v.text.strip()), None)
        if value is None:
            continue
        numeral = value.partition(" - ")[0].strip()
        parts.append(f"{VERSUS_WORDS[label]} {VERSION_NUMERALS.get(numeral, value)}")
    sentence = ", ".join(parts)
    known = game_strings()
    stages = [it.text.strip() for it in shown
              if len(it.chain) > 1 and it.chain[1] == panel and it.text.strip() in known
              and it.text.strip() not in names and it.text.strip() not in VERSUS_LABELS]
    if len(set(stages)) == 1:
        sentence += f". {stages[0]}"
    return sentence + "."


# ---------------------------------------------------------------- arcade ending
#
# An Arcade run ends on artwork with a caption: a title naming the path and
# fighter ("SFI Ryu") and above nothing else a paragraph of story, both in one
# panel, and nothing else on screen. Nothing is selected, so it was silent.
# Among every logged screen only these and a moment of the main menu showed so
# little with a paragraph in it, and there the paragraph is the menu's
# description line at the foot of the screen.

ENDING_TITLE_MAX = 40
ENDING_CAPTION_MIN = 60
ENDING_REACH = 4
# The title starts with the path's game, SFI, SFII, SFIII, SFIV or SFV (and
# Alpha's, if it follows the pattern), which the user asked to leave unsaid.
ENDING_PATH = re.compile(r"^SF[IVXAZ]*\s+")
# Unlocked pictures follow, each credited alone on screen: "Special Artwork:
# BENGUS", or "SF Legacy: Street Fighter IV Artwork". The game has 57 such
# strings, all with this word in them.
ENDING_ARTWORK = "Artwork"


def ending_summary(items: list[TextItem]) -> str | None:
    """"Ryu. The young challenger Ryu stands before..." on an Arcade ending, else None.

    Or an unlocked picture's credit, the only text on screen and one of the
    game's own artwork strings: "Special Artwork: BENGUS".
    """
    shown = [it for it in items if it.shown]
    if len(shown) == 1:
        credit = shown[0].text.strip()
        return credit if ENDING_ARTWORK in credit and credit in game_strings() else None
    if len(shown) != 2:
        return None
    title, caption = sorted(shown, key=lambda it: len(it.text.strip()))
    if len(title.text.strip()) > ENDING_TITLE_MAX or len(caption.text.strip()) < ENDING_CAPTION_MIN:
        return None
    if caption is footer(shown) or title.y >= caption.y:
        return None
    distance = _tree_distance(title.chain, caption.chain)
    if distance is None or distance > ENDING_REACH:
        return None
    name = ENDING_PATH.sub("", title.text.strip())
    story = " ".join(caption.text.split())
    return f"{name}. {story}" if name else story


# ---------------------------------------------------------------------- trials
#
# A trial lists its combo's steps down the left of the fight, each step drawn
# three times at one place: a top layer, white while to do and yellow (1, 0.8,
# 0, alpha 0.5) once landed, over two red layers (1, 0.4, 0.3, alpha 0.5) that
# turn (1, 0.6, 0.3) as the trial completes. Nothing is selected, but the
# prompt rule took the layers for buttons and marked some of them, and as steps
# lit and reset those marks moved, so attempts read out broken pieces of the
# list; and a step repeated in a combo was said once. The list is now said
# whole, numbered, once, and again on each restart: the game shows "Restart
# Battle" at the foot of the screen, and Try Again leaves the pause menu.
# Commands display draws most inputs as pictures with no text, so steps made
# only of pictures are missing from it; Display Move Names gives every step.

TRIAL_LAYER_TINTS = ((1.0, 0.4, 0.3, 0.5), (1.0, 0.6, 0.3, 0.5))
TRIAL_RESTART_NOTICE = "Restart Battle"
TRIAL_TRY_AGAIN = "Try Again"


def _near(tint, want) -> bool:
    return all(abs(a - b) <= TINT_TOLERANCE for a, b in zip(tint, want))


def _step_text(it: TextItem) -> str:
    return " ".join(it.text.split())


def _trial_places(shown: list[TextItem]) -> dict[tuple, list[TextItem]]:
    places: dict[tuple, list[TextItem]] = defaultdict(list)
    for it in shown:
        text = _step_text(it)
        if text:
            places[(round(it.x), round(it.y), text)].append(it)
    return {place: layers for place, layers in places.items()
            if len(layers) >= 2 and any(_near(l.tint, t) for l in layers for t in TRIAL_LAYER_TINTS)}


def trial_steps(items: list[TextItem]) -> list[str]:
    """A trial's steps in order, a repeated move as often as it comes."""
    places = _trial_places([it for it in items if it.shown])
    return [text for (_x, _y, text) in sorted(places, key=lambda p: (p[1], p[0]))]


def mark_trial(items: list[TextItem]) -> None:
    """A trial's step layers are never selected."""
    shown = [it for it in items if it.shown]
    for layers in _trial_places(shown).values():
        for it in layers:
            if it.chosen:
                it.chosen, it.group, it.slot = False, 0, 0


def trial_summary(items: list[TextItem]) -> str | None:
    """"(STANDING) heavy punch (COUNTER), down, down plus punch punch, ..." while a trial's steps show.

    Steps are joined by commas without numbers, following the user's example
    of a combo; each step ends with its button, which marks where it ends.
    """
    steps = trial_steps(items)
    if not steps:
        return None
    return ", ".join(steps) + "."


def trial_restarted(before: list[TextItem], after: list[TextItem]) -> bool:
    """Whether a trial has just been restarted, so its steps are worth hearing again."""
    if not trial_steps(after):
        return False

    def notice(items):
        return any(it.shown and it.text.strip() == TRIAL_RESTART_NOTICE and not it.selected for it in items)

    if notice(after) and not notice(before):
        return True
    on_try_again = any(it.highlighted and it.text.strip() == TRIAL_TRY_AGAIN for it in before)
    return on_try_again and not any(it.shown and it.text.strip() == TRIAL_TRY_AGAIN for it in after)


# --------------------------------------------------------- pictures in text
#
# Command displays draw inputs as pictures inside the text, each in place of a
# space: "(STANDING) M  H " is medium punch, then heavy punch. Each space's
# format names the picture, "img:///Game/CommonAsset/TaggedImages/punch_m...",
# and read against a screenshot of a trial the names are plain: directions in
# numpad notation (cmd_2 down, cmd_236 quarter circle forward, cmd_214 quarter
# circle back), punch and kick for the white icons meaning any, punch_m and
# punch_h for the coloured ones, plus for the plus sign and next for the arrow
# meaning then. Directions assume facing right, as the game draws them.
#
# The wording is the user's. "then" is not said, only the comma where the arrow
# was; nor is "(STANDING)", since a button with no direction before it is
# standing already. "(CROUCH)" is said "down plus", "(JUMP)" "jump".

DIRECTION_WORDS = {"1": "down back", "2": "down", "3": "down forward", "4": "back", "5": "neutral",
                   "6": "forward", "7": "up back", "8": "up", "9": "up forward"}
MOTION_WORDS = {"236": "quarter circle forward", "214": "quarter circle back",
                "41236": "half circle forward", "63214": "half circle back"}
STRENGTH_WORDS = {"l": "light", "m": "medium", "h": "heavy"}
JOINER_WORDS = {"plus": "plus", "next": ""}
# The game's own words before a button, as the user wants them said: standing
# is left out, crouch is down plus, jump stays jump.
STANCE_WORDS = (
    (re.compile(r"\(\s*STANDING\s*\)", re.IGNORECASE), ""),
    (re.compile(r"\(\s*CROUCH(ING)?\s*\)", re.IGNORECASE), "down plus"),
    (re.compile(r"\(\s*JUMP(ING)?\s*\)", re.IGNORECASE), "jump"),
)


# Pictures standing for a currency, said after the amount that follows them:
# the Current Missions notice draws "Reward: <Fight Money picture>50".
ICON_WORDS = {"icon_FM": "Fight Money"}
# Pictures that need no words: each sits beside words saying the same, as the
# EXP picture before "100 EXP" and a gem's before its name, or is a controller
# button's picture beside the hint it belongs to. Left as the game's spaces and
# not noted as wanting words.
SILENT_PICTURES = {"icon_EXP", "icon_GC", "icon_Entitlement_open", "button_a", "button_x", "button_y"}
SILENT_PICTURE_PREFIXES = ("icon_EXbattle",)


def _icon_amounts(text: str) -> str:
    """"Reward:  Fight Money 50" as "Reward: 50 Fight Money"."""
    for words in ICON_WORDS.values():
        text = re.sub(rf" *{re.escape(words)} *([\d,]+)", rf" \1 {words}", text)
    return text


def input_words(name: str) -> str | None:
    """Words for a command picture's name, or None if it is not one known."""
    if name in JOINER_WORDS:
        return JOINER_WORDS[name]
    if name.startswith("cmd_"):
        digits = name[4:]
        if digits in MOTION_WORDS:
            return MOTION_WORDS[digits]
        if digits and all(d in DIRECTION_WORDS for d in digits):
            return ", ".join(DIRECTION_WORDS[d] for d in digits)
        return None
    button, _, strength = name.partition("_")
    if button in ("punch", "kick"):
        if not strength:
            return button
        if strength in STRENGTH_WORDS:
            return f"{STRENGTH_WORDS[strength]} {button}"
    return None


def describe_inputs(pieces: list[tuple[str, str]]) -> str:
    """A command as speech: "down, down plus punch punch", "medium punch, heavy punch".

    `pieces` are ("text", ...) and ("picture", name) in order. The letter the
    game prints before a coloured button ("M" before the medium punch) is
    dropped, since the words already say it. The notation is the user's own
    example: "heavy punch, quarter circle forward plus kick kick, down, down
    plus heavy punch", so no comma before plus, a plain button pressed twice
    is said twice, the arrow meaning then is only a comma, "(STANDING)" is
    left out, "(CROUCH)" is "down plus" and "(JUMP)" is "jump".
    """
    # Each token is [kind, words, name, count]: kind "text", "input" or "joiner".
    tokens: list[list] = []
    for kind, value in pieces:
        if kind == "text":
            tokens.append(["text", value.replace("\0", ""), None, 1])
            continue
        strength = value.partition("_")[2]
        if strength in STRENGTH_WORDS and tokens and tokens[-1][0] == "text":
            before = tokens[-1][1].rstrip()
            if before[-1:].lower() == strength and (len(before) == 1 or not before[-2].isalnum()):
                tokens[-1][1] = before[:-1]
        if value in ("punch", "kick") and tokens and tokens[-1][2] == value:
            tokens[-1][3] += 1
            continue
        tokens.append(["joiner" if value in JOINER_WORDS else "input", input_words(value), value, 1])
    out, previous, previous_name, comma = "", None, None, False
    for kind, said, name, count in tokens:
        if kind == "text":
            for pattern, words in STANCE_WORDS:
                said = pattern.sub(words, said)
        said = " ".join(said.split())
        if name == "next":
            comma = True
            continue
        if not said:
            continue
        if count > 1:
            said = " ".join([said] * count)
        # Directions one after another are separate presses, "down, down".
        # Buttons side by side are pressed together: the same one is said
        # twice, "punch punch", and different ones get plus between them,
        # "medium punch plus medium kick", in the user's words.
        both_inputs = kind == "input" and previous == "input"
        both_directions = both_inputs and name.startswith("cmd_") and (previous_name or "").startswith("cmd_")
        both_buttons = both_inputs and not name.startswith("cmd_") and not (previous_name or "cmd_").startswith("cmd_")
        if previous is None:
            gap = ""
        elif comma or both_directions:
            gap = ", "
        elif both_buttons and name != previous_name:
            gap = " plus "
        else:
            gap = " "
        out += gap + said
        previous, previous_name, comma = kind, name, False
    return out


# ---------------------------------------------------------------- extra battle
#
# Entering Extra Battle opens one event's panel beside BEGIN BATTLE, the only
# thing selected: its title, START and DEADLINE with the time remaining,
# REWARD (a picture), PARTICIPATION FEE (FM) and NO. OF REMAINING PLAYS with
# their values on the same line, a description whose paragraphs begin with a
# heading line ("Difficulty", "Easy"; "Clear Reward", "\"Forest\" Gem, 100
# EXP"), and "Clear Conditions: Win the battle!". Only BEGIN BATTLE was said.
# Arriving now says the title, difficulty and clear conditions first; the read
# key says the rest.

EXTRA_BATTLE_LABELS = ("PARTICIPATION FEE (FM)", "NO. OF REMAINING PLAYS")
EXTRA_BATTLE_BUTTON = "BEGIN BATTLE"
# Said on arriving after the title, in the panel's order; the user asked for
# the deadline and fee alongside difficulty and clear conditions.
EXTRA_BATTLE_BRIEF = ("DEADLINE", "PARTICIPATION FEE", "Difficulty", "Clear Conditions")
HEADING_MAX = 40


def _extra_battle_panel(shown: list[TextItem]) -> int | None:
    labels = [it for it in shown if it.text.strip() in EXTRA_BATTLE_LABELS and it.chain]
    if len({it.text.strip() for it in labels}) != len(EXTRA_BATTLE_LABELS):
        return None
    common = set(labels[0].chain)
    for it in labels[1:]:
        common &= set(it.chain)
    return next((obj for obj in labels[0].chain[1:] if obj in common), None)


def _paragraph_sentences(text: str) -> list[str]:
    """A description's paragraphs as sentences, a heading line joined to what follows it."""
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        head = lines[0]
        if len(lines) > 1 and len(head) <= HEADING_MAX and ":" not in head and head[-1] not in ".!?)":
            out.append(f"{head}: {', '.join(lines[1:])}")
        else:
            out.extend(lines)
    return out


def extra_battle_details(items: list[TextItem], brief: bool = False) -> list[str]:
    """An Extra Battle event's panel as sentences, in reading order; `brief` for arriving.

    Brief is the title, deadline, fee, difficulty and clear conditions. A
    label with no text beside it, REWARD whose reward is a picture, is left out.
    """
    shown = [it for it in items if it.shown]
    panel = _extra_battle_panel(shown)
    if panel is None:
        return []
    inside = [it for it in shown if panel in it.chain and it.text.strip()]
    rows: dict[int, list[TextItem]] = defaultdict(list)
    for it in inside:
        rows[round(it.y)].append(it)
    sentences = []
    for y in sorted(rows):
        row = sorted(rows[y], key=lambda it: it.x)
        if len(row) == 1 and "\n" in row[0].text:
            sentences += _paragraph_sentences(row[0].text)
        elif len(row) > 1:
            sentences.append(f"{row[0].text.strip()}: {' '.join(it.text.strip() for it in row[1:])}")
        elif not sentences or ":" in row[0].text or len(row[0].text.strip()) > HEADING_MAX:
            sentences.append(" ".join(row[0].text.split()))
    if not brief:
        return sentences
    wanted = [sentences[0]] if sentences else []
    wanted += [s for s in sentences[1:] if s.startswith(EXTRA_BATTLE_BRIEF)]
    return wanted


# ---------------------------------------------------------------- notice lists
#
# After logging in, the main menu opens under notices, one after another, each
# a panel holding a title, one scrolling text and one Close button. The text is
# entries separated by blank lines, each a name, perhaps a detail line, and a
# DEADLINE line:
#
#   Current Missions: "Perform a cross-up 10 time(s)!", then "DEADLINE:Sep 15,
#   2026, 9:00:00 PM (Days left: 1) Reward: 50", a Fight Money picture before
#   the amount.
#
#   Currently Available Extra Battle (not completed): "[Quick & Immovable] Get
#   the Crossover Costume! [2]", "Costume: RASHID : Airman", "DEADLINE:Sep 14,
#   2026, 9:00:00 PM ( 4:50 remaining)", "Reward: "Forest" Gem, 100 EXP", a
#   picture before each reward and the costume. The time left is hours and
#   minutes as the notice was built: 4:50 before 9 PM, at 4:10 PM.
#
# Close is plain white, not built as a prompt's chosen button, so no rule
# marked it, and the main menu's cursor starts on the advert banner behind,
# which is marked: the first notice said only "UPGRADE KIT AVAILABLE NOW". The
# title field sits at zero alpha while plainly drawn; see `_show_notice_title`.

NOTICE_BUTTON = "Close"
NOTICE_DEADLINE = re.compile(
    r"^DEADLINE:\s*(?P<deadline>.*?)\s*(?:\((?P<left>[^)]*)\))?\s*(?:Reward:\s*(?P<reward>.*?))?\s*$")
NOTICE_REWARD = re.compile(r"^Reward:\s*(?P<reward>.*?)\s*$")
NOTICE_TITLE_MAX = 80
# How far above a notice's text and its Close button their shared panel may be.
NOTICE_PANEL_LEVELS = 4
MONTH_WORDS = {"Jan": "January", "Feb": "February", "Mar": "March", "Apr": "April", "Jun": "June",
               "Jul": "July", "Aug": "August", "Sep": "September", "Oct": "October", "Nov": "November",
               "Dec": "December"}


def notice_entries(text: str) -> list[tuple[str, list[str], str, str, str]]:
    """Each entry in a notice's list: its name, other lines, deadline, time left and reward."""
    out = []
    for block in re.split(r"\n\s*\n", text):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        deadline = next((m for m in map(NOTICE_DEADLINE.match, lines[1:]) if m), None)
        if deadline is None:
            continue
        reward = deadline["reward"] or next((m["reward"] for m in map(NOTICE_REWARD.match, lines[1:]) if m), "")
        extras = [line for line in lines[1:] if not NOTICE_DEADLINE.match(line) and not NOTICE_REWARD.match(line)]
        out.append((lines[0], extras, deadline["deadline"], (deadline["left"] or "").strip(), reward))
    return out


def _counted(text: str) -> str:
    """"10 time(s)" as "10 times" and "1 match(es)" as "1 match", by the first number."""
    number = re.search(r"\d+", text)
    one = number is not None and int(number.group()) == 1
    return re.sub(r"(\w)\((e?s)\)", lambda m: m.group(1) + ("" if one else m.group(2)), text)


def _spoken_date(text: str) -> str:
    """"Sep 15, 2026, 9:00:00 PM" as "September 15, 2026, 9:00 PM"."""
    text = re.sub(r"\b(\d{1,2}:\d\d):\d\d\b", r"\1", text)
    return re.sub(r"\b(" + "|".join(MONTH_WORDS) + r")\b", lambda m: MONTH_WORDS[m.group()], text)


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def _time_left(left: str) -> str:
    """"Days left: 1" as "1 day left", "4:50 remaining" as "4 hours 50 minutes remaining"."""
    days = re.fullmatch(r"Days left:\s*(\d+)", left)
    if days:
        return f"{_plural(int(days.group(1)), 'day')} left"
    clock = re.fullmatch(r"(\d+):(\d\d) remaining", left)
    if clock:
        hours, minutes = int(clock.group(1)), int(clock.group(2))
        parts = [_plural(hours, "hour")] if hours else []
        if minutes or not hours:
            parts.append(_plural(minutes, "minute"))
        return " ".join(parts) + " remaining"
    return left


def _notice_list(shown: list[TextItem]) -> tuple[TextItem, TextItem] | None:
    """A notice's list text and its Close button, while such a notice shows."""
    for text in shown:
        if not text.chain or "DEADLINE:" not in text.text or not notice_entries(text.text):
            continue
        for button in shown:
            if button.text.strip() != NOTICE_BUTTON or not button.chain:
                continue
            panel = next((obj for obj in text.chain[1:NOTICE_PANEL_LEVELS + 1] if obj in button.chain), None)
            if panel is not None and button.chain.index(panel) <= NOTICE_PANEL_LEVELS:
                return text, button
    return None


def mark_notice(shown: list[TextItem]) -> None:
    """Close is a notice's selection, and nothing behind the notice is.

    Gold behind it stays gold, as behind any prompt; only marks made by the
    rules without gold, such as the banner's, are cleared outside the
    notice's movie.
    """
    found = _notice_list(shown)
    if found is None:
        return
    text, button = found
    for it in shown:
        if it.chosen and it.chain and it.chain[-1] != text.chain[-1]:
            it.chosen = False
    button.chosen = True


def notice_details(items: list[TextItem], brief: bool = False) -> list[str]:
    """A notice's title and list as sentences; `brief`, for arriving, without deadlines and rewards.

    In full an entry says its name and any detail line, the time left and
    deadline, and the reward: "Perform a cross-up 10 times! 1 day left,
    deadline September 15, 2026, 9:00 PM. Reward 50 Fight Money."
    """
    shown = [it for it in items if it.shown]
    found = _notice_list(shown)
    if found is None:
        return []
    text, button = found
    holder = text.chain[1] if len(text.chain) > 1 else None
    title = next((it.text.strip() for it in shown
                  if it is not text and it is not button and holder in it.chain
                  and 0 < len(it.text.strip()) <= NOTICE_TITLE_MAX and "\n" not in it.text.strip()), None)
    sentences = [title] if title else []
    for name, extras, deadline, left, reward in notice_entries(text.text):
        sentences.append(_counted(name))
        sentences += extras
        if brief:
            continue
        when = f"deadline {_spoken_date(deadline)}"
        sentences.append(f"{_time_left(left)}, {when}" if left else when)
        if reward:
            sentences.append(f"Reward {reward}")
    # A picture left as the game's space doubles the space beside it.
    return [" ".join(s.split()) for s in sentences]


# ---------------------------------------------------------------- status lines
#
# Starting the game shows one line at a time at the foot of the title screen,
# "Applying Title Update Ver.07.011...", "Connecting to server...", "Logging
# into the server...", with nothing else and nothing selected, so nothing was
# said. In every log so far only these were a screen's one text ending "...".

STATUS_MAX = 60


def status_line(items: list[TextItem]) -> str | None:
    """A screen's only text when it is a status line such as "Logging into the server..."."""
    shown = [it for it in items if it.shown and it.text.strip()]
    if len(shown) != 1 or shown[0].selected:
        return None
    text = shown[0].text.strip()
    return text if text.endswith("...") and len(text) <= STATUS_MAX else None


PATH_STORY_MIN = 60


def path_story(items: list[TextItem]) -> list[str]:
    """The story of the path you are on in Arcade's path select, line by line, for the read key.

    Beside the paths is the chosen one's story: "Launched in August 1987, ...",
    "Story Chronological Order: 1", "A young Ryu and Ken test ...". It is the
    longest text in the paths' movie that is not selected. Moving says only
    the path; the user asked for the story on the read key.
    """
    shown = [it for it in items if it.shown]
    if not any(it.text.strip().startswith(PATH_SELECT_PROMPT) for it in shown):
        return []
    chosen = next((it for it in shown if it.highlighted and it.chain), None)
    if chosen is None:
        return []
    stories = [it for it in shown if not it.selected and it.chain and it.chain[-1] == chosen.chain[-1]
               and len(it.text.strip()) >= PATH_STORY_MIN]
    if not stories:
        return []
    story = max(stories, key=lambda it: len(it.text))
    return [line.strip() for line in story.text.splitlines() if line.strip()]


def screen_summary(items: list[TextItem]) -> tuple[bool, str | None]:
    """For screens read as one sentence rather than by what is selected.

    Whether this is one, and the sentence once all of it is showing: the
    result screen after a match, the VS screen before one, and the caption
    of an Arcade ending. Arcade's
    result screen before the final stage offers one opponent and no choice,
    and says "FINAL STAGE"; its card, gold, follows (`_show_final_opponent`).
    """
    if on_results(items):
        summary = result_summary(items)
        if summary is None and any(it.shown and it.text.strip() == ARCADE_FINAL_STAGE for it in items):
            summary = ARCADE_FINAL_STAGE
        return True, summary
    summary = versus_summary(items) or ending_summary(items) or trial_summary(items) or status_line(items)
    return summary is not None, summary


def _compose(outer, inner):
    """Affine (sx, shx, tx, shy, sy, ty) products: apply inner, then outer."""
    a, b = outer, inner
    return (
        a[0] * b[0] + a[1] * b[3],
        a[0] * b[1] + a[1] * b[4],
        a[0] * b[2] + a[1] * b[5] + a[2],
        a[3] * b[0] + a[4] * b[3],
        a[3] * b[1] + a[4] * b[4],
        a[3] * b[2] + a[4] * b[5] + a[5],
    )


class ScaleformText:
    """Reads the text fields of every Scaleform movie the game has open."""

    def __init__(self, pm: ProcessMemory, module_base: int) -> None:
        self.pm = pm
        self.module_base = module_base
        # Scaleform's own blocks, from the last walk of the address space.
        # Sweeping every page takes a third of a second and walking the address
        # space a tenth, nearly all of a read. Scaleform's blocks take thirty
        # thousandths. Sweeping only the pages that already held text is faster
        # still, and was tried: a prompt draws each newly selected answer in a
        # new text field, often in a block that held none, and the answer was
        # heard a second late.
        self._scaleform_pages = None
        self.pages_refreshed_at = 0.0   # time.monotonic() of the last walk for blocks
        # Regions outside the usual heap pages where a wide sweep has found text
        # showing, read alongside them from then on. See `wide_sweep`.
        self.extra_pages: list = []
        # Picture grids under the movies showing text, found by walking the
        # display tree, which is too slow to do on every read. Only the
        # selected tile is checked each read.
        self._grids: dict[int, list[int]] = {}
        self._text_grids: set[int] = set()   # grids seen holding text, never pictures
        self._roots: set[int] = set()
        # Pictures inside text with no words yet, by image name, for the log.
        self.unknown_pictures: set[str] = set()

    # ------------------------------------------------------------- discovery
    def keep_pages_current(self, stop: threading.Event, interval: float = PAGE_REFRESH) -> None:
        """Refresh the block list on a background thread until `stop` is set.

        Anything polling with quick reads needs this. Without it, a screen
        opened after the first read has its text in blocks the list never
        learns about, and reads as next to nothing: the first stage grid
        recording caught Battle Settings as seven lines of header.
        """
        def run():
            while not stop.is_set():
                try:
                    self.refresh_pages()
                    self.refresh_grids()
                except Exception as exc:  # the game closing, most likely
                    print(f"page refresh failed: {exc}")
                stop.wait(interval)

        self.refresh_pages()
        threading.Thread(target=run, daemon=True).start()

    def refresh_grids(self) -> None:
        """Walk the display tree under the movies last seen showing text for picture grids."""
        self._grids = find_grids(self.children, set(self._roots))
        # Forget grids that have gone, so a new object at a reused address is
        # not taken for a list it happens to share an address with.
        self._text_grids &= set(self._grids)

    def refresh_pages(self) -> None:
        """Walk the address space for Scaleform's blocks, for quick reads to sweep."""
        self._scaleform_pages = [
            r for r in self.heap_pages()
            if r.size % SCALEFORM_CHUNK == SCALEFORM_EXTRA and r.size > SCALEFORM_CHUNK
        ]
        self.pages_refreshed_at = time.monotonic()

    def wide_sweep(self, stop: threading.Event | None = None) -> list[tuple]:
        """DocViews in readable regions the usual search skips, with their regions.

        The usual search reads only small read-write pages, since that is where
        Scaleform's text has always been. Returning to stage select from
        character select left both quick and full reads finding nothing for
        most of a minute while the screen showed text, so this looks everywhere
        else: every readable region of any size or protection. It takes
        several seconds, so it is for a background thread.
        """
        usual = {(page.base, page.size) for page in self.heap_pages()}
        found = []
        for region in self.pm.regions(1 << 31):
            if stop is not None and stop.is_set():
                break
            if (region.base, region.size) in usual:
                continue
            views = self.docviews([region])
            if views:
                found.append((region, views))
        return found

    def heap_pages(self):
        return [
            r
            for r in self.pm.regions(HEAP_PAGE_LIMIT)
            if r.protect == PAGE_READWRITE and r.size <= HEAP_PAGE_LIMIT
        ]

    def docviews(self, pages=None) -> list[int]:
        want = np.uint64(self.module_base + DOCVIEW_VTABLE)
        found = []
        for r in pages if pages is not None else self.heap_pages():
            buf = self.pm.read(r.base, r.size)
            if not buf:
                continue
            words = np.frombuffer(buf[: len(buf) // 8 * 8], "<u8")
            found.extend(r.base + int(i) * 8 for i in np.flatnonzero(words == want))
        return found

    # ------------------------------------------------------------------ text
    def field_text(self, docview: int) -> str | None:
        styled = self.pm.ptr(docview + DOCVIEW_TEXT)
        if not styled or self.pm.ptr(styled) != self.module_base + STYLED_TEXT_VTABLE:
            return None
        data = self.pm.ptr(styled + TEXT_PARAGRAPHS)
        count = self.pm.u64(styled + TEXT_PARAGRAPH_COUNT)
        if count is None or count > MAX_PARAGRAPHS or (count and not data):
            return None
        parts = []
        for i in range(count):
            para = self.pm.ptr(data + i * 8)
            if not para:
                continue
            head = self.pm.read(para, PARAGRAPH_RUN_COUNT + 8)
            if not head:
                continue
            chars, size = struct.unpack_from("<QQ", head, PARAGRAPH_CHARS)
            if not chars or not size or size > MAX_PARAGRAPH_CHARS:
                continue
            raw = self.pm.read(chars, size * 2)
            if not raw:
                continue
            text = raw.decode("utf-16-le", "replace")
            runs, run_count = struct.unpack_from("<QQ", head, PARAGRAPH_RUNS)
            if runs and 1 < run_count <= min(size + 1, MAX_RUNS):
                text = self._with_pictures(text, runs, run_count)
            parts.append(text.rstrip("\0"))
        # Scaleform ends a paragraph with a carriage return.
        return "\n".join(p.rstrip("\r") for p in parts)

    def _picture_name(self, desc: int) -> str | None:
        """"punch_h" for a picture drawn from "img:///Game/CommonAsset/TaggedImages/punch_h.punch_h"."""
        tagged = self.pm.u64(desc + IMAGE_URL)
        if not tagged:
            return None
        data = tagged & ~3
        size = (self.pm.u64(data + STRING_SIZE) or 0) & 0x7FFFFFFFFFFFFFFF
        if not 0 < size <= MAX_PARAGRAPH_CHARS:
            return None
        raw = self.pm.read(data + STRING_CHARS, size)
        if not raw:
            return None
        return raw.decode("ascii", "replace").rsplit("/", 1)[-1].split(".", 1)[0]

    def _with_pictures(self, text: str, runs: int, count: int) -> str:
        """The paragraph with its known pictures put into words, others left as the game's spaces."""
        raw = self.pm.read(runs, count * RUN_STRIDE)
        if not raw:
            return text
        pieces: list[tuple[str, str]] = []
        found = icons = False
        for i in range(count):
            start, length, fmt = struct.unpack_from("<QQQ", raw, i * RUN_STRIDE)
            if start >= len(text) or not length:
                continue
            chunk = text[start:start + length]
            desc = self.pm.ptr(fmt + FORMAT_IMAGE) if fmt else None
            name = self._picture_name(desc) if desc else None
            if name is None:
                pieces.append(("text", chunk))
                continue
            if name in ICON_WORDS:
                icons = True
                pieces.append(("text", f" {ICON_WORDS[name]} {chunk[1:]}"))
                continue
            if input_words(name) is None:
                if name not in SILENT_PICTURES and not name.startswith(SILENT_PICTURE_PREFIXES):
                    self.unknown_pictures.add(name)
                pieces.append(("text", chunk))
                continue
            found = True
            pieces.append(("picture", name))
            if chunk[1:]:
                pieces.append(("text", chunk[1:]))
        if found:
            text = describe_inputs(pieces)
        elif icons:
            text = "".join(value for _kind, value in pieces)
        return _icon_amounts(text) if icons else text

    # ------------------------------------------------------------- placement
    def _node(self, obj: int):
        """An object's transform, colour multiplier and flag word, from its render node.

        A zero alpha on a node whose bounds are empty does not count. The
        Arcade opponent cards sat under such a node for minutes while plainly
        on screen, as did the main menu's entries at the start of one
        recording and a row of the menu music list in another; every text a
        node like that hid, in 667 records, was showing in the screenshot. A
        node really faded out keeps its bounds.
        """
        entry = self.pm.ptr(obj + DISPLAY_RENDER_NODE)
        data = self.pm.ptr(entry + RENDER_NODE_DATA) if entry else None
        raw = self.pm.read(data, NODE_BOUNDS + 0x20) if data else None
        if not raw:
            return None
        flags = struct.unpack_from("<H", raw, NODE_FLAGS)[0]
        m = struct.unpack_from("<8f", raw, NODE_MATRIX)
        cx = struct.unpack_from("<4f", raw, NODE_CXFORM)
        if not all(math.isfinite(v) and abs(v) < 1e7 for v in m + cx):
            return None
        if cx[3] <= 0.01 and not any(struct.unpack_from("<8f", raw, NODE_BOUNDS)):
            cx = (cx[0], cx[1], cx[2], 1.0)
        return (m[0], m[1], m[3], m[4], m[5], m[7]), cx, flags

    def place(self, docview: int):
        """The owner chain, stage position, tint, hiddenness and rootedness of a DocView's field."""
        listener = self.pm.ptr(docview + DOCVIEW_LISTENER)
        obj = self.pm.ptr(listener + LISTENER_OWNER) if listener else None
        if not obj:
            return None
        nodes = []
        chain = []
        while obj and obj not in chain and len(chain) < MAX_DEPTH:
            node = self._node(obj)
            if node is None:
                break
            nodes.append(node)
            chain.append(obj)
            obj = self.pm.ptr(obj + DISPLAY_PARENT)
        if not chain:
            return None
        world = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
        tint = [1.0, 1.0, 1.0, 1.0]
        for matrix, cx, _flags in reversed(nodes):
            world = _compose(world, matrix)
            tint = [t * c for t, c in zip(tint, cx)]
        hidden = any(not flags & NODE_VISIBLE for _m, _cx, flags in nodes[1:])
        rooted = nodes[-1][2] & MOVIE_ROOT_FLAGS == MOVIE_ROOT_FLAGS
        x, y = world[2] / TWIPS_PER_PIXEL, world[5] / TWIPS_PER_PIXEL
        return tuple(chain), x, y, tuple(tint), hidden, rooted

    def chain_states(self, chain: tuple[int, ...]) -> str:
        """Each object's flag word and raw alpha up a chain, "e" where its bounds are empty, for logs."""
        states = []
        for obj in chain:
            entry = self.pm.ptr(obj + DISPLAY_RENDER_NODE)
            data = self.pm.ptr(entry + RENDER_NODE_DATA) if entry else None
            raw = self.pm.read(data, NODE_BOUNDS + 0x20) if data else None
            if not raw:
                states.append("-")
                continue
            flags = struct.unpack_from("<H", raw, NODE_FLAGS)[0]
            alpha = struct.unpack_from("<f", raw, NODE_CXFORM + 12)[0]
            empty = "e" if not any(struct.unpack_from("<8f", raw, NODE_BOUNDS)) else ""
            states.append(f"{flags:x}/{alpha:.2f}{empty}")
        return " ".join(states)

    def children(self, obj: int) -> list[int]:
        """The display objects directly inside `obj`.

        Only those that name `obj` as their parent. A real child always does,
        and garbage left by a screen being torn down almost never will, so a
        walk that strays into freed memory stops there instead of following a
        made-up list of thousands of children.
        """
        count = self.pm.u32(obj + DISPLAY_CHILD_COUNT) or 0
        data = self.pm.ptr(obj + DISPLAY_CHILDREN)
        if not data or not 0 < count <= MAX_CHILDREN:
            return []
        raw = self.pm.read(data, count * DISPLAY_CHILD_STRIDE)
        if not raw or len(raw) < count * DISPLAY_CHILD_STRIDE:
            return []
        entries = (struct.unpack_from("<Q", raw, i * DISPLAY_CHILD_STRIDE)[0] for i in range(count))
        return [
            kid for kid in entries
            if kid > 0x10000 and not kid & 7 and self.pm.ptr(kid + DISPLAY_PARENT) == obj
        ]

    # ------------------------------------------------------------- selection
    def mark_choices(self, items: list[TextItem]) -> None:
        """Find the selected entry in a group that is not marked with gold.

        A group is a container whose children each hold exactly one short
        label. Two ways of marking the selection are recognised: a prompt's
        buttons, where the selected one has extra layers and its label sits
        deeper, and a grid of tiles, where it is drawn brighter than the rest.
        Gold elsewhere on screen does not stop either: a prompt opened from a
        menu sits over that menu's gold entry.

        On character select the fighters' names are the selection instead. See
        `mark_fighters`.
        """
        shown = [it for it in items if it.shown]
        groups: dict[int, dict[int, list]] = defaultdict(lambda: defaultdict(list))
        for it in shown:
            for level in range(1, len(it.chain)):
                groups[it.chain[level]][it.chain[level - 1]].append((it, level - 1))
        for container, slots in groups.items():
            if len(slots) == 1:
                self._mark_lone_button(container, slots, shown)
                continue
            if any(len(held) != 1 for held in slots.values()):
                continue
            if any(len(held[0][0].text.strip()) > CHOICE_TEXT_LIMIT for held in slots.values()):
                continue
            if self._mark_by_layers(container, slots):
                continue
            self._mark_by_brightness(container, slots)
        self._mark_highlighted_rows(shown, groups)
        self._mark_single_move(shown, groups)
        self._mark_picture_grids(shown)
        mark_fighters(shown)
        mark_results(shown)
        mark_versus(shown)
        mark_trial(shown)
        mark_notice(shown)
        self._mark_ticks(shown)
        if not any(it.selected for it in shown):
            stage = stage_on_offer(shown)
            if stage is not None:
                stage.chosen = True

    def _mark_highlighted_rows(self, shown: list[TextItem], groups) -> None:
        """Mark the text on a list row whose highlight bar is on, when the list has no gold.

        Unlike a prompt's buttons, the row is not recorded as a group: a list
        coming into view is not a prompt opening, and should not have the text
        around it read out as though it were a question.
        """
        def appearance(obj):
            node = self._node(obj)
            return None if node is None else (node[1], node[2])

        kids = _remembering(self.children)
        for container, slots in groups.items():
            if len(slots) < SHORT_LIST_ROWS:
                continue
            if any(it.highlighted for held in slots.values() for it, _level in held):
                continue
            row = highlighted_row(kids, appearance, grid_tiles(kids, container, minimum=SHORT_LIST_ROWS))
            if row is None:
                continue
            for it in shown:
                if row in it.chain:
                    it.chosen = True

    def _mark_single_move(self, shown: list[TextItem], groups) -> None:
        """The only move in a Command List section, which nothing else can mark.

        With two moves or more the row the cursor is on shows one part the
        others hide. With one there is nothing to compare, so on the Command
        List, and only while nothing else there is selected, a list whose text
        all sits in one move row, many parts each a background and a holder,
        is taken as the selection: the one move is the one the cursor is on.
        """
        note = next((it for it in shown if it.text.strip() == COMMAND_LIST_NOTE and it.chain), None)
        if note is None:
            return
        # Only the Command List's own movie: a trial's step layers behind the
        # pause menu are still marked at this point, and cleared later.
        movie = note.chain[-1]
        if any(it.chosen for it in shown if it.chain and it.chain[-1] == movie):
            return
        kids = _remembering(self.children)
        best = None
        for container, slots in groups.items():
            if len(slots) != 1:
                continue
            (row, held), = slots.items()
            if len(held) < 2 or (best is not None and len(held) >= len(best[1])):
                continue
            parts = kids(row)
            if len(parts) < MOVE_ROW_MIN_PARTS or any(len(kids(p)) != MOVE_ROW_PART_CHILDREN for p in parts):
                continue
            if any(len(kids(other)) >= MOVE_ROW_MIN_PARTS for other in kids(container) if other != row):
                continue
            best = (row, held)
        if best is not None:
            for it, _level in best[1]:
                if not it.highlighted:
                    it.chosen = True

    def _mark_ticks(self, shown: list[TextItem]) -> None:
        """Whether each selected checklist entry is ticked. Only the selected
        ones, since that is all that is said and each costs a few reads."""
        def x_of(obj):
            node = self._node(obj)
            return None if node is None else node[0][2]

        kids = _remembering(self.children)
        for it in shown:
            if it.selected:
                it.ticked = tick_state(kids, x_of, it.chain)

    def _mark_picture_grids(self, shown: list[TextItem]) -> None:
        """Name the selected tile of a grid of pictures by the label nearest it.

        The grids come from the last walk of the tree, but their tiles are
        listed afresh on every read. Moving down a row scrolls the stage grid
        and changes its tiles, and a list kept from the walk left the new row's
        stage unnamed for up to two seconds.
        """
        def appearance(obj):
            node = self._node(obj)
            return None if node is None else (node[1], node[2])

        kids = _remembering(self.children)
        for grid in list(self._grids):
            if grid in self._text_grids:
                continue
            if any(grid in it.chain for it in shown):
                # Its tiles carry text, which the other rules read. Remember
                # that: a list scrolling empties its rows for a moment, and a
                # list taken for a grid of pictures then was named after the
                # nearest text, which read out "BGM LIST" with every scroll.
                self._text_grids.add(grid)
                continue
            tiles = grid_tiles(kids, grid)
            if not tiles:
                continue  # gone since the last walk
            tile = selected_tile(kids, appearance, tiles)
            if tile is None:
                continue
            up = [grid]
            while len(up) < MAX_DEPTH:
                parent = self.pm.ptr(up[-1] + DISPLAY_PARENT)
                if not parent or parent in up:
                    break
                up.append(parent)
            label = name_for_grid(up, shown)
            if label is not None:
                label.chosen = True
                label.group = grid
                label.slot = tile

    def _mark_by_layers(self, container: int, slots) -> bool:
        """A prompt's buttons: the selected one has its outline and fill as extra children."""
        layers = {slot: self.pm.u32(slot + DISPLAY_CHILD_COUNT) or 0 for slot in slots}
        most = max(layers.values())
        if list(layers.values()).count(most) != 1:
            return False
        winner = next(slot for slot, n in layers.items() if n == most)
        (item, nesting), = slots[winner]
        if not all(nesting > held[0][1] for slot, held in slots.items() if slot != winner):
            return False
        item.chosen = True
        item.group = container
        return True

    def _mark_lone_button(self, container: int, slots, shown: list[TextItem]) -> None:
        """A notice's only button, such as Close: built as a prompt's chosen button.

        The Trials notice in Challenges ("Some combos or move properties...")
        is the Exit prompt's template with one button: a row holding one
        button of six children, its label inside a layer, and the message
        beside the row in the same panel. With nothing to compare it with,
        the layers rule never looked at it, and the notice was silent. Nothing
        in three recordings was built this way.
        """
        (slot, held), = slots.items()
        if len(held) != 1:
            return
        item, nesting = held[0]
        if nesting != LONE_BUTTON_NESTING or len(item.text.strip()) > CHOICE_TEXT_LIMIT:
            return
        if self.pm.u32(container + DISPLAY_CHILD_COUNT) != 1:
            return
        if self.pm.u32(slot + DISPLAY_CHILD_COUNT) != CHOSEN_BUTTON_CHILDREN:
            return
        at = item.chain.index(container)
        panel = item.chain[at + 1] if at + 1 < len(item.chain) else None
        if panel is None or not any(it is not item and panel in it.chain and container not in it.chain
                                    for it in shown):
            return
        item.chosen = True
        item.group = container

    def _mark_by_brightness(self, container: int, slots) -> None:
        """A grid of tiles: the one you are on is drawn brighter than the rest.

        The Favorite Character grid and the voice language grid dim every
        other name to 0.75 and leave the selected one at full brightness, the
        reverse of a menu's gold. Only for three tiles or more, only when none
        is gold, and only when the brightest is alone, clearly ahead of a group
        that mostly shares one tint, and the same size as most of them, so a
        heading above dim entries is not taken for a selection.
        """
        if len(slots) < BRIGHT_GROUP_MIN:
            return
        labels = [held[0][0] for held in slots.values()]
        if any(it.highlighted for it in labels):
            return
        def brightness(it):
            return sum(it.tint[:3]) * it.tint[3]
        ranked = sorted(labels, key=brightness, reverse=True)
        top, rest = ranked[0], ranked[1:]
        if brightness(rest[0]) > brightness(top) - BRIGHTNESS_MARGIN:
            return
        tints = [tuple(round(c, 2) for c in it.tint) for it in rest]
        if max(tints.count(t) for t in tints) * 2 < len(rest):
            return
        boxes = [tuple(round(v) for v in it.box) for it in rest]
        usual = max(set(boxes), key=boxes.count)
        if boxes.count(usual) * 2 < len(rest) or tuple(round(v) for v in top.box) != usual:
            return
        top.chosen = True
        top.group = container

    def _hidden_ancestors(self, chain: tuple[int, ...]) -> list[int]:
        """The objects above a field whose render node has its visible bit clear."""
        hidden = []
        for obj in chain[1:]:
            node = self._node(obj)
            if node is not None and not node[2] & NODE_VISIBLE:
                hidden.append(obj)
        return hidden

    def _show_hidden_stage_select(self, every: list[TextItem]) -> None:
        """Read stage select's panel even while its container is marked hidden.

        Stage select and character select are panels of one movie. Backing out
        of character select, stage select is back on screen but its panel's
        container can keep its visible bit clear until the stage is changed a
        few times, and for up to a minute nothing counted as showing: the log
        grouped "STAGE SELECT" under "parent hidden". Only when nothing at all
        is showing, which is never true while character select really is on
        screen, is text under the same hidden containers as stage select's
        conditions counted as showing.
        """
        conditions = [it for it in every
                      if it.hidden and it.rooted and it.depth >= 2 and stage_condition(it.text)]
        if len({stage_condition(it.text)[0] for it in conditions}) < 2:
            return
        panels = set()
        for it in conditions:
            panels.update(self._hidden_ancestors(it.chain))
        if not panels:
            return
        for it in every:
            # Only text hidden by those containers and nothing else, so character
            # select's leftovers under their own hidden panel stay hidden.
            if it.hidden and panels.intersection(it.chain):
                if set(self._hidden_ancestors(it.chain)) <= panels:
                    it.hidden = False

    def _show_final_opponent(self, every: list[TextItem]) -> None:
        """Read Arcade's final opponent on the result screen offering FINAL STAGE.

        With two opponents to choose from, the cards are an ordinary gold menu.
        Before the final stage there is one, SAGAT with his reward, gold like
        a chosen card, but the card object above his name held alpha zero with
        real bounds for the half minute the screen stayed, which elsewhere
        means faded out. Whether it is drawn is not known; the name is the
        game's own final opponent, which the VS screen then confirmed. Only
        text under a card holding a gold fighter's name, in the movie showing
        FINAL STAGE, and hidden by nothing but alpha, is counted as showing.
        """
        marker = next((it for it in every if it.shown and it.text.strip() == ARCADE_FINAL_STAGE), None)
        if marker is None or not marker.chain:
            return
        movie = marker.chain[-1]
        names = fighter_names()

        def only_faded(it):
            return (it.depth >= 2 and it.rooted and not it.hidden and it.on_stage
                    and it.tint[3] <= 0.01 and bool(it.chain) and it.chain[-1] == movie)

        cards = set()
        for it in every:
            if it.text.strip() in names and only_faded(it) and it.highlighted:
                for obj in it.chain[1:]:
                    node = self._node(obj)
                    if node is not None and node[1][3] <= 0.01:
                        cards.add(obj)
                        break
        for it in every:
            if cards.intersection(it.chain) and only_faded(it):
                it.tint = (it.tint[0], it.tint[1], it.tint[2], 1.0)

    def _show_notice_title(self, every: list[TextItem]) -> None:
        """Read the title of a notice list, drawn while its own field holds alpha zero.

        "Current Missions" and "Currently Available Extra Battle (not
        completed)" were plainly on screen in the screenshot, yet each field's
        own node had alpha zero with real bounds, and nothing above it did.
        Only while a notice list shows, and only for a one-line text beside
        its list hidden by nothing but its own alpha.
        """
        found = _notice_list([it for it in every if it.shown])
        if found is None or len(found[0].chain) < 2:
            return
        holder = found[0].chain[1]
        for it in every:
            line = it.text.strip()
            if (it.shown or it.hidden or not it.rooted or it.depth < 2 or not it.on_stage
                    or it.tint[3] > 0.01 or holder not in it.chain or not line or "\n" in line
                    or len(line) > NOTICE_TITLE_MAX or is_placeholder(line)):
                continue
            own = self._node(it.chain[0])
            above = [self._node(obj) for obj in it.chain[1:]]
            if own is None or own[1][3] > 0.01 or any(node is None or node[1][3] <= 0.01 for node in above):
                continue
            it.tint = (it.tint[0], it.tint[1], it.tint[2], 1.0)

    def _show_path_select(self, every: list[TextItem]) -> None:
        """Read Arcade's path select, whose whole movie sits under a zero alpha.

        The paths (STREET FIGHTER I to V, each with its battles and best score,
        the one you are on gold) were read from the screen before memory took
        over, so they are on screen, yet the top node of their movie holds
        alpha zero with bounds. Nothing in its node data tells it from other
        movies, and a menu left loaded behind another screen may be hidden the
        same way, so this is kept to path select: while its description line
        ("Please select a path...") shows, text hidden by nothing but its
        movie's top alpha counts as showing.
        """
        if not any(it.shown and it.text.strip().startswith(PATH_SELECT_PROMPT) for it in every):
            return
        tops = {}
        for it in every:
            if not (it.depth >= 2 and it.rooted and not it.hidden and it.on_stage and it.tint[3] <= 0.01):
                continue
            top = it.chain[-2]
            if top not in tops:
                node = self._node(top)
                tops[top] = node is not None and node[1][3] <= 0.01 and bool(node[2] & MOVIE_ROOT_FLAGS)
            if not tops[top]:
                continue
            alpha = 1.0
            for obj in it.chain:
                if obj != top:
                    node = self._node(obj)
                    alpha *= node[1][3] if node is not None else 0.0
            if alpha > 0.01:
                it.tint = (it.tint[0], it.tint[1], it.tint[2], alpha)

    # ----------------------------------------------------------------- reads
    def items(self, everything: bool = False, quick: bool = False) -> list[TextItem]:
        """Text on screen in reading order. `everything` keeps the leftovers.

        `quick` sweeps only Scaleform's blocks as found by the last
        `refresh_pages`, for polling. A block Scaleform takes after that is
        missed until the next refresh, so a caller polling quickly must run
        `keep_pages_current` alongside.
        """
        if quick:
            if self._scaleform_pages is None:
                self.refresh_pages()
            docviews = self.docviews(self._scaleform_pages + self.extra_pages)
        else:
            docviews = self.docviews(self.heap_pages() + self.extra_pages)
        roots_before = set(self._roots)
        every = []
        for dv in docviews:
            text = self.field_text(dv)
            if text is None:
                continue
            placed = self.place(dv)
            if placed is None:
                every.append(TextItem(text, -1, -1, (0, 0, 0, 0), 0, dv))
                continue
            chain, x, y, tint, hidden, rooted = placed
            raw = self.pm.read(dv + DOCVIEW_SIZE, 8)
            box = tuple(v / TWIPS_PER_PIXEL for v in struct.unpack("<2f", raw)) if raw else (0.0, 0.0)
            every.append(TextItem(text, x, y, tint, len(chain), dv, chain, hidden=hidden, box=box,
                                  rooted=rooted))
        if not any(it.shown for it in every):
            self._show_hidden_stage_select(every)
        self._show_final_opponent(every)
        self._show_path_select(every)
        self._show_notice_title(every)
        out = every if everything else [it for it in every if it.shown]
        self._roots = {it.chain[-1] for it in out if it.shown and it.chain}
        if not quick and self._roots != roots_before:
            self.refresh_grids()
        self.mark_choices(out)
        out.sort(key=lambda it: (round(it.y), it.x))
        return out


def attach() -> ScaleformText | None:
    pid = find_pid(EXE, GAME_PATH_HINT)
    if pid is None:
        return None
    try:
        pm = ProcessMemory(pid)
    except OSError:
        return None
    mod = next((m for m in pm.modules() if m.name.lower() == EXE.lower()), None)
    if mod is None:
        pm.close()
        return None
    return ScaleformText(pm, mod.base)
