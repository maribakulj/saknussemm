"""Offline XSD validation for ALTO/PAGE documents.

Role split (§ roadmap): on INPUT the validation is a *diagnostic* — a
slightly non-conformant file can still yield a perfectly good manifest,
so a host surfaces the violations without refusing the document. On
OUTPUT it is a *gate*: everything the rewriters emit must validate
against the official schema of its namespace (pinned by
``tests/test_xsd_validation.py``).

The schemas are bundled verbatim (``xsd/README.md`` records provenance)
and resolved OFFLINE: the ``xs:import`` of xlink that ALTO schemas
reference by absolute URL is remapped to the bundled copy by an lxml
resolver — compilation never touches the network (the schema parser is
``no_network`` like every parser in ``formats/``, so an unmapped remote
import fails loudly instead of fetching).
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from threading import RLock
from typing import Any, cast

from lxml import etree

from saknussemm.errors import ParseError
from saknussemm.formats._xml import (
    classified_parse_errors,
    detect_namespace,
    make_safe_parser,
)

_XSD_DIR = Path(__file__).resolve().parent / "xsd"
_VALIDATION_LOCK = RLock()

#: Root namespace → bundled schema file. This mapping IS the public
#: support matrix for validation (see ``docs/format-support.md``): the
#: parsers accept any namespace matching their format marker, but only
#: these versions can be checked against an official schema.
SCHEMA_BY_NAMESPACE: dict[str, str] = {
    "http://www.loc.gov/standards/alto/ns-v2#": "alto-2-1.xsd",
    "http://www.loc.gov/standards/alto/ns-v3#": "alto-3-1.xsd",
    "http://www.loc.gov/standards/alto/ns-v4#": "alto-4-4.xsd",
    "http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15": (
        "pagecontent_2013-07-15.xsd"
    ),
    "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15": (
        "pagecontent_2019-07-15.xsd"
    ),
    "http://schema.primaresearch.org/PAGE/gts/pagecontent/2024-07-15": (
        "pagecontent_2024-07-15.xsd"
    ),
}


class _BundledImports(etree.Resolver):
    """Remap the xlink ``xs:import`` URL to the bundled ``xlink.xsd``.

    Anything else returns ``None``: combined with the ``no_network``
    schema parser, an unknown import can only fail compilation — never
    trigger a fetch.

    The two targeted ignores paper over lxml-stubs gaps, not real
    issues: the stubs' ``Resolver.resolve`` omits the ``context``
    argument lxml actually passes at runtime, and they omit the
    inherited ``resolve_filename`` helper entirely.
    """

    def resolve(  # type: ignore[override]
        self, system_url: str | None, public_id: str | None, context: Any
    ) -> Any:
        if system_url and system_url.rsplit("/", 1)[-1] == "xlink.xsd":
            return self.resolve_filename(  # type: ignore[attr-defined]
                str(_XSD_DIR / "xlink.xsd"), context
            )
        return None


@lru_cache(maxsize=None)
def _schema_for(namespace: str) -> etree.XMLSchema:
    """Compile (once) the bundled schema for ``namespace``.

    The compiled ``XMLSchema`` is cached and shared; its ``error_log``
    reflects the LAST validation. ``validate_bytes`` serializes validation
    and diagnostic reads under one lock; direct callers must do likewise.
    """
    filename = SCHEMA_BY_NAMESPACE.get(namespace)
    if filename is None:
        supported = ", ".join(sorted(SCHEMA_BY_NAMESPACE))
        raise ParseError(
            f"no bundled XSD for root namespace {namespace!r} — "
            f"validation covers: {supported}"
        )
    parser = make_safe_parser()
    parser.resolvers.add(_BundledImports())
    schema_doc = etree.parse(str(_XSD_DIR / filename), parser)
    return etree.XMLSchema(schema_doc)


def validate_bytes(xml_bytes: bytes, *, source_name: str = "<bytes>") -> list[str]:
    """Validate a serialized ALTO/PAGE document against its namespace's
    bundled XSD.

    Returns the violations as ``source:line: message`` strings — empty
    means valid. Raises :class:`ParseError` for malformed XML (§8.4
    classified) or a root namespace with no bundled schema.
    """
    with classified_parse_errors(source_name):
        root = etree.fromstring(xml_bytes, make_safe_parser())
    # Runs render in worker threads. Keep each validation and its error-log
    # read together: cached XMLSchema objects otherwise expose another run's
    # last diagnostic, which can accept or reject the wrong deliverable.
    with _VALIDATION_LOCK:
        schema = _schema_for(detect_namespace(root))
        if schema.validate(root):
            return []
        # lxml-stubs' _ErrorLog misses __iter__ — the runtime log iterates.
        errors = cast("Iterable[Any]", schema.error_log)
        return [f"{source_name}:{e.line}: {e.message}" for e in errors]


def validate_file(path: Path) -> list[str]:
    """:func:`validate_bytes` over a file's bytes (named after the file)."""
    with classified_parse_errors(path.name):
        data = path.read_bytes()
    return validate_bytes(data, source_name=path.name)


__all__ = ["SCHEMA_BY_NAMESPACE", "validate_bytes", "validate_file"]
