"""PAGE parsing and provenance refer to a single source snapshot."""

from pathlib import Path

import pytest

from saknussemm.core.provenance import source_digest
from saknussemm.errors import ParseError
from saknussemm.formats.page import parser


_SOURCE = """<?xml version="1.0" encoding="ISO-8859-1"?>
<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15">
<Page imageFilename="scan.png" imageWidth="1000" imageHeight="1000">
<TextRegion id="r1"><TextLine id="l1">
<TextEquiv><Unicode>été</Unicode></TextEquiv>
</TextLine></TextRegion></Page></PcGts>""".encode("utf-8")


@pytest.mark.parametrize("remove_source", [False, True])
def test_manifest_provenance_uses_parsed_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, remove_source: bool
) -> None:
    path = tmp_path / "source.xml"
    path.write_bytes(_SOURCE)
    read_tree = parser.read_source_tree

    def parse_then_change(path: Path, **kwargs: bytes):
        tree = read_tree(path, **kwargs)
        if remove_source:
            path.unlink()
        else:
            path.write_bytes(_SOURCE.replace("été".encode(), b"autre"))
        return tree

    monkeypatch.setattr(parser, "read_source_tree", parse_then_change)

    manifest = parser.build_document_manifest([(path, "source.xml")])

    assert manifest.pages[0].lines[0].ocr_text == "été"
    assert manifest.source_digests == {"source.xml": source_digest(_SOURCE)}
    assert manifest.source_encodings == {"source.xml": "ISO-8859-1"}


def test_page_builder_refuses_an_alto_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "source.xml"
    path.write_text(
        '<alto xmlns="http://www.loc.gov/standards/alto/ns-v3#">'
        '<Layout><Page ID="p1" WIDTH="1000" HEIGHT="1000"/></Layout></alto>'
    )
    with pytest.raises(ParseError, match="expected PAGE source bytes"):
        parser.build_document_manifest([(path, "source.xml")])
