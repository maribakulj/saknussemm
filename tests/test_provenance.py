"""Provenance stamped into schema-defined ALTO processing records."""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from saknussemm.formats.alto._ns import _detect_namespace
from saknussemm.formats.alto.parser import build_document_manifest
from saknussemm.formats.alto.rewriter import rewrite_alto_file

_NS = "http://www.loc.gov/standards/alto/ns-v4#"

# ALTO 4 appends a new Processing record beside the source history.
_ALTO = f"""<?xml version="1.0"?>
<alto xmlns="{_NS}">
  <Description><MeasurementUnit>pixel</MeasurementUnit><Processing ID="P0"/></Description>
  <Layout>
    <Page ID="P1" WIDTH="600" HEIGHT="800" PHYSICAL_IMG_NR="1">
      <PrintSpace>
        <TextBlock ID="B1" HPOS="0" VPOS="0" WIDTH="500" HEIGHT="30">
          <TextLine ID="L1" HPOS="0" VPOS="0" WIDTH="500" HEIGHT="30">
            <String ID="S1" CONTENT="bonjour" HPOS="0" VPOS="0" WIDTH="100" HEIGHT="30"/>
          </TextLine>
        </TextBlock>
      </PrintSpace>
    </Page>
  </Layout>
</alto>"""

# Real-world ALTO (ABBYY, Tesseract, Gallica exports) records OCR under
# <OCRProcessing>/<ocrProcessingStep>, NOT the generic <Processing>. The
# post-OCR correction pass must be recorded there too — as a
# <postProcessingStep> — or §11's "every corrected file records the pass" is
# silently false for exactly the files real users bring.
_ALTO_OCRPROCESSING = """<?xml version="1.0"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v3#">
  <Description>
    <MeasurementUnit>pixel</MeasurementUnit>
    <OCRProcessing ID="OCR_1">
      <ocrProcessingStep>
        <processingSoftware>
          <softwareName>Tesseract</softwareName>
        </processingSoftware>
      </ocrProcessingStep>
    </OCRProcessing>
  </Description>
  <Layout>
    <Page ID="P1" WIDTH="600" HEIGHT="800" PHYSICAL_IMG_NR="1">
      <PrintSpace>
        <TextBlock ID="B1" HPOS="0" VPOS="0" WIDTH="500" HEIGHT="30">
          <TextLine ID="L1" HPOS="0" VPOS="0" WIDTH="500" HEIGHT="30">
            <String ID="S1" CONTENT="bonjour" HPOS="0" VPOS="0" WIDTH="100" HEIGHT="30"/>
          </TextLine>
        </TextBlock>
      </PrintSpace>
    </Page>
  </Layout>
</alto>"""


def _write(tmp_path: Path) -> Path:
    p = tmp_path / "prov.xml"
    p.write_text(_ALTO, encoding="utf-8")
    return p


def _processing_step_descriptions(xml_bytes: bytes) -> list[str]:
    root = etree.fromstring(xml_bytes)
    ns = _detect_namespace(root)
    tag = f"{{{ns}}}processingStepDescription" if ns else "processingStepDescription"
    return [el.text or "" for el in root.iter(tag)]


def _post_processing_descriptions(xml_bytes: bytes) -> list[str]:
    """Provenance text from <postProcessingStep>/<processingStepDescription>
    (the slot used inside an OCRProcessing container)."""
    root = etree.fromstring(xml_bytes)
    ns = _detect_namespace(root)
    step_tag = f"{{{ns}}}postProcessingStep" if ns else "postProcessingStep"
    desc_tag = (
        f"{{{ns}}}processingStepDescription" if ns else "processingStepDescription"
    )
    return [d.text or "" for step in root.iter(step_tag) for d in step.iter(desc_tag)]


def test_processing_step_carries_version_and_fingerprint(tmp_path: Path):
    xml_path = _write(tmp_path)
    doc = build_document_manifest([(xml_path, xml_path.name)])
    _res = rewrite_alto_file(
        xml_path,
        doc.pages,
        provider="openai",
        model="gpt-x",
        lib_version="9.9.9",
        config_fingerprint="deadbeefcafe0000",
    )
    xml_bytes = _res.xml_bytes
    descs = _processing_step_descriptions(xml_bytes)
    assert descs, "no processing description written"
    assert any("openai/gpt-x" in d for d in descs)
    assert any("saknussemm 9.9.9" in d for d in descs)
    assert any("config deadbeefcafe0000" in d for d in descs)


def test_processing_step_backwards_compatible_without_provenance(tmp_path: Path):
    """Omitting version/fingerprint yields the historical description."""
    xml_path = _write(tmp_path)
    doc = build_document_manifest([(xml_path, xml_path.name)])
    _res = rewrite_alto_file(xml_path, doc.pages, provider="openai", model="gpt-x")
    xml_bytes = _res.xml_bytes
    descs = _processing_step_descriptions(xml_bytes)
    assert any(d == "Post-OCR correction via openai/gpt-x (saknussemm)" for d in descs)


def _write_ocr(tmp_path: Path) -> Path:
    p = tmp_path / "ocr.xml"
    p.write_text(_ALTO_OCRPROCESSING, encoding="utf-8")
    return p


def test_ocrprocessing_file_records_the_pass(tmp_path: Path):
    """A real ALTO whose Description carries <OCRProcessing> (not the generic
    <Processing>) must still record the correction pass — as a
    <postProcessingStep> inside the OCRProcessing container (spec §11)."""
    xml_path = _write_ocr(tmp_path)
    doc = build_document_manifest([(xml_path, xml_path.name)])
    _res = rewrite_alto_file(
        xml_path,
        doc.pages,
        provider="openai",
        model="gpt-x",
        lib_version="9.9.9",
        config_fingerprint="deadbeefcafe0000",
    )
    xml_bytes = _res.xml_bytes
    descs = _post_processing_descriptions(xml_bytes)
    assert descs, "no postProcessingStep written into <OCRProcessing>"
    assert any("openai/gpt-x" in d for d in descs)
    assert any("saknussemm 9.9.9" in d for d in descs)
    assert any("config deadbeefcafe0000" in d for d in descs)
    # saknussemm names itself as the processing software, not just in prose.
    root = etree.fromstring(xml_bytes)
    ns = _detect_namespace(root)
    name_tag = f"{{{ns}}}softwareName" if ns else "softwareName"
    assert any((el.text or "") == "saknussemm" for el in root.iter(name_tag))
    # The original OCR step is preserved, not replaced.
    assert any((el.text or "") == "Tesseract" for el in root.iter(name_tag))
