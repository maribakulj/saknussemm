"""``CompositeVisionEditProducer`` — one labelled strip per chunk.

Self-skips without Pillow (the ``[vision]`` extra), like ``test_vision``.
Every image is drawn in-process; the provider is a fake that records what
it was sent and answers under the painted aliases.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

from saknussemm.core.batching import _split_for_image_cap  # noqa: E402
from saknussemm.core.editing import ReplaceLine  # noqa: E402
from saknussemm.core.protocols import EditProducer, ProducerOptions  # noqa: E402
from saknussemm.core.schemas import (  # noqa: E402
    ChunkGranularity,
    ChunkRequest,
    Coords,
    CorrectionRequest,
    LineContext,
    LineGeometry,
    LineManifest,
    Usage,
)
from saknussemm.producers.vision import (  # noqa: E402
    CompositeVisionEditProducer,
    ImagePart,
    build_image_asset,
    compose_line_strip,
    crop_region,
    line_aliases,
)


def _page(tmp_path: Path) -> Path:
    path = tmp_path / "page.png"
    img = Image.new("RGB", (400, 300), (255, 255, 255))
    for i in range(3):
        for x in range(20, 380):
            for y in range(30 + i * 80, 30 + i * 80 + 30):
                img.putpixel((x, y), (i * 60, 0, 0))
    img.save(path, format="PNG")
    return path


def _request(asset: Any, n: int = 3) -> CorrectionRequest:
    lines = [
        LineContext(
            line_id=f"tl_{i}",
            ocr_text=f"ligne numero {i}",
            geometry=LineGeometry(
                coords=Coords(hpos=20, vpos=30 + i * 80, width=360, height=30),
                page_width=400,
                page_height=300,
            ),
        )
        for i in range(n)
    ]
    return CorrectionRequest(
        granularity=ChunkGranularity.BLOCK,
        document_id="doc",
        page_id="p1",
        lines=lines,
        image_ref=asset,
    )


class _FakeClient:
    def __init__(self, reply: dict[str, Any]) -> None:
        self.reply = reply
        self.calls: list[dict[str, Any]] = []

    async def complete_structured_multimodal(
        self, **kwargs: Any
    ) -> tuple[dict[str, Any], Usage | None]:
        self.calls.append(kwargs)
        return self.reply, Usage(input_tokens=1, output_tokens=1)


def test_aliases_are_deterministic_opaque_and_unique() -> None:
    ids = [f"tl_{i}" for i in range(50)]
    first, second = line_aliases(ids), line_aliases(ids)
    assert first == second
    assert len(set(first.values())) == len(ids)
    for alias in first.values():
        assert len(alias) == 5 and alias.isupper()
        assert not set(alias) & set("01OI")


def test_strip_is_deterministic_and_one_row_per_line(tmp_path: Path) -> None:
    asset = build_image_asset("p1", _page(tmp_path))
    crops = [
        crop_region(asset, Coords(hpos=20, vpos=30 + i * 80, width=360, height=30))
        for i in range(3)
    ]
    rows = list(zip(["AAAAA", "BBBBB", "CCCCC"], crops, strict=True))
    a, b = (
        compose_line_strip(rows, row_height=40, gap=10),
        compose_line_strip(rows, row_height=40, gap=10),
    )
    assert a.sha256 == b.sha256
    assert a.height == 3 * 50 + 10
    with Image.open(__import__("io").BytesIO(a.data)) as img:
        # a red label pixel exists left of the ink column
        reds = sum(
            1
            for x in range(0, 200)
            for y in range(0, img.height, 3)
            if img.getpixel((x, y))[0] > 120 and img.getpixel((x, y))[1] < 60
        )
    assert reds > 0


def test_producer_sends_one_strip_and_maps_aliases_back(tmp_path: Path) -> None:
    asset = build_image_asset("p1", _page(tmp_path))
    request = _request(asset)
    aliases = line_aliases([ln.line_id for ln in request.lines])
    reply = {
        "lines": [
            {"line_id": aliases["tl_0"], "corrected_text": "ligne numéro 0"},
            {"line_id": aliases["tl_1"].lower(), "corrected_text": "ligne numéro 1"},
            {
                "line_id": "ZZZZZ",
                "corrected_text": "une ligne que personne n'a envoyée",
            },
        ]
    }
    client = _FakeClient(reply)
    producer = CompositeVisionEditProducer(client, "key", "model", max_lines=20)
    assert isinstance(producer, EditProducer)

    script, usage = asyncio.run(
        producer.produce(request, options=ProducerOptions(temperature=0.0))
    )
    call = client.calls[0]
    assert len(call["images"]) == 1 and isinstance(call["images"][0], ImagePart)
    sent_ids = [entry["line_id"] for entry in call["user_payload"]["lines"]]
    assert sent_ids == [aliases["tl_0"], aliases["tl_1"], aliases["tl_2"]]
    assert "prev_text" not in call["user_payload"]["lines"][0]

    ops = [op for op in script.ops if isinstance(op, ReplaceLine)]
    assert {op.line_id: op.text for op in ops} == {
        "tl_0": "ligne numéro 0",
        "tl_1": "ligne numéro 1",  # a lowercased alias still maps back
    }  # the unknown alias yields no op: the validator will report tl_2 missing
    assert usage is not None


def test_row_count_is_bounded_through_the_image_cap() -> None:
    producer = CompositeVisionEditProducer(_FakeClient({}), "key", "model", max_lines=4)
    ids = [f"tl_{i}" for i in range(10)]
    chunk = ChunkRequest(
        chunk_id="c",
        document_id="doc",
        page_id="p1",
        granularity=ChunkGranularity.PAGE,
        line_ids=ids,
    )
    line_by_id = {
        lid: LineManifest(
            line_id=lid,
            page_id="p1",
            block_id="b1",
            line_order_global=i,
            line_order_in_block=i,
            ocr_text="x",
            coords=Coords(hpos=0, vpos=i, width=1, height=1),
        )
        for i, lid in enumerate(ids)
    }
    split = _split_for_image_cap(routed=[(chunk, producer)], line_by_id=line_by_id)
    assert [len(c.line_ids) for c, _ in split] == [4, 4, 2]


def test_an_empty_reply_keeps_the_source_instead_of_sinking_the_chunk(
    tmp_path: Path,
) -> None:
    """The prompt says "identifiant seul" for an unreadable line; obeying it
    must not cost the chunk three retries and a downgrade (VR-9)."""
    asset = build_image_asset("p1", _page(tmp_path))
    request = _request(asset)
    aliases = line_aliases([ln.line_id for ln in request.lines])
    reply = {
        "lines": [
            {"line_id": aliases["tl_0"], "corrected_text": ""},
            {"line_id": aliases["tl_1"], "corrected_text": "ligne numéro 1"},
            {"line_id": aliases["tl_2"], "corrected_text": "   "},
        ]
    }
    producer = CompositeVisionEditProducer(_FakeClient(reply), "key", "model")
    script, _ = asyncio.run(producer.produce(request, options=ProducerOptions()))
    ops = {op.line_id: op.text for op in script.ops if isinstance(op, ReplaceLine)}
    assert ops == {
        "tl_0": "ligne numero 0",
        "tl_1": "ligne numéro 1",
        "tl_2": "ligne numero 2",
    }
