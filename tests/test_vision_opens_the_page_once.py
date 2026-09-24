"""``open_page`` + ``crop_region(source_image=…)`` yield the same crops as before (VR-8)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

from saknussemm.core.schemas import Coords  # noqa: E402
from saknussemm.producers.vision import build_image_asset, crop_region, open_page  # noqa: E402


def test_cropping_a_decoded_page_gives_the_same_bytes(tmp_path: Path) -> None:
    path = tmp_path / "page.png"
    img = Image.new("RGB", (400, 300), (255, 255, 255))
    for x in range(50, 350):
        img.putpixel((x, 100), (0, 0, 0))
    img.save(path, format="PNG")
    asset = build_image_asset("p1", path)
    coords = Coords(hpos=40, vpos=90, width=320, height=20)
    via_bytes = crop_region(asset, coords, margin_ratio=0.1)
    page = open_page(asset)
    via_image = crop_region(asset, coords, margin_ratio=0.1, source_image=page)
    assert via_image.sha256 == via_bytes.sha256
    assert via_image.pixel_box == via_bytes.pixel_box
