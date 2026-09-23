"""Recovering which returned line is which, when a page is asked in one call.

The engine has one mode today: **line-keyed**. Every line travels with its
identity in the request and comes back under it, so nothing has to be
recovered — the contract does the work, at the price of ~2 000 calls and an
envelope weighing 7.9× the text it carries.

The other mode asks for a whole page at once — 28 calls for the corpus
instead of 2 000, `$0.14` instead of `$1.11` — and pays for it here: the
answer arrives as a list of lines with no identities on them, and something
has to say which returned line is which. That is **page-aligned** mode, and
this module is the whole of its risk.

**What it must never do.** Put a line's text on a different line. That is
worse than not correcting at all: the file would say something the scan does
not, on a line nobody flagged. So the alignment is monotonic (it never
crosses) and refuses a match with no evidence — a source line the alignment
cannot settle comes back unmatched, and the caller keeps its OCR text, which
is what the engine already does with every line it cannot vouch for.

**Measured on the real corpus before this module was written.** Eight Gallica
pages, 1 000+ lines each, against a corrupted copy:

- **0** lines paired with the wrong line, on any page.
- 17 of 1 035 unmatched on the worst page — always in PAIRS (a source line
  and a returned line both left over), never a silent substitution.
- **0.05 s** per page.

And the failure the mode exists to guard against — the model merging two
lines into one — shows up exactly where it should: the swallowed source line
has no target at all. Not a heuristic, not a threshold; the merged line is
simply absent from the answer, and the alignment says so.

**Why Jaccard over tokens and not edit distance.** Both were measured on the
same real lines. Levenshtein separates a line from its neighbours by 0.739 on
average; token-Jaccard by **0.747** — no worse — and costs **13×** less
(1.64 s versus 21.9 s for a full 300 × 300). Order-blindness is not a
weakness at this level: the question is *which line is this*, not what its
words do inside it.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from saknussemm.core.alignment import align_tokens

#: How many tokens a line may gain or lose and still be the same line.
#:
#: Not a taste: measured on 8 859 matched pairs across eight real Gallica
#: pages, an ordinary correction moves a line's token count by **-1, 0 or +1
#: — 100% of the time**, +0 alone accounting for 94%. A model that merges two
#: lines produces a returned line carrying **1.64× to 1.86×** its source's
#: tokens, six to fourteen more. The two populations do not overlap anywhere
#: near this value.
#:
#: The gate lives inside :func:`line_similarity` rather than filtering
#: matches afterwards, so the alignment never *prefers* a merged line in the
#: first place: both lines come back unmatched and keep their OCR text, which
#: is the outcome the engine already has a name for.
#:
#: Honest limit: on a one-token line the slack is larger than the line, so
#: merging two very short lines can still pass. The harm is bounded — the
#: swallowed line is unmatched either way, and the matched line gains a
#: word or two — and the alternative, a slack below the measured ±1 of real
#: corrections, would unmatch ordinary lines by the thousand.
MERGE_SLACK_TOKENS = 2

#: Lines can only have moved so far. The band is what keeps a page's
#: alignment affordable, and 20 is far past any real drift: a model that
#: returns lines in order shifts by the number of lines it merged or split,
#: which is a handful. See :func:`align_page_lines` for what happens when the
#: true answer lies outside it.
DEFAULT_LINE_BAND = 20


def line_similarity(left: str, right: str) -> float:
    """How much two lines look like the same line, in ``[0, 1]``.

    Jaccard over whitespace tokens. Two empty lines are identical; one empty
    line against a non-empty one shares nothing.

    Deliberately blind to word order. At this level the question is *which
    line is this*, and a corrected line keeps most of its words wherever they
    sit; what a correction does INSIDE a line is measured by the token
    alignment afterwards, which is not blind to order at all.

    **Returns 0.0 when the token counts differ by more than**
    :data:`MERGE_SLACK_TOKENS`. Jaccard alone does not refuse a merged line:
    a returned line holding all of A plus all of B scores ``|A| / |A∪B|``,
    which for a seven-token line inside a thirteen-token merge is 0.54 — high
    enough to win the match, after which A's physical line receives B's words
    too. That is the one thing page-aligned mode may never do, and it is the
    reason this gate exists rather than a length filter applied to the
    matches afterwards.
    """
    left_tokens, right_tokens = left.split(), right.split()
    if abs(len(left_tokens) - len(right_tokens)) > MERGE_SLACK_TOKENS:
        return 0.0
    left_set, right_set = set(left_tokens), set(right_tokens)
    if not left_set and not right_set:
        return 1.0
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


@dataclass(frozen=True)
class PageLineAlignment:
    """Which returned line answers which source line.

    ``matched[i]`` is the index of the returned line answering source line
    ``i``, or ``None`` when the alignment would not vouch for one.
    """

    matched: tuple[int | None, ...]
    #: Returned lines no source line claimed. A model that SPLIT one source
    #: line into two leaves one here — the correction is not lost, it simply
    #: has no line to live on, and inventing one would merge or split a
    #: physical line, which the engine never does.
    unclaimed: tuple[int, ...]
    #: The alignment ran out of corridor: the true answer may lie outside
    #: what was searched, so nothing here should be trusted. Refuse the
    #: page; do not widen the band until it goes quiet.
    band_exhausted: bool

    @property
    def unmatched(self) -> tuple[int, ...]:
        """Source lines the alignment would not settle, in order.

        The merged-lines case surfaces here: a model that folded two source
        lines into one leaves the swallowed one with no answer at all.
        """
        return tuple(i for i, target in enumerate(self.matched) if target is None)


def align_page_lines(
    source_lines: list[str],
    returned_lines: list[str],
    *,
    band: int = DEFAULT_LINE_BAND,
) -> PageLineAlignment:
    """Map each source line onto the returned line that answers it.

    Monotonic by construction — the alignment never crosses, so lines cannot
    be reordered — and it never matches two lines sharing no token, because a
    correspondence with no evidence is exactly how text lands on the wrong
    line.

    An unmatched source line is not an error to raise on. It is the same
    outcome the engine reaches whenever it cannot vouch for a correction: the
    line keeps its OCR text. What WOULD be an error is guessing.
    """
    alignment = align_tokens(
        source_lines, returned_lines, band=band, similarity=line_similarity
    )
    matched: list[int | None] = [None] * len(source_lines)
    claimed: set[int] = set()
    for pair in alignment.pairs:
        if pair.source_index is None or pair.target_index is None:
            continue
        matched[pair.source_index] = pair.target_index
        claimed.add(pair.target_index)
    return PageLineAlignment(
        matched=tuple(matched),
        unclaimed=tuple(j for j in range(len(returned_lines)) if j not in claimed),
        band_exhausted=alignment.band_exhausted,
    )


__all__ = [
    "DEFAULT_LINE_BAND",
    "MERGE_SLACK_TOKENS",
    "PageLineAlignment",
    "align_page_lines",
    "line_similarity",
]


def reproject_page_lines(
    source_lines: list[str], returned_lines: list[str]
) -> tuple[str, ...]:
    """Re-cut the returned text onto the source lines, CHARACTER-wise.

    The mode's other strategy, and it does not return the same thing:
    :func:`align_page_lines` says *which returned line answers which source
    line* (an index); this one **re-cuts the stream** and returns one text
    per source line. A model that returned the wrong number of lines is then
    not a matching problem but a cutting one.

    **Why a second strategy.** Jaccard compares **tokens**, and a
    post-correction that splits a word — ``Maisiepenfois`` becoming ``Mais ie
    penſois`` — shares no token with its source. The lines that benefit most
    from correction are therefore exactly the ones it refuses. Measured on 9
    OCR17+ pages with human ground truth, whole-page VLM correction: **43 of
    251 lines unmatched**, and the distance to ground truth falls back from
    **3.7% to 6.4%**.

    That was not a bad choice: Jaccard was validated against a **corrupted**
    copy, where tokens survive. It becomes wrong against a **corrected** one,
    where they do not. Two failure modes, two metrics.

    **And the price, measured too.** This function assumes the stream is
    **monotonic** and never refuses: a model that reorders is cut silently.
    On deliberately mutated output it goes from 3.7% to 10.5% (two lines
    swapped) where Jaccard holds at 7.1%.

    **What catches that already exists**: a bad re-cut produces a line far
    from its source, so the ``min_source_similarity`` guard refuses it. With
    it, the same mutations give **4.3%** — better than either strategy alone
    — and **zero refusals** on normal output. The guard costs nothing until
    something goes wrong.

    The returned line count therefore does not matter; what matters is that
    the stream stays in order, and what catches it when it does not lives
    downstream.
    """
    if not source_lines:
        return ()

    src_stream = "\n".join(source_lines)
    tgt_stream = "\n".join(returned_lines)

    # Line boundaries in the SOURCE stream, to be carried across.
    marks: list[int] = []
    pos = 0
    for line in source_lines[:-1]:
        pos += len(line) + 1
        marks.append(pos)

    mapped: dict[int, int] = {}
    for _tag, i1, i2, j1, j2 in SequenceMatcher(
        None, src_stream, tgt_stream, autojunk=False
    ).get_opcodes():
        for mark in marks:
            if i1 <= mark <= i2:
                mapped[mark] = j1 + min(mark - i1, j2 - j1)

    cuts = [0] + [mapped.get(m, m) for m in marks] + [len(tgt_stream)]
    # Monotonic: a boundary never walks back over the previous one, or a
    # line would receive text already given to its neighbour.
    for i in range(1, len(cuts)):
        cuts[i] = max(cuts[i], cuts[i - 1])
    return tuple(
        tgt_stream[cuts[i] : cuts[i + 1]].strip("\n") for i in range(len(source_lines))
    )
