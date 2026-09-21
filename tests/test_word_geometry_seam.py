"""The seam's guard rail: what a resolver is NOT allowed to put in the tree.

`_geometry_is_usable` is the whole reason a third party may be handed the
slow path's geometry at all. The promise that saknussemm never emits an ALTO
whose boxes contradict its text belongs to the engine, not to whoever plugs
in — so every branch of the check needs a test that fails if the branch is
removed.

`_resolve_geometry` is tested for one property above all: every failure mode
collapses to the SAME bytes the rewriter produced before this seam existed.
No resolver, a resolver that raises, and a resolver that answers something
unusable are indistinguishable downstream. That is what made the seam safe
to add before anything filled it.
"""

from __future__ import annotations

import pytest

from saknussemm.core.protocols import LineGeometryRequest, TokenBox
from saknussemm.core.schemas import Coords, LineManifest
from saknussemm.formats.alto.rewriter import (
    _compute_geometry,
    _geometry_is_usable,
    _resolve_geometry,
)

TOKENS = ["de", " ", "la"]
HPOS, WIDTH = 100, 41


def _boxes(*triples: tuple[str, int, int]) -> tuple[TokenBox, ...]:
    return tuple(TokenBox(text=t, hpos=h, width=w) for t, h, w in triples)


GOOD = _boxes(("de", 100, 18), (" ", 118, 6), ("la", 124, 17))


def _manifest() -> LineManifest:
    return LineManifest(
        line_id="L1",
        page_id="P1",
        block_id="TB1",
        line_order_global=0,
        line_order_in_block=0,
        coords=Coords(hpos=HPOS, vpos=10, width=WIDTH, height=40),
        ocr_text="dela",
    )


# --------------------------------------------------------------------------
# _geometry_is_usable — one test per refusal
# --------------------------------------------------------------------------


def test_a_well_formed_answer_is_accepted() -> None:
    assert _geometry_is_usable(GOOD, TOKENS, HPOS, WIDTH)


def test_wrong_box_count_is_refused() -> None:
    assert not _geometry_is_usable(GOOD[:2], TOKENS, HPOS, WIDTH)


def test_a_box_carrying_the_wrong_token_is_refused() -> None:
    """Order matters, not just arity.

    A resolver that returns the right number of boxes with the words
    permuted would otherwise write each word into its neighbour's box —
    the exact failure `_word_boundary_moved` exists to prevent on the fast
    path, arriving through the back door.
    """
    swapped = _boxes(("la", 100, 18), (" ", 118, 6), ("de", 124, 17))
    assert not _geometry_is_usable(swapped, TOKENS, HPOS, WIDTH)


@pytest.mark.parametrize("width", [0, -5])
def test_a_non_positive_width_is_refused(width: int) -> None:
    """A zero-width String is not a box; it is a box-shaped absence."""
    degenerate = _boxes(("de", 100, 18), (" ", 118, width), ("la", 124, 17))
    assert not _geometry_is_usable(degenerate, TOKENS, HPOS, WIDTH)


def test_overlapping_boxes_are_refused() -> None:
    overlapping = _boxes(("de", 100, 30), (" ", 118, 6), ("la", 124, 17))
    assert not _geometry_is_usable(overlapping, TOKENS, HPOS, WIDTH)


def test_a_box_starting_left_of_the_line_is_refused() -> None:
    outside = _boxes(("de", 90, 18), (" ", 118, 6), ("la", 124, 17))
    assert not _geometry_is_usable(outside, TOKENS, HPOS, WIDTH)


def test_a_box_running_past_the_line_is_refused() -> None:
    """The line's width is a hard edge: past it the word is off its own line."""
    outside = _boxes(("de", 100, 18), (" ", 118, 6), ("la", 124, 90))
    assert not _geometry_is_usable(outside, TOKENS, HPOS, WIDTH)


# --------------------------------------------------------------------------
# _resolve_geometry — every failure is the incumbent's geometry
# --------------------------------------------------------------------------


class _Fixed:
    name = "fixed"

    def __init__(self, boxes: tuple[TokenBox, ...]) -> None:
        self._boxes = boxes
        self.seen: LineGeometryRequest | None = None

    def resolve(self, request: LineGeometryRequest) -> tuple[TokenBox, ...]:
        self.seen = request
        return self._boxes


class _Raises:
    name = "raises"

    def resolve(self, request: LineGeometryRequest) -> tuple[TokenBox, ...]:
        raise RuntimeError("no model")


def _resolve(resolver: object) -> list[tuple[str, int, int]]:
    return _resolve_geometry(
        resolver,  # type: ignore[arg-type]
        _manifest(),
        HPOS,
        10,
        WIDTH,
        40,
        list(TOKENS),
        None,
    )


BASELINE = _compute_geometry(HPOS, WIDTH, list(TOKENS))


def test_no_resolver_is_the_proportional_geometry() -> None:
    assert _resolve(None) == BASELINE


def test_a_resolver_that_raises_falls_back_silently() -> None:
    """A missing model must not take the page down with it."""
    assert _resolve(_Raises()) == BASELINE


def test_an_unusable_answer_falls_back() -> None:
    assert _resolve(_Fixed(GOOD[:2])) == BASELINE


def test_a_usable_answer_is_used() -> None:
    assert _resolve(_Fixed(GOOD)) == [
        ("de", 100, 18),
        (" ", 118, 6),
        ("la", 124, 17),
    ]


def test_the_request_carries_the_line_and_an_opaque_image() -> None:
    """`image` crosses the pixel-blind core without being decoded.

    Typed as `object`, never opened here — that is what keeps I4 true by
    construction rather than by discipline.
    """
    sentinel = object()
    resolver = _Fixed(GOOD)
    _resolve_geometry(
        resolver,  # type: ignore[arg-type]
        _manifest(),
        HPOS,
        10,
        WIDTH,
        40,
        list(TOKENS),
        sentinel,
    )
    assert resolver.seen is not None
    assert resolver.seen.image is sentinel
    assert resolver.seen.line_id == "L1"
    assert resolver.seen.tokens == ("de", " ", "la")
    assert (resolver.seen.hpos, resolver.seen.width) == (HPOS, WIDTH)
