"""Injectable, frozen policies (§8.2) and the chunk plan they shape.

A policy is a value: frozen, fingerprinted, and the only way a consumer
adapts the engine's behaviour (§15). The chunk-planning types live here
because they are what :class:`ChunkPlannerConfig` produces.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from saknussemm.core.schemas.manifest import (
    Coords,
    HyphenRole,
    LineManifest,
)


# ---------------------------------------------------------------------------
# Policies (frozen, injectable — §8.2)
# ---------------------------------------------------------------------------


class FrozenPolicy(BaseModel):
    """Base for the injectable, immutable policy objects (§8.2).

    Every policy is a frozen Pydantic model whose defaults reproduce the
    library's current behaviour. ``policy_fingerprint()`` returns a stable
    short hash of the sorted JSON dump, embedded in the corrected XML's
    ``processingStep`` (§11) so an output records the exact policy it was
    produced under.
    """

    model_config = ConfigDict(frozen=True)

    def policy_fingerprint(self) -> str:
        """Stable 16-hex-char hash of this policy's sorted JSON dump."""
        payload = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class ChunkPlannerConfig(FrozenPolicy):
    """Tunables for the chunk planner — character + line budgets per LLM request.

    Frozen like every §8.2 policy so a run's configuration is immutable and
    fingerprintable for provenance (§11).
    """

    max_input_chars_per_request: int = Field(default=12000, gt=0)
    max_lines_per_request: int = Field(default=80, gt=0)
    line_window_size: int = Field(default=12, gt=0)
    line_window_overlap: int = Field(default=1, ge=0)
    #: At BLOCK granularity, merge CONSECUTIVE block groups into one chunk
    #: while the chunk stays within both budgets. Off (the historical
    #: behaviour): one chunk per block group, however small. Measured on
    #: OCR17+ through the pipeline: PAGE files whose regions are one or two
    #: lines each gave 105 chunks for 251 lines — 32 on a single page — so a
    #: vision producer that reads context (a labelled strip of 20 rows) got
    #: strips of 2 or 3, and every call paid the envelope for nothing. Hyphen
    #: units are already grouped before this runs, so a merge never severs
    #: one. ``block_id`` is ``None`` on a merged chunk, as it already is for
    #: a group of several blocks.
    coalesce_blocks: bool = False

    @model_validator(mode="after")
    def _overlap_smaller_than_window(self) -> "ChunkPlannerConfig":
        """An overlap >= the window size can never advance."""
        if self.line_window_overlap >= self.line_window_size:
            raise ValueError(
                f"line_window_overlap={self.line_window_overlap} must be "
                f"smaller than line_window_size={self.line_window_size}"
            )
        return self


class GuardConfig(FrozenPolicy):
    """All anti-migration / acceptance thresholds in one frozen object.

    The pipeline runs three stages of text-migration guards, each living
    beside the control flow that acts on it (see ``core/guards.py`` for the
    A/B/C map): Stage A in ``validator._check_pair_drift`` (pre-retry),
    Stage B in ``hyphenation`` (pair reconciliation), Stage C in
    ``guards.check_line`` (line-level acceptance). Pre-F13 the numbers were
    scattered as module constants; they are gathered here so a consumer can
    tune them coherently — **the three stages must be tuned together**:
    tightening one stage without the others can leak a migration through
    the gap.

    Intentional per-stage twins (NOT accidental duplication — do not
    "dedup" them): PART1 word-growth and PART2 collapse are checked at BOTH
    Stage A and Stage B, deliberately as separate knobs so each stage tunes
    independently. Stage A (pre-retry) is more permissive — it tolerates a
    PART1 growth of 2 before forcing a retry — while Stage B (post-retry
    reconciliation) is stricter at 1 before falling back. Collapsing the
    twins would either force the two stages to share a value (removing the
    per-stage flexibility the staged design exists for) or silently change
    guard behaviour. Each twin below cross-references its partner.

    Every default equals the pre-F13 constant, so ``GuardConfig()`` is
    byte-for-byte compatible with the historical behaviour.

    The ``GuardConfig.vision()`` profile (spec §5.2 bis, the vision/QE programme)
    relaxes the *source-similarity* stage for VLM producers while keeping
    every inter-line migration guard intact — a VLM reads the image, not
    the OCR, so a legitimate correction of a badly-garbled line diverges
    far more from the source than a text model's would, and the text
    default (0.35) would reject it. Its relaxed threshold is PROVISIONAL
    until the Phase-4 vision benchmark refits it on real image data.
    """

    # --- Stage C: line-level acceptance (line_acceptance.check_line) ---
    #: Minimum SequenceMatcher ratio between source OCR and correction.
    min_source_similarity: float = Field(default=0.35, ge=0.0, le=1.0)
    #: Reject if the correction resembles a neighbour more than its own
    #: source by at least this margin (text migration suspected).
    neighbour_margin: float = Field(default=0.15, ge=0.0, le=1.0)
    #: Which lines the margin is held against. ``"adjacent"`` (the
    #: historical behaviour) compares the correction with the previous and
    #: next line only; ``"page"`` compares it with EVERY other line of the
    #: page. The wider scope exists because a mis-attached line is not
    #: always a neighbour's text: a model that drops or splits one line
    #: shifts everything after it, and a model shown a column reads across
    #: it — measured on 5 111 lines of 1930s press, the offsets clustered at
    #: ±1 but ran to ±15, and the adjacent scope let 1 746 of them through
    #: where the page scope let none. The wider scope costs one similarity
    #: per other line of the page per changed line, and refuses more on
    #: pages whose lines repeat (twins — see the next field).
    attachment_scope: Literal["adjacent", "page"] = "adjacent"
    #: Exempt from the margin any candidate line whose OWN source already
    #: resembles this line's source at least this much — two stage
    #: directions naming the same character, a repeated verse. Between such
    #: twins a mis-attachment is harmless by construction (the texts are
    #: the same), while the margin can never be held (the correction equals
    #: the other source). ``None`` (the default) exempts nothing. Measured
    #: at 0.85 on OCR17+: it returns half of the margin's refusals and
    #: still lets no mis-attachment through on any measured corpus — but it
    #: was designed after seeing which lines failed, so it stays an option
    #: until confirmed on a corpus it has never seen.
    attachment_twin_similarity: float | None = Field(default=None, ge=0.0, le=1.0)
    #: Two adjacent corrections are duplicates above this similarity …
    duplicate_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    #: … but only when their sources were below this (genuinely distinct).
    duplicate_source_min_diff: float = Field(default=0.70, ge=0.0, le=1.0)
    #: Absorption fires only when the correction is this much longer …
    absorption_length_ratio: float = Field(default=1.2, gt=0.0)
    #: … and matches source+neighbour concatenated above this similarity.
    absorption_concat_similarity: float = Field(default=0.8, ge=0.0, le=1.0)

    # --- Stage B: hyphen-pair reconciliation (hyphenation._part1/2_*) ---
    #: PART1 corrected word count may exceed OCR by at most this many.
    #: Stage-B twin of ``pair_drift_part1_word_growth`` (Stage A); stricter
    #: here (1) than at Stage A (2) on purpose — see the class docstring.
    part1_max_word_growth: int = Field(default=1, ge=0)
    #: PART1 last word may grow by at most this many characters.
    part1_last_word_char_growth: int = Field(default=3, ge=0)
    #: PART1 total char length may grow by ratio*len + slack.
    part1_char_growth_ratio: float = Field(default=1.4, gt=0.0)
    part1_char_growth_slack: int = Field(default=8, ge=0)
    #: PART2 collapsed if corrected word count < ratio * OCR word count.
    #: Stage-B twin of ``pair_drift_part2_collapse_ratio`` (Stage A); same
    #: default today, kept separate so the two stages tune independently.
    part2_collapse_ratio: float = Field(default=0.4, ge=0.0, le=1.0)
    #: PART2 expansion allowance: OCR word count + max(floor, ratio*OCR).
    part2_expansion_floor: int = Field(default=3, ge=0)
    part2_expansion_ratio: float = Field(default=0.4, ge=0.0)
    #: Boundary-word continuity: shared leading-char count required …
    boundary_prefix_len: int = Field(default=2, ge=0)
    #: … within this corrected/OCR first-word length ratio band.
    boundary_len_ratio_min: float = Field(default=0.5, gt=0.0)
    boundary_len_ratio_max: float = Field(default=2.0, gt=0.0)

    @model_validator(mode="after")
    def _boundary_band_ordered(self) -> "GuardConfig":
        """An inverted ratio band would reject every boundary word."""
        if self.boundary_len_ratio_min > self.boundary_len_ratio_max:
            raise ValueError(
                f"boundary_len_ratio_min={self.boundary_len_ratio_min} must "
                f"not exceed boundary_len_ratio_max={self.boundary_len_ratio_max}"
            )
        return self

    # --- Stage A: pre-retry pair drift (validator._check_pair_drift) ---
    #: PART1 grew by more than this many words → drift (retry). Stage-A twin
    #: of ``part1_max_word_growth`` (Stage B); more permissive (2) here.
    pair_drift_part1_word_growth: int = Field(default=2, ge=0)
    #: PART2 checked for collapse only when OCR had at least this many words.
    pair_drift_part2_min_words: int = Field(default=2, ge=0)
    #: PART2 collapsed if corrected word count < ratio * OCR word count.
    #: Stage-A twin of ``part2_collapse_ratio`` (Stage B).
    pair_drift_part2_collapse_ratio: float = Field(default=0.4, ge=0.0, le=1.0)

    # --- Edit protocol E4: per-op span drift (core/editing.py) ---
    # These bound a ``replace_span`` op ONLY. ``replace_line`` (the historical
    # whole-line path) is deliberately NOT gated here — it is governed by the
    # existing three-stage guard matrix (E6), so re-expressing today's
    # response as ``replace_line`` ops stays byte-for-byte identical.
    #: A span replacement may be at most this many times as long as the span
    #: it replaces (``len(replacement) <= ratio * max(1, span_len)``).
    edit_span_max_growth_ratio: float = Field(default=4.0, gt=0.0)
    #: Total characters a line's span ops may actually change: per
    #: op, the size of the differing window after trimming the common
    #: prefix/suffix of (original span, replacement) — so a length-neutral
    #: rewrite costs its real size, not 0. Generous by default; a rules
    #: pre-pass makes small, local edits well under it.
    edit_line_max_changed_chars: int = Field(default=200, ge=0)

    #: Provisional relaxed source-similarity floor for the vision profile
    #: (spec §5.2 bis). Lower than the text default (0.35) because a VLM
    #: correction of a badly-garbled line legitimately diverges further
    #: from the OCR source; NOT 0.0, so a producer that ignores the image
    #: and invents an unrelated line is still caught. To be refit on the
    #: Phase-4 vision benchmark (roadmap) — until then it is a safe default,
    #: not a calibrated one.
    _VISION_MIN_SOURCE_SIMILARITY: ClassVar[float] = 0.15

    @classmethod
    def text(cls, **overrides: Any) -> "GuardConfig":
        """Le profil d'un producteur de TEXTE — les défauts, nommés.

        ``GuardConfig()`` fait déjà exactement cela. Ce qui manquait est le
        NOM : sans lui, le seul profil qui existe est ``vision()``, et un
        consommateur qui lit les deux ne peut pas voir qu'il choisit entre
        deux points cohérents plutôt qu'entre « le défaut » et « autre
        chose ».

        Les trois étages de garde se règlent ENSEMBLE (voir la docstring de
        la classe) : un profil est un point cohérent de cet espace, un seuil
        isolé n'en est pas un. `docs/versioning.md` recommande donc les
        profils, et exclut les VALEURS des seuils du contrat SemVer — elles
        ne sont pas calibrées et le dire empêche de figer un provisoire.
        """
        return cls(**overrides)

    @classmethod
    def vision(cls, **overrides: Any) -> "GuardConfig":
        """The VLM guard profile (§5.2 bis, the vision/QE programme).

        Relaxes ONLY the Stage-C source-similarity floor
        (:attr:`min_source_similarity`); every inter-line migration guard
        — neighbour proximity, absorption, hyphen-pair drift, duplication
        — keeps its text default, because a VLM must no more merge or move
        lines than a text model. An explicit override always wins, so a
        host that has run the vision benchmark can pin its own calibrated
        floor: ``GuardConfig.vision(min_source_similarity=0.22)``.

        Like every :class:`GuardConfig`, the result carries its values into
        the composite fingerprint (§8.2) — choosing the vision profile is a
        structurally recorded decision, not a hidden mode.
        """
        params: dict[str, Any] = {
            "min_source_similarity": cls._VISION_MIN_SOURCE_SIMILARITY
        }
        params.update(overrides)
        return cls(**params)


#: Module-level default reused wherever a caller passes no GuardConfig, so
#: the historical behaviour needs no allocation per call.
DEFAULT_GUARD_CONFIG = GuardConfig()


class PairingPolicy(FrozenPolicy):
    """Decides whether a PART1/BOTH line may pair with the following line.

    Hyphen pairing is sequential — the parser proposes the next line in
    reading order — and this policy vets the proposal. The default
    is now *geometric* for **heuristic** pairs (trailing-dash detection):

    * same block — the candidate must sit BELOW the PART1 line, within
      ``max_gap_line_heights`` of the line's own height (and no more than
      ``max_rise_line_heights`` above it, tolerance for skew/overlap).
      Rejects segmentation noise and table-cell jumps.
    * different block, same page — the candidate must look like a real
      reading continuation: either *downward with horizontal overlap*
      (next block in the same column) or *upward and horizontally
      disjoint* (top of the next column; direction-agnostic, so RTL
      layouts are treated identically). A note in the margin or a block
      far below the column is rejected.
    * different page — always accepted: cross-page linking is only ever
      proposed between the last line of page N and the first line of
      page N+1 (see ``link_cross_page_hyphens``), and VPOS restarts per
      page so geometry is not comparable.
    * **explicit** pairs (ALTO ``SUBS_TYPE``/``HYP`` markup on either
      side) bypass the geometric vetting: the OCR engine asserted the
      continuation; sequential order in the engine's own serialisation
      is stronger evidence than our geometric plausibility check. NB the
      opt-in legacy vetoes (``same_block_only``, ``max_vertical_gap``)
      still apply to explicit pairs — a consumer who set them asked for
      an absolute restriction.
    * degenerate geometry — zero-height/width boxes, or the two lines
      carrying IDENTICAL boxes (block coords copied onto every line, a
      common lazy export) — accepted: there is nothing trustworthy to
      verify, and refusing would silently disable hyphenation for every
      coordinate-less document.

    ``geometric_checks=False`` restores the historical accept-everything
    behaviour exactly.
    """

    #: Reject a partner whose top is more than this many ALTO units below
    #: the PART1 line's bottom (``candidate.vpos - (part1.vpos + height)``).
    #: ``None`` disables the check (default). Legacy absolute-units knob,
    #: kept for consumers who tuned it; the relative ``*_line_heights``
    #: knobs below are the preferred interface.
    #: Only meaningful WITHIN a page: VPOS restarts on every page, so the
    #: check is skipped for cross-page candidates (a legitimate cross-page
    #: pair would otherwise be broken by a spurious negative/huge gap).
    max_vertical_gap: int | None = Field(default=None, ge=0)
    #: When ``True``, only pair lines in the same TextBlock. Because a
    #: cross-page partner is by definition in a different block, this also
    #: forbids cross-page pairing — intended reading of the constraint.
    same_block_only: bool = False
    #: Master switch for the geometric vetting of heuristic pairs.
    #: ``False`` restores the historical purely-sequential behaviour.
    geometric_checks: bool = True
    #: Max downward gap between the PART1 line's bottom and the candidate's
    #: top, in units of the PART1 line's height. Same-block candidates and
    #: cross-block downward continuations both use it.
    max_gap_line_heights: float = Field(default=3.0, ge=0.0)
    #: Tolerance for a candidate whose top sits ABOVE the PART1 line's
    #: bottom (box overlap, skewed scans), in line heights. Beyond it, an
    #: upward candidate is only plausible as a column jump (cross-block,
    #: horizontally disjoint).
    max_rise_line_heights: float = Field(default=0.5, ge=0.0)

    @staticmethod
    def _explicit(part1: LineManifest, candidate: LineManifest) -> bool:
        """Engine-asserted continuation on either side of the pair."""
        forward_explicit = (
            part1.hyphen_forward_explicit
            if part1.hyphen_role == HyphenRole.BOTH
            else part1.hyphen_source_explicit
        )
        backward_explicit = (
            candidate.hyphen_role in (HyphenRole.PART2, HyphenRole.BOTH)
            and candidate.hyphen_source_explicit
        )
        return forward_explicit or backward_explicit

    @staticmethod
    def _degenerate(c: Coords) -> bool:
        return c.height <= 0 or c.width <= 0

    def can_pair(self, part1: LineManifest, candidate: LineManifest) -> bool:
        """Return ``True`` if ``candidate`` may be ``part1``'s PART2 partner."""
        # Page-qualify the same-block veto: block IDs are reused across
        # pages (both pages export "TextBlock1"), so a bare block_id compare
        # sees EQUAL ids for a cross-page candidate and lets it through —
        # the exact opposite of the documented "forbids cross-page pairing"
        # guarantee. A cross-page candidate is by definition a different
        # block, mirroring the page-qualified max_vertical_gap veto below.
        if self.same_block_only and (
            part1.page_id != candidate.page_id or part1.block_id != candidate.block_id
        ):
            return False
        if (
            self.max_vertical_gap is not None
            and part1.page_id == candidate.page_id  # VPOS comparable intra-page only
        ):
            gap = candidate.coords.vpos - (part1.coords.vpos + part1.coords.height)
            if gap > self.max_vertical_gap:
                return False

        # --- geometric vetting (heuristic pairs, intra-page) ---
        if not self.geometric_checks:
            return True
        if part1.page_id != candidate.page_id:
            return True  # last-of-page → first-of-next by construction
        if self._explicit(part1, candidate):
            return True
        a, b = part1.coords, candidate.coords
        if self._degenerate(a) or self._degenerate(b):
            return True  # nothing to verify
        if (a.hpos, a.vpos, a.width, a.height) == (b.hpos, b.vpos, b.width, b.height):
            # Two "consecutive" lines with IDENTICAL boxes = synthetic
            # geometry (block coords copied onto every line) — treat as
            # degenerate rather than rejecting every pair in such files.
            return True
        gap = b.vpos - (a.vpos + a.height)
        below_ok = gap <= self.max_gap_line_heights * a.height
        rise_ok = gap >= -self.max_rise_line_heights * a.height

        if part1.block_id == candidate.block_id:
            return below_ok and rise_ok

        # Cross-block: downward continuation must overlap horizontally
        # (next block, same column); an upward jump must be horizontally
        # disjoint (start of another column — either side, so RTL works)
        # AND entirely above the PART1 line: a block merely *beside* the
        # column (marginal note at the same height) is not a column start.
        h_overlap = b.hpos < a.hpos + a.width and a.hpos < b.hpos + b.width
        if rise_ok:
            return below_ok and h_overlap
        return not h_overlap and (b.vpos + b.height <= a.vpos)


#: Module-level default reused wherever a caller passes no PairingPolicy.
DEFAULT_PAIRING_POLICY = PairingPolicy()


class LossPolicy(FrozenPolicy):
    """What the run does when projecting a correction would LOSE format
    granularity (ADR-012; token_realign — the vision/QE programme).

    The PAGE rewriter cannot keep ``Word`` geometry when a correction
    changes a line's word count (6.2 P4 slow path: the ``Word`` children
    are dropped and the text lives at line level). Three stances:

    * **REPORT** (``strict=False``, the default — the library's
      historical behaviour, now explicit): the correction projects, the
      loss is counted (``CorrectionReport.format_losses`` aggregate) and
      attributed per line (``ProjectionStage.losses``).
    * **STRICT** (``strict=True``): a correction that cannot project
      without loss is REJECTED before any output exists — the whole
      hyphen unit falls back to source text with a ``format_loss``
      reason, consistent with the conservative-on-ambiguity fallback
      philosophy. The source markup keeps its word geometry.
    * **TOKEN_REALIGN** (``min_alignment_score`` set, ``strict=False``):
      the middle ground. A word-count-changing correction projects only
      when the token alignment onto the source words is CONFIDENT
      (aggregate score ≥ the threshold, no suspected word move); a
      same-count correction is additionally gated on the move flag. A
      gated line reverts to source markup — but its correction is NOT
      lost: it lands in the run's **sidecar**
      (``CorrectionReport.sidecar``, ``sidecar.json`` on
      :meth:`CorrectionResult.write`) for review. ``strict=True`` wins
      over this gate.

    Scope of strict: word-granularity loss only
    (``LineManifest.word_count``). Stale-annotation drops (``conf``,
    alternative ``TextEquiv``, offset-anchored ``custom`` groups)
    describe the OLD reading — they are inherent to ANY correction, so
    they stay report-only in every mode.

    **``strict`` is a no-op on ALTO, and that is worth stating outright
    rather than leaving to be inferred from the sentence above**.
    ``word_count`` is populated by the PAGE parser alone: ALTO's per-token
    ``String`` geometry redistributes at any token count, so there is no
    word markup to lose and the gate has nothing to measure. A host that
    sets ``strict=True`` on an ALTO document gets exactly the default
    behaviour, silently.

    That is not the same as "an ALTO rewrite loses nothing". A
    word-count-changing correction rebuilds the line and drops the semantic
    ``String`` attributes it cannot re-attach to re-segmented words —
    ``TAGREFS``, ``language``, vendor attributes, and the ``STYLE`` of any
    source String the token alignment could not match. Those losses are
    REPORTED (``CorrectionReport.format_losses``, attributed per line) and
    **not gated by this policy in any mode**. Gating them would be a
    behavioural change to delivered output, so it needs a measured
    threshold rather than a flag flipped in passing; until then the
    restriction is documented and pinned by a test instead of being
    discovered by a host whose gate never fired.
    """

    strict: bool = False
    #: token_realign threshold in [0, 1] — ``None`` disables the gate
    #: (historical behaviour). 0.6 is a reasonable starting point:
    #: ordinary OCR corrections align far above it, wholesale rewrites
    #: far below. The value is NOT calibrated: no corpus has been measured
    #: against it, which is why the gate is off by default.
    min_alignment_score: float | None = Field(default=None, ge=0.0, le=1.0)


#: Module-level default reused wherever a caller passes no LossPolicy.
DEFAULT_LOSS_POLICY = LossPolicy()


class ConfidencePolicy(FrozenPolicy):
    """What the run does with line confidences.

    * **DROP** (default — the historical behaviour): no confidence is
      computed; the report carries none.
    * **REPORT_ONLY**: every :class:`LineOutcome` gains a
      :class:`LineConfidence` block (multi-component, identified
      aggregation formula). Nothing is written into the XML.
    * **WRITE_WC**: reserved — stamping confidences into the output
      markup (ALTO ``WC`` with a declared ``postProcessingStep``, PAGE
      multi-``TextEquiv``) is LOCKED until a calibration harness proves the
      values against a real corpus. Requesting it raises at construction.

    Deliberately NOT part of the §8.2 composite ``config_fingerprint``
    yet: ``report_only`` affects the report, never the corrected XML —
    the policy joins the fingerprinted surface in the same release that
    unlocks ``write_wc`` (which does affect outputs).
    """

    mode: Literal["drop", "report_only", "write_wc"] = "drop"

    @model_validator(mode="after")
    def _write_wc_is_locked(self) -> "ConfidencePolicy":
        if self.mode == "write_wc":
            raise ValueError(
                "ConfidencePolicy(mode='write_wc') is locked until the "
                "calibration harness proves the confidence values against a "
                "real corpus — use "
                "'report_only' and read LineOutcome.confidence instead."
            )
        return self


#: Module-level default reused wherever a caller passes no ConfidencePolicy.
DEFAULT_CONFIDENCE_POLICY = ConfidencePolicy()


class RetryPolicy(FrozenPolicy):
    """Per-chunk LLM retry strategy, injectable and frozen.

    Pre-F9 the temperature ramp (0.0 → 0.3 → 0.5) and the attempt cap were
    hard-coded in the pipeline, so *any* retry introduced non-determinism.
    This policy externalises them:

      - ``max_attempts`` — attempts per chunk at a given granularity.
      - ``temperatures`` — temperature per attempt (attempt *n* uses
        ``temperatures[n-1]``, clamped to the last entry). A hyphen-
        integrity violation still pins temperature to 0.0 on the next
        attempt regardless of this ramp (handled by the pipeline).
      - ``transient_backoff_base`` / ``output_backoff_base`` — the retry
        backoff is ``attempt * base`` seconds; transient-HTTP errors use
        the first, malformed-output errors the second. Hyphen violations
        retry immediately (0 s).
      - ``per_chunk_budget`` — total attempts budget for a chunk across
        all granularity downgrades. Bounds the PAGE→BLOCK→WINDOW→LINE
        descent so one malformed line can't burn unbounded calls.

    ``RetryPolicy.default()`` reproduces the historical behaviour to the
    byte; ``RetryPolicy.deterministic()`` sets every temperature to 0 for
    reproducible runs.
    """

    max_attempts: int = Field(default=3, ge=1)
    temperatures: tuple[float, ...] = (0.0, 0.3, 0.5)
    transient_backoff_base: float = Field(default=2.0, ge=0.0)
    output_backoff_base: float = Field(default=1.0, ge=0.0)
    per_chunk_budget: int = Field(default=6, ge=1)

    @model_validator(mode="after")
    def _temperatures_in_range(self) -> "RetryPolicy":
        """Every provider rejects temperatures outside [0, 2]."""
        for t in self.temperatures:
            if not (0.0 <= t <= 2.0):
                raise ValueError(f"temperature {t} outside the valid [0, 2] range")
        return self

    @classmethod
    def default(cls) -> RetryPolicy:
        """The historical behaviour (temperature ramp 0.0/0.3/0.5)."""
        return cls()

    @classmethod
    def deterministic(cls) -> RetryPolicy:
        """All temperatures 0.0 — reproducible retries (same attempt cap)."""
        return cls(temperatures=(0.0,))

    def temperature_for(self, attempt: int) -> float:
        """Temperature for a 1-based attempt index (clamped to the last)."""
        if not self.temperatures:
            return 0.0
        idx = min(max(attempt, 1) - 1, len(self.temperatures) - 1)
        return self.temperatures[idx]


class ReviewPolicy(FrozenPolicy):
    """Which corrections the run declares it cannot verify.

    A referral moves a line to ``LineStatus.REVIEW_REQUIRED``. It
    **changes no delivered byte**: the correction stays, the artefact is
    identical, and only what the run CLAIMS about the line changes. The
    rules live in ``core/review.py``, which also records what each one
    can and cannot see.

    **On by default**, and that is the whole point rather than an
    aggressive default. A library that can signal what it cannot
    establish, and does so only when asked, has not signalled it. A host
    that wants the previous behaviour asks for it: :meth:`silent`.

    Expect referrals on a substantial share of the corrected lines —
    the proper-noun rule alone fires on every respelled name, which in
    heritage print is a lot of them. That number is not a defect rate.
    It is the size of what the guards were already unable to check and
    were not saying.

    Each rule has its own switch because their noise is not comparable:
    a host with clean modern print may want the digit and negation
    rules and not the proper-noun one. Turning a rule off removes its
    code from the run's vocabulary; it never turns a referral into a
    ``CORRECTED``-with-an-asterisk.
    """

    #: Master switch. ``False`` reproduces the behaviour that predates
    #: referral exactly: no line is ever ``REVIEW_REQUIRED``.
    enabled: bool = True
    #: The digits are not the same ones (covers dates and amounts —
    #: neither is parsed; see ``core/review.py``).
    digits_changed: bool = True
    #: A negation particle appeared, vanished, or changed in number.
    negation_changed: bool = True
    #: A probable proper noun was respelled, added or dropped.
    proper_noun_changed: bool = True
    #: A character the run edited on EVERY one of its occurrences —
    #: the run-level rule, invisible line by line.
    systematic_substitution: bool = True
    #: How many occurrences a character needs before "every one of them"
    #: means anything. Three is the smallest number for which the word
    #: "systematic" is not an overstatement; the measured cases were 34
    #: and 69.
    min_systematic_occurrences: int = 3

    @classmethod
    def silent(cls) -> "ReviewPolicy":
        """No referrals at all — every corrected line reads ``corrected``.

        Named rather than spelled ``ReviewPolicy(enabled=False)`` at each
        call site, and named ``silent`` rather than ``disabled`` because
        that is what it does: the corrections the rules would have
        flagged still ship, unflagged. It suppresses the report, not the
        uncertainty.
        """
        return cls(enabled=False)


#: Module-level default reused wherever a caller passes no ReviewPolicy.
DEFAULT_REVIEW_POLICY = ReviewPolicy()


#: Module-level default reused wherever a caller passes no RetryPolicy.
DEFAULT_RETRY_POLICY = RetryPolicy()
