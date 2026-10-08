"""Pure correction pipeline.

The pipeline takes a parsed :class:`DocumentManifest`, drives the chunk
planner, asks the injected :class:`EditProducer` for an
:class:`EditScript` per chunk, validates the result, reconciles hyphen
pairs, and renders the corrected XML in memory. It depends only on the
Protocols in :mod:`saknussemm.core.protocols` — no job store, no
FastAPI, no filesystem path manipulation beyond reading source files.
Credentials never reach the pipeline: an LLM's API key lives inside its
producer (see :class:`LLMEditProducer` and the
:meth:`CorrectionPipeline.for_provider` convenience).

Side effects:
  - producer calls via :class:`EditProducer` (LLM HTTP, rules engine, …)
  - Event notifications via :class:`PipelineObserver`

The engine never persists (ADR-011): the corrected artefacts, the §9
report and the run's statistics all travel on
:class:`CorrectionResult`; the caller persists them
(:meth:`CorrectionResult.write`, or its own transaction).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from collections.abc import Callable
from typing import Any
from pathlib import Path

from saknussemm.errors import (
    ConfigurationError,
    CorrectionAborted,
)
from saknussemm.core import events as ev
from saknussemm.core.redaction import sanitize_error
from saknussemm.core.context import RunContext
from saknussemm.core.driver import PageDriver
from saknussemm.core.routing import ChunkRouter
from saknussemm.core.finalize import _finalize_document
from saknussemm.core.indexing import (
    DocumentIndex,
    _cross_page_partners,
    _index_document,
)
from saknussemm.core.preflight import _preflight
from saknussemm.core.rendering import _render_outputs
from saknussemm.core.report import _build_correction_report
from saknussemm.core.result import CorrectionResult, _build_correction_result
from saknussemm.core.provenance import (
    _build_run_provenance,
    digests_of_the_bytes_decided_on,
)
from saknussemm.core.protocols import (
    WordGeometryResolver,
    EditProducer,
    FormatAdapter,
    PipelineObserver,
    ProducerMetadata,
    StructuredCompletionClient,
)
from saknussemm.core.quality import (
    DEFAULT_ROUTING_POLICY,
    QEScorer,
    RoutingPolicy,
)
from saknussemm.core.confidence import (
    ConfidenceScorer,
    HeuristicScorer,
)
from saknussemm.core.schemas import (
    DEFAULT_GUARD_CONFIG,
    DEFAULT_CONFIDENCE_POLICY,
    DEFAULT_LOSS_POLICY,
    DEFAULT_REVIEW_POLICY,
    DEFAULT_PAIRING_POLICY,
    DEFAULT_RETRY_POLICY,
    ChunkPlannerConfig,
    DocumentManifest,
    GuardConfig,
    PageImage,
    ConfidencePolicy,
    LossPolicy,
    ReviewPolicy,
    PairingPolicy,
    RetryPolicy,
)


class CorrectionPipeline:
    """Pure orchestration of the correction pipeline over an EditProducer.

    Dependencies are injected via the constructor; the pipeline never
    reaches for global state. The instance holds only immutable
    configuration: every run creates a fresh :class:`RunContext` and its
    own deep copy of the input manifest (ADR-011 — the input is never
    modified, the instance is reentrant), and everything the run decided
    is exposed on the final `CorrectionResult` for the caller to persist.

    §5.1 resorption — the pipeline is constructed around an
    :class:`EditProducer`; there is no ``api_key``/``model`` anywhere on
    the pipeline surface. For the common LLM case, use
    :meth:`for_provider`, which wraps a :class:`StructuredCompletionClient` +
    credentials into an ``LLMEditProducer`` and sets the provenance
    labels in one call.
    """

    def __init__(
        self,
        producer: EditProducer,
        observer: PipelineObserver,
        config: ChunkPlannerConfig | None = None,
        retry_policy: RetryPolicy | None = None,
        guard_config: GuardConfig | None = None,
        pairing_policy: PairingPolicy | None = None,
        format_adapter: FormatAdapter | None = None,
        *,
        loss_policy: LossPolicy | None = None,
        review_policy: ReviewPolicy | None = None,
        producer_metadata: ProducerMetadata | None = None,
        confidence_policy: ConfidencePolicy | None = None,
        confidence_scorers: tuple[ConfidenceScorer, ...] | None = None,
        qe_scorer: QEScorer | None = None,
        routing_policy: RoutingPolicy | None = None,
        escalation_producer: EditProducer | None = None,
        word_geometry: WordGeometryResolver | None = None,
    ) -> None:
        self.producer = producer
        self.observer = observer
        self.config = config or ChunkPlannerConfig()
        # Retry ramp / attempt cap / per-chunk budget. Default reproduces
        # the historical temperature ramp (0.0/0.3/0.5) and 3-attempt cap.
        self.retry_policy = retry_policy or DEFAULT_RETRY_POLICY
        # All anti-migration / acceptance thresholds. Default reproduces
        # the historical constants byte-for-byte.
        self.guard_config = guard_config or DEFAULT_GUARD_CONFIG
        # §11 — provenance only. Hyphen pairing happens at PARSE time, before
        # the pipeline exists; pass the same PairingPolicy you parsed with so
        # the configuration fingerprint stamped into the corrected XML covers
        # every §8.2 policy. The pipeline itself never re-pairs lines.
        self.pairing_policy = pairing_policy or DEFAULT_PAIRING_POLICY
        # ADR-012 — what a run does when projecting a correction would
        # lose format granularity: REPORT (default, historical) counts
        # and attributes; STRICT rejects the unit pre-projection.
        self.loss_policy = loss_policy or DEFAULT_LOSS_POLICY
        # Which corrections the run declares it cannot establish. ON by
        # default; writes no text, so it changes what a run REPORTS only.
        self.review_policy = review_policy or DEFAULT_REVIEW_POLICY
        # Line confidences on the report. DROP (default) computes
        # nothing; REPORT_ONLY fills LineOutcome.confidence via the
        # injected scorers (default: the zero-dependency HeuristicScorer).
        # Outside the §8.2 composite fingerprint until write_wc unlocks —
        # report-only never affects the corrected XML.
        self.confidence_policy = confidence_policy or DEFAULT_CONFIDENCE_POLICY
        self.confidence_scorers: tuple[ConfidenceScorer, ...] = (
            confidence_scorers
            if confidence_scorers is not None
            else (HeuristicScorer(),)
        )
        # hybrid-selective routing. A line the QE
        # scorer + RoutingPolicy send to SKIP is confirmed clean and
        # never reaches the producer (no LLM call — the economics). Both
        # OFF by default: no scorer, and DEFAULT_ROUTING_POLICY routes
        # every line to LLM, so a default run is byte-identical. A hyphen
        # unit is NEVER skipped (atomicity) — its members always route to
        # the producer. Outside the §8.2 fingerprint until a run actually
        # skips (same rule that held ConfidencePolicy out until write_wc).
        self.qe_scorer = qe_scorer
        self.routing_policy = routing_policy or DEFAULT_ROUTING_POLICY
        # §5.2 bis — the ESCALATE tier's producer.
        # When set AND routing is on, a non-hyphen line the QE scorer +
        # RoutingPolicy send to ESCALATE is corrected by THIS producer (a
        # VLM) instead of the primary text producer, on a per-line basis —
        # the VLM routed only to the lines that earn its cost. None (the
        # default) keeps the historical behaviour: ESCALATE lines go to the
        # primary producer exactly as before, so a default run is
        # byte-identical. A hyphen unit is NEVER escalated (atomicity — a
        # pair split across two producers could not reconcile), so its
        # members always route to the primary producer.
        self.escalation_producer = escalation_producer
        # §3 format seam — None derives the adapter from the MANIFEST's
        # stamped source_format at write time (_adapter_for_format); an
        # injected adapter that contradicts that format is refused at
        # run start. There is no implicit default format.
        self.format_adapter = format_adapter
        # The slow path's resolver seam (WordGeometryResolver), reachable
        # without writing an adapter: the derived ALTO adapter carries it.
        # Exclusive with an injected adapter, which is where a resolver
        # would otherwise be set; refused for a PAGE document at run
        # start (no geometric slow path there).
        if word_geometry is not None and format_adapter is not None:
            raise ConfigurationError(
                "give word_geometry OR a format_adapter, not both: an injected "
                "adapter carries its own resolver (AltoFormatAdapter("
                "word_geometry=...))"
            )
        self.word_geometry = word_geometry
        # §11 — provenance identity stamped into the corrected XML's
        # processingStep (ProducerMetadata replaces the bare
        # provider_name/model strings — a rules producer has no "model").
        # Explicit constructor metadata wins; else the producer's own
        # declaration (optional `metadata` attribute, same convention as
        # requires_full_coverage); else anonymous. The pipeline never
        # dials a vendor either way.
        if producer_metadata is None:
            declared = getattr(producer, "metadata", None)
            producer_metadata = (
                declared if isinstance(declared, ProducerMetadata) else None
            )
        self.producer_metadata = producer_metadata or ProducerMetadata()
        # No reentrancy guard (ADR-011): the instance carries only
        # immutable configuration, and every run works on a fresh
        # RunContext plus its own deep copy of the input manifest, so
        # concurrent runs on one instance cannot contaminate each other.
        # A shared observer still sees interleaved events — inherent to
        # sharing one, and the caller's choice.

    @classmethod
    def for_provider(
        cls,
        provider: StructuredCompletionClient,
        *,
        api_key: str,
        model: str,
        provider_name: str = "unknown",
        observer: PipelineObserver,
        system_prompt: str | None = None,
        output_schema: dict[str, Any] | None = None,
        uncertainty_channel: bool = False,
        lexicon: set[str] | None = None,
        **pipeline_kwargs: Any,
    ) -> CorrectionPipeline:
        """Build a pipeline around a raw ``StructuredCompletionClient`` (§5.1).

        The core only requires ``complete_structured``: a
        client with no ``list_models`` is fully supported (model
        discovery is application vocabulary, see ``ModelCatalog``).

        Composition-boundary convenience: wraps the provider + credentials
        + prompt contract into an ``LLMEditProducer`` so callers migrating
        from the legacy ``run(api_key=…, model=…, provider_name=…)`` keep a
        one-call setup. The import is function-local — this is one of the
        two pinned lazy composition sites the import-contract test allows
        in core (the other is the adapter resolution in
        ``_render_outputs``).

        The named parameters here are the ones this constructor OWNS —
        the vendor call (``provider``, ``api_key``, ``model``,
        ``provider_name``) and the prompt contract it hands the producer
        (``system_prompt``, ``output_schema``, ``uncertainty_channel``,
        ``lexicon``) — plus ``observer``, which is kept named for a reason
        worth stating: it is REQUIRED by ``__init__``, so forwarding it
        would move the error from this call site into the constructor,
        turning a missing-argument message about ``for_provider`` into one
        about a function the caller did not call. Optional configuration
        has no such problem and goes through ``**pipeline_kwargs``
        (`RM-03`).

        Re-declaring the optional knobs here would be a SECOND declaration
        of the constructor's signature with nothing making the two agree: a
        knob added to ``__init__`` and forgotten here is silently
        unreachable through this door, and a drifting default is invisible
        in review. ``tests/test_public_api_snapshot.py`` pins both
        signatures so the loss of explicitness stays visible where consumers
        read it.
        """
        from saknussemm.producers.llm_edit import LLMEditProducer

        producer = LLMEditProducer(
            provider,
            api_key,
            model,
            system_prompt=system_prompt,
            output_schema=output_schema,
            uncertainty_channel=uncertainty_channel,
            lexicon=lexicon,
        )
        return cls(
            producer=producer,
            observer=observer,
            **pipeline_kwargs,
            # Vendor vocabulary is native HERE (the LLM convenience):
            # the two strings become the generic identity envelope. The
            # producer's configuration fingerprint (prompt + schema)
            # rides along — the explicit envelope overrides IDENTITY,
            # it must not erase configuration provenance (§11).
            producer_metadata=ProducerMetadata(
                name=provider_name,
                implementation=model,
                configuration_fingerprint=producer.metadata.configuration_fingerprint,
            ),
        )

    def config_fingerprint(self) -> str:
        """Stable 16-hex hash over the pipeline's §8.2 policies (§11).

        Public and reproducible from the public API alone: it is the sha256
        (truncated to 16 hex chars) of the sorted JSON object mapping each
        policy name to its ``policy_fingerprint()``::

            {"chunk_planner": …, "guard": …, "loss": …, "pairing": …, "retry": …}

        Covers all five §8.2 policies — RetryPolicy, GuardConfig,
        ChunkPlannerConfig, PairingPolicy and LossPolicy (ADR-012) — so
        the ``processingStep`` stamped into a corrected XML records the
        exact configuration it was produced under, and a consumer holding
        the same policy objects can recompute and verify it.
        """
        payload = json.dumps(
            {
                "chunk_planner": self.config.policy_fingerprint(),
                "guard": self.guard_config.policy_fingerprint(),
                # ADR-012 — decision-affecting (strict rejects units), so
                # it must be part of the provenance like every §8.2 policy.
                "loss": self.loss_policy.policy_fingerprint(),
                "pairing": self.pairing_policy.policy_fingerprint(),
                "retry": self.retry_policy.policy_fingerprint(),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def _emit(self, event: ev.EngineEvent) -> None:
        """Render a typed event onto the wire-shaped observer port:
        the dataclass is the payload's single definition; the
        observer keeps receiving ``(event_type, payload_dict)``."""
        self.observer.on_event(event.type, event.payload())

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(
        self,
        *,
        document_manifest: DocumentManifest,
        source_files: dict[str, Path],
        run_id: str | None = None,
        should_abort: Callable[[], bool] | None = None,
        page_images: dict[str, PageImage] | None = None,
    ) -> CorrectionResult:
        """Run the full pipeline. The input manifest is never modified.

        **Immutability & reentrancy (ADR-011)** — the engine works on
        its own deep copy of
        ``document_manifest``: the input is read, never written, so the
        same document object can be run again (or concurrently) and
        every run starts from the original OCR text. All per-run state
        lives in a fresh :class:`RunContext` plus that copy; the
        instance carries only immutable configuration, so one pipeline
        instance supports concurrent ``run()`` calls (within one event
        loop — instances are not thread-safe). The run's decisions are
        returned on the result
        (:attr:`CorrectionResult.decisions`), not written back onto the
        caller's manifest.

        Credentials and the vendor call live inside the injected
        :class:`EditProducer` (see :meth:`for_provider`); the provenance
        labels are constructor state. Nothing here carries an
        ``api_key``.

        ``page_images`` (§5.1) — optional mapping of **page_id** (document-
        unique, ADR-007) to a :data:`PageImage`: the historical opaque
        :data:`ImageRef` (str) or the richer, recommended
        :class:`~saknussemm.core.schemas.ImageAsset` — one image per
        physical page, so a multipage XML carries one ref per scan. The
        library forwards each page's ref verbatim into the producer payload
        when the producer asks (``wants_image``) and NEVER opens it (I4).
        A ``wants_image`` producer run without a complete mapping raises
        :class:`ConfigurationError` before any work starts; a key matching
        no page (e.g. a legacy file-name key) is refused explicitly.

        ``run_id`` is an optional identifier embedded in the emitted
        :class:`CorrectionReport` (which is also what ``trace.json``
        contains) so consumers can correlate the persisted report with
        their own job/request id. Generated as a uuid4 when omitted; it
        never leaks back into the public events.

        ``should_abort`` is an optional cancellation probe. It is
        polled between pages and between chunks; when it returns ``True``
        the run raises :class:`CorrectionAborted` and no result is
        produced. A provider call already in flight is not interrupted —
        cancellation is cooperative and observed only at chunk/page
        boundaries.

        **Persistence (ADR-011)** — the engine never writes: the
        returned :class:`CorrectionResult` carries the corrected XML
        (:attr:`~CorrectionResult.corrected_files`) and the §9 report,
        and persisting them is the caller's choice —
        :meth:`CorrectionResult.write` for the simple case, or a
        host-owned transaction when the host needs commit/discard
        semantics.
        """
        # ADR-011 — the working copy IS the run's mutable state;
        # the caller's document stays exactly as parsed.
        return await self._run_impl(
            document_manifest=document_manifest.model_copy(deep=True),
            source_files=source_files,
            run_id=run_id,
            should_abort=should_abort,
            page_images=page_images,
        )

    async def _run_impl(
        self,
        *,
        document_manifest: DocumentManifest,
        source_files: dict[str, Path],
        run_id: str | None,
        should_abort: Callable[[], bool] | None,
        page_images: dict[str, PageImage] | None,
    ) -> CorrectionResult:
        """Body of :meth:`run`, on the run's private manifest copy — the
        sequence and nothing else: refuse what cannot proceed, index,
        correct every page, finalise the decisions, render, report. Each
        step lives in its own module.
        """
        run_id = run_id or str(uuid.uuid4())
        # One fresh context per execution; no per-run state remains on
        # the instance.
        ctx = RunContext(should_abort=should_abort)

        if self.word_geometry is not None and document_manifest.source_format not in (
            None,
            "alto",
        ):
            raise ConfigurationError(
                f"word_geometry was given but the manifest was parsed as "
                f"{document_manifest.source_format!r}: only the ALTO rewriter "
                "has a geometric slow path to hand a resolver"
            )

        _preflight(
            producer=self.producer,
            escalation_producer=self.escalation_producer,
            format_adapter=self.format_adapter,
            document_manifest=document_manifest,
            source_files=source_files,
            page_images=page_images,
            ctx=ctx,
        )

        index = _index_document(document_manifest)
        self._emit(
            ev.DocumentParsed(
                total_pages=document_manifest.total_pages,
                total_lines=document_manifest.total_lines,
                hyphen_pairs=index.hyphen_pairs,
            )
        )

        total_chunks, total_reconciled = await self._process_pages(
            ctx=ctx,
            document_manifest=document_manifest,
            index=index,
            should_abort=should_abort,
        )

        decisions, sidecar_entries = _finalize_document(
            guard_config=self.guard_config,
            loss_policy=self.loss_policy,
            review_policy=self.review_policy,
            document_manifest=document_manifest,
            all_lines=index.lines,
            traces=index.traces,
        )

        render = await _render_outputs(
            format_adapter=self.format_adapter,
            word_geometry=self.word_geometry,
            producer_metadata=self.producer_metadata,
            config_fingerprint=self.config_fingerprint(),
            emit=self._emit,
            document_manifest=document_manifest,
            source_files=source_files,
            traces=index.traces,
            decisions=decisions,
        )

        source_digests = digests_of_the_bytes_decided_on(
            document_manifest, source_files
        )

        report = _build_correction_report(
            run_id=run_id,
            document_manifest=document_manifest,
            decisions=decisions,
            traces=index.traces,
            ctx=ctx,
            provenance=_build_run_provenance(
                self,
                document_manifest=document_manifest,
                source_digests=source_digests,
                image_assets=ctx.image_ref_by_page_id,
            ),
            render=render,
            sidecar_entries=sidecar_entries,
            confidence_policy=self.confidence_policy,
            confidence_scorers=self.confidence_scorers,
            all_lines=index.lines,
        )

        return _build_correction_result(
            ctx=ctx,
            decisions=decisions,
            traces=index.traces,
            report=report,
            corrected_files=render.corrected_files,
            source_digests=source_digests,
            total_chunks=total_chunks,
            total_reconciled=total_reconciled,
        )

    async def _process_pages(
        self,
        *,
        ctx: RunContext,
        document_manifest: DocumentManifest,
        index: DocumentIndex,
        should_abort: Callable[[], bool] | None,
    ) -> tuple[int, int]:
        """Correct every page in manifest order.

        Returns the run's ``(chunks, reconciled pairs)`` totals. Each page
        is given the partners its hyphen units need from other pages: a
        unit straddling a page break is still ONE unit, and the page that
        holds one end cannot resolve it from its own lines (ADR-010).
        """
        driver = self._page_driver()
        total_chunks = 0
        total_reconciled = 0
        for page in document_manifest.pages:
            # Cooperative cancellation between pages, before any work
            # on this page and before any output is written.
            if should_abort is not None and should_abort():
                raise CorrectionAborted(
                    f"run aborted before page {page.page_id!r} (page {page.page_index})"
                )
            page_chunks, page_reconciled = await driver.process_page(
                ctx=ctx,
                page=page,
                document_id=document_manifest.document_id,
                traces=index.traces,
                cross_page_partners=_cross_page_partners(page, index.lines),
                should_abort=should_abort,
            )
            total_chunks += page_chunks
            total_reconciled += page_reconciled
        return total_chunks, total_reconciled

    def _page_driver(self) -> PageDriver:
        """Bind this pipeline's configured components into the driver that
        runs a page. Built per run, holding no run state — the engine's
        configuration is immutable, so two concurrent runs may share it."""
        return PageDriver(
            producer=self.producer,
            config=self.config,
            retry_policy=self.retry_policy,
            guard_config=self.guard_config,
            router=ChunkRouter(
                qe_scorer=self.qe_scorer,
                routing_policy=self.routing_policy,
                escalation_producer=self.escalation_producer,
            ),
            emit=self._emit,
        )

    def run_sync(
        self,
        *,
        document_manifest: DocumentManifest,
        source_files: dict[str, Path],
        run_id: str | None = None,
        should_abort: Callable[[], bool] | None = None,
        page_images: dict[str, PageImage] | None = None,
    ) -> CorrectionResult:
        """Synchronous façade over :meth:`run` (§8.1).

        Wraps the coroutine in :func:`asyncio.run` for consumers without an
        event loop (scripts, notebooks, CLIs). Same parameters and return
        value as :meth:`run`. Must NOT be called from within a running
        event loop — ``asyncio.run`` raises ``RuntimeError`` there; use
        ``await pipeline.run(...)`` instead.
        """
        return asyncio.run(
            self.run(
                document_manifest=document_manifest,
                source_files=source_files,
                run_id=run_id,
                should_abort=should_abort,
                page_images=page_images,
            )
        )


# --- public surface ---
__all__ = [
    "sanitize_error",
    "CorrectionResult",
    "CorrectionPipeline",
]
