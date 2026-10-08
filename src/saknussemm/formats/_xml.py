"""Format-agnostic XML helpers shared by every transcription format.

lxml lives here — so this module is NOT part of the pure ``core`` (the
import-contract test allows ``formats`` to import lxml) — but it is NOT a
format either: namespace detection, tag qualification, and the hardened
parser are identical for ALTO, PAGE, and any future format.

Homing them here keeps the format packages *siblings* — ``alto → _xml ←
page`` — instead of making one an accidental base that the other reaches
sideways into (the former ``page → alto`` edge, which meant deleting or
refactoring ALTO would break PAGE). Each format's ``_ns`` re-exports these
three under its existing private names, so call sites are unchanged.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path

from lxml import etree

from saknussemm.errors import SaknussemmError, ParseError


def detect_namespace(root: object) -> str:
    """Return the namespace URI from a root element's tag, or '' if none.

    Defensive against a tag that opens with ``{`` but has no closing brace,
    and against a non-element ``root`` (``getattr`` fallback) — works for
    both the ALTO and PAGE parse/rewrite entry points.
    """
    tag = getattr(root, "tag", "")
    if isinstance(tag, str) and tag.startswith("{") and "}" in tag:
        return tag[1 : tag.index("}")]
    return ""


def local_name(element: object) -> str:
    """Return an element's tag without its namespace, or '' if it has none.

    The inverse of :func:`detect_namespace`: that one keeps the URI and
    drops the name, this one keeps the name and drops the URI. Used where
    a document must be recognised by its *schema shape* rather than by
    whose namespace URI it was published under.
    """
    tag_value = getattr(element, "tag", "")
    if not isinstance(tag_value, str):
        return ""
    if tag_value.startswith("{") and "}" in tag_value:
        return tag_value[tag_value.index("}") + 1 :]
    return tag_value


def tag(local: str, ns: str) -> str:
    """Qualify a local tag name with a namespace (Clark notation)."""
    return f"{{{ns}}}{local}" if ns else local


#: Declarations we are willing to second-guess. Deliberately one-sided: a
#: file that declares UTF-8 is taken at its word. Latin-family labels are
#: the ones a UTF-8 file gets mislabelled AS — the reverse (real latin-1
#: wearing a UTF-8 label) is not silently repairable, because those bytes
#: do not decode as UTF-8 and the parser refuses them loudly already.
_OVERRIDABLE_DECLARATIONS = (
    "iso-8859",
    "iso8859",
    "windows-125",
    "latin-1",
    "latin1",
    "cp125",
)

#: The XML declaration lives in the first line; 200 bytes is generous.
_DECLARATION_HEAD = 200
_DECLARED_ENCODING = re.compile(rb"""encoding\s*=\s*["']([^"']+)["']""")


def mislabelled_utf8(raw: bytes) -> str | None:
    """Return the declared encoding when a file's declaration lies, else None.

    Gallica serves ALTO that declares ``ISO-8859-1`` and contains UTF-8.
    Read as declared, ``cléricales`` arrives as ``clÃ©ricales`` — and a
    post-OCR corrector handed that will dutifully *repair* it, delivering a
    text change that the report cannot distinguish from a correction. That
    is precisely the class of undeclared alteration this library exists to
    refuse, so the mismatch has to be caught at the door.

    Three conditions, all necessary:

    1. the declaration names a latin-family encoding;
    2. the WHOLE byte stream decodes as strict UTF-8;
    3. it contains at least one non-ASCII character — otherwise both
       readings are identical and there is nothing to decide.

    Condition 2 is close to a proof rather than a heuristic. In latin-1
    French, ``é`` is ``0xE9`` and the byte after it is a letter
    (``0x61``-``0x7A``); UTF-8 requires the byte following a lead byte to be
    ``0x80``-``0xBF``, which a letter never is. A genuine latin-1 document
    fails at its first accent. Measured on ten French words: ten failures.

    What would still fool it: a real latin-1 file in which *every* accented
    byte happens to be followed by a continuation byte. No such document is
    in hand, and condition 3 already excludes the trivial case of a file
    with no accents at all.

    Cost, measured on a 646 KB page: 0.115 ms for the decode attempt
    against 16.5 ms to parse the file. On the common path — a file that
    declares UTF-8 — it stops at the declaration.
    """
    match = _DECLARED_ENCODING.search(raw[:_DECLARATION_HEAD])
    if match is None:
        return None
    declared = match.group(1).decode("ascii", "replace")
    if not any(f in declared.lower() for f in _OVERRIDABLE_DECLARATIONS):
        return None
    if raw.isascii():
        return None
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return declared


def read_source_header(
    path: Path, mandatory_child: str | None = None, *, source_bytes: bytes | None = None
) -> tuple[str, str, bool]:
    """Read a document's opening elements: namespace, root name, child present.

    Recognising a format needs the root element and, for a producer that
    publishes under its own namespace, the presence of the child its schema
    makes mandatory. None of that needs the body.

    :func:`sniff_format` used to get them from a full parse and throw the
    tree away, while the real parser parsed the same bytes again. Measured
    on a 646 KB newspaper page: 6.28 ms of the 16.53 ms it took to build a
    manifest — 38 % of loading, spent twice on the same file.

    Streaming stops at the first ``start`` event that answers the question:
    a conforming ALTO reaches its ``Layout`` within a handful of elements.
    A document that never produces the child is read to the end — it is
    also a document about to be refused, so the cost lands where it is
    least owed.

    Hardened like every other reader here: no entity resolution, no
    network, no DTD. ``tests/test_xml_security.py`` keeps lxml's streaming
    entry points inside this module for exactly that reason.
    """
    raw = path.read_bytes() if source_bytes is None else source_bytes
    encoding = "utf-8" if mislabelled_utf8(raw) is not None else None
    stream = etree.iterparse(
        BytesIO(raw),
        events=("start",),
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        encoding=encoding,
    )
    namespace = root_name = ""
    found = False
    for _event, element in stream:
        if not root_name:
            namespace, root_name = detect_namespace(element), local_name(element)
            if mandatory_child is None:
                break
            continue
        if local_name(element) == mandatory_child:
            found = True
            break
    return namespace, root_name, found


def read_source_tree(
    path: Path, *, source_bytes: bytes | None = None
) -> etree._ElementTree:
    """Parse a source document, overriding a declaration that provably lies.

    THE way to read a source file: the parsers and the rewriters both go
    through here, so they cannot disagree about what a document says. The
    guarantee is that one file has one reading — two independent readings
    of the same bytes is how two sides of this library once classified the
    same event differently, each correct on its own and wrong together.

    The source file is never modified — the override is handed to lxml,
    which decodes correctly on its own.
    """
    raw = path.read_bytes() if source_bytes is None else source_bytes
    encoding = "utf-8" if mislabelled_utf8(raw) is not None else None
    return etree.parse(BytesIO(raw), make_safe_parser(encoding=encoding))


def read_source_tree_classified(
    path: Path, *, source_bytes: bytes | None = None
) -> etree._ElementTree:
    """:func:`read_source_tree`, with §8.4 classification around it.

    The rewriters read the source a second time, at render, and theirs were
    **the only two ``read_source_tree`` callers outside**
    :func:`classified_parse_errors` — both parsers are wrapped,
    ``sniff_format`` is wrapped, output validation is wrapped.

    Measured 2026-08-17, perturbing the file between parse and render:

    ========================  ==============================
    what happened             what reached the host
    ========================  ==============================
    file removed              ``FileNotFoundError``
    file truncated            ``lxml.etree.XMLSyntaxError``
    permission removed        ``PermissionError``
    ========================  ==============================

    Each of them travelled through ``asyncio.to_thread`` and out of
    ``run()`` unclassified, while the *same* perturbation at parse time
    gave a proper ``ParseError``. ADR-008 asks for a single error root; the
    render path was the hole.

    A separate function rather than two ``with`` blocks because the
    rewriters' entry points are size-ratcheted (`RM-10`): the explanation
    belongs somewhere it can be written once and read once.
    """
    with classified_parse_errors(str(path)):
        return read_source_tree(path, source_bytes=source_bytes)


def make_safe_parser(encoding: str | None = None) -> etree.XMLParser:
    """Return an lxml parser hardened against XXE / SSRF / entity-amplification.

    The four flags together neutralise the well-known XML attack surface:

      - ``resolve_entities=False`` — do not expand ``&entity;`` references.
        Defeats internal-entity amplification ("billion laughs") and any
        residual external-entity leak across lxml versions.
      - ``no_network=True`` — refuse to fetch external DTDs / entities.
        Defeats SSRF via ``<!DOCTYPE x SYSTEM "http://...">``.
      - ``load_dtd=False`` — do not load any DTD (inline or external).
        Defence in depth on top of ``no_network``.
      - ``dtd_validation=False`` — do not validate against a DTD. Default
        already; pinned here for clarity (a future maintainer flipping
        validation on would silently re-enable DTD loading).

    Returns a FRESH parser instance per call: lxml parsers are not
    documented as thread-safe and the construction cost is microseconds.

    Use this for EVERY ``etree.parse`` / ``etree.fromstring`` call that
    touches user-controlled XML — the grep-based contract test in
    ``packages/saknussemm/tests/test_xml_security.py`` trips on any call
    site under ``formats/`` that doesn't.
    """
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        dtd_validation=False,
        encoding=encoding,
    )


@contextmanager
def classified_parse_errors(source_name: str) -> Iterator[None]:
    """§8.4 — a parser may only raise classified :class:`SaknussemmError`s.

    Wrap a parser entry point's body in this context manager so hostile
    or malformed input can never escape as an unclassified exception
    (ADR-008; pinned by the fuzz suite):

      - ``etree.XMLSyntaxError`` (malformed XML, encoding mismatches,
        truncated files) → :class:`ParseError`;
      - bare ``ValueError`` (e.g. a genuinely non-numeric coordinate under
        the strict ``parse_int_tolerant`` policy) → :class:`ParseError`;
      - ``OSError`` (unreadable/missing source file) → :class:`ParseError`.

    Existing classified errors — :class:`ParseError` itself,
    :class:`DuplicateIdError`, any :class:`SaknussemmError` — pass through
    untouched. Genuine programming errors (``TypeError``,
    ``AttributeError``, …) are deliberately NOT wrapped: masking a library
    bug as a bad-input error would hide it from every caller.
    """
    try:
        yield
    except SaknussemmError:
        raise
    except (etree.XMLSyntaxError, ValueError) as exc:
        raise ParseError(f"{source_name}: cannot parse document: {exc}") from exc
    except OSError as exc:
        raise ParseError(f"{source_name}: cannot read source file: {exc}") from exc


# ---------------------------------------------------------------------------
# Reniflage de format
# ---------------------------------------------------------------------------
#
# Vit ici plutôt que dans ``formats/loader.py``, où il était, pour une raison
# de dépendances : le loader importe les deux parseurs au niveau module, et
# ``formats/alto/parser.py`` a besoin de ce reniflage pour refuser un fichier
# qui n'est pas de l'ALTO. Il le réimportait donc du loader À L'INTÉRIEUR de
# sa fonction, avec un commentaire disant « local: loader imports us » — un
# cycle réel, contourné par un import différé.
#
# ``formats/_xml.py`` ne dépend d'aucun format et les deux le connaissent
# déjà. Le cycle disparaît sans que personne ait à se rappeler pourquoi un
# import est au mauvais endroit.

_ALTO_MARKER = "loc.gov/standards/alto"
_PAGE_MARKER = "primaresearch.org/PAGE"

#: Root local name -> format, for a producer that publishes one of these two
#: schemas under its OWN namespace URI. This is not hypothetical: Gallica
#: serves a large family of its ALTO under ``bibnum.bnf.fr/ns/alto_prod``,
#: with `TextLine`/`String`/`HYP` and explicit `SUBS_TYPE` hyphenation — the
#: richest input this library accepts — and the standard-namespace check
#: alone refused every one of them at the door.
_ROOT_LOCAL_NAME = {"alto": "alto", "PcGts": "page"}

#: The element each schema makes mandatory under the root. Requiring it is
#: what keeps the fallback a check on the FORMAT and not merely on a name:
#: a document whose root happens to be called `alto` but that carries no
#: `Layout` is still refused, and says so.
_MANDATORY_CHILD = {"alto": "Layout", "page": "Page"}


def sniff_format(path: Path, *, source_bytes: bytes | None = None) -> str:
    """``"alto"`` / ``"page"`` from the file's root element.

    The two standard namespaces answer first and are authoritative. Anything
    else falls through to the root's local name plus the schema's mandatory
    element — because a namespace URI says who *published* a document, not
    what format it is in.

    Nothing downstream ever needed the change: the ALTO and PAGE parsers and
    rewriters read the namespace off the document they were handed
    (``detect_namespace``) and re-emit it unchanged, so a vendor namespace
    survives a full round-trip. This door was the only branded place.
    """
    with classified_parse_errors(path.name):
        ns, root_name, _ = read_source_header(path, source_bytes=source_bytes)
        if _ALTO_MARKER in ns:
            return "alto"
        if _PAGE_MARKER in ns:
            return "page"
        # Only a vendor namespace pays for the second question, and only it
        # needs to: the two standard markers answered above without reading
        # past the root element.
        fmt = _ROOT_LOCAL_NAME.get(root_name)
        if fmt is not None:
            _, _, found = read_source_header(
                path, _MANDATORY_CHILD[fmt], source_bytes=source_bytes
            )
            if found:
                return fmt
    raise ParseError(
        f"{path.name!r}: root {root_name!r} in namespace {ns!r} is "
        "neither ALTO nor PAGE — saknussemm recognises a standard namespace, "
        f"or a root named {sorted(_ROOT_LOCAL_NAME)} carrying its schema's "
        "mandatory element (ALTO: Layout, PAGE: Page). Parse other formats "
        "through their own adapter."
    )


__all__ = [
    "sniff_format",
    "classified_parse_errors",
    "detect_namespace",
    "local_name",
    "make_safe_parser",
    "mislabelled_utf8",
    "read_source_header",
    "read_source_tree",
    "tag",
]
