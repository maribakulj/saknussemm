"""Re-cutting a returned page onto its source lines, character-wise.

The strategy exists because Jaccard refuses exactly the lines a correction
helped most — a split word shares no token with its source. What it gives up
is the refusal itself: it assumes the stream is in order and always produces
something. Both halves are pinned here.
"""

from __future__ import annotations

from saknussemm.core.page_alignment import align_page_lines, reproject_page_lines

SOURCE = [
    "Maisiepenfois quel'vne",
    "& l'autre eftoient des",
    "dons de l'elprit",
]
CORRECTED = [
    "Mais ie penſois que l'vne",
    "& l'autre eſtoient des",
    "dons de l'eſprit",
]


def test_the_empty_control_returns_the_source_untouched() -> None:
    """Re-cutting an UNCORRECTED page must give the source back verbatim.

    The only check that catches a cutting bug without a model in the loop:
    whatever the re-cut deforms, it deforms here too. Measured on the
    9-page corpus: 251/251.
    """
    assert reproject_page_lines(SOURCE, SOURCE) == tuple(SOURCE)


def test_a_split_word_keeps_its_line_where_jaccard_refuses() -> None:
    """The case the token alignment cannot settle.

    ``Maisiepenfois`` becomes ``Mais ie penſois``: no shared token, so
    Jaccard will not vouch for the line and it keeps its OCR text. The
    characters are the same, so the re-cut follows.
    """
    out = reproject_page_lines(SOURCE, CORRECTED)
    assert "penſois" in out[0]
    assert "eſtoient" in out[1]
    assert "eſprit" in out[2]

    matched = align_page_lines(SOURCE, CORRECTED).matched
    assert matched[0] is None, "ce test ne vaut que si Jaccard refuse bien ici"


def test_every_source_line_gets_exactly_one_text() -> None:
    """Whatever the model returned, the count out equals the count in.

    A whole-page correction returns the wrong line count on 2 to 4 pages out
    of 9; absorbing that is this function's reason to exist.
    """
    for returned in (
        CORRECTED,
        ["tout sur une seule ligne " + " ".join(CORRECTED)],
        CORRECTED + ["une ligne en trop", "et une autre"],
        [],
    ):
        assert len(reproject_page_lines(SOURCE, returned)) == len(SOURCE)


def test_the_cuts_never_walk_backwards() -> None:
    """Or a line would receive text already given to its neighbour.

    Pinned with a returned page sharing nothing with the source, which is
    where a non-monotonic mapping would show up as duplication.
    """
    out = reproject_page_lines(SOURCE, ["rien a voir", "du tout"])
    assert sum(len(t) for t in out) <= len("rien a voir\ndu tout")


def test_an_empty_source_is_empty() -> None:
    assert reproject_page_lines([], ["quoi que ce soit"]) == ()
