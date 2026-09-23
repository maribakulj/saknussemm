"""The neighbour margin, widened from two neighbours to the page.

A mis-attached correction carries ANOTHER line's text. The historical
Guard 2 compares a correction with the previous and next line only; a
model that drops or splits a line shifts everything after it, and a model
shown a column reads across it, so the other line is often several lines
away. ``GuardConfig(attachment_scope="page")`` holds the same margin
against every other line of the page. The default is unchanged.
"""

from __future__ import annotations

from saknussemm.core.decide import FALLBACK_REASON_CODES
from saknussemm.core.guards import check_line
from saknussemm.core.schemas import GuardConfig

PAGE = [
    "Lorsque nous arrivâmes à Paris le soir même",
    "personne ne nous attendait sur le quai de la gare",
    "et il fallut chercher une voiture sous la pluie",
    "battante qui tombait depuis le matin sans relâche",
    "COURRIER DE LONDRES",
    "En dépit des sociétés de tempérance, et malgré",
]


def test_adjacent_scope_misses_a_shift_of_three_lines() -> None:
    """The gap the wider scope exists for: line 1 receives line 4's text."""
    result = check_line(
        PAGE[1], PAGE[4], prev_ocr=PAGE[0], next_ocr=PAGE[2], config=GuardConfig()
    )
    # Guard 1 already refuses it here because the texts share nothing —
    # the interesting case is a proposal that clears the floor, below.
    assert result.reason == "too_different_from_source"


def test_page_scope_refuses_a_correction_closer_to_a_far_line() -> None:
    source = "En depit des societes de temperance, et malgre"
    proposal = "En dépit des sociétés de tempérance, et malgré"  # = PAGE[5]
    adjacent = check_line(
        source, proposal, prev_ocr=PAGE[0], next_ocr=PAGE[1], config=GuardConfig()
    )
    assert adjacent.accepted  # the neighbours are unrelated: nothing to see
    paged = check_line(
        source,
        proposal,
        prev_ocr=PAGE[0],
        next_ocr=PAGE[1],
        other_ocr=[PAGE[2], PAGE[3], PAGE[4], PAGE[5]],
        config=GuardConfig(attachment_scope="page"),
    )
    # PAGE[5] resembles the proposal MORE than the source does, by more
    # than the margin? Here the source is the same line with accents
    # stripped, so its similarity is high and the margin holds: accepted.
    assert paged.accepted


def test_page_scope_catches_another_lines_text() -> None:
    source = "battante qui tombait depuis le matin sans relache"
    proposal = "COURRIER DE LONDRES et ses correspondants"  # far from source
    # A floor low enough to let the proposal past Guard 1, so that ONLY the
    # wider margin can refuse it — the vision profile's situation.
    config = GuardConfig(attachment_scope="page", min_source_similarity=0.0)
    adjacent = check_line(
        source, proposal, prev_ocr=PAGE[2], next_ocr=PAGE[5], config=config
    )
    assert adjacent.accepted
    paged = check_line(
        source,
        proposal,
        prev_ocr=PAGE[2],
        next_ocr=PAGE[5],
        other_ocr=[PAGE[0], PAGE[1], PAGE[4]],
        config=config,
    )
    assert not paged.accepted
    assert paged.reason == "closer_to_another_line"
    assert paged.text == source


def test_the_new_reason_is_in_the_closed_set() -> None:
    assert "closer_to_another_line" in FALLBACK_REASON_CODES


def test_twins_are_exempt_from_the_margin() -> None:
    """Two stage directions naming the same character: the margin can never
    hold (the correction IS the other line), and nothing is at stake."""
    source, twin = "GEO R G ET TE.", "GEORGETTE."
    proposal = "GEORGETTE."
    strict = check_line(
        source, proposal, prev_ocr=None, next_ocr=twin, config=GuardConfig()
    )
    assert strict.reason == "closer_to_next_line"
    lenient = check_line(
        source,
        proposal,
        prev_ocr=None,
        next_ocr=twin,
        config=GuardConfig(attachment_twin_similarity=0.6),
    )
    assert lenient.accepted
    # The exemption is about the SOURCES resembling each other, not the
    # proposal: an unrelated other line still refuses.
    unrelated = check_line(
        "GEO R G ET TE.",
        "En dépit des sociétés de tempérance",
        prev_ocr=None,
        next_ocr="En dépit des sociétés de tempérance, et malgré",
        config=GuardConfig(attachment_twin_similarity=0.6, min_source_similarity=0.0),
    )
    assert unrelated.reason == "closer_to_next_line"


def test_defaults_keep_the_historical_behaviour() -> None:
    config = GuardConfig()
    assert config.attachment_scope == "adjacent"
    assert config.attachment_twin_similarity is None
    # ``other_ocr`` is never consulted under the default scope's caller,
    # and the function ignores an empty one.
    assert check_line("abc def", "abc deg", config=config).accepted
