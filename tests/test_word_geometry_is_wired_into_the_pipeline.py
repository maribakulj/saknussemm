"""The slow path's resolver seam, reachable through the public pipeline.

``rewrite_alto_file`` accepted ``word_geometry`` since 2026-09-22;
``AltoFormatAdapter`` did not pass it and ``CorrectionPipeline`` did not
expose it, so a host wanting hans's resolver had to write an adapter
(contre-revue du 7/10/2026). These tests pin the three public routes and
the trace that says which tier actually drew each slow-path line.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from saknussemm import CorrectionPipeline
from saknussemm.core.protocols import LineGeometryRequest, TokenBox
from saknussemm.errors import ConfigurationError
from saknussemm.facade import _NullObserver, correct_sync, load
from saknussemm.formats.alto.adapter import AltoFormatAdapter
from saknussemm.formats.alto.parser import build_document_manifest as build_alto
from saknussemm.formats.page.parser import build_document_manifest as build_page
from saknussemm.producers.rules import RulesProducer, SubstitutionRule

NS = "http://www.loc.gov/standards/alto/ns-v3#"

ALTO = f"""<alto xmlns="{NS}"><Description><MeasurementUnit>pixel</MeasurementUnit>
</Description><Layout><Page ID="P1" WIDTH="1000" HEIGHT="100" PHYSICAL_IMG_NR="1">
<PrintSpace HPOS="0" VPOS="0" WIDTH="1000" HEIGHT="100">
<TextBlock ID="B1" HPOS="0" VPOS="0" WIDTH="1000" HEIGHT="40">
<TextLine ID="L1" HPOS="100" VPOS="20" WIDTH="300" HEIGHT="40">
<String ID="S1" CONTENT="dela" HPOS="100" VPOS="20" WIDTH="300" HEIGHT="40"/>
</TextLine></TextBlock></PrintSpace></Page></Layout></alto>"""

PAGE = """<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15">
<Page imageFilename="p.png" imageWidth="1000" imageHeight="100">
<TextRegion id="r1"><Coords points="0,0 1000,0 1000,40 0,40"/>
<TextLine id="l1"><Coords points="100,20 400,20 400,60 100,60"/>
<TextEquiv><Unicode>dela</Unicode></TextEquiv></TextLine></TextRegion></Page></PcGts>"""


class _Pinned:
    """Answers a geometry nothing else would draw, and remembers being asked."""

    name = "pinned"

    def __init__(self) -> None:
        self.asked: list[str] = []

    def resolve(self, request: LineGeometryRequest) -> tuple[TokenBox, ...]:
        self.asked.append(request.line_id)
        return (
            TokenBox(text="de", hpos=110, width=30),
            TokenBox(text=" ", hpos=140, width=20),
            TokenBox(text="la", hpos=160, width=40),
        )


def _producer() -> RulesProducer:
    return RulesProducer([SubstitutionRule("dela", "de la")])


def _strings(xml: bytes) -> list[tuple[str | None, str | None, str | None]]:
    root = etree.fromstring(xml)
    return [
        (s.get("CONTENT"), s.get("HPOS"), s.get("WIDTH"))
        for s in root.iter(f"{{{NS}}}String")
    ]


PINNED = [("de", "110", "30"), ("la", "160", "40")]


def _alto(tmp_path: Path) -> Path:
    path = tmp_path / "page.xml"
    path.write_text(ALTO, encoding="utf-8")
    return path


def test_the_adapter_carries_the_resolver(tmp_path: Path) -> None:
    path = _alto(tmp_path)
    resolver = _Pinned()
    pipeline = CorrectionPipeline(
        producer=_producer(),
        observer=_NullObserver(),
        format_adapter=AltoFormatAdapter(word_geometry=resolver),
    )
    result = pipeline.run_sync(
        document_manifest=build_alto([(path, path.name)]),
        source_files={path.name: path},
    )
    assert resolver.asked == ["L1"]
    assert _strings(result.corrected_files[path.name]) == PINNED


def test_the_pipeline_exposes_the_resolver_without_an_adapter(tmp_path: Path) -> None:
    path = _alto(tmp_path)
    resolver = _Pinned()
    pipeline = CorrectionPipeline(
        producer=_producer(),
        observer=_NullObserver(),
        word_geometry=resolver,
    )
    result = pipeline.run_sync(
        document_manifest=build_alto([(path, path.name)]),
        source_files={path.name: path},
    )
    assert resolver.asked == ["L1"]
    assert _strings(result.corrected_files[path.name]) == PINNED


def test_the_facade_exposes_the_resolver(tmp_path: Path) -> None:
    path = _alto(tmp_path)
    resolver = _Pinned()
    result = correct_sync(load(path), producer=_producer(), word_geometry=resolver)
    assert resolver.asked == ["L1"]
    assert _strings(result.corrected_files[path.name]) == PINNED


def test_a_resolver_and_an_adapter_together_are_refused() -> None:
    with pytest.raises(ConfigurationError, match="not both"):
        CorrectionPipeline(
            producer=_producer(),
            observer=_NullObserver(),
            format_adapter=AltoFormatAdapter(),
            word_geometry=_Pinned(),
        )


def test_a_resolver_on_a_page_document_is_refused_at_run_start(tmp_path: Path) -> None:
    path = tmp_path / "page.xml"
    path.write_text(PAGE, encoding="utf-8")
    resolver = _Pinned()
    pipeline = CorrectionPipeline(
        producer=_producer(),
        observer=_NullObserver(),
        word_geometry=resolver,
    )
    with pytest.raises(ConfigurationError, match="PAGE|page"):
        pipeline.run_sync(
            document_manifest=build_page([(path, path.name)]),
            source_files={path.name: path},
        )
    assert resolver.asked == []


def test_each_slow_path_line_says_which_tier_drew_it(tmp_path: Path) -> None:
    from saknussemm.formats.alto.rewriter import rewrite_alto_file

    path = _alto(tmp_path)
    doc = build_alto([(path, path.name)])
    doc.pages[0].lines[0].corrected_text = "de la"
    with_resolver = rewrite_alto_file(
        path, doc.pages, "t", "m", word_geometry=_Pinned()
    )
    assert with_resolver.geometry_tiers == {"L1": "resolver:pinned"}
    without = rewrite_alto_file(path, doc.pages, "t", "m")
    # a one-word page: no sibling box to learn letter widths from, so the
    # anchored tier cannot draw and the pixel-blind fallback is named
    assert without.geometry_tiers == {"L1": "proportional"}
    assert without.rewriter_paths == {"L1": "slow_path"}


def test_the_default_run_is_byte_identical(tmp_path: Path) -> None:
    path = _alto(tmp_path)
    a = correct_sync(load(path), producer=_producer()).corrected_files[path.name]
    b = correct_sync(
        load(path), producer=_producer(), word_geometry=None
    ).corrected_files[path.name]
    assert a == b
