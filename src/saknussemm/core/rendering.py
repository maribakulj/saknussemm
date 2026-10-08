"""Rewriting the corrected files in memory, and verifying what they say.

The last stage before a run hands anything back: the format adapter rewrites
each source file, the projection invariant checks that the bytes carry the
run's decisions, and the per-line traces gain what the rewrite actually did.

Free function: the adapter, the producer's identity, the config fingerprint
stamped into the provenance and the observer callback all arrive as
arguments. Rendering is a step over a manifest and a set of decisions, not a
property of a run.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

from saknussemm.core import events as ev
from saknussemm.core.decisions import DecisionSet
from saknussemm.core.identity import LineRef, line_ref
from saknussemm.core.projection import _verify_projection
from saknussemm.core.fidelity import ProjectionFidelity
from saknussemm.core.protocols import (
    FormatAdapter,
    ProducerMetadata,
    RenderOutcome,
    RewriteResult,
)
from saknussemm.core.schemas import DocumentManifest, LineTrace, PageManifest
from saknussemm.errors import ProjectionError


async def _render_outputs(
    *,
    format_adapter: FormatAdapter | None,
    producer_metadata: ProducerMetadata,
    config_fingerprint: str,
    emit: Callable[[ev.EngineEvent], None],
    document_manifest: DocumentManifest,
    source_files: dict[str, Path],
    traces: dict[LineRef, LineTrace],
    decisions: DecisionSet,
) -> RenderOutcome:
    """Rewrite corrected files in memory and update the traces.

    Returns a :class:`~saknussemm.core.protocols.RenderOutcome`, which is
    also where the contract around an undeliverable file is written.

    ADR-011 — pure computation: nothing is persisted here (the engine has no
    writer; the caller persists from the result). The projection invariant
    verifies against the :class:`RewriteResult`'s texts, read off the very
    tree the bytes were serialized from: the second full parse of the output
    is gone. The heavy ``rewrite_file`` call (a full lxml
    parse/rewrite/serialize of the source file) runs in a worker thread so a
    ~100 MiB rewrite no longer freezes the host's event loop (SSE
    keepalives, /health). Observer events stay ON the loop — emit sites must
    never run from a thread (the store's queues are not thread-safe).
    """
    # §11 — provenance stamped into every corrected file's processingStep.

    # Adapter resolution is lazy (first file to write): a run with no
    # output files — every hand-built-manifest dry-run in the test
    # suite passes source_files={} — needs no format at all.
    adapter: FormatAdapter | None = format_adapter
    losses_total: dict[str, int] = {}
    corrected_files: dict[str, bytes] = {}
    undeliverable: dict[str, str] = {}

    for source_name, xml_path in source_files.items():
        pages_for_file = [
            p for p in document_manifest.pages if p.source_file == source_name
        ]
        if not pages_for_file:
            continue
        if adapter is None:
            # The ONE place core reaches a format module, and it does not
            # know which formats exist: the resolver lives beside the
            # parser dispatch in `formats/loader.py`. Kept lazy so
            # importing any core module never loads lxml.
            from saknussemm.formats.loader import adapter_for_format

            adapter = adapter_for_format(document_manifest.source_format)

        try:
            result, fidelity_by_lid = await _rewrite_and_verify(
                adapter,
                xml_path=xml_path,
                source_name=source_name,
                pages=pages_for_file,
                producer_metadata=producer_metadata,
                config_fingerprint=config_fingerprint,
                decisions=decisions,
            )
        except ProjectionError as failure:
            # No event: `ev.Warning` is chunk-scoped, and this file never
            # reached a chunk boundary. See `RenderOutcome`.
            undeliverable[source_name] = str(failure)
            continue
        corrected_files[source_name] = result.xml_bytes

        # rewriter_stats observability event — pure read-only diagnostic
        # surfacing how each line classified (UNTOUCHED / SUBS_ONLY /
        # FAST_PATH / SLOW_PATH). Zero impact on the corrected XML.
        emit(
            ev.RewriterStats(
                source_stem=xml_path.stem,
                untouched=result.metrics.untouched,
                subs_only=result.metrics.subs_only,
                fast_path=result.metrics.fast_path,
                slow_path=result.metrics.slow_path,
            )
        )
        for key, count in result.losses.items():
            losses_total[key] = losses_total.get(key, 0) + count

        _record_rewrite_on_traces(
            result,
            fidelity_by_lid=fidelity_by_lid,
            pages=pages_for_file,
            traces=traces,
        )

    # No trace persistence anywhere in the engine: trace.json IS the
    # CorrectionReport (§9), carried on the result for the caller.
    return RenderOutcome(losses_total, corrected_files, undeliverable)


async def _rewrite_and_verify(
    adapter: FormatAdapter,
    *,
    xml_path: Path,
    source_name: str,
    pages: list[PageManifest],
    producer_metadata: ProducerMetadata,
    config_fingerprint: str,
    decisions: DecisionSet,
) -> tuple[RewriteResult, dict[str, ProjectionFidelity]]:
    """Rewrite one file, and refuse the result if it does not say what the
    run decided.

    The heavy ``rewrite_file`` call — a full lxml parse/rewrite/serialize —
    runs in a worker thread so a ~100 MiB rewrite does not freeze the host's
    event loop (SSE keepalives, /health). No observer event is emitted from
    in here: emit sites must stay ON the loop, since a host's queues are not
    thread-safe.

    The projection invariant runs BEFORE the bytes go anywhere. A divergent
    artefact is corruption of the deliverable, never a valid output. What it
    CANNOT refuse — a whitespace character the format flattened — comes back
    as a per-line fidelity level and goes on the record instead of
    disappearing.
    """
    from saknussemm import __version__ as _lib_version

    # §11 provenance labels — constructor state since the §5.1 resorption
    # (run() no longer carries provider/model).
    provider_label, model_label = producer_metadata.provenance_labels()
    result = await asyncio.to_thread(
        adapter.rewrite_file,
        xml_path,
        pages,
        provider_label,
        model_label,
        lib_version=_lib_version,
        config_fingerprint=config_fingerprint,
    )
    fidelity_by_lid = _verify_projection(
        source_name,
        pages,
        result.texts,
        decisions,
        result.texts_verbatim,
    )
    return result, fidelity_by_lid


def _record_rewrite_on_traces(
    result: RewriteResult,
    *,
    fidelity_by_lid: dict[str, ProjectionFidelity],
    pages: list[PageManifest],
    traces: dict[LineRef, LineTrace],
) -> None:
    """Fan one file's rewrite out onto the per-line channels it feeds.

    Five channels, each answering a different question and none
    substitutable for another: which path the rewriter took, what the
    artefact ends up saying, how faithfully that carries the decision,
    what the format dropped and on which line (ADR-012), and whether the
    token alignment suspected a word reorder — the last deliberately NOT
    a loss counter, because nothing left the markup and summing it would
    count a non-loss.

    Keys arriving here are bare line_ids: unique per source FILE
    (ADR-007), never document-wide, so they are qualified against this
    file's pages before touching a trace.
    """
    lid_to_ref = {lm.line_id: line_ref(lm) for page in pages for lm in page.lines}

    def put(lid: str, **fields: object) -> None:
        ref = lid_to_ref.get(lid)
        trace = traces.get(ref) if ref is not None else None
        if trace is None:
            return
        for name, value in fields.items():
            setattr(trace, name, value)

    for lid, rewriter_path in result.rewriter_paths.items():
        put(lid, rewriter_path=rewriter_path)
    for lid, output_text in result.texts.items():
        put(lid, output_alto_text=output_text)
    for lid, level in fidelity_by_lid.items():
        put(lid, projection_fidelity=level)
    for lid, line_losses in result.losses_by_line.items():
        put(lid, projection_losses=line_losses)
    for lid in result.word_order_suspected:
        put(lid, word_order_suspected=True)
