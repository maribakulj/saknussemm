"""Slow-path word geometry that keeps what the page already knows. Pixel-blind.

The slow path exists because a correction changed a line's word count. Until
now it answered by discarding every ``String`` box on the line and sharing
the line's width out again in proportion to character count, one glyph = 1,
one space = 0.6. Measured against the producers' own boxes (``hans``, bench
of manufactured merges, three corpora), that puts 79-84 % of word boundaries
inside the true inter-word blank, with a tail out to four characters.

Two things the page knows were being thrown away, and this module keeps
both:

1. **The boxes of the words the correction did not touch.** The rewriter
   already aligns the source Strings onto the corrected words (identity
   follows that alignment). A corrected word matched to a source String of
   compatible length is the same physical word, and its box is exact. Only
   the *runs* the correction changed -- a word split in two, two words
   merged, a word inserted -- need new geometry, and each run is confined
   to the boxes it consumed. Measured with the same bench, confining the
   repair to the touched box alone lifts 79-84 % to 97-99 %.

2. **The widths of letters and of the space, on this page.** Every String
   carries a ``CONTENT`` and a ``WIDTH``; the width of a word is, to a
   first approximation, the sum of the widths of its letters. Hundreds of
   words, one unknown per letter: a least-squares fit, in pure Python, on
   the page being rewritten. The space is the median blank between
   consecutive Strings. Sharing a consumed box out by those weights instead
   of 1 / 0.6 lifts 97-99 % to 98.6-99.8 % and puts the median and the p90
   of the boundary error at zero pixels. On four real pages the learned
   space is 0.9-1.0 of a mean glyph, not 0.6.

What this is NOT: a resolver that looks at the image, or one that can move a
box it was not asked to move. It stays under ``I4`` (the core never opens
an image) and it is validated by ``_geometry_is_usable`` like any other
answer; where it cannot produce a usable layout it says so with ``None``
and the proportional geometry is drawn instead, exactly as before.
"""

from __future__ import annotations

import unicodedata
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from statistics import median

from lxml import etree

from saknussemm.core.alignment import char_similarity
from saknussemm.formats.alto._ns import _int_attr

#: Below this fraction of the page's mean glyph width a learned value is
#: noise; nothing on a printed page is a twentieth of a letter.
_FLOOR = 0.05

#: A page with fewer words than this cannot support a fit; the proportional
#: weights (1 per glyph, 0.6 per space) are used instead.
_MIN_WORDS = 20

#: The per-word constant of the fit. Some producers (ABBYY as exported to
#: DjVu by the Internet Archive) give every word a box that includes the
#: blank after it; without a constant that blank is smeared over the
#: letters and every short word comes out too narrow -- 0.7 character off
#: on most boundaries of the Newton of 1846. With it the fit puts the blank
#: where it is, once per word: 84.6 -> 90.7 % of boundaries within half a
#: character on that book, 81.6 -> 91.0 % on Johnson's dictionary, and no
#: change on producers whose boxes hug the ink (it fits to about zero).
INTERCEPT = ""


def fold_char(char: str) -> str:
    """One character in, one out: case and diacritics folded away.

    ``é`` and ``E`` are drawn with the same body as ``e``; folding them
    together gives each glyph more equations and the fit fewer unknowns.
    """
    base = unicodedata.normalize("NFKD", char.lower())
    return base[0] if base else char


@dataclass(frozen=True)
class WidthModel:
    """Widths per folded character, in the page's own unit (usually px)."""

    glyphs: dict[str, float]
    space: float
    unit: float  # mean glyph width: the value for a glyph never seen

    @classmethod
    def proportional(cls) -> WidthModel:
        """The incumbent's weights: every glyph 1, every space 0.6."""
        return cls(glyphs={}, space=0.6, unit=1.0)

    def glyph(self, char: str) -> float:
        return self.glyphs.get(fold_char(char), self.unit)

    def word(self, text: str) -> float:
        return self.glyphs.get(INTERCEPT, 0.0) + sum(self.glyph(c) for c in text)


def _solve(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting; small dense systems."""
    n = len(rhs)
    m = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[pivot] = m[pivot], m[col]
        p = m[col][col]
        if abs(p) < 1e-12:
            continue
        for r in range(n):
            if r == col:
                continue
            f = m[r][col] / p
            if f:
                for k in range(col, n + 1):
                    m[r][k] -= f * m[col][k]
    return [m[i][n] / m[i][i] if abs(m[i][i]) > 1e-12 else 0.0 for i in range(n)]


def _least_squares(
    chars: list[str], rows: list[tuple[dict[str, int], float]], unit: float
) -> dict[str, float]:
    """Ridge least squares of word width on character counts.

    The ridge is a whisper (1e-6 of the diagonal): it only keeps a glyph
    that occurs in a single word from making the system singular, and
    pulls it toward the mean glyph rather than toward zero.
    """
    index = {c: i for i, c in enumerate(chars)}
    n = len(chars)
    ata = [[0.0] * n for _ in range(n)]
    atb = [0.0] * n
    for counts, width in rows:
        items = [(index[c], k) for c, k in counts.items()]
        for i, ki in items:
            atb[i] += ki * width
            for j, kj in items:
                ata[i][j] += ki * kj
    ridge = 1e-6 * max(1.0, sum(ata[i][i] for i in range(n)) / max(1, n))
    for i in range(n):
        ata[i][i] += ridge
        # an unseen-ish glyph shrinks toward the mean, the constant toward 0
        atb[i] += ridge * (0.0 if chars[i] == INTERCEPT else unit)
    return dict(zip(chars, _solve(ata, atb), strict=True))


def learn_widths(words: Iterable[tuple[str, int]], gaps: Iterable[int]) -> WidthModel:
    """Fit one width per folded character to ``(text, width)`` word boxes.

    Two passes: the first fit finds the words whose box does not add up (a
    heading in a larger corps, a box that swallowed a column, a String
    that is not a word), the second leaves them out. Trimming is by median
    absolute deviation, three sigmas, floored at one pixel: ALTO is
    integer-valued, so nothing under a pixel is an outlier, and a page
    where every box adds up drops nothing.

    ``gaps`` are the blanks between consecutive word boxes on a line -- the
    only place a page shows how wide its space is.
    """
    rows: list[tuple[dict[str, int], float]] = []
    for text, width in words:
        counts: dict[str, int] = defaultdict(int)
        for c in text:
            counts[fold_char(c)] += 1
        if counts and width > 0:
            counts[INTERCEPT] = 1
            rows.append((dict(counts), float(width)))
    blanks = [float(g) for g in gaps]

    total_chars = sum(sum(c.values()) - 1 for c, _ in rows)
    if total_chars == 0:
        return WidthModel.proportional()
    unit = sum(w for _, w in rows) / total_chars
    floor = _FLOOR * unit
    if len(rows) < _MIN_WORDS:
        # too few equations to tell letters apart: the incumbent's weights,
        # but in this page's pixels, so natural widths still mean something
        space = max(floor, median(blanks)) if blanks else 0.6 * unit
        return WidthModel(glyphs={}, space=space, unit=unit)

    chars = sorted({c for counts, _ in rows for c in counts})
    beta = _least_squares(chars, rows, unit)

    residuals = [w - sum(k * beta[c] for c, k in counts.items()) for counts, w in rows]
    centre = median(residuals)
    mad = median(abs(r - centre) for r in residuals)
    cut = max(3 * 1.4826 * mad, 1.0)
    keep = [
        row for row, r in zip(rows, residuals, strict=True) if abs(r - centre) <= cut
    ]
    if len(keep) < len(rows) and len(keep) >= max(_MIN_WORDS, len(chars)):
        kept_chars = sorted({c for counts, _ in keep for c in counts})
        beta.update(_least_squares(kept_chars, keep, unit))

    glyphs = {
        c: (max(0.0, v) if c == INTERCEPT else max(floor, v)) for c, v in beta.items()
    }
    space = max(floor, median(blanks)) if blanks else 0.6 * unit
    return WidthModel(glyphs=glyphs, space=space, unit=unit)


# ---------------------------------------------------------------------------
# The page model, learned once per document
# ---------------------------------------------------------------------------

#: id(root) -> (root, model). The root is kept so the id cannot be recycled
#: under the entry; the dict is bounded so a long run does not accumulate.
_CACHE: dict[int, tuple[etree._Element, WidthModel]] = {}
_CACHE_SIZE = 4


def _local(el: etree._Element) -> str:
    return str(etree.QName(el).localname) if isinstance(el.tag, str) else ""


def page_widths(root: etree._Element) -> WidthModel:
    """The width model of the document ``root`` belongs to, fitted once.

    Every String with a ``CONTENT`` and a positive ``WIDTH`` is an equation;
    every pair of consecutive Strings on a TextLine with geometry gives one
    blank. Namespace-agnostic on purpose: the rewriter serves several ALTO
    versions and one corpus with no namespace at all.
    """
    hit = _CACHE.get(id(root))
    if hit is not None and hit[0] is root:
        return hit[1]

    words: list[tuple[str, int]] = []
    gaps: list[int] = []
    for line in root.iter():
        if _local(line) != "TextLine":
            continue
        previous_right: int | None = None
        for child in line:
            if _local(child) != "String":
                continue
            content = child.get("CONTENT") or ""
            hpos = _int_attr(child, "HPOS", -1)
            width = _int_attr(child, "WIDTH", 0)
            if content and width > 0:
                words.append((content, width))
            if hpos >= 0 and width > 0:
                if previous_right is not None:
                    gaps.append(hpos - previous_right)
                previous_right = hpos + width
            else:
                previous_right = None

    model = learn_widths(words, gaps)
    if len(_CACHE) >= _CACHE_SIZE:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[id(root)] = (root, model)
    return model


# ---------------------------------------------------------------------------
# Anchored layout
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceBox:
    """One source String of the line being rebuilt, with its geometry."""

    text: str
    hpos: int
    width: int

    @property
    def right(self) -> int:
        return self.hpos + self.width


@dataclass(frozen=True)
class LineAnchors:
    """What the rewriter knows about the line before it redraws it.

    ``sources[i]`` is the i-th source String's box, or ``None`` when that
    String had no usable geometry. ``pairs`` is the token alignment in
    reading order: ``(source_index, target_index)`` with ``None`` on the
    side that has no counterpart.
    """

    sources: tuple[SourceBox | None, ...]
    pairs: tuple[tuple[int | None, int | None], ...]
    model: WidthModel


def _same_word(source: str, target: str) -> bool:
    """Whether a matched pair is the same physical word, box included.

    Length is the test, not similarity: an OCR word turned to garbage at
    the same rank on the line is still the word in that box, while ``dela``
    matched to ``de`` is a box that must be split, and ``aujourd`` matched
    to ``aujourd'hui`` one that must be merged with its neighbour.
    """
    return abs(len(source) - len(target)) <= max(1, len(source) // 4)


def _is_anchor(
    i: int,
    pairs: tuple[tuple[int | None, int | None], ...],
    sources: tuple[SourceBox | None, ...],
    words: Sequence[str],
) -> bool:
    """Whether pair ``i`` pins its target word to its source box.

    The length test alone let a split through: ``communémentet`` matched to
    ``communément`` (13 vs 11 letters) passed as "the same word" and took
    the whole glued box, leaving ``et`` to be drawn after it in a blank
    that did not exist -- measured at 65 % of boundaries right on the BnF
    page, against 99.7 % for the same layout handed the right box. So a
    pair is refused when a neighbouring insertion or deletion EXPLAINS the
    difference: the source read as ``target + inserted neighbour`` (a
    split), or the target read as ``source + deleted neighbour`` (a merge),
    resembles more than the pair alone does.
    """
    s, t = pairs[i]
    assert s is not None and t is not None
    box = sources[s]
    assert box is not None
    base = char_similarity(box.text, words[t])
    for j in (i - 1, i + 1):
        if not 0 <= j < len(pairs):
            continue
        s2, t2 = pairs[j]
        if s2 is None and t2 is not None:
            joined = words[t2] + words[t] if j < i else words[t] + words[t2]
            if char_similarity(box.text, joined) > base:
                return False
        elif t2 is None and s2 is not None and sources[s2] is not None:
            other = sources[s2]
            assert other is not None
            joined = other.text + box.text if j < i else box.text + other.text
            if char_similarity(joined, words[t]) > base:
                return False
    return _same_word(box.text, words[t])


@dataclass
class _Item:
    """A run of consecutive target words sharing one horizontal interval."""

    targets: list[int]
    sources: list[SourceBox]
    anchored: bool
    left: int = 0
    right: int = 0


def _distribute(
    hpos: int, width: int, tokens: Sequence[str], weights: Sequence[float]
) -> list[tuple[str, int, int]]:
    """Share ``width`` between ``tokens`` by ``weights``; baseline arithmetic.

    Each boundary rounded from one exact division, the min-1 floor repaid
    by the widest tokens -- the same rules as ``_compute_geometry`` so that
    the only difference between the two is the weight each token carries.
    """
    total = sum(weights)
    if total <= 0:
        per = max(1, width // max(1, len(tokens)))
        return [(t, hpos + i * per, per) for i, t in enumerate(tokens)]
    widths: list[int] = []
    cumulative = 0.0
    prev = 0
    for w in weights:
        cumulative += w
        rounded = round(width * cumulative / total)
        widths.append(rounded - prev)
        prev = rounded
    if min(widths) < 1:
        deficit = 0
        for i, w in enumerate(widths):
            if w < 1:
                deficit += 1 - w
                widths[i] = 1
        while deficit > 0:
            donor = max(range(len(widths)), key=lambda i: widths[i])
            if widths[donor] <= 1:
                break
            take = min(deficit, widths[donor] - 1)
            widths[donor] -= take
            deficit -= take
    out: list[tuple[str, int, int]] = []
    cursor = hpos
    for t, w in zip(tokens, widths, strict=True):
        out.append((t, cursor, w))
        cursor += w
    return out


def _items(words: Sequence[str], anchors: LineAnchors) -> list[_Item] | None:
    """Group the target words into anchored words and free runs.

    A free run collects every target word between two anchors, together
    with every source box the alignment consumed there (deleted Strings,
    and matches whose length says "not the same word"). The run's extent is
    the union of those boxes; it never reaches into an anchored box.
    """
    items: list[_Item] = []
    current = _Item([], [], anchored=False)
    seen: set[int] = set()
    for i, (s, t) in enumerate(anchors.pairs):
        box = anchors.sources[s] if s is not None else None
        if t is not None:
            if t in seen or t >= len(words):
                return None
            seen.add(t)
        if (
            s is not None
            and t is not None
            and box is not None
            and _is_anchor(i, anchors.pairs, anchors.sources, words)
        ):
            if current.targets:
                items.append(current)
            current = _Item([], [], anchored=False)
            items.append(_Item([t], [box], anchored=True))
            continue
        if t is not None:
            current.targets.append(t)
        if box is not None:
            current.sources.append(box)
    if current.targets:
        items.append(current)
    if len(seen) != len(words):
        return None
    return items


def anchored_geometry(
    tokens: Sequence[str],
    is_space: Callable[[str], bool],
    anchors: LineAnchors,
    hpos: int,
    width: int,
) -> list[tuple[str, int, int]] | None:
    """One ``(token, hpos, width)`` per token, anchored where the line allows.

    ``None`` means "no usable layout": nothing to anchor on, a run squeezed
    below one pixel per token, an alignment that does not cover the words.
    The caller then draws the proportional geometry, as it always did.
    """
    words = [t for t in tokens if not is_space(t)]
    if not words or not any(anchors.sources):
        return None
    items = _items(words, anchors)
    if not items or not any(item.anchored for item in items):
        return None

    right_edge = hpos + width
    model = anchors.model
    for item in items:
        if item.sources:
            item.left = min(b.hpos for b in item.sources)
            item.right = max(b.right for b in item.sources)
    for i, item in enumerate(items):
        if item.sources:
            continue
        # A run of inserted words: the page only knows the blank between
        # its neighbours. It is drawn there at its NATURAL size -- the
        # letter and space widths of this page -- flush left after the
        # previous word, and compressed to fit only when the blank is too
        # narrow. Any slack stays in the space before the next word.
        blank_left = items[i - 1].right if i > 0 else hpos
        blank_right = items[i + 1].left if i + 1 < len(items) else right_edge
        lead = model.space if i > 0 else 0.0
        trail = model.space if i + 1 < len(items) else 0.0
        run_natural = sum(model.word(words[t]) for t in item.targets)
        run_natural += model.space * (len(item.targets) - 1)
        natural = lead + run_natural + trail
        blank = blank_right - blank_left
        scale = min(1.0, blank / natural) if natural > 0 else 1.0
        item.left = blank_left + round(lead * scale)
        item.right = item.left + round(run_natural * scale)

    # monotonic, inside the line, at least one pixel per token and one
    # pixel of blank between runs -- overlapping source boxes (0.9 % of
    # neighbours on real corpora) are clamped rather than refused
    cursor = hpos
    for i, item in enumerate(items):
        item.left = max(item.left, cursor + (1 if i > 0 else 0))
        item.right = min(item.right, right_edge)
        needed = 2 * len(item.targets) - 1
        if item.right - item.left < needed and not item.sources:
            # an inserted run with no blank to live in: borrow the missing
            # pixels from the kept neighbour after it, then before it --
            # a few pixels off one anchor beats losing every anchor of
            # the line to the proportional fallback
            deficit = needed - (item.right - item.left)
            nxt = items[i + 1] if i + 1 < len(items) else None
            if nxt is not None and nxt.right - nxt.left - deficit >= 2 * len(
                nxt.targets
            ):
                nxt.left += deficit + 1
                item.right = nxt.left - 1
            elif i > 0 and (
                prev := items[i - 1]
            ).right - prev.left - deficit >= 2 * len(prev.targets):
                prev.right -= deficit + 1
                item.left = prev.right + 1
                item.right = item.left + needed
        if item.right - item.left < needed:
            return None
        cursor = item.right

    word_at = [k for k, t in enumerate(tokens) if not is_space(t)]
    out: list[tuple[str, int, int] | None] = [None] * len(tokens)
    for i, item in enumerate(items):
        first, last = word_at[item.targets[0]], word_at[item.targets[-1]]
        run = tokens[first : last + 1]
        weights = [len(t) * model.space if is_space(t) else model.word(t) for t in run]
        for k, triple in enumerate(
            _distribute(item.left, item.right - item.left, run, weights)
        ):
            out[first + k] = triple
        if i + 1 < len(items):
            gap_index = last + 1
            out[gap_index] = (
                tokens[gap_index],
                item.right,
                items[i + 1].left - item.right,
            )

    if any(triple is None for triple in out):
        return None
    return [triple for triple in out if triple is not None]
