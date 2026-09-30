"""Validator for LLM structured responses."""

from __future__ import annotations

from typing import Any, ClassVar, cast

from saknussemm.core._norm import has_line_separator, ncfold
from saknussemm.errors import ProposalValidationError
from saknussemm.core.pairing import strip_trailing_break_marks
from saknussemm.core.schemas import (
    DEFAULT_GUARD_CONFIG,
    GuardConfig,
    LineProposal,
    ProposalBatch,
)


class HyphenIntegrityError(ProposalValidationError):
    """Raised when an LLM response broke a hyphen-pair invariant.

    Subclass of :class:`saknussemm.errors.ProposalValidationError` (itself a
    ``SaknussemmError`` and a ``ValueError``, §8.4) so existing
    ``except ValueError`` catches keep working. Carrying the type
    explicitly lets the pipeline's retry classifier use ``isinstance(exc,
    HyphenIntegrityError)`` instead of substring-matching
    ``"hyphen_integrity_violation"`` in the exception message — a coupling
    to prose that no test protects. The retry SSE event still
    emits the literal ``"hyphen_integrity_violation"`` tag for the
    frontend consumer.
    """

    code: ClassVar[str] = "hyphen_integrity_violation"

    #: The pair the violation is about. Lets the attempt loop fall the PAIR
    #: back on its last attempt instead of refusing the whole reply (VR-10):
    #: measured on NewsEye, one garbled PART2 read as a single word cost 64
    #: whole chunks on one page. Empty only for a raise site that does not
    #: know the pair.
    line_ids: tuple[str, ...] = ()

    def __init__(self, message: str, *, line_ids: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.line_ids = line_ids


def _checked_text(
    line_id: str, corrected_text: object, ocr_texts: dict[str, str] | None
) -> str:
    """The proposed text, or raise if it would erase a line that had content.

    Whitespace-only values ("   ", "\\t", NBSP) are as empty as "": the
    rewriter would write ``CONTENT="   "`` and silently obliterate the original
    word. ``.strip()`` catches every whitespace-only case.

    **Unless the source line is itself empty.** The rule exists to stop a model
    from ERASING a line that had content; a line that had none has nothing to
    erase, and an empty answer is the only honest one. An OCR engine that read
    nothing produces exactly that, and it is a real reading, not a failure.

    Measured on ``corpus/37-GT-BNL`` (2026-08-21): 6 empty source lines out of
    522 made 4 chunks of 12 exhaust their retries, and each whole chunk fell
    back — discarding **40 correct** corrections for the other lines. Six lines
    cost forty.
    """
    empty = not isinstance(corrected_text, str) or corrected_text.strip() == ""
    if not empty:
        return cast(str, corrected_text)
    # ``absent`` is NOT ``empty``: without the source text we cannot tell an
    # erasure from an honest blank, and the safe reading of ignorance is to
    # refuse. Only an explicitly empty source earns the exception.
    if ocr_texts is not None and line_id in ocr_texts:
        if ocr_texts[line_id].strip() == "":
            return ""
    raise ProposalValidationError(f"corrected_text for {line_id!r} is empty or missing")


def validate_llm_response(
    raw: dict[str, Any],
    expected_line_ids: list[str],
    hyphen_pairs: dict[str, str] | None = None,
    ocr_texts: dict[str, str] | None = None,
    hyphen_subs: dict[str, str] | None = None,
    *,
    guard_config: GuardConfig = DEFAULT_GUARD_CONFIG,
    target_line_ids: list[str] | None = None,
) -> ProposalBatch:
    """
    Validate an LLM response dict and return a typed ProposalBatch.

    Parameters
    ----------
    raw:
        Parsed JSON dict from the LLM.
    expected_line_ids:
        The line IDs the LLM was asked to correct.
    hyphen_pairs:
        Mapping of PART1 line_id → PART2 line_id (and vice-versa).
        When provided, additional hyphen-integrity checks are performed.
    ocr_texts:
        Mapping of line_id → original OCR text.  Used together with
        hyphen_pairs for semantic drift checks on hyphen-pair lines.
    hyphen_subs:
        Mapping of PART1 line_id → subs_content (the expected full word
        for the hyphen pair).  Used for fusion detection: if PART1
        corrected text equals the full word, the LLM illegally merged
        the pair.
    target_line_ids:
        The chunk's *target* lines. When provided, the 1:1 count is
        enforced on targets only: every target must be present exactly
        once; entries for *context* lines (in ``expected_line_ids`` but
        not targets) are accepted when present and their absence is NOT
        an error — their output belongs to an adjacent chunk anyway.
        Per-entry structural checks (dict shape, known id, no duplicate,
        non-empty single-line text) stay strict for every entry: garbage
        anywhere still signals a degraded response. Hyphen-integrity
        checks run over the target set (the planner pins both pair members
        into the same target set). ``None`` = every line is a target
        (historical behaviour, byte-compatible).

    Raises
    ------
    ValueError
        On any validation failure, with a descriptive message.
        Hyphen-integrity violations use message prefix
        "hyphen_integrity_violation".
    """
    # --- Basic structure ---
    # Guard against non-dict input UPFRONT with a ProposalValidationError: the
    # orchestrator's retry classifier only catches
    # `(ValueError, json.JSONDecodeError)`, so a provider returning
    # None/list/int must surface as a ValueError-shaped error to stay on
    # the standard retry path (a TypeError would bypass retries AND the
    # OCR fallback — ADR-008).
    if not isinstance(raw, dict):
        raise ProposalValidationError(
            f"LLM response is not a JSON object (got {type(raw).__name__})"
        )

    if "lines" not in raw:
        raise ProposalValidationError("Missing key 'lines' in LLM response")

    lines_raw = raw["lines"]
    if not isinstance(lines_raw, list):
        raise ProposalValidationError("'lines' must be a list")

    expected_set = set(expected_line_ids)
    # The ids whose output is REQUIRED. When target_line_ids is None
    # every expected line is a target (historical exact-count behaviour).
    check_set = expected_set if target_line_ids is None else set(target_line_ids)

    # --- Count ---
    if target_line_ids is None:
        if len(lines_raw) != len(expected_line_ids):
            raise ProposalValidationError(
                f"Line count mismatch: expected {len(expected_line_ids)}, got {len(lines_raw)}"
            )
    elif len(lines_raw) > len(expected_line_ids):
        # Targets mode: dedup + membership + targets-present cover the
        # counting; only a response LARGER than everything sent is flagged
        # here (it necessarily contains duplicates or unknown ids anyway,
        # but the early message is clearer).
        raise ProposalValidationError(
            f"Line count mismatch: sent {len(expected_line_ids)}, got {len(lines_raw)}"
        )

    seen_ids: set[str] = set()
    outputs: list[LineProposal] = []

    for entry in lines_raw:
        if not isinstance(entry, dict):
            raise ProposalValidationError(
                f"Each line entry must be a dict, got {type(entry)}"
            )

        line_id = entry.get("line_id")
        corrected_text = entry.get("corrected_text")

        if not line_id:
            raise ProposalValidationError(f"Entry missing 'line_id': {entry}")
        if line_id in seen_ids:
            raise ProposalValidationError(f"Duplicate line_id in response: {line_id!r}")
        if line_id not in expected_set:
            raise ProposalValidationError(f"Unknown line_id in response: {line_id!r}")

        seen_ids.add(line_id)

        corrected_text = _checked_text(line_id, corrected_text, ocr_texts)
        # Reject EVERY str.splitlines boundary, not just \n/\r:
        # U+2028/U+2029 (and \x0b \x0c \x85 \x1c-\x1e) would survive
        # clean_content into a single-line CONTENT attribute otherwise.
        if has_line_separator(corrected_text):
            raise ProposalValidationError(
                f"corrected_text for {line_id!r} contains a line separator"
            )

        outputs.append(LineProposal(line_id=line_id, corrected_text=corrected_text))

    # --- Check all REQUIRED (target) IDs are present ---
    missing = check_set - seen_ids
    if missing:
        raise ProposalValidationError(
            f"Missing line_ids in response: {sorted(missing)}"
        )

    # --- Hyphen integrity (over the required set — the planner keeps hyphen
    # pairs within one target set, so both members are guaranteed present) ---
    if hyphen_pairs:
        text_by_id = {o.line_id: o.corrected_text for o in outputs}
        _validate_hyphen_integrity(
            text_by_id,
            hyphen_pairs,
            check_set,
            ocr_texts or {},
            hyphen_subs or {},
            guard_config,
        )

    return ProposalBatch(lines=outputs)


def _validate_hyphen_integrity(
    text_by_id: dict[str, str],
    hyphen_pairs: dict[str, str],
    chunk_ids: set[str],
    ocr_texts: dict[str, str],
    hyphen_subs: dict[str, str],
    guard_config: GuardConfig = DEFAULT_GUARD_CONFIG,
) -> None:
    """
    Check that no hyphen-pair line has been illegally merged or shifted.

    hyphen_pairs maps PART1 → PART2 and PART2 → PART1 (both directions).
    We deduplicate via frozenset and check each pair once.

    Checks performed:
    1. Neither side is empty.
    2. PART1 word count didn't grow drastically (text pulled from PART2).
    3. PART2 word count didn't shrink drastically (absorbed by PART1).
    4. PART1 doesn't contain the full logical word (fusion with subs_content).
    """
    checked_pairs: set[frozenset[str]] = set()

    for id_a, id_b in hyphen_pairs.items():
        pair = frozenset({id_a, id_b})
        if pair in checked_pairs:
            continue
        if id_a not in chunk_ids or id_b not in chunk_ids:
            continue
        checked_pairs.add(pair)

        text_a = text_by_id.get(id_a, "")
        text_b = text_by_id.get(id_b, "")

        # 1. Either side being empty means illegal fusion/deletion
        if not text_a:
            raise HyphenIntegrityError(
                f"hyphen_integrity_violation: corrected_text for line {id_a!r} is empty",
                line_ids=(id_a, id_b),
            )
        if not text_b:
            raise HyphenIntegrityError(
                f"hyphen_integrity_violation: corrected_text for line {id_b!r} is empty",
                line_ids=(id_a, id_b),
            )

        # 2–3. Semantic drift checks (only when OCR source is available)
        ocr_a = ocr_texts.get(id_a, "")
        ocr_b = ocr_texts.get(id_b, "")
        if ocr_a and ocr_b:
            _check_pair_drift(id_a, id_b, text_a, text_b, ocr_a, ocr_b, guard_config)

    # 4. Fusion check: PART1 contains the full logical word
    for part1_id, subs_content in hyphen_subs.items():
        # Restrict to the target/required id set, exactly like the drift
        # checks above (loop 1-3). In window mode a chunk carries context
        # lines owned by an ADJACENT chunk; a context-only PART1 the LLM
        # happens to fuse must not fail THIS chunk (its output is discarded),
        # or valid TARGET corrections get thrown away on retry/fallback.
        if part1_id not in chunk_ids:
            continue
        if not subs_content or part1_id not in text_by_id:
            continue
        part1_text = text_by_id[part1_id]
        # Bare text: whitespace and the trailing break MARK, whichever of the
        # repertoire spells it (this was `rstrip("-")`, so a ⸗ or ¬ stayed
        # glued to the last word and the fusion comparison never matched).
        part1_words = strip_trailing_break_marks(part1_text.rstrip()).split()
        if not part1_words:
            continue
        part1_last_word = part1_words[-1]
        if ncfold(part1_last_word) != ncfold(subs_content):
            continue
        # Fusion is a DRIFT check, not a pattern check: when the SOURCE
        # line's own last word already equals the logical word
        # (degenerate one-letter fragments — 'A' + 'A' → word 'AA' on a
        # line reading 'AA-'), the word's presence carries no fusion
        # signal, and an identity proposal would be re-rejected on every
        # retry until the whole chunk hard-fails.
        ocr_words = strip_trailing_break_marks(
            ocr_texts.get(part1_id, "").rstrip()
        ).split()
        if ocr_words and ncfold(ocr_words[-1]) == ncfold(subs_content):
            continue
        raise HyphenIntegrityError(
            f"hyphen_integrity_violation: PART1 line {part1_id!r} "
            f"contains full logical word {subs_content!r} "
            f"(fusion detected)",
            line_ids=tuple(i for i in (part1_id, hyphen_pairs.get(part1_id)) if i),
        )


def _check_pair_drift(
    id_a: str,
    id_b: str,
    text_a: str,
    text_b: str,
    ocr_a: str,
    ocr_b: str,
    config: GuardConfig = DEFAULT_GUARD_CONFIG,
) -> None:
    """Raise if corrected texts diverge too much from their OCR sources."""
    ocr_a_wc = len(ocr_a.split())
    ocr_b_wc = len(ocr_b.split())
    cor_a_wc = len(text_a.split())
    cor_b_wc = len(text_b.split())

    # PART1 grew by more than the allowed word budget → probably pulled from PART2
    if cor_a_wc > ocr_a_wc + config.pair_drift_part1_word_growth:
        raise HyphenIntegrityError(
            f"hyphen_integrity_violation: PART1 line {id_a!r} grew from "
            f"{ocr_a_wc} to {cor_a_wc} words (text migration suspected)",
            line_ids=(id_a, id_b),
        )

    # PART2 shrank below the collapse ratio → absorbed by PART1
    if (
        ocr_b_wc >= config.pair_drift_part2_min_words
        and cor_b_wc < ocr_b_wc * config.pair_drift_part2_collapse_ratio
    ):
        raise HyphenIntegrityError(
            f"hyphen_integrity_violation: PART2 line {id_b!r} shrank from "
            f"{ocr_b_wc} to {cor_b_wc} words (text migration suspected)",
            line_ids=(id_a, id_b),
        )


# --- public surface ---
__all__ = [
    "validate_llm_response",
]
