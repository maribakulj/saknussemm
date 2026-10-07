"""Persistence must not overwrite an artefact with metadata or follow a link."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from saknussemm import CorrectionPipeline
from saknussemm.core.result import CorrectionResult
from saknussemm.core.schemas import SidecarEntry
from saknussemm.errors import ConfigurationError
from saknussemm.formats.alto.parser import build_document_manifest
from saknussemm.producers.rules import RulesProducer

from tests._paths import EXAMPLES
from tests._pipeline_harness import RecordingObserver


@pytest.fixture
def result() -> CorrectionResult:
    source = EXAMPLES / "sample.xml"
    manifest = build_document_manifest([(source, source.name)])
    return CorrectionPipeline(
        producer=RulesProducer([]), observer=RecordingObserver()
    ).run_sync(document_manifest=manifest, source_files={source.name: source})


def _with_sidecar(result: CorrectionResult) -> None:
    result.report.sidecar = [
        SidecarEntry(
            page_id="P1",
            line_id="L1",
            source_text="l'été",
            corrected_text="l'étê",
            reason="token_realign",
        )
    ]


def test_reusing_a_directory_removes_only_the_obsolete_sidecar(result, tmp_path):
    target = tmp_path / "output"
    _with_sidecar(result)
    result.write(target)
    unrelated = target / "notes.txt"
    unrelated.write_text("keep")
    result.report.sidecar = []
    written = result.write(target)
    assert not (target / "sidecar.json").exists()
    assert json.loads((target / "report.json").read_bytes())["sidecar"] == []
    assert unrelated.read_text() == "keep"
    assert "sidecar.json" not in {path.name for path in written}


@pytest.mark.parametrize("obstacle", ["symlink", "directory"])
def test_obsolete_sidecar_obstacle_is_refused_before_any_write(
    result, tmp_path, obstacle
):
    target = tmp_path / "output"
    target.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("keep")
    sidecar = target / "sidecar.json"
    if obstacle == "symlink":
        sidecar.symlink_to(outside)
    else:
        sidecar.mkdir()
    with pytest.raises(ConfigurationError, match="sidecar"):
        result.write(target)
    assert {path.name for path in target.iterdir()} == {"sidecar.json"}
    assert outside.read_text() == "keep"


def test_partial_write_refuses_an_old_xml_for_a_withheld_file(result, tmp_path):
    target = tmp_path / "output"
    result.write(target)
    old = target / "withheld.xml"
    old.write_bytes(b"old XML must not look like a current deliverable")
    before = {p.name: p.read_bytes() for p in target.iterdir()}
    result.undeliverable_files["volume/withheld.xml"] = "projection failed"
    with pytest.raises(ConfigurationError, match="withheld.xml"):
        result.write(target, allow_partial=True)
    assert {p.name: p.read_bytes() for p in target.iterdir()} == before


@pytest.mark.parametrize(
    ("delivered", "withheld"),
    [
        ("a.xml", "A.xml"),
        ("été.xml", "e\u0301te\u0301.xml"),
        ("page.xml", "REPORT.JSON"),
    ],
)
def test_partial_write_refuses_portable_aliases_of_withheld_names(
    result, tmp_path, delivered, withheld
):
    result.corrected_files = {delivered: b"<delivered/>"}
    result.undeliverable_files = {withheld: "projection failed"}
    target = tmp_path / "new-output"
    with pytest.raises(ConfigurationError, match="undeliverable"):
        result.write(target, allow_partial=True)
    assert not target.exists()


def test_partial_write_refuses_an_existing_portable_alias(result, tmp_path):
    target = tmp_path / "output"
    target.mkdir()
    old = target / "A.xml"
    old.write_bytes(b"old XML")
    result.undeliverable_files = {"a.xml": "projection failed"}
    with pytest.raises(ConfigurationError, match="undeliverable"):
        result.write(target, allow_partial=True)
    assert old.read_bytes() == b"old XML"
    assert len(list(target.iterdir())) == 1


def test_a_valid_long_filename_survives_atomic_write(
    result: CorrectionResult, tmp_path: Path
) -> None:
    name = "x" * 246 + ".xml"
    content = result.corrected_files["sample.xml"]
    result.corrected_files = {name: content}
    target = tmp_path / "output"

    written = result.write(target)

    assert (target / name).read_bytes() == content
    assert {path.name for path in written} == {name, "report.json"}
    assert {path.name for path in target.iterdir()} == {name, "report.json"}


@pytest.mark.parametrize(
    "source_name",
    ["report.json", "volume/report.json", "REPORT.JSON", "sidecar.json"],
)
@pytest.mark.parametrize("has_sidecar", [False, True])
def test_metadata_names_are_reserved_before_any_write(
    result: CorrectionResult,
    tmp_path: Path,
    source_name: str,
    has_sidecar: bool,
) -> None:
    result.corrected_files = {"first.xml": b"first", source_name: b"source XML"}
    if has_sidecar:
        _with_sidecar(result)
    target = tmp_path / "new-output"

    with pytest.raises(ConfigurationError, match="reserved"):
        result.write(target)

    assert not target.exists()


@pytest.mark.parametrize(
    ("first", "second"),
    [("a.xml", "A.xml"), ("été.xml", "e\u0301te\u0301.xml")],
)
def test_portable_filename_aliases_are_refused_before_any_write(
    result: CorrectionResult, tmp_path: Path, first: str, second: str
) -> None:
    result.corrected_files = {first: b"first", second: b"second"}
    target = tmp_path / "new-output"

    with pytest.raises(ConfigurationError, match="overwrite"):
        result.write(target)

    assert not target.exists()


@pytest.mark.parametrize("source_name", ["", ".", "..", "/", "volume/.."])
def test_empty_or_directory_basename_is_refused_before_any_write(
    result: CorrectionResult, tmp_path: Path, source_name: str
) -> None:
    result.corrected_files = {"first.xml": b"first", source_name: b"source XML"}
    target = tmp_path / "new-output"

    with pytest.raises(ConfigurationError, match="filename"):
        result.write(target)

    assert not target.exists()


@pytest.mark.parametrize("filename", ["sample.xml", "report.json", "sidecar.json"])
@pytest.mark.parametrize("dangling", [False, True])
def test_symlink_destination_is_refused_before_other_files_are_written(
    result: CorrectionResult, tmp_path: Path, filename: str, dangling: bool
) -> None:
    _with_sidecar(result)
    result.corrected_files = {"first.xml": b"first", **result.corrected_files}
    target = tmp_path / "output"
    target.mkdir()
    first = target / "first.xml"
    first.write_bytes(b"previous output")
    outside = tmp_path / "outside"
    if not dangling:
        outside.write_bytes(b"unrelated document")
    destination = target / filename
    destination.symlink_to(outside)

    with pytest.raises(ConfigurationError, match="symbolic link"):
        result.write(target)

    assert destination.is_symlink()
    assert first.read_bytes() == b"previous output"
    assert {path.name for path in target.iterdir()} == {"first.xml", filename}
    if dangling:
        assert not outside.exists()
    else:
        assert outside.read_bytes() == b"unrelated document"


def test_regular_outputs_can_still_be_overwritten(
    result: CorrectionResult, tmp_path: Path
) -> None:
    _with_sidecar(result)
    target = tmp_path / "output"
    target.mkdir()
    names = ["sample.xml", "report.json", "sidecar.json"]
    for name in names:
        (target / name).write_bytes(b"previous output")
        (target / name).chmod(0o640)

    written = result.write(target)

    assert [path.name for path in written] == names
    assert (target / "sample.xml").read_bytes() == result.corrected_files["sample.xml"]
    assert json.loads(
        (target / "report.json").read_bytes()
    ) == result.report.model_dump(mode="json")
    assert result.report.sidecar is not None
    assert json.loads((target / "sidecar.json").read_bytes()) == [
        entry.model_dump(mode="json") for entry in result.report.sidecar
    ]
    assert {path.name for path in target.iterdir()} == set(names)
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o640 for path in written)


@pytest.mark.parametrize("filename", ["sample.xml", "report.json", "sidecar.json"])
def test_link_appearing_after_preflight_cannot_overwrite_its_target(
    result: CorrectionResult,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    filename: str,
) -> None:
    _with_sidecar(result)
    target = tmp_path / "output"
    outside = tmp_path / "outside"
    outside.write_bytes(b"unrelated document")
    mkdir = Path.mkdir

    def create_directory_then_link(path: Path, *args: object, **kwargs: object) -> None:
        mkdir(path, *args, **kwargs)
        if path == target:
            (target / filename).symlink_to(outside)

    monkeypatch.setattr(Path, "mkdir", create_directory_then_link)

    result.write(target)

    assert outside.read_bytes() == b"unrelated document"
    assert not (target / filename).is_symlink()


def test_failed_replacement_preserves_previous_file_and_removes_temporary(
    result: CorrectionResult, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "output"
    target.mkdir()
    destination = target / "sample.xml"
    destination.write_bytes(b"previous output")

    def fail_replace(path: Path, destination: Path) -> Path:
        raise OSError("replacement failed")

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(OSError, match="replacement failed"):
        result.write(target)

    assert destination.read_bytes() == b"previous output"
    assert list(target.iterdir()) == [destination]
