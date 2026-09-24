"""GuardConfig — the frozen, injectable guard-threshold policy (spec F13, §8.2).

Pins:
  - the policy is immutable (frozen);
  - ``policy_fingerprint()`` is stable, deterministic, and sensitive to
    any field change (it feeds the provenance ``processingStep``, §11);
  - the defaults reproduce the historical thresholds (byte-parity);
  - the config actually threads through the guards — a stricter config
    rejects a correction the default accepts, and vice versa.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from saknussemm.core.guards import check_line
from saknussemm.core.schemas import DEFAULT_GUARD_CONFIG, GuardConfig


def test_guard_config_is_frozen():
    cfg = GuardConfig()
    with pytest.raises(ValidationError):
        cfg.min_source_similarity = 0.9  # type: ignore[misc]


def test_default_matches_historical_constants():
    cfg = GuardConfig()
    # Stage C
    assert cfg.min_source_similarity == 0.35
    assert cfg.neighbour_margin == 0.15
    assert cfg.duplicate_threshold == 0.85
    assert cfg.duplicate_source_min_diff == 0.70
    assert cfg.absorption_length_ratio == 1.2
    assert cfg.absorption_concat_similarity == 0.8
    # Stage B
    assert cfg.part1_max_word_growth == 1
    assert cfg.part1_last_word_char_growth == 3
    assert cfg.part1_char_growth_ratio == 1.4
    assert cfg.part1_char_growth_slack == 8
    assert cfg.part2_collapse_ratio == 0.4
    # Stage A
    assert cfg.pair_drift_part1_word_growth == 2
    assert cfg.pair_drift_part2_collapse_ratio == 0.4


def test_fingerprint_is_stable_and_deterministic():
    a = GuardConfig().policy_fingerprint()
    b = GuardConfig().policy_fingerprint()
    assert a == b
    assert len(a) == 16
    assert DEFAULT_GUARD_CONFIG.policy_fingerprint() == a


def test_fingerprint_changes_when_a_field_changes():
    base = GuardConfig().policy_fingerprint()
    tuned = GuardConfig(min_source_similarity=0.5).policy_fingerprint()
    assert base != tuned


def test_stricter_source_similarity_threads_through_check_line():
    """A correction that the default accepts must be rejected under a
    config demanding higher source similarity — proving the config is
    honoured, not ignored."""
    source = "hello world"
    corrected = "hallo warld"  # similar but not identical
    default = check_line(source, corrected)
    strict = check_line(
        source, corrected, config=GuardConfig(min_source_similarity=0.99)
    )
    assert default.accepted
    assert not strict.accepted
    assert strict.reason == "too_different_from_source"
    assert strict.text == source  # falls back to OCR


# ---------------------------------------------------------------------------
# GuardConfig.vision() — the VLM profile (§5.2 bis, the vision/QE programme)
# ---------------------------------------------------------------------------


def test_vision_relaxes_the_floor_and_widens_the_margin_scope():
    v = GuardConfig.vision()
    d = GuardConfig()
    # Source-similarity floor is relaxed …
    assert v.min_source_similarity < d.min_source_similarity
    # … and the margin is held against the whole page: the two are one
    # decision — the low floor is only safe with the wide scope (VR-7).
    assert v.attachment_scope == "page" and d.attachment_scope == "adjacent"
    # … but every inter-line migration guard keeps the text default.
    assert v.neighbour_margin == d.neighbour_margin
    assert v.absorption_length_ratio == d.absorption_length_ratio
    assert v.absorption_concat_similarity == d.absorption_concat_similarity
    assert v.duplicate_threshold == d.duplicate_threshold
    assert v.part1_max_word_growth == d.part1_max_word_growth
    assert v.part2_collapse_ratio == d.part2_collapse_ratio
    assert v.pair_drift_part1_word_growth == d.pair_drift_part1_word_growth


def test_vision_override_wins():
    assert GuardConfig.vision(min_source_similarity=0.22).min_source_similarity == 0.22
    # An unrelated override still applies on top of the vision floor.
    v = GuardConfig.vision(neighbour_margin=0.05)
    assert v.neighbour_margin == 0.05
    assert v.min_source_similarity == GuardConfig.vision().min_source_similarity


def test_vision_is_fingerprinted_distinctly():
    """Choosing the vision profile is a structurally recorded decision."""
    assert (
        GuardConfig.vision().policy_fingerprint() != GuardConfig().policy_fingerprint()
    )


def test_vision_accepts_a_heavy_correction_the_text_default_rejects():
    """A VLM reading a badly-garbled line legitimately diverges far from the
    OCR source; the text default rejects it, the vision profile keeps it."""
    source = "Rcs~ırc"  # heavily garbled OCR (source similarity ~0.29)
    corrected = "Messire"
    assert not check_line(source, corrected).accepted  # text default rejects
    accepted = check_line(source, corrected, config=GuardConfig.vision())
    assert accepted.accepted and accepted.text == corrected


def test_vision_still_blocks_inter_line_migration():
    """Relaxing source-similarity must NOT open the door to a correction
    that absorbs its neighbour — the migration guards stay intact."""
    source = "the cat"
    nxt = "sat down"
    corrected = "the cat sat down"  # absorbs the next line
    res = check_line(source, corrected, next_ocr=nxt, config=GuardConfig.vision())
    assert not res.accepted
    assert res.reason in {"absorbs_next_line", "closer_to_next_line"}
    assert res.text == source
