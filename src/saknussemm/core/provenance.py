"""What a run records about its own inputs and dependencies (§11).

Helpers the orchestrator used to carry: which format adapter serves a
document, which dependency versions were installed, the digest of every
source file, and the assembled provenance record itself. None of them
touches run state — the record is a function of the run's inputs and
the identities it was configured with, which is exactly why it does not
need the engine to build it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from saknussemm.core.sources import SourceSnapshot
from typing import Any, Protocol

from saknussemm.core.protocols import EditProducer, ProducerMetadata
from saknussemm.core.quality import QEScorer, RoutingPolicy
from saknussemm.core.schemas import (
    ConfidencePolicy,
    DocumentManifest,
    ImageAsset,
    PageImage,
    ProducerProvenance,
    ReviewPolicy,
    RunProvenance,
)


#: The dependencies whose installed version a run records.
_PROVENANCE_DEPENDENCIES = ("lxml", "pydantic")


def _dependency_versions() -> dict[str, str]:
    """Installed versions of the critical dependencies; a package that
    is not installed is simply absent (never an error — a core-only
    consumer legitimately runs without lxml)."""
    import importlib.metadata as _md

    versions: dict[str, str] = {}
    for package in _PROVENANCE_DEPENDENCIES:
        try:
            versions[package] = _md.version(package)
        except _md.PackageNotFoundError:
            continue
    return versions


def source_digest(raw: bytes) -> str:
    """``sha256:<hex>`` of a source document's bytes.

    One definition, because a digest computed two ways is a digest that can
    disagree with itself: the parse-time stamp on the manifest, the
    provenance record and the edit script's preconditions all come from
    here.
    """
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _digest_sources(source_files: dict[str, Path]) -> dict[str, str]:
    """``sha256:<hex>`` of every input file's bytes, as GIVEN.

    Computed once per run and shared by the provenance record and the
    final edit script's preconditions — the two must agree by
    construction, not by coincidence.
    """
    return {
        name: source_digest(path.read_bytes()) for name, path in source_files.items()
    }


def digests_of_the_bytes_decided_on(
    document_manifest: DocumentManifest,
    source_files: dict[str, Path],
    *,
    snapshots: dict[str, SourceSnapshot] | None = None,
) -> dict[str, str]:
    """Digests for the given files, taken from the parse rather than re-read.

    ``RunProvenance.source_digests`` means "the input bytes, as GIVEN", so
    the keys follow ``source_files`` — a decide-only run gives none and
    attests none.

    Runs supply the immutable snapshots captured and verified at preflight:
    neither rendering nor provenance reopens the source paths. This also
    covers hand-built manifests without a parser stamp. Callers without
    snapshots retain the parser stamp, or hash their files if unstamped.
    """
    if snapshots is not None:
        return {name: source_digest(source.raw) for name, source in snapshots.items()}
    stamped = document_manifest.source_digests
    if not stamped:
        return _digest_sources(source_files)
    return {name: stamped[name] for name in source_files if name in stamped}


class _PolicyHolder(Protocol):
    """What :func:`_build_run_provenance` reads off the pipeline (§11).

    Structural, so ``provenance`` never imports ``pipeline`` (which
    imports it): the identity envelope, the five fingerprinted policies
    through ``config_fingerprint()``, and the four that live outside it.
    """

    producer_metadata: ProducerMetadata
    escalation_producer: EditProducer | None
    routing_policy: RoutingPolicy
    review_policy: ReviewPolicy
    confidence_policy: ConfidencePolicy
    qe_scorer: QEScorer | None

    def config_fingerprint(self) -> str: ...


def _active_policies(pipeline: _PolicyHolder) -> dict[str, dict[str, Any]]:
    """The policies outside ``config_fingerprint`` that are not in their
    neutral state, each as its own JSON dump (``RunProvenance.active_policies``).

    Computed from the policy objects alone, so the report says what the
    fingerprint cannot: routing bounds decide which lines keep their OCR
    text, and that is a delivered byte. The scorer is named, not dumped —
    it is a protocol, and its name is the only identity it declares.
    """
    routing, review = pipeline.routing_policy, pipeline.review_policy
    active: dict[str, dict[str, Any]] = {}
    if routing.skip_at_or_below is not None or routing.escalate_at_or_above is not None:
        active["routing"] = routing.model_dump(mode="json")
    if review.enabled:
        active["review"] = review.model_dump(mode="json")
    if pipeline.confidence_policy.mode != "drop":
        active["confidence"] = pipeline.confidence_policy.model_dump(mode="json")
    if pipeline.qe_scorer is not None:
        # ``name`` is in the protocol, but a scorer that never declared
        # one was accepted until now; the same ``getattr`` courtesy the
        # producers get, so provenance never refuses what the run accepted
        active["qe_scorer"] = {"name": getattr(pipeline.qe_scorer, "name", "unknown")}
    return active


def _build_run_provenance(
    pipeline: _PolicyHolder,
    *,
    document_manifest: DocumentManifest,
    source_digests: dict[str, str],
    image_assets: dict[str, PageImage],
) -> RunProvenance:
    """The run's §11 provenance record.

    Library + producer identity, policy fingerprint, the active policies
    the fingerprint leaves out (:func:`_active_policies`), per-file
    digests of the INPUT bytes (computed once per run by
    :func:`_digest_sources` and shared with the edit script's
    preconditions, so the two agree by construction), per-page image
    digests, and critical dependency versions.
    """
    from saknussemm import __version__ as _lib_version

    # copy the digest each structured ImageAsset already carries; the core
    # never opens an image (I4). Bare ImageRef strings and digest-less
    # assets contribute nothing.
    image_digests = {
        page_id: f"sha256:{asset.sha256}"
        for page_id, asset in image_assets.items()
        if isinstance(asset, ImageAsset) and asset.sha256
    }
    # record the escalation (vision) producer's identity too, from its own
    # declared metadata (the same optional-attribute convention as the
    # primary producer's). None for a single-producer run, so text-only
    # provenance is unchanged.
    escalation_prov: ProducerProvenance | None = None
    if pipeline.escalation_producer is not None:
        emd = (
            getattr(pipeline.escalation_producer, "metadata", None)
            or ProducerMetadata()
        )
        escalation_prov = ProducerProvenance(
            name=emd.name,
            version=emd.version,
            implementation=emd.implementation,
            configuration_fingerprint=emd.configuration_fingerprint,
        )
    producer_metadata = pipeline.producer_metadata
    return RunProvenance(
        lib_version=_lib_version,
        config_fingerprint=pipeline.config_fingerprint(),
        active_policies=_active_policies(pipeline),
        producer=ProducerProvenance(
            name=producer_metadata.name,
            version=producer_metadata.version,
            implementation=producer_metadata.implementation,
            configuration_fingerprint=producer_metadata.configuration_fingerprint,
        ),
        escalation_producer=escalation_prov,
        source_digests=source_digests,
        image_digests=image_digests,
        source_format=document_manifest.source_format,
        dependencies=_dependency_versions(),
    )
