"""Schema diagnostics alone do not establish IDREF integrity."""

from lxml import etree
import pytest

from saknussemm.errors import ProjectionError
from saknussemm.formats._references import (
    dangling_references,
    reference_baseline,
    require_no_new_dangling_references,
)


@pytest.mark.parametrize(
    "attribute",
    ["REF", "STYLEREFS", "TAGREFS", "PROCESSINGREFS", "IDNEXT", "PROCESSING"],
)
def test_a_new_target_cannot_hide_behind_one_existing_missing_target(attribute):
    root = etree.fromstring(
        f'<alto><String ID="owner" {attribute}="old_missing"/></alto>'.encode()
    )
    baseline = dangling_references(root)
    root[0].set(attribute, "new_missing")
    with pytest.raises(ProjectionError, match="new_missing"):
        require_no_new_dangling_references(root, baseline)


def test_moving_a_missing_reference_to_another_owner_is_new_damage():
    root = etree.fromstring(
        b'<alto><String ID="first" STYLEREFS="missing"/><String ID="second"/></alto>'
    )
    baseline = dangling_references(root)
    del root[0].attrib["STYLEREFS"]
    root[1].set("STYLEREFS", "missing")
    with pytest.raises(ProjectionError, match="second"):
        require_no_new_dangling_references(root, baseline)


def test_each_idrefs_token_is_checked_but_fileid_remains_an_opaque_string():
    root = etree.fromstring(
        b'<alto><String ID="owner" STYLEREFS="exists missing" FILEID="external"/>'
        b'<TextStyle ID="exists"/></alto>'
    )
    assert {key[-1] for key in dangling_references(root)} == {"missing"}


def test_page_region_reference_loss_is_checked():
    root = etree.fromstring(
        b'<PcGts><Page><ReadingOrder><RegionRef regionRef="r1"/></ReadingOrder>'
        b'<TextRegion id="r1"/></Page></PcGts>'
    )
    baseline = dangling_references(root)
    root[0].remove(root[0][-1])
    with pytest.raises(ProjectionError, match="r1"):
        require_no_new_dangling_references(root, baseline)


def test_foreign_id_does_not_resolve_a_native_reference():
    root = etree.fromstring(
        b'<alto xmlns="urn:alto" xmlns:v="urn:vendor">'
        b'<ElementRef ID="ref" REF="missing"/><v:annotation ID="missing"/></alto>'
    )
    assert {key[-1] for key in dangling_references(root)} == {"missing"}


def test_an_id_less_owner_keeps_its_already_missing_style_after_receiving_an_id():
    # The rewriter gives an ID-less String an ID. Its unresolved style was
    # unresolved in the source: nothing new is broken.
    root = etree.fromstring(
        b'<alto><String STYLEREFS="already_missing"/><String ID="W2"/></alto>'
    )
    baseline = reference_baseline(root)
    root[0].set("ID", "L1_STR_0000")
    require_no_new_dangling_references(root, baseline)


def test_a_second_reference_to_an_already_missing_target_is_still_new_damage():
    root = etree.fromstring(
        b'<alto><String STYLEREFS="already_missing"/><String ID="W2"/></alto>'
    )
    baseline = reference_baseline(root)
    root[0].set("ID", "L1_STR_0000")
    root[1].set("STYLEREFS", "already_missing")
    with pytest.raises(ProjectionError, match="W2"):
        require_no_new_dangling_references(root, baseline)


def test_a_target_the_source_declared_cannot_vanish_even_for_a_new_owner():
    root = etree.fromstring(
        b'<alto><TextStyle ID="s1"/><String STYLEREFS="s1"/></alto>'
    )
    baseline = reference_baseline(root)
    root.remove(root[0])
    root[0].set("ID", "L1_STR_0000")
    with pytest.raises(ProjectionError, match="s1"):
        require_no_new_dangling_references(root, baseline)


def test_the_native_pipeline_delivers_a_file_whose_id_less_word_kept_its_missing_style(
    tmp_path,
):
    from saknussemm.facade import correct_sync, load
    from saknussemm.producers.rules import RulesProducer, SubstitutionRule
    from tests.test_alto_annotation_integrity import _source

    raw = _source(4).replace(b'ID="W1"', b'STYLEREFS="already_missing"')
    path = tmp_path / "page.xml"
    path.write_bytes(raw)
    result = correct_sync(
        load(path), producer=RulesProducer([SubstitutionRule("cat dog", "cat new dog")])
    )
    assert result.undeliverable_files == {}
    out = etree.fromstring(result.corrected_files[path.name])
    ns = "{http://www.loc.gov/standards/alto/ns-v4#}"
    strings = [dict(e.attrib) for e in out.iter(f"{ns}String")]
    assert [s["CONTENT"] for s in strings] == ["cat", "new", "dog"]
    assert strings[0]["STYLEREFS"] == "already_missing"
    assert "STYLEREFS" not in strings[1]
