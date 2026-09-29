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

Which record is player 1 is not in the record as far as has been found (a
field at +0x300 that looked like it turned out to mark who was knocked out).
A CPU's controller (`KBP_BattlePlayerController_C`, its `NetPlayerIndex` the
side) sometimes holds its own fighter's record at +0x6B0, where a player's
holds -1: through Training and five matches, but not in a later one. Without
it the order seen in every pair of records so far is used, player 1's at the
higher address.

Which side is the player's own is in the battle's settings: the game's live
`KWBattleSetting` (under `KiwiGameSingleton_0`; another under
`Default__KWBattleSettingPseudoSave` is Training's saved one) points through
`m_player_setting` to a `KWBattlePlayerSetting` whose +0x28 is a table of
players 0x590 apart, and each has its `EKWCtrlType` at +0x21C (read from
`GetCtrlType`'s code): 0 USER, 1 NET, 2 COM, 3 DUMMY. The player's side is
the one USER (`player_side`). Choosing CPU VS PLAYER 1 on 2026-09-28 showed
COM then USER; restarting the mod mid-session had lost the side it had seen
chosen in Versus's list (`Narrator.player_side`, the fallback).
"""

from __future__ import annotations

import ctypes
import struct
import threading
from dataclasses import dataclass

VTABLE_RVA = 0x2C51680
HEALTH, HEALTH_MAX = 0xD0, 0xD4
CRITICAL, CRITICAL_MAX = 0xDC, 0xE0
V_GAUGE, V_GAUGE_MAX = 0xF4, 0xF8
BLOCK = V_GAUGE_MAX + 4 - HEALTH      # one read covers them all
STOCK = 300                           # a Critical Art stock, and a V-Trigger bar
MOST = 3000                           # nothing here is anything like this big
CONTROLLER_CLASS = "KBP_BattlePlayerController_C"
CONTROLLER_FIGHTER = 0x6B0
SETTING_CLASS = "KWBattleSetting"
PLAYER_TABLE = 0x28     # in a KWBattlePlayerSetting: the players' entries
ENTRY = 0x590
CTRL_TYPE = 0x21C       # EKWCtrlType
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


def describe(first: Gauges, second: Gauges) -> str:
    return f"{first.words('You')} {second.words('Opponent')}"


def player_side(ctrl_types: list[int]) -> int | None:
    """0 or 1 for the one side the player controls, None if both do or neither."""
    users = [side for side, kind in enumerate(ctrl_types[:2]) if kind == USER]
    return users[0] if len(users) == 1 else None


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

    def __init__(self, note=None) -> None:
        self.records: list[int] | None = None
        self._note = note or (lambda text: None)
        self._last_how = ""
        self._last_side = ""
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
                self._note(f"fight: {len(self.records)} fighter records"
                           + (f" at {', '.join(f'{r:#x}' for r in self.records)}" if self.records else ""))
            if len(self.records) != 2:
                self.records = None
                return None
            ordered, how = order(self.records, self._links(session))
            if how != self._last_how:
                self._last_how = how
                self._note(f"fight: player 1's record is {ordered[0]:#x}, by {how}")
            first, second = (gauges_from(session.pm.read(r + HEALTH, BLOCK)) for r in ordered)
            if first is None or second is None:
                return None
            return first, second

    def side(self) -> int | None:
        """Which side the player is on, 0 the left, from the battle's settings, or None."""
        from . import live, unreal

        session = live.shared()
        if not session.attach():
            return None
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
                kinds = [session.pm.i32(table + i * ENTRY + CTRL_TYPE) for i in (0, 1)]
                side = player_side([k for k in kinds if k is not None])
                note = f"fight: controllers {kinds}, the player's side {side}"
                if note != self._last_side:
                    self._last_side = note
                    self._note(note)
                return side
        except Exception as exc:
            self._note(f"fight: side not read: {exc!r}")
        return None

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
