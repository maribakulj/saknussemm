"""``with_corpus_notes`` — the campaign tells the prompt which century it is (VR-4)."""

from __future__ import annotations

from saknussemm.integrations.llm import (
    CORPUS_NOTE_EARLY_MODERN_FRENCH,
    SYSTEM_PROMPT,
    with_corpus_notes,
)
from saknussemm.integrations.page import PAGE_SYSTEM_PROMPT
from saknussemm.producers.vision import PAGE_VISION_SYSTEM_PROMPT


def test_notes_continue_the_prompts_own_numbering() -> None:
    out = with_corpus_notes(
        PAGE_SYSTEM_PROMPT, CORPUS_NOTE_EARLY_MODERN_FRENCH, "Autre."
    )
    assert out.startswith(PAGE_SYSTEM_PROMPT.rstrip())
    tail = out[len(PAGE_SYSTEM_PROMPT.rstrip()) :].strip().splitlines()
    assert tail[0].startswith("15. Ces pages sont des imprimés")
    assert tail[1] == "16. Autre."


def test_every_shipped_prompt_can_take_a_note() -> None:
    for prompt, first in ((SYSTEM_PROMPT, "14."), (PAGE_VISION_SYSTEM_PROMPT, "14.")):
        out = with_corpus_notes(prompt, "Note.")
        assert out.splitlines()[-1] == f"{first} Note."


def test_no_note_is_the_prompt_itself() -> None:
    assert with_corpus_notes(SYSTEM_PROMPT) == SYSTEM_PROMPT.rstrip()
