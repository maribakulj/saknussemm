"""Byte-parity gate on the non-regression corpus (spec §13 DoD, v1.0).

Same inputs → same output bytes. Two deterministic scenarios over the two
corpus files, pinned by sha256:

  - **identity** — every line corrected with its own OCR text. Verified
    BYTE-IDENTICAL to the pre-v1.0 baseline (commit 8c4789c) during the
    post-audit parity run: F4 only widens the UNTOUCHED path and F2/F6
    never fire without a content change.
  - **scripted** — deterministic corrections exercising the fast path
    (every 3rd line: first 'e' → '3', same word count) and the slow path
    (every 7th line: ' zz' appended). Versus the same baseline, the only
    differing TextLines were classified as the DOCUMENTED v1.0 changes:
    F2 (WC/CC dropped on changed Strings) and F6/§6.1 (rebalanced
    slow-path String+SP geometry). No text drift, no structure drift.

    Audit-D rev (2026-07-12) — the scripted hashes moved again, classified
    per TextLine: the ONLY diff is that a slow-path rebuild of an explicit
    PART1/BOTH line now emits its trailing ``<HYP>`` with the reserved
    end-of-line geometry (HPOS/VPOS/WIDTH/HEIGHT flush to the line's right
    edge) instead of a geometry-less ``<HYP CONTENT="-"/>``. This is the
    rewriter.py #16 fix: the HYP fills its reserved slot so the child
    widths sum exactly to the line WIDTH and nothing overlaps the last
    String. String/SP geometry, text, CONTENT and structure are byte-
    identical; the identity hashes are unchanged (the rebuild path never
    fires without a word-count change).

    Double-hyphen fix (2026-07-21) — the two SCRIPTED hashes moved again
    (identity hashes unchanged: identity takes the UNTOUCHED path, which the
    fix never touches). An explicit PART1 line carries its break hyphen in
    the <HYP> element; when the LLM returns the fragment WITH a trailing
    hyphen ("préve-"), the rewriter stored it in the last String CONTENT too,
    doubling it. The fix drops that trailing hyphen from the write text on
    explicit PART1 lines only. Classified: after the fix, ZERO explicit PART1
    lines in either corpus carry a doubled hyphen; heuristic PART1 (no
    HYP/SUBS markup) keeps its trailing dash in CONTENT, unchanged.

    Provenance fix (2026-07-21) — all four hashes moved by exactly one
    localized, deterministic change: the rewriter now records the correction
    pass as a ``<postProcessingStep>`` inside the file's existing
    ``<OCRProcessing>`` container. Previously ``_add_processing_entry`` only
    handled the ALTO 4.0 generic ``<Processing>`` element and silently wrote
    NOTHING for real OCR files (both corpus fixtures use ``<OCRProcessing>``),
    breaking §11's "every corrected file records the pass". Classified per
    subtree: the original ``<ocrProcessingStep>`` (Tesseract / ABBYY) is
    preserved untouched; the ONLY addition is the appended
    ``<postProcessingStep>``. No TextLine, String, SP, HYP, text or geometry
    drift — the identity path still never rebuilds a line.

    Rename to saknussemm (2026-08-16) — all four hashes moved by exactly
    one line. The library writes its own name into the provenance it
    stamps, so ``<softwareName>`` and the step description carry the new
    one. Classified by rendering the SAME fixture with the pre-rename code
    in a git worktree and diffing the two outputs: three diff lines, all in
    the ``<postProcessingStep>``, and the two files are the same 10280
    bytes — all three names happen to be ten characters, so not even the byte
    count moved. Zero TextLine, String, SP, HYP, text or geometry drift.

    The second rename was classified the same way rather than assumed to
    be the same event: same fixture, pre-rename code in a git worktree,
    two outputs diffed. One line, in the `<postProcessingStep>`. A hash
    that moves for a known reason still has to be shown to have moved for
    THAT reason.

If a hash moves, do NOT regenerate blindly: re-run the classifier
(scratch parity_classify.py pattern — parse both outputs, diff per
TextLine, bucket into text/structure/confidence/geometry) and update the
hash ONLY for a deliberate, documented byte change, naming it in the
commit message. The rewrite is invoked WITHOUT provenance arguments so
these hashes are independent of the library version string.

    Mixed-role break fix (2026-07-27) — ONE scripted hash moved
    (``X0000002.xml``; the other three are unchanged, and identity is
    untouched because it takes the UNTOUCHED path). Classified per TextLine:
    **exactly 1 of 566 differs**, ``PAG_00000002_TL000454``, whose last
    String goes from ``Wal`` back to ``Wal-``. Nothing else in the file
    changes — not geometry, not attributes, not structure.

    That line is BOTH: it opens with an explicit ``SUBS_TYPE="HypPart2"``
    and ends on a bare heuristic dash with no ``<HYP>``. The writer decided
    whether to strip the trailing mark from the String by reading
    ``hyphen_source_explicit`` — which describes the BACKWARD link — and got
    "explicit", so it dropped the dash expecting a ``<HYP>`` to render it.
    There is none, and the mark was simply gone from the delivered file. It
    now reads ``forward_break_is_explicit``, the role→slot map applied to
    the right flag. The old hash pinned the defect.
"""

from __future__ import annotations

import hashlib

import pytest

from saknussemm.formats.alto.parser import build_document_manifest
from saknussemm.formats.alto.rewriter import rewrite_alto_file

from tests._paths import EXAMPLES

_EXAMPLES = EXAMPLES

_GOLDEN = {
    ("sample.xml", "identity"): (
        "6b1c8ea81c28076a10b65a8e147442063a4e8671cd4ee870ba67021920c0ed16"
    ),
    # 2026-09-29, anchored slow-path geometry: 2 TextLines of 10 differ,
    # geometry only -- the untouched words keep the producer's boxes and the
    # appended " zz" is drawn after the last word at its natural size. See
    # test_byte_parity_all_fixtures.py for the classification.
    ("sample.xml", "scripted"): (
        "1dfccc6a9af1db21ad1fe7970344faa5af3cc81e1ad274937cb99e80b045bdaa"
    ),
    ("X0000002.xml", "identity"): (
        "6b29f2269127f5ec9af15b6196e2e4c2ef48db4bf804aa616c2e0477f4db102a"
    ),
    # See the module docstring, "Mixed-role break fix": one TextLine of 566
    # regained the trailing dash the writer used to drop.
    # 2026-09-29, anchored slow-path geometry: 81 TextLines of 566 differ,
    # geometry only (the " zz" lines). See test_byte_parity_all_fixtures.py.
    ("X0000002.xml", "scripted"): (
        "9821e24d3c2bd2190c3b5e0531e7867272778fa2b8fd75235d7b186e3fd4d17d"
    ),
}


def _scripted_correction(i: int, text: str) -> str:
    words = text.split()
    if not words:
        return text
    if i % 7 == 0:
        return text + " zz"  # word count +1 → slow path
    if i % 3 == 0 and "e" in words[0]:
        words = [words[0].replace("e", "3", 1)] + words[1:]
        return " ".join(words)  # same word count → fast path
    return text


@pytest.mark.parametrize(
    ("filename", "scenario"),
    sorted(_GOLDEN),
    ids=lambda v: v if isinstance(v, str) else str(v),
)
def test_corpus_output_bytes_are_pinned(filename: str, scenario: str) -> None:
    xml_path = _EXAMPLES / filename
    doc = build_document_manifest([(xml_path, xml_path.name)])
    i = 0
    for page in doc.pages:
        for lm in page.lines:
            if scenario == "identity":
                lm.corrected_text = lm.ocr_text
            else:
                lm.corrected_text = _scripted_correction(i, lm.ocr_text)
            i += 1
    _res = rewrite_alto_file(xml_path, doc.pages, "test", "mock")
    xml_bytes = _res.xml_bytes
    digest = hashlib.sha256(xml_bytes).hexdigest()
    assert digest == _GOLDEN[(filename, scenario)], (
        f"{filename}/{scenario}: output bytes moved. If deliberate, classify "
        f"the diff per TextLine and update the golden hash with a documented "
        f"commit message; see this file's docstring."
    )


def test_identity_output_equals_source_reserialisation() -> None:
    """Identity corrections must not perturb a single TextLine: the output
    re-parses to the same per-line text as the source for every line."""
    from saknussemm.formats.alto.rewriter import extract_output_texts

    xml_path = _EXAMPLES / "X0000002.xml"
    doc = build_document_manifest([(xml_path, xml_path.name)])
    all_ids = set()
    for page in doc.pages:
        for lm in page.lines:
            lm.corrected_text = lm.ocr_text
            all_ids.add(lm.line_id)
    _res = rewrite_alto_file(xml_path, doc.pages, "test", "mock")
    xml_bytes = _res.xml_bytes
    metrics = _res.metrics
    assert metrics.fast_path == 0 and metrics.slow_path == 0
    out_texts = extract_output_texts(xml_bytes, all_ids)
    by_id = {lm.line_id: lm for p in doc.pages for lm in p.lines}
    for lid, txt in out_texts.items():
        assert txt.strip() == by_id[lid].ocr_text
