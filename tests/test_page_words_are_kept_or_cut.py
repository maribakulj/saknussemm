"""PAGE slow path (§6.2 P4): keep the untouched ``Word``s, cut the rest out of what exists.

The old rule dropped every ``Word`` of a line whose word count changed,
because inventing word polygons on a skewed line would have been a lie. The
polygons are not invented here: a kept word keeps its own, a split word is
its own polygon cut by a vertical line, and what has no polygon of its own
(a merge, an inserted word) takes the line's between two abscissae. These
tests pin that nothing else is drawn.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from saknussemm.formats.loader import build_document_manifest
from saknussemm.formats.page._words import cut, polygon
from saknussemm.formats.page.rewriter import rewrite_page_file

NS = "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"


def _page(line_points: str, words: list[tuple[str, str]], *, extra: str = "") -> str:
    body = "".join(
        f'<Word id="w{i}"><Coords points="{pts}"/>'
        f"<TextEquiv><Unicode>{text}</Unicode></TextEquiv></Word>"
        for i, (text, pts) in enumerate(words)
    )
    line_text = " ".join(t for t, _ in words)
    return (
        f'<?xml version="1.0" encoding="UTF-8"?><PcGts xmlns="{NS}">'
        "<Metadata><Creator>x</Creator><Created>2020-01-01T00:00:00</Created>"
        "<LastChange>2020-01-01T00:00:00</LastChange></Metadata>"
        '<Page imageFilename="p.png" imageWidth="2000" imageHeight="2000">'
        '<TextRegion id="r1"><Coords points="0,0 1000,0 1000,200 0,200"/>'
        f'<TextLine id="ln1"><Coords points="{line_points}"/>{body}'
        f"<TextEquiv><Unicode>{line_text}</Unicode></TextEquiv></TextLine>"
        f"{extra}</TextRegion></Page></PcGts>"
    )


def _rewrite(tmp_path: Path, xml: str, corrected: str):
    path = tmp_path / "p.xml"
    path.write_text(xml, encoding="utf-8")
    doc = build_document_manifest([(path, path.name)])
    next(
        ln for ln in doc.pages[0].lines if ln.line_id == "ln1"
    ).corrected_text = corrected
    result = rewrite_page_file(path, doc.pages, "prov", "mdl")
    root = etree.fromstring(result.xml_bytes)
    line = next(el for el in root.iter(f"{{{NS}}}TextLine") if el.get("id") == "ln1")
    words = [
        (
            w.get("id"),
            w.find(f"{{{NS}}}TextEquiv/{{{NS}}}Unicode").text,
            w.find(f"{{{NS}}}Coords").get("points"),
        )
        for w in line.iter(f"{{{NS}}}Word")
    ]
    return result, words


def _rect(x0: int, x1: int, y0: int = 0, y1: int = 20) -> str:
    return f"{x0},{y0} {x1},{y0} {x1},{y1} {x0},{y1}"


LINE = _rect(0, 400)
THREE = [("un", _rect(0, 30)), ("dela", _rect(50, 110)), ("fin", _rect(130, 180))]


# --------------------------------------------------------------------------
# cutting a polygon
# --------------------------------------------------------------------------


def test_a_rectangle_cut_between_two_abscissae_is_the_rectangle_between_them() -> None:
    pts = [(0, 0), (100, 0), (100, 20), (0, 20)]
    assert sorted(cut(pts, 30, 60) or []) == sorted(
        [(30, 0), (60, 0), (60, 20), (30, 20)]
    )


def test_a_skewed_polygon_is_cut_along_its_own_slope() -> None:
    """The line rises by 10 over 100: a word cut out of it rises with it.
    This is the whole answer to "word polygons on a skewed line"."""
    pts = [(0, 10), (100, 0), (100, 20), (0, 30)]
    got = cut(pts, 50, 100)
    assert got is not None
    assert (50, 5) in got and (50, 25) in got  # the cut follows the slope
    assert (100, 0) in got and (100, 20) in got


def test_cutting_outside_a_polygon_yields_nothing() -> None:
    assert cut([(0, 0), (100, 0), (100, 20), (0, 20)], 200, 300) is None


# --------------------------------------------------------------------------
# the slow path
# --------------------------------------------------------------------------


def test_a_split_word_is_its_own_polygon_cut_in_two(tmp_path: Path) -> None:
    result, words = _rewrite(tmp_path, _page(LINE, THREE), "un de la fin")
    assert [w[1] for w in words] == ["un", "de", "la", "fin"]
    # the untouched words keep their element and their polygon (P1)
    assert words[0] == ("w0", "un", _rect(0, 30))
    assert words[3] == ("w2", "fin", _rect(130, 180))
    # the split word gives way to two new elements inside its old polygon
    de = [int(p.split(",")[0]) for p in words[1][2].split()]
    la = [int(p.split(",")[0]) for p in words[2][2].split()]
    assert min(de) == 50 and max(la) == 110
    assert max(de) <= min(la)
    assert words[1][0] not in {"w0", "w1", "w2"} and words[1][0] != words[2][0]
    assert result.metrics.words_dropped == 1  # "dela", and only it
    assert result.metrics.words_rebuilt == 2


def test_two_merged_words_take_the_line_between_their_outer_edges(
    tmp_path: Path,
) -> None:
    four = [
        ("un", _rect(0, 30)),
        ("de", _rect(50, 75)),
        ("la", _rect(85, 110)),
        ("fin", _rect(130, 180)),
    ]
    result, words = _rewrite(tmp_path, _page(LINE, four), "un dela fin")
    assert [w[1] for w in words] == ["un", "dela", "fin"]
    xs = [int(p.split(",")[0]) for p in words[1][2].split()]
    assert (min(xs), max(xs)) == (50, 110)
    assert result.metrics.words_dropped == 2 and result.metrics.words_rebuilt == 1


def test_a_split_on_a_skewed_line_yields_skewed_words(tmp_path: Path) -> None:
    skew = "0,40 400,0 400,20 0,60"
    words_in = [
        ("un", "0,40 30,37 30,57 0,60"),
        ("dela", "50,35 110,29 110,49 50,55"),
        ("fin", "130,27 180,22 180,42 130,47"),
    ]
    _, words = _rewrite(tmp_path, _page(skew, words_in), "un de la fin")
    de = [tuple(int(v) for v in p.split(",")) for p in words[1][2].split()]
    # the left edge of "de" is the left edge of "dela", slope included
    assert (50, 35) in de and (50, 55) in de
    ys_at_cut = sorted(y for x, y in de if x == max(x for x, _ in de))
    assert 29 < ys_at_cut[0] < 35 and 49 < ys_at_cut[-1] < 55


def test_a_kept_word_whose_text_is_corrected_keeps_its_polygon(tmp_path: Path) -> None:
    """``dela`` split AND ``fln`` corrected to ``fin``: the second is a kept
    word, text updated in place like the fast path would."""
    src = [("un", _rect(0, 30)), ("dela", _rect(50, 110)), ("fln", _rect(130, 180))]
    _, words = _rewrite(tmp_path, _page(LINE, src), "un de la fin")
    assert words[3] == ("w2", "fin", _rect(130, 180))


# --------------------------------------------------------------------------
# what is refused: the Words go, as they always did
# --------------------------------------------------------------------------


def _all_dropped(result, words) -> bool:
    return not words and result.metrics.words_rebuilt == 0


def test_a_word_without_readable_points_stops_the_rebuild(tmp_path: Path) -> None:
    xml = _page(LINE, THREE).replace(
        f'points="{_rect(50, 110)}"', 'points="not,a polygon"'
    )
    result, words = _rewrite(tmp_path, xml, "un de la fin")
    assert _all_dropped(result, words)
    assert result.metrics.words_dropped == 3


def test_words_not_laid_out_left_to_right_stop_the_rebuild(tmp_path: Path) -> None:
    """A right-to-left script, a vertical line: abscissae say nothing."""
    backwards = list(reversed(THREE))
    result, words = _rewrite(tmp_path, _page(LINE, backwards), "fin de la un")
    assert _all_dropped(result, words)

    stacked = [
        ("un", _rect(0, 30)),
        ("dela", _rect(0, 30, 30, 60)),
        ("fin", _rect(0, 30, 60, 90)),
    ]
    result, words = _rewrite(
        tmp_path, _page(_rect(0, 30, 0, 90), stacked), "un de la fin"
    )
    assert _all_dropped(result, words)
    assert result.metrics.words_dropped == 3


def test_the_new_ids_do_not_collide_with_ids_already_in_the_document(
    tmp_path: Path,
) -> None:
    extra = (
        '<TextLine id="ln1_w0"><Coords points="0,100 400,100 400,120 0,120"/>'
        "<TextEquiv><Unicode>autre</Unicode></TextEquiv></TextLine>"
    )
    result, words = _rewrite(tmp_path, _page(LINE, THREE, extra=extra), "un de la fin")
    ids = [w[0] for w in words]
    assert len(set(ids)) == 4 and "ln1_w0" not in ids
    root = etree.fromstring(result.xml_bytes)
    all_ids = [el.get("id") for el in root.iter() if el.get("id")]
    assert len(all_ids) == len(set(all_ids))


def test_polygon_refuses_what_it_cannot_read() -> None:
    def word(points: str) -> etree._Element:
        return etree.fromstring(
            f'<Word xmlns="{NS}"><Coords points="{points}"/></Word>'
        )

    assert polygon(word("0,0 10,0 10,10"), NS) == [(0, 0), (10, 0), (10, 10)]
    assert polygon(word("0,0 10,0"), NS) is None  # two points are not a polygon
    assert polygon(word("0;0 10;0 10;10"), NS) is None
    assert polygon(etree.fromstring(f'<Word xmlns="{NS}"/>'), NS) is None


@pytest.mark.parametrize(
    "corrected", ["un de la fin", "un dela et fin", "et un dela fin"]
)
def test_the_rewritten_line_reads_as_the_correction(
    tmp_path: Path, corrected: str
) -> None:
    from saknussemm.formats.page.rewriter import extract_output_texts

    result, words = _rewrite(tmp_path, _page(LINE, THREE), corrected)
    assert extract_output_texts(result.xml_bytes, {"ln1"})["ln1"] == corrected
    assert " ".join(w[1] for w in words) == corrected
    # reading order: the words are laid out left to right in the file
    lefts = [min(int(p.split(",")[0]) for p in w[2].split()) for w in words]
    assert lefts == sorted(lefts)
