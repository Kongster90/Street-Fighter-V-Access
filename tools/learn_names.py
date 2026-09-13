"""Build the character code to display name mapping.

The display names live in the localisation table, which ships encrypted, so
they cannot be read out of the game files. But the game shows the name on
screen while memory reports the code, so pairing the two builds the table.

Getting that pairing right took three attempts, and the failures are the
interesting part.

The preview models carry no player number, and the order they appear in the
object list has nothing to do with which side they stand on, so the first
version matched every code against the other fighter's name. Ordering by world
position fixed the stability but not the question of which end is player one,
and guessing that from the roster's initials was still wrong often enough to
poison the table.

So this version assumes nothing about sides. It watches for change instead:
move the cursor and exactly one code changes in memory while exactly one name
changes on screen, and those two must belong to each other. That establishes
the link with no geometry involved, and the link then drives everything else.

Two rules catch mistakes that would otherwise pass silently. A display name
belongs to exactly one character, so a name already spoken for is refused
rather than reassigned. And most codes are initials of the name, so KEN, CMY
and RSD line up with KEN, CAMMY and RASHID; when a code is alphabetic and does
not line up, the pairing is rejected.

Everything is spoken, because this runs with the game in front.

    python tools/learn_names.py

Hover from character to character. Alt J stops; the table saves as it
goes, and every observation is logged to snapshots/learn-log.txt for diagnosis.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sfv_access import game, live, ocr  # noqa: E402
from sfv_access.capture import Capture  # noqa: E402
from sfv_access.hotkeys import Hotkeys  # noqa: E402
from sfv_access.speech import Speaker  # noqa: E402

LOG = ROOT / "snapshots" / "learn-log.txt"

# The two large names on character select, measured from a 1920x1080 capture.
NAME_REGIONS = {
    "left": (110, 610, 720, 725),
    "right": (1330, 610, 1910, 725),
}

# The displayed name and the preview model update at different moments while
# the cursor moves, so during the gap a wrong pairing can sit still and look
# settled. Two agreeing reads was only 0.6 seconds of stability and let four
# characters be learned wrongly. Four reads outlasts the gap.
CONFIRMATIONS = 4
PAIR_WINDOW = 2.0      # seconds within which a code change and a name change link up


def looks_like_a_name(text: str) -> bool:
    """Reject anything that is plainly not a character name.

    The costume panel opens over the left name and puts a sentence of help text
    in the same place. Real names are short and set in capitals, and one of them
    is simply "G".
    """
    if not (1 <= len(text) <= 16):
        return False
    letters = [c for c in text if c.isalpha()]
    if not letters or text.count(" ") > 2:
        return False
    return sum(c.isupper() for c in letters) >= len(letters) * 0.8


def tidy(text: str) -> str:
    return "".join(ch for ch in text if ch.isalnum() or ch in " .-&").strip()


def best_in(items, box) -> str:
    left, top, right, bottom = box
    inside = [it for it in items if left <= it.cx <= right and top <= it.cy <= bottom]
    if not inside:
        return ""
    return tidy(max(inside, key=lambda t: t.h).text)


def names_on_screen(bgra) -> dict[str, tuple[str, bool]]:
    """Both displayed names, with a flag for how much to trust each.

    The frame is read twice, once as captured and once with the brightness
    stretched so pale lettering separates from the artwork behind it. The
    stretched pass is far better on the left-hand name, which was the one
    coming back garbled or empty. When both passes agree the reading is treated
    as confident and counts double towards confirmation, which lets clean names
    be learned quickly while doubtful ones still have to prove themselves.
    """
    out: dict[str, tuple[str, bool]] = {}
    if bgra is None:
        return out
    plain_items = ocr.read(bgra)
    boosted_items = ocr.read(ocr.boost(bgra))
    for region, box in NAME_REGIONS.items():
        plain = best_in(plain_items, box)
        boosted = best_in(boosted_items, box)
        chosen = boosted or plain
        if not looks_like_a_name(chosen):
            continue
        out[region] = (chosen, bool(plain) and plain == boosted)
    return out


def load_vocabulary() -> set[str]:
    """Every short string the game itself can display.

    Recovered from the localisation table once the pak key was found, so a
    candidate name can be checked against the game's own words rather than only
    against its own consistency. A misreading such as ZEW, ROS or PO SO simply
    is not in here, which is a far blunter instrument than any of the shape
    rules and catches things they never would.
    """
    path = ROOT / "strings.json"
    if not path.exists():
        print("[names] strings.json missing; the game's own word list is not in use")
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))["strings"]
    except Exception as exc:
        print(f"[names] could not read strings.json: {exc}")
        return set()
    return {
        v.strip().upper()
        for v in data.values()
        if v.strip() and "\n" not in v and len(v.strip()) <= 24
    }


class Learner:
    def __init__(self, speech: Speaker) -> None:
        self.speech = speech
        self.vocabulary = load_vocabulary()
        data = live.load_name_file()
        self.names: dict[str, str] = data["names"]
        self.player_one_side: str = data["player_one_side"]
        self.by_name = {v: k for k, v in self.names.items()}

        # Restore the side link from a previous session rather than waiting for
        # a cursor move to re-derive it. Player one is the fighter shown on the
        # left, so the stored side tells us the whole mapping.
        self.link: dict[str, str] = {}      # side key -> screen region
        if self.player_one_side in ("neg", "pos"):
            other = "pos" if self.player_one_side == "neg" else "neg"
            self.link = {self.player_one_side: "left", other: "right"}
        self.seeded = False
        self.prev_codes: dict[str, str] = {}
        self.prev_names: dict[str, str] = {}
        self.code_events: list[tuple[float, str, str]] = []
        self.name_events: list[tuple[float, str, str]] = []
        self.pending: dict[str, tuple[str, int]] = {}
        self.rejected: set[tuple[str, str]] = set()
        self.first_seen: dict[str, float] = {}
        self.gave_up: set[str] = set()
        self.conflicts: dict[str, tuple[str, str]] = {}
        self.log = LOG.open("a", encoding="utf-8")
        self.log.write(f"\n=== session {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")

    # ------------------------------------------------------------------ links
    def observe(self, codes: dict[str, str], shown: dict[str, str]) -> None:
        now = time.time()

        # Only the text matters for spotting a change; how confident the
        # reading was matters later, when deciding what to believe.
        texts = {
            region: (entry[0] if isinstance(entry, tuple) else entry)
            for region, entry in shown.items()
        }

        # The first look is not a change. Recording it as one puts an event on
        # both sides at once, and while those sit in the window nothing can be
        # linked, because linking needs exactly one change on each side.
        if not self.seeded:
            self.prev_codes.update(codes)
            self.prev_names.update(texts)
            self.seeded = True
            return

        for side, code in codes.items():
            was = self.prev_codes.get(side)
            if was != code:
                self.code_events.append((now, side, was, code))
                self.prev_codes[side] = code
        for region, text in texts.items():
            was = self.prev_names.get(region)
            if was != text:
                self.name_events.append((now, region, was, text))
                self.prev_names[region] = text

        self.code_events = [e for e in self.code_events if now - e[0] <= PAIR_WINDOW]
        self.name_events = [e for e in self.name_events if now - e[0] <= PAIR_WINDOW]

        if len(self.link) < 2 and len(self.code_events) == 1 and len(self.name_events) == 1:
            _t, side, old_code, _new_code = self.code_events[0]
            _t2, region, old_name, _new_name = self.name_events[0]
            if side not in self.link and region not in self.link.values():
                self.link[side] = region
                other_side = "pos" if side == "neg" else "neg"
                other_region = "right" if region == "left" else "left"
                self.link[other_side] = other_region
                self.player_one_side = "neg" if self.link["neg"] == "left" else "pos"
                self.save()
                self.log.write(f"link established {self.link}\n")
                self.speech.say("Sides worked out. Keep going.")
                # The character that was showing before the move is now paired
                # too, so it does not need visiting a second time.
                if old_code and old_name:
                    self.try_learn(old_code.upper(), old_name, weight=CONFIRMATIONS)

    # --------------------------------------------------------------- learning
    def consider(self, codes: dict[str, str], shown: dict[str, str]) -> None:
        for side, code in codes.items():
            region = self.link.get(side)
            if region is None:
                continue
            entry = shown.get(region)
            if not entry:
                continue
            text, confident = entry if isinstance(entry, tuple) else (entry, False)
            if not text:
                continue
            self.log.write(
                f"  {side}={code.upper()} {region}={text!r}"
                f"{' agreed' if confident else ''}\n"
            )
            self.try_learn(code.upper(), text, weight=2 if confident else 1)

    def note_stuck(self, codes: dict[str, str], shown: dict[str, str]) -> None:
        """Say something when a new character will not read, rather than sit silent.

        Silence otherwise means two different things, already known and cannot
        be read, and there is no way to tell them apart without seeing the
        screen. Saying so lets you move on instead of hovering hopefully.
        """
        now = time.time()
        for side, code in codes.items():
            code = code.upper()
            if code in self.names or code in self.gave_up:
                self.first_seen.pop(code, None)
                continue
            region = self.link.get(side)
            if region and shown.get(region):
                continue  # a name is readable, so it is being handled
            started = self.first_seen.setdefault(code, now)
            if now - started > 4.0:
                self.gave_up.add(code)
                self.log.write(f"unreadable name for {code}\n")
                self.speech.say("Name not reading here. Try the next one.")

    def try_learn(self, code: str, text: str, weight: int = 1) -> None:
        if self.names.get(code) == text or (code, text) in self.rejected:
            return

        # An entry that is already recorded is never quietly replaced. Four
        # characters were silently overwritten between sessions and their old
        # names vanished from the table, with nothing said about it.
        existing = self.names.get(code)
        if existing is not None:
            if code not in self.conflicts:
                self.conflicts[code] = (existing, text)
                self.log.write(f"CONFLICT {code}: recorded {existing!r}, now reads {text!r}\n")
                print(f"  conflict {code}: recorded {existing}, now reads {text}")
                self.speech.say(f"Conflict on {existing}. Left as it was.")
            return

        # A code that reads as initials of the name is strong evidence; one
        # that plainly does not is a crossed pairing.
        if code.isalpha() and not live.code_matches_name(code, text):
            self.reject(code, text, "code does not match the name")
            return
        # Each display name belongs to exactly one character. This is the rule
        # that would have caught the whole first bad table, where six different
        # codes were all learned as KEN.
        owner = self.by_name.get(text)
        if owner and owner != code:
            self.reject(code, text, f"{text} is already {owner}")
            return
        if self.looks_truncated(text):
            self.reject(code, text, "reads like a partly recognised name")
            return

        # The strongest check available: is this a string the game can actually
        # display? Nothing the recogniser mangles survives it.
        in_vocabulary = text.upper() in self.vocabulary
        if self.vocabulary and not in_vocabulary:
            self.reject(code, text, "not a string the game contains")
            return

        # A name the game vouches for needs less repetition to be believed.
        needed = 2 if in_vocabulary else CONFIRMATIONS
        agreed = self.pending.get(code)
        count = (agreed[1] if agreed and agreed[0] == text else 0) + weight
        if count >= needed:
            self.accept(code, text)
        else:
            self.pending[code] = (text, count)

    def accept(self, code: str, text: str) -> None:
        self.names[code] = text
        self.by_name[text] = code
        self.pending.pop(code, None)
        self.save()
        self.log.write(f"LEARNED {code} -> {text}\n")
        print(f"  learned {code:6s} -> {text}   ({len(self.names)} known)")
        self.speech.say(f"{text}. {len(self.names)} learned.")

    def reject(self, code: str, text: str, why: str) -> None:
        self.rejected.add((code, text))
        self.log.write(f"rejected {code} -> {text}: {why}\n")
        print(f"  rejected {code} -> {text}: {why}")

    def looks_truncated(self, text: str) -> bool:
        """Does this read like a name the recogniser only got part of?

        Two real cases: "ROS" arrived while ROSE was on screen, and "PO SO"
        was POISON with letters dropped. A name that is the beginning of one
        already recorded is the clearest signal; the other is a short name
        broken by a space where the real two-word names all carry a full stop.
        """
        # Partial reads land anywhere in the word, not only at the front: the
        # log shows KEN read as EN, GILL as ILL and AKUMA as KUMA. Anything
        # contained in a name already recorded is treated as a fragment of it.
        # Single letters are exempt, because one fighter is called simply "G".
        if len(text) >= 2:
            for known in self.names.values():
                if known != text and text in known:
                    return True
        if " " in text and "." not in text and len(text.replace(" ", "")) <= 6:
            return True
        return False

    def remaining_text(self) -> str:
        """How many of the game's own character codes are still unnamed.

        Read from roster.json, written by tools/dump_roster.py from the per
        character data assets the game ships. Not every code is a selectable
        fighter, so this is a guide rather than a target to reach.
        """
        try:
            import json

            codes = set(json.loads((ROOT / "roster.json").read_text())["codes"])
        except Exception:
            return ""
        left = len(codes - set(self.names))
        return f", about {left} to go" if left else ""

    def save(self) -> None:
        live.save_name_file(self.names, self.player_one_side)

    def close(self) -> None:
        self.save()
        self.log.close()


def main() -> None:
    speech = Speaker()
    session = live.shared()
    if not session.attach():
        speech.say("Street Fighter 5 is not running.")
        time.sleep(2.5)
        sys.exit(1)

    LOG.parent.mkdir(exist_ok=True)
    learner = Learner(speech)

    stop = threading.Event()
    keys = Hotkeys()
    keys.bind("alt+j", stop.set)
    keys.start()

    speech.say(
        f"Learning character names. {len(learner.names)} known. Bring the game to "
        "the front on character select, then move from one character to the next. "
        "Alt J stops."
    )
    print(f"{len(learner.names)} known. Alt J to stop.")

    cap = Capture()
    warned = False
    last_progress = time.time()

    try:
        while not stop.is_set():
            time.sleep(0.3)

            win = game.find_window()
            if win is None or not win.is_foreground:
                if not warned:
                    speech.say("Bring Street Fighter 5 to the front.")
                    warned = True
                continue
            warned = False

            fighters = session.character_select()
            if len(fighters) < 2:
                continue
            codes = {live.side_key(f.y): f.code.upper() for f in fighters}
            shown = names_on_screen(cap.frame(max_age=0.0))

            learner.note_stuck(codes, shown)
            if not shown:
                continue

            learner.observe(codes, shown)
            learner.consider(codes, shown)

            if time.time() - last_progress > 40:
                if len(learner.link) < 2:
                    speech.say(
                        "Still working out the sides. Move from one character to another.",
                        interrupt=False,
                    )
                else:
                    speech.say(
                        f"{len(learner.names)} learned{learner.remaining_text()}.",
                        interrupt=False,
                    )
                last_progress = time.time()
    except KeyboardInterrupt:
        pass
    finally:
        cap.close()
        keys.stop()
        learner.close()
        note = f", {len(learner.conflicts)} conflicts" if learner.conflicts else ""
        speech.say(f"Stopped. {len(learner.names)} characters saved{note}.")
        print(f"\nsaved {len(learner.names)} names, player one on the {learner.player_one_side} side")
        for code, text in sorted(learner.names.items()):
            print(f"  {code:6s} {text}")
        if learner.conflicts:
            print("\nconflicts, left as they were rather than overwritten:")
            for code, (was, now) in sorted(learner.conflicts.items()):
                print(f"  {code:6s} recorded {was!r}, read {now!r}")
        time.sleep(2.5)


if __name__ == "__main__":
    main()
