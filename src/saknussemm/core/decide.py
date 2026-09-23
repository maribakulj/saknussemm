"""The one place a line's decision is written (ADR-013).

A line's decision is two manifest fields — ``corrected_text`` and
``status`` — plus the trace's ``fallback_reason`` and ``review_reasons``.
Every write of them goes through here; ``tests/decision/test_decision_write_exclusivity.py`` refuses
the first statement anywhere else in the package.

Four verbs, because there are four genuinely different things to say
about a line, and collapsing them would make the module lie about what
happened:

:func:`accept`
    A correction stands. Text and status both change.

:func:`refer_for_review`
    A correction that already stands is declared unverifiable. **No
    text is written** — the artefact carries exactly what ``accept``
    put there — only the status changes, and a reason is appended.

:func:`fall_back`
    A correction is taken away and the line returns to its source. Text
    and status both change; the reason is recorded **only into an empty
    trace**.

:func:`renormalise`
    A decision already made keeps standing, and only its spelling
    changes. Text changes; status does not, because nothing was decided
    here.

The two middle verbs are exact mirrors, and that symmetry is the reason
they are separate: ``renormalise`` writes text and no status,
``refer_for_review`` writes status and no text. Merging either into
``accept`` would make a call site claim something it did not do.

**Why ``fall_back`` defers, and why that is not merely cautious**
(ADR-013). It rests on an invariant, verified over the corpora rather
than assumed, and pinned by
``tests/decision/test_fallback_reason_precedence.py``:

    **I-1 — a line carrying a ``fallback_reason`` has already been
    reverted: its final text equals its source text.**

So a second revert of an already-reverted line changes no text a reader
can see. The pass that actually took the correction away is the FIRST
one, and its reason is therefore the true one, not the stale one. A
last-writer-wins rule would name a pass that did nothing.

**The revert of text and status stays unconditional**, and that
asymmetry is deliberate: ``acceptance._apply_unit_reverts`` pulls hyphen
members that may not be reverted yet, and that pull is the whole of
ADR-010's fallback atomicity. Deferring the text too would leave a mixed
pair — one member at source, one corrected — which is the single state
the reconciler guarantees cannot survive.

**Why ``renormalise`` exists rather than reusing ``accept``.**
``finalize._preserve_break_chars``
forces the source line's word-break character onto an accepted
correction. It decides nothing: it does not choose between a proposal
and a source, it respells a choice already made, and it never runs on a
line that fell back (a reverted line has ``corrected_text ==
ocr_text``, which it skips). Routing it through ``accept`` would make it
assert ``CORRECTED`` on lines whose status it has no business setting —
a behaviour change bought for the tidiness of one verb fewer. A reader
must be able to tell what happened to a line from the call alone, and
"text only, decision untouched" is its own thing to say.
"""

from __future__ import annotations

from saknussemm.core.identity import LineRef, line_ref
from saknussemm.core.schemas import LineManifest, LineStatus, LineTrace
from saknussemm.core.traces import _set_trace


#: Le vocabulaire CLOS des raisons de repli.
#:
#: Un repli est ce qu'un consommateur lit en premier quand une ligne n'a pas
#: été corrigée, et il l'agrège par ce code — ``fallback_reason_counts`` coupe
#: sur le ``:`` et compte le préfixe. Un code inconnu dans un rapport est donc
#: un défaut de la bibliothèque, pas une raison inédite.
#:
#: L'ensemble était ouvert : vingt littéraux dispersés sur huit modules, et
#: rien ne disait combien il y en avait. `docs/la-vie-d-une-ligne.md` les
#: documente pour un lecteur ; cette constante les ferme pour un programme, et
#: ``tests/test_the_fallback_reasons_are_a_closed_set.py`` refuse un
#: vingt-et-unième qui n'y figurerait pas.
#:
#: Volontairement un ``frozenset[str]`` et non un ``Enum`` : ``DecisionReason.code``
#: est ``str`` sur une surface publique versionnée, et le durcir serait un
#: changement de contrat, pas une clôture.
FALLBACK_REASON_CODES: frozenset[str] = frozenset(
    {
        # -- étage C : la ligne et ses voisines (`guards.check_line`) -------
        "too_different_from_source",
        "closer_to_previous_line",
        "closer_to_next_line",
        # Sous ``attachment_scope="page"`` : une autre ligne de la page,
        # ni la précédente ni la suivante.
        "closer_to_another_line",
        "absorbs_previous_line",
        "absorbs_next_line",
        # Le défaut de `check_line` quand une branche de refus ne nomme pas
        # sa raison. Aucune ne le fait aujourd'hui ; il reste parce que le
        # site d'appel ne peut pas le prouver.
        "rejected",
        # -- césure : l'unité, jamais un membre seul (ADR-010) -------------
        "hyphen_pair_fallback",
        "hyphen_partner_fell_back",
        "hyphen_unit_fallback",
        "orphan_hyphen_completed",
        # -- passes document-wide (`core/finalize.py`) ---------------------
        "adjacent_duplicate_detected",
        "adjacent_duplicate_pair_atomicity",
        "boundary_migration_forward",
        "boundary_migration_backward",
        "format_loss",
        "format_loss_pair_atomicity",
        "token_realign",
        "token_realign_pair_atomicity",
        # -- niveau chunk (`core/outcome.py`) ------------------------------
        "all_attempts_exhausted",
        "chunk_error_absorbed",
    }
)


#: Le vocabulaire CLOS des raisons de RENVOI EN REVUE.
#:
#: Même contrat que ``FALLBACK_REASON_CODES``, sur l'autre moitié de ce
#: qu'un rapport dit d'une ligne : ``review_reason_counts`` coupe sur le
#: ``:`` et agrège le préfixe, donc un tableau de bord affiche ces codes-là
#: et un code inconnu y est un défaut de la bibliothèque.
#:
#: Fermé dès l'écriture, et pas après coup comme l'autre : les raisons de
#: repli ont vécu ouvertes assez longtemps pour qu'il faille un ``grep``
#: d'audit pour les recenser. ``tests/test_the_review_reasons_are_a_closed_set.py``
#: refuse un code que ``core/review.py`` émettrait sans qu'il figure ici,
#: et un code déclaré ici qu'aucune règle ne produit.
#:
#: Ce que l'ensemble NE contient pas est écrit dans ``core/review.py`` :
#: trois règles du programme d'origine n'ont pas de code parce que le
#: moteur n'a pas de quoi les alimenter, et déclarer leur code ferait
#: promettre au vocabulaire une raison qu'aucun run ne rendra.
REVIEW_REASON_CODES: frozenset[str] = frozenset(
    {
        # -- par ligne : l'indice est dans le couple (source, correction) --
        "digits_changed",
        "negation_changed",
        "proper_noun_changed",
        # -- au niveau du run : l'indice n'existe que dans l'agrégat ------
        "systematic_substitution",
        "systematic_removal",
        # -- conséquence, pas décision : l'unité de césure part entière ---
        # (ADR-010). Le pendant de `hyphen_unit_fallback` côté renvoi.
        "hyphen_unit_review",
    }
)


def accept(
    line: LineManifest,
    text: str,
    *,
    traces: dict[LineRef, LineTrace] | None = None,
) -> None:
    """This text is the line's decision, and it stands.

    Used for a correction the guards passed, and for a line the QE router
    confirmed clean without asking any producer (``text`` is then the
    line's own OCR text — a skip is still a decision, and the auditable
    signature that distinguishes it from a producer answering identically
    is the trace's ``model_input_text`` staying ``None``, which this
    function does not touch).
    """
    line.corrected_text = text
    line.status = LineStatus.CORRECTED
    _set_trace(
        traces,
        line,
        projected_text=text,
        validation_status=LineStatus.CORRECTED.value,
    )


def fall_back(
    line: LineManifest,
    *,
    reason: str,
    traces: dict[LineRef, LineTrace] | None = None,
) -> None:
    """Take the correction away: the line goes back to its source text.

    Text and status are written unconditionally; ``reason`` is recorded
    only when the trace carries none, so the pass that FIRST removed the
    correction keeps the attribution (ADR-013, invariant I-1). See this
    module's docstring for why that asymmetry is the correct one and not
    an oversight.
    """
    line.corrected_text = line.ocr_text
    line.status = LineStatus.FALLBACK
    _set_trace(
        traces,
        line,
        projected_text=line.ocr_text,
        validation_status=LineStatus.FALLBACK.value,
    )
    if traces is None:
        return
    trace = traces.get(line_ref(line))
    if trace is not None and not trace.fallback_reason:
        trace.fallback_reason = reason


def refer_for_review(
    line: LineManifest,
    *,
    reason: str,
    traces: dict[LineRef, LineTrace] | None = None,
) -> None:
    """Declare a standing correction unverifiable — status only.

    The correction is NOT taken away: ``corrected_text`` is untouched,
    the artefact carries the same bytes, and the edit script still
    carries the line's op. What changes is what the run *claims*: from
    "this was corrected" to "this was corrected and I have no means of
    establishing it is right".

    That this function writes no text is the property the whole feature
    rests on. Referral is an annotation, so turning the referral rules
    on cannot change a single delivered byte — a claim the byte-parity
    corpus verifies rather than a claim this docstring makes.

    Reasons ACCUMULATE, and unlike ``fall_back`` this is
    last-writer-friendly on purpose: several rules may see the same
    line for genuinely different causes (a changed amount *and* a
    changed proper noun), and a reviewer needs all of them. Duplicates
    are dropped; order of arrival is kept, which is the order the rules
    run in.

    Refuses a line that has not been corrected. A referral says
    something about a CORRECTION; there is none on a line still
    ``PENDING``, and on a line that fell back the correction was taken
    away — referring it would resurrect a decision the engine already
    unmade. Either is an engine bug, not bad input, so it raises
    ``RuntimeError`` like ``_FinalizeOrder`` does, and deliberately not
    a ``SaknussemmError``, which the chunk loop is allowed to absorb
    (ADR-008).
    """
    if line.status not in (LineStatus.CORRECTED, LineStatus.REVIEW_REQUIRED):
        raise RuntimeError(
            f"refer_for_review on a line whose status is "
            f"{line.status.value!r}: a referral qualifies a correction, "
            f"and this line carries none. Refer before the correction is "
            f"taken away, or not at all."
        )
    line.status = LineStatus.REVIEW_REQUIRED
    _set_trace(
        traces,
        line,
        validation_status=LineStatus.REVIEW_REQUIRED.value,
    )
    if traces is None:
        return
    trace = traces.get(line_ref(line))
    if trace is not None and reason not in trace.review_reasons:
        trace.review_reasons = (*trace.review_reasons, reason)


def renormalise(line: LineManifest, text: str) -> None:
    """Respell a decision that already stands — no status, no reason.

    The narrow verb for a pass that normalises decided text rather than
    deciding anything (``finalize._preserve_break_chars``). Deliberately
    does not touch the trace: the caller's historical behaviour wrote
    nothing there, and widening it here would be a behaviour change
    smuggled into a migration.
    """
    line.corrected_text = text


__all__ = [
    "FALLBACK_REASON_CODES",
    "REVIEW_REASON_CODES",
    "accept",
    "fall_back",
    "refer_for_review",
    "renormalise",
]
