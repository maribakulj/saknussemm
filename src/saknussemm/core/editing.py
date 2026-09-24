"""The span edit protocol (spec §4) — types, normalisation, application.

An ``EditScript`` is the seam the spec inserts between the compiler
(``enrich_chunk_lines`` + payload) and the recomposer (the format
rewriters): a producer returns edit *operations* instead of raw corrected
text, and this module turns them into per-line corrected text the
rewriter already knows how to write back.

Two operations, no structural ones (invariant I2 is guaranteed by the
type, not by a check):

  - ``ReplaceLine`` — the whole line's text (the historical LLM response,
    re-expressed as one op). Byte-for-byte the old behaviour: applying it
    is just ``text_by_id[line_id] = op.text``.
  - ``ReplaceSpan`` — replace a sub-range of the line's *canonical* text,
    anchored either by explicit offsets (``RangeAnchor``, deterministic
    producers) or by an exact substring (``MatchAnchor``, LLM producers).
    Every ``MatchAnchor`` normalises to a ``RangeAnchor`` against the
    canonical text; an unfound / ambiguous / out-of-range anchor rejects
    the op (fallback keeps the line, invariant I2).

Invariants E1–E6 (§4.4). E1–E3 are structural, E4/E5 are span-only drift
guards; **E4/E5 never touch ``ReplaceLine``**, which the downstream
three-stage guard matrix (E6) already governs — that is what keeps the
re-expression byte-parity. E6 itself is applied later by the pipeline, at
the line level, identically for both ops.

Pure core: imports only ``core.schemas`` / ``core.pairing`` (no lxml, no
format, no producer) — the import-contract test keeps it that way.
"""

from __future__ import annotations

import hashlib
from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing_extensions import Annotated

from saknussemm.core._norm import has_line_separator, nfc
from saknussemm.core.pairing import HYPHEN_CHARS
from saknussemm.core.schemas import (
    DEFAULT_GUARD_CONFIG,
    GuardConfig,
    HyphenRole,
    LineManifest,
)
from saknussemm.errors import ProposalValidationError

#: Version of THIS edit protocol. Bumped only on a breaking
#: change to the op/anchor semantics; ``apply_edit_script`` refuses a
#: script stamped with a version it does not speak.
EDIT_PROTOCOL_VERSION = "1"


def line_digest(text: str) -> str:
    """Stable 16-hex digest of one line's canonical text.

    The unit of the script's per-line preconditions: same shape as the
    §11 policy fingerprints. Consumers building scripts by hand compute
    theirs with this exact function.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Anchors (§4.3)
# ---------------------------------------------------------------------------


class RangeAnchor(BaseModel):
    """Offsets into the line's canonical text (deterministic producers)."""

    model_config = ConfigDict(frozen=True)
    start: int
    end: int


class MatchAnchor(BaseModel):
    """An exact substring of the canonical text (LLM producers).

    ``occurrence`` selects the n-th (0-indexed) occurrence. Honouring the
    §4.3 uniqueness intent (the convergent practice of aider's
    search/replace and Anthropic's ``str_replace``), the default ``None``
    *requires uniqueness*: a match found more than once is ambiguous and
    the op is rejected. An explicit integer — **including 0 for "the
    first occurrence"** — always selects that occurrence.

    ``occurrence`` is ``int | None``, never defaulted to ``0``: a
    default would conflate "producer said nothing" with "producer wants
    the first occurrence", making the first of several repeats
    inexpressible (0 + multiple matches → rejected as ambiguous).
    """

    model_config = ConfigDict(frozen=True)
    match: str
    occurrence: int | None = None


# ---------------------------------------------------------------------------
# Operations (§4.2)
# ---------------------------------------------------------------------------


class ReplaceLine(BaseModel):
    op: Literal["replace_line"] = "replace_line"
    line_id: str
    #: Held in NFC: the parsers read the source in NFC and the rewriters
    #: write NFC, but a model answers in whatever form it likes — a
    #: decomposed « aisé » (e + U+0301) decided here was written
    #: precomposed, the post-render check saw two different strings and
    #: declared the page undeliverable (VR-14). Normalising at the op is
    #: the one place every producer passes through.
    text: str
    # line_ids may legitimately repeat across
    # FILES; only page_ids are document-unique. The final edit_script stamps
    # this so a consumer can attribute every op to its file. Optional and
    # additive: hand-written scripts without it keep their old semantics,
    # and per the CorrectionReport contract a new optional key does NOT
    # bump report_version.
    page_id: str | None = None
    #: the producer's self-assessment of THIS
    #: proposal in [0, 1], already VERIFIED app-side when it comes from
    #: the LLM uncertainty channel (claims checked against the confusion
    #: table / lexicon — the model supplies auditable evidence, never a
    #: raw score). Feeds the ``producer`` component of
    #: :class:`~saknussemm.core.schemas.LineConfidence`. Optional and
    #: additive; ``None`` = the producer declared nothing.
    producer_confidence: float | None = None

    @field_validator("text")
    @classmethod
    def _nfc(cls, value: str) -> str:
        return nfc(value)


class ReplaceSpan(BaseModel):
    op: Literal["replace_span"] = "replace_span"
    line_id: str
    anchor: Union[MatchAnchor, RangeAnchor]
    #: NFC, like ``ReplaceLine.text``.
    text: str
    #: See ``ReplaceLine.page_id``.
    page_id: str | None = None

    @field_validator("text")
    @classmethod
    def _nfc(cls, value: str) -> str:
        return nfc(value)


EditOp = Annotated[Union[ReplaceLine, ReplaceSpan], Field(discriminator="op")]


class LinePrecondition(BaseModel):
    """What one targeted line's SOURCE text must be for the script to
    apply to it.

    ``digest`` is :func:`line_digest` of the canonical source text at
    script-build time. ``page_id`` qualifies the line like the ops'
    stamp does (bare line_ids repeat across files); ``None`` keeps
    hand-written single-file scripts simple.
    """

    model_config = ConfigDict(frozen=True)
    line_id: str
    page_id: str | None = None
    digest: str


class EditScript(BaseModel):
    ops: list[EditOp] = Field(default_factory=list)
    #: The protocol this script speaks. Scripts built by this
    #: library stamp the current version; ``apply_edit_script`` raises
    #: on a version it does not know. ``None`` (hand-written / legacy
    #: JSON) is accepted as the current version.
    protocol_version: str | None = None
    #: Source file name → ``sha256:<hex>`` of the INPUT bytes
    #: the script was derived from (same shape as
    #: ``RunProvenance.source_digests``). Recorded for consumers
    #: replaying against files; not verifiable by ``apply_edit_script``
    #: itself, which sees only canonical text.
    source_digests: dict[str, str] = Field(default_factory=dict)
    #: Per targeted line, the digest of the source text the
    #: ops were computed against. ``apply_edit_script`` REJECTS the
    #: line's ops when the document at hand carries the same line_id
    #: with different content — an op must never land on a lookalike.
    preconditions: list[LinePrecondition] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Result / rejection reporting
# ---------------------------------------------------------------------------


class EditRejection(BaseModel):
    """One op that could not be applied — the line keeps its prior text."""

    line_id: str
    op: str
    reason: str  # short machine code (see the constants below)
    detail: str = ""


# Rejection reason codes.
R_UNKNOWN_LINE = "e1_unknown_line"
#: `E1` — the line exists in the payload but was shown for CONTEXT, not as a
#: target. A distinct code from ``e1_unknown_line`` because the two mean
#: opposite things to whoever reads the report: an unknown id is a producer
#: inventing a line, a context line is a producer answering a question it was
#: not asked. Reporting both as "unknown" made the second unreadable, and the
#: second is the common one — a payload does not mark which of its lines are
#: targets, so a model shown a window corrects all of it.
R_CONTEXT_LINE = "e1_context_line"
R_CONFLICT = "conflict"  # >1 replace_line, or replace_line mixed with spans
R_EMPTY = "e3_empty"
R_NEWLINE = "e3_newline"
R_OVERLAP = "e2_overlap"
R_DRIFT_RATIO = "e4_span_growth"
R_DRIFT_BUDGET = "e4_line_budget"
R_HYPHEN = "e5_hyphen"
#: `E5b` — a span erased the word that continues a broken word, leaving the
#: PART2 line to start on whatever followed. Its own code because it accuses
#: the opposite side of the pair from ``e5_hyphen``: that one says the
#: FORWARD line lost its mark, this one says the BACKWARD line lost the word
#: the mark pointed at.
R_BOUNDARY_WORD = "e5_boundary_word"
R_ANCHOR_NOT_FOUND = "anchor_not_found"
R_ANCHOR_AMBIGUOUS = "anchor_ambiguous"
R_ANCHOR_RANGE = "anchor_out_of_range"
R_ANCHOR_EMPTY = "anchor_empty_match"
R_PRECONDITION = "precondition_source_digest"


class EditResult(BaseModel):
    """Outcome of applying an ``EditScript``.

    ``text_by_id`` holds the new canonical text for every line that had at
    least one *accepted* op. Lines whose ops were all rejected are absent —
    the caller keeps their prior text (OCR fallback, invariant I2).
    """

    text_by_id: dict[str, str] = Field(default_factory=dict)
    rejected: list[EditRejection] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Anchor normalisation (§4.3)
# ---------------------------------------------------------------------------


def normalize_anchor(
    anchor: MatchAnchor | RangeAnchor, canonical: str
) -> tuple[RangeAnchor | None, str | None]:
    """Normalise any anchor to a ``RangeAnchor`` against ``canonical``.

    Returns ``(range, None)`` on success or ``(None, reason)`` on rejection.
    """
    if isinstance(anchor, RangeAnchor):
        if 0 <= anchor.start <= anchor.end <= len(canonical):
            return anchor, None
        return None, R_ANCHOR_RANGE

    if anchor.match == "":
        return None, R_ANCHOR_EMPTY

    starts: list[int] = []
    i = canonical.find(anchor.match)
    while i != -1:
        starts.append(i)
        i = canonical.find(anchor.match, i + 1)

    if not starts:
        return None, R_ANCHOR_NOT_FOUND
    if anchor.occurrence is None:
        # No explicit occurrence: the match must be unique.
        if len(starts) > 1:
            return None, R_ANCHOR_AMBIGUOUS
        s = starts[0]
    else:
        # Explicit occurrence — 0 legitimately names the first of several.
        if anchor.occurrence < 0 or anchor.occurrence >= len(starts):
            return None, R_ANCHOR_RANGE
        s = starts[anchor.occurrence]
    return RangeAnchor(start=s, end=s + len(anchor.match)), None


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------


def _has_newline(text: str) -> bool:
    # Twin of the validator's single-line gate: every
    # str.splitlines boundary counts, not just \n/\r (the shared
    # predicate keeps the two enforcement points from drifting).
    return has_line_separator(text)


def _changed_chars(original: str, replacement: str) -> int:
    """Characters actually changed by replacing ``original`` with
    ``replacement`` — the size of the differing window after trimming the
    common prefix and suffix.

    The E4 line budget must NOT sum ``abs(len(replacement) -
    len(original))``: a length-*neutral* rewrite of 100 characters cost 0,
    so ``edit_line_max_changed_chars`` bounded length drift, not the
    amount of text changed — much weaker than the invariant's name. The
    trimmed-window size is cheap, deterministic, and never underestimates
    the edit (it upper-bounds the Levenshtein distance): identical texts
    cost 0, a pure insertion/deletion costs its length, a full rewrite
    costs the larger side.
    """
    if original == replacement:
        return 0
    p = 0
    max_p = min(len(original), len(replacement))
    while p < max_p and original[p] == replacement[p]:
        p += 1
    s = 0
    max_s = min(len(original), len(replacement)) - p
    while (
        s < max_s
        and original[len(original) - 1 - s] == replacement[len(replacement) - 1 - s]
    ):
        s += 1
    return max(len(original), len(replacement)) - p - s


def _e5_hyphen_ok(
    role: HyphenRole, result_text: str, source: str | None = None
) -> bool:
    """E5 — a span-edited hyphen line keeps its break mark AND a word to
    continue.

    The mark alone was checked until 2026-08-17, and the docstring claimed
    the boundary word was "guaranteed by the non-empty result check". It
    was not: a span may erase the word and leave the mark. Measured —
    ``Le peuple att-`` with a span erasing ``att`` was accepted as
    ``Le peuple -``, and the ALTO carried ``<String CONTENT="-"/>``, a
    ``String`` holding a bare hyphen. ``_part1_text_migrated`` bounds only
    how much a PART1 line may GROW; nothing bounded how much it may shrink.

    So the forward side now requires a non-space character immediately
    before the mark. That is exact rather than heuristic: if the parser
    called this line PART1, a word ended here, and a break mark with
    nothing before it is not a continuation — it is a dash. **No
    legitimate correction is refused**, because none of them leaves a mark
    dangling.

    The backward side (``PART2``) is closed by :func:`_e5b_boundary_word_kept`,
    which needs the SOURCE and the spans rather than the result alone.
    """
    if role in (HyphenRole.PART1, HyphenRole.BOTH):
        stripped = result_text.rstrip()
        if not stripped.endswith(HYPHEN_CHARS):
            return False
        before_mark = stripped.rstrip("".join(HYPHEN_CHARS))
        if not before_mark:
            return False
        # A SPACE before the mark is refused only when the correction put it
        # there. Measured on a real run: of 205 proposals this side refuses,
        # the gap is inherited from the source once and introduced zero
        # times — and that one inherited case is `#126`, an excellent
        # correction of `'a la revision d: s juy<nnen!s e d -'` whose only
        # oddity is a space the SOURCE already had. Judging the result alone
        # punishes a producer for being faithful.
        if before_mark[-1].isspace() and not (source or "").rstrip().rstrip(
            "".join(HYPHEN_CHARS)
        ).endswith(" "):
            return False
    return True


def _first_word_range(text: str) -> tuple[int, int] | None:
    """Where the first word of ``text`` starts and ends, or ``None`` if none."""
    start = 0
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text):
        return None
    end = start
    while end < len(text) and not text[end].isspace():
        end += 1
    return start, end


def _e5b_boundary_word_kept(
    role: HyphenRole, canonical: str, accepted: list[tuple[RangeAnchor, str]]
) -> bool:
    """`E5b` — a span may not ERASE the word that continues a broken word.

    A ``PART2`` line opens on the second half of a word cut at the previous
    line's edge. Erase it and the pair reads ``plu-`` + ``et le reste``: the
    line survives, so the non-emptiness check is satisfied, and the word the
    mark pointed at is simply gone. ``_e5_hyphen_ok``'s docstring used to
    claim the non-empty result covered this. It does not — that check
    guarantees the LINE survives, not the WORD, and the two are different
    properties.

    **The rule is "erased", not "changed", and that is measured rather than
    chosen.** On 1 433 real ``PART2``/``BOTH`` lines corrected by
    ``mistral-small-latest``, the boundary word was left alone 63% of the
    time, corrected 12%, and **replaced by something unrecognisable 25%** —
    because a ``PART2``'s first word is where OCR is worst, often reduced to
    a single stray character. ``'•'`` → ``'seil'``, ``';'`` → ``'dré'``,
    ``'j'`` → ``'parole'``: all correct, all scoring near zero similarity. A
    minimum-similarity rule would therefore refuse **23–31%** of real
    corrections, and refuse them exactly where correction is worth most.
    Refusing only ERASURE costs 0 of those 1 433 lines.

    So this is insurance rather than a filter, and deliberately so: it names
    the one gesture no legitimate correction makes, and takes no threshold
    with it — nothing to recalibrate when the corpus changes.
    """
    if role not in (HyphenRole.PART2, HyphenRole.BOTH):
        return True
    word = _first_word_range(canonical)
    if word is None:
        return True
    start, end = word
    return not any(
        anchor.start <= start and anchor.end >= end and not replacement.strip()
        for anchor, replacement in accepted
    )


def _apply_spans(canonical: str, ranges: list[tuple[RangeAnchor, str]]) -> str:
    """Apply non-overlapping (range, replacement) pairs right-to-left."""
    text = canonical
    for anchor, replacement in sorted(ranges, key=lambda rt: rt[0].start, reverse=True):
        text = text[: anchor.start] + replacement + text[anchor.end :]
    return text


def _whole_line_verdict(
    line_ops: list[ReplaceLine],
    span_ops: list[ReplaceSpan],
    role: HyphenRole,
    canonical: str,
    guard: GuardConfig,
) -> tuple[str, str | None]:
    """The whole-line path's proposed text, and why it may not stand.

    Returns ``(text, None)`` when the proposal survives every check, else
    ``(text, reason)``. The text comes back either way so the caller has
    something to name in the refusal.

    `E1`/`E3`/conflict have always been here. `E4`/`E5` joined them on
    2026-08-19 — see :func:`_whole_line_drift_refusal` for what that cost,
    measured before it was decided.
    """
    if len(line_ops) > 1 or span_ops:
        return "", R_CONFLICT
    text = line_ops[0].text
    if _has_newline(text):
        return text, R_NEWLINE
    if text.strip() == "":
        return text, R_EMPTY
    return text, _whole_line_drift_refusal(role, canonical, text, guard)


def _whole_line_drift_refusal(
    role: HyphenRole, canonical: str, text: str, guard: GuardConfig
) -> str | None:
    """`E4`/`E5` on a whole-line proposal, or ``None`` if it may stand.

    Until 2026-08-19 this path faced neither, so the two drift guards applied
    only to span producers — the rarer kind — and the default LLM producer
    was judged on meaning alone. `E6b` in ``docs/promises.md`` called that a
    non-parity: the same result got a different verdict depending on which
    vocabulary proposed it.

    **Closed after measuring what it would cost**, on 1 796 real proposals
    from ``mistral-small-latest``:

    - `E4` refuses **0**. The median corrected line changes 20 characters and
      the worst 168, against a budget of 200. The parity is free.
    - `E5` refuses **205**, of which **204 are already refused** downstream.
      It does not reject more; it rejects earlier, and names why. The cases
      are worth naming: ``'…du bu-'`` → ``'…du bu'`` (mark gone),
      ``'…dans la-'`` → ``'galerie des Fêtes.'`` (the NEXT line's text),
      ``'…de la tran-'`` → ``'quillité des esprits…'`` (the PART2 fragment).
      Every one is a line-integrity violation reaching acceptance under a
      generic refusal.
    - The 205th changed verdict, and it is why `E5`'s forward rule was
      refined at the same time — see :func:`_e5_hyphen_ok`.

    There is no per-op growth ratio here: a whole-line proposal is one op
    covering the line, so the ratio would compare the line to itself.
    """
    if _changed_chars(canonical, text) > guard.edit_line_max_changed_chars:
        return R_DRIFT_BUDGET
    if not _e5_hyphen_ok(role, text, canonical):
        return R_HYPHEN
    return None


def _e5_refusal(
    role: HyphenRole,
    canonical: str,
    result: str,
    accepted: list[tuple[RangeAnchor, str]],
) -> str | None:
    """`E5`'s verdict on a hyphenated line, or ``None`` if it may stand.

    Two sides of one pair, and two codes, because they accuse opposite
    lines: the FORWARD line losing the mark that promises a continuation,
    and the BACKWARD line losing the word that mark pointed at. Reporting
    both as ``e5_hyphen`` would make a refusal rate unreadable.
    """
    if not _e5_hyphen_ok(role, result, canonical):
        return R_HYPHEN
    if not _e5b_boundary_word_kept(role, canonical, accepted):
        return R_BOUNDARY_WORD
    return None


def _apply_line_ops(
    line_id: str,
    ops: list[ReplaceLine | ReplaceSpan],
    canonical: str,
    role: HyphenRole,
    guard: GuardConfig,
    rejected: list[EditRejection],
) -> str | None:
    """Apply one line's ops. Returns the new text, or ``None`` if the line
    should keep its prior text (every op rejected / a fatal conflict)."""
    line_ops = [o for o in ops if isinstance(o, ReplaceLine)]
    span_ops = [o for o in ops if isinstance(o, ReplaceSpan)]

    # --- replace_line: whole-line path (E1/E3/conflict, then E4/E5) ---
    if line_ops:
        text, reason = _whole_line_verdict(line_ops, span_ops, role, canonical, guard)
        if reason is not None:
            rejected.append(
                EditRejection(line_id=line_id, op="replace_line", reason=reason)
            )
            return None
        return text

    # --- replace_span: normalise, E2 overlap, E4 drift, apply, E3/E5 ---
    normalized: list[tuple[RangeAnchor, str, ReplaceSpan]] = []
    for sp in span_ops:
        if _has_newline(sp.text):
            rejected.append(
                EditRejection(line_id=line_id, op="replace_span", reason=R_NEWLINE)
            )
            continue
        rng, reason = normalize_anchor(sp.anchor, canonical)
        if rng is None:
            rejected.append(
                EditRejection(
                    line_id=line_id, op="replace_span", reason=reason or R_ANCHOR_RANGE
                )
            )
            continue
        # E4 — per-op growth ratio (span-only).
        span_len = rng.end - rng.start
        if len(sp.text) > guard.edit_span_max_growth_ratio * max(1, span_len):
            rejected.append(
                EditRejection(line_id=line_id, op="replace_span", reason=R_DRIFT_RATIO)
            )
            continue
        normalized.append((rng, sp.text, sp))

    if not normalized:
        return None

    # E2 — no overlap between accepted spans (ascending by start, then end
    # so a zero-length insertion at p sorts before a replacement at p).
    normalized.sort(key=lambda t: (t[0].start, t[0].end))
    accepted: list[tuple[RangeAnchor, str]] = []
    changed_chars = 0
    prev_start = -1
    prev_end = -1
    for rng, text, _sp in normalized:
        # A replacement whose interval crosses into the previous span
        # overlaps. A zero-length insertion at the SAME start offset as an
        # already-accepted op is equally illegal: it shares a position with
        # that op, and _apply_spans (right-to-left, stable on equal starts)
        # would apply the two in an ambiguous order — the insertion could
        # land inside the replacement's original range, leaving a character
        # the replacement was meant to remove. Co-located ops (equal start)
        # are therefore rejected regardless of length.
        if rng.start < prev_end or rng.start == prev_start:
            rejected.append(
                EditRejection(line_id=line_id, op="replace_span", reason=R_OVERLAP)
            )
            continue
        accepted.append((rng, text))
        # Count the characters the op actually changes, not the
        # length delta (see _changed_chars).
        changed_chars += _changed_chars(canonical[rng.start : rng.end], text)
        prev_start = rng.start
        prev_end = rng.end

    if not accepted:
        return None

    # E4 — per-line changed-character budget (span-only).
    if changed_chars > guard.edit_line_max_changed_chars:
        rejected.append(
            EditRejection(line_id=line_id, op="replace_span", reason=R_DRIFT_BUDGET)
        )
        return None

    result = _apply_spans(canonical, accepted)

    # E3 — the resulting line must not be empty after strip.
    if result.strip() == "":
        rejected.append(
            EditRejection(line_id=line_id, op="replace_span", reason=R_EMPTY)
        )
        return None
    reason = _e5_refusal(role, canonical, result, accepted)
    if reason is not None:
        rejected.append(
            EditRejection(line_id=line_id, op="replace_span", reason=reason)
        )
        return None
    return result


def _e1_refusal(
    line_id: str,
    canonical_by_id: dict[str, str],
    chunk_line_ids: set[str] | None,
) -> str | None:
    """`E1` — why this line may not be edited, or ``None`` if it may.

    Two failures, reported apart because they are opposite accusations. An id
    nobody knows is a producer **inventing** a line. A known id outside the
    target set is a producer answering about a line it was only **shown for
    context** — and that one is the common case, because a payload does not
    mark which of its lines are targets, so a model handed a window corrects
    the whole window.

    Until 2026-08-19 the second was unreachable: the caller passed every
    chunk line as ``chunk_line_ids``, so "outside the set" could only be true
    where "unknown" already was, and a context edit was instead dropped
    silently by target filtering much further downstream. Same corrected
    text either way — the difference is that one of them tells the operator
    it happened, now that ``CorrectionReport.edit_rejections`` exists to
    carry it.
    """
    if line_id not in canonical_by_id:
        return R_UNKNOWN_LINE
    if chunk_line_ids is not None and line_id not in chunk_line_ids:
        return R_CONTEXT_LINE
    return None


def apply_edit_script(
    script: EditScript,
    canonical_by_id: dict[str, str],
    *,
    chunk_line_ids: set[str] | None = None,
    guard_config: GuardConfig = DEFAULT_GUARD_CONFIG,
    line_by_id: dict[str, LineManifest] | None = None,
    page_id: str | None = None,
) -> EditResult:
    """Apply an ``EditScript`` and return per-line corrected text + rejections.

    ``chunk_line_ids`` (E1) bounds which lines may be edited; an op for a
    line outside it — or with no known canonical text — is rejected.
    ``line_by_id`` supplies hyphen roles for E5; when absent, lines are
    treated as role NONE (E5 is a no-op). E6 (the three-stage guard matrix)
    is NOT run here — the pipeline applies it afterwards to the resulting
    line text, identically for ``replace_line`` and ``replace_span``.

    ``page_id`` scopes replay to one page of a
    multi-file script: ops stamped with a DIFFERENT page_id are silently
    out of scope (not rejections — they belong to another file), so a
    consumer can replay the whole final edit_script one page at a time
    even when files reuse line_ids. Ops without a stamp are always in
    scope (hand-written scripts keep their historical behaviour).

    Preconditions: a script stamped with an unknown
    ``protocol_version`` raises :class:`~saknussemm.errors.ProposalValidationError`
    — an incompatible script must fail loudly, not half-apply. A line
    whose recorded source :func:`line_digest` differs from the document
    at hand has its ops REJECTED (``precondition_source_digest``): the
    same line_id over different content is a lookalike, never a target.
    """
    if (
        script.protocol_version is not None
        and script.protocol_version != EDIT_PROTOCOL_VERSION
    ):
        raise ProposalValidationError(
            f"edit script speaks protocol version "
            f"{script.protocol_version!r}; this library speaks "
            f"{EDIT_PROTOCOL_VERSION!r} — refusing to apply a script whose "
            "semantics may have changed."
        )

    result = EditResult()

    # Precondition index, page-scoped exactly like the ops are.
    digest_by_line: dict[str, str] = {
        pc.line_id: pc.digest
        for pc in script.preconditions
        if not (
            page_id is not None and pc.page_id is not None and pc.page_id != page_id
        )
    }

    ops_by_line: dict[str, list[ReplaceLine | ReplaceSpan]] = {}
    for op in script.ops:
        if page_id is not None and op.page_id is not None and op.page_id != page_id:
            continue
        ops_by_line.setdefault(op.line_id, []).append(op)

    for line_id, ops in ops_by_line.items():
        reason = _e1_refusal(line_id, canonical_by_id, chunk_line_ids)
        if reason is not None:
            for op in ops:
                result.rejected.append(
                    EditRejection(line_id=line_id, op=op.op, reason=reason)
                )
            continue

        canonical = canonical_by_id[line_id]

        # The document at hand must carry the SAME source text
        # the ops were computed against; same id + different content is
        # a lookalike, never a target.
        expected = digest_by_line.get(line_id)
        if expected is not None and line_digest(canonical) != expected:
            for op in ops:
                result.rejected.append(
                    EditRejection(
                        line_id=line_id,
                        op=op.op,
                        reason=R_PRECONDITION,
                        detail=(
                            f"source digest {line_digest(canonical)} != "
                            f"recorded {expected}"
                        ),
                    )
                )
            continue
        role = (
            line_by_id[line_id].hyphen_role
            if line_by_id and line_id in line_by_id
            else HyphenRole.NONE
        )
        new_text = _apply_line_ops(
            line_id, ops, canonical, role, guard_config, result.rejected
        )
        if new_text is not None:
            result.text_by_id[line_id] = new_text

    return result


def replace_line_script(text_by_id: dict[str, str]) -> EditScript:
    """Re-express a whole-line correction map as a ``replace_line`` EditScript.

    This is the bridge that lets the historical LLM response flow through
    the protocol unchanged: ``apply_edit_script(replace_line_script(m), …)``
    reproduces ``m`` for every non-empty, newline-free entry.
    """
    return EditScript(
        ops=[ReplaceLine(line_id=lid, text=t) for lid, t in text_by_id.items()]
    )


__all__ = [
    "EDIT_PROTOCOL_VERSION",
    "RangeAnchor",
    "MatchAnchor",
    "ReplaceLine",
    "ReplaceSpan",
    "EditOp",
    "EditScript",
    "EditRejection",
    "EditResult",
    "LinePrecondition",
    "line_digest",
    "normalize_anchor",
    "apply_edit_script",
    "replace_line_script",
]
