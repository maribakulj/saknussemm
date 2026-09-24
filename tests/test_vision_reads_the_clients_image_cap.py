"""``VisionEditProducer`` reads the image cap its client declares (VR-3)."""

from __future__ import annotations

from typing import Any

from saknussemm.core.schemas import ModelCapabilities, Usage
from saknussemm.producers.vision import VisionEditProducer


class _Client:
    MAX_IMAGES_PER_CALL = 8

    async def complete_structured_multimodal(
        self, **_: Any
    ) -> tuple[dict[str, Any], Usage | None]:
        return {"lines": []}, None


class _Silent:
    async def complete_structured_multimodal(
        self, **_: Any
    ) -> tuple[dict[str, Any], Usage | None]:
        return {"lines": []}, None


def test_a_declared_cap_reaches_the_capabilities() -> None:
    assert VisionEditProducer(_Client(), "k", "m").capabilities.max_images == 8


def test_no_declaration_means_no_cap_as_before() -> None:
    assert VisionEditProducer(_Silent(), "k", "m").capabilities.max_images is None


def test_explicit_capabilities_win() -> None:
    explicit = ModelCapabilities(
        text=True, vision=True, structured_output=True, max_images=4
    )
    assert (
        VisionEditProducer(
            _Client(), "k", "m", capabilities=explicit
        ).capabilities.max_images
        == 4
    )
