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
glyphs = n.Glyphs(GLYPHS)
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
check("a run starts at its first glyph's pen and line", (runs[0].left, runs[0].top) == (21.0, 10.0),
      str((runs[0].left, runs[0].top)))
check("the window and font are kept", runs[2].window == "###panel" and runs[2].font == 1)
check("the colour is unpacked", runs[0].rgb == 0xE6F0F2 and runs[0].alpha == 0xFF)

two = n.decode(as_array(text_vertices("JOIN", 20, 10) + text_vertices("WATCH", 300, 10)), glyphs, "p")
check("text far apart on one line is two runs", [r.text for r in two] == ["JOIN", "WATCH"], str([r.text for r in two]))
spaced = n.decode(as_array(text_vertices("F1   or   Back", 0, 0)), glyphs, "p")
check("runs of spaces are kept", spaced and spaced[0].text == "F1   or   Back", spaced and spaced[0].text)
odd = n.decode(as_array(shape_vertices(0, 0, 5, 5)[:3] + text_vertices("A", 10, 0)), glyphs, "p")
check("a glyph after a broken shape is still found", [r.text for r in odd] == ["A"])


# ----------------------------------------------------------------- narration
HINT = 0x7E8A8C
GOLD, TEXT, DIM = 0x8CE3FF, 0xE6F0F2, 0x454545


def run(text, left, top, right, bottom, rgb=TEXT, alpha=0xFF, window="###panel", font=0):
    return n.Run(text, left, top, right, bottom, rgb, alpha, window, font)


def match_tab(code: str | None = None) -> list:
    rows = [
        run("NETPLAY", 573, 185, 674, 210, GOLD, font=1),
        run("SFVR 0.2.2", 1228, 185, 1345, 205, HINT),
        run("Match", 586, 232, 652, 252), run("Settings", 691, 232, 782, 253), run("Debug", 820, 232, 890, 258),
        run("HOST A MATCH", 593, 299, 762, 324, GOLD, font=1),
        run("You get a code to send to the other player.", 573, 354, 1043, 374, 0xA8A696),
        run("JOIN", 573, 399, 626, 424, GOLD, font=1),
        run(code, 586, 458, 586 + 40 * len(code), 506, TEXT, font=2) if code else
        run("CODE", 586, 458, 734, 506, HINT, font=2),
        run("Paste", 1256, 475, 1318, 496),
        run("JOIN", 593, 550, 646, 575, DIM, 0x99, font=1), run("WATCH", 986, 550, 1070, 575, DIM, 0x99, font=1),
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
said = narrator.step(reading(None, [], toast))
check("closing says so", said == "Netplay closed", repr(said))
said = narrator.step(reading(None, [], [run("Session over: the other player left", 700, 60, 1000, 80, window="##toasts")]))
check("a notice with the panel closed is said", said == "Session over: the other player left", repr(said))

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
