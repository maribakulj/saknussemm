"""From a reviewer's judgements to an APPROVED artefact (ADR-011 downstream).

``review_required`` changes no delivered byte: a referred line carries its
correction and declares the run could not establish it. Until now nothing
in the library turned a human's answer into a file — the demo recorded
verdicts and still handed out the candidate XML (contre-revue du
7/10/2026). This module closes that loop in the one place that can verify
it: the engine re-renders from a decision set the reviewer amended, and the
projection invariant checks the approved artefact against THOSE decisions.

What a judgement does to a line:

- ``accepted``: the run's outcome stands. A referred correction becomes a
  plain ``corrected`` one; a fallen line stays at its source text.
- ``refused``: the correction is taken away; the line goes back to its
  source text (``fallback``, reason ``human: refused``).
- ``transcribed``: the reviewer's reading replaces whatever the run did
  (``corrected``, reason ``human: transcribed``). This is the one verdict
  that can put NEW text in the file, and it says so in the decision.

A referred line NOBODY judged is not silently delivered as if approved:
by default it falls back to its source (``human: unreviewed``) and is
listed on :attr:`ApprovedResult.unreviewed`; ``unreviewed="deliver"``
keeps the candidate instead, for a host that wants a partial review to
pass through. Lines the run corrected without referral are delivered as
they were unless a judgement says otherwise.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Literal

from saknussemm.core import decide
from saknussemm.core.decisions import DecisionSet, LineDecision
from saknussemm.core.identity import LineRef, line_ref
from saknussemm.core.protocols import ProducerMetadata, RenderOutcome
from saknussemm.core.result import CorrectionResult
from saknussemm.core.schemas import DocumentManifest, LineManifest, LineStatus
from saknussemm.errors import ConfigurationError


class Verdict(str, Enum):
    """What the reader concluded — the demo's vocabulary, kept verbatim."""

    ACCEPTED = "accepted"
    REFUSED = "refused"
    TRANSCRIBED = "transcribed"


@dataclass(frozen=True)
class Judgement:
    """One reader's answer on one line, keyed as the engine keys lines."""

    page_id: str
    line_id: str
    verdict: Verdict
    #: Required for ``transcribed``: the text the reader saw on the scan.
    transcription: str | None = None

    @property
    def ref(self) -> LineRef:
        return LineRef(page_id=self.page_id, line_id=self.line_id)


@dataclass(frozen=True)
class ApprovedResult:
    """The approved artefacts and the decisions they were verified against."""

    corrected_files: dict[str, bytes]
    undeliverable_files: dict[str, str]
    decisions: DecisionSet
    #: Referred lines no judgement reached, and what was done with them.
    unreviewed: tuple[LineRef, ...]
    unreviewed_policy: str
    applied: int
    format_losses: dict[str, int] = field(default_factory=dict)

    def write(
        self, directory: str | Path, *, allow_partial: bool = False
    ) -> list[Path]:
        """Each approved XML under its source name. Refuses an incomplete
        set unless ``allow_partial=True``, like :meth:`CorrectionResult.write`."""
        if self.undeliverable_files and not allow_partial:
            names = ", ".join(sorted(self.undeliverable_files))
            raise ConfigurationError(
                f"{len(self.undeliverable_files)} approved file(s) could not be "
                f"rendered ({names}); pass allow_partial=True to write the rest"
            )
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for source_name, xml_bytes in self.corrected_files.items():
            path = target / Path(source_name).name
            path.write_bytes(xml_bytes)
            written.append(path)
        return written


def approve(
    document_manifest: DocumentManifest,
    source_files: dict[str, Path],
    result: CorrectionResult,
    judgements: Iterable[Judgement],
    *,
    unreviewed: Literal["revert", "deliver"] = "revert",
) -> ApprovedResult:
    """Re-render the run's artefacts under the reviewer's decisions.

    ``document_manifest`` and ``source_files`` are what the run was given
    (``LoadedDocument.manifest`` / ``.source_paths`` from the façade); the
    caller's manifest is never mutated. ``result`` is that run's outcome:
    its decisions are the starting point, its provenance labels the
    approved file. A judgement naming a line the document does not have,
    or ``transcribed`` without a transcription, is a configuration error
    before anything is rendered.
    """
    judged = _index(judgements)
    manifest = document_manifest.model_copy(deep=True)
    decisions: list[LineDecision] = []
    unreviewed_refs: list[LineRef] = []
    known: set[LineRef] = set()
    for page in manifest.pages:
        for lm in page.lines:
            ref = line_ref(lm)
            known.add(ref)
            before = result.decisions.by_ref.get(ref)
            if before is None:
                raise ConfigurationError(
                    f"the run's decisions carry no line ({ref.page_id!r}, "
                    f"{ref.line_id!r}): approve() needs the result of a run over "
                    "this very document"
                )
            judgement = judged.get(ref)
            if judgement is None and before.status is LineStatus.REVIEW_REQUIRED:
                unreviewed_refs.append(ref)
            decisions.append(_amend(lm, before, judgement, unreviewed))
    unknown = [r for r in judged if r not in known]
    if unknown:
        shown = ", ".join(f"({r.page_id!r}, {r.line_id!r})" for r in unknown[:5])
        raise ConfigurationError(
            f"{len(unknown)} judgement(s) name lines this document does not have: {shown}"
        )
    decision_set = DecisionSet(tuple(decisions))
    render = asyncio.run(_render(manifest, source_files, result, decision_set))
    return ApprovedResult(
        corrected_files=render.corrected_files,
        undeliverable_files=render.undeliverable,
        decisions=decision_set,
        unreviewed=tuple(unreviewed_refs),
        unreviewed_policy=unreviewed,
        applied=sum(1 for r in judged if r in known),
        format_losses=render.losses,
    )


def _index(judgements: Iterable[Judgement]) -> dict[LineRef, Judgement]:
    judged: dict[LineRef, Judgement] = {}
    for j in judgements:
        if j.verdict is Verdict.TRANSCRIBED and not (j.transcription or "").strip():
            raise ConfigurationError(
                f"judgement on ({j.page_id!r}, {j.line_id!r}) is 'transcribed' "
                "without a transcription"
            )
        judged[j.ref] = j
    return judged


def _amend(
    lm: LineManifest,
    before: LineDecision,
    judgement: Judgement | None,
    unreviewed: str,
) -> LineDecision:
    """Write one line's amended decision through ``core/decide`` (RM-01:
    the verbs are the only writers of a line's text and status) and
    return the record the artefact will be verified against."""
    status, text, reason, review = (
        before.status,
        before.final_text,
        before.fallback_reason,
        before.review_reasons,
    )
    if judgement is not None:
        if judgement.verdict is Verdict.ACCEPTED:
            if status is LineStatus.REVIEW_REQUIRED:
                status, review = LineStatus.CORRECTED, ()
        elif judgement.verdict is Verdict.REFUSED:
            status, text, reason, review = (
                LineStatus.FALLBACK,
                lm.ocr_text,
                "human: refused",
                (),
            )
        else:
            text = str(judgement.transcription)
            status, reason, review = LineStatus.CORRECTED, "human: transcribed", ()
    elif status is LineStatus.REVIEW_REQUIRED and unreviewed == "revert":
        status, text, reason, review = (
            LineStatus.FALLBACK,
            lm.ocr_text,
            "human: unreviewed",
            (),
        )

    if status is LineStatus.FALLBACK:
        decide.fall_back(lm, reason=reason or "human: unreviewed")
    else:
        decide.accept(lm, text)
        for why in review:
            decide.refer_for_review(lm, reason=why)
    return LineDecision(
        ref=before.ref,
        source_text=lm.ocr_text,
        final_text=text,
        status=status,
        fallback_reason=reason,
        review_reasons=review,
    )


async def _render(
    manifest: DocumentManifest,
    source_files: dict[str, Path],
    result: CorrectionResult,
    decisions: DecisionSet,
) -> RenderOutcome:
    from saknussemm.core.rendering import _render_outputs

    provenance = result.report.provenance
    producer = provenance.producer if provenance is not None else None
    metadata = ProducerMetadata(
        name=f"{producer.name if producer else 'unknown'}+human-review",
        version=producer.version if producer else None,
        implementation=producer.implementation if producer else None,
        configuration_fingerprint=(
            producer.configuration_fingerprint if producer else None
        ),
    )
    return await _render_outputs(
        format_adapter=None,
        producer_metadata=metadata,
        config_fingerprint=(
            provenance.config_fingerprint if provenance is not None else "unknown"
        ),
        emit=lambda event: None,
        document_manifest=manifest,
        source_files=source_files,
        traces={},
        decisions=decisions,
    )


__all__ = ["ApprovedResult", "Judgement", "Verdict", "approve"]
