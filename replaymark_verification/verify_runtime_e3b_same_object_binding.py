from __future__ import annotations

"""Safety gate for the E3b same-object certificate-binding fast path."""

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from replaymark.runtime_e3b_bridge import (
    E3B_SHADOW_BRIDGE_ID,
    E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST,
    E3B_SHADOW_RUNTIME_CERTIFICATE_SCHEMA,
    E3bShadowRuntimeReuseCertificate,
    certify_e3b_shadow_reuse,
)
from replaymark.runtime_e3b_correlation import E3bCorrelatedRuntimePair, correlate_e3b_runtime_pair
from replaymark.runtime_realization import RealizedHistoricalAction, RealizedObservation
from replaymark_verification.verify_runtime_e3b_bridge import _action, _contract, _obs

EXPECTED_BRIDGE_SEMANTIC_DIGEST = (
    "e4db6e24e2da609c3361ef279a465c88c5068c44e7ae902eed75afec42d32a03"
)


def _wrap(pair: E3bCorrelatedRuntimePair, semantic) -> E3bShadowRuntimeReuseCertificate:
    return E3bShadowRuntimeReuseCertificate(
        schema_version=E3B_SHADOW_RUNTIME_CERTIFICATE_SCHEMA,
        bridge_id=E3B_SHADOW_BRIDGE_ID,
        bridge_semantic_digest=E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST,
        contract_fingerprint=semantic.contract_fingerprint,
        claim_fingerprint=semantic.claim_fingerprint,
        correlated_pair=pair,
        semantic_certificate=semantic,
    )


def _count_wrapper_fingerprints(pair, semantic) -> tuple[E3bShadowRuntimeReuseCertificate, dict[str, int]]:
    counts = {"observation": 0, "historical_action": 0}
    original_obs = RealizedObservation.fingerprint
    original_action = RealizedHistoricalAction.fingerprint

    def counted_obs(self):
        counts["observation"] += 1
        return original_obs(self)

    def counted_action(self):
        counts["historical_action"] += 1
        return original_action(self)

    RealizedObservation.fingerprint = counted_obs  # type: ignore[method-assign]
    RealizedHistoricalAction.fingerprint = counted_action  # type: ignore[method-assign]
    try:
        chained = _wrap(pair, semantic)
    finally:
        RealizedObservation.fingerprint = original_obs  # type: ignore[method-assign]
        RealizedHistoricalAction.fingerprint = original_action  # type: ignore[method-assign]
    return chained, counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    if E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST != EXPECTED_BRIDGE_SEMANTIC_DIGEST:
        raise AssertionError("bridge semantic digest changed during non-semantic optimization")

    contract = _contract()
    pair = correlate_e3b_runtime_pair(_obs(7, True), _action(7))
    production = certify_e3b_shadow_reuse(contract, pair)
    semantic = production.semantic_certificate

    # Exact production construction must use the same immutable realized objects.
    assert semantic.observation is pair.observation
    assert semantic.historical_action is pair.historical_action
    same_object, same_counts = _count_wrapper_fingerprints(pair, semantic)
    assert same_counts == {"observation": 0, "historical_action": 0}
    assert same_object.canonical_bytes() == production.canonical_bytes()

    # Two independently reconstructed, byte-identical sides must take the old
    # content-addressed path. Do not accidentally share the detached objects
    # between pair and semantic certificate: that would correctly be a fast hit.
    pair_observation = replace(pair.observation)
    pair_action = replace(pair.historical_action)
    semantic_observation = replace(pair.observation)
    semantic_action = replace(pair.historical_action)
    detached_pair = replace(
        pair,
        observation=pair_observation,
        historical_action=pair_action,
    )
    detached_semantic = replace(
        semantic,
        observation=semantic_observation,
        historical_action=semantic_action,
    )
    assert detached_semantic.observation is not detached_pair.observation
    assert detached_semantic.historical_action is not detached_pair.historical_action
    detached, detached_counts = _count_wrapper_fingerprints(detached_pair, detached_semantic)
    assert detached_counts == {"observation": 2, "historical_action": 2}
    assert detached.canonical_bytes() == production.canonical_bytes()

    # A detached semantic certificate with a changed realized value must still fail closed.
    altered_observation = replace(
        semantic.observation,
        boundary_timestamp_ns=semantic.observation.boundary_timestamp_ns + 1,
    )
    altered_semantic = replace(semantic, observation=altered_observation)
    try:
        _wrap(pair, altered_semantic)
    except ValueError as exc:
        assert "different realized observation" in str(exc)
        detached_mismatch_rejected = True
    else:
        raise AssertionError("detached mismatched observation bypassed content binding")

    outcome_rows = {}
    for name, c, confirmed in (
        ("VALID", _contract(), True),
        ("INVALID", _contract(), False),
        ("UNRESOLVED", _contract(ambiguous=True), True),
    ):
        p = correlate_e3b_runtime_pair(_obs(9, confirmed), _action(9))
        cert = certify_e3b_shadow_reuse(c, p)
        rebuilt, counts = _count_wrapper_fingerprints(p, cert.semantic_certificate)
        assert counts == {"observation": 0, "historical_action": 0}
        assert rebuilt.canonical_bytes() == cert.canonical_bytes()
        assert cert.semantic_certificate.adjudication.verdict.value == name
        outcome_rows[name] = {
            "reuse": cert.semantic_certificate.reuse_decision.disposition.value,
            "same_object_wrapper_fingerprint_calls": 0,
            "canonical_bytes_stable": True,
        }

    report = {
        "schema": "replaymark.runtime-e3b-same-object-binding-fast-path-gate.v1",
        "verdict": "PASS",
        "bridge_semantic_digest_unchanged": True,
        "same_object_fast_path": {
            "observation_fingerprint_calls": same_counts["observation"],
            "historical_action_fingerprint_calls": same_counts["historical_action"],
            "exact_production_objects_shared": True,
        },
        "detached_content_path": {
            "observation_fingerprint_calls": detached_counts["observation"],
            "historical_action_fingerprint_calls": detached_counts["historical_action"],
            "independently_reconstructed_byte_identical_objects": True,
            "byte_identical_detached_certificate_accepted": True,
            "mismatched_detached_observation_rejected": detached_mismatch_rejected,
        },
        "semantic_outcomes": outcome_rows,
        "semantic_change": False,
        "certificate_schema_change": False,
        "execution_policy": "NOT_IMPLEMENTED",
        "selective_reuse_intervention": "NOT_IMPLEMENTED",
    }
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
