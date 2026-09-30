"""VR-12 — a half-line written from nowhere, behind an opt-in guard.

The floor compares whole lines, so a correction whose first half has no
support in the source and whose second half is right passes it. The guard
counts, word by word, the longest run of the correction the source cannot
vouch for, laid against it in order. It is OFF by default: measured on
32 470 changed lines (``hans``, H23) nothing in the text separates an
invention from words the OCR had missed and the model read off the image,
so stopping the first costs some of the second, and that trade is the
consumer's.
"""

from __future__ import annotations

import pytest

from saknussemm.core.decide import FALLBACK_REASON_CODES
from saknussemm.core.guards import check_line, unanchored_run
from saknussemm.core.schemas import GuardConfig

# The line that opened VR-12 (hans H19, *Regards* D4 line_19), simplified.
SOURCE = "raison au sein de l'Union rationaliste, lutte contre le fascisme et contre la guer-"
INVENTED = "Lutte contre l'impérialisme des puissances, lutte contre le fascisme et contre la guer-"

STRICT = GuardConfig(max_unanchored_words=2)


def test_the_default_config_does_not_run_the_guard() -> None:
    assert GuardConfig().max_unanchored_words is None
    assert check_line(SOURCE, INVENTED).accepted


def test_a_half_line_from_nowhere_is_refused_when_the_guard_is_on() -> None:
    result = check_line(SOURCE, INVENTED, config=STRICT)
    assert not result.accepted
    assert result.reason == "unanchored_run"
    assert result.text == SOURCE


def test_the_reason_is_part_of_the_closed_set() -> None:
    assert "unanchored_run" in FALLBACK_REASON_CODES


@pytest.mark.parametrize(
    ("source", "corrected", "run"),
    [
        # an ordinary correction: every word resembles its source word
        ("Ie ne fcay ce que ie veux", "Ie ne sçay ce que ie veux", 0),
        # the founding case: the invented half reuses words that exist
        # further along the source, which a bag of words would call anchored
        (SOURCE, INVENTED, 5),
        # a split and a merge leave their words findable as substrings
        ("Maisiepenfois a vous", "Mais ie penfois a vous", 0),
        ("au jourd hui", "aujourd hui", 0),
        # a prefix taken from the line above
        (
            "tenu en juillet dernier le premier",
            "Mlle Thérèse Marodon, qui a obtenu en juillet dernier le premier",
            4,
        ),
        # words the OCR missed: the same shape as an invention, by design;
        # initials are transparent, so two names are a run of two
        (
            "TH. DE DONDER A. SUMMERFELD",
            "TH. DE DONDER P. ZEEMAN P. WEISS A. SUMMERFELD",
            2,
        ),
        # digits and punctuation are not words
        ("le 12 mai 1789", "le 14 mai 1799, enfin", 1),
        ("", "trois mots neufs", 3),
    ],
)
def test_the_run_is_counted_word_by_word(source: str, corrected: str, run: int) -> None:
    assert unanchored_run(source, corrected) == run


def test_two_unanchored_words_pass_at_the_measured_setting() -> None:
    """The measured setting tolerates a run of two: a proper noun restored,
    an article and its noun. Three is where the half-line begins."""
    source = "il vit le roi et partit"
    assert unanchored_run(source, "il vit le grand duc et partit") == 2
    assert check_line(source, "il vit le grand duc et partit", config=STRICT).accepted
    refused = check_line(source, "il vit le grand duc Albert et partit", config=STRICT)
    assert not refused.accepted and refused.reason == "unanchored_run"


def test_the_earlier_guards_still_speak_first() -> None:
    """A correction the floor already refuses keeps the floor's reason."""
    result = check_line(
        "abc def", "tout autre chose entièrement différente ici", config=STRICT
    )
    assert not result.accepted
    assert result.reason == "too_different_from_source"
