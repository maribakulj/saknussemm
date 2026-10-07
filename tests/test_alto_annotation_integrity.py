"""Schema-valid provenance and honest invalidation of character annotations."""

from pathlib import Path

import pytest
from lxml import etree

from saknussemm.facade import correct_sync, load
from saknussemm.formats.alto.parser import build_document_manifest
from saknussemm.formats.alto.rewriter import rewrite_alto_file
from saknussemm.formats.validation import validate_bytes
from saknussemm.producers.rules import RulesProducer, SubstitutionRule

from tests._paths import EXAMPLES


def _source(version: int, history: str = "", *, glyphs: bool = False) -> bytes:
    def word(identity: str, text: str, hpos: int) -> str:
        children = (
            "".join(
                f'<Glyph ID="{identity}_g{i}" CONTENT="{char}" HPOS="{hpos + i * 10}" '
                'VPOS="0" WIDTH="10" HEIGHT="20"/>'
                for i, char in enumerate(text)
            )
            if glyphs
            else ""
        )
        return (
            f'<String ID="{identity}" CONTENT="{text}" HPOS="{hpos}" '
            f'VPOS="0" WIDTH="30" HEIGHT="20" WC="0.9">{children}</String>'
        )

    return f"""<alto xmlns="http://www.loc.gov/standards/alto/ns-v{version}#">
<Description><MeasurementUnit>pixel</MeasurementUnit>{history}</Description>
<Layout><Page ID="P1" WIDTH="100" HEIGHT="100" PHYSICAL_IMG_NR="1">
<PrintSpace HPOS="0" VPOS="0" WIDTH="100" HEIGHT="100">
<TextBlock ID="B1" HPOS="0" VPOS="0" WIDTH="100" HEIGHT="20">
<TextLine ID="L1" HPOS="0" VPOS="0" WIDTH="100" HEIGHT="20">
{word("W1", "cat", 0)}<SP WIDTH="10"/>{word("W2", "dog", 40)}
</TextLine></TextBlock></PrintSpace></Page></Layout></alto>""".encode()


_OCR = '<OCRProcessing ID="ocr0"><ocrProcessingStep/></OCRProcessing>'
_PROCESSING = (
    '<Processing ID="existing"><processingStepDescription>original history'
    "</processingStepDescription><processingSoftware><softwareName>source OCR"
    "</softwareName></processingSoftware></Processing>"
)


@pytest.mark.parametrize(
    ("version", "history"),
    [(v, h) for v in (2, 3) for h in ("", _OCR)]
    + [(4, h) for h in ("", _OCR, _PROCESSING, _OCR + _PROCESSING)],
)
def test_provenance_preserves_schema_and_existing_history(tmp_path, version, history):
    raw = _source(version, history)
    assert validate_bytes(raw) == []
    path = tmp_path / "page.xml"
    path.write_bytes(raw)
    doc = build_document_manifest([(path, path.name)])
    result = rewrite_alto_file(path, doc.pages, "rules", "local", lib_version="0.9.0")
    assert validate_bytes(result.xml_bytes) == []
    root = etree.fromstring(result.xml_bytes)
    ns = {"a": root.nsmap[None]}
    descriptions = root.xpath(".//a:processingStepDescription/text()", namespaces=ns)
    assert "Post-OCR correction via rules/local (saknussemm 0.9.0)" in descriptions
    if _PROCESSING in history:
        before = etree.fromstring(raw).xpath(
            ".//a:Processing[@ID='existing']", namespaces=ns
        )[0]
        after = root.xpath(".//a:Processing[@ID='existing']", namespaces=ns)[0]
        assert etree.tostring(before) == etree.tostring(after)
    if version < 4:
        assert not root.xpath(".//a:Processing", namespaces=ns)
        assert root.xpath(".//a:postProcessingStep", namespaces=ns)
    else:
        assert root.xpath(".//a:Processing/a:processingStepDescription", namespaces=ns)
        assert not root.xpath(".//a:processingStep", namespaces=ns)


def test_processing_ids_are_unique_across_the_document_and_repeated_passes(tmp_path):
    path = tmp_path / "page.xml"
    raw = _source(4).replace(b'ID="W1"', b'ID="saknussemm_processing_1"')
    path.write_bytes(raw)
    for _ in range(2):
        doc = build_document_manifest([(path, path.name)])
        result = rewrite_alto_file(path, doc.pages, "rules", "local")
        assert validate_bytes(result.xml_bytes) == []
        path.write_bytes(result.xml_bytes)
    root = etree.fromstring(path.read_bytes())
    ns = {"a": root.nsmap[None]}
    ids = root.xpath("//@ID")
    assert len(ids) == len(set(ids))
    assert len(root.xpath(".//a:Processing", namespaces=ns)) == 2


def test_real_alto4_identity_output_is_schema_valid():
    path = (
        EXAMPLES
        / "page"
        / "Descartes1637_Discours_btv1b86069594_corrected_0014_alto4.xml"
    )
    assert validate_bytes(path.read_bytes()) == []
    result = correct_sync(load(path), producer=RulesProducer([]))
    assert validate_bytes(result.corrected_files[path.name]) == []


@pytest.mark.parametrize(
    ("replacement", "removed", "rewriter_path"),
    [("cat", 0, "untouched"), ("cot", 3, "fast_path"), ("cat new", 6, "slow_path")],
)
def test_glyph_removals_match_the_file_and_reach_the_report(
    tmp_path: Path, replacement: str, removed: int, rewriter_path: str
):
    raw = _source(4, _OCR, glyphs=True)
    assert validate_bytes(raw) == []
    path = tmp_path / "glyphs.xml"
    path.write_bytes(raw)
    result = correct_sync(
        load(path), producer=RulesProducer([SubstitutionRule("cat", replacement)])
    )
    output = result.corrected_files[path.name]
    assert validate_bytes(output) == []
    root = etree.fromstring(output)
    ns = {"a": root.nsmap[None]}
    remaining = root.xpath(".//a:Glyph", namespaces=ns)
    assert len(remaining) == 6 - removed
    losses = result.report.format_losses or {}
    assert losses.get("glyph_elements_removed", 0) == removed
    projection = result.report.lines[0].projection
    assert projection is not None
    assert projection.rewriter_path == rewriter_path
    assert (projection.losses or {}).get("glyph_elements_removed", 0) == removed
    if rewriter_path == "fast_path":
        assert root.xpath(".//a:String[@ID='W1']/a:Glyph", namespaces=ns) == []
        before = etree.fromstring(raw).xpath(".//a:String[@ID='W2']", namespaces=ns)[0]
        after = root.xpath(".//a:String[@ID='W2']", namespaces=ns)[0]
        assert etree.tostring(before) == etree.tostring(after)
        assert losses["confidence_invalidated"] == 1


@pytest.mark.parametrize("replacement", ["cot", "cat new"])
@pytest.mark.parametrize("existing_broken", [False, True])
def test_removing_a_referenced_glyph_withholds_the_file(
    tmp_path: Path, replacement: str, existing_broken: bool
) -> None:
    from saknussemm.errors import ProjectionError

    broken = (
        '<ElementRef ID="broken" REF="already_missing"/>' if existing_broken else ""
    )
    reading_order = (
        '<ReadingOrder><OrderedGroup ID="order">'
        f'{broken}<ElementRef ID="reference" REF="W1_g0 W2_g0"/>'
        "</OrderedGroup></ReadingOrder>"
    )
    raw = _source(4, glyphs=True).replace(
        b"<Layout>", reading_order.encode() + b"<Layout>"
    )
    assert validate_bytes(raw) == []
    path = tmp_path / "referenced.xml"
    path.write_bytes(raw)
    document = load(path)
    result = correct_sync(
        document, producer=RulesProducer([SubstitutionRule("cat", replacement)])
    )
    assert result.corrected_files == {}
    assert "W1_g0" in result.undeliverable_files[path.name]
    assert "dangling" in result.undeliverable_files[path.name]
    doc = build_document_manifest([(path, path.name)])
    doc.pages[0].lines[0].corrected_text = f"{replacement} dog"
    with pytest.raises(ProjectionError, match="W1_g0"):
        rewrite_alto_file(path, doc.pages, "test", "rules")


def test_unchanged_missing_reference_does_not_block_correction(tmp_path: Path) -> None:
    reading_order = (
        '<ReadingOrder><OrderedGroup ID="order">'
        '<ElementRef ID="reference" REF="already_missing W2_g0"/>'
        "</OrderedGroup></ReadingOrder>"
    )
    path = tmp_path / "existing-defect.xml"
    path.write_bytes(
        _source(4, glyphs=True).replace(
            b"<Layout>", reading_order.encode() + b"<Layout>"
        )
    )
    result = correct_sync(
        load(path), producer=RulesProducer([SubstitutionRule("cat", "cot")])
    )
    assert not result.undeliverable_files
    assert b'REF="already_missing W2_g0"' in result.corrected_files[path.name]
