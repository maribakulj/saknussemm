from __future__ import annotations

from pathlib import Path

from lxml import etree

from saknussemm.errors import ParseError
from saknussemm.formats._xml import (
    classified_parse_errors,
    mislabelled_utf8,
    sniff_format,
)
from saknussemm.formats.alto._ns import (
    _detect_namespace,
    _int_attr,
    _tag,
    read_source_tree,
)
from saknussemm.formats.alto._text import reconstruct_textline
from saknussemm.core.identity import (
    ensure_element_ids_present,
    ensure_unique_element_ids,
    ensure_unique_identities,
)
from saknussemm.core.provenance import source_digest
from saknussemm.core.pairing import (
    HYPHEN_CHARS,
    disambiguate_page_ids as _disambiguate_page_ids,
    link_cross_page_hyphens as _link_cross_page_hyphens,
    link_hyphen_pairs as _link_hyphen_pairs,
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

# ---------------------------------------------------------------------------
# ocr_text reconstruction
# ---------------------------------------------------------------------------


def _build_ocr_text(textline: etree._Element, ns: str) -> str:
    """Build the parser's logical line text: NFC + carriage-return strip + strip."""
    return reconstruct_textline(textline, ns).replace("\r", "").strip()


# ---------------------------------------------------------------------------
# Hyphenation detection (mutates lines in-place)
# ---------------------------------------------------------------------------


def _parse_textline_hyphen_info(
    textline: etree._Element,
    ns: str,
    line: LineManifest,
) -> None:
    """
    First-pass hyphenation scan for a single TextLine.
    Fills hyphen_role / hyphen_source_explicit / hyphen_subs_content
    directly on the LineManifest.

    A line can be both PART2 (first String has SUBS_TYPE="HypPart2") AND
    PART1 (trailing HYP element or last String has SUBS_TYPE="HypPart1").
    In that case, role is set to BOTH with forward fields for the PART1 side.
    """
    # Comments and processing instructions carry a callable
    # ``tag`` (``etree.Comment`` / ``etree.PI``), not a ``str``. A trailing
    # comment inside a TextLine made ``etree.QName(last_child.tag)`` below
    # raise and abort the whole file. Filter them out up front so every
    # downstream child access sees only real elements.
    children = [c for c in textline if isinstance(c.tag, str)]
    if not children:
        return

    string_tag = _tag("String", ns)

    # --- Detect PART2: first String has SUBS_TYPE="HypPart2" ---
    is_part2 = False
    backward_subs: str | None = None

    first_string = next((c for c in children if c.tag == string_tag), None)
    if first_string is not None:
        subs_type = first_string.get("SUBS_TYPE", "")
        if subs_type == "HypPart2":
            is_part2 = True
            backward_subs = first_string.get("SUBS_CONTENT")

    # --- Detect PART1: trailing HYP, or last String SUBS_TYPE="HypPart1",
    #     or heuristic trailing dash ---
    is_part1 = False
    forward_subs: str | None = None
    forward_explicit = False

    last_child = children[-1]
    if etree.QName(last_child.tag).localname == "HYP":
        is_part1 = True
        forward_explicit = True
        prev_strings = [c for c in children if c.tag == string_tag]
        if prev_strings:
            sc = prev_strings[-1].get("SUBS_CONTENT")
            if sc:
                forward_subs = sc
    else:
        last_string = next((c for c in reversed(children) if c.tag == string_tag), None)
        if last_string is not None:
            if last_string.get("SUBS_TYPE", "") == "HypPart1":
                is_part1 = True
                forward_explicit = True
                sc = last_string.get("SUBS_CONTENT")
                if sc:
                    forward_subs = sc

    # Heuristic: a genuine word-break hyphen is the last non-space token
    # ending in a HYPHEN_CHARS member with an ALPHABETIC character
    # immediately before it. That alpha rule — not the repertoire — is what
    # rejects pure-numeric forms ("1789-", "n°5-") and dialogue em-dashes
    # that would otherwise mark a phantom PART1 and make the rewriter emit
    # a spurious HYP on output.
    #
    # ALTO used to pass only ``("-",)`` while the PAGE parser passed the
    # full repertoire. The asymmetry silently disabled hyphen handling on
    # Fraktur: a line ending in ``⸗`` got role NONE, and no role means no
    # pair, which means neither the Stage-A integrity check nor the
    # Stage-B drift guards ever run — the line reaches the model with
    # nothing watching its boundary. Measured on corpus/37-GT-BNL (19th-c.
    # Luxembourg press, no SUBS_TYPE anywhere): 24 of 94 break lines,
    # 25.5%, every one of them ``⸗``.
    #
    # The rewriter's own _drop_structural_break_hyphen already accepted the
    # whole repertoire, so this also removes a parser/rewriter asymmetry.
    if not is_part1:
        if trailing_hyphen_char(line.ocr_text, HYPHEN_CHARS) is not None:
            is_part1 = True
            forward_explicit = False

    # --- Set role based on detection ---
    if is_part2 and is_part1:
        line.hyphen_role = HyphenRole.BOTH
        # Backward (PART2 side) in existing fields
        line.hyphen_source_explicit = True  # PART2 from SUBS_TYPE is always explicit
        if backward_subs:
            line.hyphen_subs_content = backward_subs
        # Forward (PART1 side) in new fields
        line.hyphen_forward_explicit = forward_explicit
        if forward_subs:
            line.hyphen_forward_subs_content = forward_subs
    elif is_part2:
        line.hyphen_role = HyphenRole.PART2
        line.hyphen_source_explicit = True
        if backward_subs:
            line.hyphen_subs_content = backward_subs
    elif is_part1:
        line.hyphen_role = HyphenRole.PART1
        line.hyphen_source_explicit = forward_explicit
        if forward_subs:
            line.hyphen_subs_content = forward_subs


# ---------------------------------------------------------------------------
# Block discovery + reading order
# ---------------------------------------------------------------------------


_MARGIN_LOCALNAMES = ("TopMargin", "BottomMargin", "LeftMargin", "RightMargin")


def _collect_blocks_skipping_margins(
    container: etree._Element, ns: str
) -> list[etree._Element]:
    """Every ``TextBlock`` under ``container`` in document order, never
    descending into the four margin containers.

    When a page has no ``PrintSpace`` the container is the ``Page``
    itself; a naive ``iter`` would sweep margin-nested blocks (running
    headers, page numbers) into correction scope. An explicit walk keeps
    the margin rule true in both container shapes. Descent stops at a
    ``TextBlock`` (ALTO forbids nested TextBlocks).
    """
    margin_tags = {_tag(t, ns) for t in _MARGIN_LOCALNAMES}
    tb_tag = _tag("TextBlock", ns)
    out: list[etree._Element] = []

    def walk(el: etree._Element) -> None:
        for child in el:
            if not isinstance(child.tag, str) or child.tag in margin_tags:
                continue
            if child.tag == tb_tag:
                out.append(child)
                continue
            walk(child)

    walk(container)
    return out


def _blocks_in_reading_order(
    container: etree._Element, ns: str
) -> list[etree._Element]:
    """Every ``TextBlock`` under ``container``, in reading order.

    TextBlocks may nest inside ``ComposedBlock`` groups (articles,
    figures-with-caption, …); the whole subtree is walked in document
    order so none is dropped (ALTO does not allow a TextBlock inside a
    TextBlock, so no double-visit).

    When blocks carry the optional ``IDNEXT`` attribute (ALTO's explicit
    next-block-in-reading-sequence chain), the chains override document
    order: heads are visited in document order and each chain is followed
    to its end. The reorder is strictly validated — a self-reference, two
    blocks naming the same successor, or a cycle falls back to plain
    document order (never guess on inconsistent declarations). An IDNEXT
    pointing OUTSIDE this container (a cross-page article continuation —
    a legitimate, common METS/ALTO pattern — or a margin block) is
    treated as end-of-chain for this page, NOT as an inconsistency: only
    that link is ignored, the rest of the declared order is kept.

    Container rule: ``PrintSpace`` when present, else the whole ``Page``
    minus the four margin containers — margins stay out of correction
    scope in both shapes (the historical direct-children lookup excluded
    margin-nested blocks implicitly; the recursive walk must exclude
    them explicitly).
    """
    blocks = _collect_blocks_skipping_margins(container, ns)
    if len(blocks) < 2:
        return blocks

    # Blocks lacking a usable ID never participate in IDNEXT chains —
    # they keep their document-order slot (an empty-string ID used to
    # slip past the `is None` checks below and KeyError the chain walk).
    def _bid(b: etree._Element) -> str | None:
        raw = b.get("ID")
        return raw if raw else None

    by_id: dict[str, etree._Element] = {}
    for b in blocks:
        bid = _bid(b)
        if bid is not None:
            if bid in by_id:
                # Duplicate block IDs — the manifest-level uniqueness gate
                # (ADR-007) will refuse the file; no reordering here.
                return blocks
            by_id[bid] = b

    succ: dict[str, str] = {}
    referenced: set[str] = set()
    for b in blocks:
        nxt = b.get("IDNEXT")
        if nxt is None or not nxt.strip():
            continue
        nxt = nxt.strip()
        bid = _bid(b)
        if bid is None or nxt not in by_id:
            # Unusable head, or a target outside this container (next
            # page / margin): end of chain here — skip just this link.
            continue
        if nxt == bid or nxt in referenced:
            # Self-reference / converging chains → inconsistent.
            return blocks
        succ[bid] = nxt
        referenced.add(nxt)

    if not succ:
        return blocks

    ordered: list[etree._Element] = []
    visited: set[str] = set()
    for b in blocks:
        bid = _bid(b)
        if bid is None:
            ordered.append(b)
            continue
        if bid in visited or bid in referenced:
            continue  # emitted (or will be) as part of a chain
        cur: str | None = bid
        while cur is not None and cur not in visited:
            visited.add(cur)
            ordered.append(by_id[cur])
            cur = succ.get(cur)

    if len(ordered) != len(blocks):
        # Unreached blocks = every remaining chain is a cycle → fall back.
        return blocks
    return ordered


# ---------------------------------------------------------------------------
# Core parsing
# ---------------------------------------------------------------------------


def parse_alto_file(
    xml_path: Path,
    source_name: str,
    page_index_offset: int = 0,
    global_line_offset: int = 0,
    pairing_policy: PairingPolicy = DEFAULT_PAIRING_POLICY,
) -> tuple[list[PageManifest], etree._Element]:
    """
    Parse one ALTO XML file and return (list_of_PageManifest, root_element).

    ``pairing_policy`` is forwarded to the hyphen-pair linker; the
    default vets heuristic pairs geometrically; pass
    ``PairingPolicy(geometric_checks=False)`` for the historical
    purely-sequential pairing.

    §8.4 — raises only classified errors: malformed XML, encoding
    mismatches, unreadable files and non-numeric coordinates all surface
    as :class:`~saknussemm.errors.ParseError` (ADR-008), never as a
    bare lxml/OS/ValueError.
    """
    with classified_parse_errors(source_name):
        return _parse_alto_file(
            xml_path, source_name, page_index_offset, global_line_offset, pairing_policy
        )


def _parse_alto_file(
    xml_path: Path,
    source_name: str,
    page_index_offset: int,
    global_line_offset: int,
    pairing_policy: PairingPolicy,
    *,
    source_bytes: bytes | None = None,
) -> tuple[list[PageManifest], etree._Element]:
    # Hardened parser shared with rewriting and output text extraction.
    tree = read_source_tree(xml_path, source_bytes=source_bytes)
    root = tree.getroot()
    ns = _detect_namespace(root)
    pages: list[PageManifest] = []
    global_line_idx = global_line_offset

    layout = root.find(_tag("Layout", ns))
    if layout is None:
        return pages, root

    for page_idx, page_el in enumerate(layout.findall(_tag("Page", ns))):
        page_id = page_el.get("ID", f"PAGE_{page_index_offset + page_idx}")
        page_width = _int_attr(page_el, "WIDTH")
        page_height = _int_attr(page_el, "HEIGHT")

        blocks: list[BlockManifest] = []
        lines: list[LineManifest] = []

        printspace = page_el.find(_tag("PrintSpace", ns))
        container = printspace if printspace is not None else page_el

        block_order = 0
        for tb in _blocks_in_reading_order(container, ns):
            block_id = tb.get("ID", f"TB_{page_id}_{block_order}")
            block_coords = Coords(
                hpos=_int_attr(tb, "HPOS"),
                vpos=_int_attr(tb, "VPOS"),
                width=_int_attr(tb, "WIDTH"),
                height=_int_attr(tb, "HEIGHT"),
            )
            line_ids: list[str] = []
            line_order_in_block = 0

            for tl in tb.findall(_tag("TextLine", ns)):
                line_id = tl.get("ID", f"TL_{block_id}_{line_order_in_block}")
                coords = Coords(
                    hpos=_int_attr(tl, "HPOS"),
                    vpos=_int_attr(tl, "VPOS"),
                    width=_int_attr(tl, "WIDTH"),
                    height=_int_attr(tl, "HEIGHT"),
                )
                ocr_text = _build_ocr_text(tl, ns)

                # preserve the OCR engine's own
                # confidence at line level (mean of String/@WC): the
                # per-word attributes are invalidated by any correction,
                # but the audit trail keeps the source signal.
                wc_values = []
                for s in tl.findall(_tag("String", ns)):
                    raw_wc = s.get("WC")
                    if raw_wc is None:
                        continue
                    try:
                        wc = float(raw_wc)
                    except ValueError:
                        continue
                    if 0.0 <= wc <= 1.0:
                        wc_values.append(wc)

                lm = LineManifest(
                    line_id=line_id,
                    page_id=page_id,
                    block_id=block_id,
                    line_order_global=global_line_idx,
                    line_order_in_block=line_order_in_block,
                    coords=coords,
                    ocr_text=ocr_text,
                    ocr_confidence=(
                        sum(wc_values) / len(wc_values) if wc_values else None
                    ),
                )

                # First-pass hyphenation scan
                _parse_textline_hyphen_info(tl, ns, lm)

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

        # Link prev/next
        for i, lm in enumerate(lines):
            if i > 0:
                lm.prev_line_id = lines[i - 1].line_id
            if i < len(lines) - 1:
                lm.next_line_id = lines[i + 1].line_id

        # Second-pass: link hyphen pairs
        _link_hyphen_pairs(lines, pairing_policy)

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
    # The rewriter matches TextLine IDs over the WHOLE
    # document tree (margins included), so the parse-time gate must scan
    # the same scope: a margin line reusing a body line's ID would
    # otherwise pass here and only explode at rewrite time, after the
    # full LLM spend.
    ensure_unique_element_ids(
        (tl.get("ID") for tl in root.iter(_tag("TextLine", ns))),
        source_name,
        kind="TextLine ID(s)",
    )
    # An ID-less TextLine gets a fabricated manifest id the rewriter can
    # never match (it keys off the real ``ID`` attribute), so its
    # correction would be silently dropped — refuse it instead.
    ensure_element_ids_present(
        (tl.get("ID") for tl in root.iter(_tag("TextLine", ns))),
        source_name,
        kind="TextLine element(s)",
    )

    return pages, root


def build_document_manifest(
    files: list[tuple[Path, str]],
    pairing_policy: PairingPolicy = DEFAULT_PAIRING_POLICY,
) -> DocumentManifest:
    """
    Build a DocumentManifest from a list of (xml_path, source_name) tuples.
    Files are processed in order; page/line indices are continuous.

    ``pairing_policy`` is applied to both intra-page and cross-page
    hyphen linking; the default vets heuristic pairs geometrically.

    A file that is not ALTO is REFUSED, not read as an empty document.
    This parser used to find no ALTO pages in a valid PAGE file and return
    a manifest of zero pages and zero lines — the silent mis-read
    ``formats/loader.py`` warns about in its module docstring, and which
    cost more than the warning suggested: 63 test modules import this
    function directly, so any property anyone tried to assert on a PAGE
    document held over nothing and reported success. Refusing here fixes
    every one of those call sites at once, without editing them.

    Hosts should still come through ``formats/loader.py``, which dispatches
    on the document instead of being told. This is the guard for when they
    do not.
    """
    source_files: list[str] = []
    source_digests: dict[str, str] = {}
    source_encodings: dict[str, str] = {}
    page_offset = 0
    line_offset = 0
    parsed: list[tuple[str, list[PageManifest]]] = []

    for xml_path, source_name in files:
        # Detection, text and provenance all describe this one snapshot,
        # even if the file is replaced or removed while parsing it.
        with classified_parse_errors(source_name):
            raw = xml_path.read_bytes()
            detected = sniff_format(xml_path, source_bytes=raw)
            if detected != "alto":
                raise ParseError(
                    f"{source_name!r} is {detected.upper()}, not ALTO. Reading "
                    "it here would find no ALTO pages and yield an EMPTY "
                    "manifest — a run over nothing that reports success. Use "
                    "saknussemm.formats.loader.build_document_manifest, which "
                    "picks the parser from the document."
                )
            pages, _ = _parse_alto_file(
                xml_path,
                source_name,
                page_offset,
                line_offset,
                pairing_policy,
                source_bytes=raw,
            )
        source_files.append(source_name)
        source_digests[source_name] = source_digest(raw)
        if (declared := mislabelled_utf8(raw)) is not None:
            source_encodings[source_name] = declared
        parsed.append((source_name, pages))
        page_offset += len(pages)
        for p in pages:
            line_offset += len(p.lines)

    # Resolve cross-file Page ID collisions BEFORE cross-page hyphen linking
    # so the resulting hyphen_pair_page_id refs already use qualified ids.
    _disambiguate_page_ids(parsed)

    all_pages: list[PageManifest] = [p for _, pages in parsed for p in pages]

    # Cross-page hyphen linking (shared core.pairing helper): a PART1/BOTH
    # line at the bottom of page N that was NOT linked intra-page is paired
    # with the first line of page N+1.
    _link_cross_page_hyphens(all_pages, pairing_policy)

    return DocumentManifest(
        source_files=source_files,
        source_digests=source_digests,
        source_encodings=source_encodings,
        pages=all_pages,
        source_format="alto",
    )


# --- public surface ---
__all__ = [
    "parse_alto_file",
    "build_document_manifest",
]
