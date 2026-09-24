"""A reconciled hyphen member faces the floor and the margin too (VR-11).

Stage B judges the two halves of a cut word against each other and
nothing else. Until VR-11 a member it accepted skipped ``check_line``
entirely, so a PART1 carrying ANOTHER line's text — ``ce que notre grand
mor-`` under a source reading ``au. nt comme orateur, 'une situation
in-``, while the page held an OCR line ``ce que notre grand mo`` — was
delivered as corrected (NewsEye 0253902, composite arm, 2026-09-24).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from saknussemm import CorrectionPipeline, GuardConfig, RetryPolicy
from saknussemm.core.acceptance import _apply_line_acceptance
from saknussemm.core.editing import EditScript, ReplaceLine
from saknussemm.core.identity import line_ref
from saknussemm.core.protocols import ProducerMetadata
from saknussemm.core.schemas import HyphenRole, LineStatus
from saknussemm.formats.loader import build_document_manifest
from tests.decision._state import document, line

_NS = 'xmlns="http://www.loc.gov/standards/alto/ns-v3#"'
_LINES = (
    "ce que notre grand mo",
    "vait parler encore",
    "au nt comme orateur in-",  # PART1, heuristic (no SUBS)
    "comparable et une autorité",
)


def _alto() -> str:
    def strings(i: int, text: str) -> str:
        words = text.split()
        parts = []
        for j, w in enumerate(words):
            x = 10 + 40 * j
            parts.append(
                f'<String ID="L{i}w{j}" CONTENT="{w}" HPOS="{x}" VPOS="{10 + 30 * i}" WIDTH="35" HEIGHT="20"/>'
            )
            if j < len(words) - 1:
                parts.append(f'<SP HPOS="{x + 35}" VPOS="{10 + 30 * i}" WIDTH="5"/>')
        return "".join(parts)

    body = "".join(
        f'<TextLine ID="L{i}" HPOS="10" VPOS="{10 + 30 * i}" WIDTH="500" HEIGHT="20">'
        + strings(i, text)
        + "</TextLine>"
        for i, text in enumerate(_LINES, start=1)
    )
    return (
        f'<alto {_NS}><Layout><Page ID="p1" WIDTH="600" HEIGHT="200"><PrintSpace>'
        f'<TextBlock ID="b1">{body}</TextBlock></PrintSpace></Page></Layout></alto>'
    )


class _Silent:
    def on_event(self, event_type: str, payload: dict[str, Any]) -> None:
        pass


class _ReadsAcross:
    """Answers, for the PART1 line, the text of a line three lines up."""

    wants_geometry = False
    wants_image = False
    requires_full_coverage = True

    def __init__(self) -> None:
        self.metadata = ProducerMetadata(name="across", implementation="test")

    async def produce(self, payload: Any, *, options: Any) -> tuple[EditScript, None]:
        ops = [
            ReplaceLine(
                line_id=ln.line_id,
                text="ce que notre grand mor-" if ln.line_id == "L3" else ln.ocr_text,
            )
            for ln in payload.lines
        ]
        return EditScript(ops=ops), None


def test_a_member_carrying_another_lines_text_falls_with_its_unit(
    tmp_path: Path,
) -> None:
    src = tmp_path / "p.xml"
    src.write_text(_alto(), encoding="utf-8")
    doc = build_document_manifest([(src, src.name)])
    roles = {lm.line_id: lm.hyphen_role for lm in doc.pages[0].lines}
    assert roles["L3"] is HyphenRole.PART1 and roles["L4"] is HyphenRole.PART2
    pipeline = CorrectionPipeline(
        producer=_ReadsAcross(),
        observer=_Silent(),
        guard_config=GuardConfig(attachment_scope="page"),
        retry_policy=RetryPolicy.deterministic(),
    )
    result = asyncio.run(
        pipeline.run(document_manifest=doc, source_files={src.name: src})
    )
    by_id = {d.ref.line_id: d for d in result.decisions.decisions}
    assert by_id["L3"].status is LineStatus.FALLBACK
    assert by_id["L3"].fallback_reason == "closer_to_another_line"
    # The unit falls whole (ADR-010).
    assert by_id["L4"].status is LineStatus.FALLBACK
    assert by_id["L4"].fallback_reason == "hyphen_unit_fallback"
    assert "grand mor-" not in next(iter(result.corrected_files.values())).decode()


def test_only_the_members_named_reconciled_are_revisited() -> None:
    """An already-decided line stays decided (I-1); a reconciled member
    whose text passes the floor and the margin stands untouched."""
    tail = line(1, "pav-", "par-")
    head = line(2, "tir", "tir")
    tail.hyphen_role, head.hyphen_role = HyphenRole.PART1, HyphenRole.PART2
    tail.hyphen_pair_line_id, head.hyphen_pair_line_id = head.line_id, tail.line_id
    other = line(3, "aaa", "ZZZZ QQQQ")  # decided elsewhere, never revisited
    _, _, traces = document([tail, head, other])
    _apply_line_acceptance(
        guard_config=GuardConfig(),
        chunk_lines=[tail, head, other],
        text_by_id={},
        all_lines_by_id={lm.line_id: lm for lm in (tail, head, other)},
        traces=traces,
        reconciled=frozenset({line_ref(tail), line_ref(head)}),
    )
    assert (tail.corrected_text, head.corrected_text) == ("par-", "tir")
    assert other.corrected_text == "ZZZZ QQQQ"
    assert all(
        traces[line_ref(lm)].fallback_reason is None for lm in (tail, head, other)
    )
