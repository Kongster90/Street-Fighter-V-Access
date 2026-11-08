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
recognised off the picture, and the game is only read, but for one jump in
SFVR that keeps its status line out of the window title (`StatusLine`).

The structures are ImGui 1.92.9b's, without docking, as SFVR 0.3.0 (7
November 2026) builds it: the offsets below came from compiling that
release's headers with the toolchain and printing them, then checking each
against the live game (`tools/record_netplay.py` shows what they read).
SFVR 0.2.x was on ImGui 1.91.9b, whose layout differs throughout; 0.3.0 plays
only 0.3.0, so that one is not kept. The context is found again on every
start by checking each pointer in the mod's data against several of these at
once, so a new build of SFVR on the same ImGui is followed; a build on
another ImGui fails that check and the panel stays silent rather than
misreading.

ImGui 1.92 bakes each font at each size it is drawn at, its glyphs added as
characters are first drawn, into an atlas texture that grows and is packed
again as needed, which moves every glyph. So the glyphs are read from every
baked font in the atlas builder's pool, and read again whenever the pool,
a glyph table or the texture changes (`atlas_key`).
"""

from __future__ import annotations

import ctypes
import re
import struct
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass, field, replace

import numpy as np

from .memory import ProcessMemory, find_pid
from .scaleform import phrase

EXE = "StreetFighterV.exe"
MODULE_PREFIX = "sfv_rollback"

# ImGuiContext (ImGui 1.92.9b, no docking).
CTX_INITIALIZED = 0x0
CTX_FRAME = 0x4             # FrameCount, which moves only while SFVR draws,
CTX_FRAME_RENDERED = 0xC    # and FrameCountRendered, equal to it once a frame is whole
CTX_IO = 0x28
IO_INI_SAVING_RATE = CTX_IO + 0x1C
IO_FONTS = CTX_IO + 0x38
CTX_COLORS = 0xDCC          # Style.Colors[], RGBA floats
CTX_WINDOWS = 0x1460
CTX_VIEWPORTS = 0x2008
CTX_NAV_ID = 0x201C
CTX_NAV_WINDOW = 0x2020
CTX_NAV_LAYER = 0x202C
CTX_SPAN = 0x2030           # read in one piece to check a candidate context

# ImGuiWindow
WIN_CTX = 0x0
WIN_NAME = 0x8
WIN_CURSOR_START = 0x128    # DC.CursorStartPos, what NavRectRel is relative to
WIN_NAV_RECT = 0x3F8        # NavRectRel[2]

# ImGuiViewportP, ImDrawData, ImDrawList
VIEWPORT_DEFAULT_ID = 0x11111111
VIEWPORT_DRAW_DATA = 0x58
DRAW_DATA_LISTS = 0x10
DRAW_DATA_SIZE = 0x28       # DisplaySize, the game's picture in pixels
DRAW_LIST_VERTICES = 0x20
DRAW_LIST_OWNER = 0xD8

# ImFontAtlas, its texture and builder, whose pool holds every baked font,
# 32 to a block; ImFontBaked; ImFontGlyph
ATLAS_TEXTURE = 0x38        # TexData
ATLAS_BUILDER = 0x2B0
TEXTURE_ID = 0x0            # UniqueID, new each time the atlas is packed again
TEXTURE_SIZE = 0x24         # Width, Height
BUILDER_POOL = 0xC0         # BakedPool: Size, Capacity, then Blocks, a vector
POOL_BLOCK = 32
BAKED_STRIDE = 0x68
BAKED_ADVANCES = 0x0        # IndexAdvanceX, by codepoint, a space's included
BAKED_SIZE = 0x14
BAKED_GLYPHS = 0x30
BAKED_FLAGS = 0x4C          # MetricsTotalSurface:26, WantDestroy:1, ...
BAKED_DESTROY = 1 << 26
GLYPH_SIZE = 0x2C
GLYPH_CODEPOINT_SHIFT = 6   # after Colored:1, Visible:1, SourceIdx:4

COL_TEXT_DISABLED = 1       # ImGuiCol_TextDisabled: hint text in an empty box
COL_FRAME_BG = (7, 8, 9)    # FrameBg, Hovered, Active: a tick box's square, among others
COL_CHECK_MARK = 18         # CheckMark: the tick in it

VERTEX = np.dtype([("x", "<f4"), ("y", "<f4"), ("u", "<u4"), ("v", "<u4"), ("col", "<u4")])

PANEL = "###panel"          # the panel's window; its child windows start with this
TOASTS = "##toasts"         # the notices, which also show with the panel closed
# SFVR's own full screens, its character and stage select, drawn behind
# everything; and the side windows beside them, each player's name, REMATCH,
# CHARACTER SELECT, LEAVE and the input delay, which take ImGui's focus with
# the panel closed.
SCREEN = "##Background"
# SFVR 0.3.0 draws its window after each game (Rematch, Character select,
# Leave) and its notices ("Forever Solo Queue wants a rematch", "loading")
# in front of everything.
FOREGROUND = "##Foreground"
SIDES = "##side"
# A screen's heading and the stage or fighter under its cursor are drawn this
# big ("STAGE SELECT", "Ring of Power"); its prompts and button hints smaller.
BIG_TEXT = 40.0
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
# SFVR 0.3.0's screens: the strip along the top holding a screen's title (and
# the select screen's steps), as a share of the picture's width: titles and
# what sits beside them reach 46 pixels down at 1920 wide, and a room's first
# table starts at 106, which 0.06 took into the strip, so Table 1 was never
# said. And how much bigger than the selection a new text is to be a dialog's
# heading.
TOP_STRIP = 0.04
# Notices in front sit along the top or in the bottom corner, below this
# share of the width; the window after a game sits between.
NOTICE_LOW = 0.52
RAISED = 4.0
# Titles are this big; the hints sharing the strip are smaller.
TITLE_SIZE = 30.0
# The bottom strip, where the help line sits, below this share of the width.
BOTTOM_STRIP = 0.5
# A selected card's contents lie within this many of its header's line heights.
CARD_DEPTH = 6
# and the selection is a card when it spans this share of the width.
CARD_WIDTH = 0.4
# How a player is connected, left out of their place in a room.
CONNECTION = re.compile(r"Wired|Wireless|Wi-?Fi|\d+ ?ms")
# A wrapped line starts this close to the one above's left, and one line
# height below it.
WRAP_SLACK = 1.5
# How long the panel must stay gone to be closed rather than resizing.
CLOSE_DELAY = 0.2
# This many new texts at once is the screen changing rather than a line
# appearing on it.
SCREEN_CHANGE = 5


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
    width: float = 0.0      # the picture's width, whose halves are the two players' on the select screen
    marks: tuple = ()       # the select screen's cursor bars, rectangles as (left, top, right, bottom)

    @property
    def panel(self) -> list[Run]:
        return [r for r in self.runs if r.window.startswith(PANEL)]

    @property
    def open(self) -> bool:
        return bool(self.panel)

    @property
    def toasts(self) -> list[Run]:
        """Notices: SFVR 0.2's own window of them, and 0.3.0's along the top
        and in the bottom corner in front of everything."""
        notices = [r for r in self.foreground if self.width and r.alpha >= 0xF0
                   and (r.top < self.width * TOP_STRIP or r.top > self.width * NOTICE_LOW)]
        return [r for r in self.runs if r.window == TOASTS] + notices

    @property
    def foreground(self) -> list[Run]:
        return unshadowed([r for r in self.runs if r.window == FOREGROUND])

    @property
    def result(self) -> list[Run]:
        """SFVR 0.3.0's window after each game of a set: each player's score
        and vote, and on the player's side Rematch, Character select, Leave and
        the input delay, the selection dark on gold. Settled, so not fading."""
        if not self.width:
            return []
        window = [r for r in self.foreground
                  if self.width * TOP_STRIP <= r.top <= self.width * NOTICE_LOW]
        return window if any(is_dark(r) for r in window) else []

    @property
    def screen(self) -> list[Run]:
        """SFVR's own screen, its select screen. Each big text is drawn twice,
        the first time in black a little lower as its shadow (two pixels for
        the heading, four for a fighter); that is left out."""
        return unshadowed([r for r in self.runs if r.window == SCREEN])

    @property
    def surface(self) -> list[Run]:
        """What focus moves through: the panel while it is open, or else the
        side window holding focus. Not on the select screen: the side window
        there was the panel's preview of the match-over window ("P1 window"),
        whose focus moved with the same arrows as the screen's cursor, and
        LEAVE and Delay were heard among the fighters' names."""
        if self.open:
            return self.panel
        window = root(self.focus_window)
        if not window.startswith(SIDES) or body(self.screen):
            return []
        return [r for r in self.runs if root(r.window) == window]

    @property
    def lit(self) -> list[Run]:
        """The selection on SFVR 0.3.0's own screens, its hub, settings and
        the rest: nothing there takes ImGui's focus, and the item SFVR's
        cursor is on is drawn in dark letters on a gold bar ("Word filter",
        "On"), every other text light. The row along the top, where the
        select screen lights its step the same way, is left out, and the
        select screen itself, known by that lit step, is `ScreenNarrator`'s:
        its button hints and READY are dark on gold too. Minimised, SFVR draws
        stray letters, some dark, so nothing is lit then."""
        if not self.width or lit_step(self.screen):
            return []
        top = self.width * TOP_STRIP
        return [r for r in self.screen if is_dark(r) and r.top >= top and worth(r)]

    @property
    def fading(self) -> bool:
        """SFVR 0.3.0 fades a whole screen in or out, every text faint for a
        few frames; read then, a screen was said before it had settled."""
        return bool(self.screen) and max(r.alpha for r in self.screen) < 0xF0

    @property
    def showing(self) -> bool:
        """SFVR shows something of its own to read: its panel, its select
        screen, a side window with focus, or one of its menus."""
        return bool(self.surface or body(self.screen) or self.lit or self.result)

    def focused(self) -> list[Run]:
        """The text inside the focused item, in reading order.

        The item may be in the panel, in a list it opened, such as a combo's
        choices, which ImGui draws as a window of its own, or in a side window.
        """
        if self.focus is None or not self.surface:
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
                self.table[(u0 << 32) | v0] = (chr(cp), adv, x0, y0, x1, (u1 << 32) | v1, font,
                                               as_float(u0), as_float(v0), as_float(u1), as_float(v1))
        self.keys = np.array(sorted(self.table), dtype=np.uint64)

    def __len__(self) -> int:
        return len(self.table)


def as_float(bits: int) -> float:
    return struct.unpack("<f", struct.pack("<I", bits))[0]


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

    Text in a frame too small for it is cut to the frame, and ImGui moves the
    cut corners in with their texture coordinates: "Copy again" lost the
    tails of its p, y and g and was heard as "Co. a ain". A character whose
    bottom right lies inside its glyph, its other corners agreeing, is cut
    rather than something else, and its size comes from the part kept.
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
        ch, adv, gx0, gy0, gx1, corner, font, fu0, fv0, fu1, fv1 = glyphs.table[int(keys[i])]
        kept = 1.0
        if int(keys[i + 2]) != corner:
            if i + 3 >= len(verts) or verts["v"][i + 1] != verts["v"][i] or verts["u"][i + 3] != verts["u"][i]:
                continue
            u2, v2 = as_float(int(verts["u"][i + 2])), as_float(int(verts["v"][i + 2]))
            if not (fu0 < u2 <= fu1 and fv0 < v2 <= fv1):
                continue
            kept = (u2 - fu0) / (fu1 - fu0)
        after = i + 4
        if mask is not None:
            mask[i:i + 4] = True
        x, y = float(verts["x"][i]), float(verts["y"][i])
        x2, y2 = float(verts["x"][i + 2]), float(verts["y"][i + 2])
        scale = (x2 - x) / ((gx1 - gx0) * kept)
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


def join_wrapped(runs: list[Run]) -> list[Run]:
    """Wrapped text as one run: each line ImGui wraps onto is drawn on its
    own, one line height below the last at the same left, and was said as a
    sentence of its own ("up to eight tables with. their own rules"). A line
    so placed, in the same font and colour, that starts in lower case goes on
    the end of the one above."""
    out: list[Run] = []
    line_top = 0.0
    for r in runs:
        last = out[-1] if out else None
        if (last is not None and r.text[:1].islower() and r.window == last.window
                and r.font == last.font and r.rgb == last.rgb and r.alpha == last.alpha
                and abs(r.left - last.left) < WRAP_SLACK
                and abs(r.top - line_top - r.size) < WRAP_SLACK):
            out[-1] = replace(last, text=f"{last.text} {r.text}", right=max(last.right, r.right),
                              bottom=r.bottom)
        else:
            out.append(r)
        line_top = r.top
    return out


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
        self._atlas: tuple = ()     # `atlas_key` when `glyphs` was read
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
        # Nothing drawn yet means no glyphs yet; they are followed as they come.
        atlas = atlas_key(mem, ctx)
        glyphs = read_glyphs(mem, ctx) or Glyphs([])
        self.mem, self.ctx, self.glyphs, self._atlas = mem, ctx, glyphs, atlas
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
                self._follow_atlas()
                reading = self._read_frame(frame)
                if self._whole_frame() == frame:
                    self._last = reading
                    return reading
            return self._last
        except (OSError, struct.error, ValueError, IndexError) as exc:
            self.note(f"netplay: reading stopped ({exc!r}); looking again")
            self.detach()
            return None

    def _follow_atlas(self) -> None:
        """Read the glyphs again when they may have moved.

        ImGui 1.92 adds a glyph as a character is first drawn, bakes a font
        anew for each new size, and grows and packs its texture again, which
        moves every glyph. SFVR 0.2.x, on 1.91, did the like itself for a
        player's name; read with the old table, the select screen's headings
        and fighters came back as "Y" or nothing (7 November 2026). The table
        is taken only if the atlas held still while it was read.
        """
        atlas = atlas_key(self.mem, self.ctx)
        if atlas == self._atlas:
            return
        glyphs = read_glyphs(self.mem, self.ctx)
        if glyphs is not None and atlas_key(self.mem, self.ctx) == atlas:
            self.glyphs, self._atlas = glyphs, atlas

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
        width = mem.f32(draw_data + DRAW_DATA_SIZE) or 0.0
        marks: tuple = ()
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
                    runs += join_wrapped(decode(verts, self.glyphs, owner, mask))
                    checked = tick_box(verts, mask, focus, self.frame_rgbs, self.check_rgb)
                elif owner == SCREEN:
                    mask = np.zeros(len(verts), dtype=bool)
                    runs += join_wrapped(decode(verts, self.glyphs, owner, mask))
                    marks = cursor_bars(verts, mask)
                else:
                    runs += join_wrapped(decode(verts, self.glyphs, owner))
        return Reading(frame, tuple(runs), focus_id, name, focus, self.hint_rgb, checked, width, marks)

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


def cursor_bars(verts: np.ndarray, mask: np.ndarray) -> tuple:
    """The bars SFVR lays behind the loadout row its cursor is on: a wide
    rectangle fading from gold at one side to nothing at the other, as ImGui's
    AddRectFilledMultiColor draws it (left corners first and last, right
    corners between). Every row's dark backing fades too, but not to nothing.
    `mask` marks the characters' vertices, left out."""
    if len(verts) < 4:
        return ()
    x, y, col = verts["x"], verts["y"], verts["col"]
    a, b, c, d = (slice(k, len(verts) - 3 + k) for k in range(4))
    alpha = col >> 24
    with np.errstate(invalid="ignore"):
        bar = ((x[a] == x[d]) & (x[b] == x[c]) & (y[a] == y[b]) & (y[c] == y[d])
               & (col[a] == col[d]) & (col[b] == col[c])
               & ((col[a] & 0xFFFFFF) == (col[b] & 0xFFFFFF)) & ((alpha[a] == 0) != (alpha[b] == 0))
               & (x[b] - x[a] > 200) & (y[c] - y[a] > 20) & (y[c] - y[a] < 80) & ~mask[a])
    return tuple((float(x[i]), float(y[i]), float(x[i + 1]), float(y[i + 2])) for i in np.nonzero(bar)[0])


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


@dataclass(frozen=True)
class Baked:
    """One font baked at one size: where it sits in the pool, its size, and
    its glyph table's length and place, and its advances by codepoint."""
    index: int
    size: float
    glyphs: tuple[int, int]
    advances: tuple[int, int]


def baked_fonts(mem: ProcessMemory, ctx: int) -> tuple[tuple, list[Baked]]:
    """The atlas's texture, as (atlas, texture, its id, width, height), and
    every baked font in use; a read for the atlas, the texture and the pool,
    then one a block of 32 fonts."""
    atlas = mem.ptr(ctx + IO_FONTS)
    head = mem.read(atlas, ATLAS_BUILDER + 8) if atlas else None
    if not head or len(head) < ATLAS_BUILDER + 8:
        return (), []
    texture, builder = (struct.unpack_from("<Q", head, k)[0] for k in (ATLAS_TEXTURE, ATLAS_BUILDER))
    tex = mem.read(texture, TEXTURE_SIZE + 8) if texture else None
    texture_key = (atlas, texture) + (struct.unpack_from("<i", tex, TEXTURE_ID)
                                      + struct.unpack_from("<ii", tex, TEXTURE_SIZE) if tex else ())
    pool = mem.read(builder + BUILDER_POOL, 24) if builder else None
    if not pool or len(pool) < 24:
        return texture_key, []
    size, _capacity, blocks, _cap, data = struct.unpack("<iiiiQ", pool)
    if not 0 <= size <= 4096 or not 0 <= blocks <= 4096 // POOL_BLOCK:
        return texture_key, []
    pointers = mem.read(data, 8 * blocks) if blocks else b""
    out: list[Baked] = []
    for b, (block,) in enumerate(struct.iter_unpack("<Q", pointers or b"")):
        count = min(POOL_BLOCK, size - b * POOL_BLOCK)
        raw = mem.read(block, count * BAKED_STRIDE) if block and count > 0 else None
        for k in range(len(raw or b"") // BAKED_STRIDE):
            at = k * BAKED_STRIDE
            if struct.unpack_from("<I", raw, at + BAKED_FLAGS)[0] & BAKED_DESTROY:
                continue
            advances = struct.unpack_from("<iiQ", raw, at + BAKED_ADVANCES)
            glyphs = struct.unpack_from("<iiQ", raw, at + BAKED_GLYPHS)
            out.append(Baked(b * POOL_BLOCK + k, struct.unpack_from("<f", raw, at + BAKED_SIZE)[0],
                             (glyphs[0], glyphs[2]), (advances[0], advances[2])))
    return texture_key, out


def atlas_key(mem: ProcessMemory, ctx: int) -> tuple:
    """What changes when the glyphs move: the texture packed again or grown,
    a font baked at a new size, a glyph added to a table."""
    texture, fonts = baked_fonts(mem, ctx)
    return texture + tuple((f.index, f.glyphs) for f in fonts)


def read_glyphs(mem: ProcessMemory, ctx: int) -> Glyphs | None:
    out: list[tuple] = []
    sizes: dict[int, float] = {}
    for font in baked_fonts(mem, ctx)[1]:
        n, data = font.glyphs
        raw = mem.read(data, n * GLYPH_SIZE) if 0 < n < 100_000 else None
        if not raw:
            continue
        sizes[font.index] = font.size
        space = False
        for k in range(len(raw) // GLYPH_SIZE):
            bits, adv, x0, y0, x1, y1 = struct.unpack_from("<I5f", raw, k * GLYPH_SIZE)
            u0, v0, u1, v1 = struct.unpack_from("<4I", raw, k * GLYPH_SIZE + 0x18)
            cp = bits >> GLYPH_CODEPOINT_SHIFT
            space = space or cp == 32
            # A glyph only measured so far has no place in the texture yet.
            if cp == 32 or (u0, v0) != (u1, v1):
                out.append((cp, adv, x0, y0, x1, y1, u0, v0, u1, v1, font.index))
        # A space is only measured, never drawn, so it may have no glyph;
        # its advance is in the table by codepoint.
        count, advances = font.advances
        if count > 32 and not space:
            space = mem.f32(advances + 4 * 32)
            if space and space > 0:
                out.append((32, space, 0.0, 0.0, 0.0, 0.0, 0, 0, 0, 0, font.index))
    return Glyphs(out, sizes) if out else None


# --------------------------------------------------------------- status line
# SFVR puts a status line in the game's window title, "StreetFighterV [sfv 0]
# watching | frame 1234 | 3 frames in hand", in a match "P1 | frame 5000 |
# ping 40 ms | rollbacks 12 (max 3) | ahead 0.5", anew every half second, and
# a screen reader says the title each time it changes: NVDA said the frames
# every second while the user watched a session (7 November 2026). SFVR keeps
# the line in a std::string of its own and adds it to the title in one place,
# the window callback that writes "StreetFighterV [sfv N]" (SFVR 0.2.2):
#
#     mov  rdi, [line.size] ; test rdi, rdi ; je  <title done>
#     (a length check)      ; lea r15, [line] ; " " + line on the end
#
# That je made a jmp, the title stays "StreetFighterV [sfv N]", and the line
# is still there, read on F11. The callback is found from the prefix's text,
# so a new build is followed while the code keeps that shape; one that does
# not leaves the title as SFVR has it.
TITLE_PREFIX = b"StreetFighterV [sfv \0"
TITLE_BASE = re.compile(r"StreetFighterV \[sfv \d+\]")
RIP_OPERAND = b"[\x05\x0D\x15\x1D\x25\x2D\x35\x3D]"     # ModRM of [rip + disp32]
TITLE_JUMP = re.compile(
    b"[\x48\x4C]\x8B" + RIP_OPERAND + b"(....)"           # mov r64, [line.size]
    b"[\x48\x49\x4C\x4D]\x85[\xC0-\xFF]"                  # test r64, r64
    b"(\x0F\x84|\x90\xE9)....",                           # je, or once quieted nop, jmp
    re.DOTALL)
LEA_RIP = re.compile(b"[\x48\x4C]\x8D" + RIP_OPERAND + b"(....)", re.DOTALL)
QUIET_JUMP = b"\x90\xE9"    # the same target, since the jmp ends where the je did
# How far ahead of the line's jump the prefix is put in the title, at most,
# and how soon after it the line's own address is taken.
TITLE_SPAN = 0x800
LINE_REACH = 0x40
# A std::string, as MSVC lays it out: its text in place up to 15 bytes, else
# a pointer to it, then its length and capacity.
STRING_LENGTH = 0x10
STRING_CAPACITY = 0x18
STRING_IN_PLACE = 15
LINE_LIMIT = 512
WM_SETTEXT = 0x000C
SMTO_ABORTIFHUNG = 0x0002

user32 = ctypes.WinDLL("user32", use_last_error=True)
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.SendMessageTimeoutW.restype = ctypes.c_ssize_t
user32.SendMessageTimeoutW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPCWSTR,
    wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t),
]


def rip_target(raw: bytes, match: re.Match, group: int, base: int) -> int:
    """Where a [rip + disp32] operand points; disp32 is the instruction's last field."""
    disp = struct.unpack_from("<i", raw, match.start(group))[0]
    return base + match.end(group) + disp


def leas(code: bytes, start: int, end: int, code_base: int) -> set[int]:
    """Every address a lea r64, [rip + disp32] in code[start:end] takes."""
    start = max(0, start)
    part = code[start:end]
    return {rip_target(part, m, 1, code_base + start) for m in LEA_RIP.finditer(part)}


def find_status_line(code: bytes, code_base: int, prefix: int,
                     data: tuple[int, int]) -> tuple[int, int, bool] | None:
    """The title callback's jump past the status line, the line's std::string,
    and whether the jump is quieted already; None unless exactly one fits.

    `code` is SFVR's .text read from `code_base`, `prefix` where its
    "StreetFighterV [sfv " lives, `data` the start and end of its .data.
    """
    found = []
    for m in TITLE_JUMP.finditer(code):
        line = rip_target(code, m, 1, code_base) - STRING_LENGTH
        if (data[0] <= line < data[1]
                and line in leas(code, m.end(), m.end() + LINE_REACH, code_base)
                and prefix in leas(code, m.start() - TITLE_SPAN, m.start(), code_base)):
            found.append((code_base + m.start(2), line, m.group(2) == QUIET_JUMP))
    return found[0] if len(found) == 1 else None


def read_string(mem: ProcessMemory, address: int) -> str | None:
    """An MSVC std::string's text, or None if it does not read as one."""
    head = mem.read(address, STRING_CAPACITY + 8)
    if not head or len(head) < STRING_CAPACITY + 8:
        return None
    length, capacity = struct.unpack_from("<QQ", head, STRING_LENGTH)
    if length > capacity or length > LINE_LIMIT:
        return None
    if capacity <= STRING_IN_PLACE:
        raw = head[:length]
    else:
        raw = mem.read(struct.unpack_from("<Q", head, 0)[0], length) if length else b""
        if raw is None or len(raw) != length:
            return None
    return raw.decode("utf-8", "replace")


def status_words(line: str | None) -> str:
    """SFVR's status line as said on F11: "Watching, frame 1234, 3 frames in hand"."""
    if line is None:        # no SFVR, or a build whose line was not found
        return "No SFVR status found."
    line = tidy(line.replace("|", ","))
    line = re.sub(r"\s+,", ",", line)
    if not line:
        return "No netplay session."
    return line[0].upper() + line[1:]


class StatusLine:
    """SFVR's status line, kept out of the game's window title and read on a key.

    Looked for every few seconds until SFVR is found, then the quieted jump is
    checked as often, so a new game, or SFVR loaded again, is quieted too.
    """

    def __init__(self, note=None) -> None:
        self.note = note or (lambda text: None)
        self.mem: ProcessMemory | None = None
        self.line = 0
        self.jump = 0
        self._kept = b""        # what the jump should read while all is well
        self._retry_at = 0.0
        self._missing: tuple[int, int] | None = None    # the game and SFVR searched in vain
        self._lock = threading.Lock()

    def step(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        with self._lock:
            if now < self._retry_at:
                return
            self._retry_at = now + ATTACH_RETRY
            if self.mem is not None:
                if self.mem.read(self.jump, len(self._kept)) == self._kept:
                    return
                self.note("netplay: SFVR's title code changed or went; looking again")
                self._detach()
            self._attach()

    def text(self) -> str | None:
        """The line as SFVR has it now, "" for none, or None without SFVR."""
        with self._lock:
            if self.mem is None:
                self._attach()
            if self.mem is None:
                return None
            for _ in range(3):      # SFVR may be part way through replacing it
                line = read_string(self.mem, self.line)
                if line is not None:
                    return line
                time.sleep(0.01)
            return None

    def _detach(self) -> None:
        if self.mem is not None:
            self.mem.close()
        self.mem, self.line, self.jump, self._kept = None, 0, 0, b""

    def _attach(self) -> None:
        pid = find_pid(EXE, "Binaries", require_path=True)
        if not pid:
            return
        try:
            mem = ProcessMemory(pid)
        except OSError:
            return
        module = next((m for m in mem.modules() if m.name.lower().startswith(MODULE_PREFIX)), None)
        if module is None or self._missing == (pid, module.base):
            mem.close()
            return
        text, rdata, data = (mem.section(module, name) for name in (".text", ".rdata", ".data"))
        code = mem.read(text.base, text.size) if text else None
        consts = mem.read(rdata.base, rdata.size) if rdata else None
        at = consts.find(TITLE_PREFIX) if consts else -1
        found = (find_status_line(code, text.base, rdata.base + at, (data.base, data.end))
                 if code and at >= 0 and data else None)
        if found is None:
            mem.close()
            self._missing = (pid, module.base)
            self.note(f"netplay: {module.name}'s status line was not found; "
                      "its window title is left as it is")
            return
        jump, line, quiet = found
        if not quiet and mem.write(jump, QUIET_JUMP):
            quiet = True
            self.note(f"netplay: {module.name}'s status line kept out of the window title")
        elif not quiet:
            self.note(f"netplay: {module.name}'s window title could not be quieted")
        self.mem, self.line, self.jump = mem, line, jump
        self._kept = QUIET_JUMP if quiet else (mem.read(jump, 2) or b"")
        if quiet:
            clear_title(pid)


def clear_title(pid: int) -> None:
    """Take a status line already in the title off it, once, as SFVR would now.

    Without this the title kept the last line ("connection lost") until SFVR
    next changed it, then said its new title in the middle of a session. Every
    window of the game is looked at, as SFVR does, minimised ones too.
    """
    @WNDENUMPROC
    def each(hwnd, _lparam):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            base = TITLE_BASE.match(buf.value)
            if base and base.group() != buf.value:
                user32.SendMessageTimeoutW(hwnd, WM_SETTEXT, 0, base.group(),
                                           SMTO_ABORTIFHUNG, 1000, None)
        return True

    user32.EnumWindows(each, 0)


# ----------------------------------------------------------------- narration
def tidy(text: str) -> str:
    # A character the font lacks comes back as U+FFFD; SFVR uses one, a dot
    # between parts ("120 ms to the host · 3 watching").
    return re.sub(r"\s+", " ", re.sub(r"\s*�\s*", ", ", text)).strip()


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
    with Alt A. With the panel closed, the same for a side window holding
    focus, and SFVR's select screen through `ScreenNarrator`.
    """
    was_open: bool = False
    focus_said: tuple = ()      # the focused item's id, its text and its tick
    known: set = field(default_factory=set)      # the panel's texts at the last reading
    seen: set = field(default_factory=set)       # and every one since it opened
    unavailable: set = field(default_factory=set)   # those drawn disabled at the last reading
    toasts: set = field(default_factory=set)
    gone_since: float | None = None   # when the panel stopped showing, while it may come back
    window: str = ""            # the window focus was last heard in
    screen: ScreenNarrator = field(default_factory=lambda: ScreenNarrator())
    menu: MenuNarrator = field(default_factory=lambda: MenuNarrator())
    result: ResultNarrator = field(default_factory=lambda: ResultNarrator())

    def reset(self) -> None:
        self._leave()
        self.toasts = set()
        self.screen.reset()
        self.menu.reset()
        self.result.reset()

    def _leave(self) -> None:
        """Focus has left SFVR's windows; what was heard in them is forgotten."""
        self.was_open, self.focus_said, self.gone_since, self.window = False, (), None, ""
        self.known, self.seen, self.unavailable = set(), set(), set()

    def step(self, reading: Reading | None, now: float | None = None) -> str | None:
        if reading is None:
            return None
        now = time.monotonic() if now is None else now
        said: list[str] = []
        shown = {tidy(r.text) for r in reading.toasts}
        said += [t for t in (tidy(r.text) for r in reading.toasts) if t and t not in self.toasts]
        self.toasts = shown

        is_open = reading.open
        if is_open:
            self.gone_since = None
        elif self.was_open:
            # ImGui leaves a window out of a frame or so while it resizes, as
            # the panel does going to the wider Debug tab; heard as "Netplay
            # closed" and "Netplay" again. Closed is closed once it stays gone.
            self.gone_since = now if self.gone_since is None else self.gone_since
            if now - self.gone_since < CLOSE_DELAY:
                return phrase(dedupe(said)) or None
            said.insert(0, "Netplay closed")
            self._leave()
        if reading.result and not is_open:
            said += self.result.step(reading)
        else:
            self.result.reset()
        if reading.fading and not is_open:
            pass
        elif reading.lit and not is_open:
            said += self.menu.step(reading, now)
        else:
            self.menu.leave(now)
            said += self.screen.step(reading, now)
        surface = reading.surface
        if not surface:
            self._leave()
            return phrase(dedupe(said)) or None

        focused = reading.focused()
        now_known = {key(r) for r in surface}
        focus = (reading.focus_id, tuple(tidy(r.text) for r in focused), reading.checked)
        before = self.focus_said or (None, None, None)
        if reading.focus_id == 0 and self.focus_said:
            # ImGui drops focus to no item for a moment after a button is
            # pressed, and gives it back: the item was said twice.
            focus = before
        # Focus can move out of the panel into another of SFVR's windows, such
        # as the match-over window (which Debug's "P1 window" previews), and the
        # arrows then stay inside it. Its title is said on the way in, and
        # "Netplay" on the way back. A list opened from the panel is part of it.
        window = root(reading.focus_window)
        crossed = bool(window and self.window and window != self.window
                       and not is_list(window) and not is_list(self.window))
        # With the panel closed, focus is in a side window: on SFVR's select
        # screen, REMATCH, CHARACTER SELECT, LEAVE and the input delay. Its
        # title is said on the way in, as when focus crosses into it.
        entering = (is_open and not self.was_open) or (not is_open and window != self.window)
        if entering:
            if is_open:
                said.insert(0, "Netplay")
            self.known, self.seen, self.unavailable = set(), set(), set()
            if window and window != PANEL and not is_list(window):
                said.append(heading(reading, window))
            said.append(self.describe(reading, focused))
        elif focus[0] != before[0] and crossed:
            said.append(heading(reading, window))
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
            if focus[1] != before[1]:
                # The same item showing something else, said before whatever
                # came with it: a slider moved, a code typed into the box with
                # focus, HOST A MATCH become HOSTING, or ImGui keeping focus
                # on a button that has gone, now over other text.
                said.append(self.describe(reading, focused, with_label=False))
            said += self.changes(reading, focused)
        # JOIN and WATCH are unavailable, and skipped by the arrows, until the
        # code box holds a whole code; saying when they come back says when
        # there is somewhere to go.
        unavailable = {key(r) for r in surface if r.disabled}
        if not entering:
            said += dedupe([f"{tidy(r.text)}, available" for r in surface
                            if not r.disabled and key(r) in self.unavailable and key(r) not in unavailable])
        self.unavailable = unavailable
        self.was_open, self.focus_said, self.known = is_open, focus, now_known
        self.seen |= now_known
        self.window = window or self.window
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
        new = [r for r in reading.surface if key(r) not in self.known and not r.disabled and r not in focused
               and (above is None or r.bottom <= above + 2)]
        if len(new) >= SCREEN_CHANGE:
            # A whole screen changing: coming back to one already heard since
            # the panel opened (the Match tab after cancelling a hosted match)
            # was read out in full again; only what is new on it is said.
            new = [r for r in new if key(r) not in self.seen]
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


def unshadowed(runs: list[Run]) -> list[Run]:
    """Texts without their shadows: SFVR draws a text again in black, a few
    pixels off and faint, behind it (five times over in 0.3.0)."""
    return [r for r in runs if not (r.rgb == 0 and any(
        s.rgb != 0 and s.text == r.text and abs(s.left - r.left) < 8 and abs(s.top - r.top) < 8 for s in runs))]


# A player's label in the window after a game ("P1 \u00b7 YOU", "P2"), and the
# lines there that are a countdown, a delay or what a choice does.
PLAYER_LABEL = re.compile(r"P[12]\b")
RESULT_NOTE = re.compile(r"(?i)\bdelay\b|\bin \d+ s$|^leave ")
COUNTDOWN = re.compile(r"\bin \d+ s$")


@dataclass(frozen=True)
class Side:
    """One player's half of the window after a game."""
    name: str
    score: str          # "0 of 2 to win the set"
    statuses: tuple     # their vote and the like: "Choosing...", "Rematch", "Wins the set"
    notes: tuple        # "Rematch in 15 s", "Suggested delay 1 (ping 64 ms)"


def result_sides(reading: Reading, window: list[Run]) -> tuple[Side | None, Side | None]:
    """The player's half (the one with the selection) and the other's."""
    lit = [r for r in window if is_dark(r)]
    mine = half(reading, lit[0])
    out: dict[int, Side] = {}
    for s in (0, 1):
        runs = [r for r in window if half(reading, r) == s]
        rows = lines(runs)
        if not rows:
            continue
        margin = min(r.left for r in runs)
        label = rows[0]
        name = (commas(say(r) for r in label if not PLAYER_LABEL.match(tidy(r.text)))
                or commas(say(r) for r in label))
        score_row = next((row for row in rows if any(r.size >= BIG_TEXT and tidy(r.text).isdigit()
                                                     for r in row)), [])
        statuses, notes = [], []
        for row in rows[1:]:
            if row is score_row or any(is_dark(r) for r in row) or abs(row[0].left - margin) > 3:
                continue
            text = commas(say(r) for r in row)
            (notes if RESULT_NOTE.search(text) else statuses).append(text)
        out[s] = Side(name, " ".join(say(r) for r in score_row), tuple(statuses), tuple(notes))
    return out.get(mine), out.get(1 - mine) if mine in (0, 1) else None


def result_intro(reading: Reading, every_note: bool = False) -> list[str]:
    """The window after a game as it comes up: "You: 0 of 2 to win the set,
    Choosing... Forever Solo Queue: 1 of 2 to win the set, Choosing...
    Rematch in 15 s. Rematch"."""
    window = reading.result
    if not window:
        return []
    mine, theirs = result_sides(reading, window)
    said: list[str] = []
    if mine:
        said.append(commas([f"You: {mine.score}" if mine.score else "You"] + list(mine.statuses)))
    if theirs:
        said.append(commas([f"{theirs.name}: {theirs.score}"] + list(theirs.statuses)))
    if mine:
        said += [n for n in mine.notes if every_note or COUNTDOWN.search(n)]
    said += [commas(say(r) for r in row) for row in lines([r for r in window if is_dark(r)])]
    if every_note and theirs:
        said += list(theirs.notes)
    return said


def read_result(reading: Reading) -> list[str]:
    """Alt R on the window after a game: all of it, the delay suggested too."""
    return result_intro(reading, every_note=True)


@dataclass
class ResultNarrator:
    """Decides what to say on SFVR 0.3.0's window after each game of a set.

    Coming up it says both scores and votes, the countdown and the selection
    (see `result_intro`); then each choice moved to ("Character select"), a
    value changed alone ("4 frames"), what a choice does when that line
    changes ("Leave ends the set here."), the player's own vote or state as
    it changes ("You: Rematch"), and the other player's ("Forever Solo
    Queue: Rematch"). The countdown ticking is not said. Recorded 7 November 2026;
    the user heard nothing there, since SFVR draws it in front, where the mod
    did not read.
    """
    shown: bool = False
    items: tuple = ()
    mine: tuple = ()
    theirs: tuple = ()
    notes: frozenset = frozenset()

    def reset(self) -> None:
        self.shown, self.items, self.mine, self.theirs, self.notes = False, (), (), (), frozenset()

    def step(self, reading: Reading) -> list[str]:
        window = reading.result
        mine, theirs = result_sides(reading, window)
        items = tuple(tuple(say(r) for r in row) for row in lines([r for r in window if is_dark(r)]))
        my_statuses = mine.statuses if mine else ()
        their_statuses = theirs.statuses if theirs else ()
        notes = frozenset(re.sub(r"\d+", "#", n) for n in (mine.notes if mine else ()))
        said: list[str] = []
        if not self.shown:
            said = result_intro(reading)
        else:
            for item in (i for i in items if i not in self.items):
                was = next((o for o in self.items if o[:1] == item[:1] and o not in items), None)
                said += [t for t in item if t not in was] if was else [commas(item)]
            said += [f"You: {t}" for t in my_statuses if t not in self.mine]
            if theirs:
                said += [f"{theirs.name}: {t}" for t in their_statuses if t not in self.theirs]
            said += [n for n in (mine.notes if mine else ())
                     if re.sub(r"\d+", "#", n) not in self.notes and not n.lower().startswith("suggested")]
        self.shown, self.items, self.mine, self.theirs, self.notes = True, items, my_statuses, their_statuses, notes
        return said


@dataclass
class MenuNarrator:
    """Decides what to say on SFVR 0.3.0's own screens, its hub, settings,
    rooms and the rest, which SFVR draws whole with its own cursor
    (`Reading.lit`).

    A screen coming up says its title, the selection and where the player is
    ("Kongster's room. TABLE 1, ... You: Table 1, seated"); moving says the
    new selection ("Word filter, On"), a table with what is in it; left and
    right on the same item say the new value ("Off"). A selected item that
    stays put, as the chat's Send button always is, is not said again. With
    nothing new selected, a new line along the bottom is said ("That's
    you."), as the players list shows its cursor only as an outline. The
    player's own place is said as it changes, and each new chat line. A
    dialog coming up over the screen, a new text bigger than the selection
    and standing over it, says its heading and sentences first ("Custom
    Rooms are unavailable. The rooms server is up, ..."). What the selection
    does, shown beside it or along the bottom, is for Alt R. Recorded on SFVR
    0.3.0, 7 November 2026; the user heard the old select-screen rules read
    the settings with unrelated texts run together, and asked which table
    they were at.
    """
    title: str | None = None
    items: tuple = ()
    status: str = ""
    chat: tuple = ()
    help: str = ""
    known: set = field(default_factory=set)
    gone_since: float | None = None
    unsettled: float | None = None   # since when a new title has shown a "?"

    def reset(self) -> None:
        self.title, self.items, self.status, self.chat, self.help = None, (), "", (), ""
        self.known, self.gone_since, self.unsettled = set(), None, None

    def leave(self, now: float) -> None:
        """No selection showing; forgotten once it stays gone, since a screen
        changing can leave a frame or so without one."""
        if self.title is None and not self.items:
            return
        self.gone_since = now if self.gone_since is None else self.gone_since
        if now - self.gone_since >= CLOSE_DELAY:
            self.reset()

    def step(self, reading: Reading, now: float) -> list[str]:
        self.gone_since = None
        shown = reading.screen
        lit_runs = [r for row in lines(reading.lit) for r in row]
        items = menu_items(reading)
        title, status, chat, help_line = (menu_title(reading), you_status(reading),
                                          chat_lines(reading), bottom_line(reading))
        said: list[str] = []
        if self.title and "?" in self.title and same_but_unknown(self.title, title):
            self.title = title
        # A new title with a letter not drawn yet waits a moment for it.
        if title != self.title and "?" in title:
            self.unsettled = now if self.unsettled is None else self.unsettled
            if now - self.unsettled < CLOSE_DELAY * 2:
                return said
        self.unsettled = None
        if title != self.title:
            said += [title] if title else []
            said += [commas(item) for item in items]
            said += [status] if status else []
        else:
            size = max(r.size for r in lit_runs)
            top = reading.width * TOP_STRIP
            new = [r for r in shown if key(r) not in self.known and r.top >= top]
            # A dialog's heading stands over its own selected button; the
            # panel beside a list, whose heading is as big, stands apart.
            raised = sorted((r for r in new if r.size >= size + RAISED and not lit_text(r, items)
                             and any(r.left < o.right and o.left < r.right for o in lit_runs)),
                            key=lambda r: (r.top, r.left))
            if raised:
                said += [say(r) for r in raised]
                said += [say(r) for r in new if is_sentence(r) and r not in raised and r not in lit_runs]
                # The dialog is drawn after the screen under it, whose own
                # selection stays lit; only the dialog's button is said.
                first = min(shown.index(r) for r in raised)
                over = tuple(say(r) for r in lit_runs if shown.index(r) > first)
                said += [commas(over)] if over else []
            else:
                fresh = [item for item in items if item not in self.items]
                for item in fresh:
                    # The same item with a value changed: its first text kept.
                    was = next((o for o in self.items if o[:1] == item[:1] and o not in items), None)
                    said += ([t for t in item if t not in was] if was and len(items) == len(self.items)
                             else [commas(item)])
                if not fresh and help_line and help_line != self.help:
                    said.append(help_line)
            if status and status != self.status:
                said.append(status)
            said += new_chat(self.chat, chat)
        # The line along the bottom blinks; a frame without it keeps it.
        self.help = help_line or self.help
        self.title, self.items, self.status, self.chat = title, items, status, chat
        self.known = {key(r) for r in shown}
        return said


def menu_items(reading: Reading) -> tuple:
    """The selection as items, each a row of lit texts with what lies under
    it on its card: a table's header, then its seats ("TABLE 2", "0 in
    queue", "First to 2, winner stays, ...", "Sit here as P1", "VS", "Open
    seat"). Only a selection spanning much of the screen is a card; it ends
    at a text starting at or left of its header (the next table's), or a few
    lines down. A settings row is narrower, and has no card."""
    shown = reading.screen
    lit = reading.lit
    out = []
    for row in lines(lit):
        head = row[0]
        left, right = min(r.left for r in row), max(r.right for r in row)
        card = []
        if right - left > CARD_WIDTH * reading.width:
            depth = head.top + CARD_DEPTH * head.size
            below = sorted((r for r in shown if r.top > head.bottom - 2 and r.top < depth
                            and left - 2 <= r.left and r.right <= right + 2 and worth(r)),
                           key=lambda r: r.top)
            for r in below:
                if r.left < head.left + 3:
                    break
                if r not in lit:
                    card.append(r)
        out.append(tuple(say(r) for r in row) + tuple(say(r) for line in lines(card) for r in line))
    return tuple(out)


def same_but_unknown(before: str, now: str) -> bool:
    """The same text, but for letters that were "?" before: ImGui 1.92 draws
    a character it has not baked yet as "?" for a frame ("?'s room", then
    "Kongster's room")."""
    pattern = "".join(".+?" if c == "?" else re.escape(c) for c in before)
    return re.fullmatch(pattern, now) is not None


def lit_text(r: Run, items: tuple) -> bool:
    return any(say(r) in item for item in items)


def you_status(reading: Reading) -> str:
    """Where the player is, from their own row in a room's players list:
    "You: Table 1, seated", "You: Watching Table 1". How they are connected
    is left out."""
    shown = reading.screen
    you = next((r for r in shown if tidy(r.text) == "(you)" and r.left > reading.width / 2), None)
    if you is None:
        return ""
    row = next((row for row in lines(shown) if you in row), [])
    after = [say(r) for r in row if r.left > you.left and not CONNECTION.fullmatch(tidy(r.text))]
    return f"You: {commas(after)}" if after else ""


def chat_lines(reading: Reading) -> tuple:
    """A room's chat, oldest first: the lines starting under its heading
    ("ROOM CHAT") at the heading's left; the box to type in sits further in.
    A player's message is their name with the message beside it, said as
    "FOREVER SOLO QUEUE: They cant find you"; at first only the name was
    read, and the user missed what was said to them (7 November 2026)."""
    shown = reading.screen
    heading = next((r for r in shown if tidy(r.text).endswith("CHAT") and tidy(r.text).isupper()), None)
    if heading is None:
        return ()
    under = [r for r in shown if r is not heading and r.top > heading.top and r.left > heading.left - 3]
    out = []
    for row in lines(under):
        if abs(row[0].left - heading.left) >= 3:
            continue
        texts = [say(r) for r in row]
        out.append(f"{texts[0]}: {commas(texts[1:])}" if len(texts) > 1 else texts[0])
    return tuple(out)


def new_chat(before: tuple, now: tuple) -> list[str]:
    """The chat lines added since: the old lines move up as new ones come in
    underneath. On first sight there is nothing new."""
    if not before:
        return []
    for overlap in range(min(len(before), len(now)), 0, -1):
        if before[-overlap:] == now[:overlap]:
            return list(now[overlap:])
    return list(now)


def bottom_line(reading: Reading) -> str:
    """The line along the bottom left, which says what the selection is or
    does ("That's you.", "ROOM OPEN, Share the code to invite friends.")."""
    low = [r for r in reading.screen if r.top > reading.width * BOTTOM_STRIP and r.left < reading.width / 2]
    rows = lines(low)
    return commas(say(r) for r in rows[-1]) if rows else ""


def is_dark(r: Run) -> bool:
    """Dark letters, solid: the selection on SFVR 0.3.0's gold bar."""
    return r.alpha >= 0xF0 and (r.rgb & 0xFF) + (r.rgb >> 8 & 0xFF) + (r.rgb >> 16 & 0xFF) < 0xC0


def menu_title(reading: Reading) -> str:
    """The biggest text along the top of one of SFVR's screens: "SFVR SETTINGS".
    Button hints share the strip ("Preferred stage"), in smaller letters."""
    top = reading.width * TOP_STRIP
    along = [r for r in reading.screen if r.top < top and worth(r) and r.size >= TITLE_SIZE]
    return say(max(along, key=lambda r: r.size)) if along else ""


def read_menu(reading: Reading) -> list[str]:
    """Alt R on one of SFVR 0.3.0's screens: the selection, then the
    sentences on the screen, which say what it does ("Word filter, On. Hides
    offensive names and words in public rooms.")."""
    if not reading.lit:
        return []
    items = menu_items(reading)
    status = you_status(reading)
    return ([commas(item) for item in items] + ([status] if status else [])
            + [say(r) for r in reading.screen if is_sentence(r) and not lit_text(r, items)])


@dataclass
class ScreenNarrator:
    """Decides what to say as SFVR's select screen changes.

    Nothing on it takes ImGui's focus: SFVR moves its cursor itself, through
    the stages, the fighters and then the loadout's rows, and draws what is
    under it. So what is said is what changes. A step coming up says its
    heading, its choices and its prompt ("STAGE SELECT. Ring of Destiny. You
    select the stage.", "CHARACTER SELECT. RYU. Other player, CHUN-LI"); a
    step with no heading of its own says its name from the row along the top
    ("Loadout"). Then the stage or fighter as the cursor moves ("Suzaku
    Castle. Setting 1 of 2", "ALEX"), and on the loadout the row the cursor
    is on ("Color, 03") and a value as it changes ("04"); a row's help line
    is for Alt R. The other player's half of the screen says only their
    fighter; the button hints, their loadout and a number that only ticks
    over (a ping) are for Alt A. Measured on the preview from the panel's
    Debug tab (1 November 2026); a real session's has not been seen.
    """
    known: set = field(default_factory=set)     # the key of each text at the last reading
    lit: str = ""               # the step lit along the top
    row: tuple = ()             # the texts of the loadout row the cursor is on
    row_top: float | None = None
    gone_since: float | None = None

    def reset(self) -> None:
        self.known, self.lit, self.row, self.row_top, self.gone_since = set(), "", (), None, None

    def step(self, reading: Reading, now: float) -> list[str]:
        shown = body(reading.screen)
        if not shown:
            # The panel opening hides the screen, and closing on it unchanged
            # says nothing more. Gone with the panel closed it has closed, once
            # it stays gone, as ImGui leaves a window out of a frame or so.
            if self.known and not reading.open:
                self.gone_since = now if self.gone_since is None else self.gone_since
                if now - self.gone_since >= CLOSE_DELAY:
                    self.reset()
            return []
        self.gone_since = None
        mine = my_half(reading, shown)
        new = [r for r in shown if key(r) not in self.known and worth(r)]
        big = sorted((r for r in new if r.size >= BIG_TEXT), key=lambda r: (round(r.size), r.top, r.left))
        said = [say(r) if r in mine else f"Other player, {say(r)}" for r in big]
        lit = lit_step(reading.screen)
        if lit and self.lit and lit != self.lit and not any(lit.lower() in tidy(r.text).lower() for r in big):
            said.insert(0, lit)
        row = cursor_row(reading, shown, mine)
        if row and (self.row_top is None or abs(row[0].top - self.row_top) > 2):
            said.append(commas(say(r) for r in row))
        elif row:
            # The same row, a value changed by left or right. Compared whole,
            # since "03" becoming "04" is a number only ticking over to `key`.
            said += [say(r) for r in row if tidy(r.text) not in self.row]
        else:
            small = [r for r in new if r.size < BIG_TEXT and r in mine]
            if len(small) >= SCREEN_CHANGE:
                small = [r for r in small if is_sentence(r)]
            rows = lines([r for r in shown if r.size < BIG_TEXT and r in mine and worth(r)])
            said += [commas(say(r) for r in row) for row in rows if any(r in small for r in row)]
        self.known, self.lit = {key(r) for r in shown}, lit
        self.row, self.row_top = tuple(tidy(r.text) for r in row), (row[0].top if row else None)
        return said


def body(screen: list[Run]) -> list[Run]:
    """A select screen's texts but the row along its top, the steps ("Stage
    select", "Character", "Loadout") and the button hints ("Confirm stage").
    Nothing without a big text is a screen: minimised, SFVR draws a stray
    letter there."""
    if not any(r.size >= BIG_TEXT for r in screen):
        return []
    rows = lines(screen)
    if len(rows[0]) >= 3:
        rows = rows[1:]
    return [r for row in rows for r in row]


def lit_step(screen: list[Run]) -> str:
    """The step lit along the top of the select screen: dark text on a gold
    button, where the others are light."""
    rows = lines(screen)
    if not rows or len(rows[0]) < 3:
        return ""
    lit = [r for r in rows[0] if (r.rgb & 0xFF) + (r.rgb >> 8 & 0xFF) + (r.rgb >> 16 & 0xFF) < 0xC0]
    return tidy(lit[0].text) if len(lit) == 1 else ""


def my_half(reading: Reading, shown: list) -> list:
    """What on the select screen is the player's: the half with "(you)" over
    its fighter, and what spans the middle (the heading, the prompt). With no
    "(you)", as on the stage step, all of it."""
    you = next((r for r in shown if "(you)" in r.text), None)
    if you is None or not reading.width:
        return list(shown)
    side = half(reading, you)
    # SFVR 0.3.0's own character picker has the player's fighter on the left
    # and their loadout, "(you)" again, on the right: it is all theirs.
    if any("(you)" in r.text and half(reading, r) not in (None, side) for r in shown):
        return list(shown)
    return [r for r in shown if half(reading, r) in (None, side)]


def half(reading: Reading, r) -> int | None:
    """0 for the left half, 1 for the right, None across the middle. Takes a
    run or a rectangle."""
    left, right = (r.left, r.right) if isinstance(r, Run) else (r[0], r[2])
    middle = reading.width / 2
    return 0 if right <= middle else 1 if left >= middle else None


def cursor_row(reading: Reading, shown: list, mine: list) -> list[Run]:
    """The loadout row under the player's cursor bar, left to right, without
    its arrows: "Costume", "Kenji"."""
    you = next((r for r in shown if "(you)" in r.text), None)
    bars = [m for m in reading.marks if you is None or half(reading, m) in (None, half(reading, you))]
    return sorted((r for r in mine if worth(r) and r.size < BIG_TEXT
                   and any(m[1] <= (r.top + r.bottom) / 2 <= m[3] for m in bars)), key=lambda r: r.left)


def worth(r: Run) -> bool:
    """A text worth saying: not the random tile's "?", nor the cursors' "1P"
    and "2P", nor a row's arrows, which are pictures more than words; nor the
    player's own name over their fighter ("YOU (you)")."""
    text = tidy(r.text)
    return bool(re.search(r"[A-Za-z0-9]", text)) and not re.fullmatch(r"\dP", text) and "(you)" not in text


def is_sentence(r: Run) -> bool:
    """A prompt or a help line ("You select the stage.", "Ready: the match
    starts once both players are"), not a value in capitals ("II KARURA
    TENZAN")."""
    text = tidy(r.text)
    return len(text.split()) >= 3 and bool(re.search(r"[a-z]", text)) and (text.endswith(".") or ":" in text)


def commas(texts) -> str:
    """Texts side by side, as one line: "Costume, DEFAULT". After a sentence
    the next text starts afresh rather than after a comma, which was heard
    as "Play online in rooms of up to 16 players., Select"."""
    out = ""
    for text in texts:
        if out and text:
            out += " " if out[-1] in ".?!:" else ", "
        out += text
    return out


def say(r: Run) -> str:
    """A screen text as said: "Setting 1 / 2" as "Setting 1 of 2", and a dot
    between parts as a pause ("First to 2, winner stays"). A "?" standing
    alone is a symbol the font lacks, as in a player's name ("? EASTWOOD ?"),
    and is left out; one ending a question stays."""
    text = re.sub(r"(\s*\u00b7\s*)+", ", ", tidy(r.text)).strip(", ")
    if re.search(r"[A-Za-z0-9]", text):
        text = re.sub(r"\s+", " ", re.sub(r"(?:^|(?<=\s))\?+(?=\s|$)", "", text)).strip()
    return re.sub(r"(\d+) ?/ ?(\d+)", r"\1 of \2", text)


def read_screen(reading: Reading) -> list[str]:
    """Alt R on the select screen: its step when it has no heading, the
    heading and the choices, and the loadout row under the cursor with its
    help ("Costume, Kenji. Pick a costume.")."""
    shown = body(reading.screen)
    if not shown:
        return []
    said = ScreenNarrator().step(reading, 0.0)
    lit = lit_step(reading.screen)
    if lit and not any(lit.lower() in tidy(r.text).lower() for r in shown if r.size >= BIG_TEXT):
        said.insert(0, lit)
    mine = my_half(reading, shown)
    row = cursor_row(reading, shown, mine)
    if row:
        said += [tidy(r.text) for r in mine if is_sentence(r) and r not in row and r.size < BIG_TEXT]
    return said


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


def root(window: str) -> str:
    """A window's top window: the panel for its child windows."""
    return window.split("/", 1)[0]


def is_list(window: str) -> bool:
    """A combo's choices, which ImGui opens as a window of its own."""
    return window.startswith("##Combo")


def heading(reading: Reading, window: str) -> str:
    """What a window is called when focus moves into it: "Netplay" for the
    panel, and for another of SFVR's windows its first line ("P1 Player One
    (you)")."""
    if window == PANEL:
        return "Netplay"
    rows = lines([r for r in reading.runs if root(r.window) == window])
    return " ".join(tidy(r.text) for r in rows[0]) if rows else ""


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
    """Alt R: the focused item, then the line just under it; on SFVR's select
    screen, what it shows first ("STAGE SELECT. Ring of Power").

    The line under a big button is what it does ("You get a code to send to
    the other player."); a description is left-aligned with its item and
    close beneath it, where a neighbouring item would be further down.
    """
    narrator = PanelNarrator()
    focused = reading.focused()
    said = narrator.describe(reading, focused) if focused else ""
    window = root(reading.focus_window)
    if focused and window != PANEL and not is_list(window):
        said = phrase([heading(reading, window), said])
    if focused and reading.focus is not None:
        x0, _y0, _x1, y1 = reading.focus
        under = [r for r in reading.surface if 0 <= r.top - y1 < 15 and abs(r.left - x0) < 6
                 and len(tidy(r.text)) > 1 and not r.disabled]
        if under:
            said = phrase([said] + [tidy(r.text) for r in sorted(under, key=lambda r: r.top)])
    screen = [] if reading.open else (read_result(reading) or read_menu(reading) or read_screen(reading))
    shown = [tidy(r.text) for r in reading.runs if r.window.startswith("##Tooltip")]
    return phrase(screen + [said] + shown) or "Nothing focused"


def read_lines(reading: Reading) -> list[Line]:
    """Alt A: every line of the panel while it is open, an unavailable item
    said so; with it closed, of SFVR's select screen, then its side windows."""
    if reading.open:
        groups = [reading.panel]
    else:
        sides = sorted({root(r.window) for r in reading.runs if r.window.startswith(SIDES)})
        groups = [reading.screen] + [[r for r in reading.runs if root(r.window) == side] for side in sides]
    out = []
    focused = set(id(r) for r in reading.focused())
    for runs in groups:
        for row in lines(runs):
            words = []
            for r in row:
                text = tidy(r.text)
                if r.disabled:
                    text += ", unavailable"
                words.append(text)
            out.append(Line(commas(words), any(id(r) in focused for r in row)))
    return out
