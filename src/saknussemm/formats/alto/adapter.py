"""ALTO implementation of the core ``FormatAdapter`` port (§3 seam)."""

from __future__ import annotations

from pathlib import Path

from saknussemm.core.protocols import RewriteResult, WordGeometryResolver
from saknussemm.core.schemas import PageManifest
from saknussemm.formats.alto.rewriter import rewrite_alto_file


class AltoFormatAdapter:
    """Thin adapter: the pipeline's format seam, bound to ALTO.

    ``word_geometry`` is the slow path's resolver seam
    (:class:`~saknussemm.core.protocols.WordGeometryResolver`), reached
    through the public pipeline for the first time here. It used to be
    accepted by :func:`rewrite_alto_file` only: a host wanting hans's CTC
    resolver had to write its own adapter (contre-revue du 7/10/2026).
    """

    #: Matches ``DocumentManifest.source_format`` — the engine refuses a
    #: run whose manifest declares a different format.
    format_name = "alto"

    def __init__(self, *, word_geometry: WordGeometryResolver | None = None) -> None:
        self.word_geometry = word_geometry

    def rewrite_file(
        self,
        xml_path: Path,
        pages: list[PageManifest],
        provider: str,
        model: str,
        *,
        lib_version: str | None = None,
        config_fingerprint: str | None = None,
    ) -> RewriteResult:
        return rewrite_alto_file(
            xml_path,
            pages,
            provider,
            model,
            lib_version=lib_version,
            config_fingerprint=config_fingerprint,
            word_geometry=self.word_geometry,
        )


__all__ = ["AltoFormatAdapter"]
