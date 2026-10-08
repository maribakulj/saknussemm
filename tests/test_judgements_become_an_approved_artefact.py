"""A reviewer's judgements become an approved XML, verified like a run's.

``review_required`` delivers the candidate and changes no byte; recording a
verdict changed nothing either (contre-revue du 7/10/2026). ``approve``
re-renders under the amended decisions and runs the projection invariant
against them, so an approved file says what the reviewer decided or is
withheld.
"""

from __future__ import annotations

import pytest
from lxml import etree

from saknussemm.approval import (
    ApprovedResult,
    Judgement,
    Verdict,
    approve,
    approve_sync,
)
from saknussemm.core.identity import LineRef
from saknussemm.core.pipeline import CorrectionPipeline
from saknussemm.core.schemas import HyphenRole, LineManifest, LineStatus
from saknussemm.errors import ConfigurationError
from saknussemm.formats.loader import build_document_manifest
from tests._paths import EXAMPLES
from tests._pipeline_harness import DictProvider, RecordingObserver

_FIXTURE = "X0000002.xml"
_NS = "http://www.loc.gov/standards/alto/ns-v3#"


def _run(corrections: dict[str, str]):
    path = EXAMPLES / _FIXTURE
    doc = build_document_manifest([(path, _FIXTURE)])
    pipeline = CorrectionPipeline.for_provider(
        DictProvider(corrections), api_key="k", model="m", observer=RecordingObserver()
    )
    result = pipeline.run_sync(document_manifest=doc, source_files={_FIXTURE: path})
    return doc, {_FIXTURE: path}, result


def _ordinary_line(doc) -> LineManifest:
    for page in doc.pages:
        for lm in page.lines:
            if len(lm.ocr_text) > 25 and lm.hyphen_role is HyphenRole.NONE:
                return lm
    raise AssertionError("fixture carries no ordinary line long enough")


def _line_text(xml: bytes, line_id: str) -> str:
    root = etree.fromstring(xml)
    (line,) = [el for el in root.iter(f"{{{_NS}}}TextLine") if el.get("ID") == line_id]
    return " ".join(s.get("CONTENT", "") for s in line.iter(f"{{{_NS}}}String"))


@pytest.fixture(scope="module")
def referred():
    """A run with one referred line (a digit appeared), everything else untouched."""
    doc, _, _ = _run({})
    line = _ordinary_line(doc)
    proposal = f"{line.ocr_text} en 1789"
    doc, sources, result = _run({line.line_id: proposal})
    ref = LineRef(page_id=line.page_id, line_id=line.line_id)
    assert result.decisions.by_ref[ref].status is LineStatus.REVIEW_REQUIRED
    return doc, sources, result, line, proposal, ref


def test_an_unreviewed_referral_is_reverted_not_delivered_as_approved(referred) -> None:
    doc, sources, result, line, proposal, ref = referred
    approved = approve_sync(doc, sources, result, [])
    assert isinstance(approved, ApprovedResult)
    assert approved.unreviewed == (ref,)
    assert approved.applied == 0
    assert approved.pulled_by_unit == ()
    decision = approved.decisions.by_ref[ref]
    assert decision.status is LineStatus.FALLBACK
    assert decision.fallback_reason == "human: unreviewed"
    assert _line_text(approved.corrected_files[_FIXTURE], line.line_id) == line.ocr_text


def test_an_accepted_referral_is_delivered_as_corrected(referred) -> None:
    doc, sources, result, line, proposal, ref = referred
    approved = approve_sync(
        doc, sources, result, [Judgement(ref.page_id, ref.line_id, Verdict.ACCEPTED)]
    )
    assert approved.unreviewed == ()
    assert approved.decisions.by_ref[ref].status is LineStatus.CORRECTED
    assert _line_text(approved.corrected_files[_FIXTURE], line.line_id) == proposal
    assert approved.undeliverable_files == {}


def test_a_refused_correction_goes_back_to_the_source(referred) -> None:
    doc, sources, result, line, proposal, ref = referred
    approved = approve_sync(
        doc, sources, result, [Judgement(ref.page_id, ref.line_id, Verdict.REFUSED)]
    )
    decision = approved.decisions.by_ref[ref]
    assert decision.status is LineStatus.FALLBACK
    assert decision.fallback_reason == "human: refused"
    assert _line_text(approved.corrected_files[_FIXTURE], line.line_id) == line.ocr_text


def test_a_transcription_is_the_text_the_file_carries(referred) -> None:
    doc, sources, result, line, proposal, ref = referred
    reading = f"{line.ocr_text} en 1788"
    approved = approve_sync(
        doc,
        sources,
        result,
        [
            Judgement(
                ref.page_id, ref.line_id, Verdict.TRANSCRIBED, transcription=reading
            )
        ],
    )
    decision = approved.decisions.by_ref[ref]
    assert decision.status is LineStatus.CORRECTED
    assert decision.fallback_reason is None
    assert approved.verdicts == {ref: Verdict.TRANSCRIBED}
    assert _line_text(approved.corrected_files[_FIXTURE], line.line_id) == reading


def test_deliver_keeps_an_unreviewed_candidate_and_says_so(referred) -> None:
    doc, sources, result, line, proposal, ref = referred
    approved = approve_sync(doc, sources, result, [], unreviewed="deliver")
    assert approved.unreviewed == (ref,)
    assert approved.unreviewed_policy == "deliver"
    assert approved.decisions.by_ref[ref].status is LineStatus.REVIEW_REQUIRED
    assert _line_text(approved.corrected_files[_FIXTURE], line.line_id) == proposal


def test_the_approved_file_names_the_review_in_its_provenance(referred) -> None:
    doc, sources, result, line, proposal, ref = referred
    approved = approve_sync(
        doc, sources, result, [Judgement(ref.page_id, ref.line_id, Verdict.ACCEPTED)]
    )
    root = etree.fromstring(approved.corrected_files[_FIXTURE])
    steps = [el.text or "" for el in root.iter(f"{{{_NS}}}processingStepDescription")]
    assert any("human-review" in step for step in steps), steps


def test_a_judgement_on_an_unknown_line_is_refused_before_rendering(referred) -> None:
    doc, sources, result, *_ = referred
    with pytest.raises(ConfigurationError, match="does not have"):
        approve_sync(
            doc, sources, result, [Judgement("P0", "nowhere", Verdict.ACCEPTED)]
        )


def test_a_transcription_needs_its_text(referred) -> None:
    doc, sources, result, line, proposal, ref = referred
    with pytest.raises(ConfigurationError, match="without a transcription"):
        approve_sync(
            doc,
            sources,
            result,
            [Judgement(ref.page_id, ref.line_id, Verdict.TRANSCRIBED)],
        )


def test_the_callers_manifest_is_not_mutated(referred) -> None:
    doc, sources, result, line, proposal, ref = referred
    before = doc.model_dump()
    approve_sync(
        doc, sources, result, [Judgement(ref.page_id, ref.line_id, Verdict.REFUSED)]
    )
    assert doc.model_dump() == before


def test_write_refuses_an_incomplete_set_by_default(tmp_path) -> None:
    approved = ApprovedResult(
        corrected_files={"a.xml": b"<alto/>"},
        undeliverable_files={"b.xml": "diverged"},
        decisions=None,  # type: ignore[arg-type]
        verdicts={},
        unreviewed=(),
        unreviewed_policy="revert",
        pulled_by_unit=(),
        traces={},
    )
    with pytest.raises(ConfigurationError, match="allow_partial"):
        approved.write(tmp_path)
    assert [p.name for p in approved.write(tmp_path, allow_partial=True)] == ["a.xml"]


# -- the reviewer's answer is verified against THIS document ----------------


def test_a_result_from_another_document_is_refused(referred, tmp_path) -> None:
    doc, sources, result, line, proposal, ref = referred
    other = doc.model_copy(deep=True)
    other.pages[0].lines[0].ocr_text = "ZZZZ " + other.pages[0].lines[0].ocr_text
    with pytest.raises(ConfigurationError, match="as it reads now"):
        approve_sync(other, sources, result, [])


def test_two_judgements_on_one_line_are_refused(referred) -> None:
    doc, sources, result, line, proposal, ref = referred
    with pytest.raises(ConfigurationError, match="one line, one verdict"):
        approve_sync(
            doc,
            sources,
            result,
            [
                Judgement(ref.page_id, ref.line_id, Verdict.ACCEPTED),
                Judgement(ref.page_id, ref.line_id, Verdict.REFUSED),
            ],
        )


def test_approve_is_awaitable_from_a_running_loop(referred) -> None:
    import asyncio

    doc, sources, result, line, proposal, ref = referred

    async def handler():
        return await approve(
            doc,
            sources,
            result,
            [Judgement(ref.page_id, ref.line_id, Verdict.ACCEPTED)],
        )

    approved = asyncio.run(handler())
    assert approved.decisions.by_ref[ref].status is LineStatus.CORRECTED


def test_the_traces_carry_this_renders_projection(referred) -> None:
    doc, sources, result, line, proposal, ref = referred
    approved = approve_sync(
        doc, sources, result, [Judgement(ref.page_id, ref.line_id, Verdict.REFUSED)]
    )
    trace = approved.traces[ref]
    assert trace.output_alto_text == line.ocr_text
    assert trace.projection_fidelity is not None
    # the run's own traces were not touched
    assert result.traces[ref].output_alto_text == proposal


# -- a hyphen unit stays one thing (ADR-010) ---------------------------------


@pytest.fixture(scope="module")
def referred_pair():
    """A referred hyphen unit: the correction on PART1, every other member
    pulled into review with it, as test_review_pass pins. The fixture's
    first unit is a three-line chain (PART1 → BOTH → PART2)."""
    from saknussemm.core.units import derive_hyphen_groups, hyphen_group_by_line

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
