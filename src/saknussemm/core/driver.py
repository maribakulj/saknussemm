"""Driving one page through the producer, chunk by chunk.

The engine's inner loop, and until now the bulk of the orchestrator: plan a
page's chunks, route them, run each one, retry it, descend a granularity
when retrying at this one is hopeless, and decide what its ending does to
its lines. None of that is what a *pipeline* does — a pipeline preflights,
indexes, drives, finalises, renders and reports. This is what the fourth of
those means.

:class:`PageDriver` is built once per run from the engine's immutable
configuration, so the loop reads its policies off a value rather than off
the public façade. It owns no run state: the mutable
:class:`~saknussemm.core.context.RunContext` is threaded in per call, and a
driver can therefore serve every page of a run — or two concurrent runs —
without the two contaminating each other.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from saknussemm.core import decide, events as ev
from saknussemm.core.attempt import _AttemptOutcome, _attempt_chunk
from saknussemm.core.context import RunContext
from saknussemm.core.identity import LineRef
from saknussemm.core.outcome import (
    _absorb_chunk_error,
    _apply_chunk_fallback,
    _finish_successful_chunk,
)
from saknussemm.core.planner import downgrade_granularity, plan_page
from saknussemm.core.protocols import EditProducer, ProviderPermanentError
from saknussemm.core.retry import ChunkBudget
from saknussemm.core.reconcile import _build_hyphen_pairs, _subpage_for_lines
from saknussemm.core.routing import ChunkRouter
from saknussemm.core.workspace import PageWorkspace
from saknussemm.core.schemas import (
    ChunkGranularity,
    ChunkPlannerConfig,
    ChunkRequest,
    GuardConfig,
    HyphenRole,
    LineManifest,
    LineTrace,
    PageManifest,
    RetryPolicy,
)
from saknussemm.errors import CorrectionAborted, SaknussemmError


@dataclass(frozen=True)
class PageDriver:
    """The configured components one page's correction needs.

    Immutable and run-agnostic: everything that changes during a run
    arrives as an argument.
    """

    #: The primary edit producer every chunk goes to by default.
    producer: EditProducer
    #: Chunk planning: granularity selection, sizes, windows.
    config: ChunkPlannerConfig
    #: Retry ramp, attempt cap, per-chunk budget.
    retry_policy: RetryPolicy
    #: Acceptance and anti-migration thresholds.
    guard_config: GuardConfig
    #: Qui reçoit quoi, une fois la page planifiée. Le pilote ne connaît ni
    #: le score de qualité, ni le producteur d'escalade, ni le plafond
    #: d'images : il demande son plan à cette couture, qui le lui rend
    #: inchangé quand aucun des trois n'est actif — c'est-à-dire par défaut.
    router: ChunkRouter
    #: Where engine events go.
    emit: Callable[[ev.EngineEvent], None]

    async def process_page(
        self,
        *,
        ctx: RunContext,
        page: PageManifest,
        document_id: str,
        traces: dict[LineRef, LineTrace],
        cross_page_partners: dict[LineRef, LineManifest] | None,
        should_abort: Callable[[], bool] | None = None,
    ) -> tuple[int, int]:
        # `RM-03` — the three indices this page's work reads, bound once
        # here and passed as one thing from now on. They used to travel
        # separately through nine signatures.
        workspace = PageWorkspace(
            line_by_id={lm.line_id: lm for lm in page.lines},
            cross_page_partners=cross_page_partners,
            traces=traces,
        )

        page_hyphen_pairs = sum(
            1
            for lm in page.lines
            if lm.hyphen_role in (HyphenRole.PART1, HyphenRole.BOTH)
        )
        self.emit(
            ev.PageStarted(
                page_id=page.page_id,
                page_index=page.page_index,
                line_count=len(page.lines),
                hyphen_pair_count=page_hyphen_pairs,
            )
        )

        routed_chunks = self._plan_page_chunks(
            ctx=ctx,
            page=page,
            document_id=document_id,
            workspace=workspace,
        )

        page_reconciled = 0
        page_chunks = 0
        for chunk, producer in routed_chunks:
            # Cooperative cancellation between chunks. Checked before
            # the per-chunk try/except so CorrectionAborted propagates out
            # instead of being swallowed as a chunk error.
            if should_abort is not None and should_abort():
                raise CorrectionAborted(
                    f"run aborted before chunk {chunk.chunk_id!r} on page "
                    f"{page.page_id!r}"
                )
            page_chunks += 1
            page_reconciled += await self._run_chunk_absorbing(
                ctx=ctx,
                chunk=chunk,
                producer=producer,
                page=page,
                workspace=workspace,
                should_abort=should_abort,
            )

        # Duplicate detection is no page business anymore: the single
        # document-wide adjacency pass runs after the page loop,
        # comparing every line's live pre-revert correction on one basis —
        # chunk seams, descent sub-chunk seams and page seams included.

        page_corrections = sum(
            1
            for lm in page.lines
            if lm.corrected_text is not None and lm.corrected_text != lm.ocr_text
        )
        self.emit(
            ev.PageCompleted(
                page_id=page.page_id,
                page_index=page.page_index,
                corrections=page_corrections,
                hyphen_pairs_reconciled=page_reconciled,
            )
        )

        return page_chunks, page_reconciled

    def _plan_page_chunks(
        self,
        *,
        ctx: RunContext,
        page: PageManifest,
        document_id: str,
        workspace: PageWorkspace,
    ) -> list[tuple[ChunkRequest, EditProducer]]:
        """Ce que les appels au producteur de cette page seront.

        Planifier, puis demander à la couture de routage qui reçoit quoi.
        Elle rend le plan inchangé quand aucun de ses trois mécanismes n'est
        actif — ce qui est le cas par défaut — et le pilote n'a donc pas à
        savoir qu'ils existent pour lire ce chemin.
        """
        plan = plan_page(page, document_id, self.config)
        ctx.hyphen_splits.extend(plan.hyphen_splits)
        routed_chunks = self.router.route(
            page=page,
            chunks=plan.chunks,
            producer=self.producer,
            ctx=ctx,
            workspace=workspace,
        )
        self.emit(
            ev.ChunkPlanned(
                page_id=page.page_id,
                chunk_count=len(routed_chunks),
                granularity=plan.granularity.value,
            )
        )
        return routed_chunks

    async def _run_chunk_absorbing(
        self,
        *,
        ctx: RunContext,
        chunk: ChunkRequest,
        producer: EditProducer,
        page: PageManifest,
        workspace: PageWorkspace,
        should_abort: Callable[[], bool] | None,
    ) -> int:
        """Run one chunk, absorbing the errors a run may survive.

        ADR-008 — only RECOVERABLE domain errors become a ``chunk_error``
        event and a continue. Cancellation and a permanent provider
        rejection propagate: the latter would hit every remaining chunk
        identically, and converting it into per-chunk OCR fallbacks would
        let the run END AS A SUCCESS with silently uncorrected text.
        Anything else (a ``KeyError``, a pydantic bug, a broken invariant)
        is a programming error — continuing would let the run complete
        "successfully" with lines in an unknown state.
        """
        try:
            return await self._run_chunk(
                ctx=ctx,
                chunk=chunk,
                producer=producer,
                page=page,
                workspace=workspace,
                should_abort=should_abort,
            )
        except (CorrectionAborted, ProviderPermanentError):
            raise
        except Exception as exc:
            # ADR-006: the pipeline does not log directly; it emits an
            # event the host application can log/trace.
            self.emit(
                ev.ChunkError(
                    chunk_id=chunk.chunk_id,
                    message=str(exc)[:200],
                    exception_type=type(exc).__name__,
                )
            )
            if not isinstance(exc, SaknussemmError):
                raise
            if _absorb_chunk_error(exc=exc, chunk=chunk, workspace=workspace):
                ctx.fallback_chunks += 1
            return 0

    async def _run_chunk(
        self,
        *,
        ctx: RunContext,
        chunk: ChunkRequest,
        producer: EditProducer,
        page: PageManifest,
        workspace: PageWorkspace,
        budget: ChunkBudget | None = None,
        should_abort: Callable[[], bool] | None = None,
    ) -> int:
        """Process one chunk, and decide what its outcome means.

        Three endings: the producer answered and the chunk is finished; it
        did not and the same work is worth retrying one granularity finer
        (:meth:`_descend_granularity`); or it did not and no finer
        grain would help — a non-retryable error like an HTTP 4xx, LINE
        grain already reached, or the shared budget spent — and the chunk
        falls back to OCR source.

        ``budget`` is the :class:`~saknussemm.core.retry.ChunkBudget` this
        original chunk shares with its whole descent (default 6, from
        ``RetryPolicy.per_chunk_budget``); ``None`` at the top level opens
        a fresh one. It is mutable on purpose — a sub-chunk spends from
        the SAME purse, which is the property that stops a descent from
        multiplying the run's cost by its depth.
        """
        line_by_id = workspace.line_by_id
        chunk_lines = [line_by_id[lid] for lid in chunk.line_ids if lid in line_by_id]
        if not chunk_lines:
            return 0

        if budget is None:
            budget = ChunkBudget(self.retry_policy.per_chunk_budget)

        hyphen_pairs = _build_hyphen_pairs(chunk_lines)

        self.emit(
            ev.ChunkStarted(
                chunk_id=chunk.chunk_id,
                granularity=chunk.granularity.value,
                line_count=len(chunk_lines),
            )
        )

        attempts_cap = budget.attempts_allowed(self.retry_policy.max_attempts)
        outcome = await _attempt_chunk(
            ctx=ctx,
            chunk=chunk,
            producer=producer,
            chunk_lines=chunk_lines,
            hyphen_pairs=hyphen_pairs,
            all_lines_by_id=line_by_id,
            traces=workspace.traces,
            max_attempts=attempts_cap,
            retry_policy=self.retry_policy,
            guard_config=self.guard_config,
            emit=self.emit,
        )
        budget.spend(outcome.attempts_used)

        if outcome.response is not None:
            reconciled = _finish_successful_chunk(
                guard_config=self.guard_config,
                emit=self.emit,
                ctx=ctx,
                chunk=chunk,
                chunk_lines=chunk_lines,
                response=outcome.response,
                workspace=workspace,
                usage=outcome.usage,
            )
            # VR-10: the pair the attempt loop put back to OCR went through
            # the passes as an identity; it is reported as what it is.
            for lm in chunk_lines:
                if lm.line_id in outcome.neutralised:
                    decide.fall_back(
                        lm, reason="pair_drift_fallback", traces=workspace.traces
                    )
            return reconciled

        return await self._handle_chunk_failure(
            ctx=ctx,
            chunk=chunk,
            outcome=outcome,
            producer=producer,
            page=page,
            chunk_lines=chunk_lines,
            workspace=workspace,
            budget=budget,
            should_abort=should_abort,
        )

    async def _handle_chunk_failure(
        self,
        *,
        ctx: RunContext,
        chunk: ChunkRequest,
        outcome: _AttemptOutcome,
        producer: EditProducer,
        page: PageManifest,
        chunk_lines: list[LineManifest],
        workspace: PageWorkspace,
        budget: ChunkBudget,
        should_abort: Callable[[], bool] | None,
    ) -> int:
        """No attempt produced a proposal — descend, or fall back.

        A descent is worth it only when the terminal error was one a finer
        grain could plausibly avoid, there IS a finer grain, and the shared
        budget can still pay for it. Otherwise the chunk goes back to its
        OCR text: a hard error (an HTTP 4xx) would hit every sub-chunk
        identically, and LINE grain has nowhere left to go.
        """
        next_g = downgrade_granularity(chunk.granularity)
        if outcome.can_downgrade and next_g is not None and not budget.exhausted:
            return await self._descend_granularity(
                ctx=ctx,
                chunk=chunk,
                next_g=next_g,
                producer=producer,
                page=page,
                chunk_lines=chunk_lines,
                workspace=workspace,
                budget=budget,
                should_abort=should_abort,
                last_msg=outcome.last_msg,
            )
        _apply_chunk_fallback(
            emit=self.emit,
            chunk=chunk,
            chunk_lines=chunk_lines,
            workspace=workspace,
            sanitised_msg=outcome.last_msg or "all_attempts_exhausted",
        )
        ctx.fallback_chunks += 1
        return 0

    async def _descend_granularity(
        self,
        *,
        ctx: RunContext,
        chunk: ChunkRequest,
        next_g: ChunkGranularity,
        producer: EditProducer,
        page: PageManifest,
        chunk_lines: list[LineManifest],
        workspace: PageWorkspace,
        budget: ChunkBudget,
        should_abort: Callable[[], bool] | None,
        last_msg: str,
    ) -> int:
        """Re-plan a failed chunk one granularity finer and retry it.

        Only the chunk's TARGET lines descend. Context lines are
        owned by an adjacent chunk; re-planning them here would correct
        them at a finer grain and make their rightful window skip them
        (acceptance ignores already-corrected lines).

        Returns the pairs reconciled across the whole descent. Sub-chunks
        share the caller's cumulative ``budget``; when it runs out
        mid-descent the remaining ones fall back to OCR source rather than
        borrowing attempts from a chunk that has none left.
        """
        target_ids = set(chunk.targets())
        descent_lines = [lm for lm in chunk_lines if lm.line_id in target_ids]
        self.emit(
            ev.ChunkDowngraded(
                chunk_id=chunk.chunk_id,
                from_granularity=chunk.granularity.value,
                to_granularity=next_g.value,
                line_count=len(chunk_lines),
                target_count=len(descent_lines),
                budget_remaining=budget.remaining,
            )
        )
        sub_plan = plan_page(
            _subpage_for_lines(page, descent_lines),
            chunk.document_id,
            self.config,
            force_granularity=next_g,
        )
        ctx.hyphen_splits.extend(sub_plan.hyphen_splits)
        total = 0
        for sub in sub_plan.chunks:
            # The descent can spawn many finest-grain chunks; keep
            # the run cancellable inside it, not only between top-level
            # chunks.
            if should_abort is not None and should_abort():
                raise CorrectionAborted(
                    f"run aborted during granularity descent of chunk "
                    f"{chunk.chunk_id!r} on page {page.page_id!r}"
                )
            if budget.exhausted:
                # Budget spent mid-descent: OCR-fallback the rest.
                sub_lines = [
                    workspace.line_by_id[lid]
                    for lid in sub.line_ids
                    if lid in workspace.line_by_id
                ]
                _apply_chunk_fallback(
                    emit=self.emit,
                    chunk=sub,
                    chunk_lines=sub_lines,
                    workspace=workspace,
                    sanitised_msg=last_msg or "per_chunk_budget exhausted",
                )
                ctx.fallback_chunks += 1
                continue
            total += await self._run_chunk(
                ctx=ctx,
                chunk=sub,
                producer=producer,
                page=page,
                workspace=workspace,
                budget=budget,
                should_abort=should_abort,
            )
        return total
