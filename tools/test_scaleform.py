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
def stage_screen(selected=1, names=("???", "The Grid", "Dojo", "Ring of Pride", "Ring of Destiny", "Ring of Power"),
                 first_tile=1000):
    tree = {}
    def node(obj, kids=(), cx=(1, 1, 1, 1), flags=1):
        tree[obj] = {"kids": list(kids), "cx": cx, "flags": flags}
    tiles = []
    for i in range(len(names)):
        tile = first_tile + i * 10
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
scrolled, _, _ = stage_screen(selected=4, first_tile=5000)
skids = lambda o: scrolled.get(o, {}).get("kids", [])
slook = lambda o: (scrolled[o]["cx"], scrolled[o]["flags"]) if o in scrolled else None
check("a grid that scrolled to new tiles is read from its tiles as they are now",
      sf.selected_tile(skids, slook, sf.grid_tiles(skids, 900)) == 5040)
locked_a = [sf.TextItem("???", 1058, 811, WHITE, 5, chosen=True, slot=1000)]
locked_b = [sf.TextItem("???", 1058, 811, WHITE, 5, chosen=True, slot=1010)]
check("moving between two locked stages of the same name is still a move",
      sf.selection_key(locked_a) != sf.selection_key(locked_b) and sf.landed_on(locked_a, locked_b) == ["???"])

# The menu music list, as recorded: each row a background, a highlight bar,
# the holder of the song's name, and left of it a tick box whose holder has two
# bare shapes and, when ticked, the tick.
def music_list(ticks, box_x=184, look_alike=False):
    tree, next_id = {}, [10]
    def node(kids=(), x=0):
        next_id[0] += 1
        tree[next_id[0]] = {"kids": list(kids), "x": x}
        return next_id[0]
    rows, labels = [], []
    for ticked in ticks:
        name = node([node()], x=244)
        if look_alike:   # the Sound Settings tabs: same outline, different contents
            holder = node([node([node()]), node()])
        else:
            holder = node([node(), node()] + ([node([node()])] if ticked else []))
        box = node([node(), holder], x=box_x)
        row = node([node([node(), node([node()])]), node([node(), node()]), name, box])
        rows.append(row)
        labels.append((node(), name, row))
    rows_holder = node(rows)
    kids = lambda o: tree.get(o, {}).get("kids", [])
    x_of = lambda o: tree[o]["x"] if o in tree else None
    return [sf.tick_state(kids, x_of, (label, name, row, rows_holder)) for label, name, row in labels]


check("a ticked and an unticked song read as such", music_list([True, False, True, True]) == [True, False, True, True])
check("rows built alike on another screen are not a checklist",
      music_list([True, False, True], look_alike=True) == [None, None, None])
check("a list of two is not taken for a checklist", music_list([True, False]) == [None, None])
check("a box right of the name is not a tick box", music_list([True, True, True], box_x=400) == [None, None, None])

on_song = [sf.TextItem("Main Menu", 747, 439, GOLD, 9, ticked=True)]
on_unticked = [sf.TextItem("Main Menu", 747, 439, GOLD, 9, ticked=False)]
on_next = [sf.TextItem("Bustling Side Street", 747, 482, GOLD, 9, ticked=False)]
check("moving to a song says its name and whether it is ticked",
      sf.landed_on(on_song, on_next) == ["Bustling Side Street", "Not ticked"], repr(sf.landed_on(on_song, on_next)))
check("ticking the song you are on says only the new state",
      sf.selection_key(on_song) != sf.selection_key(on_unticked)
      and sf.landed_on(on_song, on_unticked) == ["Not ticked"], repr(sf.landed_on(on_song, on_unticked)))

# The Custom tab of the menu music list: rows of the same parts, the highlight
# bar switched on only on the row the cursor is on, and no gold, since the
# songs there cannot be chosen and are drawn in 0.6 grey.
GREY60 = (0.6, 0.6, 0.6, 1.0)


def set_children(mem, obj, kids):
    array = mem.alloc(sf.DISPLAY_CHILD_STRIDE * max(len(kids), 1))
    for i, kid in enumerate(kids):
        mem.put(array + i * sf.DISPLAY_CHILD_STRIDE, "<Q", kid)
    mem.put(obj + sf.DISPLAY_CHILDREN, "<Q", array)
    mem.put(obj + sf.DISPLAY_CHILD_COUNT, "<I", len(kids))


def custom_list(cursor, songs=("Hillside Plaza", "Air Force Base", "Kanzuki Beach", "Ring of Destiny"), gold=None):
    mem = FakeMemory()
    root = display_object(mem, 0, 0, 0, WHITE)
    panel = display_object(mem, root, 300, 250, WHITE)
    title_field = text_field(mem, panel, -75, -1, ["BGM LIST"])
    listing = display_object(mem, panel, 0, 60, WHITE)
    rows, labels = [], []
    for i, song in enumerate(songs):
        row = display_object(mem, listing, 0, 43 * i, WHITE)
        bar = display_object(mem, row, 0, 0, WHITE, flags=1 if i == cursor else 0)
        holder = display_object(mem, row, 244, 0, GOLD if song == gold else GREY60)
        labels.append(text_field(mem, holder, 0, 0, [song]))
        set_children(mem, row, [bar, holder])
        set_children(mem, holder, [mem.ptr(mem.ptr(labels[-1] + sf.DOCVIEW_LISTENER) + sf.LISTENER_OWNER)])
        rows.append(row)
    set_children(mem, listing, rows)
    set_children(mem, panel, [listing])
    set_children(mem, root, [panel])
    return mem, sf.ScaleformText(mem, MODULE), labels


mem_c, reader_c, labels_c = custom_list(cursor=3)
read_c = reader_c.items()
check("the row with its highlight bar on is the selected one, with no gold anywhere",
      [it.text for it in read_c if it.selected] == ["Ring of Destiny"], repr([it.text for it in read_c if it.selected]))
check("a song drawn in 0.6 grey is said to be unavailable, and its tick is not",
      sf.landed_on([], read_c) == ["Ring of Destiny", "Unavailable"], repr(sf.landed_on([], read_c)))
_, _, _ = custom_list(cursor=None)
check("a list with no bar on selects nothing",
      not any(it.selected for it in custom_list(cursor=None)[1].items()))
check("gold in the list is trusted over the bar",
      [it.text for it in custom_list(cursor=1, gold="Kanzuki Beach")[1].items() if it.selected] == ["Kanzuki Beach"])
# Scrolling empties the rows for a moment. The list must not then be taken for
# a grid of pictures and named after the nearest text, the tab above it.
for label in labels_c:
    mem_c.put(label, "<Q", 0)
emptied = reader_c.items()
check("a list whose rows are empty mid-scroll is not named after its tab",
      not any(it.selected for it in emptied), repr([it.text for it in emptied if it.selected]))

# Stage select, as logged: nothing selected, the heading drawn above, the stage
# name drawn twice, and conditions each a label and value in one text.
def stage_select(stage, temperature="77°F", weather="Clear", time_of_day="10:30", conditions=True,
                 panel_hidden=False, character_select=None):
    """`panel_hidden` marks stage select's panel hidden, as on returning from
    character select. `character_select` adds that panel with a name, shown
    or hidden by its own container."""
    mem = FakeMemory()
    movie = display_object(mem, 0, 0, 0, WHITE)
    root = display_object(mem, movie, 0, 0, WHITE, flags=0 if panel_hidden else 1)
    if character_select is not None:
        chara = display_object(mem, movie, 0, 0, WHITE, flags=1 if character_select == "shown" else 0)
        text_field(mem, display_object(mem, chara, 960, 87, WHITE), 0, 0, ["BLUE TEAM"])
    header = display_object(mem, root, 0, 100, WHITE)
    text_field(mem, header, 960, 2, ["STAGE SELECT"])
    text_field(mem, display_object(mem, header, 2, 3, WHITE), 0, 0, ["STAGE SELECT"])
    info = display_object(mem, root, 0, 500, WHITE)
    text_field(mem, display_object(mem, info, 62, 4, WHITE), 0, 0, [stage])
    row = display_object(mem, info, 0, 60, WHITE)
    if conditions:
        text_field(mem, row, 283, 2, [f"Temperature | {temperature}\r", "\r"])
        text_field(mem, row, 38, 11, [f"Weather | {weather}"])
        text_field(mem, row, 774, 11, [f"Time | {time_of_day}"])
    text_field(mem, row, 1150, 11, [stage])
    return sf.ScaleformText(mem, MODULE).items()


on_dojo = stage_select("Dojo")
on_ring = stage_select("Ring of Galaxy", temperature="?", weather="?", time_of_day="?")
check("stage select's stage is selected, not its heading",
      {it.text for it in on_dojo if it.selected} == {"Dojo"}, repr([it.text for it in on_dojo if it.selected]))
check("moving to another stage says only its name",
      sf.landed_on(on_dojo, on_ring) == ["Ring of Galaxy"], repr(sf.landed_on(on_dojo, on_ring)))
check("stage conditions read as words, unknown ones left out",
      sf.stage_details(on_dojo) == ["Temperature 77 degrees F", "Weather Clear", "Time 10:30"]
      and sf.stage_details(on_ring) == [], repr(sf.stage_details(on_dojo)))
check("without conditions it is not stage select",
      not any(it.selected for it in stage_select("Dojo", conditions=False)))
returned = stage_select("Dojo", panel_hidden=True, character_select="hidden")
check("back from character select, a panel still marked hidden is read when nothing else shows",
      {it.text for it in returned if it.selected} == {"Dojo"}
      and "BLUE TEAM" not in {it.text for it in returned}, repr([it.text for it in returned]))
covered = stage_select("Dojo", panel_hidden=True, character_select="shown")
check("but not while character select is really showing",
      [it.text for it in covered] == ["BLUE TEAM"], repr([it.text for it in covered]))

# Character select, as logged: each side's fighter name drawn once and then
# twice in layers, the heading, and a roster of pictures with nothing marking
# the cursor that memory can see. The cursor tags, 1P, 2P and CPU, sit in a
# holder beside the heading's, deeper and with more children, so while one
# tag shows the pair looks like a prompt's buttons with the tag chosen. A tile
# standing out beside the tag would name it too, by the picture grid rule.
CPU_GREY = (0.65, 0.65, 0.65, 1.0)
CPU_TAG = ("CPU", 1025, CPU_GREY)
P1_TAG = ("1P", 1531, (1.0, 1.0, 1.0, 0.4))


def character_select(p1, p2="KEN", heading="CHARACTER SELECT", costume=None, tags=(CPU_TAG,)):
    mem = FakeMemory()
    movie = display_object(mem, 0, 0, 0, WHITE)
    text_field(mem, display_object(mem, movie, 960, 87, WHITE), 0, 0, ["BLUE TEAM"])
    sides = display_object(mem, movie, 0, 0, WHITE)
    for name, x, layered_x in ((p1, 134, 166), (p2, 932, 904)):
        text_field(mem, display_object(mem, sides, x, 590, WHITE), 0, 0, [name])
        layers = display_object(mem, sides, layered_x, 619, WHITE)
        text_field(mem, layers, 0, 0, [name])
        text_field(mem, layers, 0, 0, [name])
    if costume:
        panel = display_object(mem, movie, 100, 455, WHITE)
        text_field(mem, panel, 0, 0, ["Costume"], tint=GOLD)
        text_field(mem, panel, 300, 4, [costume], tint=GOLD)
    overlay = display_object(mem, movie, 0, 0, WHITE)
    title = display_object(mem, overlay, 960, 685, WHITE, children=1)
    text_field(mem, title, 0, 0, [heading])
    cursors = display_object(mem, overlay, 0, 0, WHITE)
    roster = display_object(mem, cursors, 1400, 700, WHITE)
    tiles = []
    for i in range(6):
        tile = display_object(mem, roster, 70 * i, 0, WHITE)
        picture = display_object(mem, tile, 0, 0, WHITE if i == 2 else (0.4, 0.4, 0.4, 1.0))
        set_children(mem, tile, [picture, display_object(mem, tile, 0, 0, WHITE)])
        tiles.append(tile)
    set_children(mem, roster, tiles)
    held = [roster]
    for text, x, tint in tags:
        tag = display_object(mem, cursors, x, 843, WHITE)
        text_field(mem, tag, 0, 0, [text], tint=tint)
        held.append(tag)
    set_children(mem, cursors, held)
    set_children(mem, overlay, [title, cursors])
    set_children(mem, movie, [overlay])
    return sf.ScaleformText(mem, MODULE).items()


unrecognised = character_select("ZEKU", heading="TEAM SELECT")
check("the fake's CPU tag does get taken for a selection on a screen not recognised",
      [it.text for it in unrecognised if it.selected] == ["CPU"],
      repr([it.text for it in unrecognised if it.selected]))
on_zeku, on_kolin = character_select("ZEKU"), character_select("KOLIN", tags=(P1_TAG, CPU_TAG))
check("on character select the fighters' names are selected, not the CPU tag",
      {it.text for it in on_zeku if it.selected} == {"ZEKU", "KEN"},
      repr([it.text for it in on_zeku if it.selected]))
check("arriving says both fighters once each", sf.landed_on([], on_zeku) == ["ZEKU", "KEN"],
      repr(sf.landed_on([], on_zeku)))
check("moving through the roster says the fighter moved to",
      sf.landed_on(on_zeku, on_kolin) == ["KOLIN"], repr(sf.landed_on(on_zeku, on_kolin)))
blinked = character_select("KOLIN")
check("player one's tag blinking off says nothing",
      sf.selection_key(on_kolin) == sf.selection_key(blinked) and sf.landed_on(on_kolin, blinked) == [],
      repr(sf.landed_on(on_kolin, blinked)))
two_players = character_select("ZEKU", "CAMMY", tags=(("2P", 1181, (1.0, 1.0, 1.0, 0.4)),))
check("in a two player match the other side's move says only its fighter",
      sf.landed_on(on_zeku, two_players) == ["CAMMY"], repr(sf.landed_on(on_zeku, two_players)))
picking_cpu = character_select("ORO", "CAMMY", tags=(("CPU", 1095, WHITE),))
check("picking the CPU's fighter says the fighter without the tag",
      sf.landed_on(character_select("ORO", tags=(("CPU", 1025, WHITE),)), picking_cpu) == ["CAMMY"],
      repr(sf.landed_on(character_select("ORO", tags=(("CPU", 1025, WHITE),)), picking_cpu)))
mirror = character_select("KEN")
check("moving onto the fighter the other side has is still said",
      sf.selection_key(on_zeku) != sf.selection_key(mirror) and sf.landed_on(on_zeku, mirror) == ["KEN"],
      repr(sf.landed_on(on_zeku, mirror)))
dressing = character_select("ZEKU", costume="Kenji")
check("the costume panel after a pick still reads from its gold",
      sf.landed_on(on_zeku, dressing) == ["Costume", "Kenji"], repr(sf.landed_on(on_zeku, dressing)))

# The result screen after a Versus match, laid out as read from the game: a
# column per side holding the player, the outcome in three layers, and "Wins"
# and "Win Streak" each beside its number; below both, the two percentages,
# the fighters and "Win Ratio". Arriving, the CPU's column showed its name and
# one fading layer of LOSE, which the prompt rule took for a chosen button.
FADED = (0.51, 0.50, 0.60, 1.0)
MENU_ENTRIES = ("Play Again", "Return to Character/Stage Select", "Return to Battle Settings", "Return to Main Menu")


def result_screen(arriving=False, left=("PLAYER 1", "WIN", 1, 1), right=("CPU", "LOSE", 0, 0),
                  ratio=(("0.00%", 632), ("100.00%", 772)), menu=None, heading="RESULT"):
    mem = FakeMemory()
    movie = display_object(mem, 0, 0, 0, WHITE)
    screen = display_object(mem, display_object(mem, movie, 0, 0, WHITE), 0, 0, WHITE)
    text_field(mem, display_object(mem, screen, 68, 7, WHITE), 0, 0, [heading])
    for (player, outcome, wins, streak), x in ((left, 285), (right, 1646)):
        if arriving and x < 960:
            continue
        column = display_object(mem, screen, 0, 0, WHITE)
        text_field(mem, column, x, 156, [player])
        layers = display_object(mem, column, x + 10, 231, WHITE, children=3)
        if arriving:
            text_field(mem, layers, 0, 0, [outcome], tint=FADED)
            continue
        text_field(mem, layers, 0, 0, [outcome])
        text_field(mem, layers, 0, 0, [outcome])
        text_field(mem, layers, 0, 0, [outcome], tint=(1, 1, 1, 0))
        for label, value, y in (("Wins", wins, 395), ("Win Streak", streak, 444)):
            row = display_object(mem, column, x - 160, y, WHITE)
            text_field(mem, row, 0, 0, [label + "\r", "\r"])
            text_field(mem, row, 368, 9, [str(value)])
    if not arriving:
        bottom = display_object(mem, screen, 0, 0, WHITE)
        for text, x in ratio:
            text_field(mem, bottom, x, 914, [text])
        text_field(mem, bottom, 537, 953, ["AKIRA"])
        text_field(mem, bottom, 1383, 953, ["KARIN"])
        text_field(mem, display_object(mem, display_object(mem, bottom, 0, 0, WHITE), 0, 0, WHITE),
                   878, 805, ["Win Ratio"])
    if menu:
        menu_movie = display_object(mem, 0, 0, 0, WHITE)
        text_field(mem, menu_movie, 460, 245, ["Results Menu"])
        for i, entry in enumerate(MENU_ENTRIES):
            holder = display_object(mem, menu_movie, 460, 306 + 42 * i, GOLD if entry == menu else GREY)
            text_field(mem, holder, 0, 0, [entry])
    return sf.ScaleformText(mem, MODULE).items()


won = result_screen()
check("the result screen sums up the match, winner first",
      sf.result_summary(won) == "PLAYER 1 wins. Wins 1 to 0. Win streak 1 to 0. Win ratio 100 to 0 percent.",
      repr(sf.result_summary(won)))
lost = result_screen(left=("PLAYER 1", "LOSE", 1, 0), right=("CPU", "WIN", 2, 1),
                     ratio=(("66.67%", 632), ("33.33%", 772)))
check("a percentage goes to the side whose wins it agrees with, wherever it is drawn",
      sf.result_summary(lost) == "CPU wins. Wins 2 to 1. Win streak 1 to 0. Win ratio 66.67 to 33.33 percent.",
      repr(sf.result_summary(lost)))
puzzling = result_screen(ratio=(("40.00%", 632), ("60.00%", 772)))
check("a ratio that agrees with neither side is left unsaid",
      sf.result_summary(puzzling) == "PLAYER 1 wins. Wins 1 to 0. Win streak 1 to 0.", repr(sf.result_summary(puzzling)))
arriving = result_screen(arriving=True)
check("the fake's fading LOSE does get taken for a selection on a screen not recognised",
      [it.text for it in result_screen(arriving=True, heading="RESULTS?") if it.selected] == ["LOSE"],
      repr([it.text for it in result_screen(arriving=True, heading="RESULTS?") if it.selected]))
check("while the result screen arrives, nothing on it is selected and there is no summary yet",
      not any(it.selected for it in arriving) and sf.result_summary(arriving) is None,
      repr(([it.text for it in arriving if it.selected], sf.result_summary(arriving))))
check("the result summary is only for the result screen", sf.result_summary(on_zeku) is None
      and sf.result_summary(on_dojo) is None)

# A screen being torn down: an object whose child list points at garbage that
# does not name it as parent, and claims a great many entries.
gmem = FakeMemory(size=0x40000 + 0x1000)
groot = display_object(gmem, 0, 0, 0, WHITE)
real = display_object(gmem, groot, 0, 0, WHITE)
stray = display_object(gmem, 0, 0, 0, WHITE)          # parent is not groot
junk = gmem.alloc(16 * 2000)
for i in range(2000):
    gmem.put(junk + i * 16, "<Q", stray if i % 2 else real)
gmem.put(groot + sf.DISPLAY_CHILDREN, "<Q", junk)
gmem.put(groot + sf.DISPLAY_CHILD_COUNT, "<I", 2000)
greader = sf.ScaleformText(gmem, MODULE)
check("children that do not name their parent are dropped",
      set(greader.children(groot)) == {real}, repr(len(greader.children(groot))))
import time as _time  # noqa: E402
endless = lambda obj: [obj * 2 + 8, obj * 2 + 16]     # a tree that never ends
started = _time.monotonic()
sf.find_grids(endless, {16}, limit=10**9, seconds=0.05)
check("the grid walk stops at its time limit", _time.monotonic() - started < 0.5)

# The narrator the mod and the watch mode share, fed readings as they arrive.
from sfv_access import memory_narration as mn  # noqa: E402


def narrate(readings):
    """Run (time, items) readings through a narrator; return what it said, with times."""
    narrator = mn.Narrator()
    out = []
    for now, items in readings:
        said = narrator.step(items, now)
        if said:
            out.append((now, said))
    return out


question = "Are you sure you want to close the application?"
gap = [it for it in on_yes if it.text.strip() not in ("Yes", "No")]
said = narrate([
    (0.0, menu_only), (0.3, menu_only),        # the menu behind, settling on its description
    (0.4, question_first), (0.5, on_no),       # the question shows a beat before the buttons
    (0.6, gap), (0.9, gap),                    # between answers, longer than the settle time
    (1.0, on_yes), (1.1, gap), (1.15, on_no), (1.2, on_no),
])
check("a prompt reads its question once, then each answer as it is reached",
      [s for _, s in said] == ["The application will close.", f"{question} No", "Yes", "No"], repr(said))

arcade_mid = main_menu("Fighting Chance", "The application will close.")   # description first
said = narrate([(0.0, on_arcade), (1.0, arcade_mid), (1.05, on_exit), (1.25, on_exit), (1.3, on_exit)])
check("an icon waits for its name to arrive, then says it once",
      [s for _, s in said] == ["ARCADE", "EXIT"], repr(said))
check("the name is not said before the settle time",
      all(now >= 1.0 + mn.SETTLE for now, s in said if s == "EXIT"), repr(said))
check("idling on one entry says nothing more", narrate([(0, on_story), (1, on_story), (2, on_story)])
      == [(0, "STORY")])
said = narrate([(0.0, on_zeku), (0.1, on_kolin), (0.2, blinked), (0.3, on_kolin), (0.6, blinked),
                (0.7, on_zeku), (0.8, mirror)])
check("moving through the roster says each fighter as it is reached, and the tag's blinking nothing",
      [s for _, s in said] == ["ZEKU. KEN", "KOLIN", "ZEKU", "KEN"], repr(said))
said = narrate([(0.0, arriving), (0.3, arriving), (0.5, won), (0.8, won), (1.0, result_screen(menu="Play Again")),
                (1.3, result_screen(menu=MENU_ENTRIES[1])), (1.6, result_screen(menu=MENU_ENTRIES[1]))])
check("the result screen says its summary once when complete, then the Results Menu as it moves",
      [s for _, s in said] == ["PLAYER 1 wins. Wins 1 to 0. Win streak 1 to 0. Win ratio 100 to 0 percent.",
                               "Play Again", "Return to Character/Stage Select"], repr(said))
check("phrases join without doubled punctuation",
      mn.phrase(["Are you sure?", "No", "Costume.", "Kenji"]) == "Are you sure? No. Costume. Kenji")
# A session whose block list has missed the text's block: quick reads find
# nothing, so after a while a full search must find it, speak from it and say
# why in the log. The log is a scratch file; tests never write to real data.
import tempfile  # noqa: E402

scratch_log = Path(tempfile.gettempdir()) / "sfv-access-test-scaleform-log.txt"
scratch_log.unlink(missing_ok=True)
mn.LOG = scratch_log
assert mn.LOG != ROOT / "snapshots" / "scaleform-log.txt"
smem = FakeMemory()
sroot = display_object(smem, 0, 0, 0, WHITE)
text_field(smem, display_object(smem, sroot, 100, 100, WHITE), 0, 0, ["Dojo"])
session = mn.Session(log_screens=False)
session.reader = sf.ScaleformText(smem, MODULE)
session.reader._scaleform_pages = []                     # missed the block
session.reader.pages_refreshed_at = _time.monotonic() + 3600   # but not old
session._next_alive_check, session._seen_text = float("inf"), True
first = session.read(now=0.0)
soon = session.read(now=1.0)
later = session.read(now=2.5)
check("a quick read that misses text is checked by a full search, and heals",
      first == [] and soon == [] and [it.text for it in later] == ["Dojo"]
      and [it.text for it in session.read(now=2.6)] == ["Dojo"], repr((first, soon, later)))
check("and the log says why", "blocks it lacks" in scratch_log.read_text(encoding="utf-8"))
scratch_log.unlink(missing_ok=True)

check("the read key names a selected song with its tick",
      mn.selection_phrase(on_next) == "Bustling Side Street. Not ticked")

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
