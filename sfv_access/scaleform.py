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

import bisect
import math
import struct
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
LISTENER_OWNER = -0x98       # pointer to that field, relative to the listener
TEXT_PARAGRAPHS = 0x18       # array of Paragraph*
TEXT_PARAGRAPH_COUNT = 0x20
DISPLAY_PARENT = 0x38
DISPLAY_RENDER_NODE = 0x48
DISPLAY_CHILD_COUNT = 0xE0   # beside the child array at 0xD8
RENDER_NODE_DATA = 0x10
NODE_FLAGS = 0x0A            # u16; bit 0 set while visible, for parents at least
NODE_MATRIX = 0x10           # 2 by 4 floats: sx, shx, 0, tx / shy, sy, 0, ty
NODE_CXFORM = 0x50           # multiply r, g, b, a then add r, g, b, a

NODE_VISIBLE = 0x0001
TWIPS_PER_PIXEL = 20.0
STAGE_WIDTH, STAGE_HEIGHT = 1920, 1080

HIGHLIGHT_TINT = (1.0, 0.89, 0.549)
TINT_TOLERANCE = 0.05

# Labels longer than this are not answers on a button. It keeps the choice rule
# off the banner, whose date line and title sit side by side like two buttons.
CHOICE_TEXT_LIMIT = 24

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

MAX_PARAGRAPHS = 512
MAX_PARAGRAPH_CHARS = 4096
MAX_DEPTH = 40


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

    @property
    def highlighted(self) -> bool:
        return all(abs(c - h) <= TINT_TOLERANCE for c, h in zip(self.tint, HIGHLIGHT_TINT))

    @property
    def selected(self) -> bool:
        return self.highlighted or self.chosen

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
        tuple(it.text for it in items if it.selected),
        foot.text if foot else None,
    )


def _where(it: TextItem):
    return (round(it.x), round(it.y), it.text)


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
    was_lit = {_where(it) for it in before if it.selected}
    lit = [it for it in after if it.selected]
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
        return _unique(intro + [it.text for it in fresh])
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
        # The pages that held text at the last full sweep. The sweep of every
        # page takes a third of a second, nearly all of a read; the text lives
        # in a few dozen of them, a couple of megabytes, which take a thousandth.
        self._text_pages = None

    # ------------------------------------------------------------- discovery
    def refresh_pages(self) -> list[int]:
        """Sweep every page, and remember which ones hold text for quick reads."""
        pages = sorted(self.heap_pages(), key=lambda r: r.base)
        found = self.docviews(pages)
        starts = [r.base for r in pages]
        holding = {bisect.bisect_right(starts, dv) - 1 for dv in found}
        self._text_pages = [pages[i] for i in sorted(holding) if i >= 0]
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

    # ------------------------------------------------------------- selection
    def mark_choices(self, items: list[TextItem]) -> None:
        """Find the selected button in a group of buttons with plain labels.

        A group is a container whose children each hold exactly one short
        label. The selected child has more children of its own than any other,
        the outline and fill that mark it, and its label sits deeper inside it.
        Both must hold, and for exactly one child, before anything is marked.
        Gold elsewhere on screen does not stop it: a prompt opened from a menu
        sits over that menu's gold entry.
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
            layers = {slot: self.pm.u32(slot + DISPLAY_CHILD_COUNT) or 0 for slot in slots}
            most = max(layers.values())
            if list(layers.values()).count(most) != 1:
                continue
            winner = next(slot for slot, n in layers.items() if n == most)
            (item, nesting), = slots[winner]
            if all(nesting > held[0][1] for slot, held in slots.items() if slot != winner):
                item.chosen = True
                item.group = container

    # ----------------------------------------------------------------- reads
    def items(self, everything: bool = False, quick: bool = False) -> list[TextItem]:
        """Text on screen in reading order. `everything` keeps the leftovers.

        `quick` looks only in the pages that held text at the last full sweep,
        for polling. Something drawn in a page that had no text before is
        missed until `refresh_pages` runs again, so a caller polling quickly
        should keep calling that in the background.
        """
        if quick and self._text_pages is not None:
            docviews = self.docviews(self._text_pages)
        else:
            docviews = self.refresh_pages()
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
            item = TextItem(text, x, y, tint, len(chain), dv, chain, hidden=hidden)
            if everything or item.shown:
                out.append(item)
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
