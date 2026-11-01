"""SFVR, the rollback netplay mod, read from its panel's Dear ImGui frames.

SFVR (sfvr.pages.dev) loads beside the game as sfv_rollback.dll, through an
xinput1_3.dll beside StreetFighterV.exe, and draws its own panel over the
game with Dear ImGui 1.91.9b: hosting and joining matches, its lobby, its
settings, and short notices ("Player Two joined"). F1, or Back and Start on a
pad, opens the panel, and the game gets no input while it is open. None of it
goes through Scaleform, so the reader in `scaleform` never sees any of it.

ImGui keeps no text once a frame is built, only the triangles it drew. Each
character is a quad whose four corners carry that character's place in the
font atlas as texture coordinates, so reading the last frame's vertices out
of the game and matching each quad's coordinates against the fonts' glyph
tables gives back the exact text, where it sits and in what colour. ImGui's
own navigation state says which item has focus and the rectangle it covers,
so the focused item is whatever text lies inside that rectangle. Nothing is
recognised off the picture, and the game is only read, as everywhere else.

The structures were measured on SFVR 0.2.2 (1 November 2026). SFVR builds
ImGui without docking, and the only copy on hand was the docking branch, so
the offsets below were taken from that copy's header where the two agree and
from the live game where they do not (`tools/record_netplay.py` shows what
they read). The context is found again on every start by checking each
pointer in the mod's data against several of these at once, so a new build
of SFVR on the same ImGui is followed; a build on another ImGui fails that
check and the panel stays silent rather than misreading.
"""

from __future__ import annotations

import re
import struct
import time
from dataclasses import dataclass, field

import numpy as np

from .memory import ProcessMemory, find_pid
from .scaleform import phrase

EXE = "StreetFighterV.exe"
MODULE_PREFIX = "sfv_rollback"

# ImGuiContext (ImGui 1.91.9b, no docking).
CTX_INITIALIZED = 0x0
CTX_IO = 0x8
IO_INI_SAVING_RATE = CTX_IO + 0x14
IO_FONTS = CTX_IO + 0x30
CTX_COLORS = 0xD24          # Style.Colors[], RGBA floats
CTX_FRAME = 0x12F0          # FrameCount, which moves only while SFVR draws,
CTX_FRAME_RENDERED = 0x12F8  # and FrameCountRendered, equal to it once a frame is whole
CTX_WINDOWS = 0x1348
CTX_VIEWPORTS = 0x1EE8
CTX_NAV_ID = 0x1EFC
CTX_NAV_WINDOW = 0x1F00
CTX_NAV_LAYER = 0x1F0C
CTX_SPAN = 0x1F20           # read in one piece to check a candidate context

# ImGuiWindow
WIN_CTX = 0x0
WIN_NAME = 0x8
WIN_CURSOR_START = 0x128    # DC.CursorStartPos, what NavRectRel is relative to
WIN_NAV_RECT = 0x3E8        # NavRectRel[2]

# ImGuiViewportP, ImDrawData, ImDrawList, ImFontAtlas, ImFont
VIEWPORT_DEFAULT_ID = 0x11111111
VIEWPORT_DRAW_DATA = 0x50
DRAW_DATA_LISTS = 0x10
DRAW_LIST_VERTICES = 0x20
DRAW_LIST_OWNER = 0xD0
ATLAS_FONTS = 0x50
FONT_SIZE = 0x14
FONT_GLYPHS = 0x28
GLYPH_SIZE = 0x28

COL_TEXT_DISABLED = 1       # ImGuiCol_TextDisabled: hint text in an empty box
COL_FRAME_BG = (7, 8, 9)    # FrameBg, Hovered, Active: a tick box's square, among others
COL_CHECK_MARK = 18         # CheckMark: the tick in it

VERTEX = np.dtype([("x", "<f4"), ("y", "<f4"), ("u", "<u4"), ("v", "<u4"), ("col", "<u4")])

PANEL = "###panel"          # the panel's window; its child windows start with this
TOASTS = "##toasts"         # the notices, which also show with the panel closed
# The panel's tabs, as SFVR names them. The first changes with what a session
# is doing.
TABS = {"Match", "Connecting", "Loading", "Watching", "In a match", "Settings", "Debug"}
# A match code: six of these, as the panel's own keyboard offers them.
CODE_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE = re.compile(f"[{CODE_LETTERS}]{{6}}")
CODE_SO_FAR = re.compile(f"[{CODE_LETTERS}]{{1,6}}")
# The code box draws in SFVR's 60 pixel font; a code half typed is told from
# a word by that.
CODE_FONT = 40.0
# Disabled items are drawn at the style's DisabledAlpha, 0.6.
DISABLED_ALPHA = 0xD0
# How often to look for SFVR while it cannot be found. Looking walks the
# mod's data and costs a few hundred reads.
ATTACH_RETRY = 3.0
# A widget's label sits this close to its right, ImGui's ItemInnerSpacing
# (10 here); the next widget along is further, its text further still.
LABEL_GAP = 16
# How long the panel must stay gone to be closed rather than resizing.
CLOSE_DELAY = 0.2


@dataclass(frozen=True)
class Run:
    """One line of text as ImGui drew it, in screen pixels."""
    text: str
    left: float
    top: float
    right: float
    bottom: float
    rgb: int                # as ImGui packs it, 0xBBGGRR
    alpha: int
    window: str             # the window whose draw list holds it
    font: int = 0
    size: float = 0.0       # the font's height as drawn, in pixels

    @property
    def disabled(self) -> bool:
        return self.alpha < DISABLED_ALPHA

    def inside(self, rect: tuple[float, float, float, float], slack: float = 2.0) -> bool:
        x0, y0, x1, y1 = rect
        return (self.left >= x0 - slack and self.right <= x1 + slack
                and self.top >= y0 - slack and self.bottom <= y1 + slack)


@dataclass(frozen=True)
class Reading:
    """What SFVR drew in its latest frame."""
    frame: int
    runs: tuple[Run, ...]
    focus_id: int = 0
    focus_window: str = ""
    focus: tuple[float, float, float, float] | None = None
    hint_rgb: int = -1      # the colour of hint text, TextDisabled
    checked: bool | None = None   # the focused item is a tick box, ticked or not

    @property
    def panel(self) -> list[Run]:
        return [r for r in self.runs if r.window.startswith(PANEL)]

    @property
    def open(self) -> bool:
        return bool(self.panel)

    @property
    def toasts(self) -> list[Run]:
        return [r for r in self.runs if r.window == TOASTS]

    def focused(self) -> list[Run]:
        """The text inside the focused item, in reading order.

        The item may be in the panel or in a list it opened, such as a combo's
        choices, which ImGui draws as a window of its own.
        """
        if self.focus is None or not self.open:
            return []
        name = self.focus_window
        return sorted((r for r in self.runs if (r.window == name or r.window.startswith(name + "/"))
                       and r.inside(self.focus)), key=lambda r: (r.top, r.left))

    def label(self, focused: list[Run]) -> str:
        """The focused widget's label, drawn just to its right as ImGui does:
        "You are" beside a list showing "P1", "Latency (ms)" beside a slider."""
        if self.focus is None or not focused:
            return ""
        x0, y0, x1, y1 = self.focus
        beside = [r for r in self.runs if r.window == focused[0].window and r not in focused
                  and 0 <= r.left - x1 <= LABEL_GAP and r.top < y1 and r.bottom > y0]
        return tidy(min(beside, key=lambda r: r.left).text) if beside else ""


# ------------------------------------------------------------------ decoding
class Glyphs:
    """Every font's glyphs, found by the texture coordinates of their corners."""

    def __init__(self, glyphs: list[tuple], sizes: dict[int, float] | None = None) -> None:
        # Each: codepoint, advance, x0, y0, x1, y1, u0, v0, u1, v1 (raw float bits for
        # u and v), font index. Spaces draw nothing; their advance is kept per font.
        # `sizes` is each font's height.
        self.sizes = sizes or {}
        self.spaces: dict[int, float] = {}
        self.table: dict[int, tuple] = {}
        for cp, adv, x0, y0, x1, y1, u0, v0, u1, v1, font in glyphs:
            if cp == 32:
                self.spaces[font] = adv
            if x1 > x0:
                self.table[(u0 << 32) | v0] = (chr(cp), adv, x0, y0, x1, (u1 << 32) | v1, font)
        self.keys = np.array(sorted(self.table), dtype=np.uint64)

    def __len__(self) -> int:
        return len(self.table)


def decode(verts: np.ndarray, glyphs: Glyphs, window: str, mask: np.ndarray | None = None) -> list[Run]:
    """The lines of text in one draw list's vertices.

    ImGui writes each character as four vertices, top left first and bottom
    right third, so a vertex whose texture coordinates are a glyph's top left,
    two before one carrying the same glyph's bottom right, starts a character.
    Characters of one call follow each other with the font's advance between
    them; a gap of whole spaces is a space, and anything else begins a new line
    of text, as a new widget does. A run's left is its pen position, where
    ImGui put the text, so a box's typed text lines up with its hint. `mask`,
    if given, is marked at every vertex belonging to a character.
    """
    if len(verts) < 4 or not len(glyphs):
        return []
    keys = (verts["u"].astype(np.uint64) << np.uint64(32)) | verts["v"].astype(np.uint64)
    where = np.searchsorted(glyphs.keys, keys)
    where[where >= len(glyphs.keys)] = 0
    starts = np.nonzero(glyphs.keys[where] == keys)[0]
    runs: list[dict] = []
    cur: dict | None = None
    after = -1
    for i in starts:
        i = int(i)
        if i < after or i + 2 >= len(verts):
            continue
        ch, adv, gx0, gy0, gx1, corner, font = glyphs.table[int(keys[i])]
        if int(keys[i + 2]) != corner:
            continue
        after = i + 4
        if mask is not None:
            mask[i:i + 4] = True
        x, y = float(verts["x"][i]), float(verts["y"][i])
        x2, y2 = float(verts["x"][i + 2]), float(verts["y"][i + 2])
        scale = (x2 - x) / (gx1 - gx0)
        origin, top = x - gx0 * scale, y - gy0 * scale
        space = glyphs.spaces.get(font, adv * 0.5) * scale
        joined = False
        if cur is not None and cur["font"] == font and abs(cur["top"] - top) < 1.0:
            gap = origin - cur["next"]
            if -0.5 <= gap < space * 3.5:
                cur["text"] += " " * (round(gap / space) if space > 0 else 0) + ch
                joined = True
        if not joined:
            col = int(verts["col"][i])
            cur = {"text": ch, "left": origin, "top": top, "font": font,
                   "size": glyphs.sizes.get(font, 0.0) * scale,
                   "rgb": col & 0xFFFFFF, "alpha": col >> 24}
            runs.append(cur)
        cur["next"] = origin + adv * scale
        cur["right"], cur["bottom"] = x2, y2
    return [Run(r["text"], r["left"], r["top"], r["right"], r["bottom"], r["rgb"], r["alpha"],
                window, r["font"], r["size"]) for r in runs]


# ------------------------------------------------------------------- reading
class PanelReader:
    """SFVR's frames out of the running game, once its ImGui context is found."""

    def __init__(self, note=None) -> None:
        self.note = note or (lambda text: None)
        self.mem: ProcessMemory | None = None
        self.ctx = 0
        self.glyphs: Glyphs | None = None
        self.hint_rgb = -1
        self.frame_rgbs: set[int] = set()
        self.check_rgb = -1
        self._owners: dict[int, str] = {}
        self._last: Reading | None = None
        self._retry_at = 0.0
        self._missing_said = False

    @property
    def attached(self) -> bool:
        return self.ctx != 0

    def detach(self) -> None:
        if self.mem is not None:
            self.mem.close()
        self.mem, self.ctx, self.glyphs, self._last = None, 0, None, None
        self._owners.clear()

    def attach(self) -> bool:
        """Find the game, SFVR in it, and its ImGui context, at most every few seconds."""
        if self.ctx:
            return True
        now = time.monotonic()
        if now < self._retry_at:
            return False
        self._retry_at = now + ATTACH_RETRY
        pid = find_pid(EXE, "Binaries", require_path=True)
        if not pid:
            return False
        try:
            mem = ProcessMemory(pid)
        except OSError:
            return False
        module = next((m for m in mem.modules() if m.name.lower().startswith(MODULE_PREFIX)), None)
        if module is None:
            mem.close()
            return False
        ctx = find_context(mem, module)
        if not ctx:
            mem.close()
            if not self._missing_said:
                self._missing_said = True
                self.note(f"netplay: {module.name} is loaded but its panel was not found "
                          "(not drawn yet, or a different ImGui)")
            return False
        glyphs = read_glyphs(mem, ctx)
        if glyphs is None:
            mem.close()
            return False
        self.mem, self.ctx, self.glyphs = mem, ctx, glyphs
        count = COL_CHECK_MARK + 1
        colours = mem.read(ctx + CTX_COLORS, 16 * count)
        if colours and len(colours) == 16 * count:
            packed = [packed_rgb(*struct.unpack_from("<3f", colours, 16 * k)) for k in range(count)]
            self.hint_rgb = packed[COL_TEXT_DISABLED]
            self.frame_rgbs = {packed[k] for k in COL_FRAME_BG}
            self.check_rgb = packed[COL_CHECK_MARK]
        self.note(f"netplay: {module.name}'s panel found, {len(glyphs)} glyphs")
        self._missing_said = False
        return True

    def read(self) -> Reading | None:
        """The latest frame, or None while SFVR cannot be read.

        The frame number moves only while SFVR draws, so an unchanged number
        hands back the last reading without reading anything else. A frame
        built while it was being read shows as a changed number afterwards,
        and is read again.
        """
        if not self.attach():
            return None
        try:
            for _ in range(5):
                frame = self._whole_frame()
                if frame is None:
                    time.sleep(0.002)
                    continue
                if self._last is not None and self._last.frame == frame:
                    return self._last
                reading = self._read_frame(frame)
                if self._whole_frame() == frame:
                    self._last = reading
                    return reading
            return self._last
        except (OSError, struct.error, ValueError, IndexError) as exc:
            self.note(f"netplay: reading stopped ({exc!r}); looking again")
            self.detach()
            return None

    def _whole_frame(self) -> int | None:
        """SFVR's frame number, or None while it is part way through building one.

        The vertices are rewritten between starting a frame and rendering it;
        read then, the panel came back with half its text, heard as "Netplay
        closed" and "Netplay" again, or a letter said twice.
        """
        size = CTX_FRAME_RENDERED - CTX_FRAME + 4
        raw = self.mem.read(self.ctx + CTX_FRAME, size)
        if not raw or len(raw) < size:
            raise OSError("frame unreadable")
        frame = struct.unpack_from("<i", raw, 0)[0]
        rendered = struct.unpack_from("<i", raw, size - 4)[0]
        return frame if frame == rendered else None

    def _read_frame(self, frame: int) -> Reading:
        mem = self.mem
        focus_id, name, focus = self._focus()
        count, viewports = vector(mem, self.ctx + CTX_VIEWPORTS)
        if count < 1:
            raise OSError("no viewport")
        draw_data = mem.ptr(viewports) + VIEWPORT_DRAW_DATA
        valid = mem.read(draw_data, 1)
        runs: list[Run] = []
        checked = None
        if valid and valid[0]:
            count, lists = vector(mem, draw_data + DRAW_DATA_LISTS)
            pointers = mem.read(lists, 8 * count) if 0 < count < 256 else b""
            for (dl,) in struct.iter_unpack("<Q", pointers or b""):
                n, data = vector(mem, dl + DRAW_LIST_VERTICES)
                if not 0 < n < 1_000_000:
                    continue
                raw = mem.read(data, n * VERTEX.itemsize)
                if not raw:
                    continue
                verts = np.frombuffer(raw[: len(raw) // VERTEX.itemsize * VERTEX.itemsize], dtype=VERTEX)
                owner = self._owner(dl)
                if focus is not None and owner == name:
                    mask = np.zeros(len(verts), dtype=bool)
                    runs += decode(verts, self.glyphs, owner, mask)
                    checked = tick_box(verts, mask, focus, self.frame_rgbs, self.check_rgb)
                else:
                    runs += decode(verts, self.glyphs, owner)
        return Reading(frame, tuple(runs), focus_id, name, focus, self.hint_rgb, checked)

    def _focus(self) -> tuple[int, str, tuple[float, float, float, float] | None]:
        """The focused item's id, its window's name and its rectangle on screen."""
        mem = self.mem
        focus_id = mem.u32(self.ctx + CTX_NAV_ID) or 0
        window = mem.ptr(self.ctx + CTX_NAV_WINDOW) or 0
        focus, name = None, ""
        if window:
            name = mem.cstring(mem.ptr(window + WIN_NAME) or 0, 64) or ""
            layer = mem.i32(self.ctx + CTX_NAV_LAYER) or 0
            start = mem.read(window + WIN_CURSOR_START, 8)
            rect = mem.read(window + WIN_NAV_RECT + 16 * (1 if layer == 1 else 0), 16)
            if start and rect and len(start) == 8 and len(rect) == 16:
                sx, sy = struct.unpack("<ff", start)
                x0, y0, x1, y1 = struct.unpack("<4f", rect)
                if x1 > x0 and y1 > y0:
                    focus = (x0 + sx, y0 + sy, x1 + sx, y1 + sy)
        return focus_id, name, focus

    def _owner(self, draw_list: int) -> str:
        name = self._owners.get(draw_list)
        if name is None:
            name = self.mem.cstring(self.mem.ptr(draw_list + DRAW_LIST_OWNER) or 0, 64) or ""
            self._owners[draw_list] = name
        return name


def packed_rgb(r: float, g: float, b: float) -> int:
    """A style colour as ImGui packs it into a vertex, 0xBBGGRR."""
    def byte(c: float) -> int:
        return max(0, min(255, int(c * 255.0 + 0.5)))
    return byte(r) | byte(g) << 8 | byte(b) << 16


def tick_box(verts: np.ndarray, mask: np.ndarray, rect: tuple[float, float, float, float],
             frame_rgbs: set[int], check_rgb: int) -> bool | None:
    """Whether the item in `rect` is a tick box, and if so whether it is ticked.

    A tick box is a square frame at the left of its item, as tall as the item,
    in a frame colour; ticked, it holds a line in the check mark colour. Text
    boxes, lists and sliders have frames too, but wide ones.
    """
    if not frame_rgbs:
        return None
    x0, y0, x1, y1 = rect
    xs, ys = verts["x"], verts["y"]
    shape = ~mask & (xs >= x0 - 1) & (xs <= x1 + 1) & (ys >= y0 - 1) & (ys <= y1 + 1)
    colours = verts["col"] & 0xFFFFFF
    frame = shape & np.isin(colours, np.array(sorted(frame_rgbs), dtype=np.uint32))
    if not frame.any():
        return None
    fx0, fx1 = float(xs[frame].min()), float(xs[frame].max())
    fy0, fy1 = float(ys[frame].min()), float(ys[frame].max())
    side = y1 - y0
    if abs((fx1 - fx0) - side) > 6 or abs((fy1 - fy0) - side) > 6 or fx0 - x0 > 6:
        return None
    tick = shape & (colours == check_rgb) & (xs >= fx0) & (xs <= fx1) & (ys >= fy0) & (ys <= fy1)
    return bool(tick.any())


def vector(mem: ProcessMemory, address: int) -> tuple[int, int]:
    """An ImVector's size and data pointer."""
    raw = mem.read(address, 16)
    if not raw or len(raw) < 16:
        raise OSError(f"cannot read a vector at {address:#x}")
    size, _capacity, data = struct.unpack("<iiQ", raw)
    return size, data


def find_context(mem: ProcessMemory, module) -> int:
    """SFVR's ImGuiContext: the pointer in its data that passes every check.

    Initialised, a sane .ini saving rate, a font atlas, windows that all name
    this context as theirs, and one viewport with ImGui's default viewport id.
    No other block of memory looks like that.
    """
    data = mem.section(module, ".data")
    raw = mem.read(data.base, data.size) if data else None
    if not raw:
        return 0
    seen: set[int] = set()
    for (p,) in struct.iter_unpack("<Q", raw[: len(raw) // 8 * 8]):
        if p < 0x10000 or p > 0x7FFFFFFFFFFF or module.base <= p < module.end or p in seen:
            continue
        seen.add(p)
        if is_context(mem, p):
            return p
    return 0


def is_context(mem: ProcessMemory, p: int) -> bool:
    head = mem.read(p, CTX_SPAN)
    if not head or len(head) < CTX_SPAN or head[CTX_INITIALIZED] != 1:
        return False
    rate = struct.unpack_from("<f", head, IO_INI_SAVING_RATE)[0]
    fonts = struct.unpack_from("<Q", head, IO_FONTS)[0]
    if not 0.0 < rate <= 600.0 or not fonts:
        return False
    count, _cap, windows = struct.unpack_from("<iiQ", head, CTX_WINDOWS)
    if not 0 < count < 1000:
        return False
    first = mem.ptr(windows)
    if not first or mem.ptr(first + WIN_CTX) != p:
        return False
    count, _cap, viewports = struct.unpack_from("<iiQ", head, CTX_VIEWPORTS)
    if count != 1:
        return False
    viewport = mem.ptr(viewports)
    return bool(viewport) and mem.u32(viewport) == VIEWPORT_DEFAULT_ID


def read_glyphs(mem: ProcessMemory, ctx: int) -> Glyphs | None:
    atlas = mem.ptr(ctx + IO_FONTS)
    if not atlas:
        return None
    count, fonts = vector(mem, atlas + ATLAS_FONTS)
    if not 0 < count < 64:
        return None
    out: list[tuple] = []
    sizes: dict[int, float] = {}
    for index in range(count):
        font = mem.ptr(fonts + 8 * index)
        if not font:
            continue
        sizes[index] = mem.f32(font + FONT_SIZE) or 0.0
        n, data = vector(mem, font + FONT_GLYPHS)
        raw = mem.read(data, n * GLYPH_SIZE) if 0 < n < 100_000 else None
        if not raw:
            continue
        for k in range(len(raw) // GLYPH_SIZE):
            bits, adv, x0, y0, x1, y1 = struct.unpack_from("<I5f", raw, k * GLYPH_SIZE)
            u0, v0, u1, v1 = struct.unpack_from("<4I", raw, k * GLYPH_SIZE + 0x18)
            out.append((bits >> 2, adv, x0, y0, x1, y1, u0, v0, u1, v1, index))
    return Glyphs(out, sizes) if out else None


# ----------------------------------------------------------------- narration
def tidy(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def spell(text: str) -> str:
    """A code letter by letter, since heard as a word it says nothing of its spelling."""
    return " ".join(text)


def lines(runs: list[Run]) -> list[list[Run]]:
    """Runs grouped into rows, top to bottom, each left to right."""
    rows: list[list[Run]] = []
    for r in sorted(runs, key=lambda r: (r.top, r.left)):
        if rows and r.top < rows[-1][0].bottom - 2 and r.top >= rows[-1][0].top - 2:
            rows[-1].append(r)
        else:
            rows.append([r])
    return [sorted(row, key=lambda r: r.left) for row in rows]


def key(run: Run) -> tuple:
    """What a text is, setting aside numbers that tick over: a ping, a count.
    The font tells a letter typed into the code box from the same letter's key."""
    return run.window, run.font, re.sub(r"\d+", "#", tidy(run.text))


@dataclass
class Line:
    """A line for the review cursor (Alt up and down), shaped like a game text."""
    text: str
    selected: bool = False


@dataclass
class PanelNarrator:
    """Decides what to say as SFVR's panel and notices change.

    The panel opening and closing, the item with focus as it moves (a tab said
    as a tab, an empty box as empty), what appears on the panel while focus
    stays put or after a button changed the screen (a code typed or pasted,
    spelled; "Waiting for the other player..."), and each notice once. While
    focus is on a tab the tab's contents are left to be moved through, or read
    with Alt A.
    """
    was_open: bool = False
    focus_said: tuple = ()      # the focused item's id, its text and its tick
    known: set = field(default_factory=set)
    toasts: set = field(default_factory=set)
    gone_since: float | None = None   # when the panel stopped showing, while it may come back

    def reset(self) -> None:
        self.was_open, self.focus_said, self.gone_since = False, (), None
        self.known, self.toasts = set(), set()

    def step(self, reading: Reading | None, now: float | None = None) -> str | None:
        if reading is None:
            return None
        now = time.monotonic() if now is None else now
        said: list[str] = []
        shown = {tidy(r.text) for r in reading.toasts}
        said += [t for t in (tidy(r.text) for r in reading.toasts) if t and t not in self.toasts]
        self.toasts = shown

        is_open = reading.open
        if not is_open:
            # ImGui leaves a window out of a frame or so while it resizes, as
            # the panel does going to the wider Debug tab; heard as "Netplay
            # closed" and "Netplay" again. Closed is closed once it stays gone.
            if self.was_open:
                self.gone_since = now if self.gone_since is None else self.gone_since
                if now - self.gone_since >= CLOSE_DELAY:
                    said.insert(0, "Netplay closed")
                    self.was_open, self.focus_said, self.known, self.gone_since = False, (), set(), None
            return phrase(dedupe(said)) or None
        self.gone_since = None

        focused = reading.focused()
        now_known = {key(r) for r in reading.panel}
        focus = (reading.focus_id, tuple(tidy(r.text) for r in focused), reading.checked)
        before = self.focus_said or (None, None, None)
        if not self.was_open:
            said.insert(0, "Netplay")
            said.append(self.describe(reading, focused))
        elif focus[0] != before[0]:
            # Pressing a button that changes the screen moves focus as well,
            # onto an item that was not there before. What the new screen
            # says above that item comes first, as a dialog's text before its
            # button; what lies below is the rest of the screen, to move
            # through. Focus moving among what was already there says only
            # the item.
            fresh = any(key(r) not in self.known for r in focused)
            if fresh and reading.focus is not None and not on_tab(reading, focused):
                said += self.changes(reading, focused, above=reading.focus[1])
            said.append(self.describe(reading, focused))
        elif focus[1] == before[1] and focus[2] != before[2] and focus[2] is not None:
            # The same tick box, ticked or unticked.
            said.append("checked" if focus[2] else "not checked")
        elif not on_tab(reading, focused):
            said += self.changes(reading, focused)
            if focus[1] != before[1]:
                # The same item showing something else: a slider moved, a code
                # typed into the box with focus, or ImGui keeping focus on a
                # button that has gone, now over other text.
                said.append(self.describe(reading, focused, with_label=False))
        self.was_open, self.focus_said, self.known = True, focus, now_known
        return phrase(dedupe(said)) or None

    def describe(self, reading: Reading, focused: list[Run], with_label: bool = True) -> str:
        """The focused item, as heard when moving onto it: its label first, if
        it has one beside it, then what it shows, and a tick box's tick."""
        if not focused:
            return ""
        if on_tab(reading, focused):
            return f"{tidy(focused[0].text)} tab"
        if all(r.rgb == reading.hint_rgb for r in focused):
            shows = f"{tidy(' '.join(r.text for r in focused))}, empty"
        else:
            shows = phrase([words(r) for r in focused])
        if reading.checked is not None:
            shows += ", checked" if reading.checked else ", not checked"
        label = reading.label(focused) if with_label else ""
        return f"{label}, {shows}" if label else shows

    def changes(self, reading: Reading, focused: list[Run], above: float | None = None) -> list[str]:
        """New text on the panel, other than the focused item's, above a line if given."""
        new = [r for r in reading.panel if key(r) not in self.known and not r.disabled and r not in focused
               and (above is None or r.bottom <= above + 2)]
        if not new:
            return []
        # A keyboard of single keys arriving with the rest of a screen is
        # moved through, not read out; one character on its own in the code
        # box is the box filling in.
        singles = [r for r in new if len(tidy(r.text)) == 1 and r.size < CODE_FONT]
        if len(singles) >= 4:
            new = [r for r in new if r not in singles]
        out = []
        rows = lines(new)
        for i, row in enumerate(rows):
            for r in row:
                before = rows[i - 1][-1].text.strip() if i else ""
                if r.rgb == reading.hint_rgb and is_hint(r):
                    out.append(f"{tidy(r.text)}, empty")
                else:
                    out.append(words(r, before))
        return out


def is_hint(run: Run) -> bool:
    """A box's hint, the word it shows while empty ("CODE", "(Steam name)"),
    rather than the version or a line of help in the same colour."""
    return bool(re.fullmatch(r"\(?[A-Za-z]+( [A-Za-z]+)?\)?", tidy(run.text)))


def words(run: Run, before: str = "") -> str:
    """A text as it should be said: a code spelled, anything else as it is.

    A code is spelled whole wherever it shows with a digit in it or after a
    colon ("Send this code to the other player:"), and part typed in the code
    box's big font; a word in the code's letters elsewhere ("READY") is a word.
    """
    text = tidy(run.text)
    if (CODE_SO_FAR.fullmatch(text) and run.size >= CODE_FONT) or (
            CODE.fullmatch(text) and (any(c.isdigit() for c in text) or before.endswith(":"))):
        return spell(text)
    return text


def on_tab(reading: Reading, focused: list[Run]) -> bool:
    """Focus is on one of the panel's tabs: a tab's name, in a row of tab names."""
    if len(focused) != 1 or tidy(focused[0].text) not in TABS:
        return False
    row = [r for r in reading.panel if abs(r.top - focused[0].top) < 3 and tidy(r.text) in TABS]
    return len(row) >= 2


def dedupe(parts: list[str]) -> list[str]:
    out: list[str] = []
    for p in parts:
        if p and p not in out:
            out.append(p)
    return out


def read_focus(reading: Reading) -> str:
    """Alt R with the panel open: the focused item, then the line just under it.

    The line under a big button is what it does ("You get a code to send to
    the other player."); a description is left-aligned with its item and
    close beneath it, where a neighbouring item would be further down.
    """
    narrator = PanelNarrator()
    focused = reading.focused()
    said = narrator.describe(reading, focused) if focused else "Nothing focused"
    if focused and reading.focus is not None:
        x0, _y0, _x1, y1 = reading.focus
        under = [r for r in reading.panel if 0 <= r.top - y1 < 15 and abs(r.left - x0) < 6
                 and len(tidy(r.text)) > 1 and not r.disabled]
        if under:
            said = phrase([said] + [tidy(r.text) for r in sorted(under, key=lambda r: r.top)])
    shown = [tidy(r.text) for r in reading.runs if r.window.startswith("##Tooltip")]
    return phrase([said] + shown)


def read_lines(reading: Reading) -> list[Line]:
    """Alt A with the panel open: every line of it, an unavailable item said so."""
    out = []
    focused = set(id(r) for r in reading.focused())
    for row in lines(reading.panel):
        words = []
        for r in row:
            text = tidy(r.text)
            if r.disabled:
                text += ", unavailable"
            words.append(text)
        out.append(Line(", ".join(words), any(id(r) in focused for r in row)))
    return out
