"""Token-to-token alignment between a source line and its correction.

the shared component: the same alignment serves
(1) faithful projection in the rewriters' slow path (recycle a word's
identity onto the word it actually corresponds to, never onto whatever
happens to sit at the same position), (2) per-token confidence scoring,
and (3) the future ``token_realign`` loss policy.

Pure stdlib, no dependency: character-level Levenshtein similarity
between tokens drives a dynamic-programming alignment over the two
token sequences. Monotonic by construction (an alignment never crosses);
a suspected word MOVE — a token the alignment could not settle that has
a near-identical counterpart elsewhere — is *flagged*, never acted on:
deciding what to do with a reordering belongs to policies, not here.

Costs: gap (insertion/deletion) = 1.0, substitution = 2 × (1 − sim).
A substitution is therefore chosen over a gap pair only when the tokens
share at least one character of similarity (sim > 0); two tokens with
nothing in common fall to deletion + insertion instead of fabricating a
correspondence — identity must never ride a zero-evidence match.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

#: A deleted/weakly-matched token whose near-identical twin (≥ this
#: similarity) appears elsewhere in the target flags the alignment as a
#: suspected move.
_MOVE_SIMILARITY = 0.8

#: Below this similarity a DP match is considered "weak" — kept in the
#: alignment (it is still the best monotonic reading) but eligible as a
#: move suspect.
_WEAK_MATCH = 0.5


def word_boundary_moved(originals: list[str], words: list[str]) -> bool:
    """Whether equal-count positional pairing would misplace word geometry.

    The same letters with different token boundaries prove a move, e.g.
    ``au jourdhui`` -> ``aujourd hui``. A large change in an individual
    word's length also declines the fast path: half its old length, with
    a floor of one character, leaves ordinary OCR substitutions alone.
    Both format rewriters and the loss-policy gate use this same rule.
    """
    if originals == words:
        return False
    if "".join(originals) == "".join(words):
        return True
    return any(
        abs(len(word) - len(original)) > max(1, len(original) // 2)
        for original, word in zip(originals, words)
    )


def char_similarity(a: str, b: str) -> float:
    """Character-level similarity in [0, 1]: 1 − levenshtein/max_len.

    ``1.0`` for identical tokens (including two empty strings), ``0.0``
    for tokens sharing nothing.
    """
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    # Classic two-row Levenshtein — tokens are words, lengths are tiny.
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(
                min(
                    previous[j] + 1,  # deletion
                    current[j - 1] + 1,  # insertion
                    previous[j - 1] + (0 if ca == cb else 1),  # substitution
                )
            )
        previous = current
    return 1.0 - previous[-1] / max(len(a), len(b))


@dataclass(frozen=True)
class AlignedPair:
    """One correspondence in the alignment.

    ``source_index is None`` → the target token is an INSERTION;
    ``target_index is None`` → the source token is a DELETION;
    both set → a match, with the pair's character similarity.
    """

    source_index: int | None
    target_index: int | None
    similarity: float


@dataclass(frozen=True)
class TokenAlignment:
    """The full alignment of one line's source tokens onto its correction."""

    pairs: tuple[AlignedPair, ...]
    #: Aggregate in [0, 1]: sum of matched similarities over
    #: ``max(len(source), len(target))`` — 1.0 means identical sequences.
    score: float
    #: Heuristic flag: some token the alignment could not settle has a
    #: near-identical counterpart elsewhere — the correction *may* have
    #: reordered words. A flag to surface, never a licence to reorder.
    move_suspected: bool
    #: The optimal path touched the edge of the search band, so the true
    #: alignment may lie outside the corridor that was searched — the
    #: alignment below it is the best DIAGONAL reading, not necessarily the
    #: best reading.
    #:
    #: Always ``False`` for an unbanded call, which searches everything.
    #:
    #: **It says where the search went, not whether the reading is good** —
    #: and the difference is measured, not assumed. A block transposition of
    #: tokens sharing no character trips it; the SAME transposition of
    #: `w0`…`w59` does not, because a mediocre diagonal match (2 × 0.33)
    #: costs less than a deletion paired with an insertion (2.0), so the path
    #: never needs to leave. Nor does a large deletion: the corridor widens
    #: to the length difference, since a narrower one has no corner-to-corner
    #: path at all.
    #:
    #: So this is NOT the guard against a model that reordered or dropped a
    #: passage. Those are visible elsewhere — a dropped chunk as a run of
    #: deletions in :attr:`pairs`, a shifted line as a collapse of
    #: `min_source_similarity` on every line after it. Building a page-scale
    #: guard on this flag alone would give one that is quiet exactly when it
    #: matters. Refuse on it; never widen the band until it goes quiet.
    band_exhausted: bool = False
    #: Lazily built by :meth:`source_for_target`. Not part of the value:
    #: excluded from equality and repr so two alignments compare on what they
    #: SAY, never on whether one of them has been read back yet.
    _by_target: dict[int, int | None] | None = field(
        default=None, compare=False, repr=False
    )

    def source_for_target(self, target_index: int) -> int | None:
        """The source token index matched to ``target_index`` (None =
        the target token is an insertion).

        Indexed on first use rather than scanned. The scan was linear in the
        pairs and its only caller asks once per target token, so reading a
        whole alignment back cost O(len(pairs)²) — a second quadratic sitting
        on top of the DP's, and invisible because at one line's scale both
        are instant.
        """
        index = self._by_target
        if index is None:
            index = {
                pair.target_index: pair.source_index
                for pair in self.pairs
                if pair.target_index is not None
            }
            object.__setattr__(self, "_by_target", index)
        return index.get(target_index)


def _banded_range(i: int, n: int, m: int, band: int) -> tuple[int, int]:
    """Columns reachable from row ``i`` under ``band``, as ``[lo, hi)``.

    The diagonal is not ``j == i`` when the sequences differ in length: a
    correction that adds three words shifts every later token by three, and a
    band centred on ``j == i`` would push the true path off its own edge
    before the end. Centring on the interpolated diagonal keeps the band
    around where the answer actually lies.
    """
    centre = i if n == m else round(i * m / n) if n else 0
    return max(0, centre - band), min(m, centre + band + 1)


def _fill_cost_band(
    source: list[str],
    target: list[str],
    effective: int,
    gap: float,
    similarity: Callable[[str, str], float],
) -> tuple[list[list[float]], list[int], list[int]]:
    """The banded DP table, as ``(cost, lo, hi)``.

    One row per source token, holding only the corridor's columns; ``lo[i]``
    is a row's first real column, and each row is padded by one on either
    side so the neighbours a cell reads are computed rather than absent.

    Written with the row lists hoisted and the offsets inlined, not behind
    get/put helpers. Measured on a real page: the helper version spent ~33 µs
    per cell, four Python calls per cell being all of it. Same algorithm.
    """
    n, m = len(source), len(target)
    inf = float("inf")
    lo: list[int] = []
    hi: list[int] = []
    cost: list[list[float]] = []
    for i in range(n + 1):
        # Padded by one on each side so a cell's neighbours are computed
        # rather than absent; the corridor itself is `_banded_range`.
        row_lo, row_hi = _banded_range(i, n, m, effective)
        row_lo, row_hi = max(0, row_lo - 1), min(m + 1, row_hi + 1)
        lo.append(row_lo)
        hi.append(row_hi)
        cost.append([inf] * (row_hi - row_lo))

    row0, off0 = cost[0], lo[0]
    for j in range(off0, hi[0]):
        row0[j - off0] = j * gap
    for i in range(1, n + 1):
        row, off, upper = cost[i], lo[i], hi[i]
        prev, prev_off, prev_hi = cost[i - 1], lo[i - 1], hi[i - 1]
        token = source[i - 1]
        for j in range(off, upper):
            if j == 0:
                row[0 - off] = i * gap
                continue
            best = inf
            if prev_off <= j < prev_hi:
                best = prev[j - prev_off] + gap
            if off <= j - 1 < upper:
                left = row[j - 1 - off] + gap
                if left < best:
                    best = left
            if prev_off <= j - 1 < prev_hi:
                diag = prev[j - 1 - prev_off]
                if diag != inf:
                    diag += 2.0 * (1.0 - similarity(token, target[j - 1]))
                    if diag < best:
                        best = diag
            row[j - off] = best
    return cost, lo, hi


def _suspect_move(
    pairs: list[AlignedPair],
    source: list[str],
    target: list[str],
    effective: int,
    similarity: Callable[[str, str], float],
) -> bool:
    """Whether some unsettled token has a near-identical twin elsewhere.

    Scanned inside the corridor only: outside it there is no alignment to be
    suspicious of, and ``band_exhausted`` already says the reading is not to
    be trusted. Unbanded, the corridor is everything and this is the same
    scan it always was.
    """
    n, m = len(source), len(target)
    for pair in pairs:
        src = pair.source_index
        if src is None:
            continue
        if pair.target_index is not None and pair.similarity >= _WEAK_MATCH:
            continue  # confidently settled
        scan_lo, scan_hi = _banded_range(src + 1, n, m, effective)
        for j2 in range(max(0, scan_lo), min(m, scan_hi)):
            if j2 != pair.target_index and (
                similarity(source[src], target[j2]) >= _MOVE_SIMILARITY
            ):
                return True
    return False


def align_tokens(
    source: list[str],
    target: list[str],
    *,
    band: int | None = None,
    similarity: Callable[[str, str], float] = char_similarity,
) -> TokenAlignment:
    """Align ``source`` tokens onto ``target`` tokens (both in reading order).

    Deterministic. ``band=None`` computes the exact alignment and costs
    O(len(source) × len(target)); a band restricts the search to a diagonal
    corridor and costs O(len(source) × band).

    **Why a band exists at all.** One line's tokens are a handful, and the
    exact alignment is instant. A whole PAGE is not: 8 620 tokens is
    74 million cells, which is minutes of Python and gigabytes of it — the
    cost model in this docstring used to say ``O(n × m) token pairs`` and let
    the reader assume that meant time. Measured, before the band existed:
    0.005 s at 50 tokens, 0.095 s at 200, 1.83 s at 800, **14.25 s at
    2 000**, with the similarity matrix alone reaching 128 MB at 2 000².

    A band is sound here for a reason specific to this problem: a corrected
    text is the source text with words fixed, so the alignment is almost
    diagonal by construction. When the true path needs an excursion the
    corridor forbids, that is reported rather than silently approximated —
    see :attr:`TokenAlignment.band_exhausted`, and read what it does and does
    not detect there before treating it as a guard. **A band never invents a
    correspondence; it declines to look far from the diagonal and says so.**

    The similarity of two tokens is computed where it is used and not kept:
    materialising it was the larger of the two costs and bought nothing, since
    the DP reads each pair exactly once.
    """
    n, m = len(source), len(target)
    gap = 1.0
    inf = float("inf")
    # A band narrower than the length difference has NO path from corner to
    # corner: the answer would not merely be approximate, it would not exist.
    effective = max(band, abs(n - m)) if band is not None else max(n, m)
    cost, lo, hi = _fill_cost_band(source, target, effective, gap, similarity)

    def get(i: int, j: int) -> float:
        """One cell, everything outside the corridor being unreachable. Used
        by the backtrack, which walks n + m cells — never by the DP, where
        the same convenience cost 33 µs a cell."""
        if j < lo[i] or j >= hi[i]:
            return inf
        return cost[i][j - lo[i]]

    # Backtrack (prefer match > deletion > insertion on exact ties, but a
    # zero-similarity "match" costs exactly gap+gap and must NOT win: a
    # correspondence needs evidence).
    pairs: list[AlignedPair] = []
    band_exhausted = False
    i, j = n, m
    while i > 0 or j > 0:
        # Touching the corridor's edge means the true path may lie outside it.
        # Reported, never repaired: a caller that cares refuses the alignment.
        if band is not None and (j <= lo[i] or j >= hi[i] - 1) and 0 < j < m:
            band_exhausted = True
        if i > 0 and j > 0:
            pair_similarity = similarity(source[i - 1], target[j - 1])
            sub = get(i - 1, j - 1) + 2.0 * (1.0 - pair_similarity)
            if abs(get(i, j) - sub) < 1e-9 and pair_similarity > 0.0:
                pairs.append(AlignedPair(i - 1, j - 1, pair_similarity))
                i, j = i - 1, j - 1
                continue
        if i > 0 and abs(get(i, j) - (get(i - 1, j) + gap)) < 1e-9:
            pairs.append(AlignedPair(i - 1, None, 0.0))
            i -= 1
            continue
        pairs.append(AlignedPair(None, j - 1, 0.0))
        j -= 1
    pairs.reverse()

    matched = [
        p for p in pairs if p.source_index is not None and p.target_index is not None
    ]
    denominator = max(n, m, 1)
    score = sum(p.similarity for p in matched) / denominator

    return TokenAlignment(
        pairs=tuple(pairs),
        score=score,
        move_suspected=_suspect_move(pairs, source, target, effective, similarity),
        band_exhausted=band_exhausted,
    )


__all__ = ["AlignedPair", "TokenAlignment", "align_tokens", "char_similarity"]
