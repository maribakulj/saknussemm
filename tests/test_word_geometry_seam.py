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


def _request(image: object | None = None) -> LineGeometryRequest:
    return LineGeometryRequest(
        hpos=HPOS,
        width=WIDTH,
        tokens=tuple(TOKENS),
        line_id=_manifest().line_id,
        vpos=10,
        height=40,
        image=image,
    )


def _resolve(resolver: object) -> list[tuple[str, int, int]]:
    # anchors=None: the middle tier is off, so every failure mode below
    # must land on the proportional geometry, as before that tier existed
    return _resolve_geometry(resolver, _request(), None)  # type: ignore[arg-type]


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
    _resolve_geometry(resolver, _request(sentinel), None)  # type: ignore[arg-type]
    assert resolver.seen is not None
    assert resolver.seen.image is sentinel
    assert resolver.seen.line_id == "L1"
    assert resolver.seen.tokens == ("de", " ", "la")
    assert (resolver.seen.hpos, resolver.seen.width) == (HPOS, WIDTH)


# --------------------------------------------------------------------------
# Le fil complet : rewrite_alto_file -> _rebuild_line -> le résolveur
# --------------------------------------------------------------------------


def test_the_public_entry_point_reaches_the_resolver(tmp_path) -> None:
    """Sans ce fil, le Protocol est décoratif.

    Il a manqué un temps : la couture s'arrêtait à ``_rebuild_line``, que
    rien d'appelable depuis l'extérieur ne laissait atteindre. Le mode
    existait, était mesuré, et était injoignable — exactement ce qui était
    arrivé au producteur ``page_aligned`` de la démo.
    """
    from lxml import etree

    from saknussemm.core.schemas import BlockManifest, Coords, PageManifest
    from saknussemm.formats.alto.rewriter import rewrite_alto_file
    from tests.test_rewriter import NS_V3, make_alto_xml

    lines_xml = (
        '<TextLine ID="L1" HPOS="100" VPOS="20" WIDTH="300" HEIGHT="40">'
        '<String ID="S1" CONTENT="dela" HPOS="100" VPOS="20" '
        'WIDTH="300" HEIGHT="40"/>'
        "</TextLine>"
    )
    lm = LineManifest(
        line_id="L1",
        page_id="P1",
        block_id="TB1",
        line_order_global=0,
        line_order_in_block=0,
        coords=Coords(hpos=100, vpos=20, width=300, height=40),
        ocr_text="dela",
        corrected_text="de la",
    )
    page = PageManifest(
        page_id="P1",
        source_file="test.xml",
        page_index=0,
        page_width=2480,
        page_height=3508,
        blocks=[
            BlockManifest(
                block_id="TB1",
                page_id="P1",
                block_order=0,
                coords=Coords(hpos=10, vpos=20, width=400, height=60),
                line_ids=["L1"],
            )
        ],
        lines=[lm],
    )
    path = tmp_path / "test.xml"
    path.write_text(make_alto_xml(lines_xml), encoding="utf-8")

    seen: list[LineGeometryRequest] = []

    class _Pinned:
        """Rend une géométrie reconnaissable, que rien d'autre ne produirait."""

        name = "pinned"

        def resolve(self, request: LineGeometryRequest) -> tuple[TokenBox, ...]:
            seen.append(request)
            return (
                TokenBox(text="de", hpos=110, width=30),
                TokenBox(text=" ", hpos=140, width=20),
                TokenBox(text="la", hpos=160, width=40),
            )

    res = rewrite_alto_file(path, [page], "test", "mock", word_geometry=_Pinned())
    root = etree.fromstring(res.xml_bytes)
    strings = root.findall(f".//{{{NS_V3}}}String")

    assert seen, "le résolveur n'a jamais été appelé"
    assert seen[0].line_id == "L1"
    assert seen[0].tokens == ("de", " ", "la")
    assert [(s.get("CONTENT"), s.get("HPOS"), s.get("WIDTH")) for s in strings] == [
        ("de", "110", "30"),
        ("la", "160", "40"),
    ]


def test_the_public_entry_point_without_a_resolver_is_unchanged(tmp_path) -> None:
    """Le défaut reste la géométrie proportionnelle, à l'octet près."""
    from saknussemm.core.schemas import BlockManifest, Coords, PageManifest
    from saknussemm.formats.alto.rewriter import rewrite_alto_file
    from tests.test_rewriter import make_alto_xml

    lines_xml = (
        '<TextLine ID="L1" HPOS="100" VPOS="20" WIDTH="300" HEIGHT="40">'
        '<String ID="S1" CONTENT="dela" HPOS="100" VPOS="20" '
        'WIDTH="300" HEIGHT="40"/>'
        "</TextLine>"
    )
    lm = LineManifest(
        line_id="L1",
        page_id="P1",
        block_id="TB1",
        line_order_global=0,
        line_order_in_block=0,
        coords=Coords(hpos=100, vpos=20, width=300, height=40),
        ocr_text="dela",
        corrected_text="de la",
    )
    page = PageManifest(
        page_id="P1",
        source_file="test.xml",
        page_index=0,
        page_width=2480,
        page_height=3508,
        blocks=[
            BlockManifest(
                block_id="TB1",
                page_id="P1",
                block_order=0,
                coords=Coords(hpos=10, vpos=20, width=400, height=60),
                line_ids=["L1"],
            )
        ],
        lines=[lm],
    )
    path = tmp_path / "test.xml"
    path.write_text(make_alto_xml(lines_xml), encoding="utf-8")

    a = rewrite_alto_file(path, [page], "test", "mock").xml_bytes
    b = rewrite_alto_file(path, [page], "test", "mock", word_geometry=None).xml_bytes
    assert a == b


# --------------------------------------------------------------------------
# last_resort — where the resolver sits among the three tiers
# --------------------------------------------------------------------------


def _anchored_line() -> object:
    """``de | la`` kept as they are: a line the anchored tier can answer."""
    from saknussemm.formats.alto._geometry import LineAnchors, SourceBox, WidthModel

    return LineAnchors(
        sources=(SourceBox("de", 100, 18), SourceBox("la", 124, 17)),
        pairs=((0, 0), (1, 1)),
        model=WidthModel.proportional(),
    )


def _unanchorable_line() -> object:
    """Every word changed: nothing to keep, the anchored tier declines."""
    from saknussemm.formats.alto._geometry import LineAnchors, SourceBox, WidthModel

    return LineAnchors(
        sources=(SourceBox("xxxxxxxx", 100, 18), SourceBox("yyyyyyyy", 124, 17)),
        pairs=((0, 0), (1, 1)),
        model=WidthModel.proportional(),
    )


class _Counting(_Fixed):
    def __init__(self, boxes: tuple[TokenBox, ...], last_resort: bool) -> None:
        super().__init__(boxes)
        self.last_resort = last_resort
        self.calls = 0

    def resolve(self, request: LineGeometryRequest) -> tuple[TokenBox, ...]:
        self.calls += 1
        return super().resolve(request)


OTHER = _boxes(("de", 100, 10), (" ", 110, 20), ("la", 130, 11))


def test_by_default_the_resolver_is_asked_before_the_anchored_tier() -> None:
    resolver = _Counting(OTHER, last_resort=False)
    geo = _resolve_geometry(resolver, _request(), _anchored_line())  # type: ignore[arg-type]
    assert resolver.calls == 1
    assert geo == [("de", 100, 10), (" ", 110, 20), ("la", 130, 11)]


def test_a_last_resort_resolver_is_not_asked_when_the_page_can_answer() -> None:
    resolver = _Counting(OTHER, last_resort=True)
    geo = _resolve_geometry(resolver, _request(), _anchored_line())  # type: ignore[arg-type]
    assert resolver.calls == 0
    assert geo == [("de", 100, 18), (" ", 118, 6), ("la", 124, 17)]


def test_a_last_resort_resolver_is_asked_when_no_word_can_be_kept() -> None:
    resolver = _Counting(OTHER, last_resort=True)
    geo = _resolve_geometry(resolver, _request(), _unanchorable_line())  # type: ignore[arg-type]
    assert resolver.calls == 1
    assert geo == [("de", 100, 10), (" ", 110, 20), ("la", 130, 11)]


def test_a_last_resort_resolver_is_asked_without_anchors_and_may_still_fail() -> None:
    resolver = _Counting(GOOD[:2], last_resort=True)  # unusable answer
    assert _resolve_geometry(resolver, _request(), None) == BASELINE  # type: ignore[arg-type]
    assert resolver.calls == 1
