"""The order of the finalisation passes decides what ships, and is asserted
on the production path (`RM-01`, `H-3`).

``core/finalize.py`` runs four document-wide passes and its docstring says
outright that "their ORDER is the whole content of this module". Until
`RM-01` that was the only thing holding it: no type, no assertion, no test.
A contributor who reordered two while moving code between modules broke a
rule that existed only in prose — and the suite stayed green, because every
other test in this package checks the FINAL state of a run that used the
right order.

Two tests, and they answer different questions.

:func:`test_pass_order_changes_the_delivered_text` says WHY the order
matters: permuting two passes does not renumber a report, it changes the
corrected TEXT of a line and ships a correction the canonical order
rejects. It builds its own sequences, so it demonstrates the interaction
without asserting anything about production.

:func:`test_finalize_document_delivers_the_canonical_outcome` is the guard.
It runs the real ``_finalize_document`` on that same document and pins the
outcome, so a swap inside the shipped function turns it red.

`RM-01` guarded this with a runtime token instead — an object threaded
through four private functions whose only caller already calls them in
order, checked by a test that read the source with ``ast`` to confirm the
threading. `H-3` retired both once the assertion above was shown, by
mutation, to catch the same swap with the token fully neutralised.
"""

from __future__ import annotations

from saknussemm.core.acceptance import _global_adjacency_pass, _loss_policy_pass
from saknussemm.core.finalize import _finalize_document, _preserve_break_chars
from saknussemm.core.schemas import GuardConfig, LineStatus, LossPolicy, ReviewPolicy

from tests.decision._state import document, line, snapshot

#: A gate that is OFF by default (`RM-04` territory) but on a supported
#: setting. It is the cheapest way to make the loss pass do something on
#: ALTO: ``strict`` needs ``word_count``, which only the PAGE parser fills.
_GATED = LossPolicy(min_alignment_score=0.6)
_GUARDS = GuardConfig()


def _two_lines_one_gated():
    """Two adjacent lines proposing the SAME correction from clearly
    different sources — an adjacent duplicate — where only the first one's
    correction changes its word count and so trips the token_realign gate.

    That asymmetry is what makes the interaction visible: whichever pass
    runs first removes the other's evidence.
    """
    return document(
        [
            # 3 source words -> 4 corrected: the realign gate fires.
            line(1, "le chat noir", "LE CHAT GRIS TRES"),
            # 4 source words -> 4 corrected: the gate does NOT fire, so this
            # line only ever reverts as somebody's duplicate.
            line(2, "une souris grise ici", "LE CHAT GRIS TRES"),
        ]
    )


def _run_canonical():
    manifest, all_lines, traces = _two_lines_one_gated()
    _global_adjacency_pass(
        guard_config=_GUARDS,
        document_manifest=manifest,
        all_lines=all_lines,
        traces=traces,
    )
    _preserve_break_chars(manifest)
    sidecar = _loss_policy_pass(
        loss_policy=_GATED,
        document_manifest=manifest,
        all_lines=all_lines,
        traces=traces,
    )
    return snapshot(manifest, traces), sidecar


def _run_loss_first():
    """The loss gate before the adjacency pass — one swap, nothing else."""
    manifest, all_lines, traces = _two_lines_one_gated()
    sidecar = _loss_policy_pass(
        loss_policy=_GATED,
        document_manifest=manifest,
        all_lines=all_lines,
        traces=traces,
    )
    _global_adjacency_pass(
        guard_config=_GUARDS,
        document_manifest=manifest,
        all_lines=all_lines,
        traces=traces,
    )
    _preserve_break_chars(manifest)
    return snapshot(manifest, traces), sidecar


def test_pass_order_changes_the_delivered_text() -> None:
    """Swapping two passes changes what the file says, not just what the
    report counts.

    Canonical order — the adjacency pass sees both lines still holding
    their pre-revert corrections, recognises the duplicate, and reverts
    BOTH. Neither correction ships, and neither is preserved: a duplicate
    is discarded, not set aside.

    Loss-first — the gate reverts ``L1`` before the adjacency pass runs.
    ``L1`` now presents its source text, so the two lines no longer look
    like the same correction, the duplicate is never detected, and ``L2``
    SHIPS a correction the canonical order rejects.

    That is the shape of the defect: not a wrong number in a report, a
    different sentence in the delivered XML.
    """
    canonical, canonical_sidecar = _run_canonical()
    loss_first, loss_first_sidecar = _run_loss_first()

    # Canonical: both lines fall back, as duplicates of each other.
    assert canonical["L1"] == (
        "le chat noir",
        "fallback",
        "adjacent_duplicate_detected",
    )
    assert canonical["L2"] == (
        "une souris grise ici",
        "fallback",
        "adjacent_duplicate_detected",
    )
    assert canonical_sidecar == []

    # Loss-first: L1 is gated, and its revert hides the duplicate, so L2
    # keeps a correction the canonical order threw away.
    assert loss_first["L1"][0] == "le chat noir"
    assert loss_first["L1"][1] == "fallback"
    assert loss_first["L1"][2] is not None
    assert loss_first["L1"][2].startswith("token_realign:")
    assert loss_first["L2"] == ("LE CHAT GRIS TRES", "corrected", None)
    assert [entry.line_id for entry in loss_first_sidecar] == ["L1"]

    # Stated once, plainly, so a reader does not have to diff the two dicts.
    assert canonical["L2"][0] != loss_first["L2"][0], (
        "the two orders must differ in delivered text — if they no longer "
        "do, this scenario stopped demonstrating anything and needs "
        "rebuilding, not deleting"
    )


def test_finalize_document_delivers_the_canonical_outcome() -> None:
    """The production path itself, on the scenario that separates the orders.

    The two tests above build their own sequences, so neither of them reads
    ``_finalize_document``: they establish that the order matters, not that
    the shipped one is right. This one runs the real function on the same
    fixture and asserts the canonical outcome — both lines reverted as
    duplicates of each other, nothing set aside.

    That makes the order a BEHAVIOURAL guarantee rather than a structural
    one. Swap two passes inside ``_finalize_document`` and ``L2`` ships
    ``LE CHAT GRIS TRES`` while ``L1`` lands in the sidecar; this assertion
    is what turns red. Verified by mutation on 2026-09-02 — both halves
    fail when the loss pass is moved first — which is the evidence that
    retired the runtime order token it replaces.
    """
    manifest, all_lines, traces = _two_lines_one_gated()
    decisions, sidecar = _finalize_document(
        guard_config=_GUARDS,
        loss_policy=_GATED,
        review_policy=ReviewPolicy(),
        document_manifest=manifest,
        all_lines=all_lines,
        traces=traces,
    )

    assert snapshot(manifest, traces) == {
        "L1": ("le chat noir", "fallback", "adjacent_duplicate_detected"),
        "L2": ("une souris grise ici", "fallback", "adjacent_duplicate_detected"),
    }
    assert sidecar == [], (
        "a line reached the sidecar, so the loss gate saw a correction the "
        "adjacency pass should already have reverted — the passes ran in "
        "the wrong order"
    )
    assert decisions.fallback_lines == 2
    assert all(
        decision.status is LineStatus.FALLBACK for decision in decisions.decisions
    )
