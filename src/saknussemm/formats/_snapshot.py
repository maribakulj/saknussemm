"""Run-local source snapshots and checks on the serialized deliverable.

Built-in adapters render the bytes captured before correction starts. The
public path-based adapter protocol stays unchanged: custom adapters are
called normally, with a source stability check on both sides of the call.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from lxml import etree

from saknussemm.core.protocols import FormatAdapter, RewriteResult
from saknussemm.core.schemas import PageManifest
from saknussemm.errors import ParseError, ProjectionError
from saknussemm.formats._references import (
    reference_baseline,
    require_no_new_dangling_references,
)
from saknussemm.formats._xml import (
    detect_namespace,
    make_safe_parser,
    read_source_tree_classified,
    tag,
)
from saknussemm.formats.alto.adapter import AltoFormatAdapter
from saknussemm.formats.alto.rewriter import (
    _extract_texts_from_root as alto_texts,
    rewrite_alto_file,
)
from saknussemm.formats.page.adapter import PageFormatAdapter
from saknussemm.formats.page.rewriter import (
    _extract_texts_from_root as page_texts,
    rewrite_page_file,
)
from saknussemm.formats.validation import SCHEMA_BY_NAMESPACE, validate_bytes


class SnapshotAdapter:
    """Private binding of an adapter to one immutable source document."""

    def __init__(self, adapter: FormatAdapter, source_bytes: bytes) -> None:
        self._adapter = adapter
        self._source_bytes = source_bytes

    def _require_unchanged(self, path: Path) -> None:
        try:
            unchanged = path.read_bytes() == self._source_bytes
        except OSError as exc:
            raise ProjectionError(
                f"{path.name!r}: custom adapter source became unreadable: {exc}"
            ) from exc
        if not unchanged:
            raise ProjectionError(
                f"{path.name!r}: source changed during correction; the custom "
                "path-based adapter cannot render the captured source bytes"
            )

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
        # Exact types matter: a subclass may override rewrite_file. Bypassing
        # that override would silently remove the caller's adapter behavior.
        if type(self._adapter) in (AltoFormatAdapter, PageFormatAdapter):
            rewrite = (
                rewrite_alto_file
                if type(self._adapter) is AltoFormatAdapter
                else rewrite_page_file
            )
            result = rewrite(
                xml_path,
                pages,
                provider,
                model,
                lib_version=lib_version,
                config_fingerprint=config_fingerprint,
                _source_bytes=self._source_bytes,
            )
        else:
            self._require_unchanged(xml_path)
            result = self._adapter.rewrite_file(
                xml_path,
                pages,
                provider,
                model,
                lib_version=lib_version,
                config_fingerprint=config_fingerprint,
            )
            self._require_unchanged(xml_path)
        self._verify_serialized(xml_path, pages, result)
        return result

    def _verify_serialized(
        self, path: Path, pages: list[PageManifest], result: RewriteResult
    ) -> None:
        source = read_source_tree_classified(
            path, source_bytes=self._source_bytes
        ).getroot()
        try:
            output = etree.fromstring(result.xml_bytes, make_safe_parser())
        except (etree.XMLSyntaxError, ValueError) as exc:
            raise ProjectionError(
                f"{path.name!r}: malformed output XML: {exc}"
            ) from exc
        if output.tag != source.tag:
            raise ProjectionError(f"{path.name!r}: output changed the document format")
        root_name = etree.QName(source).localname
        if root_name not in {"alto", "PcGts"}:
            # The format seam also serves host-defined formats. Their text
            # extraction belongs to the injected adapter, never to PAGE.
            return
        require_no_new_dangling_references(output, reference_baseline(source))
        ns = detect_namespace(source)
        id_attr = "ID" if root_name == "alto" else "id"
        source_lines = Counter(
            line.get(id_attr) for line in source.iter(tag("TextLine", ns))
        )
        output_lines = Counter(
            line.get(id_attr) for line in output.iter(tag("TextLine", ns))
        )
        if source_lines != output_lines:
            raise ProjectionError(
                f"{path.name!r}: output changed the TextLine inventory; "
                f"missing: {list((source_lines - output_lines).elements())}; "
                f"added: {list((output_lines - source_lines).elements())}"
            )
        line_ids = {line.line_id for page in pages for line in page.lines}
        extract = alto_texts if root_name == "alto" else page_texts
        try:
            actual = extract(output, ns, line_ids)
            verbatim = extract(output, ns, line_ids, verbatim=True)
        except ParseError as exc:
            raise ProjectionError(
                f"{path.name!r}: invalid output line identities: {exc}"
            ) from exc
        if actual != result.texts or (
            result.texts_verbatim and verbatim != result.texts_verbatim
        ):
            raise ProjectionError(
                f"{path.name!r}: serialized XML disagrees with the adapter's line texts; "
                f"missing: {sorted(set(actual) ^ set(result.texts))}; "
                f"differing: {sorted(lid for lid in actual if actual[lid] != result.texts.get(lid))}"
            )
        if ns not in SCHEMA_BY_NAMESPACE:
            return
        # Existing dialect violations are tolerated, but their multiplicity
        # must not grow. Line numbers change on serialization; XSD messages
        # do not. A valid input consequently requires a valid output.
        try:
            baseline = Counter(
                message.split(": ", 1)[1]
                for message in validate_bytes(etree.tostring(source))
            )
            emitted = Counter(
                message.split(": ", 1)[1]
                for message in validate_bytes(result.xml_bytes)
            )
        except ParseError as exc:
            raise ProjectionError(
                f"{path.name!r}: output validation failed: {exc}"
            ) from exc
        introduced = emitted - baseline
        if introduced:
            raise ProjectionError(
                f"{path.name!r}: output introduces XSD violations: "
                + "; ".join(
                    f"{message} (x{count})" for message, count in introduced.items()
                )
            )
