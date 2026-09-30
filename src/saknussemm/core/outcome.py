"""What a chunk's ending does to its lines.

A chunk ends in exactly three ways, and each writes a different terminal
state onto the same lines:

  - :func:`_finish_successful_chunk` — the producer answered and the
    validator accepted: reconcile the hyphen units, run the acceptance
    guard, project the result onto the traces;
  - :func:`_apply_chunk_fallback` — the retry budget ran out, or the
    error was one smaller chunks would hit identically: the targets go
    back to their OCR text;
  - :func:`_absorb_chunk_error` — a recoverable domain error interrupted
    the chunk somewhere in the middle: whatever it left undecided goes
    back to OCR text NOW.

They live together because the third one is easy to forget, and forgetting
it is how a run finishes "successfully" with lines in no state at all.

Two invariants they share, and neither is optional:

  - **Only TARGET lines.** Context lines were sent to the producer for
    context and belong to an adjacent chunk; forcing them here would steal
    a decision from the window where their context is maximal.
  - **ADR-010 — a fallback covers the whole hyphen unit.** Intra-page
    partners are co-targets by planner atomicity, so the closure only ever
    ADDS cross-page members — the partner whose own chunk succeeded (or has
    not run yet) is pulled to OCR too, rather than leaving a joined word
    rewritten on one line and verbatim on the other.

Free functions. The engine supplies its guard config and its observer
callback; nothing here reads a pipeline.
"""

from __future__ import annotations

from collections.abc import Callable

from saknussemm.core import decide, events as ev
from saknussemm.core.acceptance import _apply_line_acceptance
from saknussemm.core.context import RunContext
from saknussemm.core.identity import LineRef, line_ref
from saknussemm.core.reconcile import (
    _reconcile_chunk_hyphens,
    _unit_pool,
)
from saknussemm.core.redaction import sanitize_error
from saknussemm.core.traces import _finalize_chunk_traces
from saknussemm.core.units import units_containing
from saknussemm.core.workspace import PageWorkspace
from saknussemm.core.schemas import (
    ChunkRequest,
    GuardConfig,
    LineManifest,
    LineStatus,
    LineTrace,
    ProposalBatch,
    Usage,
)


def _finish_successful_chunk(
    *,
    guard_config: GuardConfig,
    emit: Callable[[ev.EngineEvent], None],
    ctx: RunContext,
    chunk: ChunkRequest,
    chunk_lines: list[LineManifest],
    response: ProposalBatch,
    workspace: PageWorkspace,
    usage: Usage | None = None,
) -> int:
    """Reconcile / accept / finalize a chunk whose producer call succeeded.

    Returns the hyphen pairs reconciled. Only the chunk's *target*
    lines are corrected here; a context line's output is discarded on this
    pass.
    """
    # The validated response is already the applied EditScript's output
    # (the producer's ops were normalised and applied on the attempt path,
    # which also accumulated them for CorrectionResult.edit_script).
    text_by_id: dict[str, str] = {o.line_id: o.corrected_text for o in response.lines}

    target_ids = set(chunk.targets())
    target_lines = [lm for lm in chunk_lines if lm.line_id in target_ids]

    undecided = [lm for lm in target_lines if lm.corrected_text is None]
    reconciled_count = _reconcile_chunk_hyphens(
        guard_config=guard_config,
        emit=emit,
        ctx=ctx,
        chunk_id=chunk.chunk_id,
        chunk_lines=target_lines,
        text_by_id=text_by_id,
        workspace=workspace,
    )
    # What the reconciler just decided is what stage C revisits (VR-11):
    # a target that was undecided before and holds a text now.
    _apply_line_acceptance(
        guard_config=guard_config,
        chunk_lines=target_lines,
        text_by_id=text_by_id,
        all_lines_by_id=workspace.line_by_id,
        traces=workspace.traces,
        cross_page_partners=workspace.cross_page_partners,
        reconciled=frozenset(
            line_ref(lm) for lm in undecided if lm.corrected_text is not None
        ),
    )
    _finalize_chunk_traces(chunk_lines=target_lines, traces=workspace.traces)

    emit(
        ev.ChunkCompleted(
            chunk_id=chunk.chunk_id,
            line_count=len(chunk_lines),
            target_count=len(target_lines),
            hyphen_pairs_reconciled=reconciled_count,
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
        )
    )
    return reconciled_count


def _fall_back_to_source(
    lines: list[LineManifest],
    traces: dict[LineRef, LineTrace] | None,
    *,
    reason: str,
) -> None:
    """Put these lines back to their OCR text, terminally.

    The chunk-exhaustion path: every attempt spent, or an error a finer
    granularity would not heal. Writes through :func:`decide.fall_back`,
    so ``reason`` now lands only on a trace that carries none — this site
    used to assign unconditionally, and ADR-013 is why the difference is
    invisible (a line that already has a reason is already at its source
    text, so no earlier attribution can be a stale one). Measured before
    the change on every corpus in the repository, with a producer failing
    ~20 % of calls outright: zero collisions.
    """
    for lm in lines:
        decide.fall_back(lm, reason=reason, traces=traces)


def _extend_to_units(
    targets: list[LineManifest],
    workspace: PageWorkspace,
) -> None:
    """ADR-010 — pull the rest of each fallen line's hyphen unit down with
    it, keeping the reason each member already carries.

    A member that fell for its own reason keeps it; one dragged along by
    its partner is marked ``hyphen_unit_fallback``, so the report can tell
    a decision from its consequence.
    """
    target_ids = {lm.line_id for lm in targets}
    pool = _unit_pool(workspace.line_by_id, workspace.cross_page_partners)
    for lm in units_containing(targets, pool):
        if lm.line_id in target_ids:
            continue
        decide.fall_back(lm, reason="hyphen_unit_fallback", traces=workspace.traces)


def _apply_chunk_fallback(
    *,
    emit: Callable[[ev.EngineEvent], None],
    chunk: ChunkRequest,
    chunk_lines: list[LineManifest],
    workspace: PageWorkspace,
    sanitised_msg: str,
) -> None:
    """Revert the chunk's TARGET lines to their OCR text and warn.

    Called once the retry loop exhausts its budget or hits an error a
    finer granularity would not heal. The run-level ``fallback_chunks``
    counter is bumped by the caller, mirroring how ``retry_count`` is
    incremented at the retry call site — both are run-orchestration
    state, not chunk-level side effects.
    """
    emit(
        ev.Warning(
            chunk_id=chunk.chunk_id,
            message=f"Fallback to OCR source: {sanitised_msg[:120]}",
        )
    )
    target_ids = set(chunk.targets())
    targets = [lm for lm in chunk_lines if lm.line_id in target_ids]
    _fall_back_to_source(
        targets,
        workspace.traces,
        reason=f"all_attempts_exhausted: {sanitised_msg[:120]}",
    )
    _extend_to_units(targets, workspace)


def _absorb_chunk_error(
    *,
    exc: Exception,
    chunk: ChunkRequest,
    workspace: PageWorkspace,
) -> bool:
    """Decide the lines a failed chunk left in limbo, and say whether any
    were found.

    The absorbed error may have interrupted the chunk between its producer
    attempt and its finalization. Every target still ``PENDING`` falls back
    to its source text NOW: the run may degrade, it may never continue with
    undecided lines. Lines the chunk — or a descent sub-chunk — already
    finalized keep their decision.

    Returns ``True`` when something fell, which is what the caller counts
    as a fallen chunk.

    ADR-010 — the closure runs BEFORE the reason is written, so a unit
    member on another page (already corrected, or not yet processed)
    carries the same ``chunk_error_absorbed`` reason as the line that
    dragged it down. A mixed pair may not survive the absorb, and the
    report should say why both halves fell, not just one.
    """
    line_by_id = workspace.line_by_id
    undecided = [
        line_by_id[lid]
        for lid in chunk.targets()
        if lid in line_by_id and line_by_id[lid].status is LineStatus.PENDING
    ]
    if not undecided:
        return False
    pool = _unit_pool(line_by_id, workspace.cross_page_partners)
    _fall_back_to_source(
        units_containing(undecided, pool),
        workspace.traces,
        reason=f"chunk_error_absorbed: {sanitize_error(str(exc))[:120]}",
    )
    return True
