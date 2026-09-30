"""A returned page line holding a line separator no longer sinks the page."""

from __future__ import annotations

import asyncio
from typing import Any

from saknussemm.core.editing import ReplaceLine
from saknussemm.core.protocols import ProducerOptions
from saknussemm.core.schemas import (
    ChunkGranularity,
    CorrectionRequest,
    LineContext,
    Usage,
)
from saknussemm.producers.page_llm import PageLLMEditProducer


class _Client:
    def __init__(self, lines: list[str]) -> None:
        self.lines = lines

    async def complete_structured(
        self, **_: Any
    ) -> tuple[dict[str, Any], Usage | None]:
        return {"lines": self.lines}, None


def _request() -> CorrectionRequest:
    return CorrectionRequest(
        granularity=ChunkGranularity.PAGE,
        document_id="d",
        page_id="p",
        lines=[
            LineContext(line_id="a", ocr_text="Lorsque nous arrivames a Paris"),
            LineContext(line_id="b", ocr_text="personne ne nous attendait"),
        ],
    )


def test_characters_path_survives_a_separator_inside_a_returned_line() -> None:
    client = _Client(
        ["Lorsque nous arrivâmes\u2028à Paris", "personne ne nous attendait"]
    )
    producer = PageLLMEditProducer(client, "k", "m", line_matching="characters")
    script, _ = asyncio.run(producer.produce(_request(), options=ProducerOptions()))
    texts = {op.line_id: op.text for op in script.ops if isinstance(op, ReplaceLine)}
    assert texts == {"a": "Lorsque nous arrivâmes à Paris"}
    assert all("\u2028" not in t and "\n" not in t for t in texts.values())


def test_jaccard_path_flattens_too() -> None:
    client = _Client(["Lorsque nous arrivâmes\nà Paris", "personne ne nous attendait"])
    producer = PageLLMEditProducer(client, "k", "m")
    script, _ = asyncio.run(producer.produce(_request(), options=ProducerOptions()))
    texts = {op.line_id: op.text for op in script.ops if isinstance(op, ReplaceLine)}
    assert texts.get("a") == "Lorsque nous arrivâmes à Paris"
