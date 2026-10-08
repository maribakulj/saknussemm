"""Immutable decision record of a run (ADR-011, slices C+E).

The engine expresses its decisions by mutating its PRIVATE working copy
of the manifests (the caller's document is never
touched); this module defines THE decision model and materializes it
exactly once — after the global consistency pass, when every line's
decision is final. Everything downstream of the run reads the
:class:`DecisionSet`: the projection invariant, fallback accounting,
the final EditScript, and — via :attr:`CorrectionResult.decisions` —
the caller itself.

Materialization enforces terminality: a ``PENDING`` line at this point
is an engine bug — a decision path that forgot its lines — never an
input problem, so the set refuses to exist and the run fails loudly
(the run-level backstop that previously sat beside the write path).

Pure core: no lxml, no formats import (import-contract test).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import cached_property

from saknussemm.core.identity import LineRef, line_ref
from saknussemm.core.schemas import (
    DecisionReason,
    DecisionStage,
    DocumentManifest,
    LineOutcome,
    LineStatus,
    LineTrace,
    ProjectionStage,
    ProposalStage,
)


@dataclass(frozen=True)
class LineDecision:
    """One line's terminal decision — the text the artefact must carry."""

    ref: LineRef
    source_text: str
    final_text: str
    #: Terminal by construction: ``CORRECTED``, ``REVIEW_REQUIRED`` or
    #: ``FALLBACK``.
    status: LineStatus
    #: The trace's fallback reason for a fallen line (``None`` on
    #: corrected lines, or when the host ran without traces).
    fallback_reason: str | None
    #: The trace's review reasons for a REFERRED line — empty on
    #: every other status, and on a referred line when the host ran
    #: without traces. Plural because the causes are independent: a
    #: correction can change an amount AND a proper noun, and a reviewer
    #: needs to be told both.
    review_reasons: tuple[str, ...] = ()

    @property
    def carries_a_correction(self) -> bool:
        """Did this line keep a correction the artefact must carry?

        That is no longer the same question as ``status is
        CORRECTED``: a referred line kept its correction and merely
        declares the run could not verify it. Every site that used to
        ask the status in order to ask THIS asks here instead — the
        edit-script builder is the one that did, and answering it with
        the old test would have silently dropped the ops of every
        referred line, so a consumer replaying the script would have
        diverged from the file the same run wrote.
        """
        return self.status in (LineStatus.CORRECTED, LineStatus.REVIEW_REQUIRED)


@dataclass(frozen=True)
class DecisionSet:
    """Every line's terminal decision, in document reading order."""

    decisions: tuple[LineDecision, ...]

    @cached_property
    def by_ref(self) -> dict[LineRef, LineDecision]:
        """Index: qualified line identity → its decision."""
        return {d.ref: d for d in self.decisions}

    @property
    def fallback_lines(self) -> int:
        """Lines whose terminal status is ``FALLBACK`` (they kept their
        OCR source text, whatever path led there)."""
        return sum(1 for d in self.decisions if d.status is LineStatus.FALLBACK)

    @property
    def review_lines(self) -> int:
        """Lines the run corrected and could not verify.

        Disjoint from :attr:`fallback_lines` by construction — a line
        holds exactly one terminal status — and NOT a subset of the
        corrected ones: ``CORRECTED`` counts only what the run could
        both correct and check. ``corrected + review_required`` is the
        number of lines whose text changed hands.
        """
        return sum(1 for d in self.decisions if d.status is LineStatus.REVIEW_REQUIRED)

    def review_reason_counts(self) -> dict[str, int]:
        """Referred lines aggregated by reason PREFIX, same convention as
        :meth:`fallback_reason_counts`.

        One line can contribute to SEVERAL codes — the counts therefore
        sum to at least :attr:`review_lines`, not to it. That is the
        honest shape: "31 lines changed a digit, 12 changed a proper
        noun, 38 lines in all" is three facts, and forcing one reason per
        line would have to drop two of them.
        """
        counts: dict[str, int] = {}
        for d in self.decisions:
            if d.status is not LineStatus.REVIEW_REQUIRED:
                continue
            for raw in d.review_reasons or ("unspecified",):
                prefix = raw.split(":", 1)[0].strip() or "unspecified"
                counts[prefix] = counts.get(prefix, 0) + 1
        return counts

    def fallback_reason_counts(self) -> dict[str, int]:
        """Fallen lines aggregated by reason PREFIX (the part before
        ``:``; ``unspecified`` when no trace pinned one) — so a consumer
        can say WHY without parsing messages."""
        counts: dict[str, int] = {}
        for d in self.decisions:
            if d.status is not LineStatus.FALLBACK:
                continue
            prefix = (d.fallback_reason or "unspecified").split(":", 1)[0].strip()
            counts[prefix] = counts.get(prefix, 0) + 1
        return counts


def derive_decision_set(
    document_manifest: DocumentManifest,
    traces: Mapping[LineRef, LineTrace],
) -> DecisionSet:
    """Materialize the run's decisions from the run's manifest copy.

    Called once, after the global consistency pass — the point where no
    later pass may change a decision. Refuses a ``PENDING`` line: an
    undecided line reaching materialization is an engine bug and must
    fail the run before any output exists.
    """
    undecided = [
        (page.page_id, lm.line_id)
        for page in document_manifest.pages
        for lm in page.lines
        if lm.status is LineStatus.PENDING
    ]
    if undecided:
        shown = ", ".join(f"({p!r}, {li!r})" for p, li in undecided[:5])
        suffix = " …" if len(undecided) > 5 else ""
        raise RuntimeError(
            f"{len(undecided)} line(s) reached the end of the run with no "
            f"terminal decision (PENDING): {shown}{suffix}"
        )

    decisions: list[LineDecision] = []
    for page in document_manifest.pages:
        for lm in page.lines:
            ref = line_ref(lm)
            reason: str | None = None
            review: tuple[str, ...] = ()
            if lm.status is LineStatus.FALLBACK:
                trace = traces.get(ref)
                reason = trace.fallback_reason if trace is not None else None
            elif lm.status is LineStatus.REVIEW_REQUIRED:
                trace = traces.get(ref)
                review = trace.review_reasons if trace is not None else ()
            decisions.append(
                LineDecision(
                    ref=ref,
                    source_text=lm.ocr_text,
                    final_text=(
                        lm.corrected_text
                        if lm.corrected_text is not None
                        else lm.ocr_text
                    ),
                    status=lm.status,
                    fallback_reason=reason,
                    review_reasons=review,
                )
            )
    return DecisionSet(decisions=tuple(decisions))


def _structured_reason(raw: str | None) -> DecisionReason | None:
    """Split the run's ``"code: detail"`` reason convention into the
    report's structured motif. The code half uses the SAME normalization
    as :meth:`DecisionSet.fallback_reason_counts`, so aggregating report
    reasons by ``code`` reproduces ``CorrectionResult.fallback_reasons``.
    """
    if not raw:
        return None
    code, _, detail = raw.partition(":")
    return DecisionReason(code=code.strip(), detail=detail.strip() or None)


def build_line_outcomes(
    decisions: DecisionSet,
    traces: Mapping[LineRef, LineTrace],
) -> list[LineOutcome]:
    """Project the run into the report's staged per-line outcomes (§9 v2).

    The DecisionSet is the authority for the terminal stage (the
    report builder reads decisions, not manifests); the working traces
    contribute the producer stage and the projection stage, each absent
    when the line never reached them (no producer call / no rendered
    output file).
    """
    outcomes: list[LineOutcome] = []
    for d in decisions.decisions:
        trace = traces.get(d.ref)
        proposal: ProposalStage | None = None
        projection: ProjectionStage | None = None
        hyphen_role: str | None = None
        if trace is not None:
            hyphen_role = trace.hyphen_role
            if trace.model_input_text is not None or (
                trace.model_corrected_text is not None
            ):
                proposal = ProposalStage(
                    input_text=trace.model_input_text,
                    output_text=trace.model_corrected_text,
                )
            if trace.output_alto_text is not None or trace.rewriter_path is not None:
                projection = ProjectionStage(
                    extracted_text=trace.output_alto_text,
                    rewriter_path=trace.rewriter_path,
                    geometry_tier=trace.geometry_tier,
                    # ADR-012 — per-decision attribution of the rewrite's
                    # granularity losses (None when nothing was lost).
                    losses=trace.projection_losses,
                    # The level at which this line's bytes carry its
                    # decision: exact, or what the format cost, or a
                    # whitespace character that was substituted away.
                    fidelity=trace.projection_fidelity,
                    # A diagnostic, not a loss: it used to travel
                    # inside `losses` above, where summing the counters
                    # added a non-loss to the total.
                    word_order_suspected=trace.word_order_suspected,
                )
        outcomes.append(
            LineOutcome(
                line_id=d.ref.line_id,
                page_id=d.ref.page_id,
                hyphen_role=hyphen_role,
                source_text=d.source_text,
                proposal=proposal,
                decision=DecisionStage(
                    status=d.status.value,
                    final_text=d.final_text,
                    reason=_structured_reason(d.fallback_reason),
                    review_reasons=[
                        motif
                        for raw in d.review_reasons
                        if (motif := _structured_reason(raw)) is not None
                    ],
                    features=trace.proposal_features if trace else None,
                ),
                projection=projection,
            )
        )
    return outcomes


__all__ = [
    "DecisionSet",
    "LineDecision",
    "build_line_outcomes",
    "derive_decision_set",
]
