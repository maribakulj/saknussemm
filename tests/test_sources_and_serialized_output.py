"""The deliverable uses the captured source, and its bytes face the gates."""

from dataclasses import replace
from pathlib import Path

import pytest
from lxml import etree

from saknussemm import correct_sync, load
from saknussemm.errors import ConfigurationError
from saknussemm.core.pipeline import CorrectionPipeline
from saknussemm.core.provenance import source_digest
from saknussemm.formats.alto.adapter import AltoFormatAdapter
from saknussemm.producers.rules import RulesProducer
from tests._paths import EXAMPLES
from tests._pipeline_harness import RecordingObserver


class _MutatingProducer(RulesProducer):
    def __init__(self, path, action):
        super().__init__([])
        self.path, self.action = path, action

    async def produce(self, *args, **kwargs):
        if self.action is not None:
            self.action(self.path)
            self.action = None
        return await super().produce(*args, **kwargs)


def _change_dimensions(path):
    root = etree.fromstring(path.read_bytes())
    page = next(
        e
        for e in root.iter()
        if isinstance(e.tag, str) and etree.QName(e).localname == "Page"
    )
    page.set("WIDTH" if "WIDTH" in page.attrib else "imageWidth", "99999")
    path.write_bytes(etree.tostring(root))


@pytest.mark.parametrize(
    "fixture",
    [
        EXAMPLES / "sample.xml",
        EXAMPLES
        / "page/Descartes1637_Discours_btv1b86069594_corrected_0014_page_raw.xml",
    ],
)
@pytest.mark.parametrize("action", [_change_dimensions, Path.unlink])
def test_builtin_render_uses_the_source_captured_before_producer(
    tmp_path, fixture, action
):
    path = tmp_path / "source.xml"
    raw = fixture.read_bytes()
    path.write_bytes(raw)
    document = load(path)
    result = correct_sync(document, producer=_MutatingProducer(path, action))
    assert not result.report.undeliverable_files
    root = etree.fromstring(result.corrected_files[path.name])
    page = next(
        e
        for e in root.iter()
        if isinstance(e.tag, str) and etree.QName(e).localname == "Page"
    )
    width = page.get("WIDTH", page.get("imageWidth"))
    assert int(width) == document.manifest.pages[0].page_width
    assert result.report.provenance.source_digests == {path.name: source_digest(raw)}


class _Adapter:
    def __init__(self, mutate=None):
        self.mutate = mutate

    def rewrite_file(self, *args, **kwargs):
        result = AltoFormatAdapter().rewrite_file(*args, **kwargs)
        if self.mutate:
            root = etree.fromstring(result.xml_bytes)
            self.mutate(root)
            result = replace(result, xml_bytes=etree.tostring(root))
        return result


def _run(path, adapter, producer=None):
    document = load(path)
    return CorrectionPipeline(
        producer=producer or RulesProducer([]),
        observer=RecordingObserver(),
        format_adapter=adapter,
    ).run_sync(document_manifest=document.manifest, source_files={path.name: path})


def test_custom_path_adapter_refuses_a_changed_source(tmp_path):
    path = tmp_path / "source.xml"
    path.write_bytes((EXAMPLES / "sample.xml").read_bytes())
    result = _run(path, _Adapter(), _MutatingProducer(path, _change_dimensions))
    assert not result.corrected_files
    assert "source changed" in result.report.undeliverable_files[path.name]


def _change_text(root):
    next(
        e
        for e in root.iter()
        if isinstance(e.tag, str) and etree.QName(e).localname == "String"
    ).set("CONTENT", "wrong")


def _break_schema(root):
    next(
        e
        for e in root.iter()
        if isinstance(e.tag, str) and etree.QName(e).localname == "Page"
    ).set("WIDTH", "not-a-number")


@pytest.mark.parametrize(
    "mutation, reason",
    [
        (_change_text, "serialized XML"),
        (_break_schema, "XSD violations"),
    ],
)
def test_gate_checks_bytes_even_when_adapter_reports_correct_texts(
    tmp_path, mutation, reason
):
    path = tmp_path / "source.xml"
    path.write_bytes((EXAMPLES / "sample.xml").read_bytes())
    result = _run(path, _Adapter(mutation))
    assert not result.corrected_files
    assert reason in result.report.undeliverable_files[path.name]
    with pytest.raises(ConfigurationError):
        result.write(tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_unmodified_custom_adapter_is_still_called(tmp_path):
    path = tmp_path / "source.xml"
    path.write_bytes((EXAMPLES / "sample.xml").read_bytes())
    result = _run(path, _Adapter())
    assert result.corrected_files
    assert not result.report.undeliverable_files


def test_custom_adapter_cannot_delete_a_referenced_style(tmp_path):
    path = tmp_path / "source.xml"
    root = etree.fromstring((EXAMPLES / "sample.xml").read_bytes())
    ns = etree.QName(root).namespace
    styles = etree.Element(f"{{{ns}}}Styles")
    etree.SubElement(styles, f"{{{ns}}}TextStyle", ID="referenced_style")
    root.insert(1, styles)
    root.find(".//{*}String").set("STYLEREFS", "referenced_style")
    path.write_bytes(etree.tostring(root))

    def drop_style(root):
        style = root.find(".//{*}TextStyle")
        assert style.get("ID") in root.xpath("//@STYLEREFS")
        style.getparent().remove(style)

    result = _run(path, _Adapter(drop_style))
    assert not result.corrected_files
    assert "dangling" in result.undeliverable_files[path.name]


def test_custom_adapter_cannot_change_source_during_rewrite(tmp_path):
    path = tmp_path / "source.xml"
    path.write_bytes((EXAMPLES / "sample.xml").read_bytes())

    class ChangingAdapter(_Adapter):
        def rewrite_file(self, *args, **kwargs):
            result = super().rewrite_file(*args, **kwargs)
            path.unlink()
            return result

    result = _run(path, ChangingAdapter())
    assert not result.corrected_files
    assert "unreadable" in result.undeliverable_files[path.name]


def test_builtin_subclass_override_is_not_bypassed(tmp_path):
    path = tmp_path / "source.xml"
    path.write_bytes((EXAMPLES / "sample.xml").read_bytes())
    calls = []

    class Subclass(AltoFormatAdapter):
        def rewrite_file(self, *args, **kwargs):
            calls.append(True)
            return super().rewrite_file(*args, **kwargs)

    assert _run(path, Subclass()).corrected_files
    assert calls == [True]


def _add_line(root):
    from copy import deepcopy

    line = root.find(".//{*}TextLine")
    extra = deepcopy(line)
    for element in extra.iter():
        if element.get("ID") is not None:
            element.set("ID", "added_" + element.get("ID"))
    line.getparent().append(extra)


def test_serialized_extra_line_is_not_hidden_by_adapter_texts(tmp_path):
    path = tmp_path / "source.xml"
    path.write_bytes((EXAMPLES / "sample.xml").read_bytes())
    result = _run(path, _Adapter(_add_line))
    assert not result.corrected_files
    assert "TextLine inventory" in result.undeliverable_files[path.name]


def test_existing_xsd_violation_is_tolerated_but_may_not_multiply(tmp_path):
    path = tmp_path / "source.xml"
    root = etree.fromstring((EXAMPLES / "sample.xml").read_bytes())
    root.find(".//{*}String").set("unsupported", "yes")
    path.write_bytes(etree.tostring(root))
    assert _run(path, _Adapter()).corrected_files

    def multiply(root):
        root.findall(".//{*}String")[1].set("unsupported", "yes")

    result = _run(path, _Adapter(multiply))
    assert not result.corrected_files
    assert "XSD violations" in result.undeliverable_files[path.name]


def test_vendor_namespace_still_checks_text_without_claiming_xsd_validation(tmp_path):
    path = tmp_path / "source.xml"
    raw = (
        (EXAMPLES / "sample.xml")
        .read_bytes()
        .replace(b"http://www.loc.gov/standards/alto/ns-v3#", b"urn:vendor")
    )
    path.write_bytes(raw)
    assert _run(path, _Adapter()).corrected_files
    result = _run(path, _Adapter(_change_text))
    assert not result.corrected_files
    assert "serialized XML" in result.undeliverable_files[path.name]


def test_host_defined_xml_format_remains_supported(tmp_path):
    from saknussemm.core.protocols import RewriteResult
    from saknussemm.formats.alto.rewriter import RewriterMetrics

    path = tmp_path / "source.xml"
    path.write_bytes((EXAMPLES / "sample.xml").read_bytes())
    manifest = load(path).manifest.model_copy(
        update={"source_format": "custom", "source_digests": {}}
    )
    texts = {
        line.line_id: line.ocr_text for page in manifest.pages for line in page.lines
    }
    root = etree.Element("transcription")
    for lid, text in texts.items():
        etree.SubElement(root, "line", id=lid).text = text
    raw = etree.tostring(root)
    path.write_bytes(raw)

    class Custom:
        format_name = "custom"

        def rewrite_file(self, *args, **kwargs):
            return RewriteResult(
                xml_bytes=raw,
                texts=texts,
                metrics=RewriterMetrics(untouched=len(texts)),
                rewriter_paths={lid: "untouched" for lid in texts},
            )

    result = CorrectionPipeline(
        producer=RulesProducer([]),
        observer=RecordingObserver(),
        format_adapter=Custom(),
    ).run_sync(document_manifest=manifest, source_files={path.name: path})
    assert result.corrected_files == {path.name: raw}
    assert result.report.provenance.source_digests == {path.name: source_digest(raw)}
