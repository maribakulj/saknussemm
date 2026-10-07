"""Check known XML ID references independently of libxml's XSD diagnostics."""

from collections import Counter

from lxml import etree

from saknussemm.errors import ProjectionError


def dangling_references(root: etree._Element) -> Counter[tuple[str, str, str, str]]:
    """Count unresolved references by owner, attribute and target.

    Existing defects must not mask a different newly broken reference. XML
    IDs identify owners where available; otherwise their tree path does.
    FILEID is deliberately excluded: ALTO defines it as a string, not IDREF.
    """
    name = etree.QName(root)
    attributes: tuple[str, ...]
    if name.localname == "alto":
        id_attr = "ID"
        attributes = (
            "REF",
            "STYLEREFS",
            "TAGREFS",
            "PROCESSINGREFS",
            "IDNEXT",
            "PROCESSING",
        )
    elif name.localname == "PcGts":
        id_attr = "id"
        attributes = ("regionRef",)
    else:
        return Counter()
    elements = [
        element
        for element in root.iter()
        if isinstance(element.tag, str)
        and etree.QName(element).namespace == name.namespace
    ]
    ids = {element.get(id_attr) for element in elements if element.get(id_attr)}
    tree = root.getroottree()
    missing: Counter[tuple[str, str, str, str]] = Counter()
    for element in elements:
        for attribute in attributes:
            for target in element.get(attribute, "").split():
                if target not in ids:
                    owner = element.get(id_attr) or tree.getpath(element)
                    missing[(element.tag, owner, attribute, target)] += 1
    return missing


def require_no_new_dangling_references(
    root: etree._Element,
    baseline: Counter[tuple[str, str, str, str]],
) -> None:
    """Refuse new damage without guessing how a removed target should map."""
    introduced = dangling_references(root) - baseline
    if introduced:
        details = "; ".join(
            f"{owner}/@{attribute} -> {target} (x{count})"
            for (_, owner, attribute, target), count in sorted(introduced.items())
        )
        raise ProjectionError(f"output introduces dangling XML references: {details}")
