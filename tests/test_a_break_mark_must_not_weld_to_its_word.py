"""A break mark must not weld to the word before it. Closed 2026-08-19.

Found by a real Mistral run over 20 Gallica newspaper pages on 2026-08-17:
one page produced **no output at all**, killed by ``ProjectionError``.

    rewritten XML for 'alto.xml' diverges from the run's decision on line
    'PAG_1_TL000441': decided 'à la révision des jugements et d -' but the
    artefact contains 'à la révision des jugements et d-'

The space between ``d`` and the break mark was gone, so the file said
something the run did not decide. Refusing to deliver was correct — the
projection invariant was doing its job. The defect was upstream of it, and
what it cost was not a space: the words diverge, so
``classify_projection_fidelity`` returns ``None``, and nothing between there
and ``run()`` catches it. **One line lost the whole document** — every other
file, and the ``CorrectionReport`` with its traces along with them.

**Not the rare accident it looked like.** The shape — an explicit
``HypPart1`` whose last ``String`` is the break mark itself, preceded by an
``<SP>``, with a ``<HYP>`` after — occurs on 29 of the 24 694 lines in the
54 real Gallica files, which sounds negligible until you count files: **10
of 35 carry at least one**, and all ten belong to two issues
(``bpt6k4607951t``, ``bpt6k46079527``). It is a producer signature, not a
scatter. For a holding digitised by that chain the failure rate is not 0.12%
of lines, it is most of the files. And those 29 lines read
``"g'.e :.:;r.. --"``, ``"1K' --"`` — precisely the lines a corrector
restructures, so the odds of triggering GIVEN the shape are high.

**Why it stayed open for two days, and why that reason was wrong.** This
docstring used to say the fix "touches the geometry, and writing bad
geometry into a delivered file is worse than the lost space". Both halves
turned out to be false. The geometry is free: the ``<SP>`` is carved OUT of
the slot already reserved for the ``<HYP>``, so no other token moves and the
children still tile the line exactly.

**The real obstacle, which nobody had named.** A first fix read the trailing
whitespace off the text inside ``_rebuild_line`` — and broke
``test_f6_no_whitespace_geometry_unchanged``, a declared property saying an
edge space must not move the geometry. The two are not in conflict; they are
about different spaces, which ``_drop_structural_break_hyphen`` already
tells apart and the rebuild no longer can:

    'deux mots- '   space AFTER the mark, noise   ->  'deux mots'
    'et d -'        space BEFORE it, the source's ->  'et d '

By the time the rebuild sees the text the mark is gone and both merely "end
in whitespace". The information is not recoverable there — so it travels, as
``space_before_break``, from the one place that sees the text on both sides
of the drop. ``F6`` is untouched.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from lxml import etree

from saknussemm.core.schemas import LineStatus
from saknussemm.formats.alto.parser import parse_alto_file
from saknussemm.formats.alto.rewriter import extract_output_texts, rewrite_alto_file

_NS = 'xmlns="http://www.loc.gov/standards/alto/ns-v4#"'

#: The real line's shape: `<SP>`, the break mark as its own String carrying
#: the SUBS, then `<HYP>`. Reduced only in the words before it.
_DOCUMENT = (
    f'<?xml version="1.0" encoding="UTF-8"?><alto {_NS}><Layout>'
    '<Page ID="P1" WIDTH="4000" HEIGHT="200"><PrintSpace>'
    '<TextBlock ID="B1" HPOS="0" VPOS="0" WIDTH="4000" HEIGHT="100">'
    '<TextLine ID="TL1" HPOS="0" VPOS="10" WIDTH="900" HEIGHT="40">'
    '<String ID="S1" CONTENT="et" HPOS="0" VPOS="10" WIDTH="60" HEIGHT="30"/>'
    '<SP HPOS="60" VPOS="10" WIDTH="20"/>'
    '<String ID="S2" CONTENT="d" HPOS="80" VPOS="10" WIDTH="30" HEIGHT="30"/>'
    '<SP HPOS="110" VPOS="10" WIDTH="33"/>'
    '<String ID="S3" CONTENT="-" HPOS="143" VPOS="10" WIDTH="7" HEIGHT="4" '
    'SUBS_TYPE="HypPart1" SUBS_CONTENT="demain"/>'
    '<HYP CONTENT="-" HPOS="150" VPOS="12" WIDTH="30"/>'
    "</TextLine></TextBlock></PrintSpace></Page></Layout></alto>"
)


def _deliver(decided: str) -> str:
    path = Path(tempfile.mkdtemp()) / "w.xml"
    path.write_bytes(_DOCUMENT.encode("utf-8"))
    pages, _ = parse_alto_file(path, path.name)
    line = pages[0].lines[0]
    line.corrected_text = decided
    line.status = LineStatus.CORRECTED
    result = rewrite_alto_file(path, pages, "test", "mock")
    return extract_output_texts(result.xml_bytes, {"TL1"})["TL1"]


def test_the_fixture_is_the_shape_that_fails() -> None:
    """Guard the reproduction itself: an explicit PART1 with a doubled mark.

    If the parser stops seeing this as ``HypPart1``, or the fixture loses its
    ``<HYP>``, the case below would pass for a reason that has nothing to do
    with the defect.
    """
    path = Path(tempfile.mkdtemp()) / "w.xml"
    path.write_bytes(_DOCUMENT.encode("utf-8"))
    pages, _ = parse_alto_file(path, path.name)
    line = pages[0].lines[0]
    assert line.hyphen_role.value == "HypPart1", line.hyphen_role
    assert line.ocr_text == "et d -", repr(line.ocr_text)
    assert "<HYP" in _DOCUMENT


def test_the_fast_path_keeps_the_space() -> None:
    """The same line, same mark, unchanged word count — and it is correct.

    This is what says the defect is the REBUILD and not the hyphen handling:
    both paths drop the structural mark, only one loses the space.
    """
    assert _deliver("et d -") == "et d -"


def test_the_slow_path_keeps_the_space() -> None:
    """The line that killed a real page, now delivered as decided.

    A correction that adds words routes the line through the rebuild. Before
    the fix the space before the break mark did not survive it, the words
    diverged, and the document was lost.
    """
    decided = "à la révision et d -"
    assert _deliver(decided) == decided


def test_the_space_is_taken_from_the_hyp_slot_not_added_beside_it() -> None:
    """The geometry objection that kept this open, asserted rather than argued.

    The `<SP>` must come out of the width already reserved for the `<HYP>`:
    any other source of width moves every token on the line. Children tiling
    the line exactly — no overlap, no gap, ending on `HPOS + WIDTH` — is what
    says it did.
    """
    path = Path(tempfile.mkdtemp()) / "w.xml"
    path.write_bytes(_DOCUMENT.encode("utf-8"))
    pages, _ = parse_alto_file(path, path.name)
    line = pages[0].lines[0]
    line.corrected_text = "à la révision et d -"
    line.status = LineStatus.CORRECTED
    result = rewrite_alto_file(path, pages, "test", "mock")

    root = etree.fromstring(result.xml_bytes)
    ns = root.tag.split("}")[0].strip("{")
    textline = next(root.iter(f"{{{ns}}}TextLine"))
    kinds = {f"{{{ns}}}{n}" for n in ("String", "SP", "HYP")}
    children = [
        (c.tag.rsplit("}", 1)[-1], int(c.get("HPOS")), int(c.get("WIDTH")))
        for c in textline
        if c.tag in kinds
    ]

    assert children[-1][0] == "HYP", children
    assert children[-2][0] == "SP", children

    # Anchored layout (2026-09-29): the Strings keep the boxes the source
    # gave them and no longer tile the line, so "nothing moved" is now read
    # directly -- no overlap, in order, and the SP + HYP still inside the
    # line box, never past its right edge.
    cursor = int(textline.get("HPOS"))
    for local, hpos, width in children:
        assert hpos >= cursor, f"{local} at {hpos}, before {cursor}: {children}"
        assert width >= 1, children
        cursor = hpos + width
    assert cursor <= int(textline.get("HPOS")) + int(textline.get("WIDTH")), children


def test_a_space_after_the_mark_is_still_noise() -> None:
    """The other meaning of "ends in whitespace", which must NOT survive.

    ``'et d- '`` puts the space after the break mark, where it means nothing
    — the mark is the last thing on the line. Re-emitting it would be the
    fix overshooting into `F6`'s territory, so this is the case that says
    ``space_before_break`` is reading the right side of the mark.
    """
    assert _deliver("à la révision et d- ") == "à la révision et d-"
