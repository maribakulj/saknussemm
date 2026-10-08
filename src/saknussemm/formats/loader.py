"""Namespace-driven format detection and the generic manifest builder (§3).

The document says what it is: each file's root namespace selects the
ALTO or PAGE parser — nobody passes a format flag. One format per
document (a mixed ALTO+PAGE batch has no single rewriter).

Any host ingesting user files should build its manifest through this
module rather than importing a format-specific parser, because a parser
asked for the wrong format finds nothing rather than objecting. Half of
that trap is now closed and half is not, so the halves are worth
distinguishing: :func:`alto.parser.build_document_manifest` sniffs each
file and *refuses* a non-ALTO one, while :func:`alto.parser.parse_alto_file`
still returns an empty page list for a valid PAGE file — 0 pages, no
error, a silent mis-read. A host calling the single-file entry point
directly is still on its own.

``saknussemm.load()`` (the facade) is this module plus
basename bookkeeping; hosts that carry their own (path, source_name)
pairs and a :class:`PairingPolicy` call :func:`build_document_manifest`
directly.
"""

from __future__ import annotations

from pathlib import Path


from saknussemm.core.protocols import FormatAdapter
from saknussemm.core.schemas import (
    DEFAULT_PAIRING_POLICY,
    DocumentManifest,
    PairingPolicy,
)
from saknussemm.errors import ConfigurationError, ParseError
from saknussemm.formats._xml import (
    mislabelled_utf8,
    sniff_format,
)


def build_document_manifest(
    files: list[tuple[Path, str]],
    pairing_policy: PairingPolicy = DEFAULT_PAIRING_POLICY,
) -> DocumentManifest:
    """Build a manifest from ``(xml_path, source_name)`` pairs, any format.

    Same signature as the per-format builders it dispatches to
    (``formats.alto.parser`` / ``formats.page.parser``), so it is a
    drop-in replacement wherever one of them was hard-wired. The format
    is sniffed per file from the root namespace; a mixed batch raises
    :class:`ParseError` (one document, one format — ADR: a document has
    exactly one rewriter).
    """
    if not files:
        raise ParseError("build_document_manifest() needs at least one file")

    formats = {name: sniff_format(path) for path, name in files}
    distinct = set(formats.values())
    if len(distinct) > 1:
        detail = ", ".join(f"{name}: {fmt}" for name, fmt in formats.items())
        raise ParseError(
            f"one document, one format — got a mix ({detail}). "
            "Load ALTO and PAGE files as separate documents."
        )

    if distinct == {"page"}:
        from saknussemm.formats.page.parser import (
            build_document_manifest as build,
        )
    else:
        from saknussemm.formats.alto.parser import (
            build_document_manifest as build,
        )
    manifest = build(files, pairing_policy=pairing_policy)

    # A file read as something other than what it declared is an override,
    # and an override that nobody can see is exactly the undeclared
    # alteration the contract forbids. `read_source_tree` already
    # applied it —
    # here it is *named*, once, where the caller receives the document.
    # Same rule, one definition (``mislabelled_utf8``), two callers.
    overrides = {
        name: declared
        for path, name in files
        if (declared := mislabelled_utf8(path.read_bytes())) is not None
    }
    if overrides:
        manifest = manifest.model_copy(update={"source_encodings": overrides})
    return manifest


def adapter_for_format(
    source_format: str | None, *, word_geometry: object | None = None
) -> FormatAdapter:
    """Resolve the adapter the MANIFEST declares — no implicit default (§3).

    The format travels with the document: the parsers stamp
    ``DocumentManifest.source_format`` and the engine derives the matching
    adapter from it. A manifest without a stamped format (hand-built) has
    no derivable adapter, and silently assuming one — the historical ALTO
    default — is exactly how a PAGE document ended up rewritten by the
    ALTO rewriter.

    Lives next to :func:`build_document_manifest` because the two answer
    the same question: which module speaks this format. In
    ``core/provenance.py`` it was the one place the pure core enumerated
    ALTO and PAGE by name — lazily, so no import rule was broken, but the
    knowledge was there and a third format
    would have had to be added to a core module to be usable.

    The imports stay function-local: this module is reached from ``core``
    lazily too (``core/rendering.py``, the single remaining lazy site),
    and eager adapter imports would pull both rewriters for a run that
    writes one format.
    """
    if source_format == "alto":
        from saknussemm.formats.alto.adapter import AltoFormatAdapter

        return AltoFormatAdapter(word_geometry=word_geometry)  # type: ignore[arg-type]
    if source_format == "page":
        if word_geometry is not None:
            raise ConfigurationError(
                "word_geometry was given but the document is PAGE: the PAGE "
                "rewriter keeps or drops Word boxes and has no geometric slow "
                "path to hand a resolver (docs/formats.md)"
            )
        from saknussemm.formats.page.adapter import PageFormatAdapter

        return PageFormatAdapter()
    raise ConfigurationError(
        f"the manifest declares no derivable format "
        f"(source_format={source_format!r}); load the document through a "
        "saknussemm format parser, or inject format_adapter explicitly "
        "on the pipeline"
    )


__all__ = ["adapter_for_format", "build_document_manifest", "sniff_format"]
