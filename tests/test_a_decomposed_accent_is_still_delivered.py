"""A model answering in NFD must not make the page undeliverable (VR-14).

Parsers read the source in NFC and the rewriters write NFC; a proposal
carrying a decomposed accent (« e » + U+0301) was decided as such, then
written precomposed, and the post-render check found the artefact
diverging from the decision. Seen on OCR17+ (Descartes, three runs).
"""

from __future__ import annotations

import asyncio
import unicodedata
from typing import Any

from saknussemm import CorrectionPipeline, RetryPolicy
from saknussemm.core.editing import EditScript, ReplaceLine, ReplaceSpan
from saknussemm.core.protocols import ProducerMetadata
from saknussemm.formats.loader import build_document_manifest
from tests._paths import EXAMPLES

_SAMPLE = EXAMPLES / "sample.xml"
_NFD = "é"  # « é » decomposed


class _Silent:
    def on_event(self, event_type: str, payload: dict[str, Any]) -> None:
        pass


class _AnswersDecomposed:
    """Replaces the first line's text by a decomposed-accent variant."""

    wants_geometry = False
    wants_image = False
    requires_full_coverage = True

    def __init__(self) -> None:
        self.metadata = ProducerMetadata(name="nfd", implementation="test")
        self.first: str | None = None

    async def produce(self, payload: Any, *, options: Any) -> tuple[EditScript, None]:
        ops = []
        for i, ln in enumerate(payload.lines):
            text = ln.ocr_text
            if i == 0 and self.first is None and "e" in text:
                text = text.replace("e", _NFD, 1)
                self.first = ln.line_id
            ops.append(ReplaceLine(line_id=ln.line_id, text=text))
        return EditScript(ops=ops), None


def test_op_text_is_held_in_nfc() -> None:
    assert ReplaceLine(line_id="L1", text=_NFD).text == "é"
    span = ReplaceSpan(
        line_id="L1", anchor={"kind": "range", "start": 0, "end": 1}, text=_NFD
    )
    assert span.text == "é"


def test_a_decomposed_answer_is_delivered_precomposed() -> None:
    doc = build_document_manifest([(_SAMPLE, _SAMPLE.name)])
    producer = _AnswersDecomposed()
    pipeline = CorrectionPipeline(
        producer=producer, observer=_Silent(), retry_policy=RetryPolicy.deterministic()
    )
    result = asyncio.run(
        pipeline.run(document_manifest=doc, source_files={_SAMPLE.name: _SAMPLE})
    )
    assert producer.first is not None
    assert not result.undeliverable_files, result.undeliverable_files
    assert _SAMPLE.name in result.corrected_files
    decided = result.decisions.by_ref
    final = next(
        d.final_text for d in decided.values() if d.ref.line_id == producer.first
    )
    assert unicodedata.normalize("NFC", final) == final
    assert "́" not in result.corrected_files[_SAMPLE.name].decode("utf-8")
