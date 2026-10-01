"""G4 — what ``config_fingerprint`` leaves out is written beside it.

``config_fingerprint`` covers the five §8.2 policies. Routing is not one
of them, yet a ``SKIP`` makes the OCR text the final text: two runs with
different bounds deliver different bytes under the same fingerprint.
Folding routing into the fingerprint would move every fingerprint already
stamped into delivered files; making the fingerprint conditional would
make it impossible to recompute from the policy objects. So the report
carries ``active_policies`` beside the fingerprint, and these tests pin
that the fingerprint does not move and the field says what differs.
"""

from __future__ import annotations

from saknussemm import CorrectionPipeline
from saknussemm.core.provenance import _active_policies
from saknussemm.core.quality import HeuristicQEScorer, RoutingPolicy
from saknussemm.core.schemas import ConfidencePolicy, ReviewPolicy
from saknussemm.formats.alto.parser import build_document_manifest

from tests._pipeline_harness import EXAMPLES, DictProvider, RecordingObserver

_SAMPLE = EXAMPLES / "sample.xml"


def _pipeline(**pipeline_kwargs: object) -> CorrectionPipeline:
    return CorrectionPipeline.for_provider(
        DictProvider({}),
        api_key="k",
        model="m",
        provider_name="test-prov",
        observer=RecordingObserver(),
        **pipeline_kwargs,
    )


def _run(**pipeline_kwargs: object):
    doc = build_document_manifest([(_SAMPLE, _SAMPLE.name)])
    return _pipeline(**pipeline_kwargs).run_sync(
        document_manifest=doc, source_files={_SAMPLE.name: _SAMPLE}
    )


def test_two_routing_thresholds_share_a_fingerprint_and_differ_beside_it():
    lenient = _pipeline(
        qe_scorer=HeuristicQEScorer(),
        routing_policy=RoutingPolicy(skip_at_or_below=0.1),
    )
    strict = _pipeline(
        qe_scorer=HeuristicQEScorer(),
        routing_policy=RoutingPolicy(skip_at_or_below=0.5),
    )
    # the fingerprint already stamped into delivered files does not move
    assert lenient.config_fingerprint() == strict.config_fingerprint()
    # and the report can still tell the two runs apart
    assert _active_policies(lenient) != _active_policies(strict)
    assert _active_policies(lenient)["routing"]["skip_at_or_below"] == 0.1
    assert _active_policies(strict)["routing"]["skip_at_or_below"] == 0.5
    assert _active_policies(lenient)["qe_scorer"] == {"name": "heuristic-qe"}


def test_the_dump_recomputes_the_policy_fingerprint():
    policy = RoutingPolicy(skip_at_or_below=0.1, escalate_at_or_above=0.9)
    dump = _active_policies(
        _pipeline(qe_scorer=HeuristicQEScorer(), routing_policy=policy)
    )["routing"]
    assert RoutingPolicy(**dump).policy_fingerprint() == policy.policy_fingerprint()


def test_a_run_with_nothing_optional_active_carries_an_empty_mapping():
    result = _run(review_policy=ReviewPolicy.silent())
    prov = result.report.provenance
    assert prov is not None
    assert prov.active_policies == {}


def test_the_default_run_names_the_review_rules_it_applied():
    """Review is on by default and changes statuses, never bytes: it is
    active, and the report says which rules were on."""
    result = _run()
    prov = result.report.provenance
    assert prov is not None
    assert set(prov.active_policies) == {"review"}
    assert prov.active_policies["review"]["enabled"] is True
    assert ReviewPolicy(**prov.active_policies["review"]) == ReviewPolicy()


def test_a_reported_confidence_is_an_active_policy():
    active = _active_policies(
        _pipeline(
            review_policy=ReviewPolicy.silent(),
            confidence_policy=ConfidencePolicy(mode="report_only"),
        )
    )
    assert active == {"confidence": {"mode": "report_only"}}


def test_the_report_round_trips_the_field():
    from saknussemm.core.schemas import CorrectionReport

    result = _run(
        qe_scorer=HeuristicQEScorer(),
        routing_policy=RoutingPolicy(skip_at_or_below=0.0),
    )
    again = CorrectionReport.model_validate_json(result.report.model_dump_json())
    assert again.provenance is not None
    assert again.provenance.active_policies == result.report.provenance.active_policies
    assert "routing" in again.provenance.active_policies
