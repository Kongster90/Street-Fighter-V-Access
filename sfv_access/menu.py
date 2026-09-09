"""Working out which menu entry is highlighted.

Every menu in Street Fighter V marks the current entry the same way: the text
is redrawn in gold, close to RGB 255, 227, 140, against a near black bar, while
every other entry is dark text on a light background.  Measured across the main
menu, the story, versus, challenges and settings submenus and the training
pause menu, the gold is identical each time, which makes it a far more reliable
cue than trying to compare font sizes or guess at layout.

Finding the gold rows is a handful of array operations, so the highlight can be
tracked several times a second and only the small strip around it needs to go
through text recognition.  That is what makes live menu narration affordable.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# The header strip carries the player name, coin count and league points; the
# footer carries the description of whatever is highlighted. Neither holds
# selectable entries, so both are kept out of highlight detection.
HEADER_BOTTOM = 118
FOOTER_TOP = 925

GOLD = (255, 227, 140)


@dataclass(frozen=True)
class Band:
    """A run of rows containing gold text."""

    top: int
    bottom: int
    left: int
    right: int
    pixels: int

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def density(self) -> float:
        """Share of the band's area that is gold.

        Glyphs cover a small fraction of their box.  A solid gold element, such
        as a health bar or a border, covers nearly all of it, and that gap is
        what keeps bars from being mistaken for highlighted text.
        """
        area = max(1, self.height * self.width)
        return self.pixels / area


def gold_mask(rgb: np.ndarray) -> np.ndarray:
    """Pixels close to the exact gold the game uses for the highlighted entry.

    A loose yellow test is not enough. The parchment map behind several menus
    and the cream date and time in the corner both drift into wide yellow
    ranges, so the match is kept tight around the measured colour.
    """
    r = rgb[..., 0].astype(np.int16)
    g = rgb[..., 1].astype(np.int16)
    b = rgb[..., 2].astype(np.int16)
    return (
        (abs(r - GOLD[0]) <= 26)
        & (abs(g - GOLD[1]) <= 30)
        & (abs(b - GOLD[2]) <= 40)
        & ((r - b) > 70)
        & ((g - b) > 45)
    )


def gold_bands(
    rgb: np.ndarray,
    y_min: int = HEADER_BOTTOM,
    y_max: int = FOOTER_TOP,
    step: int = 2,
    min_rows: int = 7,
    min_row_pixels: int = 10,
    max_density: float = 0.62,
    dark_below: int = 105,
    # Measured across every captured screen. This was 0.45 while a run of rows
    # could stretch across the whole width, which put Battle Settings just out
    # of reach. Now that bands are separated horizontally the surrounding
    # measurement is local to the entry, so a lower bar reaches it without
    # letting artwork through; the screens test covers both directions.
    dark_fraction: float = 0.32,
) -> list[Band]:
    """Row runs of gold text that sit on the dark bar of a highlighted entry.

    Requiring the dark bar as well as the gold does two jobs: it rejects gold
    that belongs to artwork or to a health bar, and it stops one run from
    swallowing the whole list, because the light rows between entries fail the
    test and break the run.

    The work is done on a subsampled view of the content area only. Highlight
    glyph strokes survive halving comfortably, and the saving is what brings a
    full-frame scan down to a few milliseconds so it can be polled.
    """
    view = rgb[y_min:y_max:step, ::step]
    mask = gold_mask(view)
    # Brightest channel is a cheaper stand-in for luminance, and the dark bar
    # is dark in every channel, so nothing is lost.
    dark = view.max(axis=2) < dark_below

    vh, vw = mask.shape
    row_floor = max(3, min_row_pixels // step)
    margin = max(1, 60 // step)

    per_row = mask.sum(axis=1)
    hot = np.zeros(vh, dtype=bool)
    for y in np.flatnonzero(per_row >= row_floor):
        cols = np.flatnonzero(mask[y])
        span = int(cols[-1]) - int(cols[0]) + 1
        # A highlighted row is bordered above and below by solid gold rules,
        # and those rules are far wider than the lettering they frame. Left in,
        # they outweigh the text and drag the band across the whole screen.
        # Glyphs cover a fraction of the line they sit on; a rule covers all of
        # it, so coverage tells the two apart.
        if span >= 200 and per_row[y] / span > 0.8:
            continue
        lo = max(0, int(cols[0]) - margin)
        hi = min(vw, int(cols[-1]) + margin + 1)
        hot[y] = dark[y, lo:hi].mean() >= dark_fraction

    bands: list[Band] = []
    start = None
    for y in range(vh):
        if hot[y] and start is None:
            start = y
        elif not hot[y] and start is not None:
            bands.extend(_split_row_run(mask, start, y, y_min, step))
            start = None
    if start is not None:
        bands.extend(_split_row_run(mask, start, vh, y_min, step))

    return [
        b
        for b in bands
        if b.height >= min_rows and b.width >= 20 and b.density <= max_density
    ]


def _split_row_run(
    mask: np.ndarray, top: int, bottom: int, y_min: int, step: int, gap: int = 30
) -> list[Band]:
    """Break a run of rows into separate bands where gold appears side by side.

    Settings screens put a list on the left and a panel on the right, and the
    highlighted entry in each sits at the same height. Treating a run of rows
    as one band merges the two into something spanning the whole screen, whose
    recognised text is both entries run together. Splitting on horizontal gaps
    keeps them apart.
    """
    sub = mask[top:bottom]
    columns = np.flatnonzero(sub.any(axis=0))
    if columns.size == 0:
        return []

    groups: list[list[int]] = [[int(columns[0])]]
    for c in columns[1:]:
        if int(c) - groups[-1][-1] > gap:
            groups.append([int(c)])
        else:
            groups[-1].append(int(c))

    out = []
    for group in groups:
        lo, hi = group[0], group[-1] + 1
        out.append(
            Band(
                top=y_min + top * step,
                bottom=y_min + bottom * step,
                left=lo * step,
                right=hi * step,
                # Scaled back up so density stays comparable with full resolution.
                pixels=int(sub[:, lo:hi].sum()) * step * step,
            )
        )
    return out


# Gold frames and rules run along the edges of these screens and carry far
# more gold than any lettering does. Menu text never sits this close to the
# edge, so distance from it is a cheap way to discard the decoration.
EDGE_MARGIN = 140


def highlight_band(rgb: np.ndarray, bgra: np.ndarray | None = None) -> Band | None:
    """The band most likely to be the highlighted entry.

    Picking the largest patch of gold is not enough on the settings screens:
    the panel's own gold frame outweighs the words inside it. Where the image
    is available the candidates are read instead, and only ones that yield
    actual text are considered, which settles it whatever the decoration does.

    Where several entries are highlighted at once, the rightmost wins. The
    settings screens keep a list of pages on the left and the open page on the
    right, both showing a highlight, and the one being moved is the right one.
    """
    width = rgb.shape[1]
    bands = [
        b
        for b in gold_bands(rgb)
        if b.left >= EDGE_MARGIN and b.right <= width - EDGE_MARGIN
    ]
    if not bands:
        return None
    if bgra is None:
        return max(bands, key=lambda b: b.pixels)

    from . import ocr as _ocr

    with_text = []
    for band in sorted(bands, key=lambda b: -b.pixels)[:6]:
        items = _ocr.read(strip(bgra, band))
        text = " ".join(i.text for i in items).strip()
        if len(text) >= 2 and any(c.isalpha() for c in text):
            with_text.append(band)
    if not with_text:
        return max(bands, key=lambda b: b.pixels)

    return _pick_highlight(with_text)


def highlight_group(rgb: np.ndarray, bgra: np.ndarray) -> list[Band]:
    """Every gold band belonging to the highlighted entry, left to right.

    A settings row highlights its label and its value separately, so the value
    arrives as its own band. That is how a volume level is read: recognition
    misses the number when the whole frame is processed at once, but the band
    around it on its own comes back cleanly.
    """
    width = rgb.shape[1]
    bands = [
        b
        for b in gold_bands(rgb)
        if b.left >= EDGE_MARGIN and b.right <= width - EDGE_MARGIN
    ]
    if not bands:
        return []

    from . import ocr as _ocr

    with_text = []
    for band in sorted(bands, key=lambda b: -b.pixels)[:6]:
        items = _ocr.read(strip(bgra, band))
        text = " ".join(i.text for i in items).strip()
        if len(text) >= 1 and any(c.isalnum() for c in text):
            with_text.append(band)
    if not with_text:
        return []

    chosen = _pick_highlight(with_text)
    middle = (chosen.top + chosen.bottom) // 2
    # Only bands that read as something. Including blank ones as well, to try
    # to catch a volume level, made the main menu announce its entry twice:
    # the artwork beside a tile became a second band and read as the tile name
    # again.
    same_row = [
        b for b in with_text if abs((b.top + b.bottom) // 2 - middle) <= 20
    ]
    return sorted(same_row, key=lambda b: b.left)


# The drawn level bar on the settings panels, measured from 1920 by 1080
# captures: ten equal cells, with the number printed to their right.
BAR_CELLS = 10
BAR_LEFT, BAR_RIGHT = 1253, 1392
BAR_REFERENCE = 1150, 1240  # a patch of plain row beside it, for comparison


def volume_level(rgb: np.ndarray, top: int, bottom: int) -> int | None:
    """How many cells of a drawn level bar are filled, or None if there is none.

    Reading the printed number fails on the highlighted row, where it is small,
    gold on black, and sits in the same band as the bar itself. The bar is far
    easier: ten cells, filled from the left.

    Which way round they are depends on the row. On an ordinary row the panel
    is pale and a filled cell is dark; on the highlighted row the bar is black
    and a filled cell is bright. Measuring each cell's distance from the
    background of its own row covers both without knowing which applies.
    """
    height, width = rgb.shape[:2]
    sx, sy = width / 1920, height / 1080
    y0 = int(top + 2 * sy)
    y1 = int(min(height, top + 20 * sy))
    x0, x1 = int(BAR_LEFT * sx), int(BAR_RIGHT * sx)
    r0, r1 = int(BAR_REFERENCE[0] * sx), int(BAR_REFERENCE[1] * sx)
    if y1 - y0 < 6 or x1 - x0 < BAR_CELLS * 4 or x1 > width:
        return None

    band = rgb[y0:y1, x0:x1].astype(np.float32).mean(axis=2)
    background = float(np.median(rgb[y0:y1, r0:r1].astype(np.float32).mean(axis=2)))

    # The cells form a staircase, so only their lower part is present in all
    # ten; measuring the bottom rows compares like with like.
    cells = np.array_split(band, BAR_CELLS, axis=1)
    scores = [float(np.abs(c[-8:] - background).mean()) for c in cells]

    peak = max(scores)
    if peak < 60:
        return None  # nothing drawn here, so this row has no bar

    filled = [s >= peak * 0.45 for s in scores]
    # A level fills from the left. Anything else, such as a word sitting in a
    # pill across the middle of the row, is not a bar and must not be reported.
    count = sum(filled)
    if filled != [True] * count + [False] * (BAR_CELLS - count):
        return None
    return count


def value_from_group(bgra: np.ndarray, group: list[Band]) -> str:
    """The value sitting to the right of the label on a highlighted row."""
    if len(group) < 2:
        return ""

    from . import ocr as _ocr

    for band in sorted(group[1:], key=lambda b: -b.left):
        for image in _value_views(bgra, band):
            items = _ocr.read(image)
            text = " ".join(i.text for i in items).strip()
            text = "".join(c for c in text if c.isalnum() or c in " .-/%").strip()
            if not (1 <= len(text) <= 24):
                continue
            if sum(c.isalnum() for c in text) >= max(1, len(text) - 2):
                return text
    return ""


def _value_views(bgra: np.ndarray, band: Band, pad: int = 16):
    """The band, then just its right-hand end, plain and brightened.

    A volume row's highlighted value covers the drawn bar and the number
    together, and recognition makes nothing of the pair. The number sits at the
    right end, so looking there alone, with the brightness stretched the way
    the gold-on-black lettering needs, is what brings the level back.
    """
    from . import ocr as _ocr

    yield strip(bgra, band)

    width = band.right - band.left
    if width < 60:
        return
    left = max(0, band.right - int(width * 0.45) - pad)
    right = min(bgra.shape[1], band.right + pad)
    top = max(0, band.top - pad)
    bottom = min(bgra.shape[0], band.bottom + pad)
    tail = np.ascontiguousarray(bgra[top:bottom, left:right])
    yield _ocr.boost(tail)
    yield tail


def _pick_highlight(bands: list[Band], group_gap: int = 40) -> Band:
    """Choose between several highlighted things on one screen.

    Two quite different situations produce more than one band, and they want
    opposite answers.

    A settings screen highlights the page in its left-hand list and the row
    being changed in the panel beside it. The panel is where the cursor is, and
    it sits further right, so the rightmost group wins.

    A single highlighted entry can also span several lines: an arcade path
    shows its title, its number of battles and its best score, all gold, all
    part of one tile. Those want the title, not the last line of it.

    Grouping bands that sit close together vertically separates the two cases.
    Within a group the topmost and leftmost band is the label; between groups
    the one furthest right is the live one.
    """
    ordered = sorted(bands, key=lambda b: b.top)
    groups: list[list[Band]] = [[ordered[0]]]
    for band in ordered[1:]:
        if band.top - max(b.bottom for b in groups[-1]) <= group_gap:
            groups[-1].append(band)
        else:
            groups.append([band])

    chosen = max(groups, key=lambda g: min(b.left for b in g))
    return min(chosen, key=lambda b: (b.top, b.left))


def bar_extent(
    rgb: np.ndarray, top: int, bottom: int, left: int, right: int, dark_below: int = 105
) -> tuple[int, int]:
    """How far the dark bar behind an entry reaches, left and right."""
    height, width = rgb.shape[:2]
    y = min(height - 1, max(0, (top + bottom) // 2))
    row = rgb[y].max(axis=1) < dark_below

    lo = max(0, min(width - 1, left))
    hi = max(0, min(width - 1, right - 1))
    while lo > 0 and row[lo - 1]:
        lo -= 1
    while hi < width - 1 and row[hi + 1]:
        hi += 1
    return lo, hi


def bar_width(rgb: np.ndarray, band: Band, dark_below: int = 105) -> int:
    """How wide the dark bar behind an entry runs.

    A settings page highlights both the page in its left-hand list and the row
    being changed in the panel. The panel's bar spans most of the screen while
    the list item's is a few hundred pixels, so this separates the entry the
    cursor is on from the one merely showing where you are.
    """
    lo, hi = bar_extent(rgb, band.top, band.bottom, band.left, band.right, dark_below)
    return hi - lo


def selected_index(items, band: Band) -> int | None:
    """Which recognised line sits inside `band`.

    Overlap has to be measured in both directions. A settings row holds its
    label and its value at the same height, so matching on height alone picks
    between them at random; the gold covers the label, so the larger overlap
    is the right answer.
    """
    if band is None:
        return None

    best, best_area = None, 0
    for i, it in enumerate(items):
        ox = min(it.x + it.w, band.right) - max(it.x, band.left)
        oy = min(it.y + it.h, band.bottom) - max(it.y, band.top)
        area = max(0, ox) * max(0, oy)
        if area > best_area:
            best, best_area = i, area
    if best is not None:
        return best

    # Nothing overlapped, so fall back to whatever shares the band's height.
    centre = (band.top + band.bottom) / 2
    best, best_gap = None, 1e9
    for i, it in enumerate(items):
        if it.y - 6 <= centre <= it.y + it.h + 6 and abs(it.cy - centre) < best_gap:
            best, best_gap = i, abs(it.cy - centre)
    return best


def value_on_bar(
    rgb: np.ndarray,
    items,
    idx: int,
    row_tolerance: float = 16.0,
    bgra: np.ndarray | None = None,
) -> str:
    """The setting value paired with the highlighted label.

    A value belongs to a label when it sits on the same highlighted bar. That
    is what separates a settings row, where the label and its value share one
    long bar, from a grid of menu tiles, where two entries on the same line sit
    on bars of their own with a gap between them.

    Volume rows carry a drawn bar as well as a number, and the drawn bar comes
    back from recognition as nonsense, so the rightmost sensible-looking item
    on the row is taken rather than the first.
    """
    if idx is None or idx >= len(items):
        return ""
    base = items[idx]
    lo, hi = bar_extent(
        rgb, int(base.y), int(base.y + base.h), int(base.x), int(base.x + base.w)
    )
    if hi - lo < base.w + 40:
        return ""  # no bar wider than the label itself, so nothing is paired

    on_row = [
        it
        for j, it in enumerate(items)
        if j != idx
        and abs(it.cy - base.cy) <= row_tolerance
        and it.x > base.x + base.w
        and it.x + it.w <= hi + 8
    ]
    for it in sorted(on_row, key=lambda t: -t.x):
        text = it.text.strip()
        if not (1 <= len(text) <= 24):
            continue
        letters = sum(c.isalnum() for c in text)
        if letters >= max(1, len(text) - 2):
            return text

    if bgra is not None:
        return _value_by_second_look(bgra, base, lo, hi)
    return ""


def _value_by_second_look(bgra: np.ndarray, base, lo: int, hi: int) -> str:
    """Read the right-hand end of a highlighted row again, harder.

    A volume row carries a drawn bar and a number. On every row but the
    highlighted one the number reads fine, but on the highlighted one it is
    gold on black and small, and the first pass misses it entirely, so the
    setting is announced with no value at all. Stretching the brightness the
    way the character names needed brings it back.
    """
    from . import ocr as _ocr

    top = int(max(0, base.y - 8))
    bottom = int(min(bgra.shape[0], base.y + base.h + 8))
    # Everything to the right of the label, out to the end of its bar. The
    # number sits at the far end, past the drawn bar, so the rightmost thing
    # that reads as a value is the one wanted.
    left = int(min(bgra.shape[1] - 1, base.x + base.w + 10))
    right = int(min(bgra.shape[1], hi + 8))
    if right - left < 20 or bottom - top < 8:
        return ""

    region = np.ascontiguousarray(bgra[top:bottom, left:right])
    for image in (_ocr.boost(region), region):
        items = _ocr.read(image)
        for it in sorted(items, key=lambda t: -t.x):
            text = it.text.strip()
            if 1 <= len(text) <= 12 and any(c.isalnum() for c in text):
                if sum(c.isalnum() for c in text) >= max(1, len(text) - 1):
                    return text
    return ""


def value_for(items, idx: int, row_tolerance: float = 14.0) -> str:
    """The setting value paired with the highlighted label, if there is one.

    Screens like the pause menu and battle settings put a label on the left and
    its current value in a column on the right, and that value is the whole
    point of the row. Grid menus also place entries side by side, so a screen
    only counts as a settings list when its rows hold at most two entries and
    the right-hand ones line up into a column.
    """
    if idx is None or idx >= len(items):
        return ""

    rows: dict[int, list] = {}
    for it in items:
        key = min(rows, key=lambda k: abs(k - it.cy), default=None)
        if key is not None and abs(key - it.cy) <= row_tolerance:
            rows[key].append(it)
        else:
            rows[int(it.cy)] = [it]

    if any(len(r) > 2 for r in rows.values()):
        return ""  # three across means a grid of entries, not label and value

    pairs = [sorted(r, key=lambda t: t.x) for r in rows.values() if len(r) == 2]
    if len(pairs) < 3:
        return ""

    # Take the largest cluster of aligned right-hand entries rather than the
    # full spread. The pause menu draws both player names on one line above the
    # settings, and that pair would otherwise hide the real value column.
    lefts = sorted(p[1].x for p in pairs)
    span, best_lo, best_n = 40.0, None, 0
    for lo in lefts:
        n = sum(1 for x in lefts if lo <= x <= lo + span)
        if n > best_n:
            best_lo, best_n = lo, n
    if best_n < 3:
        return ""

    base = items[idx]
    for left, right in pairs:
        if left is base and best_lo <= right.x <= best_lo + span:
            return right.text
    return ""


def split_chrome(items):
    """Separate the persistent header and footer from the actual page content."""
    header = [it for it in items if it.cy < HEADER_BOTTOM]
    footer = [it for it in items if it.cy >= FOOTER_TOP]
    body = [it for it in items if HEADER_BOTTOM <= it.cy < FOOTER_TOP]
    return header, body, footer


def strip(image: np.ndarray, band: Band, pad: int = 16) -> np.ndarray:
    """The highlighted band plus margin, ready for text recognition.

    Recognition needs whitespace around the glyphs; cropping to the exact gold
    extent makes short words such as "Trials" come back empty.
    """
    h, w = image.shape[:2]
    y0, y1 = max(0, band.top - pad), min(h, band.bottom + pad)
    x0, x1 = max(0, band.left - pad), min(w, band.right + pad)
    return np.ascontiguousarray(image[y0:y1, x0:x1])


def description(footer_items) -> str:
    """The help line for the highlighted entry, which sits along the bottom."""
    if not footer_items:
        return ""
    # The description is the widest thing down there; the rest is status chrome.
    return max(footer_items, key=lambda it: it.w).text
