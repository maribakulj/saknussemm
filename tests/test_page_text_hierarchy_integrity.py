"""A corrected PAGE must not retain text or geometry for another reading."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from lxml import etree
import pytest

from saknussemm import CorrectionPipeline, load
from saknussemm.core.schemas import DocumentManifest, LineStatus, LossPolicy
from saknussemm.formats.page.parser import build_document_manifest
from saknussemm.formats.page.rewriter import rewrite_page_file
from saknussemm.formats.validation import validate_bytes
from saknussemm.producers.rules import RulesProducer, SubstitutionRule

from tests._pipeline_harness import RecordingObserver

_NS = "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"
_MAP = {"p": _NS}


def _line(line_id: str, words: list[str], y: int = 0) -> str:
    elements = []
    x = 0
    for i, word in enumerate(words):
        width = 10 * len(word)
        glyphs = "".join(
            f'<Glyph id="{line_id}_w{i}_g{j}">'
            f'<Coords points="{x + j * 10},{y} {x + (j + 1) * 10},{y} '
            f'{x + (j + 1) * 10},{y + 20} {x + j * 10},{y + 20}"/>'
            f"<TextEquiv><Unicode>{char}</Unicode></TextEquiv></Glyph>"
            for j, char in enumerate(word)
        )
        elements.append(
            f'<Word id="{line_id}_w{i}"><Coords points="{x},{y} {x + width},{y} '
            f'{x + width},{y + 20} {x},{y + 20}"/>{glyphs}'
            f"<TextEquiv><Unicode>{word}</Unicode></TextEquiv></Word>"
        )
        x += width + 5
    return (
        f'<TextLine id="{line_id}"><Coords points="0,{y} 300,{y} '
        f'300,{y + 20} 0,{y + 20}"/>{"".join(elements)}'
        f"<TextEquiv><Unicode>{' '.join(words)}</Unicode></TextEquiv></TextLine>"
    )


def _source(tmp_path: Path) -> Path:
    first = _line("l1", ["au", "jourdhui"])
    second = _line("l2", ["bonjour", "monde"], 30)
    third = _line("l3", ["source", "intacte"], 90)
    raw = (
        f'<PcGts xmlns="{_NS}"><Metadata><Creator>test</Creator>'
        "<Created>2026-10-07T00:00:00</Created>"
        "<LastChange>2026-10-07T00:00:00</LastChange></Metadata>"
        '<Page imageFilename="p.png" imageWidth="1000" imageHeight="200">'
        '<TextRegion id="r1"><Coords points="0,0 300,0 300,80 0,80"/>'
        f"{first}{second}"
        '<TextEquiv index="0" conf="0.9"><Unicode>au jourdhui\nbonjour monde'
        '</Unicode></TextEquiv><TextEquiv index="1"><Unicode>old alternative'
        "</Unicode></TextEquiv></TextRegion>"
        '<TextRegion id="r2"><Coords points="0,90 300,90 300,120 0,120"/>'
        f"{third}<TextEquiv><Unicode>source intacte</Unicode></TextEquiv>"
        "</TextRegion></Page></PcGts>"
    ).encode()
    assert validate_bytes(raw) == []
    path = tmp_path / "source.xml"
    path.write_bytes(raw)
    return path


def _rewrite(path: Path, changes: dict[str, str]):
    doc = build_document_manifest([(path, path.name)])
    for line in doc.pages[0].lines:
        line.corrected_text = changes.get(line.line_id)
    return rewrite_page_file(path, doc.pages, "test", "rules")


@pytest.mark.parametrize("strict", [False, True])
def test_boundary_move_with_a_typo_does_not_retain_positional_polygons(
    tmp_path: Path, strict: bool
) -> None:
    path = _source(tmp_path)
    root = etree.fromstring(path.read_bytes())
    old = root.xpath('.//p:TextLine[@id="l1"]', namespaces=_MAP)[0]
    replacement = etree.fromstring(
        (f'<root xmlns="{_NS}">' + _line("l1", ["le", "stcmps"]) + "</root>").encode()
    )[0]
    old.getparent().replace(old, replacement)
    path.write_bytes(etree.tostring(root))
    document = load(path)
    result = CorrectionPipeline(
        producer=RulesProducer([SubstitutionRule("le stcmps", "les temps")]),
        observer=RecordingObserver(),
        loss_policy=LossPolicy(strict=strict),
    ).run_sync(document_manifest=document.manifest, source_files=document.source_paths)
    outcome = next(line for line in result.report.lines if line.line_id == "l1")
    assert outcome.projection is not None
    if strict:
        assert outcome.decision.status == LineStatus.FALLBACK
        assert outcome.projection.rewriter_path == "untouched"
    else:
        assert outcome.decision.status == LineStatus.CORRECTED
        assert outcome.projection.rewriter_path == "slow_path"
        assert outcome.projection.losses["words_dropped"] == 2
    assert validate_bytes(result.corrected_files[path.name]) == []


@pytest.mark.parametrize("strict", [False, True])
def test_boundary_move_at_constant_count_never_keeps_wrong_boxes(
    tmp_path: Path, strict: bool
) -> None:
    path = _source(tmp_path)
    document = load(path)
    result = CorrectionPipeline(
        producer=RulesProducer([SubstitutionRule("au jourd", "aujourd ")]),
        observer=RecordingObserver(),
        loss_policy=LossPolicy(strict=strict),
    ).run_sync(document_manifest=document.manifest, source_files=document.source_paths)
    root = etree.fromstring(result.corrected_files[path.name])
    words = root.xpath('.//p:TextLine[@id="l1"]/p:Word', namespaces=_MAP)
    outcome = next(line for line in result.report.lines if line.line_id == "l1")
    assert outcome.projection is not None
    if strict:
        assert outcome.decision.status == LineStatus.FALLBACK
        assert outcome.projection.rewriter_path == "untouched"
        assert len(words) == 2
        assert outcome.projection.losses is None
        assert root.xpath('.//p:TextRegion[@id="r1"]/p:TextEquiv', namespaces=_MAP)
    else:
        assert words == []
        assert outcome.projection.rewriter_path == "slow_path"
        assert outcome.projection.losses is not None
        assert outcome.projection.losses["words_dropped"] == 2
        assert outcome.projection.losses["glyph_elements_removed"] == 10
        assert outcome.projection.losses["region_textequiv_dropped"] == 2
    assert validate_bytes(result.corrected_files[path.name]) == []


def test_changed_words_invalidate_only_their_glyphs_and_ancestor_readings(
    tmp_path: Path,
) -> None:
    path = _source(tmp_path)
    before = etree.fromstring(path.read_bytes())
    result = _rewrite(path, {"l1": "eu jourdhui", "l2": "bonsoir monde"})
    after = etree.fromstring(result.xml_bytes)
    assert after.xpath('.//p:Word[@id="l1_w0"]/p:Glyph', namespaces=_MAP) == []
    assert after.xpath('.//p:Word[@id="l2_w0"]/p:Glyph', namespaces=_MAP) == []
    for word_id in ("l1_w1", "l2_w1", "l3_w0", "l3_w1"):
        selector = f'.//p:Word[@id="{word_id}"]'
        assert etree.tostring(after.xpath(selector, namespaces=_MAP)[0]) == (
            etree.tostring(before.xpath(selector, namespaces=_MAP)[0])
        )
    assert after.xpath('.//p:TextRegion[@id="r1"]/p:TextEquiv', namespaces=_MAP) == []
    r2 = './/p:TextRegion[@id="r2"]'
    assert etree.tostring(after.xpath(r2, namespaces=_MAP)[0]) == etree.tostring(
        before.xpath(r2, namespaces=_MAP)[0]
    )
    assert result.metrics.glyph_elements_removed == 9
    assert result.metrics.region_textequiv_dropped == 2
    assert result.losses_by_line["l1"]["region_textequiv_dropped"] == 2
    assert "region_textequiv_dropped" not in result.losses_by_line["l2"]
    totals: Counter[str] = Counter()
    for losses in result.losses_by_line.values():
        totals.update(losses)
    assert dict(totals) == result.losses
    assert (
        len(before.xpath(".//p:Glyph", namespaces=_MAP))
        - len(after.xpath(".//p:Glyph", namespaces=_MAP))
        == totals["glyph_elements_removed"]
    )
    assert validate_bytes(result.xml_bytes) == []


def test_unchanged_page_keeps_glyphs_and_region_readings(tmp_path: Path) -> None:
    path = _source(tmp_path)
    result = _rewrite(path, {})
    before, after = (
        etree.fromstring(path.read_bytes()),
        etree.fromstring(result.xml_bytes),
    )
    assert etree.tostring(before.find(f"{{{_NS}}}Page")) == etree.tostring(
        after.find(f"{{{_NS}}}Page")
    )
    assert result.losses == {}


def test_strict_uses_actual_word_readings_when_line_text_disagrees(
    tmp_path: Path,
) -> None:
    path = _source(tmp_path)
    root = etree.fromstring(path.read_bytes())
    line_reading = root.xpath(
        './/p:TextLine[@id="l1"]/p:TextEquiv/p:Unicode', namespaces=_MAP
    )[0]
    line_reading.text = "aujourd hui"
    path.write_bytes(etree.tostring(root))
    document = load(path)
    original = document.manifest.pages[0].lines[0]
    assert original._source_word_texts == ["au", "jourdhui"]
    copied = original.model_copy(deep=True)
    assert copied._source_word_texts == original._source_word_texts
    assert copied._source_word_texts is not original._source_word_texts
    assert "_source_word_texts" not in original.model_dump()
    result = CorrectionPipeline(
        producer=RulesProducer([SubstitutionRule("aujourd hui", "aujourd lui")]),
        observer=RecordingObserver(),
        loss_policy=LossPolicy(strict=True),
    ).run_sync(document_manifest=document.manifest, source_files=document.source_paths)
    outcome = next(line for line in result.report.lines if line.line_id == "l1")
    assert outcome.decision.status == LineStatus.FALLBACK
    assert outcome.projection is not None
    assert outcome.projection.rewriter_path == "untouched"
    assert b'<Word id="l1_w0">' in result.corrected_files[path.name]


@pytest.mark.parametrize("restored", [False, True])
@pytest.mark.parametrize("changed", [False, True])
def test_strict_needs_source_word_evidence_only_for_corrections(
    tmp_path: Path, restored: bool, changed: bool
) -> None:
    path = _source(tmp_path)
    document = load(path)
    manifest = document.manifest
    if restored:
        manifest = DocumentManifest.model_validate_json(manifest.model_dump_json())
        assert manifest.pages[0].lines[0]._source_word_texts is None
    rules = [SubstitutionRule("au jourdhui", "eu jourdhui")] if changed else []
    result = CorrectionPipeline(
        producer=RulesProducer(rules),
        observer=RecordingObserver(),
        loss_policy=LossPolicy(strict=True),
    ).run_sync(document_manifest=manifest, source_files=document.source_paths)
    outcome = next(line for line in result.report.lines if line.line_id == "l1")
    assert outcome.projection is not None
    if restored and changed:
        assert outcome.decision.status == LineStatus.FALLBACK
        assert outcome.decision.reason is not None
        assert "source Word readings unavailable" in outcome.decision.reason.detail
        assert outcome.projection.rewriter_path == "untouched"
    elif changed:
        assert outcome.decision.status == LineStatus.CORRECTED
        assert outcome.projection.rewriter_path == "fast_path"
    else:
        assert outcome.projection.rewriter_path == "untouched"
    assert b'<Word id="l1_w0">' in result.corrected_files[path.name]


def test_region_readings_are_invalidated_up_to_nested_ancestors(tmp_path: Path) -> None:
    path = _source(tmp_path)
    root = etree.fromstring(path.read_bytes())
    region = root.xpath('.//p:TextRegion[@id="r1"]', namespaces=_MAP)[0]
    page = region.getparent()
    parent = etree.Element(f"{{{_NS}}}TextRegion", id="outer")
    etree.SubElement(parent, f"{{{_NS}}}Coords", points="0,0 300,0 300,80 0,80")
    page.replace(region, parent)
    parent.append(region)
    equiv = etree.SubElement(parent, f"{{{_NS}}}TextEquiv")
    etree.SubElement(equiv, f"{{{_NS}}}Unicode").text = "old aggregate"
    path.write_bytes(etree.tostring(root))
    result = _rewrite(path, {"l1": "eu jourdhui"})
    after = etree.fromstring(result.xml_bytes)
    assert (
        after.xpath('.//p:TextRegion[@id="outer"]/p:TextEquiv', namespaces=_MAP) == []
    )
    assert result.losses_by_line["l1"]["region_textequiv_dropped"] == 3


def test_snapshot_rewrite_uses_supplied_bytes_after_path_changes(
    tmp_path: Path,
) -> None:
    path = _source(tmp_path)
    source_bytes = path.read_bytes()
    doc = build_document_manifest([(path, path.name)])
    doc.pages[0].lines[0].corrected_text = "eu jourdhui"
    path.unlink()
    result = rewrite_page_file(
        path, doc.pages, "test", "rules", _source_bytes=source_bytes
    )
    assert b"eu jourdhui" in result.xml_bytes
    assert validate_bytes(result.xml_bytes) == []


@pytest.mark.parametrize("level", ["Word", "TextLine"])
@pytest.mark.parametrize(
    ("version", "following"),
    [("2013", "TextStyle")]
    + [
        (version, child)
        for version in ("2019", "2024")
        for child in ("TextStyle", "UserDefined", "Labels")
    ],
)
def test_new_text_readings_precede_trailing_metadata(
    tmp_path: Path, level: str, version: str, following: str
) -> None:
    path = _source(tmp_path)
    root = etree.fromstring(path.read_bytes())
    old_line = root.xpath('.//p:TextLine[@id="l1"]', namespaces=_MAP)[0]
    line = etree.fromstring(
        _line("l1", ["a", "b"])
        .replace("<TextLine ", f'<TextLine xmlns="{_NS}" ')
        .encode()
    )
    old_line.getparent().replace(old_line, line)
    element = line if level == "TextLine" else line.find(f"{{{_NS}}}Word")
    assert element is not None
    for reading in element.findall(f"{{{_NS}}}TextEquiv"):
        element.remove(reading)
    metadata = etree.SubElement(element, f"{{{_NS}}}{following}")
    if following == "UserDefined":
        etree.SubElement(
            metadata, f"{{{_NS}}}UserAttribute", name="reviewed", value="true"
        )
    elif following == "Labels":
        etree.SubElement(metadata, f"{{{_NS}}}Label", value="example")
    if version == "2013":
        # 2013 permits one reading and has no TextEquiv@index.
        for region in root.findall(f".//{{{_NS}}}TextRegion"):
            for reading in region.findall(f"{{{_NS}}}TextEquiv"):
                region.remove(reading)
    raw = etree.tostring(root).replace(b"2019-07-15", f"{version}-07-15".encode())
    assert validate_bytes(raw) == []
    path.write_bytes(raw)
    document = load(path)
    result = CorrectionPipeline(
        producer=RulesProducer([SubstitutionRule("a b", "c b")]),
        observer=RecordingObserver(),
    ).run_sync(document_manifest=document.manifest, source_files=document.source_paths)
    assert path.name in result.corrected_files
    output = result.corrected_files[path.name]
    assert validate_bytes(output) == []
    ns = _NS.replace("2019", version)
    after = etree.fromstring(output).find(f'.//{{{ns}}}TextLine[@id="l1"]')
    assert after is not None
    if level == "Word":
        after = after.find(f"{{{ns}}}Word")
    assert after is not None
    names = [etree.QName(child).localname for child in after]
    assert names.index("TextEquiv") < names.index(following)
    assert after.find(f"{{{ns}}}TextEquiv/{{{ns}}}Unicode").text == (
        "c b" if level == "TextLine" else "c"
    )


@pytest.mark.parametrize("has_region_reading", [False, True])
def test_region_offsets_are_invalidated_once_even_without_aggregate_text(
    tmp_path: Path, has_region_reading: bool
) -> None:
    path = _source(tmp_path)
    before = etree.fromstring(path.read_bytes())
    for region in before.findall(f".//{{{_NS}}}TextRegion"):
        region.set(
            "custom",
            "readingOrder {index:0;} person {offset:11; length:7;} "
            "structure {type:paragraph;} date {offset:0; length:2;}",
        )
    if not has_region_reading:
        region = before.find(f'.//{{{_NS}}}TextRegion[@id="r1"]')
        for reading in region.findall(f"{{{_NS}}}TextEquiv"):
            region.remove(reading)
    raw = etree.tostring(before)
    assert validate_bytes(raw) == []
    path.write_bytes(raw)
    result = _rewrite(path, {"l1": "eu jourdhui", "l2": "bonsoir monde"})
    after = etree.fromstring(result.xml_bytes)
    custom = after.find(f'.//{{{_NS}}}TextRegion[@id="r1"]').get("custom")
    assert custom == "readingOrder {index:0;} structure {type:paragraph;}"
    assert result.losses_by_line["l1"]["custom_offset_stripped"] == 2
    assert "custom_offset_stripped" not in result.losses_by_line["l2"]
    assert result.losses["custom_offset_stripped"] == 2
    r2 = f'.//{{{_NS}}}TextRegion[@id="r2"]'
    assert etree.tostring(before.find(r2)) == etree.tostring(after.find(r2))
    assert validate_bytes(result.xml_bytes) == []
