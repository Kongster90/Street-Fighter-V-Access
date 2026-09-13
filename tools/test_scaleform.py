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

    def __init__(self, size=0x10000):
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

    def regions(self, max_size=1 << 31):
        return [Region(HEAP, len(self.buf), 0x04)]


def display_object(mem, parent, x, y, tint, visible=True):
    """A display object with a render node placing it at (x, y) pixels in its parent."""
    obj = mem.alloc(0x360)
    entry = mem.alloc(0x20)
    data = mem.alloc(0x80)
    mem.put(obj + sf.DISPLAY_PARENT, "<Q", parent)
    mem.put(obj + sf.DISPLAY_RENDER_NODE, "<Q", entry)
    mem.put(entry + sf.RENDER_NODE_DATA, "<Q", data)
    mem.put(data + sf.NODE_FLAGS, "<H", 1 if visible else 0)
    mem.put(data + sf.NODE_MATRIX, "<8f", 1, 0, 0, x * 20, 0, 1, 0, y * 20)
    mem.put(data + sf.NODE_CXFORM, "<8f", *tint, 0, 0, 0, 0)
    return obj


def text_field(mem, parent, x, y, paragraphs, tint=WHITE, visible=True):
    field = display_object(mem, parent, x, y, tint, visible)
    docview = mem.alloc(0x100)
    styled = mem.alloc(0x40)
    array = mem.alloc(8 * max(len(paragraphs), 1))
    mem.put(docview, "<Q", MODULE + sf.DOCVIEW_VTABLE)
    mem.put(docview + sf.DOCVIEW_TEXT, "<Q", styled)
    mem.put(docview + sf.DOCVIEW_LISTENER, "<Q", field + sf.LISTENER_IN_FIELD)
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
text_field(mem, root, 110, 992, ["Enjoy battle without worrying about a time limit.\r"])
text_field(mem, root, 100, 100, ["Two lines\r", "of text"])
text_field(mem, menu, 0, 700, ["HIDDEN"], visible=False)
text_field(mem, root, -1920, 0, ["Off to the side"])
text_field(mem, root, 300, 300, ["Faded out"], tint=(1, 1, 1, 0))
text_field(mem, root, 500, 500, ["   "])
orphan = text_field(mem, 0, 10, 10, ["Detached"])

# A DocView left behind by a closed screen: its field no longer has a node.
stale = text_field(mem, root, 5, 5, ["Close"])
listener = mem.ptr(stale + sf.DOCVIEW_LISTENER)
mem.put(listener - sf.LISTENER_IN_FIELD + sf.DISPLAY_RENDER_NODE, "<Q", 0)

reader = sf.ScaleformText(mem, MODULE)

found = reader.docviews()
check("sweep finds every DocView", len(found) == 10, f"{len(found)} found")

shown = reader.items()
texts = [it.text for it in shown]
check(
    "shown fields in reading order",
    texts == ["Two lines\nof text", "ARCADE", "TRAINING", "Enjoy battle without worrying about a time limit."],
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
check("hidden parent hides the field", "HIDDEN" in everything and not everything["HIDDEN"].shown)
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
    return sf.TextItem(text, x, y, tint, True, 7)


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

print()
print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
