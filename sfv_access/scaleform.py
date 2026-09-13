"""What Scaleform is drawing, read straight out of the running game.

The interface is Scaleform GFx, which keeps its text and its display tree well
away from anything Unreal describes, so the object reader in `unreal.py` cannot
see it. The pixel reader rebuilds the screen from a picture. This reads the real
thing instead: each text field's exact text, where it sits, the colour it is
tinted, and whether it is showing at all. No recognition, so no misreadings, and
it does not need the game in front.

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
  in twips and a colour transform.
- Multiplying the transforms and colours from the field up to the root gives
  the position on the 1920 by 1080 stage and the tint the text is drawn with.
  A highlighted menu entry is tinted by the multiplier 1.0, 0.89, 0.549, which
  is RGB 255, 227, 140, the gold the pixel reader already looks for. Unselected
  entries on the main menu sit at 0.27 grey.

The layout was found by recording memory while the selection moved and keeping
what followed it, then walking pointers from the text fields until the colour
turned up. `tools/read_scaleform.py` prints the result.

DocViews from screens that have closed stay in the heap until overwritten. They
fail the walk to a render node, or come out detached, hidden or transparent,
and are dropped unless asked for.
"""

from __future__ import annotations

import math
import struct
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
RENDER_NODE_DATA = 0x10
NODE_FLAGS = 0x0A            # u16, bit 0 set while visible
NODE_MATRIX = 0x10           # 2 by 4 floats: sx, shx, 0, tx / shy, sy, 0, ty
NODE_CXFORM = 0x50           # multiply r, g, b, a then add r, g, b, a

NODE_VISIBLE = 0x0001
TWIPS_PER_PIXEL = 20.0
STAGE_WIDTH, STAGE_HEIGHT = 1920, 1080

HIGHLIGHT_TINT = (1.0, 0.89, 0.549)
TINT_TOLERANCE = 0.05

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
    visible: bool
    depth: int               # the field plus each parent above it
    docview: int = 0

    @property
    def highlighted(self) -> bool:
        return all(abs(c - h) <= TINT_TOLERANCE for c, h in zip(self.tint, HIGHLIGHT_TINT))

    @property
    def on_stage(self) -> bool:
        return 0 <= self.x < STAGE_WIDTH and 0 <= self.y < STAGE_HEIGHT

    @property
    def shown(self) -> bool:
        """Visible, attached to a movie, on the stage, and not blank."""
        return (
            self.visible
            and self.depth >= 2
            and self.tint[3] > 0.01
            and self.on_stage
            and bool(self.text.strip())
        )


def footer(items: list[TextItem]) -> TextItem | None:
    """The description line under the menu, if this screen has one."""
    return next((it for it in items if it.y >= FOOTER_TOP and it.x < FOOTER_RIGHT), None)


def selection_key(items: list[TextItem]):
    """What changes when the cursor moves, and does not change on its own.

    The gold text is the usual sign. It is not enough by itself: the main
    menu's icon row, Options, Gallery, Message Log, Login and Exit, carries no
    text, so moving along it lights nothing. The description line changes
    either way, while the adverts that rotate in the banner change neither.
    """
    foot = footer(items)
    return (
        tuple(it.text for it in items if it.highlighted),
        foot.text if foot else None,
    )


def landed_on(before: list[TextItem], after: list[TextItem]) -> list[str]:
    """What to say for a move from the `before` screen to the `after` one.

    The gold text if there is any. Otherwise the text that changed with the
    move, which is how an icon gets its name: the banner switches to OPTIONS
    or EXIT as the icon is reached. Failing that, the description line.
    """
    lit = [it.text for it in after if it.highlighted]
    if lit:
        return lit
    foot = footer(after)
    old = {(round(it.x), round(it.y), it.text) for it in before}
    changed = [
        it.text
        for it in after
        if it is not foot and (round(it.x), round(it.y), it.text) not in old
    ]
    if 0 < len(changed) <= MOVE_TEXT_LIMIT:
        return changed
    return [foot.text] if foot else []


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

    # ------------------------------------------------------------- discovery
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
        values = m + cx
        if not all(math.isfinite(v) and abs(v) < 1e7 for v in values):
            return None
        return flags, (m[0], m[1], m[3], m[4], m[5], m[7]), cx

    def place(self, docview: int):
        """Depth, visibility, stage position and tint of a DocView's field."""
        listener = self.pm.ptr(docview + DOCVIEW_LISTENER)
        obj = self.pm.ptr(listener + LISTENER_OWNER) if listener else None
        if not obj:
            return None
        chain = []
        seen = set()
        while obj and obj not in seen and len(chain) < MAX_DEPTH:
            seen.add(obj)
            node = self._node(obj)
            if node is None:
                break
            chain.append(node)
            obj = self.pm.ptr(obj + DISPLAY_PARENT)
        if not chain:
            return None
        world = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
        tint = [1.0, 1.0, 1.0, 1.0]
        visible = True
        for flags, matrix, cx in reversed(chain):
            world = _compose(world, matrix)
            tint = [t * c for t, c in zip(tint, cx)]
            visible = visible and bool(flags & NODE_VISIBLE)
        return len(chain), visible, world[2] / TWIPS_PER_PIXEL, world[5] / TWIPS_PER_PIXEL, tuple(tint)

    # ----------------------------------------------------------------- reads
    def items(self, everything: bool = False) -> list[TextItem]:
        """Text on screen in reading order. `everything` keeps the leftovers."""
        out = []
        for dv in self.docviews():
            text = self.field_text(dv)
            if text is None:
                continue
            placed = self.place(dv)
            if placed is None:
                if everything:
                    out.append(TextItem(text, -1, -1, (0, 0, 0, 0), False, 0, dv))
                continue
            depth, visible, x, y, tint = placed
            item = TextItem(text, x, y, tint, visible, depth, dv)
            if everything or item.shown:
                out.append(item)
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
