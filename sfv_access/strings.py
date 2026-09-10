"""Correcting recognised text against the game's own words.

Every mistake the pixel reader makes is a string that does not exist in the
game: "RANKED MAT H", "BAÜLE LOUNGE", "CASUAL MATC". The right answer is
sitting in the localisation table recovered from the pak files, so recognised
text can be snapped to the nearest string the game can actually display.

Matching every line against fifty thousand strings one at a time is far too
slow to do while narrating a menu. Instead each string is indexed by the
three-character runs it contains, so a query only has to be compared against
the handful of entries that share several of its runs. That turns a search of
the whole table into a search of a few dozen candidates.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

STRINGS_FILE = Path(__file__).resolve().parent.parent / "strings.json"

_WHITESPACE = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Upper case for comparison, without letting the length change.

    A few characters grow when upper cased, and the German sharp s is the one
    recognition produces: it becomes two letters, so a misread stage name came
    out one character longer than it looked and scored 0.769 against a
    threshold of 0.78. "Ring of Power" was sitting right there and was refused
    over four thousandths. Similarity is measured on length, so a character
    that changes it distorts every comparison it appears in.
    """
    text = _WHITESPACE.sub(" ", text).strip()
    return "".join(c if len(c.upper()) != 1 else c.upper() for c in text)


def _numbers(text: str) -> tuple[str, ...]:
    """Numbers that stand on their own, ignoring digits stuck inside words.

    A correction must not throw away a reading: "Temperature 800 F" otherwise
    matches the bare word "Temperature" closely enough to win, and the value is
    silently lost. But recognition also drops digits into the middle of words,
    turning "Area" into "A7ea", and refusing to correct those would be worse
    than the mistake. So only whole numeric words count.

    See `_keeps_numbers` for what is then done with them.
    """
    out = []
    for token in re.split(r"[^0-9A-Za-z:.]+", text):
        stripped = token.strip(":.")
        if stripped and all(c.isdigit() or c in ":." for c in token):
            out.append(token)
    return tuple(out)


def _keeps_numbers(query: tuple[str, ...], candidate: tuple[str, ...]) -> bool:
    """Whether a candidate keeps every number the reading found.

    What has to be prevented is a correction that discards a number, because
    that silently throws the value away: "Temperature 800 F" matches the bare
    word "Temperature" closely enough to win otherwise.

    A candidate carrying a number the reading missed is the opposite case, and
    demanding the two agree exactly used to block it. Recognition reads the
    digit one as a letter often enough that "PLAYER 1 VS PLAYER 2" came back as
    "PLAYER I VS PLAYER 2" and could not be repaired, because the reading had
    lost a number rather than gained one. Restoring it is the whole point.
    """
    remaining = list(candidate)
    for number in query:
        if number not in remaining:
            return False
        remaining.remove(number)
    return True


def trigrams(text: str) -> set[str]:
    padded = f"  {text} "
    return {padded[i : i + 3] for i in range(len(padded) - 2)}


@dataclass(frozen=True)
class Match:
    text: str
    score: float
    changed: bool


class Vocabulary:
    """The strings the game can display, searchable by approximate match."""

    def __init__(self, entries: list[str]) -> None:
        self.entries = entries
        self.normalised = [normalise(e) for e in entries]
        self.exact = {n: e for n, e in zip(self.normalised, entries)}
        self.index: dict[str, list[int]] = {}
        for i, text in enumerate(self.normalised):
            for gram in trigrams(text):
                self.index.setdefault(gram, []).append(i)

    @classmethod
    def load(cls, path: Path = STRINGS_FILE, max_length: int = 200) -> "Vocabulary | None":
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))["strings"]
        except Exception:
            return None
        seen: dict[str, str] = {}
        for value in data.values():
            text = value.strip()
            if not text or len(text) > max_length:
                continue
            # One line at a time; the reader never sees a paragraph as a unit.
            for line in text.splitlines():
                line = line.strip()
                if len(line) >= 2:
                    seen.setdefault(normalise(line), line)
        return cls(list(seen.values()))

    def correct(
        self, text: str, min_score: float = 0.78, candidates: int = 40
    ) -> Match:
        """The closest string the game contains, or the text unchanged.

        Refuses to guess at anything too short to be distinctive, and at
        anything it cannot match closely, so a player name or an unfamiliar
        word is left alone rather than rewritten into something wrong.
        """
        query = normalise(text)
        if len(query) < 3:
            return Match(text, 1.0, False)
        if query in self.exact:
            return Match(self.exact[query], 1.0, self.exact[query] != text)

        counts: dict[int, int] = {}
        for gram in trigrams(query):
            for i in self.index.get(gram, ()):
                counts[i] = counts.get(i, 0) + 1
        if not counts:
            return Match(text, 0.0, False)

        # Length is a cheap sanity filter: a correction should be about as long
        # as what was read, not a different string that happens to share runs.
        best_ids = sorted(counts, key=lambda i: -counts[i])[: candidates * 4]
        best_ids = [
            i for i in best_ids if 0.6 <= len(self.normalised[i]) / len(query) <= 1.7
        ][:candidates]

        numbers = _numbers(query)
        best_text, best_score = text, 0.0
        for i in best_ids:
            if numbers and not _keeps_numbers(numbers, _numbers(self.normalised[i])):
                continue
            score = SequenceMatcher(None, query, self.normalised[i]).ratio()
            if score > best_score:
                best_text, best_score = self.entries[i], score

        if best_score >= min_score:
            return Match(best_text, best_score, normalise(best_text) != query)
        return Match(text, best_score, False)


_shared: Vocabulary | None = None
_loaded = False


def shared() -> Vocabulary | None:
    global _shared, _loaded
    if not _loaded:
        _shared = Vocabulary.load()
        _loaded = True
    return _shared
