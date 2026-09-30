"""Turning a corrected document into the run's terminal decisions.

Between "every page has been through the producer" and "the outputs exist"
sit five document-wide passes, and their ORDER is the whole content of this
module — each one depends on running against what the previous left behind:

  1. the adjacent-duplicate consistency pass, which needs every
     line still holding its pre-revert accepted correction, so it must be
     the first thing to revert anything;
  2. break-character preservation, which normalises the accepted text
     BEFORE it becomes a decision. Forcing the source's break character
     AFTER the decision is recorded makes the artefact spell something the
     decision does not, and the projection invariant then raises on the
     engine's own output;
  3. the loss-policy gates (ADR-012 strict, token_realign), which reject a
     correction that cannot project without losing word granularity —
     before the decisions materialise and before any output exists, so the
     unit falls back to source and the markup keeps its Word geometry;
  4. the review pass, which qualifies the corrections that survived all
     three — LAST, because every pass above can still take a correction
     away and a referral on a reverted line describes something nobody
     receives. It is also the only pass that writes no text, so it can
     move no output byte;
  5. deriving the immutable :class:`DecisionSet`, which refuses a line
     still PENDING: outputs exist only for a document where every line
     carries a terminal decision.

Free function: none of it is execution control — no producer, no retry,
no observer.

The order is not only stated here. It is asserted on the production path:
``tests/decision/test_finalize_pass_order.py`` runs ``_finalize_document``
itself on a document where two passes interact, and pins the outcome. A
swap changes the delivered TEXT of a line rather than a counter, which is
what turns that assertion red. It replaced a runtime token that proved the
same contract by threading a mutable argument through four private
functions whose only caller already calls them in this order.
"""

from __future__ import annotations

from saknussemm.core import decide
from saknussemm.core.acceptance import (
    _global_adjacency_pass,
    _loss_policy_pass,
    _review_pass,
)
from saknussemm.core.decisions import DecisionSet, derive_decision_set
from saknussemm.core.identity import LineRef
from saknussemm.core.pairing import preserve_break_char
from saknussemm.core.schemas import (
    DocumentManifest,
    GuardConfig,
    LineManifest,
    LineTrace,
    LossPolicy,
    ReviewPolicy,
    SidecarEntry,
)


def _preserve_break_chars(document_manifest: DocumentManifest) -> None:
    """Force the SOURCE line's word-break character onto every accepted
    correction that changed it (P5, found by the OCR17+ corpus).

    Only the decided text is normalised: the proposal stage in the traces
    keeps the producer's RAW text, so what the producer actually said stays
    auditable.

    Goes through :func:`decide.renormalise` and NOT ``decide.accept``,
    which is the question ADR-013 left for `RM-01` to answer. This pass
    decides nothing: it does not choose between a proposal and a source,
    it respells a choice already made, and it never runs on a line that
    fell back — a reverted line has ``corrected_text == ocr_text``, which
    the guard above skips. Routing it through ``accept`` would stamp
    ``CORRECTED`` on lines whose status it has no business setting, which
    is a behaviour change bought for the tidiness of two verbs instead of
    three. The narrow verb keeps the call honest about what happened.
    """
    for page in document_manifest.pages:
        for lm in page.lines:
            if lm.corrected_text is not None and lm.corrected_text != lm.ocr_text:
                decide.renormalise(
                    lm, preserve_break_char(lm.ocr_text, lm.corrected_text)
                )


def _finalize_document(
    *,
    guard_config: GuardConfig,
    loss_policy: LossPolicy,
    review_policy: ReviewPolicy,
    document_manifest: DocumentManifest,
    all_lines: dict[LineRef, LineManifest],
    traces: dict[LineRef, LineTrace],
) -> tuple[DecisionSet, list[SidecarEntry]]:
    """Run the document-wide passes and materialise the run's decisions.

    Returns the terminal :class:`DecisionSet` and the sidecar entries the
    loss policy set aside — corrections the token_realign gate refused to
    project, preserved for review instead of lost.
    """
    _global_adjacency_pass(
        guard_config=guard_config,
        document_manifest=document_manifest,
        all_lines=all_lines,
        traces=traces,
    )
    _preserve_break_chars(document_manifest)
    sidecar_entries = _loss_policy_pass(
        loss_policy=loss_policy,
        document_manifest=document_manifest,
        all_lines=all_lines,
        traces=traces,
    )
    _review_pass(
        review_policy=review_policy,
        document_manifest=document_manifest,
        all_lines=all_lines,
        traces=traces,
    )
    return derive_decision_set(document_manifest, traces), sidecar_entries
