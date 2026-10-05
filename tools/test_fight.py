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
check("Survival's settings naming the next opponent still find player 1 by their own character",
      fight.order_by_character([LOW, HIGH], {LOW: b"KEN", HIGH: b"Z37"}, [b"Z37", b"Z23"]) == [HIGH, LOW])
check("player 2's character decides it when player 1's cannot be read",
      fight.order_by_character([LOW, HIGH], {LOW: None, HIGH: b"Z40"}, [b"Z30", b"Z40"]) == [LOW, HIGH]
      and fight.order_by_character([LOW, HIGH], {LOW: b"Z30", HIGH: b"Z40"}, [None, b"Z40"]) == [LOW, HIGH])
check("a mirror match, or nothing read, leaves it to the other ways",
      fight.order_by_character([LOW, HIGH], {LOW: b"KEN", HIGH: b"KEN"}, [b"KEN", b"KEN"]) is None
      and fight.order_by_character([LOW, HIGH], {LOW: None, HIGH: None}, [b"Z30", b"Z40"]) is None
      and fight.order_by_character([LOW, HIGH], {LOW: b"Z30", HIGH: b"Z40"}, [None, None]) is None)

# The battle's settings say who controls each side: 0 USER, 1 NET, 2 COM,
# 3 DUMMY. CPU VS PLAYER 1 read COM then USER on 2026-09-28.
check("the player is the side the one USER controls",
      fight.player_side([2, 0]) == 1 and fight.player_side([0, 2]) == 0
      and fight.player_side([0, 3]) == 0 and fight.player_side([1, 0]) == 1)
check("two people on one machine, or nobody, leave the side unknown",
      fight.player_side([0, 0]) is None and fight.player_side([2, 2]) is None and fight.player_side([]) is None)


# Counter hits, marked in the record of the fighter hit (2026-09-30).
MARKER = 0x7FF6_2C51_680


def record_start(counter=0, crush=0, marker=MARKER, health=1000, kind=0, combo=0):
    raw = bytearray(fight.MARKS)
    struct.pack_into("<Q", raw, 0, marker)
    struct.pack_into("<i", raw, fight.HEALTH, health << 16)
    struct.pack_into("<i", raw, fight.HIT_KIND, kind)
    struct.pack_into("<i", raw, fight.COMBO, combo)
    raw[fight.COUNTER], raw[fight.CRUSH] = counter, crush
    return bytes(raw)


check("a fighter reeling from a counter hit is marked so, with their health",
      fight.counter_marks(record_start(1, health=812), MARKER) == fight.Marks(812, True, False))
check("a crush counter is marked as both",
      fight.counter_marks(record_start(1, 1), MARKER) == fight.Marks(1000, True, True))
check("otherwise neither", fight.counter_marks(record_start(), MARKER) == fight.Marks(1000, False, False))
check("a fighter taking a throw is marked thrown, as Ryu's throws set -2 (2026-10-04)",
      fight.counter_marks(record_start(kind=-2, health=870), MARKER) == fight.Marks(870, False, False, True))
check("a strike of any kind is not a throw",
      not any(fight.counter_marks(record_start(kind=k), MARKER).thrown for k in (0, 1, 2)))
check("the combo count is read, 2 for Zeku's V-Trigger's second hit (2026-10-04)",
      fight.counter_marks(record_start(combo=2), MARKER).combo == 2
      and fight.counter_marks(record_start(), MARKER).combo == 0)
check("memory that is no longer a record, or too little of it, is no reading",
      fight.counter_marks(record_start(1, marker=MARKER + 8), MARKER) is None
      and fight.counter_marks(record_start(1)[:-1], MARKER) is None and fight.counter_marks(None, MARKER) is None)

# Crossups, from where the fighters were as hits landed on 2026-09-30: Ken
# hit by Akuma, Ken's yaw -90 facing towards +X and +90 towards -X.
landed = [  # (Akuma's X on the hit's frame less Ken's before it, Ken's yaw, a crossup by the banner)
    (-11.4, -90, True), (11.4, 90, True), (46.6, 90, True), (4.5, 90, True),
    (50.0, -90, False), (1.1, -90, False), (-34.1, 90, False), (-10.2, 90, False),
    (0.0, 90, True), (0.0, -90, True),     # in the corner, level at the wall
]
check("a hit landing level with the defender, or from the side they face away from, is a crossup",
      all(fight.behind(146 + rel, 146, yaw) == crossup for rel, yaw, crossup in landed),
      repr([fight.behind(146 + rel, 146, yaw) for rel, yaw, _c in landed]))
# Corner hit 2: both at the wall before the hit; on its frame Ken's model is
# jolted 2.5 back to 752.5, which judged on its own would put Akuma in front.
before_hit = [(750.0, 90.0), (750.0, 90.0)]          # player 1 Akuma, player 2 Ken
on_hit = [(750.0, 90.0), (752.5, 90.0)]
check("a hit is judged by the defender's place before it and the attacker's on it",
      fight.crossup(1, before_hit, on_hit) and not fight.behind(750.0, 752.5, 90.0))
# Akuma's forward throw, as recorded: Ken turned round 0.42 s before its
# damage, and then by place alone Akuma is behind him.
turns = fight.Turns()
turns.update([(-143.0, 90.0), (4.9, 90.0)], 0.0)
turns.update([(28.2, 90.0), (110.6, -90.0)], 0.6)          # the throw turns Ken
check("a defender turned round just before a hit, as by a throw, is not steady",
      not turns.steady(1, 1.02) and turns.steady(0, 1.02))
check("one who has faced the same way for long enough is", turns.steady(1, 1.6))
check("nothing to go on is no turn", fight.Turns().steady(0, 0.0))
check("without both readings there is no crossup",
      not fight.crossup(1, None, on_hit) and not fight.crossup(1, before_hit, None))

# Story mode's fights leave the settings' characters empty; the names over the
# health bars settle it, as against Nash on 2026-10-04 (records NSH and VEM).
check("a fighter's name gives their code", fight.name_code("NASH") == b"NSH" and fight.name_code("Rank 6398") is None
      and fight.name_code(None) is None)
story_records = [0x2000, 0x1000]
story_codes = {0x2000: b"VEM", 0x1000: b"NSH"}
check("the opponent named on the right puts the other record first",
      fight.order_by_character(story_records, story_codes, [None, fight.name_code("NASH")]) == [0x2000, 0x1000])

print()
print("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
