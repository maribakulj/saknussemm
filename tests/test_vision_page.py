"""``PageVisionEditProducer`` — the whole page as one image, ids in the text."""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

from saknussemm.core.editing import ReplaceLine  # noqa: E402
from saknussemm.core.protocols import EditProducer, ProducerOptions  # noqa: E402
from saknussemm.core.schemas import (  # noqa: E402
    ChunkGranularity,
    CorrectionRequest,
    LineContext,
    Usage,
)
from saknussemm.producers.vision import (  # noqa: E402
    ImagePart,
    PageVisionEditProducer,
    build_image_asset,
    line_aliases,
    page_image,
)


def _page(tmp_path: Path) -> Path:
    path = tmp_path / "page.png"
    Image.new("RGB", (3000, 4200), (250, 250, 240)).save(path, format="PNG")
    return path


class _FakeClient:
    def __init__(self, reply: dict[str, Any]) -> None:
        self.reply = reply
        self.calls: list[dict[str, Any]] = []

    async def complete_structured_multimodal(
        self, **kwargs: Any
    ) -> tuple[dict[str, Any], Usage | None]:
        self.calls.append(kwargs)
        return self.reply, Usage(input_tokens=1, output_tokens=1)


def test_page_image_is_bounded_deterministic_and_jpeg(tmp_path: Path) -> None:
    asset = build_image_asset("p1", _page(tmp_path))
    a, b = page_image(asset, max_side=1024), page_image(asset, max_side=1024)
    assert a.sha256 == b.sha256 and a.media_type == "image/jpeg"
    with Image.open(io.BytesIO(a.data)) as img:
        assert max(img.size) == 1024 and img.size == (731, 1024)


def test_producer_sends_the_page_once_with_aliased_lines(tmp_path: Path) -> None:
    asset = build_image_asset("p1", _page(tmp_path))
    lines = [LineContext(line_id=f"tl_{i}", ocr_text=f"ligne {i}") for i in range(3)]
    request = CorrectionRequest(
        granularity=ChunkGranularity.PAGE,
        document_id="doc",
        page_id="p1",
        lines=lines,
        image_ref=asset,
    )
    aliases = line_aliases([ln.line_id for ln in lines])
    client = _FakeClient(
        {"lines": [{"line_id": aliases["tl_1"], "corrected_text": "ligne un"}]}
    )
    producer = PageVisionEditProducer(client, "key", "model")
    assert isinstance(producer, EditProducer)
    assert producer.wants_geometry is False and producer.wants_image is True

    script, _ = asyncio.run(producer.produce(request, options=ProducerOptions()))
    call = client.calls[0]
    assert len(call["images"]) == 1 and isinstance(call["images"][0], ImagePart)
    assert call["images"][0].media_type == "image/jpeg"
    assert [e["line_id"] for e in call["user_payload"]["lines"]] == [
        aliases["tl_0"],
        aliases["tl_1"],
        aliases["tl_2"],
    ]
    ops = [op for op in script.ops if isinstance(op, ReplaceLine)]
    assert {op.line_id: op.text for op in ops} == {"tl_1": "ligne un"}
