"""Check the fight's gauges as read from the fighters' records, with records built by hand.

The numbers are the ones read on 2026-09-28: player 1 (Zeku) at 447 of 1000
health, the Critical Art gauge at 62 of 900 and the V-Gauge at 0 of 600;
player 2 (Ken) knocked out at 0 of 1025 with both gauges full at 900. Needs
no game.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access import fight  # noqa: E402

ok = True


def check(label, condition, detail=""):
    global ok
    if condition:
        print(f"PASS  {label}{(': ' + detail) if detail else ''}")
    else:
        ok = False
        print(f"FAIL  {label}{(': ' + detail) if detail else ''}")


def block(health, health_most, critical, critical_most, v, v_most, fraction=0):
    """The bytes read at a record + HEALTH: 16.16 fixed point in 4-byte slots."""
    raw = bytearray(fight.BLOCK)
    for offset, value in ((fight.HEALTH, health), (fight.HEALTH_MAX, health_most),
                          (fight.CRITICAL, critical), (fight.CRITICAL_MAX, critical_most),
                          (fight.V_GAUGE, v), (fight.V_GAUGE_MAX, v_most)):
        struct.pack_into("<i", raw, offset - fight.HEALTH, (value << 16) | fraction)
    return bytes(raw)


zeku = fight.gauges_from(block(447, 1000, 62, 900, 0, 600, fraction=0x8000))
ken = fight.gauges_from(block(0, 1025, 900, 900, 900, 900))
check("a record reads as its whole numbers, fractions dropped",
      zeku == fight.Gauges(447, 1000, 62, 900, 0, 600), repr(zeku))
check("both fighters are said as before, with how many bars each gauge has",
      fight.describe(zeku, ken) ==
      "You, health 45 percent, V-Trigger 0 of 2, Critical 0 of 3. "
      "Opponent, health 0 percent, V-Trigger 3 of 3, Critical 3 of 3.",
      fight.describe(zeku, ken))
stocks = fight.gauges_from(block(1000, 1000, 638, 900, 301, 600))
check("stocks are whole 300s: 638 is two Critical Art stocks, 301 one V-Trigger bar",
      "V-Trigger 1 of 2, Critical 2 of 3" in stocks.words("You"), stocks.words("You"))
check("nonsense is no reading",
      fight.gauges_from(block(1200, 1000, 0, 900, 0, 600)) is None
      and fight.gauges_from(block(10, 0, 0, 900, 0, 600)) is None
      and fight.gauges_from(b"\x00" * 4) is None and fight.gauges_from(None) is None)

P1, P2 = 0x250C898CC00, 0x250C8980CC0
check("the CPU as player 2 makes the other record player 1's",
      fight.order([P2, P1], {1: P2, 0: 0xFFFFFFFFFFFFFFFF, 2: 0, 3: 0}) == ([P1, P2], "the CPU's side"))
check("the CPU as player 1 is put first, wherever it is in memory",
      fight.order([P2, P1], {0: P2}) == ([P2, P1], "the CPU's side"))
check("with no CPU, player 1's record is the one higher in memory",
      fight.order([P2, P1], {0: 0xFFFFFFFFFFFFFFFF}) == ([P1, P2], "their order in memory"))

# Player 1's record by character: each record's character data holds its
# code, and the settings hold each player's. Survival on 2026-09-29 had G
# (Z30) as player 1 lower in memory in one stage and higher in the next.
LOW, HIGH = 0x2516A85CC00, 0x2516A85E580
check("a character code is read from the bytes it starts",
      fight.code(b"Z30\0\0\0\0\0") == b"Z30" and fight.code(b"KEN\0") == b"KEN"
      and fight.code(b"\0\0\0\0") is None and fight.code(b"\xff\xfe\x01\0") is None and fight.code(None) is None)
check("player 1's record is the one with player 1's character, wherever it is in memory",
      fight.order_by_character([LOW, HIGH], {LOW: b"Z30", HIGH: b"Z40"}, [b"Z30", b"Z40"]) == [LOW, HIGH]
      and fight.order_by_character([LOW, HIGH], {LOW: b"Z40", HIGH: b"Z30"}, [b"Z30", b"Z40"]) == [HIGH, LOW])
check("a mirror match, or a code not read, leaves it to the other ways",
      fight.order_by_character([LOW, HIGH], {LOW: b"KEN", HIGH: b"KEN"}, [b"KEN", b"KEN"]) is None
      and fight.order_by_character([LOW, HIGH], {LOW: None, HIGH: b"Z40"}, [b"Z30", b"Z40"]) is None
      and fight.order_by_character([LOW, HIGH], {LOW: b"Z30", HIGH: b"Z40"}, [b"Z30", None]) is None)

# The battle's settings say who controls each side: 0 USER, 1 NET, 2 COM,
# 3 DUMMY. CPU VS PLAYER 1 read COM then USER on 2026-09-28.
check("the player is the side the one USER controls",
      fight.player_side([2, 0]) == 1 and fight.player_side([0, 2]) == 0
      and fight.player_side([0, 3]) == 0 and fight.player_side([1, 0]) == 1)
check("two people on one machine, or nobody, leave the side unknown",
      fight.player_side([0, 0]) is None and fight.player_side([2, 2]) is None and fight.player_side([]) is None)

print()
print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
