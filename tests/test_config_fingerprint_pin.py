"""Pin the configuration fingerprint and the §8.2 policy surface (audit
— filet for audit Problem 7).

Problem 7: ``GuardConfig`` carries 21 knobs, two of which are duplicated
concepts (``part2_collapse_ratio`` / ``pair_drift_part2_collapse_ratio``
and ``part1_max_word_growth`` / ``pair_drift_part1_word_growth``). Merging
the duplicates is a **public-API break** (§11 provenance fingerprints
every policy field) and must never happen silently. This test freezes:

  * the exact ``config_fingerprint()`` stamped into corrected XML today;
  * every policy's ``policy_fingerprint()``;
  * the full ``GuardConfig`` field set (so removing a field trips here);
  * the current values of the duplicated knobs (so the Phase-4 merge is a
    conscious edit to this file, tied to a SemVer decision).

If a change here is intentional, update the pinned values AND record the
version bump / CHANGELOG entry in the same commit.
"""

from __future__ import annotations

from saknussemm.core.schemas import (
    ChunkPlannerConfig,
    GuardConfig,
    LossPolicy,
    PairingPolicy,
    RetryPolicy,
)
from saknussemm.core.pipeline import CorrectionPipeline


class _Noop:
    wants_geometry = False
    wants_image = False
    requires_full_coverage = True

    async def produce(self, payload, *, options):  # pragma: no cover
        from saknussemm.core.editing import EditScript

        return EditScript(ops=[]), None

    def on_event(self, event_type, payload):  # pragma: no cover
        pass

    def write_corrected(self, *, source_stem, xml_bytes):  # pragma: no cover
        pass

    def write_trace(self, *, traces_payload):  # pragma: no cover
        pass


def _default_pipeline() -> CorrectionPipeline:
    noop = _Noop()
    return CorrectionPipeline(
        producer=noop,
        observer=noop,
    )


# --- Fingerprints -----------------------------------------------------------


def test_config_fingerprint_is_pinned():
    """The composite fingerprint stamped into every corrected XML's
    processingStep. Changing any default policy value changes this.

    History: ``3a06d0a93ac4eedc`` (1.0.0) → ``216aa712f1e99b79`` after the
    P1-2 geometric pairing defaults landed (PairingPolicy grew
    ``geometric_checks`` / ``max_gap_line_heights`` / ``max_rise_line_heights``)
    → ``55dc80679dd71f94`` when LossPolicy joined the §8.2 surface
    (ADR-012, P3.8 — a fifth ``loss`` key in the composite payload;
    behaviour change recorded in CHANGELOG under [Unreleased])
    → ``15dc07cba9122106`` when LossPolicy grew ``min_alignment_score``
    (the vision/QE programme token_realign gate — default ``None`` keeps
    behaviour identical; the FIELD joins the fingerprinted surface,
    recorded in CHANGELOG under [Unreleased])."""
    assert _default_pipeline().config_fingerprint() == "8035af05be00aedd"


def test_each_policy_fingerprint_is_pinned():
    assert GuardConfig().policy_fingerprint() == "32bf7bf6e915f388"
    # The remaining four are pinned by-shape: any default change trips the
    # composite above, and these lock each policy independently.
    for policy in (ChunkPlannerConfig(), LossPolicy(), PairingPolicy(), RetryPolicy()):
        fp = policy.policy_fingerprint()
        assert isinstance(fp, str) and len(fp) == 16


# --- GuardConfig surface (Problem 7 target) ---------------------------------


_GUARD_FIELDS = {
    "attachment_scope",
    "attachment_twin_similarity",
    "absorption_concat_similarity",
    "absorption_length_ratio",
    "boundary_len_ratio_max",
    "boundary_len_ratio_min",
    "boundary_prefix_len",
    "duplicate_source_min_diff",
    "duplicate_threshold",
    "edit_line_max_changed_chars",
    "edit_span_max_growth_ratio",
    "min_source_similarity",
    "neighbour_margin",
    "pair_drift_part1_word_growth",
    "pair_drift_part2_collapse_ratio",
    "pair_drift_part2_min_words",
    "part1_char_growth_ratio",
    "part1_char_growth_slack",
    "part1_last_word_char_growth",
    "part1_max_word_growth",
    "part2_collapse_ratio",
    "part2_expansion_floor",
    "part2_expansion_ratio",
}


def test_guard_config_field_set_is_frozen():
    """21 knobs today. Removing one is a public-API break (each field is
    provenance-fingerprinted, §11) → deliberate edit here + a version bump."""
    assert set(GuardConfig.model_fields) == _GUARD_FIELDS
    assert len(_GUARD_FIELDS) == 23


def test_per_stage_twin_knobs_are_intentional_not_duplication():
    """Phase-4 decision: the PART1/PART2 knobs that appear at BOTH Stage A
    (validator, pre-retry) and Stage B (hyphenation, reconcile) are kept as
    SEPARATE knobs on purpose — NOT accidental duplication to be merged.

    The PART1 twin proves the point directly: the two stages carry
    DIFFERENT defaults (Stage A tolerates 2, Stage B 1), so they cannot be
    one field without changing guard behaviour. The PART2 twin shares a
    default today but stays separate so the stages tune independently.
    Merging either is a breaking change (removes a fingerprinted field) for
    no behavioural benefit; this test pins the intent so a future reader
    doesn't mistake the twins for redundancy.
    """
    g = GuardConfig()
    # PART1 growth: DIFFERENT per stage → provably not one knob.
    assert g.part1_max_word_growth == 1  # Stage B (stricter)
    assert g.pair_drift_part1_word_growth == 2  # Stage A (more permissive)
    assert g.part1_max_word_growth != g.pair_drift_part1_word_growth
    # PART2 collapse: same value today, deliberately two independent knobs.
    assert g.part2_collapse_ratio == 0.4  # Stage B
    assert g.pair_drift_part2_collapse_ratio == 0.4  # Stage A
