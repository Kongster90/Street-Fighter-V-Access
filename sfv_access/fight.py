"""The fight's gauges, read from the game's own records of the two fighters.

Health, the Critical Art gauge and the V-Gauge used to be measured off the
bars on screen, which only worked on a 16 by 9 screen and read a full health
bar as 83 percent. The game keeps each fighter in a record found on
2026-09-28 by matching memory against the bars while the user played:

- Every record starts with the same type marker, a pointer to module +
  `VTABLE_RVA`, so a sweep of the read-write pages for that value finds both.
  Only two were ever there. The same two lasted through Training and five
  Versus matches in one run, and a later match had two new ones, found again
  because the old ones had lost their marker; so the sweep is done when the
  marker is gone and checked at every reading.
- The numbers are 16.16 fixed point in 4-byte slots: health and its most at
  +0xD0 and +0xD4 (1000, 1025), the Critical Art gauge and its most at +0xDC
  and +0xE0 (900, three stocks of 300), the V-Gauge and its most at +0xF4 and
  +0xF8 (600 for a two-bar V-Trigger, 900 for three, 300 a bar). Checked
  against the screen: the gauge passed 300 as the first stock lit, 600 as the
  second, was 900 with all three and 0 after a Critical Art.

Which record is player 1 is found by character. Each record points at +0x98
to its character's data, which holds the character's code ("Z30" for G) at
+0x1C0, and the battle's settings (below) hold each player's code at +0x90
of their entry; the record whose code is player 1's is player 1's. Found on
2026-09-29 after Survival put player 1's record lower in memory in one stage
and higher in the next, and Alt H and the beeps swapped with it: the order
in memory is chance. A mirror match leaves the codes alike, and then the old
ways are used: a CPU's controller (`KBP_BattlePlayerController_C`, its
`NetPlayerIndex` the side) sometimes holds its own fighter's record at
+0x6B0, and failing that player 1's is taken to be the higher address.

Which side is the player's own is in the battle's settings: the game's live
`KWBattleSetting` (under `KiwiGameSingleton_0`; another under
`Default__KWBattleSettingPseudoSave` is Training's saved one) points through
`m_player_setting` to a `KWBattlePlayerSetting` whose +0x28 is a table of
players 0x590 apart, and each has its `EKWCtrlType` at +0x21C (read from
`GetCtrlType`'s code): 0 USER, 1 NET, 2 COM, 3 DUMMY. The player's side is
the one USER (`player_side`). Choosing CPU VS PLAYER 1 on 2026-09-28 showed
COM then USER; restarting the mod mid-session had lost the side it had seen
chosen in Versus's list (`Narrator.player_side`, the fallback).

A counter hit is marked in the record of the fighter it lands on: the byte
at +0x2F8 goes from 0 to 1 as the hit lands and stays while they reel, 0.37
to 0.7 seconds, back to 0 sooner if a follow-up hit lands, which is never a
counter. A crush counter sets +0x2FC with it, for as long as its longer
stagger lasts. Found on 2026-09-30 by keeping both records around 35 hits in
Training, the dummy's Counter setting ON for 27 (crush counters among them)
and Normal for 8: no other byte in either record told them apart.

A crossup, an attack landing from behind, is marked nowhere: not in the
records, not in the 64 KB block they sit in, and the banner Training shows
("CROSS-UP", where "COUNTER" goes) is a picture the fight draws itself. It is
worked out instead, as the game must: at the moment a hit lands, the attacker
is on the side the defender faces away from. Where each fighter is and which
way they face come from their 3D characters (`PAWN_CLASS`), the two with a
costume, matched to the records by the character code in the folder the
costume sits in ("/Game/Chara/KEN/SkelMesh/01/DataAsset/DA_KEN_Costume_01";
not its name, since Ryu's costume 16 is "DA_Z00_Costume_16", which left
crossups silent for that fight on 2026-10-04): the root component's
location X, and its yaw, -90
facing towards +X and +90 towards -X. The defender does not turn until after
the hit, so the hit's own frame is the one to judge by, with two catches
found in the corner. There the attacker cannot get past a cornered
defender, both stand at the wall (X 750), and the game calls it a crossup:
level counts as behind. And on the hit's frame the defender's model jolts
2.5 units backwards, which made those level hits look like front ones; so
the defender's place is taken from the reading before the hit, the
attacker's from the hit's. Checked against the banner in screenshots of 35
jump-in hits on 2026-09-30, 21 crossups (8 in the corner, level) and 14 not,
all right; the closest front one had the attacker 1.1 units ahead.

Throws then sounded as crossups in play: Akuma's forward throw carries the
defender over and turns them round before its damage lands, which by place
alone is a hit from behind. Every throw recorded (5 forward, 5 back) turned
the defender between 15 and 618 ms before the damage, and no crossup had the
defender turn in the 0.6 s before it, so a hit is a crossup only if the
defender has faced the same way for `FACING_STEADY` (`Turns`).

That was not enough for Ryu (2026-10-04): his forward throw turns the
defender 0.93 s before its damage, and thrown again as they rose in the
corner they faced the wall the whole time. The record says it outright.
The int32 at `HIT_KIND` in the fighter hit holds -2 from a throw's grab and
on the reading its damage lands, in all 7 throws recorded that night, and 0,
1 or 2 as every one of 178 strikes landed, crossups included. It keeps the
last hit's kind until the next lands, so read it on the hit's own reading:
a crossup straight after a throw read -2 before it and 1 as it landed.

A crossup is sounded once a combo, on the hit that opens it, since after a
crossup every hit lands on a defender facing away. That was a hit a second
after the defender's last, until Zeku's V-Trigger (2026-10-04) juggled a
cornered Akira and landed its second hit 1.1 s after the first, level with
her at the wall, with no banner. The record counts the combo: the int32 at
`COMBO` is 1 as a combo's first hit lands, 2 for the next and so on, and 0
once it is over or for a blocked hit's chip. Replayed over every recording
that night it keeps all of Ryu's crossups and silences Zeku's.
"""

from __future__ import annotations

import ctypes
import re
import struct
import threading
from dataclasses import dataclass

VTABLE_RVA = 0x2C51680
HEALTH, HEALTH_MAX = 0xD0, 0xD4
CRITICAL, CRITICAL_MAX = 0xDC, 0xE0
V_GAUGE, V_GAUGE_MAX = 0xF4, 0xF8
BLOCK = V_GAUGE_MAX + 4 - HEALTH      # one read covers them all
COMBO = 0x180                         # int32, hits of the current combo taken, set as each lands, 0 once it ends
HIT_KIND = 0x2F4                      # int32, the kind of hit last taken, set as it lands: 0 to 2 a strike, -2 a throw
COUNTER, CRUSH = 0x2F8, 0x2FC         # set while a counter hit, and a crush counter, has its target reeling
MARKS = CRUSH + 1                     # read from the record's start, its type marker with them
PAWN_CLASS = "KBP_BattlePawn_C"       # a fighter's 3D character, and two spare ones without a costume
FACING_STEADY = 0.8                   # seconds a defender must have faced one way for a hit to be a crossup
STOCK = 300                           # a Critical Art stock, and a V-Trigger bar
MOST = 3000                           # nothing here is anything like this big
CONTROLLER_CLASS = "KBP_BattlePlayerController_C"
CONTROLLER_FIGHTER = 0x6B0
SETTING_CLASS = "KWBattleSetting"
PLAYER_TABLE = 0x28     # in a KWBattlePlayerSetting: the players' entries
ENTRY = 0x590
CTRL_TYPE = 0x21C       # EKWCtrlType
PLAYER_CHARA = 0x90     # the player's character code, "Z30", in their entry
RECORD_CHARA = 0x98     # in a fighter record: its character's data
CHARA_CODE = 0x1C0      # in that data: the character code
USER = 0
PAGE_READWRITE = 0x04
LARGEST_REGION = 256 << 20


@dataclass(frozen=True)
class Gauges:
    health: int
    health_most: int
    critical: int
    critical_most: int
    v: int
    v_most: int

    def words(self, label: str) -> str:
        """"You, health 83 percent, V-Trigger 1 of 2, Critical 2 of 3." """
        health = round(self.health * 100 / self.health_most)
        return (f"{label}, health {health} percent, "
                f"V-Trigger {self.v // STOCK} of {self.v_most // STOCK}, "
                f"Critical {self.critical // STOCK} of {self.critical_most // STOCK}.")


def _whole(raw: bytes, offset: int) -> int:
    """The whole part of a 16.16 fixed-point number at `offset` into `raw`."""
    return struct.unpack_from("<i", raw, offset)[0] >> 16


def gauges_from(raw: bytes | None) -> Gauges | None:
    """A fighter's gauges from the block read at the record + HEALTH, or None if they make no sense."""
    if not raw or len(raw) < BLOCK:
        return None
    at = lambda offset: _whole(raw, offset - HEALTH)  # noqa: E731
    g = Gauges(at(HEALTH), at(HEALTH_MAX), at(CRITICAL), at(CRITICAL_MAX), at(V_GAUGE), at(V_GAUGE_MAX))
    for value, most in ((g.health, g.health_most), (g.critical, g.critical_most), (g.v, g.v_most)):
        if not (0 < most <= MOST and 0 <= value <= most):
            return None
    return g


@dataclass(frozen=True)
class Marks:
    """A fighter's health, whether they are reeling from a counter hit and a
    crush counter, whether the hit they last took was a throw, and how many
    hits of a combo they have taken (0 out of one)."""
    health: int
    counter: bool
    crush: bool
    thrown: bool = False
    combo: int = 0


def counter_marks(raw: bytes | None, marker: int) -> Marks | None:
    """A fighter's `Marks`, from the bytes read at their record's start; None if it is no longer a record."""
    if not raw or len(raw) < MARKS or struct.unpack_from("<Q", raw)[0] != marker:
        return None
    thrown = struct.unpack_from("<i", raw, HIT_KIND)[0] < 0
    combo = struct.unpack_from("<i", raw, COMBO)[0]
    return Marks(_whole(raw, HEALTH), raw[COUNTER] == 1, raw[CRUSH] == 1, thrown, combo)


def behind(attacker_x: float, defender_x: float, defender_yaw: float) -> bool:
    """Whether the attacker is level with the defender or on the side they face
    away from: a yaw of -90 faces towards +X, and +90 towards -X. For a hit,
    the attacker's X on its frame and the defender's from before it."""
    facing = 1 if defender_yaw < 0 else -1
    return (attacker_x - defender_x) * facing <= 0


class Turns:
    """When each fighter last turned round, from successive `Fight.placements`."""

    def __init__(self) -> None:
        self.at = [float("-inf"), float("-inf")]
        self._facing: list[bool] | None = None

    def update(self, placed, now: float) -> None:
        if not placed:
            return
        facing = [yaw < 0 for _x, yaw in placed]
        if self._facing is not None:
            for side in (0, 1):
                if facing[side] != self._facing[side]:
                    self.at[side] = now
        self._facing = facing

    def steady(self, side: int, now: float) -> bool:
        """Whether `side` has faced the same way for `FACING_STEADY`, as no throw leaves them."""
        return now - self.at[side] >= FACING_STEADY


def crossup(side: int, placed_before, placed) -> bool:
    """Whether the hit `side` has just taken was a crossup, from `Fight.placements`
    at the reading before the hit and the reading that saw it."""
    if not placed_before or not placed:
        return False
    return behind(placed[1 - side][0], placed_before[side][0], placed[side][1])


# Alt H names the sides as you and your opponent; in a replay, by number.
PLAYER_SIDES = ("You", "Opponent")
REPLAY_SIDES = ("Player 1", "Player 2")


def describe(first: Gauges, second: Gauges, sides: tuple[str, str] = PLAYER_SIDES) -> str:
    return f"{first.words(sides[0])} {second.words(sides[1])}"


def player_side(ctrl_types: list[int]) -> int | None:
    """0 or 1 for the one side the player controls, None if both do or neither."""
    users = [side for side, kind in enumerate(ctrl_types[:2]) if kind == USER]
    return users[0] if len(users) == 1 else None


def code(raw: bytes | None) -> bytes | None:
    """A character code from the bytes it starts, "Z30", or None if it does not look like one."""
    text = (raw or b"").split(b"\0")[0]
    return text if 2 <= len(text) <= 4 and text.isalnum() else None


def costume_code(session, costume: int) -> bytes | None:
    """The character a costume asset belongs to, b"RYU" from its folder,
    "/Game/Chara/RYU/SkelMesh/16/DataAsset/DA_Z00_Costume_16"; its name can
    carry another code."""
    from . import unreal

    path = unreal.full_object_path(session.pm, session.names, costume, session.objects.layout)
    found = re.search(r"/Game/Chara/([^/.]+)/", path)
    return found.group(1).encode() if found else None


def order_by_character(records: list[int], record_codes: dict[int, bytes | None],
                       player_codes: list[bytes | None]) -> list[int] | None:
    """The two records with player 1's first, by character, or None when that cannot tell them apart.

    Player 1's character decides it when exactly one record has it; player
    2's only when player 1's cannot. Survival's settings move on to the next
    stage's opponent before the fight ends: in stage 3 against Ken they said
    Menat, and asking both to match gave up (2026-09-29). A mirror match,
    both records with the same character, is left to the other ways.
    """
    if len(records) != 2 or len(player_codes) < 2:
        return None
    for index, wanted in enumerate(player_codes[:2]):
        if wanted is None:
            continue
        having = [r for r in records if record_codes.get(r) == wanted]
        if len(having) == 1:
            other = next(r for r in records if r != having[0])
            return [having[0], other] if index == 0 else [other, having[0]]
    return None


_codes_by_name: dict[str, bytes] | None = None


def _codes_by_name_table() -> dict[str, bytes]:
    """Every regular fighter's name and character code, from character_names.json."""
    global _codes_by_name
    if _codes_by_name is None:
        from . import live

        _codes_by_name = {said: found.encode() for found, said in live.load_name_file().get("names", {}).items()}
    return _codes_by_name


def name_code(name: str | None) -> bytes | None:
    """A fighter's character code from their name, b"NSH" for "NASH", or None."""
    return _codes_by_name_table().get(name) if name else None


def order_by_name(records: list[int], record_codes: dict[int, bytes | None],
                  player_one: str | None) -> list[int] | None:
    """The two records with player 1's first, by the name the display gives player 1, or None.

    A fighter's name picks their record. A name that is no fighter's, as a
    story soldier's "AS-M", picks the record whose character is no regular
    fighter's, provided the other one is (the player's, on the right); a
    Fighter ID, as Survival's, over two regular fighters settles nothing.
    """
    if len(records) != 2 or not player_one:
        return None
    wanted = name_code(player_one)
    if wanted is not None:
        return order_by_character(records, record_codes, [wanted, None])
    regular = set(_codes_by_name_table().values())
    known = [r for r in records if record_codes.get(r) in regular]
    if len(known) != 1:
        return None
    return [next(r for r in records if r != known[0]), known[0]]


def order(records: list[int], links: dict[int, int]) -> tuple[list[int], str]:
    """The two records with player 1's first, and how that was decided.

    `links` maps a CPU controller's side (0 for player 1) to the record it
    holds. Without one, player 1's is the one at the higher address.
    """
    for side, record in links.items():
        if record in records and side in (0, 1):
            other = next(r for r in records if r != record)
            return ([record, other] if side == 0 else [other, record]), "the CPU's side"
    return sorted(records, reverse=True), "their order in memory"


class Fight:
    """Both fighters' gauges, for the read key.

    The records are swept for once, which takes about a second, and then
    checked by their marker at each reading. `note` receives what was found,
    for the screen log.
    """

    def __init__(self, note=None, names=None) -> None:
        self.records: list[int] | None = None
        self._note = note or (lambda text: None)
        # The name the fight display gives player 1, or None: what settles
        # player 1's record when the battle's settings name no characters, as
        # in story mode's fights.
        self._names = names or (lambda: None)
        self._last_how = ""
        self._last_side = ""
        # The last order settled by character, player 1's record first, and
        # whether the last reading's order can be trusted: settled by
        # character, or a mirror match, where nothing better is known.
        self._decided: list[int] | None = None
        self.certain = False
        # Player 1's record and player 2's, as the last reading ordered them.
        self.ordered: list[int] | None = None
        # Where player 1's and player 2's 3D characters keep their location
        # and rotation, found once a fight; see `placements`.
        self._pawns: list[tuple[int, int]] | None = None
        self._lock = threading.Lock()

    def read(self) -> tuple[Gauges, Gauges] | None:
        """Player 1's gauges and player 2's, or None if the fight cannot be read."""
        from . import live

        session = live.shared()
        if not session.attach():
            return None
        with self._lock:
            marker = session.module_base + VTABLE_RVA
            if self.records is None or any(session.pm.ptr(r) != marker for r in self.records):
                self.records = self._find(session.pm, marker)
                self._pawns = None
                self._note(f"fight: {len(self.records)} fighter records"
                           + (f" at {', '.join(f'{r:#x}' for r in self.records)}" if self.records else ""))
            if len(self.records) != 2:
                self.records = None
                return None
            players = self._players(session)
            codes = {r: code(self._record_code(session.pm, r)) for r in self.records}
            by_character = order_by_character(self.records, codes, [c for _k, c in players])
            by_names = None
            if by_character is None:
                # Story mode's fights leave the settings' characters empty
                # ("characters None, None" on 2026-10-04, no sound in a fight
                # against Nash); the display names the opponent, "NASH".
                by_names = order_by_name(self.records, codes, self._names())
            player_codes = [c for _k, c in players]
            mirror = len(player_codes) == 2 and player_codes[0] is not None and player_codes[0] == player_codes[1]
            self.certain = by_character is not None or mirror
            if by_character is not None:
                ordered, how = by_character, "character"
                self._decided = by_character
            elif self._decided is not None and set(self._decided) == set(self.records):
                # The same two records, settled already: the settings are
                # rewritten between Survival's stages, and for a moment read
                # as nothing, and a story fight's empty out after its start.
                ordered, how = self._decided, "character, as before"
                self.certain = True
            elif by_names is not None:
                ordered, how = by_names, f"player 1's name on the display, {self._names()!r}"
                self._decided = by_names
                self.certain = True
            else:
                ordered, how = order(self.records, self._links(session))
                how += " (characters " + ", ".join(repr(c) for _k, c in players) + " did not settle it)"
            if how != self._last_how:
                self._last_how = how
                self._note(f"fight: player 1's record is {ordered[0]:#x}, by {how}")
            self.ordered = ordered
            if self._pawns is None:
                # Looked for once a fight; an empty list is "looked, and none to use".
                self._pawns = self._find_pawns(session, [code(self._record_code(session.pm, r)) for r in ordered]) or []
            first, second = (gauges_from(session.pm.read(r + HEALTH, BLOCK)) for r in ordered)
            if first is None or second is None:
                return None
            return first, second

    def counters(self) -> list[Marks] | None:
        """Player 1's and player 2's `Marks`, from the records the last `read`
        ordered; None while that order is unsure.

        Two small reads and nothing else, so it can be asked far more often
        than `read`: the counter hit's sound is for following up on it.
        """
        from . import live

        ordered = self.ordered
        session = live.shared()
        if ordered is None or not self.certain or session.pm is None:
            return None
        marker = session.module_base + VTABLE_RVA
        marks = [counter_marks(session.pm.read(r, MARKS), marker) for r in ordered]
        return None if None in marks else marks

    def placements(self) -> list[tuple[float, float]] | None:
        """Player 1's and player 2's (location X, yaw), from their 3D characters;
        None until `read` has found them, or if they no longer make sense."""
        from . import live

        pawns = self._pawns
        session = live.shared()
        if not pawns or session.pm is None:
            return None
        out = []
        for location, rotation in pawns:
            x, yaw = session.pm.f32(location), session.pm.f32(rotation + 4)
            if x is None or yaw is None or abs(abs(yaw) - 90) > 1:
                self._pawns = None   # found again at the next `read`
                return None
            out.append((x, yaw))
        return out

    def _find_pawns(self, session, codes: list[bytes | None]) -> list[tuple[int, int]] | None:
        """Player 1's and player 2's characters' location and rotation addresses,
        by the character code of each costume's folder; None for a mirror match."""
        if len(codes) != 2 or None in codes or codes[0] == codes[1]:
            return None
        by_code = {}
        try:
            for obj, _name in session.find_by_class(PAWN_CLASS, limit=8):
                props = session.all_properties(obj)
                costume = session.pm.ptr(obj + props["CostumeData"].offset)
                root = session.pm.ptr(obj + props["RootComponent"].offset)
                if not costume or not root:
                    continue
                character = costume_code(session, costume)
                if character is None:
                    continue
                component = session.all_properties(root)
                by_code[character] = (root + component["RelativeLocation"].offset,
                                      root + component["RelativeRotation"].offset)
        except Exception as exc:
            self._note(f"fight: characters not found: {exc!r}")
            return None
        found = [by_code.get(c) for c in codes]
        if None in found:
            self._note(f"fight: characters {sorted(by_code)} do not match the records' {codes}")
            return None
        return found

    def side(self) -> int | None:
        """Which side the player is on, 0 the left, from the battle's settings, or None."""
        from . import live

        session = live.shared()
        if not session.attach():
            return None
        players = self._players(session)
        if not players:
            return None
        kinds = [kind for kind, _code in players]
        side = player_side([k for k in kinds if k is not None])
        note = f"fight: controllers {kinds}, the player's side {side}"
        if note != self._last_side:
            self._last_side = note
            self._note(note)
        return side

    def _players(self, session) -> list[tuple[int | None, bytes | None]]:
        """Player 1's and player 2's controller type and character code, from the live settings."""
        from . import unreal

        try:
            for obj, _name in session.find_by_class(SETTING_CLASS, limit=8):
                path = unreal.full_object_path(session.pm, session.names, obj, session.objects.layout)
                prop = session.all_properties(obj).get("m_player_setting")
                if "Default__" in path or prop is None:
                    continue
                players = session.pm.ptr(obj + prop.offset)
                table = session.pm.ptr(players + PLAYER_TABLE) if players else None
                if not table:
                    continue
                return [(session.pm.i32(table + i * ENTRY + CTRL_TYPE),
                         code(session.pm.read(table + i * ENTRY + PLAYER_CHARA, 8))) for i in (0, 1)]
        except Exception as exc:
            self._note(f"fight: settings not read: {exc!r}")
        return []

    @staticmethod
    def _record_code(pm, record: int) -> bytes | None:
        data = pm.ptr(record + RECORD_CHARA)
        return pm.read(data + CHARA_CODE, 8) if data else None

    @staticmethod
    def _links(session) -> dict[int, int]:
        from . import unreal

        links = {}
        for obj, _name in session.find_by_class(CONTROLLER_CLASS, limit=8):
            prop = session.all_properties(obj).get("NetPlayerIndex")
            if prop is None:
                continue
            side = unreal.read_property(session.pm, session.names, obj, prop, session.objects.layout)
            record = session.pm.ptr(obj + CONTROLLER_FIGHTER)
            if side is not None and record:
                links[side] = record
        return links

    @staticmethod
    def _find(pm, marker: int) -> list[int]:
        """Every record in the read-write pages, by its marker."""
        import numpy as np

        kernel32 = ctypes.windll.kernel32
        found: list[int] = []
        for region in pm.regions():
            if region.protect != PAGE_READWRITE or region.size > LARGEST_REGION:
                continue
            words = np.empty(region.size // 8, dtype=np.uint64)
            got = ctypes.c_size_t(0)
            if not kernel32.ReadProcessMemory(pm.handle, ctypes.c_void_p(region.base),
                                              words.ctypes.data_as(ctypes.c_void_p),
                                              ctypes.c_size_t(region.size), ctypes.byref(got)):
                continue
            found += [region.base + int(i) * 8 for i in np.nonzero(words == marker)[0]]
        return found
