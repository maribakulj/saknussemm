"""A reference the code makes must resolve, and must still resolve later.

Two vocabularies are legitimate in a source comment, and the repository
rule (CONTRIBUTING.md, `docs/adr/README.md`) says why: code comments state
the invariant, ADRs hold the genealogy, and the spec holds the contract.

  * ``ADR-NNN`` — a file under ``docs/adr/``.
  * ``§n`` — a numbered section of ``SPECS_LIB_V2.md``.

`ADR-012` was cited seventeen times across `core` and both format packages
while `docs/adr/` stopped at 011, and the index stopped at 008 while
009-011 existed on disk. Neither is a typo anyone would catch by reading:
a citation reads as authoritative precisely because it looks resolvable,
and an index reads as complete precisely because it is an index.

Everything else the code cites is **work-item vocabulary**: the row of a
plan, the finding of an audit, the slice of a wave. It resolves for as long
as someone remembers which plan, and then it stops — three of the four
families below already point into ``docs/history/``, which is frozen by
`CLAUDE.md` and must never be updated to match the code. A reader who
cannot resolve the tag has been told nothing; a reader who can has been
told where the change came from, which is not what a comment is for.

So the tags go and the knowledge stays. That trade is the whole point: a
comment reading ``F8 — only TARGET lines`` loses nothing by becoming ``Only
TARGET lines``, and a comment whose entire content is ``(S2)`` was never
carrying any.

The families, and where each one used to point:

  ``F<nn>``      spec-review findings — ``docs/history/PLAN-CORRECTIONS.md``
  ``P3.<n>``     slices of the v3 roadmap — ``docs/history/ROADMAP_LIB_V3.md``
  ``S/L/R<n>``   rows of ``docs/PLAN.md``, archived as each one closes
  ``slice <X>``  wave slices, admissible ONLY next to the ADR that defines
                 them (``ADR-011 slice E`` resolves; a bare ``slice E``
                 does not)
  ``Audit-…``,   the audit trail, which CONTRIBUTING.md already keeps out of
  ``wave <n>``   new code comments

`RM-<nn>` is deliberately NOT in that list. The remediation wave is in
flight and its rows are live in ``docs/PLAN.md``; those tags are swept when
the wave closes, by the session that closes it.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests._paths import REPO, SRC as _SRC

REPO = REPO
SRC = _SRC  # the arithmetic lives in tests._paths, and only there
ADR_DIR = REPO / "docs" / "adr"
SPEC = REPO / "SPECS_LIB_V2.md"

_CITATION = re.compile(r"ADR-(\d{3})")
_INDEX_LINK = re.compile(r"\[(\d{3})\]\((\d{3}-[a-z0-9-]+\.md)\)")

#: ``## 8. API publique`` / ``### 5.2 bis — …`` → ``8`` / ``5.2``.
_SPEC_HEADING = re.compile(r"^#{2,4}\s+(\d+(?:\.\d+)*)\.?\s")
_SPEC_CITATION = re.compile(r"§\s?(\d+(?:\.\d+)*)")

#: One match per work-item tag. The leading lookbehind keeps ``ADR-011``
#: from reading as an ``R``-row and ``P3.7-4`` from reading as two tags.
_WORK_ITEM = re.compile(
    r"(?<![\w.\-§])("
    r"F\d{1,2}"
    r"|P3\.\d+(?:-\d+)?"
    r"|[GLRSV]\d{1,2}[a-z]?"
    r"|(?:slice|tranche)\s+[A-Z0-9]"
    r"|Audit-[\w-]+"
    r"|(?:waves?|vagues?)\s+\d+"
    r")(?![\w-])"
)


def _adr_files() -> dict[str, Path]:
    return {p.name[:3]: p for p in ADR_DIR.glob("[0-9][0-9][0-9]-*.md")}


def _sources() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def _rel(path: Path) -> str:
    return str(path.relative_to(SRC))


def _work_item_tags(text: str) -> list[str]:
    """Every work-item tag in ``text``, in order.

    A ``slice``/``tranche`` mention on a line that also names an ADR is a
    resolvable citation (``ADR-011`` documents its slices) and is not a tag.
    """
    found = []
    for line in text.splitlines():
        anchored = _CITATION.search(line) is not None
        for tag in _WORK_ITEM.findall(line):
            if anchored and tag[:5] in ("slice", "tranc"):
                continue
            found.append(tag)
    return found


# --- The two resolvable vocabularies ----------------------------------------


def test_every_cited_adr_exists() -> None:
    have = _adr_files()
    missing: dict[str, list[str]] = {}
    for path in _sources():
        for number in set(_CITATION.findall(path.read_text(encoding="utf-8"))):
            if number not in have:
                missing.setdefault(number, []).append(_rel(path))
    assert not missing, (
        f"the code cites ADRs with no file: {missing}. A citation is a "
        "promise that the reasoning is written down somewhere — write the "
        "ADR, or stop citing it."
    )


def test_the_index_lists_every_adr() -> None:
    index = (ADR_DIR / "README.md").read_text(encoding="utf-8")
    linked = {n for n, _ in _INDEX_LINK.findall(index)}
    on_disk = set(_adr_files())
    assert on_disk - linked == set(), (
        f"ADR(s) {sorted(on_disk - linked)} exist but are absent from "
        "docs/adr/README.md — an index that stops early reads as a complete "
        "one."
    )


def test_every_index_link_resolves() -> None:
    index = (ADR_DIR / "README.md").read_text(encoding="utf-8")
    broken = [
        filename
        for _, filename in _INDEX_LINK.findall(index)
        if not (ADR_DIR / filename).exists()
    ]
    assert not broken, f"docs/adr/README.md links to missing file(s): {broken}"


def test_the_spec_numbers_its_sections() -> None:
    """Guard against the § test passing because it found nothing to check."""
    sections = _spec_sections()
    assert len(sections) >= 20, (
        f"only {len(sections)} numbered sections found in {SPEC.name} — the "
        "heading pattern has drifted, and every § citation is now checked "
        "against an empty set."
    )


def _spec_sections() -> set[str]:
    numbers = set()
    for line in SPEC.read_text(encoding="utf-8").splitlines():
        match = _SPEC_HEADING.match(line)
        if match:
            numbers.add(match.group(1))
    return numbers


def test_every_cited_spec_section_exists() -> None:
    """``§n`` means ``SPECS_LIB_V2.md``, and it means it unqualified.

    Two of these used to name another document inline — ``ARCHITECTURE.md
    §3.2`` (frozen history) and ``prior audit §7.1`` (an audit nobody can
    name). Both read exactly like a spec reference at a glance, which is
    the failure: the sigil is the library's contract or it is nothing.
    """
    sections = _spec_sections()
    dangling: dict[str, list[str]] = {}
    for path in _sources():
        for number in set(_SPEC_CITATION.findall(path.read_text(encoding="utf-8"))):
            if number not in sections:
                dangling.setdefault(number, []).append(_rel(path))
    assert not dangling, (
        f"§ citations with no section in {SPEC.name}: {dangling}. § is "
        "reserved for the spec — if the reference is to another document, "
        "state the invariant in the comment instead."
    )


# --- The vocabulary that has to go ------------------------------------------

#: Files that still carry work-item tags, with how many. A ratchet, and the
#: reason this test is worth more than one grep: a file may only shrink, a
#: file that reached zero must leave the map, and a file absent from the map
#: must be clean. Sorting one file is then a self-contained green commit.
#:
#: Measured 2026-08-10 at 215 tags in 48 files; `RM-06` cleared 45 of them.
#: The three that remain are exactly the files this wave is forbidden to
#: touch (`docs/PLAN.md`, "Ce que la vague ne touche pas"):
#: `core/pairing.py` and `core/hyphenation.py` are `S1` territory, and
#: `formats/alto/rewriter.py` is measured by `RM-10` and never cut. Their 23
#: tags are swept by whoever opens those files next — the same triage, and
#: the domain knowledge around them (the BnF `TL000454` case, the geometric
#: vetting) stays.
_STILL_TAGGED: dict[str, int] = {
    "core/hyphenation.py": 2,
    "core/pairing.py": 5,
    "formats/alto/rewriter.py": 14,
}


def test_no_new_file_carries_work_item_tags() -> None:
    offenders = {
        _rel(path): tags
        for path in _sources()
        if (tags := _work_item_tags(path.read_text(encoding="utf-8")))
        and _rel(path) not in _STILL_TAGGED
    }
    named = {file: sorted(set(tags)) for file, tags in offenders.items()}
    assert not offenders, (
        f"work-item tags in files that had none: {named}. "
        "These name a plan row, not an invariant. State what the code "
        "guarantees; cite an ADR or a § if the genealogy matters."
    )


def test_the_tagged_files_only_shrink() -> None:
    grown = {}
    for relative, budget in _STILL_TAGGED.items():
        count = len(_work_item_tags((SRC / relative).read_text(encoding="utf-8")))
        if count > budget:
            grown[relative] = (budget, count)
    assert not grown, (
        f"work-item tags added to already-tagged files (budget, now): {grown}. "
        "The ratchet only turns one way."
    )


def test_the_ratchet_has_no_stale_entries() -> None:
    """A file that reached zero leaves the map, or the map lies about it."""
    stale = {}
    for relative, budget in _STILL_TAGGED.items():
        path = SRC / relative
        assert path.exists(), f"_STILL_TAGGED names a file that is gone: {relative}"
        count = len(_work_item_tags(path.read_text(encoding="utf-8")))
        if count < budget:
            stale[relative] = (budget, count)
    assert not stale, (
        f"these files carry fewer tags than the map claims (budget, now): "
        f"{stale}. Lower the budget in the same commit that removed them — "
        "a ratchet with slack in it stops being one."
    )
