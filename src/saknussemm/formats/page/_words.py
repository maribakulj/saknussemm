"""Slow-path ``Word`` elements: keep the untouched ones, cut the rest out of what exists.

Until now a correction that changed a line's word count cost the line
every ``Word`` it had (spec §6.2 P4): fabricating word polygons on a skewed
line was judged more dishonest than dropping them. That reasoning assumed
the polygons had to be invented. They do not:

- a word the correction did not touch **keeps its element**, ``Coords``
  untouched -- P1 holds for it literally, no geometry is rewritten;
- a run the correction changed is redrawn inside the ``Word`` polygons it
  consumed: a word split in two is its own polygon **cut** by a vertical
  line, two words merged are the line's polygon between their outer edges,
  an inserted word is the line's polygon over the blank it is drawn in.
  Nothing is drawn that a polygon of the source did not already enclose,
  so a skewed line yields skewed words.

Where the cuts fall is decided by the same pixel-blind layout ALTO uses
(``formats/alto/_geometry``): the kept words anchor the line, and the
letter widths are learned from the document's own ``Word`` boxes. Measured
on PAGE files with the bench of ``hans`` (H22): 97 to 99 % of boundaries
inside the true inter-word blank.

When the layout cannot answer -- no ``Word`` kept, a vertical or
right-to-left line, a ``Coords`` without ``@points`` -- nothing is rebuilt
and the caller removes the words, exactly as before.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from lxml import etree

from saknussemm.core.alignment import align_tokens
from saknussemm.formats.alto._geometry import (
    LineAnchors,
    SourceBox,
    WidthModel,
    anchored_geometry,
    learn_widths,
)
from saknussemm.formats.page._ns import _tag
from saknussemm.formats.page._text import word_text

Point = tuple[int, int]


def polygon(el: etree._Element, ns: str) -> list[Point] | None:
    """The ``Coords@points`` of ``el`` as integer pairs, or ``None``.

    ``None`` for the 2010 schema's ``<Point x= y=>`` children and for
    anything malformed: a polygon this module cannot read is one it must
    not cut.
    """
    coords = el.find(_tag("Coords", ns))
    raw = coords.get("points") if coords is not None else None
    if not raw:
        return None
    points: list[Point] = []
    for pair in raw.split():
        x, sep, y = pair.partition(",")
        if not sep:
            return None
        try:
            points.append((int(float(x)), int(float(y))))
        except ValueError:
            return None
    return points if len(points) >= 3 else None


def _clip(points: list[Point], bound: int, *, keep_right: bool) -> list[Point]:
    """One Sutherland-Hodgman pass against the vertical line ``x = bound``."""

    def inside(p: Point) -> bool:
        return p[0] >= bound if keep_right else p[0] <= bound

    out: list[Point] = []
    for i, current in enumerate(points):
        previous = points[i - 1]
        if inside(current) != inside(previous):
            (x0, y0), (x1, y1) = previous, current
            y = y0 + (y1 - y0) * (bound - x0) / (x1 - x0)
            out.append((bound, round(y)))
        if inside(current):
            out.append(current)
    return out


def cut(points: list[Point], left: int, right: int) -> list[Point] | None:
    """The part of ``points`` between ``x = left`` and ``x = right``.

    ``None`` when nothing of it lies there -- the caller then has no
    honest polygon to give.
    """
    clipped = _clip(_clip(points, left, keep_right=True), right, keep_right=False)
    deduped = [p for i, p in enumerate(clipped) if p != clipped[i - 1]]
    if len(deduped) < 3 or len({p[0] for p in deduped}) < 2:
        return None
    return deduped


def _extent(points: list[Point]) -> tuple[int, int]:
    xs = [p[0] for p in points]
    return min(xs), max(xs)


class PageWidths:
    """The document's letter widths, fitted on first use from its ``Word`` boxes.

    Created before the rewrite loop touches the tree and asked only on a
    slow-path line, so a document with no such line never pays for the fit
    and the fit never sees a line already rebuilt.
    """

    def __init__(self, root: etree._Element, ns: str) -> None:
        self._root, self._ns = root, ns
        self._model: WidthModel | None = None

    def __call__(self) -> WidthModel:
        if self._model is None:
            words: list[tuple[str, int]] = []
            gaps: list[int] = []
            for line in self._root.iter(_tag("TextLine", self._ns)):
                previous_right: int | None = None
                for word in line.iterchildren(_tag("Word", self._ns)):
                    points = polygon(word, self._ns)
                    text = word_text(word, self._ns)
                    if points is None:
                        previous_right = None
                        continue
                    left, right = _extent(points)
                    if text and right > left:
                        words.append((text, right - left))
                    if previous_right is not None:
                        gaps.append(left - previous_right)
                    previous_right = right
            self._model = learn_widths(words, gaps)
        return self._model


@dataclass(frozen=True)
class WordPlan:
    """One corrected word: the element it keeps, or the polygon it gets."""

    text: str
    kept: int | None  # index of the source Word kept as is
    points: tuple[Point, ...] = ()


def plan_words(
    line: etree._Element,
    word_els: Sequence[etree._Element],
    words: Sequence[str],
    ns: str,
    widths: PageWidths,
) -> list[WordPlan] | None:
    """What each corrected word becomes, or ``None`` when nothing can be kept.

    ``None`` is every case this module refuses: a source ``Word`` or the
    line without a readable polygon, words not laid out left to right (a
    vertical line, a right-to-left script), no word the correction left
    alone, a layout that does not fit the line.
    """
    line_points = polygon(line, ns)
    word_points = [polygon(w, ns) for w in word_els]
    if line_points is None or any(p is None for p in word_points) or not words:
        return None
    polygons = [p for p in word_points if p is not None]
    extents = [_extent(p) for p in polygons]
    # left to right, each word starting past the middle of the one before:
    # a few pixels of overlap are an OCR habit, a word sitting on its
    # predecessor is a vertical line or another script
    if any(2 * b[0] < a[0] + a[1] for a, b in zip(extents, extents[1:], strict=False)):
        return None

    texts = [word_text(w, ns) or "" for w in word_els]
    alignment = align_tokens(texts, list(words))
    anchors = LineAnchors(
        sources=tuple(
            SourceBox(text, left, right - left) if right > left else None
            for text, (left, right) in zip(texts, extents, strict=True)
        ),
        pairs=tuple((p.source_index, p.target_index) for p in alignment.pairs),
        model=widths(),
    )
    tokens: list[str] = []
    for word in words:
        tokens += [word, " "]
    tokens.pop()
    line_left, line_right = _extent(line_points)
    layout = anchored_geometry(
        tokens, lambda t: t == " ", anchors, line_left, line_right - line_left
    )
    if layout is None:
        return None

    plans: list[WordPlan] = []
    boxes = [triple for triple in layout if triple[0] != " "]
    for (text, left, width), (kept, consumed) in zip(
        boxes, layout.origins, strict=True
    ):
        if kept:
            plans.append(WordPlan(text, consumed[0]))
            continue
        # a split is cut out of the one polygon it consumed; a merge or an
        # insertion has no single polygon of its own and takes the line's
        source = polygons[consumed[0]] if len(consumed) == 1 else line_points
        points = cut(source, left, left + width) or cut(line_points, left, left + width)
        if points is None:
            return None
        plans.append(WordPlan(text, None, tuple(points)))
    return plans


def new_word(word_id: str, plan: WordPlan, ns: str) -> etree._Element:
    """A ``Word`` carrying ``plan``'s polygon and text, and nothing else."""
    word = etree.Element(_tag("Word", ns))
    word.set("id", word_id)
    coords = etree.SubElement(word, _tag("Coords", ns))
    coords.set("points", " ".join(f"{x},{y}" for x, y in plan.points))
    equiv = etree.SubElement(word, _tag("TextEquiv", ns))
    etree.SubElement(equiv, _tag("Unicode", ns)).text = plan.text
    return word
