"""A hyphen unit stays one thing under ``approve`` too (ADR-010).

The reviewer's verdicts are applied per line; a refused or unreviewed
member pulls its whole unit back to the source, and transcribing a single
member is refused before rendering. The fixture's first unit is a
three-line chain (PART1 → BOTH → PART2).
"""

from __future__ import annotations

import pytest

from saknussemm.approval import Judgement, Verdict, approve_sync
from saknussemm.core.identity import LineRef
from saknussemm.core.schemas import HyphenRole, LineStatus
from saknussemm.core.units import derive_hyphen_groups, hyphen_group_by_line
from saknussemm.errors import ConfigurationError
from tests.test_judgements_become_an_approved_artefact import _FIXTURE, _line_text, _run


@pytest.fixture(scope="module")
def referred_pair():
    """A referred hyphen unit: the correction on PART1, every other member
    pulled into review with it, as test_review_pass pins. The fixture's
    first unit is a three-line chain (PART1 → BOTH → PART2)."""
    doc, _, _ = _run({})
    part1 = next(
        (
            lm
            for page in doc.pages
            for lm in page.lines
            if lm.hyphen_role is HyphenRole.PART1 and lm.hyphen_pair_line_id
        ),
        None,
    )
    if part1 is None:  # pragma: no cover
        pytest.skip("fixture carries no hyphen pair")
    proposal = f"1789 {part1.ocr_text}"
    doc, sources, result = _run({part1.line_id: proposal})
    first = LineRef(page_id=part1.page_id, line_id=part1.line_id)
    by_line = hyphen_group_by_line(
        derive_hyphen_groups(lm for page in doc.pages for lm in page.lines)
    )
    members = by_line[first].members
    second = members[1]
    if result.decisions.by_ref[first].status is not LineStatus.REVIEW_REQUIRED:
        pytest.skip("the pair reconciler refused this proposal before referral")
    assert all(
        result.decisions.by_ref[m].status is LineStatus.REVIEW_REQUIRED for m in members
    )
    return doc, sources, result, first, second, proposal, members


def test_accepting_one_half_only_pulls_the_unit_back_to_the_source(
    referred_pair,
) -> None:
    doc, sources, result, first, second, proposal, members = referred_pair
    approved = approve_sync(
        doc,
        sources,
        result,
        [Judgement(first.page_id, first.line_id, Verdict.ACCEPTED)],
    )
    assert approved.decisions.by_ref[second].fallback_reason == "human: unreviewed"
    assert approved.decisions.by_ref[first].status is LineStatus.FALLBACK
    assert approved.decisions.by_ref[first].fallback_reason == "human: unit atomicity"
    assert approved.pulled_by_unit == (first,)
    assert set(approved.unreviewed) == set(members) - {first}
    assert _line_text(approved.corrected_files[_FIXTURE], first.line_id) != proposal


def test_refusing_one_half_pulls_the_other(referred_pair) -> None:
    doc, sources, result, first, second, proposal, members = referred_pair
    judgements = [Judgement(m.page_id, m.line_id, Verdict.ACCEPTED) for m in members]
    judgements[1] = Judgement(second.page_id, second.line_id, Verdict.REFUSED)
    approved = approve_sync(doc, sources, result, judgements)
    assert approved.decisions.by_ref[second].fallback_reason == "human: refused"
    for m in members:
        if m != second:
            assert (
                approved.decisions.by_ref[m].fallback_reason == "human: unit atomicity"
            )
    assert approved.unreviewed == ()
    assert approved.undeliverable_files == {}


def test_accepting_both_halves_delivers_the_unit(referred_pair) -> None:
    doc, sources, result, first, second, proposal, members = referred_pair
    approved = approve_sync(
        doc,
        sources,
        result,
        [Judgement(m.page_id, m.line_id, Verdict.ACCEPTED) for m in members],
    )
    for m in members:
        assert approved.decisions.by_ref[m].status is LineStatus.CORRECTED
    assert approved.pulled_by_unit == ()
    assert approved.undeliverable_files == {}
    assert _line_text(approved.corrected_files[_FIXTURE], first.line_id).startswith(
        "1789 "
    )


def test_transcribing_one_half_is_refused_before_rendering(referred_pair) -> None:
    doc, sources, result, first, second, proposal, members = referred_pair
    with pytest.raises(ConfigurationError, match="hyphen unit"):
        approve_sync(
            doc,
            sources,
            result,
            [
                Judgement(
                    first.page_id, first.line_id, Verdict.TRANSCRIBED, transcription="x"
                ),
                Judgement(second.page_id, second.line_id, Verdict.ACCEPTED),
            ],
        )
