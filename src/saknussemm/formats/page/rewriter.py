"""PAGE XML rewriter — writes corrected text back without touching geometry.

Implements spec 6.2 P1–P5/P7. No existing polygon is ever rewritten (P1);
since 2026-09-30 the slow path may ADD ``Word`` elements whose polygon is
cut out of a polygon of the source (``_words``). A modified line is handled
as:

  - **P3** — update the canonical (minimal ``@index``) line ``TextEquiv``:
    set its ``Unicode`` (and ``PlainText`` if present), drop its stale
    ``@conf``, and delete the alternative line-level ``TextEquiv`` (they
    described the old reading). Create the canonical one if the line only
    carried word-level text.
  - **P4** — word elements. When the corrected word count matches the
    number of ``Word`` children, update each ``Word``'s canonical
    ``TextEquiv`` in place, keep its ``Coords``, drop its ``@conf`` (fast
    path). When the count changed (slow path), the ``Word``s the
    correction left alone are kept as they are, and the run it changed is
    given new ``Word``s cut out of the polygons it consumed — see
    :mod:`saknussemm.formats.page._words`. When nothing can be kept the
    ``Word`` children are removed and the text lives at line level, as
    before. Every source ``Word`` removed is counted (``words_dropped``).
  - **P5** — the original hyphen character is preserved verbatim: a
    producer may not normalise ``¬`` → ``-`` (E5 extended).
  - **P7** — ``make_safe_parser`` throughout; provenance recorded as a
    ``MetadataItem`` on 2019+ schemas, else appended to ``Metadata/Comments``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from saknussemm.core._norm import nfc
from saknussemm.core.identity import ensure_unique_identities
from saknussemm.core.losses import COUNTS_INVALIDATION, INVALIDATION_COUNTER
from saknussemm.core.pairing import (
    HYPHEN_CHARS,
    preserve_break_char,
    trailing_hyphen_char,
)
from saknussemm.errors import DuplicateIdError
from saknussemm.core.protocols import RewriteResult
from saknussemm.core.schemas import LineManifest, PageManifest
from saknussemm.formats.page._custom import strip_offset_groups
from saknussemm.formats.page._ns import (
    _detect_namespace,
    _tag,
    make_safe_parser,
    supports_metadata_item,
)
from saknussemm.formats._xml import read_source_tree_classified
from saknussemm.formats.page._words import PageWidths, new_word, plan_words
from saknussemm.formats.page._text import (
    canonical_line_text,
    canonical_textequiv,
    word_text,
)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


@dataclass
class PageRewriterMetrics:
    """Per-path line counts for the PAGE rewriter.

    ``untouched``/``subs_only``/``fast_path``/``slow_path`` satisfy the core
    ``RewriteMetrics`` port so the pipeline treats PAGE like ALTO;
    ``subs_only`` is always 0 (PAGE has no SUBS markup). The remaining
    counters feed the CorrectionReport's PAGE-specific losses (6.2).
    """

    untouched: int = 0
    subs_only: int = 0  # never used by PAGE; present for RewriteMetrics parity
    fast_path: int = 0
    slow_path: int = 0

    # PAGE-specific provenance of what was dropped / detected.
    words_dropped: int = 0
    #: ``Word`` elements created on the slow path for a run the correction
    #: changed (``_words``). Not a loss, so not in ``_loss_counters``: the
    #: source Words such a run consumed are counted in ``words_dropped``.
    words_rebuilt: int = 0
    #: Lines that lost their OCR confidence — @conf removed because the
    #: correction made it false. Counted per LINE and named for the shared
    #: key both formats emit; it was ``conf_dropped`` and counted per
    #: @conf, which made PAGE the only counter in the report speaking a
    #: unit no line could be held to, and left ALTO silent about the same
    #: event. See :mod:`saknussemm.core.losses`.
    confidence_invalidated: int = 0
    #: Raw @conf removals. NOT reported — the promotion to a per-line count
    #: happens in the rewrite loop, which is the only place that knows where
    #: a line ends. Private so no consumer can key on it.
    _conf_occurrences: int = 0
    alt_textequiv_dropped: int = 0
    custom_offset_stripped: int = 0
    hyphen_preserved: int = 0
    line_word_disagreement: int = 0

    @property
    def total_processed(self) -> int:
        return self.subs_only + self.fast_path + self.slow_path

    @property
    def total_lines(self) -> int:
        return self.untouched + self.total_processed

    def _loss_counters(self) -> dict[str, int]:
        """The raw loss-counter snapshot (all keys, zeros included) —
        diffed around each line by the rewrite loop for the per-line
        attribution (ADR-012)."""
        return {
            "words_dropped": self.words_dropped,
            INVALIDATION_COUNTER: self.confidence_invalidated,
            "alt_textequiv_dropped": self.alt_textequiv_dropped,
            "custom_offset_stripped": self.custom_offset_stripped,
            "hyphen_preserved": self.hyphen_preserved,
            "line_word_disagreement": self.line_word_disagreement,
        }

    def as_losses(self) -> dict[str, int]:
        """Non-zero PAGE-specific counters, for ``CorrectionReport.format_losses``."""
        return {k: v for k, v in self._loss_counters().items() if v}


def _promote_confidence_to_line(
    metrics: PageRewriterMetrics, occurrences_before: int
) -> None:
    """One ``@conf`` removed or forty, the line lost its confidence once.

    Called by the rewrite loop, the only scope that knows where a line ends,
    and before :func:`_record_line_losses` so the per-line attribution sees
    it. A ``Word`` deleted outright by the slow path takes its ``@conf`` with
    it and is NOT counted here: that loss is ``words_dropped``, and the line
    still reports its confidence gone via the line-level ``TextEquiv``.
    """
    if COUNTS_INVALIDATION and metrics._conf_occurrences > occurrences_before:
        metrics.confidence_invalidated += 1


def _record_line_losses(
    losses_by_line: dict[str, dict[str, int]],
    line_id: str,
    counters_before: dict[str, int],
    metrics: PageRewriterMetrics,
) -> None:
    """ADR-012 — attribute what the loss counters gained while one line
    was processed to that line (only lines that lost something appear)."""
    delta = {
        key: after - counters_before[key]
        for key, after in metrics._loss_counters().items()
        if after > counters_before[key]
    }
    if delta:
        losses_by_line[line_id] = delta


# ---------------------------------------------------------------------------
# Low-level element helpers
# ---------------------------------------------------------------------------


def _direct(el: etree._Element, local: str, ns: str) -> list[etree._Element]:
    want = _tag(local, ns)
    return [c for c in el if c.tag == want]


def _drop_conf(te: etree._Element) -> bool:
    """Remove a stale ``@conf`` from a TextEquiv. Returns True if one went."""
    if "conf" in te.attrib:
        del te.attrib["conf"]
        return True
    return False


def _set_textequiv_text(te: etree._Element, text: str, ns: str) -> None:
    """Set a TextEquiv's ``Unicode`` (create if missing) and its
    ``PlainText`` when one is present. Geometry/order untouched."""
    uni = te.find(_tag("Unicode", ns))
    if uni is None:
        uni = etree.SubElement(te, _tag("Unicode", ns))
    uni.text = text
    plain = te.find(_tag("PlainText", ns))
    if plain is not None:
        plain.text = text


def _insertion_index(tl: etree._Element, ns: str) -> int:
    """Where to insert a new line-level TextEquiv: before a line ``TextStyle``
    if one exists, else at the end. Keeps the PAGE child sequence valid."""
    style_tag = _tag("TextStyle", ns)
    for i, child in enumerate(tl):
        if child.tag == style_tag:
            return i
    return len(tl)


def _update_line_textequiv(
    tl: etree._Element, text: str, ns: str, metrics: PageRewriterMetrics
) -> None:
    """P3: update the canonical line TextEquiv, drop @conf and alternatives.

    Creates the canonical TextEquiv when the line had none (word-only line).
    """
    equivs = _direct(tl, "TextEquiv", ns)
    if not equivs:
        te = etree.Element(_tag("TextEquiv", ns))
        _set_textequiv_text(te, text, ns)
        tl.insert(_insertion_index(tl, ns), te)
        return

    canonical = canonical_textequiv(tl, ns)
    assert canonical is not None  # equivs non-empty
    _set_textequiv_text(canonical, text, ns)
    if _drop_conf(canonical):
        metrics._conf_occurrences += 1
    # Remove the alternatives — they described the old reading (P3).
    for te in equivs:
        if te is not canonical:
            tl.remove(te)
            metrics.alt_textequiv_dropped += 1


def _update_words_fast(
    tl: etree._Element,
    word_els: list[etree._Element],
    words: list[str],
    ns: str,
    metrics: PageRewriterMetrics,
) -> None:
    """P4 fast path: word count unchanged — update each Word's canonical
    TextEquiv in place, keep Coords, drop @conf, remove word alternatives."""
    for w_el, token in zip(word_els, words):
        equivs = _direct(w_el, "TextEquiv", ns)
        canonical = canonical_textequiv(w_el, ns)
        if canonical is None:
            canonical = etree.SubElement(w_el, _tag("TextEquiv", ns))
        _set_textequiv_text(canonical, token, ns)
        if _drop_conf(canonical):
            metrics._conf_occurrences += 1
        for te in equivs:
            if te is not canonical:
                w_el.remove(te)
                metrics.alt_textequiv_dropped += 1


def _remove_words(
    tl: etree._Element,
    word_els: list[etree._Element],
    metrics: PageRewriterMetrics,
) -> None:
    """P4 slow path: word count changed — drop Word children (text lives at
    line level). Word polygons on a skewed line would be dishonest."""
    for w_el in word_els:
        tl.remove(w_el)
        metrics.words_dropped += 1


class _WordRebuilder:
    """P4 slow path: keep the Words the correction left alone, redraw the rest.

    One per rewritten document. When nothing can be kept (see
    :func:`_words.plan_words`) the line's Words are removed, which is what
    the slow path always did.
    """

    def __init__(self, root: etree._Element, ns: str) -> None:
        self._root, self._ns = root, ns
        self._widths = PageWidths(root, ns)
        self._ids: set[str] | None = None

    def _fresh_id(self, line_id: str) -> str:
        if self._ids is None:
            self._ids = {i for el in self._root.iter() if (i := el.get("id"))}
        n = 0
        while (candidate := f"{line_id}_w{n}") in self._ids:
            n += 1
        self._ids.add(candidate)
        return candidate

    def rebuild_or_remove(
        self,
        tl: etree._Element,
        word_els: list[etree._Element],
        words: list[str],
        metrics: PageRewriterMetrics,
    ) -> None:
        plans = plan_words(tl, word_els, words, self._ns, self._widths)
        if plans is None:
            _remove_words(tl, word_els, metrics)
            return
        at = list(tl).index(word_els[0])
        tail = word_els[0].tail
        kept = {plan.kept for plan in plans if plan.kept is not None}
        for i, w_el in enumerate(word_els):
            tl.remove(w_el)
            metrics.words_dropped += i not in kept
        placed: list[etree._Element] = []
        for plan in plans:
            if plan.kept is None:
                el = new_word(self._fresh_id(tl.get("id", "")), plan, self._ns)
                el.tail = tail
                metrics.words_rebuilt += 1
            else:
                el = word_els[plan.kept]
                _update_words_fast(tl, [el], [plan.text], self._ns, metrics)
                _strip_custom_offsets(el, metrics)
            placed.append(el)
        for k, el in enumerate(placed):
            tl.insert(at + k, el)


def _strip_custom_offsets(el: etree._Element, metrics: PageRewriterMetrics) -> None:
    """P6: drop offset-anchored ``custom`` groups whose ranges are now stale.

    Structural groups (readingOrder/structure) are preserved verbatim. When
    nothing offset-anchored remains the attribute is left as-is; when it
    empties out entirely it is removed rather than left blank.
    """
    custom = el.get("custom")
    if not custom:
        return
    new_custom, removed = strip_offset_groups(custom)
    if removed == 0:
        return
    metrics.custom_offset_stripped += removed
    if new_custom:
        el.set("custom", new_custom)
    else:
        del el.attrib["custom"]


# P5 / E5-extended — now the shared core helper: the PIPELINE applies it
# before decisions materialize (decision == artefact, always); this call
# site remains as idempotent defence in depth.
_preserve_hyphen = preserve_break_char


# ---------------------------------------------------------------------------
# Provenance (P7)
# ---------------------------------------------------------------------------


def _provenance_text(
    provider: str,
    model: str,
    lib_version: str | None,
    config_fingerprint: str | None,
) -> str:
    provenance = "saknussemm"
    if lib_version:
        provenance += f" {lib_version}"
    if config_fingerprint:
        provenance += f"; config {config_fingerprint}"
    return f"Post-OCR correction via {provider}/{model} ({provenance})"


def _add_provenance(
    root: etree._Element,
    ns: str,
    provider: str,
    model: str,
    lib_version: str | None,
    config_fingerprint: str | None,
) -> None:
    """Record the correction pass (P7): a ``MetadataItem`` on 2019+ schemas,
    else appended to ``Metadata/Comments``. No wall-clock timestamp is
    written, keeping the output deterministic (byte-stable for a given
    input) — the same choice the ALTO ``processingStep`` makes."""
    metadata = root.find(_tag("Metadata", ns))
    if metadata is None:
        return
    desc = _provenance_text(provider, model, lib_version, config_fingerprint)

    if supports_metadata_item(ns):
        item = etree.SubElement(metadata, _tag("MetadataItem", ns))
        item.set("type", "processingStep")
        item.set("name", "saknussemm")
        item.set("value", desc)
        return

    comments = metadata.find(_tag("Comments", ns))
    if comments is None:
        comments = etree.SubElement(metadata, _tag("Comments", ns))
        comments.text = desc
    else:
        existing = comments.text or ""
        comments.text = f"{existing}\n{desc}" if existing.strip() else desc


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def rewrite_page_file(
    xml_path: Path,
    page_manifests: list[PageManifest],
    provider: str,
    model: str,
    *,
    lib_version: str | None = None,
    config_fingerprint: str | None = None,
) -> RewriteResult:
    """Rewrite a PAGE XML file with corrected text from ``page_manifests``.

    Returns a :class:`RewriteResult`; the per-line rewriter path is one
    of ``untouched`` / ``fast_path`` / ``slow_path`` (never
    ``subs_only``).
    """
    tree = read_source_tree_classified(xml_path)
    root = tree.getroot()
    ns = _detect_namespace(root)
    metrics, rebuilder = PageRewriterMetrics(), _WordRebuilder(root, ns)
    line_paths: dict[str, str] = {}
    losses_by_line: dict[str, dict[str, int]] = {}

    # ADR-007 — a bare line_id keys every correction-to-element association
    # below; duplicates (manifest or element side) fail loudly instead of
    # silently rewriting the wrong physical line. Mirrors the ALTO
    # rewriter: canonical shared check for the manifest side.
    ensure_unique_identities(page_manifests, xml_path.name)
    line_by_id: dict[str, LineManifest] = {
        lm.line_id: lm for page in page_manifests for lm in page.lines
    }

    seen_element_ids: set[str] = set()
    textline_tag = _tag("TextLine", ns)
    for tl in root.iter(textline_tag):
        line_id = tl.get("id")
        if line_id not in line_by_id:
            continue
        if line_id in seen_element_ids:
            raise DuplicateIdError(
                f"duplicate TextLine id {line_id!r} in {xml_path.name!r} — "
                "two physical lines would receive the same correction (ADR-007)."
            )
        seen_element_ids.add(line_id)
        lm = line_by_id[line_id]
        # ADR-012 — everything the counters gain while THIS line is
        # processed is this line's own loss attribution.
        counters_before = metrics._loss_counters()
        conf_occurrences_before = metrics._conf_occurrences

        source_text = canonical_line_text(tl, ns)
        raw_corrected = (
            lm.corrected_text if lm.corrected_text is not None else lm.ocr_text
        )
        corrected = (
            _preserve_hyphen(source_text, nfc(raw_corrected)).replace("\r", "").strip()
        )

        # P2 diagnostic — line text vs word concat disagreement (line wins).
        word_els = _direct(tl, "Word", ns)
        if word_els and _direct(tl, "TextEquiv", ns):
            concat = nfc(
                " ".join(t for w in word_els if (t := word_text(w, ns)))
            ).strip()
            if concat and concat != source_text:
                metrics.line_word_disagreement += 1

        # --- Path 1: UNTOUCHED ---
        if corrected == source_text:
            metrics.untouched += 1
            line_paths[line_id] = "untouched"
            _promote_confidence_to_line(metrics, conf_occurrences_before)
            _record_line_losses(losses_by_line, line_id, counters_before, metrics)
            continue

        if trailing_hyphen_char(source_text, HYPHEN_CHARS) is not None:
            metrics.hyphen_preserved += 1

        words = corrected.split()

        # --- P4 word handling ---
        if word_els and len(words) != len(word_els):
            rebuilder.rebuild_or_remove(tl, word_els, words, metrics)
            path = "slow_path"
        else:
            if word_els:
                _update_words_fast(tl, word_els, words, ns, metrics)
                # P6 — surviving Words: strip their stale offset groups.
                for w_el in word_els:
                    _strip_custom_offsets(w_el, metrics)
            path = "fast_path"

        # --- P3 line-level update (both paths) ---
        _update_line_textequiv(tl, corrected, ns, metrics)
        # --- P6 line-level custom: offsets into the old text are now stale ---
        _strip_custom_offsets(tl, metrics)

        if path == "fast_path":
            metrics.fast_path += 1
        else:
            metrics.slow_path += 1
        line_paths[line_id] = path
        _promote_confidence_to_line(metrics, conf_occurrences_before)
        _record_line_losses(losses_by_line, line_id, counters_before, metrics)

    _add_provenance(root, ns, provider, model, lib_version, config_fingerprint)
    xml_bytes = etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", pretty_print=False
    )
    return RewriteResult(
        xml_bytes=xml_bytes,
        metrics=metrics,
        rewriter_paths=line_paths,
        texts=_extract_texts_from_root(root, ns, set(line_by_id)),
        texts_verbatim=_extract_texts_from_root(root, ns, set(line_by_id), True),
        losses=metrics.as_losses(),
        losses_by_line=losses_by_line,
    )


def _extract_texts_from_root(
    root: etree._Element, ns: str, line_ids: set[str], verbatim: bool = False
) -> dict[str, str]:
    """Canonical per-line text of a PAGE tree, matching the parser's
    reconstruction.

    ``verbatim=True`` is the same walk with the NFC pass OFF: the file's
    codepoints rather than the logical reading of them. Where the two
    differ, the file spells a character its own way — decomposed — and the
    decision spells it composed. Real, invisible to a comparison of two
    normalised strings, and reported as ``exact`` until 2026-08-16. ALTO
    grew the same second reading first, for the same reason.

    Called positionally from ``rewrite_page_file`` on purpose: that
    function is pinned by the size ratchet and may only shrink, so the
    explanation lives here rather than at the call site.
    """
    textline_tag = _tag("TextLine", ns)
    result: dict[str, str] = {}
    for tl in root.iter(textline_tag):
        line_id = tl.get("id")
        if line_id in line_ids:
            if line_id in result:
                # ADR-007 — a repeated id would silently collapse two physical
                # lines into one trace entry.
                raise DuplicateIdError(
                    f"duplicate TextLine id {line_id!r} in rewritten PAGE — "
                    "output-text extraction would be ambiguous (ADR-007)."
                )
            result[line_id] = canonical_line_text(tl, ns, verbatim=verbatim)
    return result


def extract_output_texts(xml_bytes: bytes, line_ids: set[str]) -> dict[str, str]:
    """Re-extract canonical line text from rewritten PAGE XML.

    The pipeline no longer calls this (the rewrite returns its texts on
    the :class:`RewriteResult`); it remains for round-trip checks over
    arbitrary PAGE bytes."""
    root = etree.fromstring(xml_bytes, make_safe_parser())
    return _extract_texts_from_root(root, _detect_namespace(root), line_ids)


__all__ = [
    "PageRewriterMetrics",
    "rewrite_page_file",
    "extract_output_texts",
]
