"""Manifest text and provenance must describe the same source bytes."""

from __future__ import annotations

from pathlib import Path

import pytest

from saknussemm.core.provenance import source_digest
from saknussemm.formats.alto import parser


_SOURCE = """<?xml version="1.0" encoding="ISO-8859-1"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v3#"><Layout>
<Page ID="P1" WIDTH="1000" HEIGHT="1000"><PrintSpace>
<TextBlock ID="B1"><TextLine ID="L1">
<String ID="W1" CONTENT="été" HPOS="0" VPOS="0" WIDTH="50" HEIGHT="20"/>
</TextLine></TextBlock></PrintSpace></Page></Layout></alto>""".encode("utf-8")


@pytest.mark.parametrize("remove_source", [False, True])
def test_manifest_provenance_uses_the_bytes_parsed_before_source_changes(
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
