"""One chunk, asked of a producer until it answers or the budget runs out.

The narrowest loop in the engine, and the one that was hardest to read: a
single 221-line method held what to ask, how to ask it again, what came
back, and what to record — four different jobs, only one of which is
control flow. They are four functions now, and the loop reads as the
retry policy it implements:

  - :func:`_build_correction_request` — what the producer is asked, and
    the input side of the trace;
  - :func:`_produce` — the call itself, stopping at the raw
    :class:`EditScript`, and :func:`_script_to_raw` to put that script in
    the shape the validator checks;
  - :func:`_validate_and_capture` — what happens to what came back:
    proposal traces, validation, and capturing the ops actually applied;
  - :func:`_handle_failed_attempt` — what a failure means and what a
    retry costs;
  - :func:`_attempt_chunk` — the loop itself, and nothing else.

Free functions: the retry policy that shapes the ramp, the guard config the
validator and the span protocol read, and the observer callback all arrive
as arguments. An attempt is a call over a chunk and a policy, not a property
of a run.

**This function never applies the OCR fallback.** That decision — and the
warning event that goes with it — belongs to the caller, which may descend
a granularity instead.
"""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from saknussemm.core import events as ev
from saknussemm.core.context import RunContext
from saknussemm.core.editing import (
    EditRejection,
    EditOp,
    EditScript,
    ReplaceLine,
    ReplaceSpan,
    apply_edit_script,
)
from saknussemm.core.hyphenation import enrich_chunk_lines
from saknussemm.core.identity import LineRef
from saknussemm.core.protocols import (
    EditProducer,
    ProducerOptions,
    ProviderPermanentError,
    ProviderTransientError,
)
from saknussemm.core.redaction import sanitize_error
from saknussemm.core.retry import _RetryDecision, _classify_retry
from saknussemm.core.traces import _set_trace
from saknussemm.core.schemas import (
    ChunkRequest,
    CorrectionRequest,
    GuardConfig,
    HyphenRole,
    LineManifest,
    LineTrace,
    ProposalBatch,
    RefusedEdit,
    RetryPolicy,
    Usage,
)
from saknussemm.core.validator import HyphenIntegrityError, validate_llm_response

# ADR-008 (revised) — recoverability is an ALLOWLIST. Exactly the two
# families the retry classifier can route are recoverable on the
# producer-attempt path:
#   - ProviderTransientError — transport flakiness a conforming provider
#     wrapped (wrapping is the provider CONTRACT, not a courtesy: the
#     provider-agnostic pipeline cannot name raw httpx/SDK exceptions,
#     so an unwrapped one is indistinguishable from a bug and fails the
#     run rather than degrading to a fake success);
#   - ValueError — the documented malformed-producer-output family
#     (ProposalValidationError, HyphenIntegrityError, json.JSONDecodeError all
#     inherit it; §8.4 keeps them value-shaped for exactly this route).
# Everything else — RuntimeError, KeyError, a pydantic bug, an SDK
# exception nobody classified — fails the run: an unknown exception
# must never become a silently-uncorrected "success".
_RECOVERABLE_ERROR_TYPES: tuple[type[BaseException], ...] = (
    ProviderTransientError,
    ValueError,
)


@dataclass(frozen=True)
class _Proposed:
    """What a producer's script became: the batch to validate, and the lines
    whose ops the guards refused.

    One value rather than two parameters: they come from the same
    computation and are only correct together.
    """

    raw: dict[str, Any]
    #: The refusals themselves, not just which lines they hit: the reason
    #: is what makes a refusal rate actionable, and `A2b` puts it on the
    #: report for exactly that.
    refusals: tuple[EditRejection, ...]

    @property
    def refused_lines(self) -> frozenset[str]:
        return frozenset(r.line_id for r in self.refusals)


def _script_to_raw(
    script: EditScript,
    chunk_lines: list[LineManifest],
    *,
    producer: EditProducer,
    guard_config: GuardConfig,
    target_line_ids: set[str],
) -> _Proposed:
    """Normalise a producer's EditScript into the validator's raw shape.

    - ``replace_line`` ops pass through as-is (duplicates and empty
      texts included — the validator's structural checks must see them
      exactly as the historical raw response did).
    - ``replace_span`` ops are normalised and applied against the
      chunk's canonical text via :func:`apply_edit_script` (E1–E5); a
      rejected op leaves its line uncovered.
    - When the producer declares ``requires_full_coverage = False``
      (deterministic producers: no op == no edit), uncovered lines are
      filled with their canonical text so the validator's 1:1 check
      passes. An LLM producer keeps full-coverage semantics: a dropped
      target line stays missing → ProposalValidationError → retry.
    """
    canonical = {lm.line_id: lm.ocr_text for lm in chunk_lines}
    entries: list[dict[str, str]] = []
    refusals: tuple[EditRejection, ...] = ()

    span_ops = [op for op in script.ops if isinstance(op, ReplaceSpan)]
    for op in script.ops:
        if isinstance(op, ReplaceLine):
            entries.append({"line_id": op.line_id, "corrected_text": op.text})
    if span_ops:
        span_result = apply_edit_script(
            EditScript(ops=list(span_ops)),
            canonical,
            # The TARGETS, not every line in the chunk. Passing every line
            # made `E1`'s first clause unreachable — it could only be true
            # where the second already was — so an edit landing on a context
            # line was silently dropped downstream instead of refused here.
            # The drop and the refusal produce the same corrected text; only
            # one of them tells the operator it happened.
            chunk_line_ids=target_line_ids,
            guard_config=guard_config,
            line_by_id={lm.line_id: lm for lm in chunk_lines},
        )
        for lid, txt in span_result.text_by_id.items():
            entries.append({"line_id": lid, "corrected_text": txt})
        # The refused lines must travel. Dropped here, and with
        # ``requires_full_coverage = False``, the next block fills them with
        # their canonical text — so the report sees ``produced == final``,
        # concludes the op survived every guard, and PUBLISHES it. Measured
        # 2026-08-17: delivered
        # 'Le peuple att-', published the refused span, and a consumer
        # replaying the script got 'Le peuple -'.
        refusals = tuple(span_result.rejected)

    if not getattr(producer, "requires_full_coverage", True):
        covered = {e["line_id"] for e in entries}
        for lid, txt in canonical.items():
            if lid not in covered:
                entries.append({"line_id": lid, "corrected_text": txt})

    return _Proposed(raw={"lines": entries}, refusals=refusals)


def _build_correction_request(
    *,
    ctx: RunContext,
    chunk: ChunkRequest,
    chunk_lines: list[LineManifest],
    all_lines_by_id: dict[str, LineManifest],
    producer: EditProducer,
    traces: dict[LineRef, LineTrace] | None,
) -> CorrectionRequest:
    """What this attempt asks the producer, and what the trace records
    having asked.

    The enrichment is what the producer actually sees, so it is also what
    the trace's input side must hold — recording the raw manifest text
    there would describe a call that never happened. §4.1: the page's
    vision envelope is copied in only when the producer asks for it, and
    the library never opens it (I4).
    """
    enriched = enrich_chunk_lines(
        chunk_lines,
        all_lines_by_id,
        include_geometry=getattr(producer, "wants_geometry", False),
        page_dims=ctx.page_dims,
    )
    enriched_by_id = {e.line_id: e for e in enriched}
    for lm in chunk_lines:
        ei = enriched_by_id.get(lm.line_id)
        if ei is not None:
            _set_trace(traces, lm, model_input_text=ei.ocr_text)

    return CorrectionRequest(
        granularity=chunk.granularity,
        document_id=chunk.document_id,
        page_id=chunk.page_id,
        block_id=chunk.block_id,
        lines=enriched,
        image_ref=(
            ctx.image_ref_by_page_id.get(chunk.page_id)
            if getattr(producer, "wants_image", False)
            else None
        ),
    )


def _record_proposal_traces(
    raw: dict[str, Any],
    chunk_lines: list[LineManifest],
    traces: dict[LineRef, LineTrace] | None,
) -> None:
    """Record what the producer PROPOSED, before any guard sees it.

    Deliberately the raw text: the proposal stage is the audit trail of
    what was actually said, and a normalised copy of it would answer a
    different question than the one an auditor is asking.
    """
    lm_by_id = {lm.line_id: lm for lm in chunk_lines}
    for rl in raw.get("lines", []) if isinstance(raw, dict) else []:
        if not isinstance(rl, dict):
            continue
        target = lm_by_id.get(rl.get("line_id", ""))
        if target is not None:
            _set_trace(
                traces, target, model_corrected_text=rl.get("corrected_text", "")
            )


def _declared_subs_content(chunk_lines: list[LineManifest]) -> dict[str, str]:
    """The ``SUBS_CONTENT`` the SOURCE declared, per opening line.

    Read straight off each line's own fields — no partner is resolved
    here, and none may be: this is the markup's own word for the unit,
    handed to the validator so a proposal cannot contradict it.
    """
    declared: dict[str, str] = {}
    for lm in chunk_lines:
        if lm.hyphen_role == HyphenRole.PART1 and lm.hyphen_subs_content:
            declared[lm.line_id] = lm.hyphen_subs_content
        elif lm.hyphen_role == HyphenRole.BOTH and lm.hyphen_forward_subs_content:
            declared[lm.line_id] = lm.hyphen_forward_subs_content
    return declared


def _capture_producer_ops(
    *,
    ctx: RunContext,
    chunk: ChunkRequest,
    script: EditScript,
    response: ProposalBatch,
    refused_lines: frozenset[str],
) -> None:
    """§4 — remember each TARGET line's ops and the text they produced.

    Captured pre-guard and pre-reconcile, and NOT emitted as the final
    EditScript from here: a line later reverted (duplicate, rejected by
    ``check_line``) or reconciled to different text must not leave a
    stale op behind — a dry-run consumer replaying it would diverge from
    the pipeline's own corrected XML. ``_build_final_edit_script``
    reconciles these against the FINAL per-line state, keeping the
    producer's op TYPE (e.g. a rules producer's ``replace_span``) where
    its output survived unchanged.
    """
    target_ids = set(chunk.targets())
    produced_by_line = {o.line_id: o.corrected_text for o in response.lines}
    ops_by_line: dict[str, list[EditOp]] = {}
    for op in script.ops:
        if op.line_id in refused_lines:
            continue  # an op the guards refused produced nothing to publish
        if op.line_id in target_ids and op.line_id in produced_by_line:
            ops_by_line.setdefault(op.line_id, []).append(op)
    for line_id, line_ops in ops_by_line.items():
        # Chunks are page-scoped, so chunk.page_id qualifies every target
        # line unambiguously.
        ctx.producer_ops[LineRef(page_id=chunk.page_id, line_id=line_id)] = (
            line_ops,
            produced_by_line[line_id],
        )


def _validate_and_capture(
    *,
    ctx: RunContext,
    chunk: ChunkRequest,
    chunk_lines: list[LineManifest],
    hyphen_pairs: dict[str, str],
    proposed: _Proposed,
    script: EditScript,
    guard_config: GuardConfig,
    traces: dict[LineRef, LineTrace] | None,
) -> ProposalBatch:
    """Record what was proposed, check it, and capture what it applied.

    Raises the malformed-output family (all ``ValueError``) on a proposal
    the validator refuses, which is what puts the attempt loop back into
    its retry branch — and why the caller counts this call's tokens
    BEFORE getting here: they were spent either way.
    """
    _record_proposal_traces(proposed.raw, chunk_lines, traces)

    declared_subs = _declared_subs_content(chunk_lines)
    response = validate_llm_response(
        proposed.raw,
        [lm.line_id for lm in chunk_lines],
        hyphen_pairs if hyphen_pairs else None,
        {lm.line_id: lm.ocr_text for lm in chunk_lines},
        declared_subs if declared_subs else None,
        guard_config=guard_config,
        # The 1:1 count is enforced on targets; a missing context
        # line's output is not an error (it belongs to an adjacent chunk).
        target_line_ids=chunk.target_line_ids,
    )
    ctx.edit_rejections.extend(
        RefusedEdit(
            page_id=chunk.page_id,
            line_id=refusal.line_id,
            op=refusal.op,
            reason=refusal.reason,
            detail=refusal.detail,
        )
        for refusal in proposed.refusals
    )
    _capture_producer_ops(
        ctx=ctx,
        chunk=chunk,
        script=script,
        response=response,
        refused_lines=proposed.refused_lines,
    )
    return response


def _without_pairs(
    exc: HyphenIntegrityError,
    script: EditScript,
    propose: Callable[[EditScript], ProposalBatch],
    source_by_id: dict[str, str],
) -> tuple[ProposalBatch, frozenset[str]]:
    """The reply with the refused hyphen pair(s) put back to OCR, validated.

    Stage A refused the reply for ONE pair; until VR-10 that refusal cost
    the whole chunk: retried, downgraded, and finally every line returned
    to OCR. Measured on NewsEye (1930s press through the pipeline), a
    garbled PART2 read as a single word did that to 64 chunks on one page
    — 180 lines that had nothing to do with the pair, and were, corrected
    by another producer, exactly as good as any other line (72 % better,
    18 % worse: the corpus-wide rate). So on the LAST attempt the pair's
    ops are dropped, the reply is re-validated with no further call
    (``propose`` is the loop's own normalise-and-validate step) with the
    pair's own ops replaced by identities — full coverage still holds — and
    the pair is reported ``pair_drift_fallback`` while the other lines go
    through Stage B and C like any accepted reply. A second pair refused
    in the same reply is dropped the same way; any other error propagates.
    """
    dropped: set[str] = set()
    while True:
        dropped.update(exc.line_ids)
        # The pair stays IN the reply, as itself: a producer that promised
        # full coverage must still cover it, so its ops become identities.
        kept = EditScript(
            ops=[op for op in script.ops if op.line_id not in dropped]
            + [
                ReplaceLine(line_id=lid, text=source_by_id[lid])
                for lid in sorted(dropped)
                if lid in source_by_id
            ]
        )
        try:
            return propose(kept), frozenset(dropped)
        except HyphenIntegrityError as again:
            if not again.line_ids or set(again.line_ids) <= dropped:
                raise
            exc = again


def _propose(
    script: EditScript,
    *,
    ctx: RunContext,
    chunk: ChunkRequest,
    chunk_lines: list[LineManifest],
    hyphen_pairs: dict[str, str],
    producer: EditProducer,
    guard_config: GuardConfig,
    traces: dict[LineRef, LineTrace] | None,
) -> ProposalBatch:
    """Normalise a script into the validator's shape and validate it — the
    loop's own step, also what :func:`_without_pairs` re-runs."""
    proposed = _script_to_raw(
        script,
        chunk_lines,
        producer=producer,
        guard_config=guard_config,
        target_line_ids=set(chunk.targets()),
    )
    return _validate_and_capture(
        ctx=ctx,
        chunk=chunk,
        chunk_lines=chunk_lines,
        hyphen_pairs=hyphen_pairs,
        proposed=proposed,
        script=script,
        guard_config=guard_config,
        traces=traces,
    )


def _pair_fallback(
    exc: Exception,
    *,
    attempt: int,
    max_attempts: int,
    script: EditScript | None,
    propose: Callable[[EditScript], ProposalBatch],
    chunk: ChunkRequest,
    chunk_lines: list[LineManifest],
    emit: Callable[[ev.EngineEvent], None],
) -> tuple[ProposalBatch, frozenset[str]] | None:
    """VR-10 — on the LAST attempt, a hyphen pair the validator still refuses
    falls alone and the rest of the reply stands. ``None`` in every other
    case, and the ordinary failure path takes over."""
    if not (
        isinstance(exc, HyphenIntegrityError)
        and exc.line_ids
        and attempt == max_attempts
        and script is not None
    ):
        return None
    source_by_id = {lm.line_id: lm.ocr_text for lm in chunk_lines}
    response, dropped = _without_pairs(exc, script, propose, source_by_id)
    emit(
        ev.Warning(
            chunk_id=chunk.chunk_id,
            message=f"pair_drift_fallback: {sorted(dropped)} — "
            f"{sanitize_error(str(exc))[:100]}",
        )
    )
    return response, dropped


async def _produce(
    *,
    ctx: RunContext,
    chunk: ChunkRequest,
    producer: EditProducer,
    chunk_lines: list[LineManifest],
    all_lines_by_id: dict[str, LineManifest],
    traces: dict[LineRef, LineTrace] | None,
    attempt: int,
    temperature: float,
) -> tuple[EditScript, Usage | None]:
    """Ask the producer once, and return what it said.

    Deliberately stops at the raw :class:`EditScript`: what came back is
    not yet known to be usable, and the caller must charge this call's
    tokens before finding out — they were spent either way.
    """
    payload = _build_correction_request(
        ctx=ctx,
        chunk=chunk,
        chunk_lines=chunk_lines,
        all_lines_by_id=all_lines_by_id,
        producer=producer,
        traces=traces,
    )
    # The producer gets a per-call envelope, not the engine's whole
    # RetryPolicy: the ramp (and the hyphen 0.0 pin) is decided by the
    # caller; the probe lets long I/O be abandoned mid-flight. Count every
    # invocation (this attempt hits the producer whether or not it
    # succeeds): the real cost.
    ctx.producer_calls += 1
    return await producer.produce(
        payload,
        options=ProducerOptions(
            attempt=attempt,
            temperature=temperature,
            should_abort=ctx.should_abort,
        ),
    )


def _failure_family(exc: BaseException) -> str:
    """Which of the two recoverable families this failure belongs to.

    Both end the same way — attempts run out, the chunk falls back, and the
    report says ``all_attempts_exhausted`` — but they mean opposite things to
    whoever reads it. **Transport** means the run was throttled or the network
    faltered: the model was never asked, and asking again later would work.
    **Malformed output** means the producer answered and could not hold the
    contract: asking again changes nothing until the producer does.

    Conflating them is not academic. Measured on 2026-08-18: running three
    jobs against one rate-limited account turned sustained 429s into chunk
    fallbacks, and the same page went from 67 % of lines corrected to 37 %.
    Every one of those failures was reported as the model failing. An operator
    reading that concludes their model is bad and changes it, when what they
    needed was to stop hammering their own quota.

    The distinction already exists — ``_RECOVERABLE_ERROR_TYPES`` is built on
    it — it simply stopped travelling at the point the message was built.
    """
    return "transport" if isinstance(exc, ProviderTransientError) else "producer_output"


async def _handle_failed_attempt(
    *,
    exc: Exception,
    ctx: RunContext,
    chunk: ChunkRequest,
    attempt: int,
    max_attempts: int,
    hyphen_already_seen: bool,
    retry_policy: RetryPolicy,
    emit: Callable[[ev.EngineEvent], None],
) -> tuple[bool, _RetryDecision, str]:
    """Decide what a failed attempt means, and pay for the retry if there
    is one.

    Re-raises anything outside the recoverable allowlist (ADR-008): only
    the two families the classifier can route degrade to
    retry-then-OCR-fallback. A programming error, an unwrapped SDK
    transport exception or a broken invariant FAILS the run — masking one
    as uncorrected OCR text would degrade EVERY chunk while still
    reporting success. Providers signal transport flakiness by wrapping it
    as ``ProviderTransientError`` (their contract).

    Returns ``(will_retry, decision, sanitised_msg)``. When ``will_retry``
    the backoff has already been slept and the ``retry`` event emitted.
    """
    if not isinstance(exc, _RECOVERABLE_ERROR_TYPES):
        raise exc
    # The pipeline holds no credentials, but a producer may still leak a
    # secret-shaped substring into a message; the consumer layer (which DOES
    # hold the key) sanitises again on its own error paths.
    msg = f"{_failure_family(exc)}: {sanitize_error(str(exc))}"
    decision = _classify_retry(
        exc=exc,
        sanitised_msg=msg,
        attempt=attempt,
        hyphen_already_seen=hyphen_already_seen,
        policy=retry_policy,
    )
    will_retry = attempt < max_attempts and decision.is_retryable
    if will_retry:
        if decision.backoff > 0:
            await asyncio.sleep(decision.backoff)
        emit(
            ev.Retry(chunk_id=chunk.chunk_id, attempt=attempt, error=decision.error_tag)
        )
        ctx.retry_count += 1
    return will_retry, decision, msg


@dataclass(frozen=True)
class _AttemptOutcome:
    """What a chunk's attempt loop has to say when it stops.

    A five-slot tuple said the same thing and made every field a position
    to remember at the call site — including two that only mean anything
    on failure.
    """

    #: The validated batch, or ``None`` when no attempt produced one.
    response: ProposalBatch | None
    #: Attempts consumed, charged by the caller to the per-chunk budget.
    attempts_used: int
    #: On failure: the terminal error was retryable, so the same work is
    #: worth another try at a finer granularity. A hard error (e.g. a
    #: 4xx) is ``False`` — smaller chunks would hit the same wall.
    can_downgrade: bool
    #: The sanitised terminal error message, empty on success.
    last_msg: str
    #: Tokens this chunk spent across EVERY call of the loop, including
    #: calls whose response later failed validation — they were spent
    #: regardless, and the chunk_completed event reports the true total.
    usage: Usage | None
    #: The hyphen pair the loop put back to its OCR text on the last
    #: attempt so the rest of the reply could stand (VR-10). The caller
    #: falls these lines back as ``pair_drift_fallback``; empty otherwise.
    neutralised: frozenset[str] = frozenset()


async def _attempt_chunk(
    *,
    ctx: RunContext,
    chunk: ChunkRequest,
    producer: EditProducer,
    chunk_lines: list[LineManifest],
    hyphen_pairs: dict[str, str],
    all_lines_by_id: dict[str, LineManifest],
    traces: dict[LineRef, LineTrace] | None,
    max_attempts: int,
    retry_policy: RetryPolicy,
    guard_config: GuardConfig,
    emit: Callable[[ev.EngineEvent], None],
) -> _AttemptOutcome:
    """Call the edit producer with retries; return the outcome.

    Up to ``max_attempts`` (the caller's remaining budget), on the injected
    :class:`RetryPolicy`'s ramp — pinned to 0.0 after a hyphen violation,
    since a colder attempt sticks closer to source. VR-10 settles a pair the
    last attempt still refuses (:func:`_pair_fallback`).
    """
    hyphen_violation = False
    attempts_used = 0
    last_msg = ""
    chunk_usage = Usage()
    propose = functools.partial(
        _propose,
        ctx=ctx,
        chunk=chunk,
        chunk_lines=chunk_lines,
        hyphen_pairs=hyphen_pairs,
        producer=producer,
        guard_config=guard_config,
        traces=traces,
    )
    for attempt in range(1, max_attempts + 1):
        attempts_used = attempt
        temperature = 0.0 if hyphen_violation else retry_policy.temperature_for(attempt)
        script: EditScript | None = None
        try:
            script, usage = await _produce(
                ctx=ctx,
                chunk=chunk,
                producer=producer,
                chunk_lines=chunk_lines,
                all_lines_by_id=all_lines_by_id,
                traces=traces,
                attempt=attempt,
                temperature=temperature,
            )
            # Charged before validation: a response the validator goes
            # on to refuse still cost its tokens, and both the run's total
            # and this chunk's must say so.
            if usage is not None:
                ctx.usage = ctx.usage + usage
                chunk_usage = chunk_usage + usage
            response = propose(script)
            return _AttemptOutcome(response, attempts_used, False, "", chunk_usage)

        except ProviderPermanentError:
            # ADR-008 — credentials/model rejected: retrying is pointless
            # and falling back would fake success. Fatal for the run.
            raise
        except Exception as exc:
            settled = _pair_fallback(
                exc,
                attempt=attempt,
                max_attempts=max_attempts,
                script=script,
                propose=propose,
                chunk=chunk,
                chunk_lines=chunk_lines,
                emit=emit,
            )
            if settled is not None:
                return _AttemptOutcome(
                    settled[0], attempts_used, False, "", chunk_usage, settled[1]
                )
            will_retry, decision, last_msg = await _handle_failed_attempt(
                exc=exc,
                ctx=ctx,
                chunk=chunk,
                attempt=attempt,
                max_attempts=max_attempts,
                hyphen_already_seen=hyphen_violation,
                retry_policy=retry_policy,
                emit=emit,
            )
            if will_retry:
                if decision.is_hyphen_violation:
                    hyphen_violation = True
                continue
            # Exhausted, or non-retryable: the CALLER chooses between a
            # granularity downgrade and the OCR fallback.
            return _AttemptOutcome(
                None, attempts_used, decision.is_retryable, last_msg, None
            )

    # max_attempts <= 0 (no budget left): nothing attempted.
    return _AttemptOutcome(None, attempts_used, False, last_msg, None)
