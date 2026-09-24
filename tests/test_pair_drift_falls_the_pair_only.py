"""Stage A refuses a hyphen pair on every attempt: the PAIR falls, the rest stands (VR-10)."""

from __future__ import annotations

import asyncio
from typing import Any

from saknussemm import CorrectionPipeline, RetryPolicy
from saknussemm.core.editing import EditScript, ReplaceLine
from saknussemm.core.protocols import ProducerMetadata
from saknussemm.formats.loader import build_document_manifest
from tests._paths import EXAMPLES

_SAMPLE = EXAMPLES / "sample.xml"


class _Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def on_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events.append((event_type, payload))


class _CollapsesPart2:
    """Capitalises every line, and answers ONE word for a PART2 line —
    the garbled-second-half behaviour measured on 1930s press."""

    wants_geometry = False
    wants_image = False
    requires_full_coverage = True

    def __init__(self) -> None:
        self.metadata = ProducerMetadata(name="collapse", implementation="test")
        self.calls = 0
        self.part2: set[str] = set()

    async def produce(self, payload: Any, *, options: Any) -> tuple[EditScript, None]:
        self.calls += 1
        ops = []
        for ln in payload.lines:
            text = ln.ocr_text[:1].upper() + ln.ocr_text[1:]
            if ln.hyphenation_role == "HypPart2" and len(ln.ocr_text.split()) >= 3:
                text = ln.ocr_text.split()[0]
                self.part2.add(ln.line_id)
            ops.append(ReplaceLine(line_id=ln.line_id, text=text))
        return EditScript(ops=ops), None


def test_the_pair_falls_alone_and_the_chunk_is_corrected() -> None:
    doc = build_document_manifest([(_SAMPLE, _SAMPLE.name)])
    producer, rec = _CollapsesPart2(), _Recorder()
    pipeline = CorrectionPipeline(
        producer=producer, observer=rec, retry_policy=RetryPolicy.deterministic()
    )
    result = asyncio.run(
        pipeline.run(document_manifest=doc, source_files={_SAMPLE.name: _SAMPLE})
    )
    assert producer.part2, "the fixture must hold a hyphen pair with a 3+ word PART2"
    reasons = result.fallback_reasons
    assert reasons.get("pair_drift_fallback", 0) >= 2  # both members of the pair
    assert "all_attempts_exhausted" not in "".join(reasons)
    # The other lines were corrected, not sacrificed with the pair.
    corrected = [d for d in result.decisions.decisions if d.status.value == "corrected"]
    assert len(corrected) > 0
    # Attempts 1 and 2 still ran on every chunk that holds such a pair (the
    # retry ladder is unchanged); the third settles it. Never a downgrade.
    kinds = [t for t, _ in rec.events]
    chunks_with_pair = reasons["pair_drift_fallback"] // 2
    assert kinds.count("retry") == 2 * chunks_with_pair
    assert "chunk_downgraded" not in kinds
    assert any(
        "pair_drift_fallback" in str(p.get("message", ""))
        for t, p in rec.events
        if t == "warning"
    )
