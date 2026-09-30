"""A ``ValueError`` raised by the ENGINE must fail the run, not degrade it.

`ADR-008` says recoverability is an allowlist and that "an unknown
exception must never become a silently-uncorrected success". The allowlist
named ``ValueError`` for it, and ``ValueError`` is not a synonym for
"the producer answered badly": ``pydantic.ValidationError`` inherits it, so
does ``json.JSONDecodeError``, and so does a plain ``setattr`` onto a
pydantic model with a misspelled field name.

The blast radius was the whole ``try`` in ``_attempt_chunk`` — the producer
call, the script normalisation, the usage accounting and the validation.
An engine bug anywhere in there looked exactly like a malformed proposal:
the chunk retried, descended, fell back to OCR, and the run returned a
result whose ``fallback_reason`` blamed the producer.

The fix is a boundary, not a narrower catch: a producer's own bare
``ValueError`` is still the documented malformed-output signal and is
classified AT the call, so tightening the allowlist costs producers
nothing. What no longer passes is a ``ValueError`` the engine raised
about itself.
"""

from __future__ import annotations

from typing import Any

import pytest

from saknussemm import CorrectionPipeline
from saknussemm.core.editing import EditScript, ReplaceLine
from saknussemm.errors import ProposalValidationError

from tests._paths import EXAMPLES


class _Null:
    def on_event(self, event_type: Any, payload: dict[str, Any]) -> None:
        return None


class _Upper:
    """Corrects every line, so a fallback is visible against a baseline."""

    async def produce(self, payload: Any, *, options: Any) -> Any:
        return EditScript(
            ops=[
                ReplaceLine(line_id=line.line_id, text=line.ocr_text.upper())
                for line in payload.lines
            ]
        ), None


def _run(producer: Any) -> Any:
    from saknussemm.formats.loader import build_document_manifest

    path = EXAMPLES / "sample.xml"
    manifest = build_document_manifest([(path, path.name)])
    return CorrectionPipeline(producer=producer, observer=_Null()).run_sync(
        document_manifest=manifest, source_files={path.name: path}
    )


def test_an_engine_value_error_fails_the_run_instead_of_falling_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The regression itself, driven through the public entry point.

    ``_script_to_raw`` stands in for any engine-side helper on the chunk
    path. Before the fix this run RETURNED, with every line reported
    ``all_attempts_exhausted`` — a library bug delivered as a
    successful, less-corrected document.
    """
    import saknussemm.core.attempt as attempt

    def _buggy(*args: Any, **kwargs: Any) -> Any:
        raise ValueError("engine bug: not a producer's malformed output")

    monkeypatch.setattr(attempt, "_script_to_raw", _buggy)

    with pytest.raises(ValueError, match="engine bug"):
        _run(_Upper())


def test_a_misspelled_trace_field_is_not_absorbed_either(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The amplifier that made the first test more than theoretical.

    ``_set_trace`` used ``**fields: object`` + ``setattr``, so ``mypy
    --strict`` could not see a typo and pydantic refused it as — of all
    things — a ``ValueError``. A misspelled trace field therefore emptied
    a chunk onto its OCR text and blamed the model for it.
    """
    import saknussemm.core.attempt as attempt

    def _typo(*args: Any, **kwargs: Any) -> Any:
        raise ValueError('"LineTrace" object has no field "projetced_text"')

    monkeypatch.setattr(attempt, "_record_proposal_traces", _typo)

    with pytest.raises(ValueError, match="no field"):
        _run(_Upper())


def test_a_producer_raising_a_bare_value_error_still_degrades() -> None:
    """The compatibility the boundary buys.

    A producer signalling malformed output with a bare ``ValueError`` is
    the historical contract. It must still retry and fall back — narrowing
    the allowlist must not turn a producer's own signal into a crash.
    """

    class _BadOutput:
        async def produce(self, payload: Any, *, options: Any) -> Any:
            raise ValueError("could not parse my own response")

    result = _run(_BadOutput())
    reasons = [
        line.decision.reason.code
        for line in result.report.lines
        if line.decision.reason is not None
    ]
    assert reasons, "the producer's ValueError did not reach a reported fallback"
    assert all(r == "all_attempts_exhausted" for r in reasons), reasons


def test_a_producer_raising_proposal_validation_error_still_degrades() -> None:
    """The classified half of the same family, unchanged."""

    class _Invalid:
        async def produce(self, payload: Any, *, options: Any) -> Any:
            raise ProposalValidationError("line count mismatch")

    result = _run(_Invalid())
    assert any(
        line.decision.reason is not None
        and line.decision.reason.code == "all_attempts_exhausted"
        for line in result.report.lines
    )
