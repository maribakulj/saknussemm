"""What a run says about itself: per-line traces, and the report (§9).

The staged :class:`LineOutcome` per line, the provenance record (§11) and
the :class:`CorrectionReport` that carries both.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from saknussemm.core.fidelity import ProjectionFidelity
from saknussemm.core.schemas.chunking import HyphenSplit
from saknussemm.core.schemas.producer import Usage


# ---------------------------------------------------------------------------
# Line trace — per-line observability through the correction pipeline
# ---------------------------------------------------------------------------


class RefusedEdit(BaseModel):
    """One producer op the edit guards refused, and why.

    Without it the report cannot distinguish "the producer proposed
    nothing" from "it proposed something the guards refused": a line whose
    only op is refused reports ``corrected`` with no reason, and the refusal
    rate of the edit guards is not merely unmeasured but **unmeasurable**.

    A reason rather than a counter, because a rate needs one to be
    actionable: ``e5_hyphen`` and ``e4_line_budget`` firing on the same
    corpus mean opposite things about what to change.

    Line ids are bare and ``page_id`` qualifies them, as for
    :class:`HyphenSplit` (ADR-009).
    """

    model_config = ConfigDict(frozen=True)

    page_id: str
    line_id: str
    op: str
    reason: str
    detail: str = ""


class LineTrace(BaseModel):
    """Working text trace for a single line through the correction run.

    This is the PYTHON-side accumulator the pipeline fills as the run
    progresses (exposed on ``CorrectionResult.traces``). The report's
    JSON artefact does not serialize it: the report builder projects
    each line's trace + terminal decision into a staged
    :class:`LineOutcome` (report v2). The two surfaces version
    independently (see ``docs/versioning.md``).
    """

    #: ``model_`` is pydantic's protected prefix, and two fields here use
    #: it because they mean "the model" in the OCR sense, not pydantic's.
    #: pydantic 2.0 made that a hard ``NameError`` at import time — so
    #: ``pydantic>=2.0``, which `docs/versioning.md` promises, described a
    #: version at which ``import saknussemm`` did not work. 2.0.1 downgraded
    #: it to a warning and recent versions are silent, which is why nothing
    #: surfaced it locally. Declaring the prefix unprotected fixes the cause
    #: rather than narrowing the promise, and the min-deps CI job is what
    #: verifies the promise instead of asserting it.
    model_config = ConfigDict(protected_namespaces=())

    line_id: str
    page_id: str
    source_ocr_text: str
    model_input_text: str | None = None  # ocr_text sent to LLM
    model_corrected_text: str | None = None  # raw LLM output before any post-processing
    projected_text: str | None = (
        None  # text retained after validation/reconciliation/fallback
    )
    output_alto_text: str | None = None  # text re-extracted from the output XML
    #: The acceptance guard's once-computed metrics (see
    #: :class:`ProposalFeatures`); surfaces on the report's decision stage.
    proposal_features: ProposalFeatures | None = None

    # Diagnostic metadata
    hyphen_role: str | None = None
    rewriter_path: str | None = None  # untouched / subs_only / fast_path / slow_path
    #: This line's share of the rewrite's granularity losses
    #: (e.g. ``{"words_dropped": 4}``), ``None`` when its rewrite lost
    #: nothing; surfaces on the report's projection stage.
    projection_losses: dict[str, int] | None = None
    #: The fidelity level the projection invariant measured for this line;
    #: surfaces on the report's projection stage. ``None`` until the line's
    #: file has been rewritten (and forever, for a run that writes nothing).
    projection_fidelity: ProjectionFidelity | None = None
    #: The rewriter's token alignment suspected a word reorder on this
    #: line. Flagged, never acted on.
    word_order_suspected: bool | None = None
    validation_status: str | None = (
        None  # corrected / review_required / fallback / failed
    )
    fallback_reason: str | None = None
    #: Why this line was referred for review — the codes of
    #: :data:`~saknussemm.core.decide.REVIEW_REASON_CODES`, each
    #: optionally followed by ``": detail"``. Empty on every line the
    #: run could decide, which is most of them. Unlike
    #: ``fallback_reason`` this ACCUMULATES: a line may be unverifiable
    #: for several independent causes at once, and a reviewer needs all
    #: of them rather than the first.
    review_reasons: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Report v2 (§9) — one staged LineOutcome per line:
# source → proposal → decision → projection
# ---------------------------------------------------------------------------


class ProposalStage(BaseModel):
    """What the producer was asked and what it answered — absent when the
    line never reached a producer (e.g. a rules producer's uncovered
    line)."""

    input_text: str | None = None  # enriched text sent to the producer
    output_text: str | None = None  # raw producer output, pre-guards


class DecisionReason(BaseModel):
    """Structured decision motif: a machine-stable ``code`` (the family a
    consumer aggregates on — same normalization as
    ``CorrectionResult.fallback_reasons``) plus the free-text remainder."""

    code: str
    detail: str | None = None


class ProposalFeatures(BaseModel):
    """Metrics the acceptance guard computed ONCE while deciding —
    recorded so no consumer re-derives them. Each field is ``None`` when
    the guard's path never computed it (e.g. neighbour similarities on a
    line whose source-similarity check already rejected it, or a line
    that never went through per-line acceptance at all)."""

    #: SequenceMatcher ratio proposal ↔ source (1.0 for an identity
    #: proposal).
    source_similarity: float | None = None
    #: SequenceMatcher ratio proposal ↔ previous line's source.
    prev_similarity: float | None = None
    #: SequenceMatcher ratio proposal ↔ next line's source.
    next_similarity: float | None = None
    #: len(proposal) / len(source) (source clamped to ≥ 1 char).
    length_ratio: float | None = None


class DecisionStage(BaseModel):
    """The line's terminal decision (always present — every line ends
    ``corrected``, ``review_required`` or ``fallback``, enforced by the
    DecisionSet).

    ``review_required`` is ``corrected`` plus an admission: the text
    below is the correction, and the run has no means of establishing it
    is right. A consumer filtering on ``status == "corrected"`` will not
    see those lines, which is what the value is for."""

    status: str  # corrected / review_required / fallback
    final_text: str  # the text the artefact carries
    reason: DecisionReason | None = None  # why a fallen line fell
    #: Why the run could not establish this correction is right —
    #: empty unless ``status`` is ``review_required``. A referred line
    #: DID keep its correction: ``final_text`` carries it, and the
    #: artefact carries ``final_text``. Additive and optional, so this
    #: does NOT bump ``report_version``.
    review_reasons: list[DecisionReason] = Field(default_factory=list)
    #: The guard's once-computed metrics for the proposal this decision
    #: judged; ``None`` for lines that never reached per-line acceptance
    #: (chunk-level fallbacks, hyphen-unit extensions, …).
    features: ProposalFeatures | None = None


class ProjectionStage(BaseModel):
    """How the decided text landed in the rewritten artefact — absent
    when no output file was rendered (e.g. ``source_files={}``)."""

    #: Text re-extracted from the very tree the output bytes were
    #: serialized from. Renamed from the v1 ``output_alto_text`` — this
    #: library writes PAGE too, the name was wrong.
    extracted_text: str | None = None
    rewriter_path: str | None = None  # untouched / subs_only / fast_path / slow_path
    #: ADR-012 — THIS line's granularity losses (e.g.
    #: ``{"words_dropped": 4}``): the per-decision attribution of the
    #: run-level ``CorrectionReport.format_losses`` aggregate. Absent
    #: when this line's rewrite lost nothing. Additive and optional —
    #: no ``report_version`` bump.
    losses: dict[str, int] | None = None
    #: How faithfully the artefact carries this line's decision — see
    #: :class:`~saknussemm.core.fidelity.ProjectionFidelity`. ``exact`` when
    #: the bytes say the decision character for character;
    #: ``token_equivalent`` when only what the format cannot represent was
    #: lost (a collapsed whitespace run, an edge space); ``normalized``
    #: when a whitespace character was SUBSTITUTED — a no-break space or
    #: U+202F flattened to an ordinary one. The run fails outright if the
    #: words diverge, so no worse level can reach a report. Additive and
    #: optional — no ``report_version`` bump.
    fidelity: ProjectionFidelity | None = None
    #: The token alignment suspected the correction REORDERED this
    #: line's words. Flagged, never acted on: lines never merge and words
    #: never move, so the text is written exactly as decided and the source
    #: identities stay where the alignment could vouch for them. Not a loss
    #: therefore not counted as one: inside :attr:`losses` it would make a
    #: consumer summing the loss counters add a non-loss to the total.
    #: ``None`` when the alignment saw no reorder (and on every path that
    #: does not align: untouched, subs-only, fast). Additive and optional —
    #: no ``report_version`` bump.
    word_order_suspected: bool | None = None


class LineConfidence(BaseModel):
    """Multi-component confidence of one line's DECISION.

    Every component keeps its own name — a single magic number whose
    recipe is lost is exactly what this type exists to prevent:

    - ``ocr``: the source engine's confidence in the ORIGINAL reading
      (mean ALTO ``WC`` / PAGE ``conf``), preserved for the audit even
      when a correction invalidates the per-word attributes;
    - ``producer``: the producer's self-assessment (LLM uncertainty
      channel; ``None`` until it lands or for producers that have none);
    - ``alignment``: the token-alignment score of final vs source text
      (1.0 for an unchanged line);
    - ``scorers``: each injected :class:`ConfidenceScorer`'s value by
      name (e.g. ``heuristic``);
    - ``decision``: the aggregate, computed by the IDENTIFIED
      ``formula`` (currently ``min`` over present components —
      conservative: a decision is only as safe as its weakest evidence).

    These values ORDER lines from safest to riskiest; they are not
    calibrated probabilities until the calibration harness says so.
    """

    ocr: float | None = None
    producer: float | None = None
    alignment: float | None = None
    scorers: dict[str, float] = Field(default_factory=dict)
    decision: float
    formula: str = "min"


class LineOutcome(BaseModel):
    """One line's whole journey through a run (report v2, §9)."""

    line_id: str
    page_id: str
    hyphen_role: str | None = None
    source_text: str
    proposal: ProposalStage | None = None
    decision: DecisionStage
    projection: ProjectionStage | None = None
    #: multi-component decision confidence, computed when the
    #: run's :class:`ConfidencePolicy` is not ``drop``. Additive and
    #: optional — no ``report_version`` bump.
    confidence: LineConfidence | None = None


#: Bumped on any breaking change to the CorrectionReport JSON shape (§9).
#: 2.0: flat ``LineTrace`` entries became staged ``LineOutcome``
#: objects (``source_text`` / ``proposal`` / ``decision`` /
#: ``projection``); ``output_alto_text`` renamed to
#: ``projection.extracted_text``; ``fallback_reason`` became the
#: structured ``decision.reason`` (code + detail).
CORRECTION_REPORT_VERSION = "2.0"


class ProducerProvenance(BaseModel):
    """The producer's identity as recorded on the report (§11).

    Mirrors :class:`saknussemm.core.protocols.ProducerMetadata` field for
    field (the dataclass cannot be the report type directly — protocols
    imports schemas, and the report is a schemas artefact). GENERIC
    vocabulary: a rules producer has no "model", so ``implementation``
    is simply ``None`` — never an artificial vendor pair.
    """

    name: str = "unknown"
    version: str | None = None
    implementation: str | None = None
    configuration_fingerprint: str | None = None


class RunProvenance(BaseModel):
    """Everything needed to say WHAT produced this report (§11).

    Extends the §11 story beyond the policy fingerprint: the exact
    library, the exact producer identity, the exact SOURCE bytes
    (per-file sha256), the format, and the critical dependencies.
    A consumer holding the same inputs and versions can re-run and
    compare; a consumer holding only the report can say precisely what
    it is looking at. Present on every run, including dry runs
    (``source_digests`` is then empty).

    Generation parameters are not duplicated here: the temperature ramp
    and retry strategy live in :class:`RetryPolicy`, already covered by
    ``config_fingerprint``.
    """

    #: saknussemm's own version.
    lib_version: str
    #: The §8.2 composite policy fingerprint (chunk_planner / guard /
    #: loss / pairing / retry) — same value stamped into the XML.
    config_fingerprint: str
    #: Who produced the edits (generic identity).
    producer: ProducerProvenance
    #: the ESCALATE tier's producer identity, when a run was
    #: configured with an ``escalation_producer`` (a VLM). ``None`` when the
    #: run had a single producer, so a text-only run's provenance is
    #: unchanged. Additive.
    escalation_producer: ProducerProvenance | None = None
    #: source file name → ``sha256:<hex>`` of the INPUT bytes, so the
    #: report is verifiably tied to the exact document it corrected.
    #: Empty on dry runs (no source files given).
    source_digests: dict[str, str] = Field(default_factory=dict)
    #: page_id → ``sha256:<hex>`` of the page IMAGE
    #: bytes, for every page whose ``run(page_images=…)`` value is a
    #: structured :class:`ImageAsset` carrying its digest. The mirror of
    #: ``source_digests`` for pixels: it ties the report to the exact scans
    #: a vision producer saw, and — together with the source digest, the
    #: per-line coords, and the producer's ``configuration_fingerprint``
    #: (which folds in the crop margin / polygon-mask knobs) — makes every
    #: crop REPRODUCIBLE without storing N crop hashes. The core never opens
    #: an image to fill this: it copies the digest the asset already
    #: carries (I4). Empty when no images were given, when they were bare
    #: ``ImageRef`` strings (opaque — no known digest), or when the assets
    #: carried none. Additive; no ``report_version`` bump.
    image_digests: dict[str, str] = Field(default_factory=dict)
    #: The manifest's stamped source format ("alto" / "page"), None for
    #: hand-built manifests that never went through a parser.
    source_format: str | None = None
    #: Critical dependency versions ({"lxml": …, "pydantic": …}),
    #: resolved from package metadata without importing the packages —
    #: the pure core stays lxml-free. A package that is not installed
    #: is simply absent.
    dependencies: dict[str, str] = Field(default_factory=dict)
    #: The policies that shaped this run and are NOT in
    #: ``config_fingerprint``: ``routing`` (its two bounds — a ``SKIP``
    #: makes the OCR text the final text, so two runs with different
    #: bounds deliver different bytes under the same fingerprint),
    #: ``review`` (which rules were on — changes statuses, never bytes),
    #: ``confidence`` (its mode) and ``qe_scorer`` (its declared name).
    #: Each value is the policy's own JSON dump, so a consumer recomputes
    #: its ``policy_fingerprint()`` from the report alone. A policy in its
    #: neutral state is absent: routing with no bound set, review silent,
    #: confidence ``drop``, no scorer — a run that used none of them has
    #: an empty mapping. Kept BESIDE the fingerprint rather than folded
    #: into it: folding would move every fingerprint already stamped into
    #: delivered files, and a conditional fingerprint could no longer be
    #: recomputed from the policy objects alone. Additive; no
    #: ``report_version`` bump.
    active_policies: dict[str, dict[str, Any]] = Field(default_factory=dict)


class SidecarEntry(BaseModel):
    """A correction the run REFUSED to project into the XML — preserved
    here instead of lost (token_realign gate, the vision/QE programme).

    The line's XML keeps its source markup (decision status
    ``fallback``); the corrected text plus the refusal evidence live
    here so a reviewer can apply, adapt or discard it.
    ``alignment_score`` is ``None`` for a line reverted only by hyphen-
    unit atomicity (its own alignment was never the problem).
    """

    page_id: str
    line_id: str
    source_text: str
    corrected_text: str
    reason: str
    alignment_score: float | None = None
    move_suspected: bool = False


class CorrectionReport(BaseModel):
    """Public, versioned correction report (§9).

    Each line is a staged :class:`LineOutcome` (v2) recording its
    full journey — source → proposal (producer in/out) → decision
    (terminal status, final text, structured reason) → projection
    (re-extracted text, rewriter path) — so a consumer can render a
    diff/preview or measure a run without re-deriving anything.
    Returned on every run; the engine never persists it (ADR-011) — it
    is ``result.report``, written as ``report.json`` by
    :meth:`CorrectionResult.write` or by the host's own transaction.
    """

    report_version: str = CORRECTION_REPORT_VERSION
    run_id: str
    total_lines: int = 0
    lines: list[LineOutcome] = Field(default_factory=list)
    #: Format-specific granularity losses aggregated over the run — e.g. the
    #: PAGE rewriter reports ``words_dropped`` / ``custom_offset_stripped`` /
    #: ``alt_textequiv_dropped`` (6.2 P4/P6) here. Additive and optional, so
    #: this does NOT bump ``report_version`` — the field's contract is to
    #: bump only on a *breaking* JSON change, and a new optional key is
    #: backward-compatible.
    #:
    #: **``None`` does NOT mean the run lost nothing.** This field
    #: counts losses of MARKUP granularity: an element or attribute that
    #: left the tree. A character the format could not carry — a no-break
    #: space or a tab flattened into an ordinary one — is a loss of TEXT,
    #: and it is counted by :attr:`projection_fidelity` as a ``normalized``
    #: line, with the level attributed per line on
    #: :attr:`ProjectionStage.fidelity`. A run can therefore have
    #: ``format_losses is None`` and still have flattened a character; both
    #: fields have to be read to audit a run.
    #:
    #: Deliberately NOT mirrored here as a second counter. It would agree
    #: with ``projection_fidelity["normalized"]`` on every run by
    #: construction, and a counter derivable from another counter is what
    #: this accounting already suffered once: two sites for one event,
    #: free to drift apart.
    format_losses: dict[str, int] | None = None
    #: Source files the run could NOT deliver, mapped to why — the artefact
    #: did not carry the decisions, so the file is absent from
    #: ``CorrectionResult.corrected_files`` rather than present in a
    #: doubtful version. Empty on a run that delivered everything.
    #:
    #: Additive and optional, so this does NOT bump ``report_version``.
    #:
    #: This is the persisted half of the guarantee. The live half is
    #: :attr:`CorrectionResult.undeliverable_files`, and the loud half is
    #: :meth:`CorrectionResult.write`, which refuses a partial set unless
    #: the caller passes ``allow_partial``.
    undeliverable_files: dict[str, str] = Field(default_factory=dict)
    #: Per-line projection fidelity, counted by level over the run — e.g.
    #: ``{"exact": 498, "token_equivalent": 22, "normalized": 2}``. Two
    #: normalized lines mean two lines where a significant whitespace
    #: character (U+00A0, U+202F, a tab) was flattened into an ordinary
    #: space: the artefact still says the same WORDS, and no longer says
    #: them the same way — which an invariant comparing in whitespace normal
    #: form cannot see at all. ``None`` when
    #: the run rendered no output file. Additive and optional — no
    #: ``report_version`` bump.
    projection_fidelity: dict[str, int] | None = None
    #: Lines that announce a hyphen break with no partner this run can see —
    #: the pairing policy refused the candidate, the partner sits on a page
    #: this run does not have, the pointer dangles. Each was silent: the line
    #: still ends mid-word, is corrected alone, and never reaches the
    #: reconciler, so its pair-drift guards never run either. A host reading
    #: "0 fallback" could not learn that N words were split across a seam
    #: nobody sewed. ``None`` when every break found its partner. Additive
    #: and optional — no ``report_version`` bump.
    unpaired_breaks: int | None = None
    #: The forward hyphen links this run SEVERED to keep a chain inside
    #: one request (ADR-010 unit SPLIT). Recorded on the ``ChunkPlan`` since
    #: the split existed and read by nobody, which made the engine's one
    #: deliberately destructive operation the only one a host could not see.
    #: It is not covered by anything else on this report: the cut resets the
    #: tail's role to ``NONE``, so it is not an ``unpaired_break``; both
    #: sides keep their OCR text verbatim, so it is not a fallback; nothing
    #: leaves the markup, so it is not a ``format_loss``. What a host
    #: actually gets is a delivered line whose text still ends mid-word and
    #: which declares no break at all. ``None`` when no chain was cut — the
    #: common case, since only chains over ``max_lines_per_request`` are.
    #: Additive and optional — no ``report_version`` bump.
    hyphen_splits: list[HyphenSplit] | None = None

    #: Every producer op the edit guards refused, or ``None`` when none
    #: were. Additive, so ``report_version`` does not move.
    #:
    #: This is the field that makes a ``GuardConfig`` tunable. Before it, a
    #: line whose only op was refused reported ``corrected`` with no reason
    #: and nothing counted the refusal, so a consumer could loosen
    #: ``min_source_similarity`` on a degraded corpus and measure no
    #: difference whatever the setting did. The reason code is what makes it
    #: actionable: ``e5_hyphen`` and ``e4_line_budget`` firing on the same
    #: pages call for opposite changes.
    #:
    #: Sorted by ``(page_id, line_id, op, reason)`` rather than accumulated
    #: in execution order, so two runs over the same document produce the
    #: same report — which is not yet true of ``hyphen_splits`` above.
    edit_rejections: list[RefusedEdit] | None = None
    #: §11 — the run's full provenance record. Optional and
    #: additive (no ``report_version`` bump): a v2.0 consumer that
    #: ignores unknown keys keeps working, one that reads it gains the
    #: source digests, producer identity and dependency versions.
    provenance: RunProvenance | None = None
    #: §11 — provider usage aggregated over the run (tokens +
    #: response ids). Historically it lived only on the TRANSIENT
    #: ``CorrectionResult`` while the report was the persisted artefact,
    #: so cost never reached trace.json. ``None`` when no producer call
    #: reported usage (rules producer, dry runs). Additive and optional —
    #: no ``report_version`` bump (same contract as ``format_losses``).
    usage: Usage | None = None
    #: corrections the token_realign gate refused to project,
    #: preserved for review (see :class:`SidecarEntry`). ``None`` when
    #: the gate is off or nothing was refused. Additive and optional —
    #: no ``report_version`` bump.
    sidecar: list[SidecarEntry] | None = None

    @property
    def fallback_lines(self) -> list[LineOutcome]:
        """Lines that fell back to OCR (a quick health signal for consumers)."""
        return [ln for ln in self.lines if ln.decision.status == "fallback"]
