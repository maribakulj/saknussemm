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
  (``corrected``). This is the one verdict that can put NEW text in the
  file; the reading keeps the source's word-break character, as a run's
  correction does (``preserve_break_char``).

A referred line NOBODY judged is not silently delivered as if approved:
by default it falls back to its source (``human: unreviewed``) and is
listed on :attr:`ApprovedResult.unreviewed`; ``unreviewed="deliver"``
keeps the candidate instead, for a host that wants a partial review to
pass through. Lines the run corrected without referral are delivered as
they were unless a judgement says otherwise.

**A hyphen unit stays one thing** (ADR-010). A refused or unreviewed member
pulls its whole unit back to the source (``human: unit atomicity`` on the
pulled members): a pair half corrected, half at its OCR text is the state
the reconciler guarantees can never survive, and a reviewer's verdict
does not get to create it. A ``transcribed`` member is refused outright —
the reading of one half cannot be reconciled with the other's
``SUBS_CONTENT`` here; transcribe outside the unit or accept/refuse it.

What this does NOT reproduce: the hyphen state the run wrote on its own
private copy (a pair that fell back had its SUBS neutralised there). The
approved file is rendered from the caller's manifest, so such a pair keeps
the source's SUBS. And the render uses the engine's default adapter: a run
made with an injected ``format_adapter`` (a word-geometry resolver, say)
must pass the same one, or its slow-path boxes are redrawn without it.
"""

from __future__ import annotations

import asyncio
import copy
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Literal

from saknussemm.core import decide
from saknussemm.core.decisions import DecisionSet, LineDecision
from saknussemm.core.identity import LineRef, line_ref
from saknussemm.core.pairing import preserve_break_char
from saknussemm.core.protocols import FormatAdapter, ProducerMetadata, RenderOutcome
from saknussemm.core.result import CorrectionResult
from saknussemm.core.schemas import (
    DocumentManifest,
    LineManifest,
    LineStatus,
    LineTrace,
)
from saknussemm.core.units import derive_hyphen_groups, hyphen_group_by_line
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
    #: Every judgement that reached a line, by line.
    verdicts: dict[LineRef, Verdict]
    #: Referred lines no judgement reached, and what was done with them.
    unreviewed: tuple[LineRef, ...]
    unreviewed_policy: str
    #: Members pulled back to the source by a refused or unreviewed member
    #: of their hyphen unit.
    pulled_by_unit: tuple[LineRef, ...]
    #: The run's traces, with this render's projection channels (text the
    #: file carries, fidelity, losses) written over the run's.
    traces: dict[LineRef, LineTrace]
    format_losses: dict[str, int] = field(default_factory=dict)

    @property
    def applied(self) -> int:
        return len(self.verdicts)

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


Unreviewed = Literal["revert", "deliver"]


async def approve(
    document_manifest: DocumentManifest,
    source_files: dict[str, Path],
    result: CorrectionResult,
    judgements: Iterable[Judgement],
    *,
    unreviewed: Unreviewed = "revert",
    format_adapter: FormatAdapter | None = None,
) -> ApprovedResult:
    """Re-render the run's artefacts under the reviewer's decisions.

    ``document_manifest`` and ``source_files`` are what the run was given
    (``LoadedDocument.manifest`` / ``.source_paths`` from the façade); the
    caller's manifest is never mutated. ``result`` is that run's outcome:
    its decisions are the starting point, its provenance labels the
    approved file. Refused before anything is rendered: a judgement naming
    a line the document does not have, two judgements on one line,
    ``transcribed`` without a transcription or on a hyphen-unit member, and
    a result whose decisions do not match this document's source text.
    """
    judged = _index(judgements)
    manifest = document_manifest.model_copy(deep=True)
    lines = {line_ref(lm): lm for page in manifest.pages for lm in page.lines}
    unknown = [r for r in judged if r not in lines]
    if unknown:
        shown = ", ".join(f"({r.page_id!r}, {r.line_id!r})" for r in unknown[:5])
        raise ConfigurationError(
            f"{len(unknown)} judgement(s) name lines this document does not have: {shown}"
        )
    before = {ref: _decision_of(result, ref, lm) for ref, lm in lines.items()}
    plan = _plan(lines, before, judged, unreviewed)
    decisions = [_amend(lines[ref], before[ref], plan.intent[ref]) for ref in lines]
    traces = copy.deepcopy(result.traces)
    render = await _render(
        manifest,
        source_files,
        result,
        DecisionSet(tuple(decisions)),
        traces,
        format_adapter,
    )
    return ApprovedResult(
        corrected_files=render.corrected_files,
        undeliverable_files=render.undeliverable,
        decisions=DecisionSet(tuple(decisions)),
        verdicts={ref: j.verdict for ref, j in judged.items()},
        unreviewed=plan.unreviewed,
        unreviewed_policy=unreviewed,
        pulled_by_unit=plan.pulled,
        traces=traces,
        format_losses=render.losses,
    )


def approve_sync(
    document_manifest: DocumentManifest,
    source_files: dict[str, Path],
    result: CorrectionResult,
    judgements: Iterable[Judgement],
    *,
    unreviewed: Unreviewed = "revert",
    format_adapter: FormatAdapter | None = None,
) -> ApprovedResult:
    """Synchronous twin of :func:`approve` (scripts, notebooks, CLIs). Must
    not be called from within a running event loop — ``await approve(...)``
    there (a web handler, the demo's)."""
    return asyncio.run(
        approve(
            document_manifest,
            source_files,
            result,
            judgements,
            unreviewed=unreviewed,
            format_adapter=format_adapter,
        )
    )


def _index(judgements: Iterable[Judgement]) -> dict[LineRef, Judgement]:
    judged: dict[LineRef, Judgement] = {}
    for j in judgements:
        if j.verdict is Verdict.TRANSCRIBED and not (j.transcription or "").strip():
            raise ConfigurationError(
                f"judgement on ({j.page_id!r}, {j.line_id!r}) is 'transcribed' "
                "without a transcription"
            )
        if j.ref in judged:
            raise ConfigurationError(
                f"two judgements on ({j.page_id!r}, {j.line_id!r}): one line, one verdict"
            )
        judged[j.ref] = j
    return judged


def _decision_of(
    result: CorrectionResult, ref: LineRef, lm: LineManifest
) -> LineDecision:
    before = result.decisions.by_ref.get(ref)
    if before is None or before.source_text != lm.ocr_text:
        raise ConfigurationError(
            f"the run's decisions do not cover line ({ref.page_id!r}, {ref.line_id!r}) "
            "of this document as it reads now: approve() needs the result of a run "
            "over this very document"
        )
    return before


@dataclass(frozen=True)
class _Intent:
    """What one line will carry: a status, a text, and why."""

    status: LineStatus
    text: str
    reason: str | None = None
    review: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Plan:
    intent: dict[LineRef, _Intent]
    unreviewed: tuple[LineRef, ...]
    pulled: tuple[LineRef, ...]


def _intent_of(
    lm: LineManifest,
    before: LineDecision,
    judgement: Judgement | None,
    unreviewed: Unreviewed,
) -> tuple[_Intent, bool]:
    """One line's own intent, before the unit rule; True when it was a
    referral nobody judged."""
    status, text, reason, review = (
        before.status,
        before.final_text,
        before.fallback_reason,
        before.review_reasons,
    )
    if judgement is None:
        if status is not LineStatus.REVIEW_REQUIRED:
            return _Intent(status, text, reason, review), False
        if unreviewed == "deliver":
            return _Intent(status, text, reason, review), True
        return _Intent(LineStatus.FALLBACK, lm.ocr_text, "human: unreviewed"), True
    if judgement.verdict is Verdict.ACCEPTED:
        if status is LineStatus.REVIEW_REQUIRED:
            return _Intent(LineStatus.CORRECTED, text), False
        return _Intent(status, text, reason, review), False
    if judgement.verdict is Verdict.REFUSED:
        return _Intent(LineStatus.FALLBACK, lm.ocr_text, "human: refused"), False
    reading = preserve_break_char(lm.ocr_text, str(judgement.transcription))
    return _Intent(LineStatus.CORRECTED, reading), False


def _plan(
    lines: dict[LineRef, LineManifest],
    before: dict[LineRef, LineDecision],
    judged: dict[LineRef, Judgement],
    unreviewed: Unreviewed,
) -> _Plan:
    """Every line's intent, with the hyphen-unit rule applied (ADR-010)."""
    intents: dict[LineRef, _Intent] = {}
    unreviewed_refs: list[LineRef] = []
    for ref, lm in lines.items():
        intents[ref], was_unreviewed = _intent_of(
            lm, before[ref], judged.get(ref), unreviewed
        )
        if was_unreviewed:
            unreviewed_refs.append(ref)
    by_line = hyphen_group_by_line(derive_hyphen_groups(lines.values()))
    pulled: list[LineRef] = []
    for group in {id(g): g for g in by_line.values()}.values():
        members = group.members
        transcribed = [
            m
            for m in members
            if (j := judged.get(m)) and j.verdict is Verdict.TRANSCRIBED
        ]
        if transcribed:
            m = transcribed[0]
            raise ConfigurationError(
                f"'transcribed' on ({m.page_id!r}, {m.line_id!r}), a member of a "
                "hyphen unit: one half's reading cannot be reconciled with the "
                "other's SUBS_CONTENT here; accept or refuse the unit instead"
            )
        if not any(intents[m].status is LineStatus.FALLBACK for m in members):
            continue
        for m in members:
            if intents[m].status is LineStatus.FALLBACK and intents[m].reason:
                continue
            intents[m] = _Intent(
                LineStatus.FALLBACK, lines[m].ocr_text, "human: unit atomicity"
            )
            pulled.append(m)
    return _Plan(intents, tuple(unreviewed_refs), tuple(pulled))


def _amend(lm: LineManifest, before: LineDecision, intent: _Intent) -> LineDecision:
    """Write one line's amended decision through ``core/decide`` (RM-01:
    the verbs are the only writers of a line's text and status) and
    return the record the artefact will be verified against."""
    if intent.status is LineStatus.FALLBACK:
        decide.fall_back(lm, reason=intent.reason or "human: unreviewed")
    else:
        decide.accept(lm, intent.text)
        for why in intent.review:
            decide.refer_for_review(lm, reason=why)
    return LineDecision(
        ref=before.ref,
        source_text=lm.ocr_text,
        final_text=intent.text,
        status=intent.status,
        fallback_reason=intent.reason if intent.status is LineStatus.FALLBACK else None,
        review_reasons=intent.review,
    )


async def _render(
    manifest: DocumentManifest,
    source_files: dict[str, Path],
    result: CorrectionResult,
    decisions: DecisionSet,
    traces: dict[LineRef, LineTrace],
    format_adapter: FormatAdapter | None,
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
        format_adapter=format_adapter,
        producer_metadata=metadata,
        config_fingerprint=(
            provenance.config_fingerprint if provenance is not None else "unknown"
        ),
        emit=lambda event: None,
        document_manifest=manifest,
        source_files=source_files,
        traces=traces,
        decisions=decisions,
    )


__all__ = ["ApprovedResult", "Judgement", "Verdict", "approve", "approve_sync"]
