"""Check the Scaleform reader against a small fake of the game's memory.

The fake lays out text fields, their parents and render nodes exactly as they
sit in the real game, so the offsets, the walk up to the root and the colour
arithmetic are all exercised without the game running. A failure here is a
bug in the reader rather than a change in the game.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access import scaleform as sf  # noqa: E402
from sfv_access.memory import Region  # noqa: E402

ok = True


def check(label, condition, detail=""):
    global ok
    if condition:
        print(f"PASS  {label}{(': ' + detail) if detail else ''}")
    else:
        ok = False
        print(f"FAIL  {label}{(': ' + detail) if detail else ''}")


MODULE = 0x7FF600000000
HEAP = 0x10000000
GREY = (0.27, 0.27, 0.27, 1.0)
GOLD = (1.0, 0.89, 0.549, 1.0)
WHITE = (1.0, 1.0, 1.0, 1.0)


class FakeMemory:
    """One read-write heap page, with a bump allocator for laying out objects."""

    def __init__(self, size=0x11000):   # shaped like one of Scaleform's blocks
        self.buf = bytearray(size)
        self.top = 0x100

    def alloc(self, size):
        at = HEAP + self.top
        self.top += (size + 15) // 16 * 16
        return at

    def put(self, addr, fmt, *values):
        struct.pack_into(fmt, self.buf, addr - HEAP, *values)

    def read(self, address, size):
        off = address - HEAP
        if address <= 0 or off < 0 or off + size > len(self.buf):
            return None
        return bytes(self.buf[off : off + size])

    def ptr(self, a):
        b = self.read(a, 8)
        return struct.unpack("<Q", b)[0] if b else None

    u64 = ptr

    def u32(self, a):
        b = self.read(a, 4)
        return struct.unpack("<I", b)[0] if b else None

    def regions(self, max_size=1 << 31):
        return [Region(HEAP, len(self.buf), 0x04)]


NODE_FLAG_WORD = sf.NODE_FLAGS


def display_object(mem, parent, x, y, tint, flags=1, children=0):
    """A display object with a render node placing it at (x, y) pixels in its parent."""
    obj = mem.alloc(0x360)
    entry = mem.alloc(0x20)
    data = mem.alloc(0x80)
    mem.put(obj + sf.DISPLAY_PARENT, "<Q", parent)
    mem.put(obj + sf.DISPLAY_RENDER_NODE, "<Q", entry)
    mem.put(obj + sf.DISPLAY_CHILD_COUNT, "<I", children)
    mem.put(entry + sf.RENDER_NODE_DATA, "<Q", data)
    mem.put(data + NODE_FLAG_WORD, "<H", flags)
    mem.put(data + sf.NODE_MATRIX, "<8f", 1, 0, 0, x * 20, 0, 1, 0, y * 20)
    mem.put(data + sf.NODE_CXFORM, "<8f", *tint, 0, 0, 0, 0)
    return obj


def text_field(mem, parent, x, y, paragraphs, tint=WHITE, flags=1, separate=False, box=(2000, 400)):
    """A text field with its DocView and text.

    The listener lives inside the field on the main menu, and in its own
    allocation elsewhere, the case the first reader missed. `separate` puts it
    after a gap of unrelated memory.
    """
    field = display_object(mem, parent, x, y, tint, flags)
    if separate:
        mem.alloc(0x400)
        listener = mem.alloc(0x200) + 0x130
    else:
        listener = field + 0x2F0
    mem.put(listener + sf.LISTENER_OWNER, "<Q", field)
    docview = mem.alloc(0x100)
    styled = mem.alloc(0x40)
    array = mem.alloc(8 * max(len(paragraphs), 1))
    mem.put(docview, "<Q", MODULE + sf.DOCVIEW_VTABLE)
    mem.put(docview + sf.DOCVIEW_TEXT, "<Q", styled)
    mem.put(docview + sf.DOCVIEW_LISTENER, "<Q", listener)
    mem.put(docview + sf.DOCVIEW_SIZE, "<2f", *box)
    mem.put(styled, "<Q", MODULE + sf.STYLED_TEXT_VTABLE)
    mem.put(styled + sf.TEXT_PARAGRAPHS, "<Q", array)
    mem.put(styled + sf.TEXT_PARAGRAPH_COUNT, "<Q", len(paragraphs))
    for i, text in enumerate(paragraphs):
        encoded = (text + "\0").encode("utf-16-le")
        chars = mem.alloc(len(encoded))
        mem.buf[chars - HEAP : chars - HEAP + len(encoded)] = encoded
        para = mem.alloc(0x50)
        mem.put(para, "<QQQ", chars, len(text) + 1, len(text) + 1)
        mem.put(array + i * 8, "<Q", para)
    return docview


mem = FakeMemory()
root = display_object(mem, 0, 0, 0, WHITE)
menu = display_object(mem, root, 400, 200, WHITE)
arcade_item = display_object(mem, menu, 0, 0, GREY)
training_item = display_object(mem, menu, 0, 480, GOLD)
text_field(mem, arcade_item, 42, 19, ["ARCADE"])
text_field(mem, training_item, 42, 19, ["TRAINING"])
text_field(mem, root, 110, 992, ["Enjoy battle without worrying about a time limit.\r"], separate=True)
text_field(mem, root, 100, 100, ["Two lines\r", "of text"])
# The Exit prompt's question has its own node's visible bit clear while on
# screen; a date line that never shows is hidden by its parent's.
text_field(mem, menu, 0, 700, ["Flag word clear"], flags=0)
text_field(mem, display_object(mem, root, 0, 0, WHITE, flags=0), 0, 0, ["Parent switched off"])
text_field(mem, root, -1920, 0, ["Off to the side"])
text_field(mem, root, 300, 300, ["Faded out"], tint=(1, 1, 1, 0))
text_field(mem, root, 500, 500, ["   "])
orphan = text_field(mem, 0, 10, 10, ["Detached"])

# A DocView left behind by a closed screen: its field no longer has a node.
stale = text_field(mem, root, 5, 5, ["Close"])
listener = mem.ptr(stale + sf.DOCVIEW_LISTENER)
mem.put(mem.ptr(listener + sf.LISTENER_OWNER) + sf.DISPLAY_RENDER_NODE, "<Q", 0)

reader = sf.ScaleformText(mem, MODULE)

found = reader.docviews()
check("sweep finds every DocView", len(found) == 11, f"{len(found)} found")

shown = reader.items()
texts = [it.text for it in shown]
check(
    "shown fields in reading order",
    texts == ["Two lines\nof text", "ARCADE", "TRAINING", "Flag word clear",
              "Enjoy battle without worrying about a time limit."],
    repr(texts),
)

by_text = {it.text: it for it in shown}
training = by_text.get("TRAINING")
arcade = by_text.get("ARCADE")
check("position composes up the parents", training is not None and (training.x, training.y) == (442, 699),
      f"{(training.x, training.y) if training else None}")
check("tint multiplies up the parents", training is not None and training.highlighted,
      f"{training.tint if training else None}")
check("an unselected entry is not highlighted", arcade is not None and not arcade.highlighted,
      f"{arcade.tint if arcade else None}")
check("paragraph terminators stripped", "Two lines\nof text" in by_text)

everything = {it.text: it for it in reader.items(everything=True)}
check("a field's own clear visible bit does not hide it", "Flag word clear" in by_text)
check("a parent's clear visible bit does", "Parent switched off" in everything
      and not everything["Parent switched off"].shown)
check("off the stage is not shown", "Off to the side" in everything and not everything["Off to the side"].shown)
check("fully transparent is not shown", "Faded out" in everything and not everything["Faded out"].shown)
check("blank text is not shown", "   " in everything and not everything["   "].shown)
check("detached field is not shown", "Detached" in everything and not everything["Detached"].shown)
check("stale DocView is kept only when asked", "Close" in everything and everything["Close"].depth == 0)

# A DocView whose text object has the wrong vtable is not a text field at all.
mem.put(mem.ptr(stale + sf.DOCVIEW_TEXT), "<Q", MODULE + 0x1234)
check("wrong StyledText vtable is refused", reader.field_text(stale) is None)

# What a move lands on. These are the main menu as the watch mode logged it.
def item(text, x, y, tint=WHITE):
    return sf.TextItem(text, x, y, tint, 7)


def main_menu(banner, description, lit=None):
    entries = [("ARCADE", 442, 219), ("STORY", 442, 339), ("VERSUS", 442, 459)]
    out = [item("Dengster", 1379, 53), item(banner, 799, 452), item(description, 110, 992)]
    out += [item(t, x, y, GOLD if t == lit else GREY) for t, x, y in entries]
    return out


on_arcade = main_menu("Fighting Chance", "A single player mode.", lit="ARCADE")
on_story = main_menu("Fighting Chance", "Play through the storylines.", lit="STORY")
on_exit = main_menu("EXIT", "The application will close.")
on_login = main_menu("LOGIN", "Log into server.")
advert_rotated = main_menu("Nostalgia Collection", "The application will close.")
on_info = main_menu("Nostalgia Collection", "Go to the purchase screen.")

check("gold text is what a move lands on", sf.landed_on(on_arcade, on_story) == ["STORY"],
      repr(sf.landed_on(on_arcade, on_story)))
check("an icon is named by the banner", sf.landed_on(on_arcade, on_exit) == ["EXIT"],
      repr(sf.landed_on(on_arcade, on_exit)))
check("icon to icon", sf.landed_on(on_exit, on_login) == ["LOGIN"], repr(sf.landed_on(on_exit, on_login)))
check("nothing else changed, so the description", sf.landed_on(advert_rotated, on_info) == ["Go to the purchase screen."],
      repr(sf.landed_on(advert_rotated, on_info)))
check("a whole new screen falls back to the description",
      sf.landed_on([], on_exit) == ["The application will close."], repr(sf.landed_on([], on_exit)))
check("a rotating advert is not a move", sf.selection_key(on_exit) == sf.selection_key(advert_rotated))
check("moving along the icon row is a move", sf.selection_key(on_exit) != sf.selection_key(on_login))
check("the footer is found by where it sits", (sf.footer(on_exit) or item("", 0, 0)).text == "The application will close.")
label_gone = [it for it in on_exit if it.text != "EXIT"]
check("labels vanishing mid-move say nothing", sf.landed_on(on_exit, label_gone) == [],
      repr(sf.landed_on(on_exit, label_gone)))


# The Exit prompt, laid out as recorded: a panel holding the question and a row
# of two buttons. The selected button has four more children, its outline and
# fill, and its label sits one level further down inside them.
def exit_prompt(selected, question="Are you sure you want to close the application?",
                behind=("The application will close.", WHITE)):
    """The prompt over a screen. `selected` of None is the moment before either
    button has taken the selection, with the question already showing."""
    mem = FakeMemory()
    root = display_object(mem, 0, 0, 0, WHITE)
    text_field(mem, display_object(mem, root, 110, 992, behind[1]), 0, 0, [behind[0]])
    panel = display_object(mem, root, 0, 340, WHITE)
    text_field(mem, panel, 520, 100, [question], tint=(0.62, 0.62, 0.62, 0.5), flags=0, separate=True)
    text_field(mem, panel, 960, 274, ["wwwwwwwwwwwwwwwwwww"], flags=0)
    row = display_object(mem, panel, 960, 350, WHITE)
    for label, x in (("Yes ", -233), ("No", 233)):
        if label.strip() == selected:
            button = display_object(mem, row, x, 0, WHITE, children=6)
            layer = display_object(mem, button, 201, -19, WHITE)
            text_field(mem, layer, 0, 0, [label], tint=(1, 1, 1, 0.15), separate=True)
        else:
            button = display_object(mem, row, x, 0, WHITE, children=2)
            text_field(mem, button, 0, 0, [label], separate=True)
    return sf.ScaleformText(mem, MODULE).items()


menu_only = [it for it in exit_prompt("No") if it.text == "The application will close."]
question_first = exit_prompt(None)
on_no = exit_prompt("No")
on_yes = exit_prompt("Yes")
chosen = [it.text.strip() for it in on_no if it.chosen]
check("the button with the outline is the selected one", chosen == ["No"], repr(chosen))
check("and it follows the selection", [it.text.strip() for it in on_yes if it.chosen] == ["Yes"])
check("the question is shown though its flag word is clear",
      any("Are you sure" in it.text for it in on_no))
check("opening the prompt reads the question, then the answer",
      sf.landed_on(menu_only, on_no) == ["Are you sure you want to close the application?", "No"],
      repr(sf.landed_on(menu_only, on_no)))
check("moving to the other answer reads only that answer", sf.landed_on(on_no, on_yes) == ["Yes "],
      repr(sf.landed_on(on_no, on_yes)))
check("a dialog move is a move", sf.selection_key(on_no) != sf.selection_key(on_yes))
check("the prompt's placeholder is never shown", not any("wwww" in it.text for it in on_no))
check("the question is read even if it showed before the buttons",
      sf.landed_on(question_first, on_no) == ["Are you sure you want to close the application?", "No"],
      repr(sf.landed_on(question_first, on_no)))
closed = [it for it in on_no if it.text == "The application will close."] + [item("  Fighter Profile", 1310, 948)]
check("closing the prompt says nothing", sf.landed_on(on_no, closed) == [], repr(sf.landed_on(on_no, closed)))

# From the Training pause menu the prompt opens over a gold entry that stays gold.
training_question = "Exit current mode and return to Main Menu. Are you sure?"
t_open = exit_prompt(None, training_question, ("Go to Main Menu", GOLD))
t_yes = exit_prompt("Yes", training_question, ("Go to Main Menu", GOLD))
t_no = exit_prompt("No", training_question, ("Go to Main Menu", GOLD))
check("a prompt over a gold menu still finds its selection",
      [it.text.strip() for it in t_yes if it.chosen] == ["Yes"])
check("and reads its question, not the gold entry behind it",
      sf.landed_on(t_open, t_yes) == [training_question, "Yes "], repr(sf.landed_on(t_open, t_yes)))
check("moving in it reads the answer", sf.landed_on(t_yes, t_no) == ["No"], repr(sf.landed_on(t_yes, t_no)))
gap = [it for it in t_yes if not it.chosen and it.text.strip() not in ("Yes", "No")]
groups = frozenset(it.group for it in t_yes if it.chosen)
check("a read between the answers does not reopen the prompt",
      sf.landed_on(gap, t_no, groups) == ["No"], repr(sf.landed_on(gap, t_no, groups)))
check("nor does anything get said for that read", sf.landed_on(t_yes, gap, groups) == [],
      repr(sf.landed_on(t_yes, gap, groups)))

# The Favorite Character grid: every name dimmed to 0.75 but the one you are on.
DIM = (0.75, 0.75, 0.75, 1.0)
ROSTER = ["RYU", "KEN", "CHUN-LI", "CAMMY", "NASH", "M. BISON", "VEGA", "BIRDIE"]


def character_grid(on, heading=None, gold=None):
    mem = FakeMemory()
    root = display_object(mem, 0, 0, 0, WHITE)
    grid = display_object(mem, root, 1000, 300, WHITE)
    if heading:
        text_field(mem, display_object(mem, grid, 0, -60, WHITE), 0, 0, [heading], box=(9000, 800))
    for i, name in enumerate(ROSTER):
        tint = GOLD if name == gold else (WHITE if name == on else DIM)
        tile = display_object(mem, grid, 164 * (i % 4), 52 * (i // 4), WHITE)
        text_field(mem, tile, 37, 26, [name], tint=tint)
    text_field(mem, root, 1041, 857, [on or "RYU"], box=(6000, 900))
    return sf.ScaleformText(mem, MODULE).items()


on_ryu, on_ken = character_grid("RYU"), character_grid("KEN")
check("the brighter tile in a grid is the selected one",
      [it.text for it in on_ken if it.chosen] == ["KEN"], repr([it.text for it in on_ken if it.chosen]))
check("moving in the grid says the name once, not the label that repeats it",
      sf.landed_on(on_ryu, on_ken) == ["KEN"], repr(sf.landed_on(on_ryu, on_ken)))
check("a heading brighter than dim entries is not a selection",
      not any(it.chosen for it in character_grid(None, heading="Favorite Character")))
check("gold in the group leaves it to the gold",
      [it.text for it in character_grid("RYU", gold="VEGA") if it.selected] == ["VEGA"])

# The Favorite Stage grid, as recorded: tiles of seven parts, the selected one
# with its outline switched on and its picture undimmed, and a label five
# levels away naming the stage, where the category tab is seven.
def stage_screen(selected=1, names=("???", "The Grid", "Dojo", "Ring of Pride", "Ring of Destiny", "Ring of Power")):
    tree = {}
    def node(obj, kids=(), cx=(1, 1, 1, 1), flags=1):
        tree[obj] = {"kids": list(kids), "cx": cx, "flags": flags}
    tiles = []
    for i in range(len(names)):
        tile = 1000 + i * 10
        parts = [tile + p for p in range(1, 8)]
        on = i == selected
        node(parts[0], flags=1 if on else 0)                                      # outline
        node(parts[2], cx=(1, 1, 1, 1) if on else (0.4, 0.4, 0.4, 1))             # picture
        for p in (parts[1], *parts[3:]):
            node(p)
        node(tile, parts)
        tiles.append(tile)
    node(998)
    node(999, [998])                   # the scroll bar, one part, not a tile
    node(900, [999] + tiles)           # the grid
    node(800, [900]); node(700, [800, 610]); node(610, [611]); node(611, [612]); node(612, [613])
    node(600, [700, 500]); node(500, [501]); node(501, [502]); node(502, [503])
    node(1, [600])                     # the movie root
    parent = {k: p for p, v in tree.items() for k in v["kids"]}
    def chain(leaf):
        out = [leaf]
        while out[-1] in parent:
            out.append(parent[out[-1]])
        return tuple(out)
    label = sf.TextItem(names[selected or 0], 1058, 811, WHITE, 0, chain=chain(613))
    tab = sf.TextItem("ALL", 1196, 237, WHITE, 0, chain=chain(503))
    for it in (label, tab):
        it.depth = len(it.chain)
    up = [900]
    while up[-1] in parent:
        up.append(parent[up[-1]])
    return tree, [label, tab], up


tree, texts, up = stage_screen(selected=3)
kids = lambda o: tree.get(o, {}).get("kids", [])
look = lambda o: (tree[o]["cx"], tree[o]["flags"]) if o in tree else None
grids = sf.find_grids(kids, {1})
check("a grid of picture tiles is found, and the one-part scroll bar is not a tile",
      list(grids) == [900] and len(grids[900]) == 6, repr({k: len(v) for k, v in grids.items()}))
check("the tile with its outline on and picture undimmed is the selected one",
      sf.selected_tile(kids, look, grids[900]) == 1030)
check("the stage is named by the nearest label, not the category tab",
      getattr(sf.name_for_grid(up, texts), "text", None) == "Ring of Pride")
tree2, _, _ = stage_screen(selected=None)
check("a grid with nothing standing out selects nothing",
      sf.selected_tile(lambda o: tree2.get(o, {}).get("kids", []),
                       lambda o: (tree2[o]["cx"], tree2[o]["flags"]) if o in tree2 else None, grids[900]) is None)
locked_a = [sf.TextItem("???", 1058, 811, WHITE, 5, chosen=True, slot=1000)]
locked_b = [sf.TextItem("???", 1058, 811, WHITE, 5, chosen=True, slot=1010)]
check("moving between two locked stages of the same name is still a move",
      sf.selection_key(locked_a) != sf.selection_key(locked_b) and sf.landed_on(locked_a, locked_b) == ["???"])

# Quick reads sweep only blocks shaped like Scaleform's own.
qmem = FakeMemory()
qroot = display_object(qmem, 0, 0, 0, WHITE)
text_field(qmem, display_object(qmem, qroot, 100, 100, WHITE), 0, 0, ["Found quickly"])
qreader = sf.ScaleformText(qmem, MODULE)
check("a quick read finds text in a Scaleform block, walking first if it must",
      [it.text for it in qreader.items(quick=True)] == ["Found quickly"])
other = FakeMemory(size=0x10000)
oroot = display_object(other, 0, 0, 0, WHITE)
text_field(other, display_object(other, oroot, 100, 100, WHITE), 0, 0, ["In an engine page"])
oreader = sf.ScaleformText(other, MODULE)
check("a quick read skips pages of another shape, a full read does not",
      oreader.items(quick=True) == [] and [it.text for it in oreader.items()] == ["In an engine page"])

layered = [item("VERSION SELECT", 960, 524), item("VERSION SELECT", 232, 613), item("VERSION SELECT", 232, 613)]
check("text drawn in layers is said once", sf.landed_on([], layered) == ["VERSION SELECT"],
      repr(sf.landed_on([], layered)))
row_kenji = [item("Favorite Character", 100, 200, GOLD), item("Costume", 100, 300, GOLD), item("Kenji", 400, 300, GOLD)]
row_suit = [item("Favorite Character", 100, 200, GOLD), item("Costume", 100, 300, GOLD), item("Track Suit", 400, 300, GOLD)]
check("changing a value says only the value", sf.landed_on(row_kenji, row_suit) == ["Track Suit"],
      repr(sf.landed_on(row_kenji, row_suit)))
check("W placeholders are recognised", sf.is_placeholder("WWWWWWWWyWWWWWWWW")
      and sf.is_placeholder("WWWWWWWWWWWWWWWW\n") and not sf.is_placeholder("WWE NETWORK")
      and not sf.is_placeholder("Wow"))

# The choice rule has to stay off things that merely look like two buttons.
mem = FakeMemory()
root = display_object(mem, 0, 0, 0, WHITE)
banner = display_object(mem, root, 799, 191, WHITE)
date = display_object(mem, banner, 0, 0, WHITE, children=3)
layer = display_object(mem, date, 0, 0, WHITE)
text_field(mem, layer, 0, 0, ["Aug 31, 2026 - Sep 30, 2026"])
title = display_object(mem, banner, 0, 261, WHITE, children=2)
text_field(mem, title, 0, 0, ["UPGRADE KIT AVAILABLE NOW"])
check("long labels are never a choice", not any(it.chosen for it in sf.ScaleformText(mem, MODULE).items()))

mem = FakeMemory()
root = display_object(mem, 0, 0, 0, WHITE)
pair = display_object(mem, root, 500, 500, WHITE)
text_field(mem, display_object(mem, pair, 0, 0, WHITE, children=4), 0, 0, ["ON"])
text_field(mem, display_object(mem, pair, 200, 0, WHITE, children=2), 0, 0, ["OFF"])
check("more layers without deeper nesting is not a choice",
      not any(it.chosen for it in sf.ScaleformText(mem, MODULE).items()))

mem = FakeMemory()
root = display_object(mem, 0, 0, 0, WHITE)
menu = display_object(mem, root, 0, 0, WHITE)
text_field(mem, display_object(mem, menu, 400, 200, GOLD), 0, 0, ["ARCADE"])
row = display_object(mem, root, 900, 600, WHITE)
button = display_object(mem, row, 0, 0, WHITE, children=6)
text_field(mem, display_object(mem, button, 0, 0, WHITE), 0, 0, ["Yes"])
text_field(mem, display_object(mem, row, 200, 0, WHITE, children=2), 0, 0, ["No"])
check("gold elsewhere does not stop a choice being found",
      [it.text for it in sf.ScaleformText(mem, MODULE).items() if it.chosen] == ["Yes"])

print()
print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
