"""Stage-C line-level text-migration guards (spec §7 stage C).

The LLM occasionally tries to move text between OCR lines — completing a
hyphenated word into PART1, absorbing a neighbour into a line, or dropping
PART2 because it "looks redundant". The pipeline guards against this in
THREE stages, each living beside the control flow that acts on it — there
is no single "guards" module, and this docstring is the map of where each
stage lives rather than a claim to own them all:

  +----------+----------------------+------------------+-------------------+
  | Stage    | Home                 | Scope            | Action on hit     |
  +----------+----------------------+------------------+-------------------+
  | A.       | validator.py         | Hyphen pair      | Raise             |
  | Validate | _check_pair_drift    | (PART1+PART2)    | HyphenIntegrity-  |
  | (pre-    |                      | word counts      | Error → retry at  |
  |  retry)  |                      |                  | temp 0.0          |
  +----------+----------------------+------------------+-------------------+
  | B.       | hyphenation.py       | Hyphen pair      | Fall back to OCR  |
  | Recon-   | _part1_text_migrated | word counts +    | for both sides;   |
  | cile     | _part2_text_migrated | char-length +    | neutralise        |
  |          | _part2_boundary_*    | boundary word    | SUBS_CONTENT      |
  +----------+----------------------+------------------+-------------------+
  | C.       | guards.py (HERE)     | Single line vs.  | Fall back to OCR  |
  | Accept   | check_line           | source +         | for that line;    |
  | (post-   | check_adjacent_*     | neighbours       | capture rejection |
  |  recon-  |                      | (SequenceMatcher)| reason            |
  +----------+----------------------+------------------+-------------------+

The thresholds intentionally differ and tune TOGETHER (all read from
``GuardConfig``): tightening one stage without the others can leak
migrations through the gap.

  - Stage A carries the *most aggressive remedy* — a hyphen drift is
    suspicious enough to retry the whole chunk before any fallback. Its
    numeric thresholds are deliberately MORE permissive than Stage B's
    (PART1 growth: 2 words at A vs 1 at B — see ``GuardConfig``): a cheap
    retry only fires on gross drift, then the strict Stage B bound decides
    what actually survives reconciliation ("strict" describes the
    remedy, not the thresholds).
  - Stage B catches drift the LLM produced despite the retry; the fallback
    preserves the OCR pair atomically. Its predicates live in
    ``hyphenation.py`` beside their sole caller (``reconcile_hyphen_pair``).
  - Stage C is a *line-level* safety net (this module) that fires
    regardless of hyphen role: it catches absorption / neighbour migration
    the pair-level guards can't see.

Each stage lives with its remedy on purpose: Stage A's raise belongs to
``HyphenIntegrityError``'s home (validator.py), Stage B's predicates to the
reconciliation flow (hyphenation.py), Stage C's decision here. Forcing them
into one file would only re-introduce the cross-module imports Stage B had
until it was moved to its caller.
"""

from __future__ import annotations

from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import TypeVar

from saknussemm.core._norm import ncfold
from saknussemm.core.schemas import (
    DEFAULT_GUARD_CONFIG,
    GuardConfig,
    ProposalFeatures,
)

#: Line key type for :func:`check_adjacent_duplicates` — any hashable
#: identifier (a bare page-scoped line_id, or a LineRef for the
#: document-wide pass). The guard never interprets the key.
K = TypeVar("K", bound=Hashable)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class AcceptanceResult:
    """Result of the acceptance check for a single line."""

    accepted: bool
    text: str  # retained text (correction or OCR fallback)
    reason: str | None = None  # None when accepted; short tag when rejected
    #: The metrics this check computed while deciding, recorded
    #: once so no consumer re-derives them (report v2's decision stage).
    features: ProposalFeatures | None = None


# ---------------------------------------------------------------------------
# Similarity helper
# ---------------------------------------------------------------------------


def _similarity(a: str, b: str) -> float:
    """Return SequenceMatcher ratio between two strings (0.0–1.0).

    ``autojunk=False`` because the default is a heuristic for comparing
    *files*, where an element is a whole line and a line repeated throughout
    really is noise. Here an element is a character, so past difflib's
    200-element threshold the space and the common letters are all "popular"
    enough to be junked and can no longer anchor a match — on a repetitive
    line, a correction of 8 characters in 215 scored 0.08 where the ratio
    cannot arithmetically be below 0.96, and was refused as
    ``too_different_from_source``. Measured over 27108 pairs from every real
    corpus here: turning it off changes no ratio and costs 0.7%.

    With it off, ``ratio()`` is symmetric, so the operand order — guard 3
    passes the correction first, guards 1 and 2 pass it second — can no
    longer make the two measure different things.
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _is_twin(source_ocr: str, candidate: str, config: GuardConfig) -> bool:
    """Whether ``candidate``'s source is a twin of this line's source.

    Twins are exempt from the neighbour margin: the margin asks the
    correction to resemble its own source MORE than any other line's, and
    when two sources are (near-)identical that can never hold — yet a
    mis-attachment between them changes nothing, since the texts are the
    same. Off unless ``attachment_twin_similarity`` is set.
    """
    threshold = config.attachment_twin_similarity
    return threshold is not None and _similarity(source_ocr, candidate) >= threshold


def _closer_to_another_line(
    source_ocr: str,
    corrected: str,
    sim_source: float,
    *,
    prev_ocr: str | None,
    next_ocr: str | None,
    other_ocr: Sequence[str],
    features: ProposalFeatures,
    config: GuardConfig,
) -> AcceptanceResult | None:
    """Guard 2 — the rejection when the correction is another line's text.

    A mis-attached correction carries ANOTHER line's text, so it resembles
    that line more than its own source, by more than the margin. The two
    neighbours are the historical candidates and keep their own reason
    codes and recorded similarities; ``other_ocr`` widens the set to the
    page when the caller asks (``attachment_scope="page"``): a dropped or
    split line shifts every line after it, and a model shown a column reads
    across it, so the other line is often several lines away. Twins are
    exempt (:func:`_is_twin`). ``None`` when nothing fires.
    """
    limit = sim_source + config.neighbour_margin
    if prev_ocr is not None:
        sim_prev = _similarity(prev_ocr, corrected)
        features.prev_similarity = round(sim_prev, 4)
        if sim_prev > limit and not _is_twin(source_ocr, prev_ocr, config):
            return AcceptanceResult(
                accepted=False,
                text=source_ocr,
                reason="closer_to_previous_line",
                features=features,
            )
    if next_ocr is not None:
        sim_next = _similarity(next_ocr, corrected)
        features.next_similarity = round(sim_next, 4)
        if sim_next > limit and not _is_twin(source_ocr, next_ocr, config):
            return AcceptanceResult(
                accepted=False,
                text=source_ocr,
                reason="closer_to_next_line",
                features=features,
            )
    for other in other_ocr:
        if _similarity(other, corrected) > limit and not _is_twin(
            source_ocr, other, config
        ):
            return AcceptanceResult(
                accepted=False,
                text=source_ocr,
                reason="closer_to_another_line",
                features=features,
            )
    return None


def _absorbs_a_neighbour(
    source_ocr: str,
    corrected: str,
    *,
    prev_ocr: str | None,
    next_ocr: str | None,
    features: ProposalFeatures,
    config: GuardConfig,
) -> AcceptanceResult | None:
    """Guard 3 — the correction is the source and a neighbour concatenated.

    ``None`` when nothing fires.
    """
    src_len = max(len(source_ocr), 1)
    if len(corrected) <= src_len * config.absorption_length_ratio:
        return None
    if next_ocr and (
        _similarity(corrected, f"{source_ocr} {next_ocr}")
        > config.absorption_concat_similarity
    ):
        return AcceptanceResult(
            accepted=False,
            text=source_ocr,
            reason="absorbs_next_line",
            features=features,
        )
    if prev_ocr and (
        _similarity(corrected, f"{prev_ocr} {source_ocr}")
        > config.absorption_concat_similarity
    ):
        return AcceptanceResult(
            accepted=False,
            text=source_ocr,
            reason="absorbs_previous_line",
            features=features,
        )
    return None


def check_line(
    source_ocr: str,
    corrected: str,
    prev_ocr: str | None = None,
    next_ocr: str | None = None,
    *,
    other_ocr: Sequence[str] = (),
    config: GuardConfig = DEFAULT_GUARD_CONFIG,
    absorption: bool = True,
) -> AcceptanceResult:
    """Decide whether *corrected* is safe to accept for *source_ocr*.

    Parameters
    ----------
    source_ocr : str
        Original OCR text for this line.
    corrected : str
        LLM-proposed correction.
    prev_ocr : str | None
        OCR text of the previous line (if available).
    next_ocr : str | None
        OCR text of the next line (if available).
    other_ocr : Sequence[str]
        OCR text of every OTHER line the margin is held against beyond the
        two neighbours — the rest of the page under
        ``GuardConfig.attachment_scope="page"``. Empty (the default) keeps
        the historical two-neighbour check. The caller decides the scope;
        this function only knows the texts.
    absorption : bool
        Run guard 3 (the correction is source + neighbour concatenated).
        ``False`` for a reconciled hyphen member: stage B already ruled on
        the pair's word split, and a fragment that legitimately completes
        its partner's word would look like an absorption here. Guards 1
        and 2 — the floor and the neighbour margin — always run: a pair
        member can carry ANOTHER line's text as easily as a lone line
        (VR-11), and stage B cannot see that.

    Returns
    -------
    AcceptanceResult
        .accepted = True and .text = corrected  when safe;
        .accepted = False and .text = source_ocr when rejected.
    """
    # Identity: no change, always accept
    if corrected == source_ocr:
        return AcceptanceResult(
            accepted=True,
            text=corrected,
            features=ProposalFeatures(source_similarity=1.0, length_ratio=1.0),
        )

    # Every ratio this check computes is recorded ONCE on the
    # result (fields the taken path never computed stay None).
    src_len = max(len(source_ocr), 1)
    features = ProposalFeatures(length_ratio=round(len(corrected) / src_len, 4))

    # --- Guard 1: source similarity ---
    sim_source = _similarity(source_ocr, corrected)
    features.source_similarity = round(sim_source, 4)
    if sim_source < config.min_source_similarity:
        return AcceptanceResult(
            accepted=False,
            text=source_ocr,
            reason="too_different_from_source",
            features=features,
        )

    # --- Guard 2: neighbour proximity ---
    migrated = _closer_to_another_line(
        source_ocr,
        corrected,
        sim_source,
        prev_ocr=prev_ocr,
        next_ocr=next_ocr,
        other_ocr=other_ocr,
        features=features,
        config=config,
    )
    if migrated is not None:
        return migrated

    # --- Guard 3: absorption of adjacent line ---
    if absorption:
        absorbed = _absorbs_a_neighbour(
            source_ocr,
            corrected,
            prev_ocr=prev_ocr,
            next_ocr=next_ocr,
            features=features,
            config=config,
        )
        if absorbed is not None:
            return absorbed
    return AcceptanceResult(accepted=True, text=corrected, features=features)


def check_adjacent_duplicates(
    lines: list[tuple[K, str, str]],
    *,
    config: GuardConfig = DEFAULT_GUARD_CONFIG,
) -> dict[K, str]:
    """Detect adjacent duplicate corrections.

    Parameters
    ----------
    lines : list of (line_key, source_ocr, corrected_text)
        Ordered list of adjacent lines, already individually accepted.
        The key is opaque — bare line_ids for a page-scoped caller,
        LineRefs for the document-wide pass.

    Returns
    -------
    dict mapping line_key → fallback_reason for lines that should revert.
    Both lines of a duplicate pair are reverted.
    """
    revert: dict[K, str] = {}
    for i in range(len(lines) - 1):
        id_a, src_a, cor_a = lines[i]
        id_b, src_b, cor_b = lines[i + 1]

        # Skip only if the RIGHT line is already flagged (nothing new to
        # decide). When only the left line is already flagged we must still
        # evaluate the right one against it — otherwise a run of three or
        # more identical corrections leaves its third line unreverted
        # (i=0 flags lines 0,1; i=1 would `continue` on the flagged line 1
        # and never test line 2).
        if id_b in revert:
            continue

        # Corrections must be very similar
        sim_corrected = _similarity(cor_a, cor_b)
        if sim_corrected < config.duplicate_threshold:
            continue

        # Sources must be clearly different (otherwise the duplication is genuine)
        sim_sources = _similarity(src_a, src_b)
        if sim_sources >= config.duplicate_source_min_diff:
            continue

        # Flag both lines
        revert[id_a] = "adjacent_duplicate_detected"
        revert[id_b] = "adjacent_duplicate_detected"

    return revert


def _word_migrated_across_seam(
    cor_word: str,
    own_src: str,
    neighbour: str,
    *,
    neighbour_first: bool,
    config: GuardConfig,
) -> bool:
    """True if *cor_word* is better explained by its own source joined with
    the *neighbour* boundary word than by *own_src* alone — i.e. the word
    absorbed material across the seam.

    ``neighbour_first`` places the neighbour on the correct side in reading
    order: for a line's LAST word the neighbour (next line's head) comes
    AFTER; for a line's FIRST word the neighbour (previous line's tail) comes
    BEFORE. Keys on the boundary tokens only, so the mangled break glyph the
    neighbour carries (``re«``, ``absolu*``) is irrelevant: ``SequenceMatcher``
    scores ``"re" + "tentlssent,"`` against ``"retentissent,"`` on shared
    characters and the junk washes out. Reuses the Stage-C absorption knobs —
    the same phenomenon the line-level Guard 3 models, at word granularity —
    so no new threshold is introduced.
    """
    if not cor_word or not own_src or not neighbour:
        return False
    if cor_word == own_src:
        return False  # word untouched → nothing crossed the seam
    joined = (neighbour + own_src) if neighbour_first else (own_src + neighbour)
    sim_joined = _similarity(cor_word, joined)
    if sim_joined <= config.absorption_concat_similarity:
        return False
    return sim_joined > _similarity(cor_word, own_src) + config.neighbour_margin


def _whole_word_crossed_the_seam(
    wa_src: list[str],
    wa_cor: list[str],
    wb_src: list[str],
    wb_cor: list[str],
) -> bool:
    """A whole word appeared on one side of the seam and left the other.

    :func:`_word_migrated_across_seam` models a word being **completed**
    across the seam — fragment plus fragment, judged by similarity to the
    concatenation. It cannot see a word being **moved** intact, because a
    moved word does not resemble ``own_src + neighbour``. Measured
    2026-08-17: with ``attendre`` gaining ``longtemps`` and line B losing
    it, ``sim("longtemps", "attendrelongtemps")`` is 0.69, below the 0.8
    threshold, so the guard returns False. Both lines were reported
    ``corrected``, ``fallback_lines`` was 0, and the invariant this
    repository states most often — *no text migrates between physical
    lines* — was violated in silence.

    The rule here requires **both halves of the move**: the word appears
    where it was not, *and* it is gone from where it was. Requiring only
    the appearance would flag a real typographic repetition — line A's last
    word legitimately corrected into the same word line B starts with,
    which happens with short function words — as a migration. Requiring the
    disappearance too costs nothing and removes that class: if B still
    starts with its own word, nothing moved.
    """
    if not (wa_cor and wb_cor):
        return False
    a_last_src, a_last_cor = ncfold(wa_src[-1]), ncfold(wa_cor[-1])
    b_first_src, b_first_cor = ncfold(wb_src[0]), ncfold(wb_cor[0])
    # Forward: A now ends with B's word, and B no longer begins with it.
    if (
        a_last_cor == b_first_src
        and a_last_cor != a_last_src
        and b_first_cor != b_first_src
    ):
        return True
    # Backward: B now begins with A's word, and A no longer ends with it.
    return (
        b_first_cor == a_last_src
        and b_first_cor != b_first_src
        and a_last_cor != a_last_src
    )


def check_boundary_migration(
    lines: list[tuple[K, str, str]],
    *,
    config: GuardConfig = DEFAULT_GUARD_CONFIG,
) -> dict[K, str]:
    """Detect a word migrating across a physical line seam.

    The pair-level guards (Stage A/B) only fire on lines the parser paired
    as a hyphen unit. When the OCR mangles the end-of-line hyphen into a
    non-``-`` glyph, the line is never paired and the LLM can complete the
    broken word by pulling its continuation up from the next line (or push a
    fragment down). The invariant — *no text migrates between physical
    lines* — must hold regardless of hyphen role, so this Stage-C pass keys
    on the boundary tokens, not on detection.

    Parameters
    ----------
    lines : list of (line_key, source_ocr, corrected_text)
        Ordered adjacent lines, already individually accepted. Same shape
        and ordering contract as :func:`check_adjacent_duplicates`: the
        caller breaks the list at source-file transitions so no seam
        straddles two documents.

    Returns
    -------
    dict mapping line_key → fallback_reason. Both lines of a migrating seam
    are reverted, mirroring Stage B's "if either side migrated, BOTH sides
    fall back" rule — reverting only the absorbing side would turn the
    duplication into a hole on the other side.
    """
    revert: dict[K, str] = {}
    for i in range(len(lines) - 1):
        id_a, src_a, cor_a = lines[i]
        id_b, src_b, cor_b = lines[i + 1]

        wa_src, wa_cor = src_a.split(), cor_a.split()
        wb_src, wb_cor = src_b.split(), cor_b.split()
        if not wa_src or not wb_src:
            continue

        # Forward: A's last word pulled B's first word up (neighbour after).
        forward = bool(wa_cor) and _word_migrated_across_seam(
            wa_cor[-1], wa_src[-1], wb_src[0], neighbour_first=False, config=config
        )
        # Backward: B's first word pulled A's last word down (neighbour before).
        backward = bool(wb_cor) and _word_migrated_across_seam(
            wb_cor[0], wb_src[0], wa_src[-1], neighbour_first=True, config=config
        )

        # A word moved intact, which the concatenation model above cannot
        # see: it resembles neither fragment-plus-fragment nor its own
        # source. Reported as a forward migration — the direction is not
        # observable once the word has landed, and both sides revert either
        # way.
        moved = _whole_word_crossed_the_seam(wa_src, wa_cor, wb_src, wb_cor)

        if forward or backward or moved:
            reason = (
                "boundary_migration_forward"
                if (forward or moved)
                else "boundary_migration_backward"
            )
            revert[id_a] = reason
            revert[id_b] = reason

    return revert


# --- __all__ ---
__all__ = [
    "AcceptanceResult",
    "check_line",
    "check_adjacent_duplicates",
    "check_boundary_migration",
]
