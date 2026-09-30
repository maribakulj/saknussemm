"""``ChunkPlannerConfig(coalesce_blocks=True)`` — small regions ride together (VR-2)."""

from __future__ import annotations

from saknussemm.core.planner import plan_page
from saknussemm.core.schemas import (
    BlockManifest,
    ChunkGranularity,
    ChunkPlannerConfig,
    Coords,
    LineManifest,
    PageManifest,
)


def _line(line_id: str, block_id: str, order: int) -> LineManifest:
    return LineManifest(
        line_id=line_id,
        page_id="P1",
        block_id=block_id,
        line_order_global=order,
        line_order_in_block=0,
        coords=Coords(hpos=0, vpos=order * 10, width=100, height=8),
        ocr_text=f"ligne {order}",
    )


def _page(blocks: int, lines_per_block: int) -> PageManifest:
    lines, manifests = [], []
    for b in range(blocks):
        ids = [f"l{b}_{i}" for i in range(lines_per_block)]
        lines += [
            _line(lid, f"B{b}", b * lines_per_block + i) for i, lid in enumerate(ids)
        ]
        manifests.append(
            BlockManifest(
                block_id=f"B{b}",
                page_id="P1",
                block_order=b,
                coords=Coords(hpos=0, vpos=b * 100, width=100, height=90),
                line_ids=ids,
            )
        )
    return PageManifest(
        page_id="P1",
        source_file="t.xml",
        page_index=0,
        page_width=1000,
        page_height=1000,
        blocks=manifests,
        lines=lines,
    )


def test_default_keeps_one_chunk_per_block() -> None:
    plan = plan_page(_page(6, 3), "d", ChunkPlannerConfig(max_lines_per_request=10))
    assert plan.granularity is ChunkGranularity.BLOCK
    assert [len(c.line_ids) for c in plan.chunks] == [3] * 6


def test_coalescing_fills_the_line_budget_in_reading_order() -> None:
    plan = plan_page(
        _page(6, 3),
        "d",
        ChunkPlannerConfig(max_lines_per_request=10, coalesce_blocks=True),
    )
    assert plan.granularity is ChunkGranularity.BLOCK
    assert [len(c.line_ids) for c in plan.chunks] == [9, 9]
    assert plan.chunks[0].line_ids == [f"l{b}_{i}" for b in range(3) for i in range(3)]
    assert all(c.block_id is None for c in plan.chunks)


def test_coalescing_respects_the_character_budget() -> None:
    plan = plan_page(
        _page(4, 2),
        "d",
        ChunkPlannerConfig(
            max_lines_per_request=10,
            max_input_chars_per_request=30,
            coalesce_blocks=True,
        ),
    )
    # each block is 2 lines of ~7 chars; three blocks would exceed 30 chars
    assert [len(c.line_ids) for c in plan.chunks] == [4, 4]
