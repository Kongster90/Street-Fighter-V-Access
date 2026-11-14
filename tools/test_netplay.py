"""Check reading SFVR's netplay panel, without the game.

A made-up font is laid out the way ImGui lays out text, four vertices a
character, and the decoder must give back the words, their spaces and where
they sit. Then panel readings shaped like the ones recorded on 1 November
2026 (the Match tab, its code box and keyboard, the tabs, a notice) go
through the narrator, which must say the panel opening and closing, each item
focus lands on, a tab as a tab, an empty box as empty, a code spelled as it
is typed, and each notice once.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access import netplay as n  # noqa: E402

ok = True


def check(label, condition, detail=""):
    global ok
    if condition:
        print(f"PASS  {label}{(': ' + detail) if detail else ''}")
    else:
        ok = False
        print(f"FAIL  {label}{(': ' + detail) if detail else ''}")


def bits(f: float) -> int:
    return struct.unpack("<I", struct.pack("<f", f))[0]


# A font of fixed-width glyphs, 10 wide, advance 12, a space of 6, each glyph
# at its own place in a 1024-wide atlas. A second font, twice the size,
# shares nothing with it.
CHARS = [chr(c) for c in range(33, 127)]
GLYPHS = []
for font, size in ((0, 1.0), (1, 2.0)):
    GLYPHS.append((32, 6 * size, 0, 0, 0, 0, 0, 0, 0, 0, font))
    for k, ch in enumerate(CHARS):
        u0, v0 = (k * 12) / 1024, (font * 40) / 1024
        u1, v1 = u0 + 10 / 1024, v0 + 20 / 1024
        GLYPHS.append((ord(ch), 12 * size, 1 * size, 3 * size, 11 * size, 23 * size,
                       bits(u0), bits(v0), bits(u1), bits(v1), font))
glyphs = n.Glyphs(GLYPHS, {0: 20.0, 1: 40.0})
by_char = {(g[0], g[10]): g for g in GLYPHS}


def text_vertices(text: str, x: float, y: float, col: int = 0xFFE6F0F2, font: int = 0) -> list:
    """The vertices ImGui writes for `text` with its pen at x, y."""
    out = []
    for ch in text:
        g = by_char[(ord(ch), font)]
        _cp, adv, x0, y0, x1, y1, u0, v0, u1, v1, _f = g
        if ch != " ":
            out += [(x + x0, y + y0, u0, v0, col), (x + x1, y + y0, u1, v0, col),
                    (x + x1, y + y1, u1, v1, col), (x + x0, y + y1, u0, v1, col)]
        x += adv
    return out


def shape_vertices(x0, y0, x1, y1, col=0xFF222A2A) -> list:
    white = bits(0.5)
    return [(x0, y0, white, white, col), (x1, y0, white, white, col),
            (x1, y1, white, white, col), (x0, y1, white, white, col)]


def as_array(verts: list) -> np.ndarray:
    return np.array(verts, dtype=n.VERTEX)


# ------------------------------------------------------------------ decoding
verts = (shape_vertices(0, 0, 400, 40) + text_vertices("HOST A MATCH", 20, 10)
         + shape_vertices(0, 50, 400, 90) + text_vertices("Send this code:", 20, 60)
         + text_vertices("K7Q2MX", 20, 100, font=1))
runs = n.decode(as_array(verts), glyphs, "###panel")
check("each piece of text is one run", [r.text for r in runs] == ["HOST A MATCH", "Send this code:", "K7Q2MX"],
      str([r.text for r in runs]))
check("a run starts at its pen and line", (runs[0].left, runs[0].top) == (20.0, 10.0),
      str((runs[0].left, runs[0].top)))
check("the window and font are kept", runs[2].window == "###panel" and runs[2].font == 1)
check("the font's height as drawn is kept", runs[0].size == 20.0 and runs[2].size == 40.0,
      str((runs[0].size, runs[2].size)))
check("the colour is unpacked", runs[0].rgb == 0xE6F0F2 and runs[0].alpha == 0xFF)

two = n.decode(as_array(text_vertices("JOIN", 20, 10) + text_vertices("WATCH", 300, 10)), glyphs, "p")
check("text far apart on one line is two runs", [r.text for r in two] == ["JOIN", "WATCH"], str([r.text for r in two]))
spaced = n.decode(as_array(text_vertices("F1   or   Back", 0, 0)), glyphs, "p")
check("runs of spaces are kept", spaced and spaced[0].text == "F1   or   Back", spaced and spaced[0].text)
def cut_at(verts: list, bottom: float) -> list:
    """Characters cut off below `bottom`, as ImGui cuts text to a small frame:
    the lower corners move up, and their texture coordinates with them."""
    out = []
    for k in range(0, len(verts), 4):
        quad = verts[k:k + 4]
        top, low = quad[0][1], quad[2][1]
        if low > bottom:
            v_top, v_low = n.as_float(quad[0][3]), n.as_float(quad[2][3])
            v_cut = bits(v_top + (v_low - v_top) * (bottom - top) / (low - top))
            quad = [quad[0], quad[1], (quad[2][0], bottom, quad[2][2], v_cut, quad[2][4]),
                    (quad[3][0], bottom, quad[3][2], v_cut, quad[3][4])]
        out += quad
    return out


cut = n.decode(as_array(cut_at(text_vertices("Copy again", 20, 10), 28)), glyphs, "p")
check("text cut short by its frame is still read whole", [r.text for r in cut] == ["Copy again"],
      str([r.text for r in cut]))
odd = n.decode(as_array(shape_vertices(0, 0, 5, 5)[:3] + text_vertices("A", 10, 0)), glyphs, "p")
check("a glyph after a broken shape is still found", [r.text for r in odd] == ["A"])

# A tick box: a square frame as tall as its item at the left, its label after
# it, and when ticked a line in the check mark colour inside the square.
FRAME, HOVER, TICK = 0x222A2A, 0x393B2B, 0xFFE38C
box = (573.0, 278.0, 971.0, 317.0)


def tick_box_vertices(ticked: bool, frame_col=0xFF000000 | HOVER) -> list:
    out = shape_vertices(573, 278, 612, 317, frame_col)
    if ticked:
        out += [(580, 297, bits(0.5), bits(0.5), 0xFF000000 | TICK), (590, 307, bits(0.5), bits(0.5), 0xFF000000 | TICK),
                (604, 287, bits(0.5), bits(0.5), 0xFF000000 | TICK)]
    return out + text_vertices("Others may watch my sessions", 622, 286)


for ticked in (True, False):
    v = as_array(tick_box_vertices(ticked))
    mask = np.zeros(len(v), dtype=bool)
    got = n.decode(v, glyphs, "###panel", mask)
    state = n.tick_box(v, mask, box, {FRAME, HOVER}, TICK)
    check(f"a tick box {'ticked' if ticked else 'not ticked'} is found so", state is ticked, repr(state))
    check("its label is still read", [r.text for r in got] == ["Others may watch my sessions"])
gold_text = as_array(shape_vertices(573, 278, 612, 317, 0xFF000000 | HOVER)
                     + text_vertices("Others", 622, 286, col=0xFF000000 | TICK))
mask = np.zeros(len(gold_text), dtype=bool)
n.decode(gold_text, glyphs, "###panel", mask)
check("gold text beside an empty box is not its tick", n.tick_box(gold_text, mask, box, {FRAME, HOVER}, TICK) is False)
wide = as_array(shape_vertices(411, 740, 811, 779, 0xFF000000 | FRAME) + text_vertices("0", 600, 748))
mask = np.zeros(len(wide), dtype=bool)
n.decode(wide, glyphs, "###panel", mask)
check("a slider's wide frame is not a tick box",
      n.tick_box(wide, mask, (411.0, 740.0, 811.0, 779.0), {FRAME, HOVER}, TICK) is None)
check("style colours pack as ImGui packs them", n.packed_rgb(0x8C / 255, 0xE3 / 255, 1.0) == 0xFFE38C)


# ----------------------------------------------------------------- narration
HINT = 0x7E8A8C
GOLD, TEXT, DIM = 0x8CE3FF, 0xE6F0F2, 0x454545


def run(text, left, top, right, bottom, rgb=TEXT, alpha=0xFF, window="###panel", font=0, size=None):
    sizes = {0: 25.0, 1: 30.0, 2: 60.0}
    return n.Run(text, left, top, right, bottom, rgb, alpha, window, font, size or sizes[font])


def match_tab(code: str | None = None, shift: float = 0, ready: bool = False) -> list:
    """The Match tab; `shift` moves what is under JOIN down, as the hint "A code
    is 6 characters" appearing above the box does."""
    rows = [
        run("NETPLAY", 573, 185, 674, 210, GOLD, font=1),
        run("SFVR 0.2.2", 1228, 185, 1345, 205, HINT),
        run("Match", 586, 232, 652, 252), run("Settings", 691, 232, 782, 253), run("Debug", 820, 232, 890, 258),
        run("HOST A MATCH", 593, 299, 762, 324, GOLD, font=1),
        run("You get a code to send to the other player.", 573, 354, 1043, 374, 0xA8A696),
        run("JOIN", 573, 399, 626, 424, GOLD, font=1),
        run(code, 586, 458 + shift, 586 + 40 * len(code), 506 + shift, TEXT, font=2) if code else
        run("CODE", 586, 458 + shift, 734, 506 + shift, HINT, font=2),
        run("Paste", 1256, 475, 1318, 496),
        run("JOIN", 593, 550, 646, 575, DIM, 0xFF if ready else 0x99, font=1),
        run("WATCH", 986, 550, 1070, 575, DIM, 0xFF if ready else 0x99, font=1),
    ]
    for i, ch in enumerate("ABCDEFGH"):
        rows.append(run(ch, 607 + 98 * i, 622, 622 + 98 * i, 642))
    rows += [run("Delete", 727, 818, 798, 839), run("Clear", 1125, 818, 1186, 838),
             run("F1 or Back + Start closes this; the game gets no input while it is open.", 573, 870, 1346, 890, HINT)]
    return rows


FOCUS = {
    "host": (0x18BE2031, (573.0, 284.0, 1347.0, 344.8)),
    "code": (0x32F049F, (573.0, 451.0, 1219.0, 525.0)),
    "A": (0x161976A, (573.0, 615.0, 659.25, 654.0)),
    "match": (0x32C605F3, (573.0, 225.0, 668.0, 264.0)),
    "settings": (0x40, (678.0, 225.0, 795.0, 264.0)),
    "cancel": (0x41, (573.0, 520.0, 1347.0, 560.0)),
}
frame = [100]


def reading(focus: str | None, runs: list, extra: list = ()) -> n.Reading:
    frame[0] += 1
    fid, rect = FOCUS[focus] if focus else (0, None)
    return n.Reading(frame[0], tuple(runs) + tuple(extra), fid, "###panel" if focus else "", rect, HINT)


narrator = n.PanelNarrator()
said = [narrator.step(reading(None, []))]
said.append(narrator.step(reading("host", match_tab())))
check("closed says nothing", said[0] is None)
check("opening says the panel and the focused item", said[1] == "Netplay. HOST A MATCH", repr(said[1]))
check("the same frame again says nothing", narrator.step(reading("host", match_tab())) is None)
said = narrator.step(reading("code", match_tab()))
check("an empty box is said empty", said == "CODE, empty", repr(said))
said = narrator.step(reading("A", match_tab()))
check("a key of the keyboard is its letter", said == "A", repr(said))
said = narrator.step(reading("A", match_tab("K")))
check("a code typed is said as it fills in", said == "K", repr(said))
said = narrator.step(reading("A", match_tab("K7Q")))
check("and spelled", said == "K 7 Q", repr(said))
said = narrator.step(reading("A", match_tab("K7Q2MX", ready=True)))
check("a whole code says JOIN and WATCH are there to go to",
      said == "K 7 Q 2 M X. JOIN, available. WATCH, available", repr(said))
said = narrator.step(reading("A", match_tab()))
check("a cleared box is said empty", said == "CODE, empty", repr(said))
said = narrator.step(reading("code", match_tab("K7Q2MX")))
check("focus on a filled box spells it", said == "K 7 Q 2 M X", repr(said))
said = narrator.step(reading("match", match_tab()))
check("a tab is said as a tab", said == "Match tab", repr(said))
settings = [r for r in match_tab()[:5]] + [run("Name", 573, 299, 640, 319), run("(Steam name)", 700, 299, 840, 319, HINT),
                                           run("Others may watch my sessions", 610, 340, 900, 360)]
said = narrator.step(reading("settings", settings))
check("moving to another tab says only its name", said == "Settings tab", repr(said))
said = narrator.step(reading("settings", settings + [run("Checking for updates...", 573, 400, 800, 420)]))
check("a tab's contents changing under it are left for Alt A", said is None, repr(said))
narrator.step(reading("host", match_tab()))
relabelled = match_tab()[:5] + [run("HOSTING", 593, 299, 720, 324, GOLD, font=1),
                               run("Send this code to the other player:", 573, 354, 900, 374),
                               run("L6KDCW", 573, 390, 760, 438, TEXT, font=2)]
other = n.PanelNarrator()
other.step(reading("host", match_tab()))
said = other.step(reading("host", relabelled))
check("a button relabelled under focus is said first, then what came with it",
      said == "HOSTING. Send this code to the other player: L 6 K D C W", repr(said))
hosting = match_tab()[:5] + [run("HOSTING", 573, 299, 700, 324, GOLD, font=1),
                             run("Send this code to the other player:", 573, 340, 900, 360),
                             run("KQMXTR", 573, 380, 760, 428, TEXT, font=2),
                             run("Copied to the clipboard.", 573, 440, 800, 460, HINT),
                             run("Waiting for the other player...", 573, 480, 900, 500),
                             run("Cancel", 593, 530, 680, 550)]
said = narrator.step(reading("cancel", hosting))
check("a button changing the screen: what it says, a code spelled after its colon, then the new focus",
      said == "HOSTING. Send this code to the other player: K Q M X T R. Copied to the clipboard. "
              "Waiting for the other player... Cancel", repr(said))
said = narrator.step(reading("host", match_tab()))
check("coming back to a screen heard already says only the focus", said == "HOST A MATCH", repr(said))
said = narrator.step(reading("cancel", hosting))
check("going back to one heard already says only the focus", said == "Cancel", repr(said))
said = narrator.step(reading("cancel", hosting + [run("Player Two is here", 573, 600, 800, 620)]))
check("what appears while focus stays put is said", said == "Player Two is here", repr(said))
ticking = hosting + [run("12 ms", 1200, 299, 1260, 319)]
narrator.step(reading("cancel", ticking))
said = narrator.step(reading("cancel", hosting + [run("38 ms", 1200, 299, 1260, 319)]))
check("a number ticking over is not said again", said is None, repr(said))

said = narrator.step(n.Reading(frame[0] + 1, tuple(hosting), FOCUS["cancel"][0], "###panel", (573.0, 470.0, 1347.0, 510.0), HINT))
frame[0] += 1
check("focus kept on a button's old place reads what is under it", said == "Waiting for the other player...", repr(said))
said = narrator.step(reading("host", match_tab()))
check("coming back to a screen says what is above the new focus, then it", said == "HOST A MATCH", repr(said))
combo = [run("Ryu", 600, 300, 640, 320, window="##Combo_00"), run("Ken", 600, 330, 640, 350, window="##Combo_00")]
r = n.Reading(frame[0] + 1, tuple(match_tab() + combo), 0x77, "##Combo_00", (590.0, 325.0, 900.0, 355.0), HINT)
frame[0] += 1
said = narrator.step(r)
check("focus in a list the panel opened is read", said == "Ken", repr(said))

toast = [run("Player Two joined", 760, 60, 960, 80, window="##toasts")]
said = narrator.step(reading("cancel", hosting, toast))
check("a notice is said first", said and said.startswith("Player Two joined"), repr(said))
check("once", narrator.step(reading("cancel", hosting, toast)) is None)
said = narrator.step(reading(None, [], toast), now=100.0)
check("the panel left out of a frame is not closed yet", said is None, repr(said))
said = narrator.step(reading("cancel", hosting, toast), now=100.02)
check("and coming back a frame later says nothing", said is None, repr(said))
gone = reading(None, [], toast)
narrator.step(gone, now=101.0)
check("still gone a moment later", narrator.step(gone, now=101.1) is None)
said = narrator.step(gone, now=101.25)
check("gone for a fifth of a second it is closed", said == "Netplay closed", repr(said))
said = narrator.step(reading(None, [], [run("Session over: the other player left", 700, 60, 1000, 80, window="##toasts")]))
check("a notice with the panel closed is said", said == "Session over: the other player left", repr(said))

narrator = n.PanelNarrator()
narrator.step(reading("A", match_tab()))
hint = [run("A code is 6 characters, like ABCDEF.", 573, 440, 950, 460, HINT)]
said = narrator.step(reading("A", match_tab("A", shift=17) + hint))
check("a code typed after the box moves down is still the box", said == "A code is 6 characters, like ABCDEF. A",
      repr(said))
said = narrator.step(reading("A", match_tab("AAB", shift=17) + hint))
check("and spelled though it has no digit", said == "A A B", repr(said))


def settings(focus_id, rect, checked, extra=()):
    rows = [run("NETPLAY", 573, 130, 674, 155, GOLD, font=1), run("Match", 586, 177, 652, 197),
            run("Settings", 691, 177, 782, 197), run("Debug", 820, 177, 890, 197),
            run("(Steam name)", 586, 237, 742, 257, HINT), run("Name", 973, 237, 1037, 257),
            run("Others may watch my sessions", 622, 286, 970, 306)]
    frame[0] += 1
    return n.Reading(frame[0], tuple(rows) + tuple(extra), focus_id, "###panel", rect, HINT, checked)


narrator = n.PanelNarrator()
narrator.step(settings(1, (573.0, 229.0, 963.0, 268.0), None))
said = narrator.step(settings(1, (573.0, 229.0, 963.0, 268.0), None))
said = narrator.step(settings(2, box, True))
check("a tick box is said with its tick", said == "Others may watch my sessions, checked", repr(said))
said = narrator.step(settings(2, box, False))
check("unticking it says only that", said == "not checked", repr(said))
said = narrator.step(settings(1, (573.0, 229.0, 963.0, 268.0), None))
check("a box's label beside it comes first, then its hint", said == "Name, (Steam name), empty", repr(said))

debug = [run("P1", 424, 474, 448, 494), run("You are", 600, 474, 684, 494),
         run("0", 604, 748, 616, 768), run("Latency (ms)", 821, 748, 965, 768)]
narrator = n.PanelNarrator()
narrator.step(n.Reading(1, tuple(debug), 5, "###panel", (411.0, 466.0, 591.0, 505.0), HINT))
said = narrator.step(n.Reading(2, tuple(debug), 6, "###panel", (411.0, 740.0, 811.0, 779.0), HINT))
check("a slider is said with its label", said == "Latency (ms), 0", repr(said))
moved = [r if r.text != "0" else run("25", 598, 748, 622, 768) for r in debug]
said = narrator.step(n.Reading(3, tuple(moved), 6, "###panel", (411.0, 740.0, 811.0, 779.0), HINT))
check("moving it says the new value alone", said == "25", repr(said))
said = narrator.step(n.Reading(4, tuple(moved), 5, "###panel", (411.0, 466.0, 591.0, 505.0), HINT))
check("a list is said with its label", said == "You are, P1", repr(said))
check("Alt R says the label too", n.read_focus(n.Reading(4, tuple(moved), 5, "###panel", (411.0, 466.0, 591.0, 505.0),
                                                         HINT)) == "You are, P1")

narrator = n.PanelNarrator()
narrator.step(settings(1, (573.0, 229.0, 963.0, 268.0), None))
battle = [run("READY", 586, 1040, 680, 1060), run("Battle now", 586, 1080, 720, 1100)]
narrator.step(settings(9, (573.0, 1030.0, 700.0, 1070.0), None, battle))
said = narrator.step(settings(10, (573.0, 1070.0, 730.0, 1110.0), None, battle))
check("a button under a box's column is not spelled", said == "Battle now", repr(said))
said = narrator.step(settings(9, (573.0, 1030.0, 700.0, 1070.0), None, battle))
check("a word in the code's letters is a word", said == "READY", repr(said))

side = [run("P1", 40, 668, 66, 688, 0xFFB45A, window="##side1"),
        run("Player One (you)", 80, 668, 256, 688, window="##side1"),
        run("choosing...", 40, 715, 156, 735, HINT, window="##side1"),
        run("REMATCH", 60, 770, 167, 790, GOLD, window="##side1", font=1),
        run("CHARACTER SELECT", 60, 840, 273, 860, DIM, window="##side1", font=1)]
narrator = n.PanelNarrator()
narrator.step(reading("host", match_tab() + side))
said = narrator.step(n.Reading(frame[0] + 1, tuple(match_tab() + side), 0x99, "##side1", (40.0, 748.0, 442.0, 808.8), HINT))
frame[0] += 1
check("focus moving into another window says its title first", said == "P1 Player One (you). REMATCH", repr(said))
said = narrator.step(n.Reading(frame[0] + 1, tuple(match_tab() + side), 0x9A, "##side1", (40.0, 818.0, 442.0, 878.8), HINT))
frame[0] += 1
check("moving within it says only the item", said == "CHARACTER SELECT", repr(said))
check("Alt R there says which window", n.read_focus(n.Reading(frame[0], tuple(match_tab() + side), 0x9A, "##side1",
                                                              (40.0, 818.0, 442.0, 878.8), HINT))
      == "P1 Player One (you). CHARACTER SELECT")
pressed = n.Reading(frame[0] + 1, tuple(match_tab() + side), 0, "##side1", (40.0, 818.0, 442.0, 878.8), HINT)
check("focus dropped to no item for a moment says nothing", narrator.step(pressed) is None)
back = n.Reading(frame[0] + 2, tuple(match_tab() + side), 0x9A, "##side1", (40.0, 818.0, 442.0, 878.8), HINT)
frame[0] += 2
check("and given back says nothing", narrator.step(back) is None)
said = narrator.step(reading("host", match_tab() + side))
check("coming back to the panel says so", said == "Netplay. HOST A MATCH", repr(said))
narrator = n.PanelNarrator()
said = narrator.step(n.Reading(frame[0] + 1, tuple(match_tab() + side), 0x99, "##side1", (40.0, 748.0, 442.0, 808.8), HINT))
frame[0] += 1
check("opening with focus in another window says that window", said == "Netplay. P1 Player One (you). REMATCH",
      repr(said))

# ---------------------------------------------------------- the select screen
# As SFVR 0.2.2 drew its select preview (snapshots/netplay-select and
# netplay-loadout, 1 November 2026): a row of steps and button hints along the
# top, the lit step dark on gold, big texts drawn twice with a black shadow,
# each player's half of the screen with their fighter and loadout, a gold bar
# fading out behind the loadout row the cursor is on; and the panel's preview
# of the match-over window, holding focus, beside it.
def screen_text(text, left, top, size, rgb=0xFFFFFF, font=5):
    width = 0.5 * size * len(text)
    shadow = 4 if size > 80 else 2
    return [run(text, left, top + shadow, left + width, top + shadow + size, 0, 220, "##Background", font, size),
            run(text, left, top, left + width, top + size, rgb, 0xFF, "##Background", font, size)]


def bar(lit, *hints):
    steps = [("Stage select", 45), ("Character", 188), ("Loadout", 311), ("Ready", 419), ("Close preview", 512)]
    return [run(t, x, 28, x + 9 * len(t), 46, 0x15130D if t == lit else 0xF4F1E8, window="##Background", size=18.0)
            for t, x in steps] + \
        [run(t, 1500 + 120 * i, 28, 1500 + 120 * i + 9 * len(t), 48, 0xF4F1E8, window="##Background", size=20.4)
         for i, t in enumerate(hints)]


def stage_step(stage="Ring of Destiny", setting=None, prompt="You select the stage."):
    runs = bar("Stage select", *(["Setting"] if setting else []), "Confirm stage", "Menu")
    runs += screen_text("STAGE SELECT", 827, 91, 50.4) + screen_text(stage, 802, 565, 55.2)
    if setting:
        runs.append(run(f"Setting {setting}", 910, 524, 1010, 543, 0xE9C46A, window="##Background", size=19.2))
    return runs + [run(prompt, 871, 992, 1060, 1011, 0xBDB8AA, window="##Background", size=19.2)]


def table(left, values, arrows=False):
    out = []
    for i, (label, value) in enumerate(zip(("Costume", "Color", "V-Skill"), values)):
        top = 140 + 53 * i
        out += [run(label, left, top, left + 100, top + 23, 0xF4F1E8, window="##Background", size=22.8),
                run(value, left + 400, top + 1, left + 520, top + 23, 0xF4F1E8, window="##Background", size=21.6)]
        if arrows:
            out += [run(c, x, top + 2, x + 8, top + 20, 0xE9C46A, window="##Background", size=18.0)
                    for c, x in (("<", left + 198), (">", left + 661))]
    return out


def character_step(mine="RYU", ping="38 ms", loadout=None, help_line="Pick a costume."):
    """The fighter step, or with `loadout` (my three values) the loadout step."""
    runs = bar("Loadout" if loadout else "Character", *(["Ready", "Back"] if loadout else ["Select", "Stage"]), "Menu")
    runs += table(1228, ("Story", "01", "II HAZANSHU"))
    if loadout:
        runs += table(52, loadout, arrows=True)
        runs.append(run(help_line, 52, 507, 200, 524, 0xD9D4C6, window="##Background", size=16.8))
    runs += [run("YOU  (you)", 143, 568, 230, 587, 0xF4F1E8, window="##Background", size=19.2),
             run(ping, 1544, 570, 1590, 588, 0x7FD88B, window="##Background", size=18.0),
             run("MOCK OPPONENT", 1622, 568, 1775, 587, 0xF4F1E8, window="##Background", size=19.2),
             run("1P", 866, 877, 880, 891, 0xFFFFFF, window="##Background", size=14.4)]
    return runs + screen_text(mine, 141, 595, 88.8) + screen_text("CHUN-LI", 1492, 595, 88.8) + \
        screen_text("CHARACTER SELECT", 772, 602, 50.4) + screen_text("?", 944, 806, 69.6, font=2)


def select_side(delay="3 frames"):
    return [run("P1  Player One (you)", 40, 661, 256, 691, 0x5C9EFF, window="##side1", font=1),
            run("choosing...", 40, 713, 156, 738, 0xA8A696, window="##side1"),
            run("REMATCH", 60, 763, 167, 793, DIM, window="##side1", font=1),
            run("CHARACTER SELECT", 60, 833, 273, 863, DIM, window="##side1", font=1),
            run("LEAVE", 60, 903, 140, 933, DIM, window="##side1", font=1),
            run(delay, 132, 975, 230, 1000, window="##side1"),
            run("Delay", 335, 975, 400, 1000, window="##side1"),
            run("Suggested delay 1 (ping 38 ms)", 40, 1017, 383, 1042, 0xA8A696, window="##side1")]


SIDE = {"rematch": (0x51, (40.0, 748.0, 442.0, 808.8)), "character": (0x52, (40.0, 818.0, 442.0, 878.8)),
        "leave": (0x53, (40.0, 888.0, 442.0, 948.8)), "delay": (0x54, (40.0, 968.0, 325.0, 1007.0))}
ROWS = {"costume": (0.0, 129.6, 336.0, 177.6), "color": (0.0, 182.4, 336.0, 230.4)}


def select(screen, focus="leave", delay="3 frames", row=None, extra=()):
    frame[0] += 1
    fid, rect = SIDE[focus] if focus else (0, None)
    return n.Reading(frame[0], tuple(screen) + tuple(select_side(delay) if focus else ()) + tuple(extra),
                     fid, "##side1" if focus else "", rect, HINT, None, 1920.0, (ROWS[row],) if row else ())


narrator = n.PanelNarrator()
said = narrator.step(select(stage_step()), now=10.0)
check("the select screen coming up says its heading, the stage and the prompt",
      said == "STAGE SELECT. Ring of Destiny. You select the stage.", repr(said))
check("the same again says nothing", narrator.step(select(stage_step()), now=10.1) is None)
said = narrator.step(select(stage_step(), "character"), now=10.2)
check("the match-over preview's focus, moved by the same arrows as the cursor, is not said", said is None, repr(said))
said = narrator.step(select(stage_step("Suzaku Castle", "1 / 2"), "character"), now=10.3)
check("the cursor onto another stage says it, with its setting", said == "Suzaku Castle. Setting 1 of 2", repr(said))
said = narrator.step(select(stage_step("Suzaku Castle at Night", "2 / 2"), "character"), now=10.4)
check("another setting of it says the new name", said == "Suzaku Castle at Night", repr(said))
said = narrator.step(select(stage_step("Ring of Power"), "delay", "4 frames"), now=10.5)
check("nor the preview's delay stepping with the stage", said == "Ring of Power", repr(said))
said = narrator.step(select(character_step(), "delay"), now=10.7)
check("the fighter step: its heading, my fighter, the other player's", said == "CHARACTER SELECT. RYU. Other player, CHUN-LI",
      repr(said))
said = narrator.step(select(character_step("ALEX"), "delay"), now=10.8)
check("the cursor onto another fighter says them", said == "ALEX", repr(said))
said = narrator.step(select(character_step("ALEX", "41 ms"), "delay"), now=10.9)
check("a ping ticking over is not said", said is None, repr(said))
mine = ("DEFAULT", "01", "I FUKURO")
said = narrator.step(select(character_step("ALEX", loadout=mine), row="costume"), now=11.0)
check("the loadout step: its name, as the heading stays, and the row the cursor is on",
      said == "Loadout. Costume, DEFAULT", repr(said))
said = narrator.step(select(character_step("ALEX", loadout=("Kenji",) + mine[1:]), row="costume"), now=11.1)
check("a value changed says the value", said == "Kenji", repr(said))
said = narrator.step(select(character_step("ALEX", loadout=("Kenji",) + mine[1:], help_line="Pick a color."),
                            row="color"), now=11.2)
check("the cursor down a row says the row, not its help, nor the other player's", said == "Color, 01", repr(said))
loadout = select(character_step("ALEX", loadout=("Kenji", "02", "I FUKURO"), help_line="Pick a color."), row="color")
said = narrator.step(loadout, now=11.3)
check("a number changed in the row is said though it only ticks over elsewhere", said == "02", repr(said))
check("Alt R on the loadout says the step, the fighters, the row and its help",
      n.read_focus(loadout) == "Loadout. CHARACTER SELECT. ALEX. Other player, CHUN-LI. Color, 02. Pick a color.",
      n.read_focus(loadout))
texts = [line.text for line in n.read_lines(loadout)]
check("Alt A reads the screen row by row, the top row too, each shadow once, then the side window",
      texts[0] == "Stage select, Character, Loadout, Ready, Close preview, Ready, Back, Menu"
      and "Color, <, 02, >, Color, 01" in texts and "ALEX, CHARACTER SELECT, CHUN-LI" in texts
      and "3 frames, Delay" in texts, str(texts))
check("the select screen takes the read keys", loadout.showing)
narrator.step(reading("host", match_tab()), now=11.4)
said = narrator.step(loadout, now=11.5)
check("closing the panel waits a moment", said is None, repr(said))
said = narrator.step(loadout, now=11.8)
check("then says so, and not the screen again", said == "Netplay closed", repr(said))
narrator.step(select([], None), now=12.0)
narrator.step(select([], None), now=12.3)
said = narrator.step(select(stage_step(prompt="Player 1 is selecting the stage..."), "rematch"), now=13.0)
check("the screen gone and back is said again",
      said == "STAGE SELECT. Ring of Destiny. Player 1 is selecting the stage...", repr(said))
said = narrator.step(select([], "rematch"), now=14.0)
check("the side window holding focus with the screen gone is followed, as after a match",
      said == "P1 Player One (you). REMATCH", repr(said))
minimised = n.Reading(1, (run("Y", 0, 0, 13, 20, 0xBDB8AA, window="##Background"),), 0x52, "##side1", None, HINT)
check("minimised, the stray letter SFVR draws is not a screen",
      n.PanelNarrator().step(minimised) is None and not minimised.showing)
check("a character the font lacks is said as a pause", n.tidy("120 ms to the host  \ufffd  3 watching")
      == "120 ms to the host, 3 watching")
fade = shape_vertices(0, 182.4, 336, 230.4, 0x8CF0C85A)
fade[1] = (336.0, 182.4, fade[1][2], fade[1][3], 0x00F0C85A)
fade[2] = (336.0, 230.4, fade[2][2], fade[2][3], 0x00F0C85A)
backing = shape_vertices(0, 129.6, 744, 177.6, 0xEB0B0908)
backing[1] = (744.0, 129.6, backing[1][2], backing[1][3], 0xC80B0908)
backing[2] = (744.0, 177.6, backing[2][2], backing[2][3], 0xC80B0908)
verts = as_array(backing + fade)
check("the cursor bar is the rectangle fading to nothing, not a row's dark backing",
      n.cursor_bars(verts, np.zeros(len(verts), dtype=bool)) == ((0.0, 182.39999389648438, 336.0, 230.39999389648438),),
      str(n.cursor_bars(verts, np.zeros(len(verts), dtype=bool))))

# ---------------------------------------------------------------- read keys
r = reading("host", match_tab())
check("Alt R adds the line under a button", n.read_focus(r) == "HOST A MATCH. You get a code to send to the other player.",
      n.read_focus(r))
check("Alt R on a key adds nothing", n.read_focus(reading("A", match_tab())) == "A")
lines = n.read_lines(reading("code", match_tab()))
texts = [line.text for line in lines]
check("Alt A reads the panel row by row", texts[1] == "Match, Settings, Debug" and "A, B, C, D, E, F, G, H" in texts,
      str(texts))
check("an unavailable item is said so", "JOIN, unavailable, WATCH, unavailable" in texts, str(texts))
check("the focused row is marked for the review cursor", [line.selected for line in lines].count(True) == 1
      and lines[texts.index("CODE, Paste")].selected)

# ---------------------------------------------------------- wrapped lines
# SFVR's update notice as 0.2.6.1 drew it (7 November 2026): a heading, then
# a paragraph wrapped over lines 25 pixels apart, then a sentence of its own.
def line(text, top, rgb=0x96A6A8, left=573.0):
    return n.Run(text, left, top, left + 600, top + 25, rgb, 255, "###panel", 3, 25.0)


notice = [line("SFVR 0.3.0 is available, from 2026-11-07.", 712, 0x8CE3FF),
          line("Custom rooms: up to 16 players on up to eight tables with", 747),
          line("their own rules, in public rooms anyone can find or private", 772),
          line("ones by code, with chat.", 797),
          line("Both players need the same version to play each other.", 832),
          line("lower case but a widget further down", 900)]
joined = [r.text for r in n.join_wrapped(notice)]
check("wrapped lines are one paragraph", joined[1] == "Custom rooms: up to 16 players on up to eight tables with "
      "their own rules, in public rooms anyone can find or private ones by code, with chat.", str(joined))
check("a line in another colour, a capital, or further down stays apart", len(joined) == 4 and joined[0].startswith("SFVR")
      and joined[2].startswith("Both") and joined[3].startswith("lower"), str(joined))
check("a symbol the font lacks is left out of a name, a question keeps its mark",
      [n.say(line(t, 0)) for t in ("? EASTWOOD ?", "Leave the room?")] == ["EASTWOOD", "Leave the room?"])
check("a sentence then a button has no comma between",
      n.commas(["Play online in rooms of up to 16 players.", "Select", "SFVR settings"])
      == "Play online in rooms of up to 16 players. Select, SFVR settings")

# ------------------------------------------------------ SFVR 0.3.0's menus
# Shaped like the settings screen recorded on 7 November 2026: the title
# along the top, rows of a label and a value, the selected row's text dark on
# its gold bar, and a panel beside the list explaining the selection.
LIGHT, DARK = 0xE8F1F4, 0x0B0B0B


def text(t, left, top, size=25.2, rgb=LIGHT, alpha=255):
    return n.Run(t, left, top, left + 12 * len(t), top + size, rgb, alpha, "##Background", 0, size)


def settings(lit_row, value="Off", details="Check at start", alpha=255, dialog=False):
    rows = [("Check at start", "On", 236), ("Name", "Kongster (Steam name)", 342), ("Streamer mode", value, 582)]
    runs = [text("SFVR SETTINGS", 57, 26, 48.0, 0xFFFFFF, alpha), text("Version 0.3.0", 485, 46, 24.0, alpha=alpha)]
    for label, val, top in rows:
        rgb = DARK if label == lit_row and not dialog else LIGHT
        runs += [text(label, 107, top, rgb=rgb, alpha=alpha), text(val, 810, top, rgb=rgb, alpha=alpha)]
    runs += [text(details, 1231, 187, 33.6, alpha=alpha),
             text("Shown to other players. Leave it empty to use your Steam name.", 1231, 247, 24.0, alpha=alpha)]
    if dialog:
        runs += [text("Custom Rooms are unavailable", 633, 408, 33.6),
                 text("The rooms server is up, but isn't hosting rooms right now.", 633, 463, 22.8),
                 text("Try again", 763, 552, 21.6, DARK), text("Close", 1114, 552, 21.6)]
    return n.Reading(1, tuple(runs), width=1920.0)


menu = n.PanelNarrator()
check("a menu screen says its title and selection", menu.step(settings("Check at start"), 0.0)
      == "SFVR SETTINGS. Check at start, On", str(menu.step(settings("Check at start"), 0.0)))
said = menu.step(settings("Name", details="Kongster"), 1.0)
check("moving says the selection alone, not the panel beside it", said == "Name, Kongster (Steam name)", str(said))
menu.step(settings("Streamer mode", details="Streamer mode"), 2.0)
said = menu.step(settings("Streamer mode", "On", details="Streamer mode"), 3.0)
check("left or right says the new value", said == "On", str(said))
said = menu.step(settings("Streamer mode", "On", details="Streamer mode", dialog=True), 4.0)
check("a dialog says its heading, its sentence and its button", said ==
      "Custom Rooms are unavailable. The rooms server is up, but isn't hosting rooms right now. Try again", str(said))
check("a screen fading says nothing", n.PanelNarrator().step(settings("Name", alpha=50), 0.0) is None)
check("Alt R adds what the selection does", n.read_focus(settings("Name", details="Kongster"))
      == "Name, Kongster (Steam name). Shown to other players. Leave it empty to use your Steam name.",
      n.read_focus(settings("Name", details="Kongster")))
steps = [text(t, x, 28, 15.0, DARK if t == "Stage select" else LIGHT) for t, x in
         (("Stage select", 45), ("Character", 188), ("Loadout", 311), ("Ready", 419))]
select = n.Reading(1, tuple(steps + [text("STAGE SELECT", 827, 91, 50.4, 0xFFFFFF),
                                     text("Stage", 1600, 1025, 20.0, DARK)]), width=1920.0)
check("the select screen keeps its own rules", not select.lit)

# A room, shaped like Kongster's room as recorded: tables down the left, each
# a header row and two seats; the players list and chat on the right; the
# chat's Send button always gold.
def room(table=2, seat="Sit here as P1", status="Watching Table 1", chat=("DCQ left",), helpline="ROOM OPEN"):
    runs = [text("Kongster's room", 57, 26, 48.0, 0xFFFFFF)]
    for k, top in ((1, 106), (2, 334), (3, 562)):
        rgb = DARK if k == table else LIGHT
        runs += [text(f"TABLE {k}", 76, top, rgb=rgb),
                 text("First to 2 · winner stays, up to 3 · 99 seconds", 546, top, 22.8, rgb),
                 text("0 in queue", 936, top, 22.8, rgb),
                 text(seat if k == table else "Open seat", 235, top + 105, 21.6),
                 text("VS", 524, top + 95, 36.0, 0x8A8170), text("Open seat", 785, top + 106, 21.6)]
    runs += [text("KONGS...", 1253, 150, 22.8), text("(you)", 1335, 151, 21.6), text(status, 1392, 151, 21.6, 0x7FD88B),
             text("Wired", 1780, 152, 20.4), text("ROOM CHAT", 1092, 652, 19.2, 0xE9C46A)]
    for k, line in enumerate(reversed(chat)):
        if isinstance(line, tuple):
            runs += [text(line[0], 1092, 904 - 27 * k, 22.8, 0xE9C46A), text(line[1], 1293, 904 - 27 * k, 22.8)]
        else:
            runs.append(text(line, 1092, 904 - 27 * k, 22.8))
    runs += [text("Say something (Back + Y, or click here)", 1108, 945, 22.8), text("Send", 1780, 945, 21.6, DARK),
             text(helpline, 57, 1026, 24.0)]
    return n.Reading(1, tuple(runs), width=1920.0)


lobby = n.PanelNarrator()
said = lobby.step(room(), 0.0)
check("a room says its title, the table with its seats, and where the player is",
      said == "Kongster's room. TABLE 2, First to 2, winner stays, up to 3, 99 seconds, 0 in queue, "
      "Sit here as P1, VS, Open seat. Send. You: Watching Table 1", str(said))
said = lobby.step(room(table=3), 1.0)
check("moving to another table says that table, not Send again",
      said == "TABLE 3, First to 2, winner stays, up to 3, 99 seconds, 0 in queue, Sit here as P1, VS, Open seat",
      str(said))
said = lobby.step(room(table=1), 1.5)
check("the top table is read, below the title strip",
      said == "TABLE 1, First to 2, winner stays, up to 3, 99 seconds, 0 in queue, Sit here as P1, VS, Open seat",
      str(said))
lobby.step(room(table=3), 1.8)
said = lobby.step(room(table=3, seat="KONGSTER", status="Table 3 · seated"), 2.0)
check("sitting says who is in the seat now and where the player is", said == "KONGSTER. You: Table 3, seated",
      str(said))
said = lobby.step(room(table=3, seat="KONGSTER", status="Table 3 · seated",
                       chat=("DCQ left", "Forever Solo Queue joined")), 3.0)
check("a new chat line is said", said == "Forever Solo Queue joined", str(said))
said = lobby.step(room(table=0, seat="KONGSTER", status="Table 3 · seated",
                       chat=("DCQ left", "Forever Solo Queue joined"), helpline="That's you."), 4.0)
check("moving to the players list says the line along the bottom", said == "That's you.", str(said))

said = lobby.step(room(table=0, seat="KONGSTER", status="Table 3 · seated", helpline="That's you.",
                       chat=("DCQ left", "Forever Solo Queue joined", ("FOREVER SOLO QUEUE", "They cant find you"))),
                  5.0)
check("a player's chat message is said with their name", said == "FOREVER SOLO QUEUE: They cant find you", str(said))
coded = room()
coded = n.Reading(1, coded.runs + (text("Private", 490, 46, 24.0, 0x7FD88B), text("Code", 564, 46, 24.0),
                                   text("PKG7NU", 616, 46, 24.0, 0xE9C46A), text("Copy code", 758, 46, 24.0)),
                  width=1920.0)
said = n.PanelNarrator().step(coded, 0.0)
check("a room says whether it is private and its code, spelled",
      said.startswith("Kongster's room. Private, Code, P K G 7 N U. TABLE 2"), str(said))
real_style = n.buttons.style
try:
    n.buttons.style = lambda: "playstation"
    help_said = n.room_help(coded)
    n.buttons.style = lambda: "keyboard"
    keyboard_said = n.room_help(coded)
finally:
    n.buttons.style = real_style
check("Alt R in a room says how to copy the code and to chat, in the chosen buttons",
      help_said == ["Share copies the code.", "Chat box: Say something (Share + triangle, or click here)"],
      str(help_said))
check("with keyboard keys chosen, SFVR's controller names stay", keyboard_said[0] == "Back copies the code.",
      str(keyboard_said))
over = room(chat=("SFVR left",))
over = n.Reading(1, over.runs + (text("Leave queue", 1500, 904, 21.6),), width=1920.0)
check("a button over the chat stays out of its line", n.chat_lines(over) == ("SFVR left",), str(n.chat_lines(over)))
check("the row just left, fading, is not said again",
      n.fading_out(("V-Skill",), (("V-Skill", "I RAKAN"),)) and not n.fading_out(("V-Trigger", "II"), (("V-Skill", "I"),)))


# The window after a game, in front, as recorded: each player's label and
# name, a big score, their vote, and on the player's side the choices.
def fore(t, left, top, size=19.2, rgb=LIGHT):
    return n.Run(t, left, top, left + 12 * len(t), top + size, rgb, 255, "##Foreground", 0, size)


def after_game(my_vote="Choosing...", their_vote="Choosing...", lit="Rematch", note="Rematch in 15 s", notice=None):
    runs = [fore("P1 · YOU", 83, 480, 16.8), fore("Kongster", 427, 478, 18.0), fore("0", 83, 528, 48.0),
            fore("of 2 to win the set", 125, 554), fore(my_vote, 83, 595)]
    for t, left, top in (("Rematch", 249, 640), ("Character select", 219, 708), ("Leave", 261, 775)):
        runs.append(fore(t, left, top, 21.6, DARK if t == lit else LIGHT))
    runs += [fore("Delay", 110, 846, 21.6), fore("3 frames", 356, 846, 21.6),
             fore("Suggested delay 1 (ping 64 ms)", 83, 897, 18.0), fore(note, 83, 956, 18.0),
             fore("P2", 1432, 780, 16.8), fore("Forever Solo Queue", 1710, 778, 18.0), fore("1", 1432, 828, 48.0),
             fore("of 2 to win the set", 1474, 854), fore(their_vote, 1432, 895),
             fore("Input delay 0 frames", 1432, 956, 18.0)]
    if notice:
        runs.append(fore(notice, 1605, 40))
    runs.append(text("Kongster (you)  (0/1)", 178, 4, 30.0))
    return n.Reading(1, tuple(runs), width=1920.0)


match = n.PanelNarrator()
said = match.step(after_game(), 0.0)
check("the window after a game says both scores, the countdown and the choice",
      said == "You: 0 of 2 to win the set, Choosing... Forever Solo Queue: 1 of 2 to win the set, Choosing... "
      "Rematch in 15 s. Rematch", str(said))
said = match.step(after_game(lit="Leave", note="Leave ends the set here."), 1.0)
check("moving says the choice and what it does", said == "Leave. Leave ends the set here.", str(said))
said = match.step(after_game(lit="Leave", note="Leave ends the set here.", their_vote="Rematch",
                             notice="Forever Solo Queue wants a rematch"), 2.0)
check("the other player's vote and notice are said", said == "Forever Solo Queue wants a rematch. "
      "Forever Solo Queue: Rematch", str(said))
said = match.step(after_game(my_vote="Rematch", lit="Rematch", note="Leave ends the set here.", their_vote="Rematch",
                             notice="Forever Solo Queue wants a rematch"), 3.0)
check("the player's own vote is said as theirs", said == "Rematch. You: Rematch", str(said))

# Polarity's benchmark: a countdown along the bottom, then its results, a
# dialog in front with no players in it.
def countdown(left):
    return n.Reading(1, (fore("BENCHMARK", 57, 1042), fore(f"Please wait, and keep the game window in focus · {left} left",
                                                            170, 1040, 21.6), fore("Stop", 1842, 1040, 20.4)), width=1920.0)


bench = n.PanelNarrator()
first = bench.step(countdown("0:44"), 0.0)
check("a countdown in a notice is said once, not every second",
      first == "BENCHMARK. Please wait, and keep the game window in focus, 0:44 left. Stop"
      and bench.step(countdown("0:43"), 1.0) is None, str(first))
results = n.Reading(1, (fore("BENCHMARK · NOV 13, 17:03", 453, 158), fore("Polarity 0.4.3", 1369, 157, 20.4),
                        fore("PASS", 453, 192, 76.8, 0x7FD88B), fore("60.0 fps average", 695, 204, 33.6),
                        fore("1% low", 475, 321, 20.4), fore("Slowest frame", 817, 321, 20.4),
                        fore("49.5 fps", 475, 352, 31.2), fore("21.5 ms", 817, 352, 31.2),
                        fore("No mods are installed.", 487, 542, 22.8),
                        fore("Done", 682, 636, 21.6, DARK), fore("Run again", 1177, 636, 21.6)), width=1920.0)
check("a dialog in front is not taken for the window after a game", not results.result and results.dialog)
said = bench.step(results, 2.0)
check("the benchmark's results are read in order, each figure with its label",
      said == "BENCHMARK, NOV 13, 17:03, Polarity 0.4.3. PASS, 60.0 fps average. 1% low 49.5 fps, "
      "Slowest frame 21.5 ms. No mods are installed. Done", str(said))

# ------------------------------------------------------- fonts built again
# SFVR builds its fonts again when a player's name brings a character they
# lack, which moves every glyph. The reader must take the new table, but not
# one read while the atlas was still changing.
reader = n.PanelReader()
reader.mem, reader.ctx, reader.glyphs, reader._atlas = object(), 1, "old table", ("atlas", 191)
keys, real_key, real_read = [], n.atlas_key, n.read_glyphs
n.atlas_key = lambda mem, ctx: keys.pop(0)
n.read_glyphs = lambda mem, ctx: "new table"
try:
    keys[:] = [("atlas", 191)]
    reader._follow_atlas()
    check("an unchanged atlas keeps the table", reader.glyphs == "old table" and not keys)
    keys[:] = [("atlas", 192), ("atlas", 193)]
    reader._follow_atlas()
    check("a table read while the atlas moved is not taken", reader.glyphs == "old table")
    keys[:] = [("atlas", 193), ("atlas", 193)]
    reader._follow_atlas()
    check("the fonts built again are read again", reader.glyphs == "new table" and reader._atlas == ("atlas", 193))
finally:
    n.atlas_key, n.read_glyphs = real_key, real_read

# --------------------------------------------------------------- status line
# The title callback as SFVR 0.2.2 builds it, at made-up addresses: the
# prefix's lea, some code, then the line's length tested, a length check, and
# the line's own lea. A second test of another string, with no prefix before
# it, must not be taken for it.
CODE_BASE, PREFIX, LINE, OTHER = 0x10000, 0x90000, 0xA0770, 0xA0800
DATA = (0xA0000, 0xB0000)


def rip(opcode: bytes, at: int, target: int) -> bytes:
    """An instruction ending in disp32 that points at `target`, placed at `at`."""
    return opcode + struct.pack("<i", target - (at + len(opcode) + 4))


def title_code(jump: bytes = b"\x0F\x84") -> tuple[bytes, int]:
    code = bytearray(b"\xCC" * 0x40)
    code += rip(b"\x48\x8D\x35", CODE_BASE + len(code), PREFIX)          # lea rsi, [prefix]
    code += b"\x90" * 0x1F0
    code += rip(b"\x48\x8B\x3D", CODE_BASE + len(code), LINE + 0x10)     # mov rdi, [line.size]
    code += b"\x48\x85\xFF"                                              # test rdi, rdi
    at = CODE_BASE + len(code)
    code += jump + struct.pack("<i", 0x142)                              # je <title done>
    code += b"\x48\x8B\xC1\x48\x2B\xC7\x48\x83\xF8\x01"                  # the length check
    code += b"\x0F\x82" + struct.pack("<i", 0x36C)
    code += rip(b"\x4C\x8D\x3D", CODE_BASE + len(code), LINE)            # lea r15, [line]
    code += b"\xCC" * 0x900
    code += rip(b"\x48\x8B\x3D", CODE_BASE + len(code), OTHER + 0x10)
    code += b"\x48\x85\xFF\x0F\x84" + struct.pack("<i", 0x20)
    code += rip(b"\x4C\x8D\x3D", CODE_BASE + len(code), OTHER)
    return bytes(code), at


code, jump_at = title_code()
check("the title's status line is found by the prefix before it",
      n.find_status_line(code, CODE_BASE, PREFIX, DATA) == (jump_at, LINE, False),
      str(n.find_status_line(code, CODE_BASE, PREFIX, DATA)))
quieted, _ = title_code(n.QUIET_JUMP)
check("once quieted it is known as quieted, and found again",
      n.find_status_line(quieted, CODE_BASE, PREFIX, DATA) == (jump_at, LINE, True))
check("without the prefix nothing is taken", n.find_status_line(code, CODE_BASE, PREFIX + 8, DATA) is None)
check("a line outside SFVR's data is not taken", n.find_status_line(code, CODE_BASE, PREFIX, (0, 0x1000)) is None)


class StringMemory:
    """Two std::strings as MSVC lays them out: one in place, one on the heap."""
    def __init__(self) -> None:
        heap = b"watching | frame 1394 | 434 frames in hand"
        self.at = {
            0x100: b"connection lost\0" + struct.pack("<QQ", 15, 15),
            0x200: struct.pack("<Q", 0x900) + b"\0" * 8 + struct.pack("<QQ", len(heap), 47),
            0x900: heap,
            0x300: b"\0" * 16 + struct.pack("<QQ", 9999, 15),
        }

    def read(self, address: int, size: int) -> bytes | None:
        raw = self.at.get(address)
        return raw[:size] if raw is not None else None


mem = StringMemory()
check("a short status line is read in place", n.read_string(mem, 0x100) == "connection lost")
check("a long one through its pointer", n.read_string(mem, 0x200) == "watching | frame 1394 | 434 frames in hand")
check("a torn one is not read", n.read_string(mem, 0x300) is None)
for line, words in (("watching | frame 1394 | 434 frames in hand", "Watching, frame 1394, 434 frames in hand"),
                    ("P1 | frame 5000 | ping 40 ms | rollbacks 12 (max 3) | ahead 0.5 | DESYNC",
                     "P1, frame 5000, ping 40 ms, rollbacks 12 (max 3), ahead 0.5, DESYNC"),
                    ("connection lost", "Connection lost"),
                    ("", "No netplay session."),
                    (None, "No Polarity status found.")):
    check(f"F11 says {words!r}", n.status_words(line) == words, n.status_words(line))

print("all passed" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
