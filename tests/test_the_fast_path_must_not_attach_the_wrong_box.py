"""An equal word count does not make positional pairing correct.

The ALTO rewriter has a fast path: when the corrected line has as many
words as the line has ``String`` children, it rewrites ``CONTENT`` in
place and leaves every other attribute alone. That is the path that keeps
geometry, identity and ``STYLEREFS`` byte-identical, and it is worth
having.

Its premise is that word *i* corresponds to ``String`` *i*. The rewriter
states the opposite promise a hundred lines further down — *identity
follows the word it corresponds to, never whatever sat at the same
position* — and only the **slow path** keeps it, by aligning tokens.

**A correction can keep the count and move the boundary.** ``au`` +
``jourdhui`` corrected to ``aujourd`` + ``hui`` is two words before and
two words after; a word-splitting rule over OCR spacing does this on
every page it touches. Measured on 2026-08-17, before the guard:

    S1 CONTENT='aujourd'  WIDTH=60   ->   8.6 units per character
    S2 CONTENT='hui'      WIDTH=820  -> 273.3 units per character
    rewriter_path='fast_path'  fidelity=EXACT  losses=None

Seven characters in the box drawn for two, ``STYLEREFS`` swapped with
them, and the report claims the strongest thing the fidelity scale can
say — because the reconstructed *text* does equal the decision. **The
fidelity check reads text; it is blind to which box a word landed in.**

Who pays: any consumer that crops line images from the geometry. That
includes this library's own vision producer, which would read the wrong
slice of the scan and be told the projection was exact.

After the guard, same line: 84.9 and 85.0 units per character.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from saknussemm.core.pipeline import CorrectionPipeline
from saknussemm.formats.alto.rewriter import _word_boundary_moved
from saknussemm.formats.loader import build_document_manifest
from saknussemm.producers.rules import RulesProducer, SubstitutionRule

from tests._pipeline_harness import RecordingObserver

#: ``au`` sits in a narrow box and ``jourdhui`` in a wide one, so a moved
#: boundary is visible in the geometry rather than needing to be inferred.
_ALTO = """<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#"><Layout>
<Page ID="P1" WIDTH="1000" HEIGHT="200"><PrintSpace>
<TextBlock ID="B1" HPOS="0" VPOS="0" WIDTH="1000" HEIGHT="100">
<TextLine ID="TL1" HPOS="100" VPOS="10" WIDTH="900" HEIGHT="40">
<String ID="S1" CONTENT="au" HPOS="100" VPOS="10" WIDTH="60" HEIGHT="40" STYLEREFS="TXT_1"/>
<SP WIDTH="20" HPOS="160" VPOS="10"/>
<String ID="S2" CONTENT="jourdhui" HPOS="180" VPOS="10" WIDTH="820" HEIGHT="40" STYLEREFS="TXT_2"/>
</TextLine></TextBlock></PrintSpace></Page></Layout></alto>
"""

#: Before the guard the two ratios differed by a factor of 32. Three is
#: generous for a proportional redistribution and nowhere near 32.
_MAX_RATIO_SPREAD = 3.0


def _run_the_splitting_correction() -> tuple[list[tuple[str, int]], str]:
    """``([(content, width), …], rewriter_path)`` for the corrected line."""
    directory = Path(tempfile.mkdtemp())
    path = directory / "boundary.xml"
    path.write_text(_ALTO, encoding="utf-8")

    manifest = build_document_manifest([(path, path.name)])
    pipeline = CorrectionPipeline(
        producer=RulesProducer([SubstitutionRule("au jourd", "aujourd ")]),
        observer=RecordingObserver(),
    )
    result = pipeline.run_sync(
        document_manifest=manifest, source_files={path.name: path}
    )

    strings = [
        (
            re.search(r'CONTENT="([^"]*)"', element).group(1),  # type: ignore[union-attr]
            int(re.search(r'WIDTH="([^"]*)"', element).group(1)),  # type: ignore[union-attr]
        )
        for element in re.findall(
            r"<String[^>]*/>", result.corrected_files[path.name].decode("utf-8")
        )
    ]
    return strings, result.report.lines[0].projection.rewriter_path or ""


def test_the_fixture_really_moves_a_boundary_at_constant_word_count() -> None:
    """Otherwise the assertion below holds over a line the fast path owns.

    Both halves matter: the count must be equal (or the fast path is never
    reached and the test proves nothing about it) and the words must
    actually differ (or there is no boundary to misplace).
    """
    strings, _ = _run_the_splitting_correction()
    assert [content for content, _ in strings] == ["aujourd", "hui"], (
        f"the correction did not land as expected — got {strings}. This test "
        "needs a line whose word COUNT is unchanged and whose word "
        "BOUNDARY moved; without that it says nothing."
    )


def test_geometry_follows_the_word_it_belongs_to() -> None:
    strings, path_taken = _run_the_splitting_correction()
    ratios = [width / max(1, len(content)) for content, width in strings]
    spread = max(ratios) / max(1e-9, min(ratios))
    assert spread <= _MAX_RATIO_SPREAD, (
        f"the words sit in boxes of wildly different density — {spread:.1f}× "
        f"between {ratios} for {strings}, via {path_taken!r}. An equal word "
        "count made the fast path possible; it did not make the positional "
        "pairing correct. The rewriter promises that identity follows the "
        "word, never whatever sat at the same position — and a consumer "
        "cropping line images from this geometry reads the wrong slice of "
        "the scan while the report calls the projection exact."
    )


def test_the_report_does_not_claim_the_fast_path_took_it() -> None:
    """The narrower statement, so a regression names itself.

    Kept separate from the geometry assertion because it is a different
    claim: this one says the rewriter *noticed*, the other says the file
    is right. A future rewriter that pairs correctly on the fast path
    would make this one obsolete and the other one still true.
    """
    _, path_taken = _run_the_splitting_correction()
    assert path_taken == "slow_path", (
        f"the line was rewritten via {path_taken!r}. A moved boundary must "
        "fall back to the path that aligns tokens rather than trusting "
        "positions."
    )


def test_the_obvious_guard_would_have_passed_this_line() -> None:
    """Why the boundary test is what it is, pinned so it is not simplified.

    The first idea — *a corrected word must share at least one character
    with the original at the same position* — reads like the right guard
    and passes the very line above: ``aujourd`` shares ``a`` and ``u``
    with ``au``, ``hui`` shares three characters with ``jourdhui``. It was
    verified before the guard was written, and this test keeps that
    finding executable.
    """
    originals, words = ["au", "jourdhui"], ["aujourd", "hui"]
    assert all(set(o.lower()) & set(w.lower()) for o, w in zip(originals, words)), (
        "the 'shares a character' rule no longer passes this line, so the "
        "warning in this test is stale — recheck it before trusting it."
    )
    assert _word_boundary_moved(originals, words), (
        "the boundary guard no longer catches the case it exists for."
    )


def test_ordinary_corrections_stay_on_the_fast_path() -> None:
    """The other half: re-routing everything would also satisfy the above.

    These are the corrections the fast path exists to serve — same word,
    different glyphs — including the ones where *every* character changes.
    Sending them to the slow path would recompute geometry that was
    already right, which is a loss even though it breaks no invariant.
    """
    for originals, words in (
        (["Frauce"], ["France"]),
        (["uue"], ["une"]),
        (["0"], ["o"]),
        (["|||"], ["Ill"]),
        (["attendre"], ["attendrent"]),
        (["au", "jourdhui"], ["au", "jourdhui"]),
        (["Frauce", "uue"], ["France", "une"]),
        (["ﬂeur", "bleue"], ["fleur", "bleue"]),
        (["cafe\u0301", "chaud"], ["café", "chaud"]),
        (["bonjour,", "ami!"], ["bonjour", "ami."]),
        (["un", "jour"], ["une", "jours"]),
    ):
        assert not _word_boundary_moved(originals, words), (
            f"{originals} -> {words} was refused the fast path. This is an "
            "ordinary correction at a stable boundary; refusing it costs "
            "geometry that was already correct."
        )


def test_a_boundary_move_with_a_typo_declines_the_alto_fast_path(tmp_path):
    path = tmp_path / "boundary.xml"
    path.write_text(
        _ALTO.replace('CONTENT="au"', 'CONTENT="le"').replace(
            'CONTENT="jourdhui"', 'CONTENT="stcmps"'
        )
    )
    manifest = build_document_manifest([(path, path.name)])
    result = CorrectionPipeline(
        producer=RulesProducer([SubstitutionRule("le stcmps", "les temps")]),
        observer=RecordingObserver(),
    ).run_sync(document_manifest=manifest, source_files={path.name: path})
    assert result.report.lines[0].projection.rewriter_path == "slow_path"
    assert result.report.lines[0].projection.extracted_text == "les temps"
