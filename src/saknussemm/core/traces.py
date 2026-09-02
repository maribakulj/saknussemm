"""Writing onto a line's trace, when there is one.

Lifted out of the orchestrator because several modules now need this
and none of them should reach into the pipeline for it.

**Why the fields are spelled out.** This was ``**fields: object`` followed
by ``setattr``, which is shorter and hides two things a strict project
should not hide. ``mypy --strict`` cannot see a misspelled field name, and
pydantic refuses one at runtime as a ``ValueError`` — which the chunk
retry loop then read as a malformed producer response, emptying the chunk
onto its OCR text and blaming the model. Five explicit parameters cost
more lines than one ``**fields`` and buy the typo back at the call site,
where it is a type error rather than a fallback.
"""

from __future__ import annotations

from saknussemm.core.identity import LineRef, line_ref
from saknussemm.core.schemas import LineManifest, LineTrace, ProposalFeatures


class _Unset:
    """Absence, distinct from ``None``.

    ``None`` is a legal value for every field below — a line whose
    correction was reverted really does project ``None`` — so "not passed"
    needs a value of its own rather than a falsy one.
    """

    __slots__ = ()


_UNSET = _Unset()


def _set_trace(
    traces: dict[LineRef, LineTrace] | None,
    lm: LineManifest,
    *,
    model_input_text: str | None | _Unset = _UNSET,
    model_corrected_text: str | None | _Unset = _UNSET,
    projected_text: str | None | _Unset = _UNSET,
    validation_status: str | None | _Unset = _UNSET,
    proposal_features: ProposalFeatures | None | _Unset = _UNSET,
) -> None:
    """Assign trace fields on the LineTrace keyed by ``lm``, if tracked.

    Centralises the ``if traces is not None: t = traces.get(...);
    if t is not None: ...`` pattern that was repeated five times in
    ``_run_chunk`` and its helpers. A trace dict that isn't tracking
    a given line silently no-ops.
    """
    if traces is None:
        return
    trace = traces.get(line_ref(lm))
    if trace is None:
        return
    if not isinstance(model_input_text, _Unset):
        trace.model_input_text = model_input_text
    if not isinstance(model_corrected_text, _Unset):
        trace.model_corrected_text = model_corrected_text
    if not isinstance(projected_text, _Unset):
        trace.projected_text = projected_text
    if not isinstance(validation_status, _Unset):
        trace.validation_status = validation_status
    if not isinstance(proposal_features, _Unset):
        trace.proposal_features = proposal_features


def _finalize_chunk_traces(
    *,
    chunk_lines: list[LineManifest],
    traces: dict[LineRef, LineTrace] | None,
) -> None:
    """Project a chunk's post-acceptance state onto the traces (when the
    host opted in by passing a non-None ``traces`` dict).

    Duplicate detection is not chunk business anymore: the single
    document-wide adjacency pass runs after the page loop, so the
    state projected here is provisional until that pass ran.
    """
    for lm in chunk_lines:
        _set_trace(
            traces,
            lm,
            projected_text=(
                lm.corrected_text if lm.corrected_text is not None else lm.ocr_text
            ),
            validation_status=lm.status.value,
        )
