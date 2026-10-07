"""Schema diagnostics alone do not establish IDREF integrity."""

from lxml import etree
import pytest

from saknussemm.errors import ProjectionError
from saknussemm.formats._references import (
    dangling_references,
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
