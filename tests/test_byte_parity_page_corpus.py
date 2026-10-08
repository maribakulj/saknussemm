"""Byte parity for PAGE, which had a text check and no hash.

``docs/promises.md`` graded this row **"partielle, proche d'aucune" — texte
seulement, aucun sha256**, next to an ALTO row that has had pinned digests and
a classified diff history since v1.0. So the format where the rewrite drops
the most markup was the one nothing pinned at the byte level.

What makes the digests here worth having rather than ceremonial is that the
diff is **classified**, not merely frozen. Measured on 2026-08-17 over both
real PAGE fixtures, with the identity and scripted scenarios ALTO already
uses:

============  ==========  =========  ==================================
fixture       scenario    bytes      element census vs source
============  ==========  =========  ==================================
Descartes     identity    131791     **unchanged**
Descartes     scripted    113204     ``Word`` -47, and its four children
LaFayette     identity     29000     **unchanged**
LaFayette     scripted     26163     ``Word`` -7, and its four children
============  ==========  =========  ==================================

On 2026-10-07, the scripted digests deliberately changed again: stale
region-level TextEquiv are now removed when a descendant line changes.
Compared with f763824, Descartes drops four region readings and LaFayette
two; every TextLine remains byte-identical. Identity digests stay unchanged.

Two things follow, and both are asserted below rather than left to the hash.

**The identity run changes no element at all.** Its 20 extra bytes are the
provenance stamp. That assertion survives a deliberate provenance change,
which a digest does not — so it is the one that keeps meaning after the next
justified hash update.

**Every dropped ``Word`` is counted.** ``words_dropped`` equals the number of
``<Word>`` elements missing from the output, exactly, on both fixtures. That
is the `R*` promise — every alteration declared and counted — cross-checked
between the report and the delivered bytes, which nothing did for PAGE. A
digest would have frozen an uncounted drop just as happily as a counted one.

**Why dropping them is principled**, since 47 elements is a visible loss: the
line-level text is authoritative, and in these files it already disagrees
with its own words. Measured, because "the fixtures disagree" is the sort of
claim that should not be asserted from the shape of the code — 31 of 32 lines
in the Descartes page and 10 of 13 in the LaFayette one, and only one of the
41 by spacing alone. The line reads ``ſciences … richeſſes`` where its words
read ``fciences … richesses``; another reads ``8 Discours.`` against
``L Discours.``. Two transcriptions of one line in one file. Keeping stale
words beside a corrected line would deliver a contradiction; dropping and
counting them is the documented remedy.

**A wrinkle named rather than pinned.** ``line_word_disagreement`` is that
measurement, and its own comment in the rewriter calls it a *diagnostic*. It
lands in ``format_losses`` — the field for what the run lost — so an identity
run whose element census is provably unchanged still reports 31 "losses". It
is the mirror image of a phantom loss: a true observation about the source,
published under a heading that means something else. Moving it changes the
report's shape, which is an arbitration like the one open on `#108`, so this
file makes the fact visible and leaves the move to that decision.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter

import pytest

from saknussemm.formats.page.parser import build_document_manifest
from saknussemm.formats.page.rewriter import rewrite_page_file

from tests._paths import EXAMPLES
from tests.test_byte_parity_corpus import _scripted_correction

_PAGE = EXAMPLES / "page"

_FIXTURES = {
    "Descartes": "Descartes1637_Discours_btv1b86069594_corrected_0014_page_raw.xml",
    "LaFayette": "LaFayette1678_Cleves_btv1b8610820b_corrected_0011_page_raw.xml",
}

#: Pinned 2026-08-17. Moving one of these is legitimate; moving it without
#: classifying the diff per element, in the commit message, is not — the ALTO
#: sibling's docstring is the model, and it is long because every move is
#: accounted for there.
_GOLDEN = {
    ("Descartes", "identity"): (
        "afcf40824bc272d78b4b41fee75d76874ee92ee4fa63316581983b049f869a9a"
    ),
    ("Descartes", "scripted"): (
        "476fe97c74d9eddda45dc40a3a9b79cb0c047c03eb7ca45860669dff20b88cf0"
    ),
    ("LaFayette", "identity"): (
        "4b38b1e1ecdcc1e29ec68056115e8a1ab234414a2da3c8d05efe08bd1d7e7c7d"
    ),
    ("LaFayette", "scripted"): (
        "10c62e508fcb7ea06b98f7190a3bf3d2bf380c95a50cb0998f40adeb17160295"
    ),
}

#: The four elements a ``<Word>`` subtree carries, so a drop is visible as a
#: shape rather than as one number.
_WORD_CHILDREN = ("Coords", "TextStyle", "TextEquiv", "Unicode")


def _census(payload: bytes) -> Counter[str]:
    """Element-name counts, read from the bytes rather than from a tree.

    Counting on the delivered bytes is the point: it cannot agree with the
    rewrite by construction the way a check against the tree the rewrite
    built would.
    """
    return Counter(name.decode() for name in re.findall(rb"<(\w+)[ />]", payload))


def _rewrite(fixture: str, scenario: str):
    path = _PAGE / _FIXTURES[fixture]
    doc = build_document_manifest([(path, path.name)])
    index = 0
    for page in doc.pages:
        for line in page.lines:
            line.corrected_text = (
                line.ocr_text
                if scenario == "identity"
                else _scripted_correction(index, line.ocr_text)
            )
            index += 1
    return path.read_bytes(), rewrite_page_file(path, doc.pages, "test", "mock")


def _declared(result) -> Counter[str]:
    total: Counter[str] = Counter()
    for per_line in (result.losses_by_line or {}).values():
        total.update(per_line)
    return total


@pytest.mark.parametrize(("fixture", "scenario"), sorted(_GOLDEN))
def test_page_output_bytes_are_pinned(fixture: str, scenario: str) -> None:
    _, result = _rewrite(fixture, scenario)
    digest = hashlib.sha256(result.xml_bytes).hexdigest()
    assert digest == _GOLDEN[(fixture, scenario)], (
        f"{fixture}/{scenario}: PAGE output bytes moved. If deliberate, "
        "classify the diff per element — the two assertions below say which "
        "shapes are expected — and update the digest with that classification "
        "in the commit message."
    )


@pytest.mark.parametrize("fixture", sorted(_FIXTURES))
def test_an_identity_run_changes_no_element(fixture: str) -> None:
    """The assertion that outlives the next justified digest change.

    A hash says "these bytes"; this says "nothing structural moved", which is
    the property the hash was standing in for. The 20-byte growth is the
    provenance stamp, and stamping it is a promise of its own (§11).
    """
    source, result = _rewrite(fixture, "identity")
    before, after = _census(source), _census(result.xml_bytes)
    drifted = {
        name: after[name] - before[name]
        for name in set(before) | set(after)
        if after[name] != before[name]
    }
    assert not drifted, (
        f"{fixture}: an identity run changed the element census by {drifted}. "
        "Correcting a line to its own text must take the untouched path, "
        "which rebuilds nothing."
    )
    assert result.metrics.fast_path == 0 and result.metrics.slow_path == 0, (
        f"{fixture}: identity took fast={result.metrics.fast_path} "
        f"slow={result.metrics.slow_path}. Both must be zero, or the census "
        "above agreed for a reason that will not hold on the next fixture."
    )
    assert len(result.xml_bytes) > len(source), (
        f"{fixture}: the identity output is not larger than its source, so the "
        "provenance step §11 requires was not written."
    )


@pytest.mark.parametrize("fixture", sorted(_FIXTURES))
def test_every_dropped_word_is_counted(fixture: str) -> None:
    """`R*` cross-checked between the report and the bytes, for PAGE.

    ``words_dropped`` is a number the rewrite reports about itself. This
    counts the ``<Word>`` elements actually missing from the delivered bytes
    and requires the two to agree — the arithmetic a phantom loss and an
    uncounted one both fail, from opposite sides.

    **Both channels are checked, and the second was added after a mutation
    slipped through the first.** The per-line sum comes from a counter the
    rewrite loop *diffs* around each line (ADR-012), so a constant offset
    injected into that counter cancels out and is invisible to it. The
    run-level total is absolute and catches exactly that — and also a loss
    counted outside any line's window, which the per-line sum can never see.
    """
    source, result = _rewrite(fixture, "scripted")
    before, after = _census(source), _census(result.xml_bytes)
    lost = before["Word"] - after["Word"]
    per_line = _declared(result)["words_dropped"]
    run_level = result.metrics.as_losses().get("words_dropped", 0)

    assert lost > 0, (
        f"{fixture}: the scripted scenario dropped no Word element, so this "
        "case checks nothing. Either the scenario stopped correcting anything "
        "or the rewrite stopped rebuilding — both change what the digests "
        "above mean."
    )
    assert (per_line, run_level) == (lost, lost), (
        f"{fixture}: {lost} <Word> element(s) are missing from the delivered "
        f"bytes; the per-line attribution declares {per_line} and the run "
        f"total {run_level}. A loss the report does not carry is the `R*` "
        "promise inverted; a loss it carries and the file did not take is a "
        "phantom; and the two channels disagreeing means one of them is "
        "attributing to the wrong line."
    )
    region_readings = _declared(result)["region_textequiv_dropped"]
    for child in _WORD_CHILDREN:
        expected = lost + (region_readings if child in {"TextEquiv", "Unicode"} else 0)
        assert before[child] - after[child] == expected, (
            f"{fixture}: {lost} <Word> element(s) went but {child} moved by "
            f"{before[child] - after[child]}. A Word is dropped whole, with "
            "its four children; region readings also lose TextEquiv/Unicode, "
            "and each must be counted separately."
        )


@pytest.mark.parametrize("fixture", sorted(_FIXTURES))
def test_a_source_diagnostic_is_published_as_a_loss(fixture: str) -> None:
    """Named so the wrinkle is visible, not so it is endorsed.

    ``line_word_disagreement`` counts lines whose own text contradicts the
    concatenation of their ``<Word>`` elements. It is a fact about the SOURCE,
    it fires whether or not the run touches the line, and it is published in
    ``format_losses`` — the field for what the run lost. So an identity run
    that provably changed no element still reports losses.

    This asserts the current behaviour, deliberately: moving the counter out
    of ``format_losses`` changes the report's shape, which is a public-surface
    arbitration and not a test's decision to make. When it moves, this test
    fails and points at the reason.
    """
    _, result = _rewrite(fixture, "identity")
    declared = _declared(result)
    assert set(declared) == {"line_word_disagreement"}, (
        f"{fixture}: an identity run declared {dict(declared)}. Every counter "
        "here but this one describes something the run did, and an identity "
        "run does nothing."
    )
    assert declared["line_word_disagreement"] > 0, (
        f"{fixture}: the fixture's line and word levels now agree, so nothing "
        "demonstrates the wrinkle. It also means the justification for "
        "dropping Word elements — the line level is authoritative because the "
        "two already disagree — needs re-measuring on this corpus."
    )
