"""The slow path's middle tier: keep the boxes the correction did not touch.

Every test here is about one promise: a word the correction left alone
keeps its box to the pixel, and a run the correction changed is redrawn
INSIDE the boxes it consumed and nowhere else. The widths that share a
consumed box out are learned from the page's own Strings, so the second
half of the file pins that fit.
"""

from __future__ import annotations

import pytest
from lxml import etree

from saknussemm.formats.alto._geometry import (
    LineAnchors,
    SourceBox,
    WidthModel,
    anchored_geometry,
    box_int,
    fold_char,
    learn_widths,
    page_widths,
)
from saknussemm.formats.alto.rewriter import _is_space_token, _tokenize

# A page-shaped model in pixels: i=4, m=12, a=8, everything else 8, space 6.
MODEL = WidthModel(glyphs={"i": 4.0, "m": 12.0, "a": 8.0}, space=6.0, unit=8.0)


def _anchors(
    sources: list[tuple[str, int, int] | None],
    pairs: list[tuple[int | None, int | None]],
    model: WidthModel = MODEL,
) -> LineAnchors:
    return LineAnchors(
        sources=tuple(SourceBox(*s) if s else None for s in sources),
        pairs=tuple(pairs),
        model=model,
    )


def _layout(
    text: str, anchors: LineAnchors, hpos: int = 0, width: int = 400
) -> list[tuple[str, int, int]] | None:
    return anchored_geometry(_tokenize(text), _is_space_token, anchors, hpos, width)


# --------------------------------------------------------------------------
# anchoring
# --------------------------------------------------------------------------


def test_a_split_word_is_cut_inside_its_own_box_and_the_neighbours_do_not_move() -> (
    None
):
    """``un | dela | fin`` corrected to ``un de la fin``.

    ``dela`` (100..140) is matched to ``la`` by the aligner and ``de`` is an
    insertion; the pair is refused as "same word" (4 vs 2 letters), so both
    corrected words share the 40 px box. ``un`` and ``fin`` keep theirs.
    """
    anchors = _anchors(
        [("un", 10, 20), ("dela", 100, 40), ("fin", 200, 30)],
        [(0, 0), (None, 1), (1, 2), (2, 3)],
    )
    geo = _layout("un de la fin", anchors)
    assert geo is not None
    assert geo[0] == ("un", 10, 20)
    assert geo[-1] == ("fin", 200, 30)
    de, sp, la = geo[2], geo[3], geo[4]
    assert de[1] == 100 and la[1] + la[2] == 140
    assert sp[1] == de[1] + de[2] and la[1] == sp[1] + sp[2]
    # weights 16 : 6 : 16 over 40 px -> 17 | 6 | 17
    assert (de[2], sp[2], la[2]) == (17, 6, 17)
    # the blanks between kept words are the source's blanks
    assert geo[1] == (" ", 30, 70)
    assert geo[5] == (" ", 140, 60)


def test_two_merged_words_take_the_union_of_their_boxes() -> None:
    anchors = _anchors(
        [("un", 10, 20), ("de", 100, 15), ("la", 125, 15), ("fin", 200, 30)],
        [(0, 0), (1, None), (2, 1), (3, 2)],
    )
    geo = _layout("un dela fin", anchors)
    assert geo is not None
    assert geo[2] == ("dela", 100, 40)
    assert geo[0] == ("un", 10, 20) and geo[4] == ("fin", 200, 30)


def test_a_one_to_one_correction_keeps_every_box() -> None:
    """Same word count but a boundary the fast path refused: nothing moves."""
    anchors = _anchors(
        [("Frauce", 10, 60), ("et", 80, 20)],
        [(0, 0), (1, 1)],
    )
    assert _layout("France et", anchors) == [
        ("France", 10, 60),
        (" ", 70, 10),
        ("et", 80, 20),
    ]


def test_an_inserted_word_is_drawn_at_its_natural_size_after_its_neighbour() -> None:
    """``un fin`` -> ``un ami fin``: no box was consumed, so the word goes in
    the blank at the size this page would give it, flush left; the slack
    stays in the space before the next kept word."""
    # the kept boxes measure exactly what the model gives them (u+n = 16,
    # f+i+n = 20), so the line's scale is 1 and its space the page's
    anchors = _anchors([("un", 0, 16), ("fin", 100, 20)], [(0, 0), (None, 1), (1, 2)])
    geo = _layout("un ami fin", anchors)
    assert geo is not None
    assert geo[0] == ("un", 0, 16) and geo[4] == ("fin", 100, 20)
    # space 6, then a+m+i = 8+12+4 = 24
    assert geo[1] == (" ", 16, 6)
    assert geo[2] == ("ami", 22, 24)
    assert geo[3] == (" ", 46, 54)


def test_an_inserted_word_follows_the_corps_of_its_line() -> None:
    """A heading set twice as large: the kept words measure twice the
    model, so the inserted word and its spaces are drawn twice as large."""
    anchors = _anchors([("un", 0, 32), ("fin", 200, 40)], [(0, 0), (None, 1), (1, 2)])
    geo = _layout("un ami fin", anchors)
    assert geo is not None
    assert geo[1] == (" ", 32, 12)
    assert geo[2] == ("ami", 44, 48)


def test_an_inserted_word_takes_the_blank_its_own_line_shows() -> None:
    """Two kept neighbours 30 px apart on this line: that, not the page's
    6 px, is the space drawn before a word inserted further along."""
    anchors = _anchors(
        [("un", 0, 16), ("mi", 46, 16), ("fin", 200, 20)],
        [(0, 0), (1, 1), (None, 2), (2, 3)],
    )
    geo = _layout("un mi ami fin", anchors)
    assert geo is not None
    assert geo[3] == (" ", 62, 30)
    assert geo[4] == ("ami", 92, 24)


def test_an_inserted_word_is_compressed_when_the_blank_is_too_narrow() -> None:
    anchors = _anchors([("un", 0, 16), ("fin", 26, 20)], [(0, 0), (None, 1), (1, 2)])
    geo = _layout("un ami fin", anchors)
    assert geo is not None
    assert geo[0] == ("un", 0, 16) and geo[4] == ("fin", 26, 20)
    assert all(w >= 1 for _, _, w in geo)
    assert geo[2][1] + geo[2][2] < 26


def test_an_inserted_word_at_the_end_of_the_line_does_not_stretch_to_the_edge() -> None:
    anchors = _anchors([("un", 0, 16)], [(0, 0), (None, 1)])
    geo = _layout("un ami", anchors, width=400)
    assert geo == [("un", 0, 16), (" ", 16, 6), ("ami", 22, 24)]


def test_overlapping_source_boxes_are_clamped_not_refused() -> None:
    """0.9 % of neighbouring boxes overlap on real corpora."""
    anchors = _anchors([("un", 0, 25), ("de", 20, 20)], [(0, 0), (1, 1)])
    geo = _layout("un de", anchors)
    assert geo is not None
    un, sp, de = geo
    assert un[1] + un[2] <= sp[1] and sp[1] + sp[2] <= de[1]
    assert sp[2] >= 1


def test_a_run_with_no_blank_borrows_pixels_from_the_next_kept_word() -> None:
    """``a x y b`` with one pixel between ``a`` and ``b``: the inserted run
    needs three, so ``b`` gives them up rather than the whole line falling
    back to the proportional layout."""
    anchors = _anchors(
        [("a", 0, 5), ("b", 6, 5)], [(0, 0), (None, 1), (None, 2), (1, 3)]
    )
    geo = _layout("a x y b", anchors, width=11)
    assert geo is not None
    assert geo[0] == ("a", 0, 5)
    assert all(w >= 1 for _, _, w in geo)
    assert all(x[1] + x[2] <= y[1] for x, y in zip(geo, geo[1:]))
    b = geo[-1]
    assert b[1] + b[2] == 11 and 1 <= b[2] < 5


def test_a_run_no_neighbour_can_make_room_for_yields_none() -> None:
    anchors = _anchors(
        [("a", 0, 2), ("b", 3, 2)], [(0, 0), (None, 1), (None, 2), (None, 3), (1, 4)]
    )
    assert _layout("a x y z b", anchors, width=5) is None


def test_no_geometry_on_any_source_yields_none() -> None:
    anchors = _anchors([None, None], [(0, 0), (1, 1)])
    assert _layout("un de", anchors) is None


def test_an_alignment_that_does_not_cover_every_word_yields_none() -> None:
    anchors = _anchors([("un", 0, 20), ("de", 30, 20)], [(0, 0), (1, 1)])
    assert _layout("un de la", anchors) is None


def test_the_layout_is_clamped_inside_the_line_box() -> None:
    """A source box may poke out of its line (142 of 7 000 lines measured)."""
    anchors = _anchors([("un", -5, 20), ("de", 380, 40)], [(0, 0), (1, 1)])
    geo = _layout("un de", anchors, hpos=0, width=400)
    assert geo is not None
    assert geo[0][1] >= 0 and geo[-1][1] + geo[-1][2] <= 400


# --------------------------------------------------------------------------
# learning
# --------------------------------------------------------------------------

_FONT = {"i": 4, "m": 12, "a": 8}


def _words(texts: list[str]) -> list[tuple[str, int]]:
    return [(t, sum(_FONT[c] for c in t)) for t in texts]


PAGE_WORDS = _words(
    ["mi", "ami", "im", "aim", "mm", "i", "ii", "aa", "ma", "iam", "mia", "am"] * 2
)


def test_widths_are_recovered_from_word_boxes_alone() -> None:
    model = learn_widths(PAGE_WORDS, gaps=[6, 6, 7, 5, 6])
    assert model.glyph("i") == pytest.approx(4, abs=1e-3)
    assert model.glyph("m") == pytest.approx(12, abs=1e-3)
    assert model.glyph("a") == pytest.approx(8, abs=1e-3)
    assert model.space == 6
    assert model.glyph("z") == pytest.approx(model.unit)
    assert fold_char("Í") == "i" and model.glyph("Í") == model.glyph("i")


def test_a_box_that_does_not_add_up_is_left_out_of_the_fit() -> None:
    poisoned = PAGE_WORDS + [("iii", 900)]
    model = learn_widths(poisoned, gaps=[6])
    assert model.glyph("i") == pytest.approx(4, abs=1e-3)


def test_a_page_too_small_to_fit_keeps_the_incumbent_ratios_in_pixels() -> None:
    model = learn_widths(_words(["mi", "am"]), gaps=[6])
    assert model.glyphs == {}
    assert model.unit == pytest.approx((16 + 20) / 4)
    assert model.space == 6
    assert model.word("mi") == pytest.approx(2 * model.unit)


@pytest.mark.parametrize(
    "opening",
    ['<alto xmlns="http://www.loc.gov/standards/alto/ns-v3#">', "<alto>"],
    ids=["v3", "no-namespace"],
)
def test_page_widths_reads_strings_of_any_alto_flavour(opening: str) -> None:
    strings = "".join(
        f'<String CONTENT="{t}" HPOS="{i * 40}" WIDTH="{w}"/>'
        for i, (t, w) in enumerate(PAGE_WORDS)
    )
    xml = f"{opening}<Layout><Page><TextBlock><TextLine>{strings}</TextLine></TextBlock></Page></Layout></alto>"
    root = etree.fromstring(xml.encode())
    model = page_widths(root)
    assert model.glyph("m") == pytest.approx(12, abs=1e-3)
    # pure: the same tree gives the same model, and nothing is remembered
    assert page_widths(root) == model


@pytest.mark.parametrize("bad", ["abc", "inf", "nan", "1e999", ""])
def test_a_malformed_string_box_is_not_evidence_and_not_an_error(bad: str) -> None:
    """The rewriter never parsed String geometry before this module; a
    malformed value on SOME String must not abort the whole file now."""
    strings = "".join(
        f'<String CONTENT="{t}" HPOS="{i * 40}" WIDTH="{w}"/>'
        for i, (t, w) in enumerate(PAGE_WORDS)
    )
    broken = (
        f'<String CONTENT="autre" HPOS="{bad}" WIDTH="50"/>'
        f'<String CONTENT="encore" HPOS="10" WIDTH="{bad}"/>'
    )
    xml = f"<alto><TextLine>{strings}</TextLine><TextLine>{broken}</TextLine></alto>"
    model = page_widths(etree.fromstring(xml.encode()))
    assert model.glyph("m") == pytest.approx(12, abs=0.5)
    assert box_int(bad) is None


def test_a_float_total_is_the_same_float_on_every_python() -> None:
    """``sum()`` is compensated from CPython 3.12 on and naive before: ten
    times 0.1 is 1.0 on one and 0.9999999999999999 on the other, and a
    boundary on a rounding tie moves a pixel. Every total goes through
    ``fsum``, which is correctly rounded everywhere."""
    model = WidthModel(glyphs={"a": 0.1}, space=0.1, unit=0.1)
    assert model.word("a" * 10) == 1.0
