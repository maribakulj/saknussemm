"""What a run returns, and what a caller may do with it (ADR-011).

The engine never writes: it computes values and hands them back. This module
holds that value and the assembly of it — the shape of an answer, not
execution control.
"""

from __future__ import annotations

import json
import stat
import tempfile
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from saknussemm.core.context import RunContext
from saknussemm.errors import ConfigurationError
from saknussemm.core.decisions import DecisionSet
from saknussemm.core.identity import LineRef
from saknussemm.core.editing import EditScript
from saknussemm.core.hyphenation import ReconcileMetrics
from saknussemm.core.report import _build_final_edit_script
from saknussemm.core.schemas import CorrectionReport, LineTrace, Usage


def _portable_filename(name: str) -> str:
    """One filename identity for case-insensitive and Unicode-normalizing disks."""
    return unicodedata.normalize("NFD", name).casefold()


def _replace_output(path: Path, content: bytes) -> None:
    """Replace one directory entry without ever opening its previous target.

    The preflight refuses existing links. Replacement also protects against
    a link installed after that check: it replaces the link itself, without
    writing to the file it names. This is atomic per file, not per result.
    """
    try:
        previous = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        previous = None
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=".saknussemm-", suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        if previous is not None and stat.S_ISREG(previous.st_mode):
            temporary.chmod(stat.S_IMODE(previous.st_mode))
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@dataclass
class CorrectionResult:
    """Outcome of a full pipeline run.

    The input manifest is never mutated (ADR-011): what the run
    decided is read off ``decisions`` (and ``corrected_files`` for the
    artefacts). `traces` is the line-by-line text trace through every
    stage.
    """

    total_chunks: int
    total_reconciled: int
    retry_count: int
    #: Number of chunks whose producer attempts were exhausted (an
    #: orchestration counter — one rejected 20-line chunk counts once).
    fallback_chunks: int
    #: Number of LINES whose terminal status is ``FALLBACK`` — they kept
    #: their OCR source text, whether a whole chunk fell back, a guard
    #: rejected the correction, or a duplicate revert undid it. Manifest
    #: statuses are the authority; "completed with fallbacks" means
    #: exactly ``fallback_lines > 0``.
    fallback_lines: int
    #: Aggregated ``fallback_reason`` prefixes → line counts for the
    #: fallen lines (e.g. ``{"all_attempts_exhausted": 20}``), so a
    #: consumer can say WHY without parsing messages.
    fallback_reasons: dict[str, int]
    #: Number of LINES whose terminal status is ``REVIEW_REQUIRED`` —
    #: they kept their CORRECTION, and the run declares it has no means
    #: of establishing the change is right. Disjoint from
    #: ``fallback_lines``: a referred line was not taken away.
    #:
    #: Reading it as a failure count is the one mistake to avoid. It
    #: counts what the library refuses to VOUCH for, not what it got
    #: wrong — on the run this feature was measured against, the great
    #: majority of the flagged changes were good ones, which is exactly
    #: why they are delivered rather than reverted.
    review_lines: int
    #: Aggregated review-reason prefixes → line counts (e.g.
    #: ``{"digits_changed": 31, "proper_noun_changed": 12}``). One line
    #: can appear under several codes, so these sum to at least
    #: ``review_lines`` rather than to it.
    review_reasons: dict[str, int]
    traces: dict[LineRef, LineTrace]
    reconcile_metrics: ReconcileMetrics
    #: Aggregate token consumption across every producer call in the
    #: run (zero when no provider reported usage).
    usage: Usage
    #: §9 — public, versioned correction report (same line traces, promoted
    #: to a documented artefact). Present on every run, including dry runs.
    report: CorrectionReport
    #: §4 — the normalized EditScript the run applied, accumulated across
    #: chunks. In v1 the LLM path emits ``replace_line`` ops (byte-identical
    #: to the direct correction); a rules/​span producer surfaces its
    #: ``replace_span`` ops here too.
    edit_script: EditScript
    #: ADR-011 — the run's immutable :class:`DecisionSet`: one terminal
    #: decision per line in document reading order. The input manifest
    #: is never mutated, so THIS is where a caller reads
    #: what the run decided (``decisions.by_ref[LineRef(...)]``).
    decisions: DecisionSet
    #: ADR-011 — the corrected artefacts themselves, keyed by source file
    #: name, computed on EVERY run: the result IS the output; persisting
    #: it is the caller's choice (:meth:`write`, or a host-owned
    #: transaction with commit/discard semantics).
    corrected_files: dict[str, bytes] = field(default_factory=dict)
    #: Source files the run could NOT deliver, mapped to why: the rewritten
    #: artefact did not carry the run's decisions for that file.
    #:
    #: Such a file is **absent** from :attr:`corrected_files`, never present
    #: in a doubtful version — a lookup by name raises ``KeyError`` rather
    #: than handing back bytes nobody vouched for. Reading this dict is how
    #: a caller learns the output is a subset; :meth:`write` refuses the
    #: partial set outright unless told otherwise, so the common path cannot
    #: persist an incomplete volume by omission.
    #:
    #: Empty on a run that delivered everything, which is every run that
    #: does not hit a library defect: a divergence means the artefact and
    #: the decision disagree, and that has always been a bug rather than a
    #: cost of the format.
    undeliverable_files: dict[str, str] = field(default_factory=dict)
    #: lines the QE router judged already clean and SKIPPED
    #: (confirmed as-is, no producer call). 0 when routing is off. The
    #: economics signal: each skip is one LLM call not spent.
    lines_skipped: int = 0
    #: non-hyphen lines the QE router sent to ESCALATE and that
    #: were routed to the ``escalation_producer`` (a VLM) instead of the
    #: primary producer. 0 when no escalation producer is set. Each one is
    #: a line the hybrid judged worth the heavier (vision) call.
    escalated_lines: int = 0
    #: total ``producer.produce`` invocations (retries included):
    #: the run's real call cost. Falls when routing drops whole chunks —
    #: routing-on vs routing-off on one document is the cheaper-hybrid proof.
    producer_calls: int = 0

    def _refuse_colliding_names(self) -> None:
        """Two keys that flatten to one filename would silently lose one.

        ``Path(source_name).name`` below is a deliberate path-traversal
        guard, not an oversight: a key must never steer the write outside
        ``directory``. But it also flattens ``volume1/page.xml`` and
        ``volume2/page.xml`` onto one name. Measured 2026-08-17: ``write``
        **returned three paths and left two files on disk**, reporting
        that it had written ``page.xml`` twice while the second overwrote
        the first.

        The facade refuses duplicate basenames when it loads
        (`facade.load`), so the collision is only reachable through the
        low-level API — which is the one the sibling repositories use.
        This method is therefore about `write` defending its own contract
        rather than inheriting a guarantee from whichever door the object
        came through.

        Refusing before anything is written keeps the failure clean: no
        half-populated directory to reason about afterwards.
        """
        seen: dict[str, str] = {}
        for source_name in self.corrected_files:
            flattened = Path(source_name).name
            if flattened in {"", ".", ".."}:
                raise ConfigurationError(
                    f"{source_name!r} has no usable output filename. "
                    "Each source must name a file, not a directory."
                )
            # Conservative across filesystems: names must remain distinct
            # under both Unicode decomposition and case-insensitive lookup.
            portable_name = _portable_filename(flattened)
            # Reserve both names even when this run has no sidecar, and on
            # case-insensitive filesystems as well as case-sensitive ones.
            if portable_name in {"report.json", "sidecar.json"}:
                raise ConfigurationError(
                    f"{source_name!r} would be written as {flattened!r}, which "
                    "is reserved for result metadata. Rename the source or "
                    "persist `corrected_files` with your own writer."
                )
            if portable_name in seen:
                raise ConfigurationError(
                    f"{source_name!r} and {seen[portable_name]!r} have colliding "
                    "output filenames, so one could overwrite the other. "
                    "`write` flattens directory parts on purpose — a "
                    "source name must not steer the write outside the target "
                    "directory — so distinct sources need distinct file "
                    "names. Write them to separate directories, or persist "
                    "`corrected_files` yourself: the engine has no writer and "
                    "this method is a convenience."
                )
            seen[portable_name] = source_name

    def _refuse_partial_write(self, allow_partial: bool) -> None:
        """A volume missing a file must not reach disk by omission.

        A divergent artefact does not throw the whole run away — the other
        files are faithful, and refusing to hand them over never made them
        better. The risk that trade creates is precise: a caller who writes
        ``corrected_files`` in a loop persists 299 of 300 pages, reports
        success, and nobody looks.

        So the loudness lands here, at the one door that puts bytes on
        disk. ``allow_partial=True`` is the caller saying it has read
        :attr:`undeliverable_files` and accepts the subset — a decision,
        made once, in code someone reviews. A host with its own writer
        (a staging transaction) never reaches this and answers the same
        question in its own terms.

        The same shape as :meth:`_refuse_colliding_names`: ``write``
        defending its own contract rather than inheriting one.
        """
        if not self.undeliverable_files or allow_partial:
            return
        listed = "; ".join(
            f"{name}: {why}" for name, why in sorted(self.undeliverable_files.items())
        )
        raise ConfigurationError(
            f"{len(self.undeliverable_files)} of "
            f"{len(self.corrected_files) + len(self.undeliverable_files)} source "
            "files could not be delivered, so writing now would leave an "
            f"INCOMPLETE set on disk — {listed}. Read "
            "`result.undeliverable_files`, then either fix the cause or call "
            "`write(..., allow_partial=True)` to persist the faithful files "
            "on purpose."
        )

    def write(
        self, directory: str | Path, *, allow_partial: bool = False
    ) -> list[Path]:
        """Persist the run's artefacts into ``directory`` (created if
        needed): each corrected XML under its source file's name, plus
        the §9 report as ``report.json``. Returns the written paths.

        Refuses outright when the run has :attr:`undeliverable_files`,
        unless ``allow_partial=True`` — see :meth:`_refuse_partial_write`.
        The report is written either way once the call is allowed, so what
        is missing is on disk beside what is not.

        Source basenames ``report.json`` and ``sidecar.json`` are reserved
        (case-insensitively). Empty names and directory names are refused;
        names must remain distinct after Unicode decomposition and case
        folding, conservatively on every filesystem. Existing symbolic
        links at output filenames are refused before any write. Regular
        files are replaced, one at a time; this is not a transaction for
        the whole result. The caller
        must control the destination directory throughout the call. New
        files use private permissions (0600); replacing a regular file
        preserves its permission bits.

        An obsolete sidecar.json is removed when the current sidecar is
        empty. A partial write refuses an existing path named for a withheld
        source, since its old XML could be mistaken for a current result.
        Other files are never removed; use a new directory for each run.

        ADR-011 — a caller-side convenience, not engine behaviour: the
        engine only computes values. Hosts that own a file transaction
        (commit/discard staging) keep their injected writer instead.
        """
        target = Path(directory)
        self._refuse_partial_write(allow_partial)
        self._refuse_colliding_names()
        # Strip directory parts: a source name must not steer a write out
        # of the destination. Serialize metadata before writing anything.
        outputs = {
            target / Path(name).name: content
            for name, content in self.corrected_files.items()
        }
        outputs[target / "report.json"] = self.report.model_dump_json(indent=2).encode(
            "utf-8"
        )
        # refused-but-preserved corrections as their own small
        # artefact for review tooling (they are ALSO inside report.json;
        # this is the convenience view, written only when non-empty).
        if self.report.sidecar:
            outputs[target / "sidecar.json"] = json.dumps(
                [entry.model_dump(mode="json") for entry in self.report.sidecar],
                indent=2,
                ensure_ascii=False,
            ).encode("utf-8")
        sidecar_path = target / "sidecar.json"
        output_names = {_portable_filename(path.name) for path in outputs}
        existing_names = (
            {_portable_filename(path.name) for path in target.iterdir()}
            if self.undeliverable_files and target.is_dir()
            else set()
        )
        for source_name in self.undeliverable_files:
            withheld_path = target / Path(source_name).name
            if _portable_filename(withheld_path.name) in output_names | existing_names:
                raise ConfigurationError(
                    f"Refusing to leave {str(withheld_path)!r} beside the report: "
                    "this source is undeliverable in the current run. "
                    "Use a new destination directory for a partial result."
                )
        for path in outputs.keys() | {sidecar_path}:
            if path.is_symlink():
                raise ConfigurationError(
                    f"Refusing to write {str(path)!r}: the output is a symbolic link. "
                    "Use a destination containing only regular output files."
                )
        if sidecar_path.exists() and not sidecar_path.is_file():
            raise ConfigurationError(
                f"Refusing to replace or remove {str(sidecar_path)!r}: "
                "sidecar.json is not a regular file."
            )
        target.mkdir(parents=True, exist_ok=True)
        for path, content in outputs.items():
            _replace_output(path, content)
        if not self.report.sidecar:
            sidecar_path.unlink(missing_ok=True)
        return list(outputs)


def _build_correction_result(
    *,
    ctx: RunContext,
    decisions: DecisionSet,
    traces: dict[LineRef, LineTrace],
    report: CorrectionReport,
    corrected_files: dict[str, bytes],
    source_digests: dict[str, str],
    total_chunks: int,
    total_reconciled: int,
) -> CorrectionResult:
    """Copy what the run accumulated into the value it returns.

    The counters come off the :class:`RunContext` (which does not survive
    the run), but the LINE-level fallback accounting is read from the
    :class:`DecisionSet` (ADR-011): it covers every path that leaves a
    line at its OCR text — chunk fallback, guard rejection, duplicate
    revert — not just the chunks whose attempts were exhausted.
    """
    return CorrectionResult(
        total_chunks=total_chunks,
        total_reconciled=total_reconciled,
        retry_count=ctx.retry_count,
        fallback_chunks=ctx.fallback_chunks,
        fallback_lines=decisions.fallback_lines,
        fallback_reasons=decisions.fallback_reason_counts(),
        review_lines=decisions.review_lines,
        review_reasons=decisions.review_reason_counts(),
        traces=traces,
        reconcile_metrics=ctx.reconcile_metrics,
        usage=ctx.usage,
        report=report,
        edit_script=_build_final_edit_script(
            decisions, ctx, source_digests=source_digests
        ),
        decisions=decisions,
        corrected_files=corrected_files,
        undeliverable_files=report.undeliverable_files,
        # routing economics: lines skipped (no producer call) and the
        # run's total producer-call count.
        lines_skipped=ctx.lines_skipped,
        # lines routed to the escalation (vision) producer.
        escalated_lines=ctx.escalated_lines,
        producer_calls=ctx.producer_calls,
    )
