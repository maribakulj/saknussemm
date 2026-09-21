"""Ports of the pure core (§3): every seam a consumer can plug into.

Structural-typing contracts decoupling the pipeline from its
infrastructure: the LLM client (``BaseProvider``), the event sink
(``PipelineObserver``) and — since the §3 reorganisation — the FORMAT
seam (``FormatAdapter``), through which the pipeline reads/writes
concrete transcription XML without importing any format module (core
stays lxml-free by construction; the import-contract test enforces it).
There is no persistence port: the engine never writes (ADR-011) — the
corrected artefacts travel on ``CorrectionResult`` and the caller
persists them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Callable, Iterable
from typing import Any, ClassVar, Protocol, runtime_checkable

from saknussemm.core.editing import EditScript
from saknussemm.core.schemas import (
    ImageAsset,
    PageImage,
    CorrectionRequest,
    ModelInfo,
    PageManifest,
    Usage,
)
from saknussemm.errors import ConfigurationError, ProviderError


class ProviderTransientError(ProviderError):
    """Raised by a ``BaseProvider`` to signal a recoverable transport
    failure (network timeout, 5xx upstream, connection reset, …).

    The pipeline's retry classifier uses ``isinstance(exc,
    ProviderTransientError)`` to route the error to the
    exponential-backoff branch. Providers should wrap the underlying
    library exception (``httpx.HTTPStatusError``,
    ``httpx.TimeoutException``, …) and re-raise as
    ``ProviderTransientError`` — that way saknussemm stays
    http-library-agnostic without resorting to fragile class-name
    string matching at the catch site.

    When the underlying failure was HTTP, the originating status code
    is preserved on ``status_code`` so observers can route on it (e.g.,
    distinguish 429 rate-limit from 503 upstream-blip without parsing
    the message). Transport-level failures (timeouts, network errors)
    leave ``status_code`` as ``None``. The full underlying exception is
    additionally reachable via ``__cause__`` when callers raise as
    ``raise wrapped from original``.
    """

    code: ClassVar[str] = "provider_transient"
    retryable: ClassVar[bool] = True


class ProviderPermanentError(ProviderError):
    """Raised by a ``BaseProvider`` for a failure that will NEVER heal by
    retrying: invalid credentials (401/403), unknown model (404), a
    schema the vendor definitively rejects — the client-side 4xx family
    other than 429.

    ADR-008 — semantics contract: the pipeline treats this as FATAL for the
    whole run. It is never retried, never downgraded, and NEVER converted
    into an OCR fallback: a run whose provider rejected every call must
    fail loudly, not report success with silently uncorrected text.
    Propagates out of :meth:`CorrectionPipeline.run` like
    :class:`~saknussemm.errors.CorrectionAborted` does — before any
    output is written.

    A :class:`~saknussemm.errors.SaknussemmError` (via ``ProviderError``)
    so the single-root catch contract holds, but deliberately NOT a
    ``ValueError`` (the retry classifier routes ``ValueError`` to the
    malformed-output retry branch). Fatality is enforced by the pipeline's
    explicit ``except ProviderPermanentError: raise`` handlers, which sit
    BEFORE every branch that absorbs recoverable ``SaknussemmError``s —
    the hierarchy states ownership, the handler ordering states severity.
    """

    code: ClassVar[str] = "provider_permanent"
    retryable: ClassVar[bool] = False


@runtime_checkable
class StructuredCompletionClient(Protocol):
    """The ONLY LLM capability the core consumes.

    Implementations call out to their provider's API (or run a local
    model) and return the JSON shape declared by ``OUTPUT_JSON_SCHEMA``.
    Implementations MUST wrap recoverable transport failures as
    ``ProviderTransientError`` (and permanent rejections as
    ``ProviderPermanentError``): recoverability is an allowlist, so a
    raw httpx/SDK exception is treated as a bug and FAILS the run
    instead of being retried.
    """

    async def complete_structured(
        self,
        api_key: str,
        model: str,
        system_prompt: str,
        user_payload: dict[str, Any],
        json_schema: dict[str, Any],
        temperature: float = 0.0,
    ) -> tuple[dict[str, Any], Usage | None]:
        """Return ``(parsed_json, usage)``.

        ``parsed_json`` matches ``OUTPUT_JSON_SCHEMA``; ``usage`` reports
        token consumption for the call, or ``None`` when the provider
        cannot report it.
        """
        ...


@runtime_checkable
class ModelCatalog(Protocol):
    """Model discovery — APPLICATION vocabulary.

    The engine never lists models: a run is handed one resolved model
    string. Catalog lookups belong to the host (a
    ``/providers/{p}/models`` endpoint, say); the protocol lives here only
    so the split is nameable on one seam.
    """

    async def list_models(self, api_key: str) -> list[ModelInfo]: ...


@runtime_checkable
class BaseProvider(StructuredCompletionClient, ModelCatalog, Protocol):
    """A full vendor client: completions + catalog.

    Convenience composition for hosts whose provider objects do both.
    The CORE only ever requires
    :class:`StructuredCompletionClient` — ``LLMEditProducer`` and
    ``CorrectionPipeline.for_provider`` accept a client with no
    ``list_models`` at all.
    """


@dataclass(frozen=True)
class ProducerOptions:
    """Per-call envelope the engine hands a producer (§5.1).

    Replaces the full ``RetryPolicy`` on the ``produce()`` seam: the
    ENGINE owns the retry/downgrade strategy — a producer only needs to
    know about THIS call. ``temperature`` is already resolved for the
    attempt (ramp and hyphen 0.0-pin decided engine-side);
    ``deadline_seconds`` is an optional wall-clock budget hint;
    ``should_abort`` is the run's cooperative cancellation probe — a
    producer doing long I/O SHOULD poll it (or wire it to its HTTP
    client) and abandon the call by raising
    :class:`~saknussemm.errors.CorrectionAborted` when it trips,
    instead of the engine only noticing between chunks.
    """

    attempt: int = 1
    temperature: float = 0.0
    deadline_seconds: float | None = None
    should_abort: Callable[[], bool] | None = None

    def cancelled(self) -> bool:
        """True when the run asked to abort — poll around long I/O."""
        return self.should_abort is not None and self.should_abort()


@dataclass(frozen=True)
class ProducerMetadata:
    """Provenance identity of an :class:`EditProducer` (§11).

    Replaces the bare ``provider_name``/``model`` strings with GENERIC
    producer vocabulary — a rules engine has no "model". ``name`` says
    WHO produced the edits (``"openai"``, ``"rules"``, …);
    ``implementation`` names the concrete engine behind the name when
    one exists (an LLM's model string, a rules-set label);
    ``configuration_fingerprint`` is the producer-side configuration
    digest (prompt/schema hash, rules-table hash) — the counterpart of
    the pipeline's policy :meth:`~CorrectionPipeline.config_fingerprint`.

    A producer MAY declare its own identity via a ``metadata`` attribute
    (the same optional-attribute convention as
    ``requires_full_coverage``); an explicit ``producer_metadata`` on the
    :class:`CorrectionPipeline` constructor wins over the declaration.
    """

    name: str = "unknown"
    version: str | None = None
    implementation: str | None = None
    configuration_fingerprint: str | None = None

    def provenance_labels(self) -> tuple[str, str]:
        """The ``(provider, model)`` label pair stamped into corrected
        XML — the format seam predates the generic vocabulary and keeps
        its historical two-string surface, so an implementation-less
        producer stamps ``"unknown"`` exactly as the bare strings did."""
        return self.name, self.implementation or "unknown"


@runtime_checkable
class EditProducer(Protocol):
    """Producer contract of the edit protocol (§5.1).

    From v2.0 the LLM ``BaseProvider`` is *an implementation* of this
    contract, not the contract itself; a deterministic rules engine (§5.3)
    and a vision/VLM producer (§5.2 bis) are others. A producer returns an
    :class:`~saknussemm.core.editing.EditScript` plus optional token
    :class:`~saknussemm.core.schemas.Usage`.

    ``wants_geometry`` / ``wants_image`` let the compiler include the
    physical anchor envelope (line geometry, opaque page image reference)
    ONLY for producers that consume it — a text producer keeps a lean
    payload. A producer with ``wants_image=True`` run without a matching
    ``page_images`` entry is a start-up error (:func:`require_page_images`),
    never a silent image-less call.

    Optional declared surfaces (read via ``getattr``, absent is fine —
    deliberately NOT protocol members so third-party producers and the
    ``isinstance`` check stay unaffected): ``requires_full_coverage``
    (bool, default ``True``), ``metadata``
    (:class:`ProducerMetadata` — the producer's provenance identity) and
    ``capabilities`` (:class:`~saknussemm.core.schemas.ModelCapabilities`
    — what the model can do, read by the Router; absent = unconstrained).
    """

    wants_geometry: bool
    wants_image: bool

    async def produce(
        self, payload: CorrectionRequest, *, options: ProducerOptions
    ) -> tuple[EditScript, Usage | None]: ...


def require_page_images(
    producer: EditProducer,
    pages: Iterable[PageManifest],
    page_images: dict[str, PageImage] | None,
) -> None:
    """Raise :class:`ConfigurationError` if a vision producer lacks images (§5.1).

    A producer that does not want images is always fine. A vision producer
    needs a ``page_images`` mapping (page_id → opaque ref or
    :class:`~saknussemm.core.schemas.ImageAsset`) covering EVERY page — one
    image per physical page, never one per source file: a multipage XML has
    as many scans as pages, and flattening them to a single per-file ref
    sent the producer the wrong image for every page but the first.
    Otherwise the run would issue an image-less VLM call, which the spec
    forbids.

    When a value is a structured :class:`ImageAsset`, its ``page_id`` MUST
    equal its mapping key: a scan filed under the wrong page is the same
    silent wrong-image bug the per-page contract exists to prevent, and an
    asset that names its own page lets us catch it at start-up instead of
    cropping the wrong scan.
    """
    if not getattr(producer, "wants_image", False):
        return
    if not page_images:
        raise ConfigurationError(
            "producer requires page images (wants_image=True) but run() "
            "received no page_images mapping"
        )
    mismatched = [
        f"asset.page_id={value.page_id!r} filed under key {key!r}"
        for key, value in page_images.items()
        if isinstance(value, ImageAsset) and value.page_id != key
    ]
    if mismatched:
        raise ConfigurationError(
            "page_images ImageAsset values must be filed under their own "
            f"page_id; disagreements: {mismatched}"
        )
    missing = [
        f"{page.page_id!r} ({page.source_file})"
        for page in pages
        if page.page_id not in page_images
    ]
    if missing:
        raise ConfigurationError(
            "producer requires page images but page_images (keyed by "
            f"page_id) is missing entries for: {missing}"
        )


def require_capabilities(producer: EditProducer) -> None:
    """Refuse a producer whose declared capabilities contradict its wiring
    (the vision/QE programme, §5.2 bis).

    A ``capabilities`` declaration is optional (``getattr``, absent = no
    constraint, back-compatible). When present it must be internally
    consistent with the producer's edit-protocol flags: a producer that
    asks for page images (``wants_image=True``) but declares
    :attr:`~saknussemm.core.schemas.ModelCapabilities.vision` ``= False``
    is misconfigured — it would crop and send pixels its own model says it
    cannot read. Caught at start-up, like ``require_page_images``, never as
    a confusing mid-run provider rejection.

    Per-line producer SELECTION by capability (routing a chunk to a
    vision-capable producer, honouring ``max_images``/``context``) is the
    Router's job and consumes :meth:`ModelCapabilities.can_serve`; this is
    only the consistency gate the engine owns for its single producer.
    """
    caps = getattr(producer, "capabilities", None)
    if caps is None:
        return
    if getattr(producer, "wants_image", False) and not caps.vision:
        raise ConfigurationError(
            "producer wants page images (wants_image=True) but its declared "
            "capabilities say vision=False — a vision producer must declare "
            "ModelCapabilities(vision=True)"
        )


@runtime_checkable
class PipelineObserver(Protocol):
    """Receives lifecycle events emitted by the correction pipeline.

    The pipeline calls ``on_event`` synchronously after each significant
    step (chunk started/completed, retry, fallback, warning, page lifecycle,
    document lifecycle). The observer is responsible for whatever side
    effect it wants — SSE fan-out, structured logging, metrics — without
    blocking the pipeline.

    A no-op observer is acceptable; the pipeline never inspects return values.
    """

    def on_event(self, event_type: str, payload: dict[str, Any]) -> None: ...


class RewriteMetrics(Protocol):
    """Structural view of a format rewriter's per-path line counts."""

    untouched: int
    subs_only: int
    fast_path: int
    slow_path: int


@dataclass(frozen=True)
class RenderOutcome:
    """Everything the render step produces about a document's artefacts.

    Three things travelled as a tuple and then as three parameters, which is
    how ``_build_correction_report`` reached twelve arguments. They belong
    together: each answers a different question about the SAME rewrite.

    ``undeliverable`` is the one that carries a contract. A file listed there
    is **absent** from ``corrected_files``, never present in a doubtful
    version — a lookup by name raises rather than handing back bytes nobody
    vouched for. The run does not fail for it: the other files are faithful,
    and refusing to hand them over never made them better. What keeps that
    from becoming a silent partial delivery is
    :meth:`saknussemm.core.result.CorrectionResult.write`, which refuses an
    incomplete set unless the caller says it accepts one.

    "Not rewritten" and "undeliverable" are deliberately different: a file
    the manifest never claimed is out of scope, whereas an undeliverable one
    was rewritten and refused. Collapsing them would make ``write`` refuse a
    clean run.
    """

    #: Format granularity losses aggregated across every file.
    losses: dict[str, int]
    #: Corrected bytes per source file name — the faithful ones only.
    corrected_files: dict[str, bytes]
    #: Source file name → why its artefact did not carry the decisions.
    undeliverable: dict[str, str]


@dataclass(frozen=True)
class RewriteResult:
    """Everything one file's rewrite produced, in one value (ADR-011).

    ``texts`` maps bare line_id → the line's final text (line_ids are
    unique per source file, ADR-007), extracted from the very tree the
    bytes were serialized from — the projection invariant (P1.4)
    verifies against them without re-parsing the output. ``losses`` are
    the format's granularity-loss counters for this file
    (:attr:`~saknussemm.core.schemas.CorrectionReport.format_losses`
    aggregates them over the run); empty when the rewrite dropped no
    markup. "Empty" is not "lossless" — a character the format cannot carry
    is a loss of TEXT and is graded on the projection fidelity scale
    instead (:mod:`saknussemm.core.fidelity`).
    """

    xml_bytes: bytes
    metrics: RewriteMetrics
    #: line_id → "untouched" / "subs_only" / "fast_path" / "slow_path"
    rewriter_paths: dict[str, str]
    texts: dict[str, str]
    #: The same lines read with the format's mark substitutions OFF:
    #: what the artefact's characters SAY, not the logical reading of them.
    #: Empty when a format has no such substitution to declare, and read
    #: only to grade projection fidelity — never as anyone's text. Without
    #: it a line whose file spells its break mark U+00AD while the decision
    #: spells it ``-`` graded ``exact``, because both sides of the
    #: comparison had gone through the same collapse.
    texts_verbatim: dict[str, str] = field(default_factory=dict)
    losses: dict[str, int] = field(default_factory=dict)
    #: Line ids whose token alignment SUSPECTED a word reorder. A
    #: diagnostic, never acted on (lines never merge, words never move), and
    #: deliberately not a loss: nothing left the markup. It used to ride in
    #: ``losses`` as ``word_order_suspected``, so any consumer summing the
    #: loss counters counted a non-loss — the same defect the loss table
    #: settles, with a different attribute.
    word_order_suspected: frozenset[str] = frozenset()
    #: ADR-012 — per-line attribution of ``losses``: line_id →
    #: that line's own loss counters (only lines that lost something
    #: appear). Summing the values reproduces ``losses``.
    losses_by_line: dict[str, dict[str, int]] = field(default_factory=dict)


@runtime_checkable
class FormatAdapter(Protocol):
    """Format seam (§3): how the pipeline touches concrete XML.

    The orchestrator never imports a format module; it writes corrected
    documents exclusively through this port.
    ``saknussemm.formats.alto`` provides the ALTO implementation (and the
    pipeline's lazy composition-boundary default); ``formats.page`` plugs
    in the same way.
    """

    def rewrite_file(
        self,
        xml_path: Path,
        pages: list[PageManifest],
        provider: str,
        model: str,
        *,
        lib_version: str | None = None,
        config_fingerprint: str | None = None,
    ) -> RewriteResult:
        """Rewrite one source file with the pages' corrected text."""
        ...


__all__ = [
    "BaseProvider",
    "EditProducer",
    "ModelCatalog",
    "StructuredCompletionClient",
    "FormatAdapter",
    "PipelineObserver",
    "ProducerMetadata",
    "ProducerOptions",
    "ProviderTransientError",
    "ProviderPermanentError",
    "RewriteMetrics",
    "RewriteResult",
    "require_capabilities",
    "require_page_images",
]

# ---------------------------------------------------------------------------
# Word geometry (§6.1) — the slow path's only guess
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TokenBox:
    """A token and the horizontal span the rewriter should draw for it.

    Horizontal only, and deliberately. A line's ``VPOS``/``HEIGHT`` are the
    line's own and every token inherits them; a resolver that claimed a
    per-word vertical extent would be asserting a precision no method here
    has. When one does — an ink mask, a polygon — it gets its own seam
    rather than smuggling itself through this one.

    ``text`` may be a run of whitespace: ``SP`` elements are emitted from
    space tokens and their geometry has to agree with the Strings around
    them, so spaces are carried here rather than left as gaps.
    """

    text: str
    hpos: int
    width: int


@dataclass(frozen=True)
class LineGeometryRequest:
    """One line's box, and the tokens that must be laid out inside it.

    ``image`` is an OPAQUE reference and the core never opens it. That is
    what lets this request cross the pixel-blind engine untouched: the
    caller puts something in (a path, an ``ImageAsset``, a pre-cut crop),
    the core hands it over without importing anything that can decode it,
    and only a resolver that lives outside this package looks. ``I4``
    (``tests/test_import_contract.py``) stays true by construction rather
    than by discipline.
    """

    hpos: int
    width: int
    tokens: tuple[str, ...]
    line_id: str = ""
    vpos: int = 0
    height: int = 0
    image: object | None = None


@runtime_checkable
class WordGeometryResolver(Protocol):
    """Where each token of a re-segmented line sits, horizontally.

    The slow path exists because a correction changed the word count, and
    once it does, every original ``String`` box on that line is discarded
    and the width redistributed. Today that redistribution is proportional
    to character count — honest, deterministic, and blind to the image.
    Measured against the producers' own boxes, it puts 87–93% of word
    boundaries inside the true inter-word blank, with a tail out to nearly
    four characters. This seam is where something that looks at the pixels
    can do better, and where it has to prove that it does.

    A resolver is NOT trusted. Its output is validated before it reaches
    the tree — right token count, monotonic, inside the line box, widths
    positive — and the proportional geometry is used instead when the
    check fails. A third party must not be able to make saknussemm emit an
    ALTO whose boxes contradict its text; that guarantee is the engine's,
    not the resolver's.
    """

    name: str

    def resolve(self, request: LineGeometryRequest) -> tuple[TokenBox, ...]: ...
