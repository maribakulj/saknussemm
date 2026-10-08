"""Everything a run refuses BEFORE spending any correction work.

Six checks, and the reason they are one function rather than six scattered
guards is that they share a property: each turns a mid-run surprise into a
start-up error. A `source_files` mapping that does not describe the same
document as the manifest, a vision producer with no images, a producer whose
declared capabilities contradict its wiring, an injected adapter that
disagrees with the format the manifest was parsed as, a duplicate identity,
an image key matching no page — every one of them would otherwise fail late,
confusingly, with correction work already spent. The first of them would not
fail at all: it would report success over a document half of which reached
no artefact.

Lifted out of ``_run_impl``: the 311-line orchestrator opened with 60
lines that decide nothing about how the run proceeds, only whether it may
start at all.
"""

from __future__ import annotations

from pathlib import Path

from saknussemm.core.context import RunContext
from saknussemm.core.provenance import source_digest
from saknussemm.core.identity import (
    ensure_unique_identities,
    ensure_unique_page_ids_across_files,
)
from saknussemm.core.protocols import (
    EditProducer,
    FormatAdapter,
    require_capabilities,
    require_page_images,
)
from saknussemm.core.schemas import DocumentManifest, PageImage, PageManifest
from saknussemm.core.sources import SourceSnapshot
from saknussemm.errors import ConfigurationError, ParseError


def _require_every_source(
    document_manifest: DocumentManifest,
    source_files: dict[str, Path],
) -> None:
    """Every file the manifest was parsed from must be renderable, or none.

    Refusing at start-up rather than reporting a partial render is the
    whole point: a run that half-renders has already spent the producer
    calls, and its report is indistinguishable from a complete one except
    by summing two counters that nothing says should agree.
    """
    if not source_files:
        return
    declared = set(document_manifest.source_files)
    supplied = set(source_files)
    missing = sorted(declared - supplied)
    unknown = sorted(supplied - declared)
    if not missing and not unknown:
        return
    detail = []
    if missing:
        detail.append(
            f"{missing} were parsed into the manifest but have no source file, "
            "so their decided lines would reach no artefact"
        )
    if unknown:
        detail.append(
            f"{unknown} were supplied but name no page in the manifest, so "
            "they would be read, hashed into the provenance, and contribute "
            "nothing"
        )
    raise ConfigurationError(
        "`source_files` does not describe the same document as the manifest: "
        + "; ".join(detail)
        + ". Pass every source the manifest was built from, or pass none at "
        "all for a decide-only run."
    )


def _snapshot_sources(
    document_manifest: DocumentManifest,
    source_files: dict[str, Path],
) -> dict[str, SourceSnapshot]:
    """Capture the exact bytes the built-in adapters will render.

    A parser's digest must match this capture before any producer is called.
    Keeping the verified bytes closes the gap between that check and a
    later reopen after correction. Hand-built manifests have no digest to
    compare, but still render and attest the captured bytes.
    """
    stamped = document_manifest.source_digests
    changed: list[str] = []
    snapshots: dict[str, SourceSnapshot] = {}
    for name, path in sorted(source_files.items()):
        # A source that has become unreadable is a §8.4 event, not a
        # configuration one, and reading it here must not be the one place
        # that lets an OSError out raw — which is exactly what the first
        # version of this check did.
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise ParseError(f"{name!r}: cannot read source file: {exc}") from exc
        snapshots[name] = SourceSnapshot(path, raw)
        if name in stamped and source_digest(raw) != stamped[name]:
            changed.append(name)
    if changed:
        raise ConfigurationError(
            f"{changed} no longer hold the bytes they were parsed from. Either "
            "`source_files` names a different file for one of these, or the "
            "file changed since it was parsed. Writing anyway would deliver "
            "decisions made on one document inside another one's markup — and "
            "the projection check could not tell, because it compares the "
            "artefact to the decisions the artefact was built from. Re-parse "
            "the current bytes, or point at the files that were parsed."
        )
    return snapshots


def _preflight(
    *,
    producer: EditProducer,
    escalation_producer: EditProducer | None,
    format_adapter: FormatAdapter | None,
    document_manifest: DocumentManifest,
    source_files: dict[str, Path],
    page_images: dict[str, PageImage] | None,
    ctx: RunContext,
) -> dict[str, SourceSnapshot]:
    """Validate the run, populate its image envelope and capture its sources."""
    # The manifest says which files it was parsed from; `source_files`
    # says which ones will be rewritten. Nothing compared the two, and
    # this function could not: it did not receive `source_files` at all.
    #
    # Measured 2026-08-17 — a manifest parsed from `a.xml` + `b.xml` run
    # with only `a.xml` supplied: the run SUCCEEDED, `report.total_lines`
    # counted both files' lines, and `projection_fidelity` counted one
    # file's. Half the decided lines existed in no artefact, and the only
    # trace was that arithmetic.
    #
    # An empty mapping stays legal and means "decide, render nothing": the
    # dry run is a documented mode, and five test files rely on it.
    _require_every_source(document_manifest, source_files)
    # §5.1 — a vision producer without its images is a start-up error,
    # never a silent image-less call.
    require_page_images(producer, document_manifest.pages, page_images)
    # §5.2 bis — a producer whose declared capabilities
    # contradict its wiring (wants images but vision=False) is a
    # start-up error, not a mid-run surprise.
    require_capabilities(producer)
    # the escalation (vision) producer is the one that needs
    # images: preflight it too, so a run that WILL escalate fails at
    # start-up if its VLM lacks a scan, never mid-run.
    if escalation_producer is not None:
        require_page_images(escalation_producer, document_manifest.pages, page_images)
        require_capabilities(escalation_producer)

    # §3 — the format travels with the document. An injected adapter
    # that contradicts the format the manifest was parsed as would
    # only surface at write time (as a confusing projection failure);
    # refuse it before any correction work is spent. Adapters without
    # a ``format_name`` (custom implementations) are trusted as-is.
    declared = document_manifest.source_format
    adapter_format = getattr(format_adapter, "format_name", None)
    if declared and adapter_format and declared != adapter_format:
        raise ConfigurationError(
            f"the injected format_adapter writes {adapter_format!r} but "
            f"the manifest was parsed as {declared!r} — parse with the "
            "matching saknussemm parser or inject the matching adapter"
        )

    # ADR-007 — identity-uniqueness invariant, enforced at the pipeline
    # door so hand-built manifests get the same guarantee as
    # parser-built ones: within one source file every page/block/line
    # ID must be unique (correction-to-line association is keyed by
    # bare line_id per file), and page_ids must be unique across the
    # whole document (trace keys, per-page image/dimension lookups).
    pages_by_file: dict[str, list[PageManifest]] = {}
    for page in document_manifest.pages:
        pages_by_file.setdefault(page.source_file, []).append(page)
    for src_name, src_pages in pages_by_file.items():
        ensure_unique_identities(src_pages, src_name)
    ensure_unique_page_ids_across_files(document_manifest.pages)
    # §4.1 — per-page vision envelope lookups. Pure copying: the
    # ImageRef stays an opaque string end to end. A key matching no
    # page is refused: it is almost always a legacy file-name key
    # from the pre-page_images contract, silently dropping it would
    # reproduce the old wrong-image behaviour.
    images = page_images or {}
    known_pages = {page.page_id for page in document_manifest.pages}
    unknown = sorted(set(images) - known_pages)
    if unknown:
        raise ConfigurationError(
            f"page_images keys must be page ids; {unknown} match no "
            "page of this document (file-name keys are no longer "
            "accepted — pass one ImageRef per page_id)"
        )
    ctx.image_ref_by_page_id = dict(images)
    ctx.page_dims = {
        page.page_id: (page.page_width, page.page_height)
        for page in document_manifest.pages
    }
    return _snapshot_sources(document_manifest, source_files)
