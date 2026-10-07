"""The document as the pipeline sees it: pages, blocks, lines, geometry.

The parse-side half of the schema package. Everything here is filled by a
format parser and read by the engine; nothing here knows how a correction
is produced or reported.
"""

from __future__ import annotations

import uuid
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, computed_field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class LineStatus(str, Enum):
    """Per-line outcome after the pipeline has visited a TextLine.

    ``REVIEW_REQUIRED`` is the odd one out and deliberately so. The
    other three answer *what happened to the text*; it answers *what
    the library is able to say about it*. A referred line carries its
    CORRECTION — the same bytes ``CORRECTED`` would have delivered,
    byte for byte — and declares that the library could not establish
    the change is right.

    The distinction is not decorative. The stage-C guards compare
    characters and have no notion of meaning: on twelve counter-examples
    put through the real ``guards.check_line``, all twelve were accepted
    at both thresholds — a removed negation at 0.8955, a changed date at
    0.9388, a truncated amount at 0.9643, a neighbouring line copied
    verbatim at 0.8852. No threshold closes that family, because the
    problem is not the threshold. Folding those lines into ``CORRECTED``
    would have the library assert "I checked this" about precisely the
    changes it cannot check.

    A consumer that treats ``CORRECTED`` as "done" therefore no longer
    sweeps referrals up with it, which is the point of the value
    existing rather than a cost of it.
    """

    PENDING = "pending"
    CORRECTED = "corrected"
    #: Corrected, and the library declares it cannot establish the
    #: change is right. The artefact carries the correction.
    REVIEW_REQUIRED = "review_required"
    FALLBACK = "fallback"
    FAILED = "failed"


class ChunkGranularity(str, Enum):
    """Granularity tier used by the chunk planner — PAGE → BLOCK → WINDOW → LINE on downgrade."""

    PAGE = "page"
    BLOCK = "block"
    WINDOW = "window"
    LINE = "line"


class HyphenRole(str, Enum):
    """Position of a line within a hyphenated pair.

    ``NONE`` for ordinary lines. ``PART1`` is the FIRST (top) line of
    a pair — it carries the left word fragment and ends with the
    trailing hyphen. ``PART2`` is the SECOND (bottom) line of the
    pair — it carries the right word fragment. ``BOTH`` is the
    PART2-of-the-previous-pair AND PART1-of-the-next-pair (chained
    hyphenation across three consecutive lines).

    Verified against examples/sample.xml: TL4 (the line carrying the
    HYP element) is PART1; TL5 (the next line) is PART2. The previous
    docstring inverted these — a real trap for any reader trying to
    reason about the data model.
    """

    NONE = "none"
    PART1 = (
        "HypPart1"  # first (top) line of pair: carries left fragment + trailing hyphen
    )
    PART2 = "HypPart2"  # second (bottom) line of pair: carries right fragment
    BOTH = "HypBoth"  # PART2 of previous pair AND PART1 of next pair (chained)


class PipelineEventType(str, Enum):
    """Canonical event names emitted by the correction ENGINE.

    Only events the pipeline itself (or a host reporting the pipeline's
    metrics) can emit live here. Server-side job lifecycle
    (started/completed/failed/cancelled/queued) and transport events
    (keepalive/error) are a HOST's vocabulary and belong to the host, in
    its own enum: this library opens no socket and knows nothing about
    delivery.

    The wire strings are part of a host's contract with its clients, so
    they stay stable across releases and change only through the same
    door as any other public rename.

    No test is named here: the one that would be lives in a repository
    this one does not own, and such a reference rots without anyone
    noticing.
    """

    # Document / page / chunk lifecycle (emitted by CorrectionPipeline)
    DOCUMENT_PARSED = "document_parsed"
    PAGE_STARTED = "page_started"
    PAGE_COMPLETED = "page_completed"
    CHUNK_PLANNED = "chunk_planned"
    CHUNK_STARTED = "chunk_started"
    CHUNK_COMPLETED = "chunk_completed"
    CHUNK_ERROR = "chunk_error"
    # Emitted when a chunk's retry budget is exhausted and its lines are
    # re-planned at the next-finer granularity (PAGE→BLOCK→WINDOW→LINE).
    CHUNK_DOWNGRADED = "chunk_downgraded"
    RETRY = "retry"
    WARNING = "warning"
    HYPHEN_PARTNER_MISSING = "hyphen_partner_missing"

    # Observability stats — emitted at file/job boundaries with rewriter
    # and reconcile path counts. Pure read-only diagnostics; never
    # influence the corrected XML output.
    REWRITER_STATS = "rewriter_stats"
    RECONCILE_STATS = "reconcile_stats"


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


class Coords(BaseModel):
    """A line/block geometry box — pixels in the source image's coordinate system.

    ALTO carries an axis-aligned bounding box natively (``HPOS``/``VPOS``/
    ``WIDTH``/``HEIGHT``). PAGE XML instead encodes a **polygon**
    (``Coords@points``); the parser stores that polygon verbatim in
    ``polygon`` and derives the enclosing bbox (the four int fields) for the
    planner, which only needs a box (P1). ``polygon`` is ``None`` for ALTO —
    it has no polygon to preserve — and the rewriter never touches geometry
    on the PAGE side, so the source polygon is a read-only provenance field.
    """

    # ADR-011, made structural — on this model, not yet on every manifest
    # type. The engine works on a deep copy and never writes here; freezing
    # says so in the type instead of leaving it to the discipline of one
    # call site.
    #
    # Not yet frozen, and each for its own measured reason: `LineManifest`
    # IS the run's working state (246 assignment sites — corrected_text,
    # status, the hyphen pointers), and `PageManifest`/`BlockManifest` are
    # written once by the page-id disambiguation in `core.pairing`, which
    # rewrites hyphen pointer fields in the same pass — freezing them waits
    # on the hyphen unit becoming the storage of record.
    model_config = ConfigDict(frozen=True)

    hpos: int
    vpos: int
    width: int
    height: int
    #: PAGE ``Coords@points`` verbatim (e.g. ``"617,1046 3450,1046 …"``);
    #: ``None`` for ALTO. Preserved for provenance/parity, never rewritten.
    polygon: str | None = None


# ---------------------------------------------------------------------------
# Core line / block / page / document models
# ---------------------------------------------------------------------------


class LineManifest(BaseModel):
    """A single ALTO ``TextLine`` enriched with correction + hyphenation state.

    Carries the OCR text, the corrected text once the pipeline has
    visited it, the line's place in the global reading order, and any
    hyphenation links to its partner line(s). Mutated in place during
    a pipeline run; callers read ``corrected_text`` and ``status``
    once the job completes.
    """

    line_id: str
    page_id: str
    block_id: str
    line_order_global: int
    line_order_in_block: int
    coords: Coords
    ocr_text: str
    #: Number of word-granularity elements the physical line carries in
    #: its source markup (PAGE ``Word`` children), or ``None`` when the
    #: line has no word markup to lose (word-less PAGE lines, ALTO —
    #: whose per-token ``String`` geometry redistributes at any token
    #: count). Feeds the :class:`LossPolicy` strict check (§6.2/ADR-012):
    #: a correction whose token count diverges from this cannot project
    #: without dropping the word geometry.
    word_count: int | None = None
    # Parse-time evidence for the PAGE loss gate. The canonical line reading
    # may disagree with its Word readings, so its split is not a substitute.
    # Internal only: not part of the manifest's serialised public schema.
    _source_word_texts: list[str] | None = PrivateAttr(default=None)
    #: the SOURCE engine's own confidence in this
    #: line, in [0, 1]: mean of the ALTO ``String/@WC`` values, or the
    #: PAGE line ``TextEquiv/@conf``. ``None`` when the source carries
    #: none. Preserved so the audit trail keeps the OCR confidence even
    #: where a correction invalidates the per-word attributes — it feeds
    #: the ``ocr`` component of :class:`LineConfidence`.
    ocr_confidence: float | None = None
    prev_line_id: str | None = None
    next_line_id: str | None = None
    corrected_text: str | None = None
    status: LineStatus = LineStatus.PENDING

    # Hyphenation fields
    # For PART1: pair_line_id = forward partner (the PART2 line)
    # For PART2: pair_line_id = backward partner (the PART1 line)
    # For BOTH:  pair_line_id = backward partner, forward_* = forward partner
    #
    # pair_page_id / forward_pair_page_id qualify the partner reference so
    # cross-page lookups stay correct when two ALTO files share TextLine IDs
    # (e.g. both call their first line "TL1"). When None, the partner is
    # presumed intra-page and the bare line_id lookup is authoritative.
    hyphen_role: HyphenRole = HyphenRole.NONE
    hyphen_pair_line_id: str | None = None
    hyphen_pair_page_id: str | None = None
    hyphen_subs_content: str | None = None
    hyphen_source_explicit: bool = False
    # Forward link fields — used only when role == BOTH (chained hyphenation)
    hyphen_forward_pair_id: str | None = None
    hyphen_forward_pair_page_id: str | None = None
    hyphen_forward_subs_content: str | None = None
    hyphen_forward_explicit: bool = False


class BlockManifest(BaseModel):
    """An ALTO ``TextBlock`` with its coordinates and the line IDs it contains."""

    block_id: str
    page_id: str
    block_order: int
    coords: Coords
    line_ids: list[str]


class PageManifest(BaseModel):
    """An ALTO ``Page``: source file, geometry, and the blocks and lines it owns."""

    page_id: str
    source_file: str
    page_index: int
    page_width: int
    page_height: int
    blocks: list[BlockManifest]
    lines: list[LineManifest]


class DocumentManifest(BaseModel):
    """A multi-page document: the top-level structure the pipeline consumes."""

    # ADR-011, made structural — on this model, not yet on every manifest
    # type. The engine works on a deep copy and never writes here; freezing
    # says so in the type instead of leaving it to the discipline of one
    # call site.
    #
    # Not yet frozen, and each for its own measured reason: `LineManifest`
    # IS the run's working state (246 assignment sites — corrected_text,
    # status, the hyphen pointers), and `PageManifest`/`BlockManifest` are
    # written once by the page-id disambiguation in `core.pairing`, which
    # rewrites hyphen pointer fields in the same pass — freezing them waits
    # on the hyphen unit becoming the storage of record.
    model_config = ConfigDict(frozen=True)

    document_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_files: list[str]
    pages: list[PageManifest]
    #: Format the sources were parsed as ("alto" | "page"), stamped by the
    #: format builders so the engine can derive the matching adapter at
    #: write time. ``None`` on hand-built manifests: writing output then
    #: requires an explicit ``format_adapter`` on the pipeline — there is
    #: no implicit default format.
    source_format: str | None = None
    #: Source files whose XML declaration did not match their bytes, as
    #: ``{source_file: declared_encoding}``. The library read them as what
    #: they ARE — always UTF-8, which is the only override the rule makes —
    #: and names it here rather than performing it in silence: read as
    #: declared, a UTF-8 file labelled ``ISO-8859-1`` yields ``clÃ©ricales``
    #: where the document says ``cléricales``, and a corrector handed that
    #: will repair it, delivering a text change no report could tell apart
    #: from a correction. The source file is never modified.
    #:
    #: A plain mapping rather than a named type on purpose: the public
    #: surface is at its computed closure, and a new type reachable from
    #: this model would extend it as a side effect. ``used`` would be the
    #: constant ``"utf-8"`` in every entry, so nothing is lost.
    #: Empty in the overwhelmingly common case.
    source_encodings: dict[str, str] = Field(default_factory=dict)

    #: ``{source_file: "sha256:<hex>"}`` of the bytes each page was parsed
    #: FROM, stamped from that same read. Preflight verifies a captured copy
    #: against these digests; the native adapters render the copy without
    #: reopening the paths after producer calls.
    #:
    #: Two measured consequences. A ``source_files`` mapping that names the
    #: wrong path for a name delivered one file's decided text inside
    #: another file's tree, geometry and page ids, destroying the other
    #: file's text, and the run SUCCEEDED — ``ADR-007`` makes ``line_id``
    #: unique only within a file, so two files of one document normally
    #: both carry ``TL1…TLn`` and every lookup matched. And a file replaced
    #: under a run projected one version's decisions into another version's
    #: markup, line by line, silently.
    #:
    #: Neither was visible to the projection invariant, which is the part
    #: worth keeping in mind: it compares the delivered artefact to the
    #: decisions, and the artefact was *made* by writing those decisions. It
    #: cannot see that the tree underneath was the wrong one. A digest can.
    #:
    #: Empty on a hand-built manifest, and that is deliberate rather than a
    #: gap: the check is a claim about a file this library read, so a caller
    #: who assembled a manifest by other means is not held to it.
    source_digests: dict[str, str] = Field(default_factory=dict)

    # ADR-011 — the counters are DERIVED from the pages. A stored copy
    # could contradict the content (the old validator existed to catch
    # exactly that lie); a computed one cannot. ``computed_field`` keeps
    # them in the serialized shape.

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_pages(self) -> int:
        return len(self.pages)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_blocks(self) -> int:
        return sum(len(p.blocks) for p in self.pages)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_lines(self) -> int:
        return sum(len(p.lines) for p in self.pages)
