"""Quality estimation and routing.

QE answers the PRE-LLM question the calibration harness proved
is missing: does this line still carry an OCR error, or is it already
clean? A :class:`QEScorer` scores the SOURCE text alone (no correction
yet) — higher means *more likely to need correction*. The :func:`route_line`
brain turns that score, under a :class:`RoutingPolicy`, into a per-line
decision: SKIP a line judged clean (no LLM call — the hybrid-selective
economics the review asked for), send an uncertain one to the LLM, or
ESCALATE the riskiest for a heavier pass.

The core ships a zero-dependency :class:`HeuristicQEScorer` (archaic-glyph
and confusion signals + optional lexicon coverage); the ``saknussemm[qe]``
extra will add an ONNX discriminator behind the SAME protocol. Same
doctrine as the confidence scorers: the model informs, the app decides.
Nothing here calls a provider or mutates a document — it only reads text
and returns a number or a decision.
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable

from pydantic import Field, model_validator

from saknussemm.core.schemas import FrozenPolicy

_PUNCT = ".,;:!?()[]{}«»\"'—–-…"


@runtime_checkable
class QEScorer(Protocol):
    """Scores a SOURCE line's need for correction, in [0, 1].

    ``needs_correction`` returns higher for a line more likely to carry
    an OCR error. Deterministic; reads only the text. The pipeline never
    requires a scorer — routing is opt-in — and a scorer never decides
    anything, it informs the Router (app-decides doctrine)."""

    name: str

    def needs_correction(self, text: str) -> float: ...


class HeuristicQEScorer:
    """Zero-dependency QE baseline: the fraction of a line's word tokens
    that look like raw OCR — using ONLY orthography-neutral signals.

    Design lesson, measured on the OCR17+ corpus (2026-07-23): archaic
    glyphs (``ſ``, ligatures, ``u``-for-``v``) are NOT a "needs
    correction" signal here — saknussemm PRESERVES historical
    orthography (system prompt rule 3), so the human-corrected reference
    is FULL of them. A naive archaic-glyph heuristic scored the clean
    reference HIGHER than the raw OCR — exactly the "a contemporary
    model would flag historical spelling as improbable" trap the review
    named. So this baseline flags a token only on signals that mean OCR
    BREAKAGE regardless of period:

    - a digit adjacent to a letter (the ``l``/``1``, ``o``/``0``
      confusions strand a digit inside a word: ``vil1e``, ``c0mme``);
    - a lexicon was supplied and the token is out of it (the ONLY signal
      that distinguishes a real OCR non-word like ``cukiuent`` from a
      valid historical form like ``cultiuent`` — and it takes a
      HISTORICAL lexicon to be right, which is precisely why the
      scorer wants D'AlemBERT, not a rule of thumb).

    Line score = ``flagged / word_tokens`` (0.0 for an empty or
    punctuation-only line). Without a lexicon only the digit signal
    fires, so the score is sparse BY DESIGN — an honest admission that a
    zero-dependency heuristic cannot judge historical OCR quality alone.
    This is the baseline the ONNX/D'AlemBERT scorer must beat on
    the calibration harness.
    """

    name: str = "heuristic-qe"

    def __init__(self, lexicon: set[str] | None = None) -> None:
        self._lexicon = {w.casefold() for w in lexicon} if lexicon else set()

    def _is_suspicious(self, token: str) -> bool:
        if any(
            (a.isdigit() and b.isalpha()) or (a.isalpha() and b.isdigit())
            for a, b in zip(token, token[1:])
        ):
            return True
        if self._lexicon:
            core = token.strip(_PUNCT)
            if core and not core.isdigit() and core.casefold() not in self._lexicon:
                return True
        return False

    def needs_correction(self, text: str) -> float:
        tokens = [t for t in text.split() if any(c.isalnum() for c in t)]
        if not tokens:
            return 0.0
        flagged = sum(1 for t in tokens if self._is_suspicious(t))
        return flagged / len(tokens)


class RoutingDecision(str, Enum):
    """What the Router decided for one line."""

    #: QE judged the line already clean — do NOT spend an LLM call.
    SKIP = "skip"
    #: Ordinary case — send the line to the LLM producer.
    LLM = "llm"
    #: QE flagged the line as high-risk — mark for a heavier pass
    #: (adversarial re-check / vision), still an LLM call for now.
    ESCALATE = "escalate"


class RoutingPolicy(FrozenPolicy):
    """Per-line routing thresholds over a QE score (§ hybrid selective).

    Both bounds default to ``None`` — routing DISABLED, every line goes
    to the LLM exactly as before (the conservative default). Set them to
    turn on the economics:

    - ``skip_at_or_below``: a QE score ≤ this routes to SKIP (a clean
      line costs no LLM call);
    - ``escalate_at_or_above``: a QE score ≥ this routes to ESCALATE.

    Between the two (or when a bound is ``None``) the line routes to LLM.
    A frozen §8.2-style policy, and NOT in the composite
    ``config_fingerprint``: folding it in would move every fingerprint
    already stamped into delivered files. Yet a ``SKIP`` makes the OCR
    text the final text, so two runs with different bounds deliver
    different bytes under the same fingerprint. The report therefore
    carries the policy BESIDE the fingerprint — ``RunProvenance.active_policies["routing"]``,
    present whenever a bound is set — and a consumer recomputes
    ``policy_fingerprint()`` from that dump.
    """

    skip_at_or_below: float | None = Field(default=None, ge=0.0, le=1.0)
    escalate_at_or_above: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _bounds_do_not_cross(self) -> "RoutingPolicy":
        lo, hi = self.skip_at_or_below, self.escalate_at_or_above
        if lo is not None and hi is not None and lo >= hi:
            raise ValueError(
                f"skip_at_or_below ({lo}) must be < escalate_at_or_above "
                f"({hi}) — an overlapping band has no LLM tier"
            )
        return self


#: Module-level default reused wherever a caller passes no RoutingPolicy.
DEFAULT_ROUTING_POLICY = RoutingPolicy()


def route_line(qe_score: float, policy: RoutingPolicy) -> RoutingDecision:
    """Route one line by its QE score under ``policy``. SKIP wins ties at
    the low bound, ESCALATE at the high bound; everything else is LLM."""
    if policy.skip_at_or_below is not None and qe_score <= policy.skip_at_or_below:
        return RoutingDecision.SKIP
    if (
        policy.escalate_at_or_above is not None
        and qe_score >= policy.escalate_at_or_above
    ):
        return RoutingDecision.ESCALATE
    return RoutingDecision.LLM


__all__ = [
    "DEFAULT_ROUTING_POLICY",
    "HeuristicQEScorer",
    "QEScorer",
    "RoutingDecision",
    "RoutingPolicy",
    "route_line",
]
