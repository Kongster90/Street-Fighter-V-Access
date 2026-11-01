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


def run(text, left, top, right, bottom, rgb=TEXT, alpha=0xFF, window="###panel", font=0):
    sizes = {0: 25.0, 1: 30.0, 2: 60.0}
    return n.Run(text, left, top, right, bottom, rgb, alpha, window, font, sizes[font])


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

print("all passed" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
