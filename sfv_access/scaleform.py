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

import math
import struct
import threading
import time
from collections import defaultdict
from dataclasses import dataclass

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
DISPLAY_PARENT = 0x38
DISPLAY_RENDER_NODE = 0x48
DISPLAY_CHILDREN = 0xD8      # array of children, an object pointer per entry
DISPLAY_CHILD_COUNT = 0xE0
DISPLAY_CHILD_STRIDE = 16
RENDER_NODE_DATA = 0x10
NODE_FLAGS = 0x0A            # u16; bit 0 set while visible, for parents at least
NODE_MATRIX = 0x10           # 2 by 4 floats: sx, shx, 0, tx / shy, sy, 0, ty
NODE_CXFORM = 0x50           # multiply r, g, b, a then add r, g, b, a

NODE_VISIBLE = 0x0001
TWIPS_PER_PIXEL = 20.0
STAGE_WIDTH, STAGE_HEIGHT = 1920, 1080

HIGHLIGHT_TINT = (1.0, 0.89, 0.549)
TINT_TOLERANCE = 0.05
UNAVAILABLE_GREY = 0.6

# Labels longer than this are not answers on a button. It keeps the choice rule
# off the banner, whose date line and title sit side by side like two buttons.
CHOICE_TEXT_LIMIT = 24
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
        """Attached, not hidden, not transparent, on the stage, and real text."""
        return (
            self.depth >= 2
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


def grid_tiles(children, obj) -> list[int]:
    """The tiles of `obj` if it is a grid: four or more children with the same number of parts."""
    inside = children(obj)
    if len(inside) < GRID_MIN_TILES:
        return []
    parts = [len(children(k)) for k in inside]
    usual = max(set(parts), key=parts.count)
    tiles = [k for k, n in zip(inside, parts) if n == usual]
    return tiles if usual >= 2 and len(tiles) >= GRID_MIN_TILES else []


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
    """
    if len(rows) < GRID_MIN_TILES:
        return None
    parts = [children(row) for row in rows]
    width = len(parts[0])
    if width < 2 or any(len(p) != width for p in parts):
        return None
    for index in range(width):
        shown = []
        for row, row_parts in zip(rows, parts):
            seen = appearance(row_parts[index])
            if seen is None:
                break
            shown.append(bool(seen[1] & NODE_VISIBLE))
        else:
            if shown.count(True) == 1:
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
        # Picture grids under the movies showing text, found by walking the
        # display tree, which is too slow to do on every read. Only the
        # selected tile is checked each read.
        self._grids: dict[int, list[int]] = {}
        self._text_grids: set[int] = set()   # grids seen holding text, never pictures
        self._roots: set[int] = set()

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
            chars = self.pm.ptr(para)
            size = self.pm.u64(para + 8)
            if not chars or not size or size > MAX_PARAGRAPH_CHARS:
                continue
            raw = self.pm.read(chars, size * 2)
            if raw:
                parts.append(raw.decode("utf-16-le", "replace").rstrip("\0"))
        # Scaleform ends a paragraph with a carriage return.
        return "\n".join(p.rstrip("\r") for p in parts)

    # ------------------------------------------------------------- placement
    def _node(self, obj: int):
        entry = self.pm.ptr(obj + DISPLAY_RENDER_NODE)
        data = self.pm.ptr(entry + RENDER_NODE_DATA) if entry else None
        raw = self.pm.read(data, NODE_CXFORM + 0x20) if data else None
        if not raw:
            return None
        flags = struct.unpack_from("<H", raw, NODE_FLAGS)[0]
        m = struct.unpack_from("<8f", raw, NODE_MATRIX)
        cx = struct.unpack_from("<4f", raw, NODE_CXFORM)
        if not all(math.isfinite(v) and abs(v) < 1e7 for v in m + cx):
            return None
        return (m[0], m[1], m[3], m[4], m[5], m[7]), cx, flags

    def place(self, docview: int):
        """The owner chain, stage position, tint and hiddenness of a DocView's field."""
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
        x, y = world[2] / TWIPS_PER_PIXEL, world[5] / TWIPS_PER_PIXEL
        return tuple(chain), x, y, tuple(tint), hidden

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
        """
        shown = [it for it in items if it.shown]
        groups: dict[int, dict[int, list]] = defaultdict(lambda: defaultdict(list))
        for it in shown:
            for level in range(1, len(it.chain)):
                groups[it.chain[level]][it.chain[level - 1]].append((it, level - 1))
        for container, slots in groups.items():
            if len(slots) < 2 or any(len(held) != 1 for held in slots.values()):
                continue
            if any(len(held[0][0].text.strip()) > CHOICE_TEXT_LIMIT for held in slots.values()):
                continue
            if self._mark_by_layers(container, slots):
                continue
            self._mark_by_brightness(container, slots)
        self._mark_highlighted_rows(shown, groups)
        self._mark_picture_grids(shown)
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
            if len(slots) < GRID_MIN_TILES:
                continue
            if any(it.highlighted for held in slots.values() for it, _level in held):
                continue
            row = highlighted_row(kids, appearance, grid_tiles(kids, container))
            if row is None:
                continue
            for it in shown:
                if row in it.chain:
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
            docviews = self.docviews(self._scaleform_pages)
        else:
            docviews = self.docviews()
        roots_before = set(self._roots)
        out = []
        for dv in docviews:
            text = self.field_text(dv)
            if text is None:
                continue
            placed = self.place(dv)
            if placed is None:
                if everything:
                    out.append(TextItem(text, -1, -1, (0, 0, 0, 0), 0, dv))
                continue
            chain, x, y, tint, hidden = placed
            raw = self.pm.read(dv + DOCVIEW_SIZE, 8)
            box = tuple(v / TWIPS_PER_PIXEL for v in struct.unpack("<2f", raw)) if raw else (0.0, 0.0)
            item = TextItem(text, x, y, tint, len(chain), dv, chain, hidden=hidden, box=box)
            if everything or item.shown:
                out.append(item)
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
