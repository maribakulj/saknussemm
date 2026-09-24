"""Chunk planner: splits a page's lines into LLM-sized chunks.

Budget semantics: ``max_input_chars_per_request`` bounds the sum of
the chunk lines' RAW OCR text — it deliberately excludes the JSON
envelope, system prompt, neighbour context and optional geometry the
enrichment step adds (all of which grow roughly linearly with the same
line count). Consumers sizing the budget against a provider's token limit
should keep generous headroom (the 12 000 default assumes ~3-4× overhead
against 128k-class context windows). Two documented exceptions may
overshoot the budget, both bounded by ``max_lines_per_request``:

  * a hyphen CHAIN is atomic — splitting a hyphenated word across chunks
    corrupts reconciliation, so chain extension outranks the char budget;
  * a single line longer than the whole budget still ships alone (a line
    is the smallest unit the pipeline corrects).
"""

from __future__ import annotations

import uuid

from saknussemm.core.pairing import forward_partner_id
from saknussemm.core.units import derive_hyphen_groups, split_forward_link
from saknussemm.core.schemas import (
    ChunkGranularity,
    ChunkPlan,
    ChunkPlannerConfig,
    ChunkRequest,
    HyphenSplit,
    LineManifest,
    PageManifest,
)

# ---------------------------------------------------------------------------
# Granularity downgrade
# ---------------------------------------------------------------------------

_CHAIN = [
    ChunkGranularity.PAGE,
    ChunkGranularity.BLOCK,
    ChunkGranularity.WINDOW,
    ChunkGranularity.LINE,
]


def downgrade_granularity(current: ChunkGranularity) -> ChunkGranularity | None:
    """Return the next granularity level, or None if already at LINE."""
    idx = _CHAIN.index(current)
    if idx + 1 < len(_CHAIN):
        return _CHAIN[idx + 1]
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _total_chars(lines: list[LineManifest]) -> int:
    return sum(len(lm.ocr_text) for lm in lines)


def _unit_reach(
    lines: list[LineManifest],
    index_by_id: dict[str, int],
    start: int,
    end: int,
) -> int:
    """The exclusive end a window must reach to hold every live forward link
    that leaves ``lines[start:end]``.

    Returns ``end`` when nothing leaves — the window is already whole.

    This replaces the pairwise ``should_stay_in_same_chunk(last_in_window,
    next_line)``, which asked whether the window's LAST line pairs with the
    very NEXT one. Two different questions, and the pairwise one is wrong in
    both directions: it cannot see a link that leaves from an EARLIER line in
    the window, and it cannot see a partner that is not the immediately next
    line. The second became reachable the moment the linker learned to step
    over blank lines — a pair linked across a blank failed the test, the
    window closed between the two, and no single window held both members, so
    the target assignment fell through to its per-line fallback and the pair
    was corrected in two different chunks.

    Absorbing the predicate here also retires it: it was the third
    formulation of "who is my partner?" left standing, and it had
    exactly one production caller.

    A partner off this page (a cross-page pair) or behind ``start`` is not a
    forward continuation this window can hold, and is ignored rather than
    chased.
    """
    reach = end
    for position in range(start, end):
        partner_id = forward_partner_id(lines[position])
        if not partner_id:
            continue
        partner_at = index_by_id.get(partner_id)
        if partner_at is None or partner_at < end:
            continue
        reach = max(reach, partner_at + 1)
    return reach


def _make_chunk(
    document_id: str,
    page_id: str,
    granularity: ChunkGranularity,
    line_ids: list[str],
    block_id: str | None = None,
    target_line_ids: list[str] | None = None,
) -> ChunkRequest:
    return ChunkRequest(
        chunk_id=str(uuid.uuid4()),
        document_id=document_id,
        page_id=page_id,
        block_id=block_id,
        granularity=granularity,
        line_ids=list(line_ids),
        target_line_ids=None if target_line_ids is None else list(target_line_ids),
    )


def _assign_window_targets(
    windows: list[list[str]],
    line_by_id: dict[str, LineManifest],
) -> list[list[str]]:
    """Assign every line to exactly one target window.

    Overlapping windows mean a boundary line appears in two windows; pre-F8
    it was corrected in whichever window ran first (its context there was
    truncated). Here each line becomes a target in the LAST window that
    contains it — the window where it has the most in-chunk *following*
    context (following lines drive word-completion and hyphen joins). A
    hyphen pair is forced into the last window that contains BOTH members
    so reconciliation never spans a target boundary.
    """
    membership: dict[str, list[int]] = {}
    for i, w in enumerate(windows):
        for lid in w:
            membership.setdefault(lid, []).append(i)

    target_win: dict[str, int] = {lid: idxs[-1] for lid, idxs in membership.items()}

    # Hyphen atomicity (audit P0): a chain of 3+ lines (PART1→BOTH→…→PART2)
    # must be targeted in ONE window. The grouping is the SHARED unit
    # derivation (ADR-010) — one definition of "these lines travel
    # together" instead of a local union-find that could drift from the
    # reconciler's view. Each group gets the LAST window common to ALL
    # its members — order-independent by construction.
    components = [
        [ref.line_id for ref in group.members if ref.line_id in membership]
        for group in derive_hyphen_groups(
            lm for lm in line_by_id.values() if lm.line_id in membership
        )
    ]

    for members in components:
        if len(members) < 2:
            continue
        # Intersection of every member's membership set = windows that
        # contain the WHOLE component. Target the last such window.
        common: set[int] = set(membership[members[0]])
        for m in members[1:]:
            common &= set(membership[m])
        if common:
            win = max(common)
            for m in members:
                target_win[m] = win
        # If no single window holds the whole component (a chain longer
        # than any window — the planner caps chains to a window, so this
        # is the pathological over-cap case), leave the per-line last-window
        # assignment: the LINE-granularity downgrade + unlink handles it.

    return [
        [lid for lid in w if target_win.get(lid) == i] for i, w in enumerate(windows)
    ]


# ---------------------------------------------------------------------------
# PAGE granularity
# ---------------------------------------------------------------------------


def _try_page(
    page: PageManifest,
    document_id: str,
    config: ChunkPlannerConfig,
) -> ChunkPlan | None:
    lines = page.lines
    if (
        _total_chars(lines) <= config.max_input_chars_per_request
        and len(lines) <= config.max_lines_per_request
    ):
        chunk = _make_chunk(
            document_id,
            page.page_id,
            ChunkGranularity.PAGE,
            [lm.line_id for lm in lines],
        )
        return ChunkPlan(
            page_id=page.page_id,
            chunks=[chunk],
            granularity=ChunkGranularity.PAGE,
        )
    return None


# ---------------------------------------------------------------------------
# BLOCK granularity
# ---------------------------------------------------------------------------


def _try_block(
    page: PageManifest,
    document_id: str,
    config: ChunkPlannerConfig,
) -> ChunkPlan | None:
    line_by_id = {lm.line_id: lm for lm in page.lines}

    # Group lines by block in page.blocks order
    block_lines: dict[str, list[LineManifest]] = {}
    for block in page.blocks:
        block_lines[block.block_id] = [
            line_by_id[lid] for lid in block.line_ids if lid in line_by_id
        ]

    block_ids_ordered = [b.block_id for b in page.blocks]

    # Union-find to merge blocks linked by cross-block hyphen pairs
    parent: dict[str, str] = {bid: bid for bid in block_ids_ordered}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # A hyphen unit spanning blocks forces those blocks into one chunk.
    # The grouping is the SHARED unit derivation (ADR-010) — the same
    # definition of "these lines travel together" that the window
    # pinning and the reconciler consume — instead of a local per-link
    # walk over the pointer fields.
    for group in derive_hyphen_groups(page.lines):
        member_blocks = [
            line_by_id[ref.line_id].block_id
            for ref in group.members
            if ref.line_id in line_by_id
        ]
        linked = [bid for bid in member_blocks if bid in parent]
        for a, b in zip(linked, linked[1:]):
            union(a, b)

    # Collect groups in page order (use dict to deduplicate while preserving order)
    seen_roots: dict[str, None] = {}
    for bid in block_ids_ordered:
        seen_roots[find(bid)] = None

    groups: dict[str, list[str]] = {}
    for bid in block_ids_ordered:
        root = find(bid)
        groups.setdefault(root, []).append(bid)

    grouped: list[tuple[list[str], list[LineManifest]]] = []
    for root in seen_roots:
        group_block_ids = groups[root]
        group_lines: list[LineManifest] = []
        for bid in group_block_ids:
            group_lines.extend(block_lines.get(bid, []))

        if (
            _total_chars(group_lines) > config.max_input_chars_per_request
            or len(group_lines) > config.max_lines_per_request
        ):
            return None  # too large → fall back to WINDOW
        grouped.append((group_block_ids, group_lines))
    if config.coalesce_blocks:
        grouped = _coalesce(grouped, config)

    chunks: list[ChunkRequest] = []
    for group_block_ids, group_lines in grouped:
        block_id_label = group_block_ids[0] if len(group_block_ids) == 1 else None
        chunks.append(
            _make_chunk(
                document_id,
                page.page_id,
                ChunkGranularity.BLOCK,
                [lm.line_id for lm in group_lines],
                block_id=block_id_label,
            )
        )

    if not chunks:
        return None

    return ChunkPlan(
        page_id=page.page_id,
        chunks=chunks,
        granularity=ChunkGranularity.BLOCK,
    )


def _coalesce(
    grouped: list[tuple[list[str], list[LineManifest]]],
    config: ChunkPlannerConfig,
) -> list[tuple[list[str], list[LineManifest]]]:
    """Merge consecutive block groups while both budgets hold.

    Greedy and in reading order: a group joins the chunk being built when
    the lines and the characters still fit, else it starts the next one.
    Each input group is already within budget (the caller returned
    ``None`` otherwise), so every output chunk is too. Groups are never
    reordered and never split — a hyphen unit spanning two blocks arrived
    here as one group and leaves as part of one chunk.
    """
    out: list[tuple[list[str], list[LineManifest]]] = []
    for block_ids, lines in grouped:
        if out:
            prev_ids, prev_lines = out[-1]
            merged = prev_lines + lines
            if (
                len(merged) <= config.max_lines_per_request
                and _total_chars(merged) <= config.max_input_chars_per_request
            ):
                out[-1] = (prev_ids + block_ids, merged)
                continue
        out.append((list(block_ids), list(lines)))
    return out


# ---------------------------------------------------------------------------
# WINDOW granularity
# ---------------------------------------------------------------------------


def _try_window(
    page: PageManifest,
    document_id: str,
    config: ChunkPlannerConfig,
) -> ChunkPlan:
    lines = page.lines
    n = len(lines)
    if n == 0:
        return ChunkPlan(
            page_id=page.page_id, chunks=[], granularity=ChunkGranularity.WINDOW
        )

    window_size = config.line_window_size
    overlap = config.line_window_overlap
    # A LOOKUP, not a resolver: id -> position on this page.
    index_by_id = {lm.line_id: position for position, lm in enumerate(lines)}

    window_line_ids: list[list[str]] = []
    start = 0

    while start < n:
        # A window is bounded by BOTH the line count and the char
        # budget (historically only PAGE/BLOCK honoured the char budget;
        # a window of pathologically long lines blew straight past
        # max_input_chars_per_request). At least one line always enters,
        # even over budget — a single line is atomic.
        end = start + 1
        chars = len(lines[start].ocr_text)
        while end < min(start + window_size, n):
            c = len(lines[end].ocr_text)
            if chars + c > config.max_input_chars_per_request:
                break
            chars += c
            end += 1
        core_end = end  # budget/size-limited end, drives the overlap step

        # Extend to keep hyphen chains intact at window boundary,
        # but cap to avoid unbounded growth beyond the line budget.
        # Chain atomicity deliberately outranks the char budget: splitting
        # a hyphenated word across chunks corrupts reconciliation, while
        # a temporarily oversized request only risks a producer error
        # (retried / downgraded). The extension stays line-capped.
        extension_limit = max(config.max_lines_per_request, end - start + 10)
        max_end = min(n, start + extension_limit)
        while end < max_end:
            reach = _unit_reach(lines, index_by_id, start, end)
            if reach <= end:
                break
            end = min(reach, max_end)

        window_line_ids.append([lines[i].line_id for i in range(start, end)])

        # Step relative to the ACTUAL core window when the char budget
        # shortened it, so nothing is skipped (a fixed step would jump
        # past unvisited lines). When the budget did not bind, keep the
        # historical fixed step exactly (byte-parity with the fixed-step
        # planner, including its tail-window behaviour near page end).
        budget_bound = core_end < min(start + window_size, n)
        if budget_bound:
            next_start = max(start + 1, core_end - overlap)
        else:
            next_start = start + (window_size - overlap)
        # Defensive progress guard: the config validator forbids
        # overlap >= window_size, but pydantic's model_copy(update=...)
        # BYPASSES validation — without this clamp such a config spins
        # this loop forever (review finding, reproduced).
        if next_start <= start:
            next_start = start + 1
        start = next_start

    # Each line is a target in exactly one window (its last, best-context
    # window); overlaps become pure context in the other window.
    line_by_id = {lm.line_id: lm for lm in lines}
    targets_per_window = _assign_window_targets(window_line_ids, line_by_id)

    chunks = [
        _make_chunk(
            document_id,
            page.page_id,
            ChunkGranularity.WINDOW,
            ids,
            target_line_ids=targets,
        )
        for ids, targets in zip(window_line_ids, targets_per_window)
    ]

    return ChunkPlan(
        page_id=page.page_id,
        chunks=chunks,
        granularity=ChunkGranularity.WINDOW,
    )


# ---------------------------------------------------------------------------
# LINE granularity
# ---------------------------------------------------------------------------


def _plan_line(
    page: PageManifest,
    document_id: str,
    config: ChunkPlannerConfig,
) -> ChunkPlan:
    lines = page.lines
    chunks: list[ChunkRequest] = []
    splits: list[HyphenSplit] = []
    # A LOOKUP, not a resolver, and the distinction matters: id -> position on this
    # page. The chain follow used to require the partner to be the literally
    # NEXT line, which is a different question from "where is my partner?"
    # and answers it wrongly whenever anything sits between the two — a
    # blank line, most concretely, now that the linker steps over those.
    # A non-adjacent pair then failed the adjacency test, the chain
    # stopped, the two members landed in DIFFERENT chunks, and the link was
    # left live: the validator skips a pair that is not wholly in-chunk and
    # the reconciler could write across the boundary. Silent, and with no
    # HyphenSplit to show for it.
    index_by_id = {lm.line_id: position for position, lm in enumerate(lines)}
    i = 0
    while i < len(lines):
        # Follow the full chain: PART1 → BOTH → ... → BOTH → PART2.
        # All lines linked by forward hyphen pairs must stay together.
        chain_ids = [lines[i].line_id]
        j = i
        while True:
            forward_pair = forward_partner_id(lines[j])
            if not forward_pair:
                break
            partner_at = index_by_id.get(forward_pair)
            # None: the partner is not on this page (a cross-page pair,
            # owned by the reconciler's cross-page join) or the pointer
            # dangles. Behind us: not a forward continuation. Neither is
            # this loop's business, and neither may be severed here.
            if partner_at is None or partner_at <= j:
                break
            # Everything BETWEEN the two travels with them. Skipping it
            # would leave a line in no chunk at all — and the lines in
            # between are exactly the blank ones the linker steps over.
            # The chain follow stays capped: an adversarial page where
            # every line ends in a dash must not produce one unbounded
            # request.
            if len(chain_ids) + (partner_at - j) > config.max_lines_per_request:
                break
            chain_ids.extend(lm.line_id for lm in lines[j + 1 : partner_at + 1])
            j = partner_at

        # Pair atomicity (core invariant): if the walk stopped with the
        # tail's partner OUTSIDE this chunk, the two halves would sit in
        # different chunks as a still-linked pair. Sever the cut pair
        # explicitly through the unit SPLIT operation (ADR-010): both sides
        # degrade to independent lines with their OCR text preserved
        # verbatim, so every remaining pair is fully contained in one chunk
        # and atomicity stays true by construction. The record rides on the
        # plan — the cut is a unit operation, not a silent side effect.
        #
        # The condition is "my partner is not in my chunk", not "the cap
        # cut me": those coincided only while the chain required adjacency.
        tail = lines[j]
        partner_id = forward_partner_id(tail)
        if partner_id and partner_id not in chain_ids:
            partner_at = index_by_id.get(partner_id)
            if partner_at is not None:
                splits.append(split_forward_link(tail, lines[partner_at]))

        chunks.append(
            _make_chunk(
                document_id,
                page.page_id,
                ChunkGranularity.LINE,
                chain_ids,
            )
        )
        i = j + 1

    return ChunkPlan(
        page_id=page.page_id,
        chunks=chunks,
        granularity=ChunkGranularity.LINE,
        hyphen_splits=splits,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def plan_page(
    page: PageManifest,
    document_id: str,
    config: ChunkPlannerConfig,
    force_granularity: ChunkGranularity | None = None,
) -> ChunkPlan:
    """
    Produce a ChunkPlan for a page.

    Tries PAGE → BLOCK → WINDOW (→ LINE only when force_granularity=LINE).
    force_granularity skips directly to a specific level.
    """
    if force_granularity == ChunkGranularity.LINE:
        return _plan_line(page, document_id, config)
    if force_granularity == ChunkGranularity.WINDOW:
        return _try_window(page, document_id, config)
    if force_granularity == ChunkGranularity.BLOCK:
        result = _try_block(page, document_id, config)
        if result:
            return result
        return _try_window(page, document_id, config)
    if force_granularity == ChunkGranularity.PAGE:
        result = _try_page(page, document_id, config)
        if result:
            return result
        # fall through auto-select

    # Auto-select: PAGE → BLOCK → WINDOW
    result = _try_page(page, document_id, config)
    if result:
        return result

    result = _try_block(page, document_id, config)
    if result:
        return result

    return _try_window(page, document_id, config)


# --- public surface ---
__all__ = [
    "downgrade_granularity",
    "plan_page",
]
