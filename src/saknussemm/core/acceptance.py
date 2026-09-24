"""Deciding whether a proposal may stand, and what falls back with it.

Five passes, each taking the policy it consults as an explicit argument
rather than reading it off the engine: "given THIS guard config, is this
line acceptable?" is a question about a line and a policy, not about a
run.

``_apply_unit_reverts`` is the one they share: a member of a hyphen unit
never falls back alone (ADR-010).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from saknussemm.core import decide
from saknussemm.core.alignment import align_tokens
from saknussemm.core.guards import (
    check_adjacent_duplicates,
    check_boundary_migration,
    check_line,
)
from saknussemm.core.identity import LineRef, line_ref
from saknussemm.core.pairing import ends_with_break_mark, forward_ref, pair_ref
from saknussemm.core.reconcile import _lookup_ref
from saknussemm.core.review import find_review_referrals
from saknussemm.core.traces import _set_trace
from saknussemm.core.units import derive_hyphen_groups, hyphen_group_by_line
from saknussemm.core.schemas import (
    DocumentManifest,
    GuardConfig,
    HyphenRole,
    LineManifest,
    LineStatus,
    LineTrace,
    LossPolicy,
    ReviewPolicy,
    SidecarEntry,
)


@dataclass
class _FinalizeOrder:
    """Proof that the document-wide passes ran in the order they must.

    ``core/finalize.py`` runs four passes whose ORDER is their whole
    content, and until now that contract lived in a docstring: calling
    them out of order was not refused, not detected, and not reported —
    it silently produced different output. Not different counters:
    different TEXT. The loss gate run before the adjacency pass reverts
    one line of a duplicate pair, which erases the evidence of
    duplication, so the other line ships a correction the canonical
    order rejects (``tests/decision/test_finalize_pass_order.py``).

    So the contract becomes a token. Each pass declares what must have
    run before it and refuses otherwise. One instance per run, created
    in :func:`_finalize_document` and never shared, so the guard cannot
    become the global state ADR-011 spent a slice removing — two
    concurrent runs each carry their own.

    Lives here rather than in ``finalize`` because three of the four
    ordered passes are in this module and ``finalize`` already imports
    it; the reverse would be a cycle.

    A wrong order is an engine bug, not bad input, so it raises
    ``RuntimeError`` — deliberately NOT a ``SaknussemmError``, which the
    chunk loop is allowed to absorb (ADR-008). Same choice, same reason,
    as ``units.split_forward_link``.

    ``order=None`` on every pass means unchecked. Production never does
    that — a static test asserts :func:`_finalize_document` threads a
    token into all of them — but a test that needs to DEMONSTRATE the
    divergence has to be able to run the wrong order on purpose.
    """

    _done: list[str] = field(default_factory=list)

    def entering(self, step: str, *, requires: tuple[str, ...] = ()) -> None:
        missing = [name for name in requires if name not in self._done]
        if missing:
            raise RuntimeError(
                f"finalisation pass {step!r} ran before {missing} — the "
                "document-wide passes have a required order and this one "
                f"is not it (ran so far: {self._done}). See "
                "core/finalize.py for what each pass depends on."
            )
        if step in self._done:
            raise RuntimeError(
                f"finalisation pass {step!r} ran twice in one run — each "
                "pass reverts against what the previous left behind, so a "
                "repeat is not idempotent."
            )
        self._done.append(step)


def _entering(
    order: _FinalizeOrder | None,
    step: str,
    *,
    requires: tuple[str, ...] = (),
) -> None:
    """Announce a pass to the run's order token, if there is one.

    ``None`` means unchecked — only tests pass it (see
    ``tests/decision/test_finalize_pass_order.py``, which has to be able
    to run the wrong order to show what the guard prevents).
    """
    if order is not None:
        order.entering(step, requires=requires)


def _margin_candidates(
    lm: LineManifest,
    all_lines_by_id: dict[str, LineManifest],
    *,
    page_scope: bool,
) -> tuple[str | None, str | None, list[str]]:
    """The texts the neighbour margin is held against for ``lm``.

    The previous and next line as before; under ``attachment_scope="page"``
    every other line of the page as well — ``all_lines_by_id`` is the
    workspace's page index, so this IS the page.
    """
    prev_ocr = (
        all_lines_by_id[lm.prev_line_id].ocr_text
        if lm.prev_line_id and lm.prev_line_id in all_lines_by_id
        else None
    )
    next_ocr = (
        all_lines_by_id[lm.next_line_id].ocr_text
        if lm.next_line_id and lm.next_line_id in all_lines_by_id
        else None
    )
    if not page_scope:
        return prev_ocr, next_ocr, []
    excluded = {lm.line_id, lm.prev_line_id, lm.next_line_id}
    return (
        prev_ocr,
        next_ocr,
        [o.ocr_text for o in all_lines_by_id.values() if o.line_id not in excluded],
    )


def _apply_line_acceptance(
    *,
    guard_config: GuardConfig,
    chunk_lines: list[LineManifest],
    text_by_id: dict[str, str],
    all_lines_by_id: dict[str, LineManifest],
    traces: dict[LineRef, LineTrace] | None,
    cross_page_partners: dict[LineRef, LineManifest] | None = None,
    reconciled: frozenset[LineRef] = frozenset(),
) -> None:
    """Apply the per-line acceptance policy on lines not already
    reconciled as hyphen pairs — and the attachment guards on those.

    ``reconciled`` names the members stage B accepted in THIS chunk;
    they alone are revisited (:func:`_attachment_of_reconciled`). Any
    other line that already holds a decision is skipped, as before.
    Two guards in order on the rest: an orphan PART1/BOTH whose OCR
    ends in '-' but whose correction does not falls back to keep the
    marker; then :func:`check_line` with prev/next context — and under
    ``attachment_scope="page"`` every other line of the page, which
    ``all_lines_by_id`` IS (the workspace's index).
    """
    page_scope = guard_config.attachment_scope == "page"
    reverts: dict[LineRef, str] = {}
    for lm in chunk_lines:
        if lm.corrected_text is not None:
            if line_ref(lm) in reconciled:
                reason = _attachment_of_reconciled(
                    lm,
                    guard_config=guard_config,
                    all_lines_by_id=all_lines_by_id,
                    traces=traces,
                )
                if reason is not None:
                    reverts[line_ref(lm)] = reason
            continue
        corrected = text_by_id.get(lm.line_id)
        if corrected is None:
            continue

        # The repertoire, not the ASCII hyphen. This guard read
        # `endswith("-")`, so a line ending in ⸗ or ¬ whose correction
        # dropped the mark was NOT pulled back: 32 of the 363
        # hyphenated lines in the repo's corpora end in one of those.
        if (
            lm.hyphen_role in (HyphenRole.PART1, HyphenRole.BOTH)
            and ends_with_break_mark(lm.ocr_text)
            and not ends_with_break_mark(corrected)
        ):
            decide.fall_back(lm, reason="orphan_hyphen_completed", traces=traces)
            continue

        fallen_partner = _partner_fell(lm, all_lines_by_id, cross_page_partners)
        if fallen_partner:
            decide.fall_back(lm, reason="hyphen_partner_fell_back", traces=traces)
            continue

        prev_ocr, next_ocr, other_ocr = _margin_candidates(
            lm, all_lines_by_id, page_scope=page_scope
        )
        result = check_line(
            lm.ocr_text,
            corrected,
            prev_ocr,
            next_ocr,
            other_ocr=other_ocr,
            config=guard_config,
        )
        if result.accepted:
            decide.accept(lm, result.text, traces=traces)
        else:
            # Every rejection branch of ``check_line`` returns
            # ``text=source_ocr`` and a non-None reason, so ``fall_back``
            # writes exactly the text this site used to write. Pinned by
            # ``tests/decision/test_acceptance_translation.py`` — the
            # translation is only safe while that holds.
            decide.fall_back(lm, reason=result.reason or "rejected", traces=traces)
        # The guard's once-computed metrics ride the trace to
        # the report's decision stage, accepted or not.
        _set_trace(traces, lm, proposal_features=result.features)
    _revert_units(reverts, all_lines_by_id, cross_page_partners, traces)


def _partner_fell(
    lm: LineManifest,
    all_lines_by_id: dict[str, LineManifest],
    cross_page_partners: dict[LineRef, LineManifest] | None,
) -> bool:
    """ADR-010 (unit fallback atomicity): a hyphen member whose partner
    already fell back (its chunk was rejected — the cross-page case: this
    side reaches acceptance because the partner sits in no reconcile pass
    of THIS chunk) keeps its source text too.

    Both slots, DIRECT partners only — deliberately not the transitive
    unit. Widening this to the whole chain is defensible under unit
    atomicity but changes behaviour on 3+-member chains, so it belongs
    behind a measurement, not inside a refactor.
    """
    return any(
        partner is not None and partner.status is LineStatus.FALLBACK
        for partner in (
            _lookup_ref(
                ref,
                page_id=lm.page_id,
                line_by_id=all_lines_by_id,
                cross_page_partners=cross_page_partners,
            )
            for ref in (pair_ref(lm), forward_ref(lm))
        )
    )


def _revert_units(
    reverts: dict[LineRef, str],
    all_lines_by_id: dict[str, LineManifest],
    cross_page_partners: dict[LineRef, LineManifest] | None,
    traces: dict[LineRef, LineTrace] | None,
) -> None:
    """A refused member pulls its whole unit (ADR-010): the page index
    plus the cross-page partners IS every line a unit can span."""
    if not reverts:
        return
    all_lines = {line_ref(o): o for o in all_lines_by_id.values()}
    all_lines.update(cross_page_partners or {})
    _apply_unit_reverts(
        reverts=reverts,
        all_lines=all_lines,
        traces=traces,
        atomicity_reason="hyphen_unit_fallback",
    )


def _attachment_of_reconciled(
    lm: LineManifest,
    *,
    guard_config: GuardConfig,
    all_lines_by_id: dict[str, LineManifest],
    traces: dict[LineRef, LineTrace] | None,
) -> str | None:
    """Stage C's floor and margin on a hyphen member stage B has accepted.

    The reconciler judges the two halves of a cut word against each
    other — whether text migrated across the break — and nothing else.
    It cannot see that a half carries the text of a line elsewhere on
    the page, and until VR-11 nothing else looked either: a reconciled
    member skipped ``check_line`` entirely, so a PART1 reading
    ``ce que notre grand mor-`` under a source that said ``au. nt comme
    orateur, 'une situation in-`` was delivered as corrected while the
    page held an OCR line ``ce que notre grand mo`` (NewsEye 0253902,
    replayed: ``check_line`` refuses it at 0.95 against 0.31).

    Returns the refusal reason, or ``None`` when the member stands. The
    absorption guard stays off: stage B owns the pair's word split. A
    member the reconciler left at its source text is not judged — it
    would pass as identity anyway.
    """
    if lm.corrected_text == lm.ocr_text:
        return None
    prev_ocr, next_ocr, other_ocr = _margin_candidates(
        lm, all_lines_by_id, page_scope=guard_config.attachment_scope == "page"
    )
    result = check_line(
        lm.ocr_text,
        lm.corrected_text or "",
        prev_ocr,
        next_ocr,
        other_ocr=other_ocr,
        config=guard_config,
        absorption=False,
    )
    _set_trace(traces, lm, proposal_features=result.features)
    return None if result.accepted else (result.reason or "rejected")


def _global_adjacency_pass(
    *,
    guard_config: GuardConfig,
    document_manifest: DocumentManifest,
    all_lines: dict[LineRef, LineManifest],
    traces: dict[LineRef, LineTrace] | None,
    order: _FinalizeOrder | None = None,
) -> None:
    """ONE adjacent-duplicate pass over the whole document.

    The canonical sequence is pages in manifest order, lines in page
    order, broken at source-file transitions: file A's last physical
    line is not adjacent to file B's first, and comparing them could
    spuriously revert either. Keys are :class:`LineRef`s, so the
    bare-id ambiguity that forced the old page-seam pass to skip
    colliding seams (ADR-007) cannot arise — every seam is checked.
    Runs after the page loop: no earlier pass has reverted anything,
    so the live ``corrected_text`` IS the pre-revert accepted
    correction, and a run of three identical corrections straddling
    any seam is seen whole on one comparison basis.
    """
    _entering(order, "adjacency")
    reverts: dict[LineRef, str] = {}
    segment: list[tuple[LineRef, str, str]] = []
    prev_file: str | None = None

    def flush() -> None:
        if len(segment) > 1:
            reverts.update(check_adjacent_duplicates(segment, config=guard_config))
            # A word migrating across a line seam is invisible to the
            # pair-level guards when the OCR mangled the break glyph
            # (the line was never paired). This line-role-agnostic pass
            # catches it; reverts merge — a line flagged by either guard
            # falls back, atomically with its hyphen unit below.
            reverts.update(check_boundary_migration(segment, config=guard_config))
        segment.clear()

    for page in document_manifest.pages:
        if page.source_file != prev_file:
            flush()
            prev_file = page.source_file
        for lm in page.lines:
            segment.append(
                (
                    line_ref(lm),
                    lm.ocr_text,
                    lm.corrected_text if lm.corrected_text is not None else lm.ocr_text,
                )
            )
    flush()

    _apply_unit_reverts(reverts=reverts, all_lines=all_lines, traces=traces)


def _loss_policy_pass(
    *,
    loss_policy: LossPolicy,
    document_manifest: DocumentManifest,
    all_lines: dict[LineRef, LineManifest],
    traces: dict[LineRef, LineTrace] | None,
    order: _FinalizeOrder | None = None,
) -> list[SidecarEntry]:
    """Loss policy gates (ADR-012 strict; token_realign).

    **STRICT**: reject corrections that cannot project without
    losing word granularity. The PAGE rewriter drops a line's
    ``Word`` children when the corrected word count diverges from
    the markup's (6.2 P4 slow path) — the one predictable,
    decision-relevant format loss. ``LineManifest.word_count``
    carries the markup's count from parse time, so the check runs in
    the pure core, BEFORE the decisions materialize: a rejected line
    falls back to source (whole hyphen unit, ADR-010) and its
    rewrite becomes untouched — the source geometry survives.

    **TOKEN_REALIGN** (``min_alignment_score`` set, not strict): a
    word-count-changing correction whose tokens cannot be aligned
    onto the source tokens with at least the threshold score — or
    ANY correction that raises the move flag — is not projected.
    The line reverts like strict, but the correction is preserved as
    a :class:`SidecarEntry` (returned; surfaced on
    ``CorrectionReport.sidecar``) instead of lost.

    Under REPORT (default) this pass is a no-op: the loss projects,
    is counted, and is attributed per line.
    """
    _entering(order, "loss_policy", requires=("adjacency", "break_chars"))
    if loss_policy.strict:
        reverts: dict[LineRef, str] = {}
        for page in document_manifest.pages:
            for lm in page.lines:
                if lm.word_count is None or lm.corrected_text is None:
                    continue
                if lm.corrected_text == lm.ocr_text:
                    continue  # identity projects untouched
                n_corrected = len(lm.corrected_text.split())
                if n_corrected != lm.word_count:
                    reverts[line_ref(lm)] = (
                        "format_loss: corrected word count "
                        f"{n_corrected} != source Word markup {lm.word_count} "
                        "— unprojectable without dropping word geometry "
                        "(LossPolicy strict)"
                    )
        _apply_unit_reverts(
            reverts=reverts,
            all_lines=all_lines,
            traces=traces,
            atomicity_reason="format_loss_pair_atomicity",
        )
        return []

    threshold = loss_policy.min_alignment_score
    if threshold is None:
        return []

    gate_reverts: dict[LineRef, str] = {}
    evidence: dict[LineRef, tuple[float, bool]] = {}
    snapshots: dict[LineRef, tuple[str, str]] = {}
    for page in document_manifest.pages:
        for lm in page.lines:
            if lm.corrected_text is None or lm.corrected_text == lm.ocr_text:
                continue
            ref = line_ref(lm)
            snapshots[ref] = (lm.ocr_text, lm.corrected_text)
            source_tokens = lm.ocr_text.split()
            target_tokens = lm.corrected_text.split()
            al = align_tokens(source_tokens, target_tokens)
            if al.move_suspected:
                evidence[ref] = (al.score, True)
                gate_reverts[ref] = (
                    "token_realign: suspected word reorder — "
                    "correction preserved in sidecar"
                )
            elif len(target_tokens) != len(source_tokens) and al.score < threshold:
                evidence[ref] = (al.score, False)
                gate_reverts[ref] = (
                    f"token_realign: alignment score {al.score:.2f} < "
                    f"{threshold:.2f} — correction preserved in sidecar"
                )
    reverted = _apply_unit_reverts(
        reverts=gate_reverts,
        all_lines=all_lines,
        traces=traces,
        atomicity_reason="token_realign_pair_atomicity",
    )
    return _sidecar_entries(reverted, snapshots=snapshots, evidence=evidence)


def _sidecar_entries(
    reverted: dict[LineRef, str],
    *,
    snapshots: dict[LineRef, tuple[str, str]],
    evidence: dict[LineRef, tuple[float, bool]],
) -> list[SidecarEntry]:
    """The corrections the token_realign gate set aside, for review.

    A reverted line with no snapshot is a unit member pulled down by a
    flagged partner (ADR-010) whose own text was never corrected — there
    is nothing to preserve, so it contributes no entry.
    """
    entries: list[SidecarEntry] = []
    for ref, reason in reverted.items():
        snapshot = snapshots.get(ref)
        if snapshot is None:
            continue
        source_text, corrected_text = snapshot
        score, moved = evidence.get(ref, (None, False))
        entries.append(
            SidecarEntry(
                page_id=ref.page_id,
                line_id=ref.line_id,
                source_text=source_text,
                corrected_text=corrected_text,
                reason=reason,
                alignment_score=score,
                move_suspected=moved,
            )
        )
    return entries


def _review_pass(
    *,
    review_policy: ReviewPolicy,
    document_manifest: DocumentManifest,
    all_lines: dict[LineRef, LineManifest],
    traces: dict[LineRef, LineTrace] | None,
    order: _FinalizeOrder | None = None,
) -> None:
    """Name the corrections the run cannot establish, and say so.

    LAST of the document-wide passes, and the order is the content here
    as it is for the other three. Every pass before this one can still
    TAKE a correction away; this one only qualifies what is left, so it
    runs when "what is left" is final. Running it earlier would refer
    lines that then fell back — a referral on a line the run reverted
    describes a correction nobody receives.

    It is also the only pass that writes no text. Nothing it does can
    change an output byte, which is why turning referral on is not a
    behavioural change to the artefact and is verified as one by the
    byte-parity corpus rather than asserted here.

    The whole hyphen unit is referred together (ADR-010). Not for the
    fallback reason — no text moves, so nothing can end up mixed — but
    because a referral is a statement about a WORD, and half of a word
    split across two lines is not something a human can review. A member
    pulled in this way carries ``hyphen_unit_review``, which is to
    ``hyphen_unit_fallback`` what this pass is to a revert.
    """
    _entering(order, "review", requires=("adjacency", "break_chars", "loss_policy"))
    if not review_policy.enabled:
        return

    referrals = find_review_referrals(
        (
            (line_ref(lm), lm.ocr_text, lm.corrected_text)
            for page in document_manifest.pages
            for lm in page.lines
            if lm.status is LineStatus.CORRECTED and lm.corrected_text is not None
        ),
        policy=review_policy,
    )
    if not referrals:
        return

    by_line = hyphen_group_by_line(derive_hyphen_groups(all_lines.values()))
    to_refer: dict[LineRef, tuple[str, ...]] = dict(referrals)
    for ref in referrals:
        group = by_line.get(ref)
        if group is None:
            continue
        for member in group.members:
            to_refer.setdefault(member, ("hyphen_unit_review",))

    for ref, reasons in to_refer.items():
        lm = all_lines.get(ref)
        # A pulled unit member may have fallen back for its own reason
        # while the flagged one stood — the pair is not mixed in TEXT
        # (the flagged line kept a correction, this one kept its source),
        # and referring it would claim a correction it does not carry.
        if lm is None or lm.status is not LineStatus.CORRECTED:
            continue
        for reason in reasons:
            decide.refer_for_review(lm, reason=reason, traces=traces)


def _apply_unit_reverts(
    *,
    reverts: dict[LineRef, str],
    all_lines: dict[LineRef, LineManifest],
    traces: dict[LineRef, LineTrace] | None,
    atomicity_reason: str = "adjacent_duplicate_pair_atomicity",
) -> dict[LineRef, str]:
    """Revert flagged lines to OCR — atomically with their WHOLE
    hyphen unit. Returns the FULL revert map (flagged + pulled
    members, each with its reason) so a caller can attribute what
    was reverted — the sidecar builder needs the pulled members too.

    A mixed OCR+corrected pair is the exact state
    ``reconcile_hyphen_pair`` guarantees can never survive, so a
    flagged member pulls every other member of its unit with it —
    cross-page members included, ``all_lines`` being the
    page-qualified document-wide index. Membership is a group lookup
    on THE derivation (ADR-010): the pass runs after planning, when
    the pointer fields are final, so the derived groups cannot be
    stale. A flagged line keeps its own revert reason; pulled
    members are stamped ``atomicity_reason`` (the calling pass's
    vocabulary) unless an earlier fallback path already pinned one.
    """
    if not reverts:
        return {}
    by_line = hyphen_group_by_line(derive_hyphen_groups(all_lines.values()))
    to_revert: dict[LineRef, str] = dict(reverts)
    for ref in reverts:
        group = by_line.get(ref)
        if group is None:
            continue
        for member in group.members:
            to_revert.setdefault(member, atomicity_reason)

    for ref, reason in to_revert.items():
        lm = all_lines.get(ref)
        if lm is None:
            continue
        decide.fall_back(lm, reason=reason, traces=traces)
    return to_revert
