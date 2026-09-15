"""Live game state read from the running process.

Wraps the engine table discovery in something the running tool can use: attach
once, then ask questions about whatever screen is open. Reads only, from
outside the process, so a stale pointer fails a read rather than disturbing the
game.

Character select is the first screen served here, because it is the one the
pixel reader cannot do at all: the roster is artwork, and the only text on
screen is the two names.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import unreal
from .memory import ProcessMemory, find_pid

EXE = "StreetFighterV.exe"
GAME_PATH_HINT = r"Binaries\Win64"
NAME_MAP_FILE = Path(__file__).resolve().parent.parent / "character_names.json"

ENGINE_OWNERS = {"Object", "Actor", "Pawn", "Info", "Controller", "HUD"}
# How long a name or class not found is taken as missing before looking again.
# Started with the game, the mod first looked while the game was still loading,
# found the name table incomplete, and took Controller Setting's class for
# missing for the rest of the session.
MISS_RETRY = 15.0


def side_key(y: float) -> str:
    """Which side of the stage a preview model stands on.

    The two sit at roughly minus 570 and plus 530, so the sign is a stable
    label that survives the models being swapped out as the cursor moves.
    """
    return "neg" if y < 0 else "pos"


def load_name_file() -> dict:
    """Character codes mapped to display names, plus which side is player one.

    The display names come from the localisation table, which ships encrypted,
    so this file is built up by `tools/learn_names.py` pairing what memory says
    with what is on screen. An unknown code is spoken as-is rather than hidden.

    `player_one_side` is the sign of the world position where player one's
    model stands. Nothing in the objects records a player number, so the
    learning tool establishes it by watching which side changes when.
    """
    try:
        data = json.loads(NAME_MAP_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"names": {}, "player_one_side": "unknown"}
    return {
        "names": {k.upper(): v for k, v in data.get("names", {}).items()},
        "player_one_side": data.get("player_one_side", "unknown"),
    }


def save_name_file(names: dict[str, str], player_one_side: str) -> None:
    NAME_MAP_FILE.write_text(
        json.dumps(
            {
                "player_one_side": player_one_side,
                "names": dict(sorted(names.items())),
            },
            indent=1,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


@dataclass
class Fighter:
    code: str
    costume: int | None = None
    color: int | None = None
    y: float = 0.0  # world position, which is what separates the two sides

    def describe(self, names: dict[str, str]) -> str:
        label = names.get(self.code.upper(), self.code)
        parts = [label]
        if self.costume is not None:
            parts.append(f"costume {self.costume}")
        if self.color is not None:
            parts.append(f"colour {self.color}")
        return ", ".join(parts)


def valid_code(code) -> bool:
    """Is this a real character code rather than a half-written string?

    Reads can land while the game is replacing the value, which yields
    fragments of the previous string or plain rubbish. Codes are short and
    alphanumeric, so anything else is discarded rather than learned.
    """
    if not isinstance(code, str):
        return False
    code = code.strip()
    return 2 <= len(code) <= 6 and code.isascii() and code.isalnum()


# Capcom's internal codes use the Japanese names, and the western release swaps
# three of them: the dictator is Vega in Japan, the claw fighter is Balrog, and
# the boxer is Bison. So none of these three codes can ever read as initials of
# the name on screen, and the rule below would call all three wrong forever,
# which is why hovering never learned them. Established from the game's own
# V-Trigger data by tools/names_from_data.py.
SWAPPED_NAMES = {"VEG": "M. BISON", "BLR": "VEGA", "BSN": "BALROG"}


def code_matches_name(code: str, name: str) -> bool:
    """Does the code read as an abbreviation of the name?

    Most of the roster uses initials of the displayed name, so KEN, CMY and RSD
    line up with KEN, CAMMY and RASHID. Season characters use codes like Z20
    that cannot be checked this way, so a failure here only means unproven, not
    wrong.

    The three swapped names above are the exception, and are accepted outright.
    """
    if SWAPPED_NAMES.get(code.upper()) == name.strip().upper():
        return True
    letters = [c for c in name.upper() if c.isalpha()]
    pos = 0
    for ch in code.upper():
        if not ch.isalpha():
            return False
        while pos < len(letters) and letters[pos] != ch:
            pos += 1
        if pos >= len(letters):
            return False
        pos += 1
    return True


class Live:
    """An attached view of the running game."""

    def __init__(self) -> None:
        self.pm: ProcessMemory | None = None
        self.pid: int | None = None
        self.names = None
        self.objects = None
        self.struct_layout = None
        self.module_base = 0
        self._lock = threading.Lock()
        loaded = load_name_file()
        self._name_map: dict[str, str] = loaded["names"]
        self.player_one_side: str = loaded["player_one_side"]
        self._class_cache: dict[str, int] = {}
        self._instance_cache: dict[str, list[tuple[int, str]]] = {}
        self._prop_cache: dict[int, dict[str, unreal.Property]] = {}
        self._preview_owner: int | None = None
        self._name_lookup: dict[str, int] | None = None
        self._name_lookup_at = 0.0
        self._class_missed_at: dict[str, float] = {}

    def reload_names(self) -> None:
        loaded = load_name_file()
        self._name_map = loaded["names"]
        self.player_one_side = loaded["player_one_side"]

    # ------------------------------------------------------------------ setup
    def still_alive(self) -> bool:
        """Cheap check that the existing handle is still good.

        Re-deriving the process id means walking every process on the machine,
        which is far too slow to do on a polling loop. Reading a value we
        already know the address of costs nothing and fails the moment the
        game closes.
        """
        if self.pm is None or self.objects is None:
            return False
        count = self.pm.i32(self.objects.address + 8)
        return count is not None and 1000 < count < 8_000_000

    def attach(self) -> bool:
        with self._lock:
            if self.still_alive():
                return True
            self.detach()
            pid = find_pid(EXE, GAME_PATH_HINT, require_path=True)
            if pid is None:
                return False
            try:
                pm = ProcessMemory(pid)
            except OSError:
                return False
            mod = next((m for m in pm.modules() if m.name.lower() == EXE.lower()), None)
            if mod is None:
                pm.close()
                return False
            names = unreal.name_array_from_hint(pm, mod.base)
            objects = unreal.object_array_from_hint(pm, names, mod.base) if names else None
            if names is None or objects is None:
                pm.close()
                return False
            layout = unreal.find_struct_layout(pm, names, objects, verbose=False)
            if layout is None:
                pm.close()
                return False
            self.pm, self.pid = pm, pid
            self.names, self.objects, self.struct_layout = names, objects, layout
            self.module_base = mod.base
            self._class_cache.clear()
            self._class_missed_at.clear()
            self._instance_cache.clear()
            self._prop_cache.clear()
            self._preview_owner = None
            self._name_lookup = None
            return True

    def detach(self) -> None:
        if self.pm is not None:
            self.pm.close()
        self.pm = None
        self.pid = None
        self.names = self.objects = self.struct_layout = None

    @property
    def attached(self) -> bool:
        return self.pm is not None

    # ---------------------------------------------------------------- queries
    CLASS_KINDS = ("Class", "BlueprintGeneratedClass", "DynamicClass")

    def name_index(self, text: str) -> int | None:
        """The name table index for a string, with the whole table read once.

        A name not in the table read is read for again once the table is
        `MISS_RETRY` old: names are added as the game loads.
        """
        if (self._name_lookup is not None and text not in self._name_lookup
                and time.monotonic() - self._name_lookup_at > MISS_RETRY):
            self._name_lookup = None
        if self._name_lookup is None:
            self._name_lookup_at = time.monotonic()
            table: dict[str, int] = {}
            layout = self.names.layout
            import struct

            for chunk_index in range(self.names.num_chunks):
                chunk = self.pm.ptr(self.names.address + chunk_index * 8)
                if not chunk:
                    continue
                raw = self.pm.read(chunk, layout.elements_per_chunk * 8)
                if not raw:
                    continue
                base = chunk_index * layout.elements_per_chunk
                for i in range(layout.elements_per_chunk):
                    if base + i >= self.names.num_elements:
                        break
                    entry = struct.unpack_from("<Q", raw, i * 8)[0]
                    if not entry:
                        continue
                    value = unreal.entry_text(self.pm, entry, layout)
                    if value is not None:
                        table.setdefault(value, base + i)
            self._name_lookup = table
        return self._name_lookup.get(text)

    def class_address(self, class_name: str) -> int | None:
        """The UClass object for a name, found once and remembered.

        Comparing class pointers is far cheaper than resolving a class name for
        every object, and the address is stable for the life of the process.
        """
        if class_name in self._class_cache:
            if self._class_cache[class_name] is not None:
                return self._class_cache[class_name]
            if time.monotonic() - self._class_missed_at.get(class_name, 0.0) < MISS_RETRY:
                return None
        pm, names, objects = self.pm, self.names, self.objects
        layout = objects.layout

        # Resolving each object's name means following it into the name table,
        # several reads per object across 151,000 of them. The name we are
        # looking for has one index, so find that once and then compare a
        # single integer per object.
        wanted = self.name_index(class_name)
        if wanted is None:
            self._class_cache[class_name] = None
            self._class_missed_at[class_name] = time.monotonic()
            return None

        import struct

        data = pm.ptr(objects.address)
        raw = pm.read(data, objects.num_elements * 8) if data else None
        if not raw:
            return None

        for i in range(objects.num_elements):
            obj = struct.unpack_from("<Q", raw, i * 8)[0]
            if not obj or obj < 0x10000:
                continue
            if pm.i32(obj + layout.name_private) != wanted:
                continue
            # A class written in C++ is a UClass; one made as a Blueprint is a
            # BlueprintGeneratedClass. Accepting only the first missed every
            # Blueprint class and sent the caller back to a full scan each time.
            if unreal.object_class_name(pm, names, obj, layout) in self.CLASS_KINDS:
                self._class_cache[class_name] = obj
                return obj
        # Remember the miss too, for a while: a fruitless search costs as much
        # as a successful one, but a class can load after the first look.
        self._class_cache[class_name] = None
        self._class_missed_at[class_name] = time.monotonic()
        return None

    def find_by_class(self, class_name: str, limit: int = 8) -> list[tuple[int, str]]:
        """Live instances of a class.

        Objects are not allocated in screen order, so there is no shortcut of
        looking only at the end of the list. Instead the whole pointer array is
        pulled in one read and each entry is checked by comparing its class
        pointer, which is a single read rather than a name resolution. Results
        are cached and revalidated, so repeat calls cost almost nothing.
        """
        if not self.attached:
            return []
        cached = self._instance_cache.get(class_name)
        if cached is not None and self._still_valid(cached, class_name):
            return cached
        # A class that does not exist here should not be searched for again and
        # again while the same screen is open; `class_address` looks again
        # once its miss is `MISS_RETRY` old.
        pm, objects, names = self.pm, self.objects, self.names
        layout = objects.layout
        target = self.class_address(class_name)
        if target is None:
            return []

        data = pm.ptr(objects.address)
        raw = pm.read(data, objects.num_elements * 8) if data else None
        if not raw:
            return []

        import struct

        out: list[tuple[int, str]] = []
        for i in range(objects.num_elements):
            obj = struct.unpack_from("<Q", raw, i * 8)[0]
            if not obj or obj < 0x10000:
                continue
            if pm.ptr(obj + layout.class_private) != target:
                continue
            nm = unreal.object_name(pm, names, obj, layout)
            if not nm or nm.startswith("Default__"):
                continue
            out.append((obj, nm))
            if len(out) >= limit:
                break

        self._instance_cache[class_name] = out
        return out

    def _still_valid(self, entries: list[tuple[int, str]], class_name: str) -> bool:
        """Do the remembered objects still exist and still belong to that class?"""
        target = self._class_cache.get(class_name)
        if target is None or not entries:
            return False
        layout = self.objects.layout
        return all(self.pm.ptr(obj + layout.class_private) == target for obj, _ in entries)

    def invalidate(self) -> None:
        """Forget cached instances, for when the screen has changed."""
        self._instance_cache.clear()

    def properties(self, obj: int) -> dict[str, unreal.Property]:
        pm, names, objects = self.pm, self.names, self.objects
        cls = pm.ptr(obj + objects.layout.class_private)
        props = unreal.class_properties(
            pm, names, cls, objects.layout, self.struct_layout
        )
        return {p.name: p for p in props if p.owner not in ENGINE_OWNERS}

    def value(self, obj: int, props: dict, name: str):
        prop = props.get(name)
        if prop is None:
            return None
        return unreal.read_property(self.pm, self.names, obj, prop, self.objects.layout)

    def all_properties(self, obj: int) -> dict[str, unreal.Property]:
        """Every property including inherited ones, cached per class."""
        cls = self.pm.ptr(obj + self.objects.layout.class_private)
        cached = self._prop_cache.get(cls)
        if cached is None:
            props = unreal.class_properties(
                self.pm, self.names, cls, self.objects.layout, self.struct_layout
            )
            cached = {p.name: p for p in props}
            self._prop_cache[cls] = cached
        return cached

    def actor_y(self, obj: int) -> float | None:
        """An actor's world Y, read through its root component."""
        props = self.all_properties(obj)
        root = props.get("RootComponent")
        if root is None:
            return None
        comp = self.pm.ptr(obj + root.offset)
        if not comp:
            return None
        cprops = self.all_properties(comp)
        loc = cprops.get("RelativeLocation")
        if loc is None:
            return None
        return self.pm.f32(comp + loc.offset + 4)  # X, then Y

    def preview_pawns(self) -> list[tuple[int, str]]:
        """The two preview models, found without walking the object list.

        Moving the cursor destroys the models and builds new ones, so anything
        that caches them by address is stale immediately and a fresh search of
        all 151,000 objects costs the best part of a second. The scene actor
        that owns them survives the whole screen, and it holds them in an
        array, so finding it once turns every later read into two pointer
        lookups.
        """
        actor = self._preview_owner
        if actor is not None and not self._owner_still_valid(actor):
            actor = self._preview_owner = None
        if actor is None:
            found = self.find_by_class("BP_CharaSelectActor_C", limit=1)
            if not found:
                return self.find_by_class("KWPreviewPawn", limit=4)
            actor = self._preview_owner = found[0][0]

        props = self.properties(actor)
        prop = props.get("PreviewCharacters")
        if prop is None:
            return self.find_by_class("KWPreviewPawn", limit=4)

        at = actor + prop.offset
        data = self.pm.ptr(at)
        count = self.pm.i32(at + 8)
        if not data or not count or not (0 < count <= 8):
            return []
        out = []
        for i in range(count):
            pawn = self.pm.ptr(data + i * 8)
            if pawn:
                out.append((pawn, ""))
        return out

    def _owner_still_valid(self, actor: int) -> bool:
        target = self._class_cache.get("BP_CharaSelectActor_C")
        if target is None:
            return False
        return self.pm.ptr(actor + self.objects.layout.class_private) == target

    def character_select(self) -> list[Fighter]:
        """Each side's highlighted fighter, from the preview models on stage.

        Ordered by world position, because the objects themselves carry no
        player number and the order they were created in has nothing to do with
        which side they stand on. Sorting on position was the fix for names
        being learned against the wrong fighter.
        """
        if not self.attach():
            return []
        found = []
        for obj, _nm in self.preview_pawns():
            props = self.properties(obj)
            code = self.value(obj, props, "CharaCode")
            if not valid_code(code):
                continue
            y = self.actor_y(obj)
            found.append(
                Fighter(
                    code=code.strip(),
                    costume=self.value(obj, props, "CostumeId"),
                    color=self.value(obj, props, "ColorId"),
                    y=0.0 if y is None else y,
                )
            )
        found.sort(key=lambda f: f.y)
        if self.player_one_side == "pos":
            found.reverse()
        return found

    def character_select_lines(self) -> list[str]:
        """One line per side, so only the side that changed need be spoken."""
        fighters = self.character_select()
        if not fighters:
            return []
        if self.player_one_side in ("neg", "pos"):
            labels = ["Player 1", "Player 2"]
        else:
            labels = ["One side", "Other side"]
        return [
            f"{labels[i] if i < len(labels) else 'Other'}, {f.describe(self._name_map)}"
            for i, f in enumerate(fighters)
        ]

    def describe_character_select(self) -> str | None:
        fighters = self.character_select()
        if not fighters:
            return None
        # Until the learning tool has established which side is which, name the
        # fighters without claiming a player number for either.
        if self.player_one_side not in ("neg", "pos"):
            listed = ". ".join(f.describe(self._name_map) for f in fighters)
            return f"{listed}. Sides not identified yet."
        labels = ["Player 1", "Player 2"]
        parts = [
            f"{labels[i] if i < len(labels) else 'Other'}, {f.describe(self._name_map)}"
            for i, f in enumerate(fighters)
        ]
        return ". ".join(parts) + "."


_shared: Live | None = None


def shared() -> Live:
    global _shared
    if _shared is None:
        _shared = Live()
    return _shared
