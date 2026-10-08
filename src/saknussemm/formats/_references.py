"""Check known XML ID references independently of libxml's XSD diagnostics."""

from collections import Counter
from dataclasses import dataclass, field

from lxml import etree

from saknussemm.errors import ProjectionError

ReferenceKey = tuple[str, str, str, str]


def _reference_attributes(root: etree._Element) -> tuple[str, tuple[str, ...]]:
    name = etree.QName(root)
    if name.localname == "alto":
        # FILEID is deliberately excluded: ALTO defines it as a string, not IDREF.
        return "ID", (
            "REF",
            "STYLEREFS",
            "TAGREFS",
            "PROCESSINGREFS",
            "IDNEXT",
            "PROCESSING",
        )
    if name.localname == "PcGts":
        return "id", ("regionRef",)
    return "", ()


def _native_elements(root: etree._Element) -> list[etree._Element]:
    namespace = etree.QName(root).namespace
    return [
        element
        for element in root.iter()
        if isinstance(element.tag, str) and etree.QName(element).namespace == namespace
    ]


def _ids(root: etree._Element) -> frozenset[str]:
    id_attr, attributes = _reference_attributes(root)
    if not attributes:
        return frozenset()
    return frozenset(
        value for element in _native_elements(root) if (value := element.get(id_attr))
    )


def dangling_references(root: etree._Element) -> Counter[ReferenceKey]:
    """Count unresolved references by owner, attribute and target.

    Existing defects must not mask a different newly broken reference. XML
    IDs identify owners where available; otherwise their tree path does.
    """
    id_attr, attributes = _reference_attributes(root)
    if not attributes:
        return Counter()
    elements = _native_elements(root)
    ids = {element.get(id_attr) for element in elements if element.get(id_attr)}
    tree = root.getroottree()
    missing: Counter[ReferenceKey] = Counter()
    for element in elements:
        for attribute in attributes:
            for target in element.get(attribute, "").split():
                if target not in ids:
                    owner = element.get(id_attr) or tree.getpath(element)
                    missing[(element.tag, owner, attribute, target)] += 1
    return missing


@dataclass(frozen=True)
class ReferenceBaseline:
    """What the source already failed to resolve, and which IDs it declared.

    The IDs let the check tell a reference that lost its target (the target
    was in the source and is gone) from a reference the source already left
    unresolved and that merely changed owner key because the rewriter gave
    an ID-less element an ID.
    """

    missing: Counter[ReferenceKey] = field(default_factory=Counter)
    ids: frozenset[str] = frozenset()


def reference_baseline(root: etree._Element) -> ReferenceBaseline:
    return ReferenceBaseline(dangling_references(root), _ids(root))


def _by_target(missing: Counter[ReferenceKey]) -> Counter[tuple[str, str, str]]:
    totals: Counter[tuple[str, str, str]] = Counter()
    for (tag, _, attribute, target), count in missing.items():
        totals[(tag, attribute, target)] += count
    return totals


def require_no_new_dangling_references(
    root: etree._Element,
    baseline: ReferenceBaseline | Counter[ReferenceKey],
) -> None:
    """Refuse new damage without guessing how a removed target should map.

    A plain Counter baseline keeps the strict owner-keyed comparison. With a
    :class:`ReferenceBaseline`, an unresolved reference carried by an element
    the source never identified (so its owner key changed when it received
    an ID) is tolerated as long as the target was already unresolved in the
    source and the number of such references did not grow. A target the
    source did declare, or a previously identified owner that gained the
    reference, is always new damage.
    """
    output = dangling_references(root)
    if isinstance(baseline, Counter):
        damage = output - baseline
    else:
        introduced = output - baseline.missing
        before = _by_target(baseline.missing)
        after = _by_target(output)
        damage = Counter(
            {
                key: count
                for key, count in introduced.items()
                if key[1] in baseline.ids
                or key[3] in baseline.ids
                or after[(key[0], key[2], key[3])] > before[(key[0], key[2], key[3])]
            }
        )
    if damage:
        details = "; ".join(
            f"{owner}/@{attribute} -> {target} (x{count})"
            for (_, owner, attribute, target), count in sorted(damage.items())
        )
        raise ProjectionError(f"output introduces dangling XML references: {details}")
