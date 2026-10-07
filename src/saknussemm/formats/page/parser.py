"""PAGE XML parser — builds the same ``DocumentManifest`` as ALTO (6.3).

Walks ``PcGts → Page → TextRegion → TextLine → Word`` and produces the
format-neutral manifests the pure core consumes. Geometry is read from
``Coords@points`` polygons: the polygon is kept verbatim on
``Coords.polygon`` and the enclosing bbox drives the planner (P1). Line
text follows P2/P3 (see ``_text``). Hyphenation is heuristic-only (P5):
``hyphen_source_explicit`` is always ``False`` and no ``SUBS_CONTENT`` is
invented; the shared ``core.pairing`` linker does the second pass exactly
as it does for ALTO.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from saknussemm.core._parse import parse_int_tolerant
from saknussemm.core.identity import (
    ensure_element_ids_present,
    ensure_unique_element_ids,
    ensure_unique_identities,
)
from saknussemm.core.provenance import source_digest
from saknussemm.core.pairing import (
    HYPHEN_CHARS,
    disambiguate_page_ids,
    link_cross_page_hyphens,
    link_hyphen_pairs,
    trailing_hyphen_char,
)
from saknussemm.core.schemas import (
    DEFAULT_PAIRING_POLICY,
    BlockManifest,
    Coords,
    DocumentManifest,
    HyphenRole,
    LineManifest,
    PageManifest,
    PairingPolicy,
)
from saknussemm.errors import ParseError
from saknussemm.formats._xml import (
    classified_parse_errors,
    mislabelled_utf8,
    sniff_format,
)
from saknussemm.formats.page._ns import (
    _detect_namespace,
    _tag,
    read_source_tree,
    polygon_to_bbox,
)
from saknussemm.formats.page._text import canonical_line_text, word_text


def _coords_of(el: etree._Element, ns: str) -> Coords:
    """Build a Coords (bbox + verbatim polygon) from an element's Coords child."""
    coords_el = el.find(_tag("Coords", ns))
    points = coords_el.get("points", "") if coords_el is not None else ""
    hpos, vpos, width, height = polygon_to_bbox(points)
    return Coords(
        hpos=hpos,
        vpos=vpos,
        width=width,
        height=height,
        polygon=points or None,
    )


def _assign_hyphen_roles(lines: list[LineManifest]) -> None:
    """First-pass heuristic hyphenation for PAGE (P5).

    A line ending in a word-break hyphen is PART1; if the line *before* it
    also ends in one, it is the middle of a chain → BOTH. Everything is
    heuristic: ``hyphen_source_explicit`` / ``hyphen_forward_explicit`` stay
    ``False`` and no SUBS content is invented. The PART2 side is assigned
    later by the shared linker when it consumes a PART1/BOTH line.
    """
    trailing = [trailing_hyphen_char(lm.ocr_text, HYPHEN_CHARS) for lm in lines]
    for i, lm in enumerate(lines):
        if trailing[i] is None:
            continue
        prev_hyphenated = i > 0 and trailing[i - 1] is not None
        if prev_hyphenated:
            lm.hyphen_role = HyphenRole.BOTH
        else:
            lm.hyphen_role = HyphenRole.PART1
        # Heuristic mode throughout — no explicit flags, no subs content.


def _reading_order_refs(page_el: etree._Element, ns: str) -> list[str]:
    """Region ids in the page's declared ``ReadingOrder``, flattened.

    ``OrderedGroup`` children are visited by ascending ``@index``
    (document order breaks ties / missing indexes), ``UnorderedGroup``
    children in document order; groups nest arbitrarily. Returns ``[]``
    when the page declares no reading order. Unknown children are skipped.
    """
    ro = page_el.find(_tag("ReadingOrder", ns))
    if ro is None:
        return []

    _BIG = 10**9

    def group_refs(group: etree._Element) -> list[str]:
        entries: list[tuple[int, int, list[str]]] = []
        for seq, child in enumerate(c for c in group if isinstance(c.tag, str)):
            local = etree.QName(child.tag).localname
            if local in ("RegionRefIndexed", "RegionRef"):
                ref = child.get("regionRef")
                refs = [ref] if ref else []
            elif local in (
                "OrderedGroup",
                "OrderedGroupIndexed",
                "UnorderedGroup",
                "UnorderedGroupIndexed",
            ):
                refs = group_refs(child)
            else:
                continue
            raw_index = child.get("index")
            key = parse_int_tolerant(raw_index, _BIG) if raw_index is not None else _BIG
            entries.append((key, seq, refs))
        entries.sort(key=lambda t: (t[0], t[1]))
        return [r for _, _, refs in entries for r in refs]

    return group_refs(ro)


def _regions_in_reading_order(page_el: etree._Element, ns: str) -> list[etree._Element]:
    """Every ``TextRegion`` under the page, in reading order.

    Regions may nest inside other regions (PAGE's region hierarchy);
    the whole subtree is collected in document order so none is dropped.
    Each region later contributes only its *direct*
    ``TextLine`` children, so nested regions' lines are attributed to
    their own block, never double-counted.

    When the page declares a ``ReadingOrder`` that covers EVERY region
    carrying an id, regions are reordered to the declared sequence (first
    occurrence of an id wins). A *partial* declaration — common in tools
    that only group some articles/tables — is ignored entirely and
    document order is kept: yanking the referenced regions ahead of every
    unreferenced one would reorder text the declaration said nothing
    about (conservative, mirrors the ALTO IDNEXT fallback rule: never
    guess on an incomplete declaration).
    """
    regions = list(page_el.iter(_tag("TextRegion", ns)))
    refs = _reading_order_refs(page_el, ns)
    if not refs or len(regions) < 2:
        return regions
    pos: dict[str, int] = {}
    for i, rid in enumerate(refs):
        pos.setdefault(rid, i)
    for region in regions:
        region_id = region.get("id")
        if not region_id:
            # An id-less region can't be placed by the declaration; sorting
            # would silently yank it to the end (key == len(refs)),
            # reordering text the declaration said nothing about. Treat it
            # like a partial declaration and keep document order.
            return regions
        if region_id not in pos:
            return regions  # partial/dangling declaration → document order
    return sorted(
        regions,
        key=lambda r: pos[r.get("id") or ""],
    )


def parse_page_file(
    xml_path: Path,
    source_name: str,
    page_index_offset: int = 0,
    global_line_offset: int = 0,
    pairing_policy: PairingPolicy = DEFAULT_PAIRING_POLICY,
) -> tuple[list[PageManifest], etree._Element]:
    """Parse one PAGE XML file → (list_of_PageManifest, root_element).

    §8.4 — raises only classified errors: malformed XML, encoding
    mismatches, unreadable files and non-numeric values all surface as
    :class:`~saknussemm.errors.ParseError` (ADR-008), never as a
    bare lxml/OS/ValueError.
    """
    with classified_parse_errors(source_name):
        return _parse_page_file(
            xml_path, source_name, page_index_offset, global_line_offset, pairing_policy
        )


def _parse_page_file(
    xml_path: Path,
    source_name: str,
    page_index_offset: int,
    global_line_offset: int,
    pairing_policy: PairingPolicy,
    *,
    source_bytes: bytes | None = None,
) -> tuple[list[PageManifest], etree._Element]:
    tree = read_source_tree(xml_path, source_bytes=source_bytes)
    root = tree.getroot()
    ns = _detect_namespace(root)

    pages: list[PageManifest] = []
    global_line_idx = global_line_offset

    for page_idx, page_el in enumerate(root.findall(_tag("Page", ns))):
        # PAGE has no Page@ID; the image filename is the stable identity.
        raw_name = page_el.get("imageFilename")
        page_id = raw_name or f"PAGE_{page_index_offset + page_idx}"
        page_width = _int_or_zero(page_el.get("imageWidth"))
        page_height = _int_or_zero(page_el.get("imageHeight"))

        blocks: list[BlockManifest] = []
        lines: list[LineManifest] = []

        block_order = 0
        for region in _regions_in_reading_order(page_el, ns):
            block_id = region.get("id", f"TR_{page_id}_{block_order}")
            block_coords = _coords_of(region, ns)
            line_ids: list[str] = []
            line_order_in_block = 0

            for tl in region.findall(_tag("TextLine", ns)):
                line_id = tl.get("id", f"TL_{block_id}_{line_order_in_block}")
                coords = _coords_of(tl, ns)
                ocr_text = canonical_line_text(tl, ns)
                # Strict checks actual Words, which may disagree with TextEquiv.
                source_words = [word_text(w, ns) for w in tl.findall(_tag("Word", ns))]

                # preserve the source engine's
                # line confidence (first line-level TextEquiv/@conf).
                ocr_confidence = None
                first_equiv = tl.find(_tag("TextEquiv", ns))
                if first_equiv is not None and (raw := first_equiv.get("conf")):
                    try:
                        conf = float(raw)
                    except ValueError:
                        conf = None
                    if conf is not None and 0.0 <= conf <= 1.0:
                        ocr_confidence = conf

                lm = LineManifest(
                    line_id=line_id,
                    page_id=page_id,
                    block_id=block_id,
                    line_order_global=global_line_idx,
                    line_order_in_block=line_order_in_block,
                    coords=coords,
                    ocr_text=ocr_text,
                    word_count=len(source_words) if source_words else None,
                    ocr_confidence=ocr_confidence,
                )
                lm._source_word_texts = source_words or None
                lines.append(lm)
                line_ids.append(line_id)
                line_order_in_block += 1
                global_line_idx += 1

            blocks.append(
                BlockManifest(
                    block_id=block_id,
                    page_id=page_id,
                    block_order=block_order,
                    coords=block_coords,
                    line_ids=line_ids,
                )
            )
            block_order += 1

        # Link prev/next in reading order.
        for i, lm in enumerate(lines):
            if i > 0:
                lm.prev_line_id = lines[i - 1].line_id
            if i < len(lines) - 1:
                lm.next_line_id = lines[i + 1].line_id

        # First-pass heuristic roles, then the shared second-pass linker.
        _assign_hyphen_roles(lines)
        link_hyphen_pairs(lines, pairing_policy)

        pages.append(
            PageManifest(
                page_id=page_id,
                source_file=source_name,
                page_index=page_index_offset + page_idx,
                page_width=page_width,
                page_height=page_height,
                blocks=blocks,
                lines=lines,
            )
        )

    # ADR-007 — duplicate IDs within one file make every downstream
    # correction-to-line association ambiguous. Refuse explicitly.
    ensure_unique_identities(pages, source_name)
    # The rewriter matches TextLine ids over the WHOLE
    # document tree; the parse-time gate must scan the same scope so a
    # duplicate never surfaces only at rewrite time (after the full
    # producer spend).
    ensure_unique_element_ids(
        (tl.get("id") for tl in root.iter(_tag("TextLine", ns))),
        source_name,
        kind="TextLine id(s)",
    )
    # An id-less TextLine gets a fabricated manifest id the rewriter can
    # never match (it keys off the real ``id`` attribute), so its
    # correction would be silently dropped — refuse it instead.
    ensure_element_ids_present(
        (tl.get("id") for tl in root.iter(_tag("TextLine", ns))),
        source_name,
        kind="TextLine element(s)",
    )

    return pages, root


def _int_or_zero(raw: str | None) -> int:
    """PAGE dimensions: blank/float/garbage → 0 (shared tolerant policy)."""
    return parse_int_tolerant(raw, 0)


def build_document_manifest(
    files: list[tuple[Path, str]],
    pairing_policy: PairingPolicy = DEFAULT_PAIRING_POLICY,
) -> DocumentManifest:
    """Build a DocumentManifest from PAGE files (mirrors the ALTO builder)."""
    source_files: list[str] = []
    source_digests: dict[str, str] = {}
    source_encodings: dict[str, str] = {}
    page_offset = 0
    line_offset = 0
    parsed: list[tuple[str, list[PageManifest]]] = []

    for xml_path, source_name in files:
        source_files.append(source_name)
        with classified_parse_errors(source_name):
            raw = xml_path.read_bytes()
            if sniff_format(xml_path, source_bytes=raw) != "page":
                raise ParseError(f"{source_name!r}: expected PAGE source bytes")
            pages, _ = _parse_page_file(
                xml_path,
                source_name,
                page_offset,
                line_offset,
                pairing_policy,
                source_bytes=raw,
            )
        source_digests[source_name] = source_digest(raw)
        if declared_encoding := mislabelled_utf8(raw):
            source_encodings[source_name] = declared_encoding
        parsed.append((source_name, pages))
        page_offset += len(pages)
        for p in pages:
            line_offset += len(p.lines)

    disambiguate_page_ids(parsed)

    all_pages: list[PageManifest] = [p for _, pages in parsed for p in pages]
    link_cross_page_hyphens(all_pages, pairing_policy)

    return DocumentManifest(
        source_files=source_files,
        source_digests=source_digests,
        source_encodings=source_encodings,
        pages=all_pages,
        source_format="page",
    )


__all__ = [
    "parse_page_file",
    "build_document_manifest",
]
