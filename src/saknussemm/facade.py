"""The three-line happy path (§2): load → correct → write.

::

    document = saknussemm.load("page.xml")            # format by namespace
    result = await saknussemm.correct(document, producer=producer)
    result.write("out/")

Observer, format adapter, manifest plumbing: optional, never required
for the simple case. :func:`load` sniffs each file's root namespace and
dispatches to the matching parser (ALTO or PAGE — one format per
document); :func:`correct` / :func:`correct_sync` wrap a default
:class:`~saknussemm.core.pipeline.CorrectionPipeline` around any
:class:`~saknussemm.core.protocols.EditProducer` with a no-op observer.
Power users keep constructing the pipeline directly — every knob this
façade hides stays available there.

This module imports the format packages (lxml), so it is exported
LAZILY from the top level: ``import saknussemm`` alone stays pure.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from pathlib import Path
from typing import Any

from saknussemm.core.pipeline import CorrectionPipeline, CorrectionResult
from saknussemm.core.protocols import EditProducer, WordGeometryResolver
from saknussemm.core.schemas import DocumentManifest, PageImage
from saknussemm.errors import ParseError
from saknussemm.formats.loader import build_document_manifest


class _NullObserver:
    """The façade's default: the simple path needs no event sink."""

    def on_event(self, event_type: str, payload: dict[str, Any]) -> None:
        pass


@dataclass(frozen=True)
class LoadedDocument:
    """What :func:`load` hands to :func:`correct`: the parsed manifest
    plus the name → path map a run needs to render its outputs."""

    manifest: DocumentManifest
    source_paths: dict[str, Path]


def load(*paths: str | Path) -> LoadedDocument:
    """Parse one or more ALTO/PAGE files into a single document.

    The format is detected per file from the root namespace; all files
    of one document must share it (a mixed ALTO+PAGE document has no
    single rewriter). File basenames become the artefact keys
    (``result.corrected_files``), so they must be unique across paths.
    """
    if not paths:
        raise ParseError("saknussemm.load() needs at least one file path")
    resolved = [Path(p) for p in paths]

    by_name: dict[str, Path] = {}
    for path in resolved:
        if path.name in by_name:
            raise ParseError(
                f"two source files share the basename {path.name!r} "
                f"({by_name[path.name]} and {path}) — basenames key the "
                "corrected artefacts and must be unique; rename one file."
            )
        by_name[path.name] = path

    # Format sniffing, the one-format-per-document check and the parser
    # dispatch all live in formats.loader (shared with any host that
    # ingests user files with its own (path, name) pairs).
    manifest = build_document_manifest([(p, p.name) for p in resolved])
    return LoadedDocument(manifest=manifest, source_paths=by_name)


async def correct(
    document: LoadedDocument,
    *,
    producer: EditProducer,
    run_id: str | None = None,
    should_abort: Callable[[], bool] | None = None,
    page_images: dict[str, PageImage] | None = None,
    word_geometry: WordGeometryResolver | None = None,
) -> CorrectionResult:
    """Run the correction pipeline over a loaded document (§2).

    ``word_geometry``: a resolver for the ALTO slow path's word boxes
    (hans's CTC resolver, say); see :class:`WordGeometryResolver`.

    Wraps a default :class:`CorrectionPipeline` (no-op observer, default
    policies, provenance from the producer's own declared metadata)
    around ``producer``. Every knob — policies, observer, explicit
    metadata — lives on the pipeline constructor for callers who need
    it; this function is the three-line path, not a second surface.
    """
    pipeline = CorrectionPipeline(
        producer=producer, observer=_NullObserver(), word_geometry=word_geometry
    )
    return await pipeline.run(
        document_manifest=document.manifest,
        source_files=document.source_paths,
        run_id=run_id,
        should_abort=should_abort,
        page_images=page_images,
    )


def correct_sync(
    document: LoadedDocument,
    *,
    producer: EditProducer,
    run_id: str | None = None,
    should_abort: Callable[[], bool] | None = None,
    page_images: dict[str, PageImage] | None = None,
    word_geometry: WordGeometryResolver | None = None,
) -> CorrectionResult:
    """Synchronous twin of :func:`correct` (scripts, notebooks, CLIs).

    Must not be called from within a running event loop — use
    ``await saknussemm.correct(...)`` there.
    """
    pipeline = CorrectionPipeline(
        producer=producer, observer=_NullObserver(), word_geometry=word_geometry
    )
    return pipeline.run_sync(
        document_manifest=document.manifest,
        source_files=document.source_paths,
        run_id=run_id,
        should_abort=should_abort,
        page_images=page_images,
    )


__all__ = [
    "LoadedDocument",
    "correct",
    "correct_sync",
    "load",
]
