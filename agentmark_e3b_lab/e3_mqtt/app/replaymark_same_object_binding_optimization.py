from __future__ import annotations

"""Paired A/B characterization of the E3b same-object certificate-binding fast path.

The parent behavior is emulated literally: after constructing the semantic
certificate it fingerprints both realized values on both sides of the wrapper
binding. The optimized production path uses object identity only when the exact
same frozen value objects are shared, while detached values retain content hashes.
"""

import argparse
import json
from pathlib import Path

from replaymark.runtime_contract_identity import verified_runtime_contract_identity
from replaymark.runtime_e3b_bridge import (
    E3B_SHADOW_BRIDGE_ID,
    E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST,
    E3B_SHADOW_RUNTIME_CERTIFICATE_SCHEMA,
    E3bShadowRuntimeReuseCertificate,
    certify_e3b_shadow_reuse,
)
from replaymark.runtime_e3b_correlation import correlate_e3b_runtime_pair
from replaymark.runtime_realization import RuntimeReuseCertificate
from replaymark_verification.runtime_cost_measurement import run_interleaved, summary_is_ordered

from replaymark_runtime_cost import _build_cases, _collect_live_materials, _pin_single_cpu
from replaymark_shadow import compile_e3b_r1_shadow_contract

SCHEMA = "replaymark.runtime-e3b-same-object-binding-fast-path-ab.v1"
_RUNTIME_REUSE_CERTIFICATE_SCHEMA = "replaymark.runtime.reuse-certificate.v1"


def _legacy_parent_bridge(contract, pair):
    observation = pair.observation
    historical_action = pair.historical_action
    token = observation.evidence_token
    action = historical_action.action
    identity = verified_runtime_contract_identity(contract)
    adjudication = contract.adjudicate(token, action)
    reuse_decision = contract.certify_reuse(token, action)
    semantic = RuntimeReuseCertificate(
        schema_version=_RUNTIME_REUSE_CERTIFICATE_SCHEMA,
        contract_fingerprint=identity.contract_fingerprint,
        claim_fingerprint=identity.claim_fingerprint,
        observation=observation,
        historical_action=historical_action,
        adjudication=adjudication,
        reuse_decision=reuse_decision,
    )

    # Exact parent-wrapper content binding, before the same-object fast path.
    if semantic.observation.fingerprint() != pair.observation.fingerprint():
        raise ValueError("legacy observation binding mismatch")
    if semantic.historical_action.fingerprint() != pair.historical_action.fingerprint():
        raise ValueError("legacy historical-action binding mismatch")

    return E3bShadowRuntimeReuseCertificate(
        schema_version=E3B_SHADOW_RUNTIME_CERTIFICATE_SCHEMA,
        bridge_id=E3B_SHADOW_BRIDGE_ID,
        bridge_semantic_digest=E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST,
        contract_fingerprint=identity.contract_fingerprint,
        claim_fingerprint=identity.claim_fingerprint,
        correlated_pair=pair,
        semantic_certificate=semantic,
    )


def _pair_result(cases, contract, *, rounds: int, inner: int, seed: int):
    verified_runtime_contract_identity(contract)

    def legacy_full(index: int):
        case = cases[index]
        pair = correlate_e3b_runtime_pair(case.raw_observation, case.raw_action)
        return _legacy_parent_bridge(contract, pair)

    def optimized_full(index: int):
        case = cases[index]
        pair = correlate_e3b_runtime_pair(case.raw_observation, case.raw_action)
        return certify_e3b_shadow_reuse(contract, pair)

    def legacy_constructor(index: int):
        case = cases[index]
        semantic = case.certificate.semantic_certificate
        pair = case.pair
        if semantic.observation.fingerprint() != pair.observation.fingerprint():
            raise AssertionError("legacy observation binding drift")
        if semantic.historical_action.fingerprint() != pair.historical_action.fingerprint():
            raise AssertionError("legacy action binding drift")
        return E3bShadowRuntimeReuseCertificate(
            schema_version=E3B_SHADOW_RUNTIME_CERTIFICATE_SCHEMA,
            bridge_id=E3B_SHADOW_BRIDGE_ID,
            bridge_semantic_digest=E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST,
            contract_fingerprint=case.certificate.contract_fingerprint,
            claim_fingerprint=case.certificate.claim_fingerprint,
            correlated_pair=pair,
            semantic_certificate=semantic,
        )

    def optimized_constructor(index: int):
        case = cases[index]
        return E3bShadowRuntimeReuseCertificate(
            schema_version=E3B_SHADOW_RUNTIME_CERTIFICATE_SCHEMA,
            bridge_id=E3B_SHADOW_BRIDGE_ID,
            bridge_semantic_digest=E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST,
            contract_fingerprint=case.certificate.contract_fingerprint,
            claim_fingerprint=case.certificate.claim_fingerprint,
            correlated_pair=case.pair,
            semantic_certificate=case.certificate.semantic_certificate,
        )

    for index in range(len(cases)):
        legacy = legacy_full(index)
        optimized = optimized_full(index)
        if legacy.canonical_bytes() != optimized.canonical_bytes():
            raise AssertionError("parent/optimized full-pipeline certificate bytes differ")
        if legacy_constructor(index).canonical_bytes() != optimized_constructor(index).canonical_bytes():
            raise AssertionError("parent/optimized wrapper certificate bytes differ")

    full = run_interleaved(
        {"parent_content_binding": legacy_full, "same_object_fast_path": optimized_full},
        case_count=len(cases), rounds=rounds, inner=inner, warmup_rounds=20, seed=seed,
    )
    constructor = run_interleaved(
        {"parent_content_binding": legacy_constructor, "same_object_fast_path": optimized_constructor},
        case_count=len(cases), rounds=rounds, inner=inner, warmup_rounds=20, seed=seed + 1000,
    )
    for result in (full, constructor):
        if not all(summary_is_ordered(summary) for summary in result.values()):
            raise AssertionError("paired percentile ordering failed")
        if not all(int(summary["samples"]) == rounds for summary in result.values()):
            raise AssertionError("paired sample count incomplete")

    def delta(result):
        old = float(result["parent_content_binding"]["p50_ns"])
        new = float(result["same_object_fast_path"]["p50_ns"])
        return {
            "p50_saved_ns": old - new,
            "p50_saved_us": (old - new) / 1000.0,
            "p50_ratio_parent_over_fast_path": old / new,
            "status": "DESCRIPTIVE_PAIRED_MEASUREMENT_NOT_A_PROMOTION_THRESHOLD",
        }

    return {
        "full_pipeline": full,
        "full_pipeline_descriptive_delta": delta(full),
        "wrapper_constructor": constructor,
        "wrapper_constructor_descriptive_delta": delta(constructor),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--broker", default="mosquitto")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--tasks", type=int, default=64)
    parser.add_argument("--wave-size", type=int, default=16)
    parser.add_argument("--wave-period-ms", type=float, default=300)
    parser.add_argument("--verify-floor-ms", type=float, default=100)
    parser.add_argument("--source-guard-ms", type=float, default=20)
    parser.add_argument("--changed-delay-floor-ms", type=float, default=150)
    parser.add_argument("--target-margin-ms", type=float, default=50)
    parser.add_argument("--post-completion-gap-ms", type=float, default=20)
    parser.add_argument("--task-timeout-ms", type=int, default=1200)
    parser.add_argument("--rounds", type=int, default=240)
    parser.add_argument("--inner", type=int, default=8)
    parser.add_argument("--authority-head", required=True)
    parser.add_argument("--out", default="/results/e3b_same_object_binding_fast_path_ab.json")
    args = parser.parse_args()

    if args.tasks != 64 or args.tasks % args.wave_size:
        raise ValueError("frozen A/B requires exactly 64 tasks divisible by wave size")

    contract = compile_e3b_r1_shadow_contract()
    contract_fp = contract.fingerprint()
    broker_version, verify_ms, target_delay_ms, materials = _collect_live_materials(
        contract,
        broker=args.broker,
        port=args.port,
        tasks=args.tasks,
        wave_size=args.wave_size,
        wave_period_ms=args.wave_period_ms,
        verify_floor_ms=args.verify_floor_ms,
        source_guard_ms=args.source_guard_ms,
        changed_delay_floor_ms=args.changed_delay_floor_ms,
        target_margin_ms=args.target_margin_ms,
        post_completion_gap_ms=args.post_completion_gap_ms,
        task_timeout_ms=args.task_timeout_ms,
    )
    negative, positive = _build_cases(materials, contract)
    affinity = _pin_single_cpu()

    negative_ab = _pair_result(negative, contract, rounds=args.rounds, inner=args.inner, seed=20260911)
    positive_ab = _pair_result(positive, contract, rounds=args.rounds, inner=args.inner, seed=20260912)

    promotion_pass = (
        broker_version == "mosquitto version 2.1.2"
        and len(negative) == 64
        and len(positive) == 64
        and all(
            int(summary["samples"]) == args.rounds
            for outcome in (negative_ab, positive_ab)
            for group in (outcome["full_pipeline"], outcome["wrapper_constructor"])
            for summary in group.values()
        )
    )

    report = {
        "schema": SCHEMA,
        "authority_head": args.authority_head,
        "broker_version_sys": broker_version,
        "contract_fingerprint": contract_fp,
        "bridge_semantic_digest": E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST,
        "live_corpus": {
            "negative_live_cases": len(negative),
            "positive_definition_derived_cases": len(positive),
            "positive_cases_are_not_live_empirical_outcomes": True,
            "verify_ms": verify_ms,
            "target_delay_ms": target_delay_ms,
        },
        "measurement_environment": {"affinity": affinity},
        "paired_ab": {
            "live_negative": negative_ab,
            "derived_positive": positive_ab,
        },
        "semantic_equivalence": {
            "complete_128_case_parent_vs_fast_path_canonical_bytes_exact": True,
            "bridge_semantic_digest_unchanged": True,
        },
        "measurement_validity": {
            "network_closed_before_timing": True,
            "same_process_same_contract_same_corpus": True,
            "deterministic_randomized_interleaving": True,
            "fixed_speed_promotion_threshold": False,
        },
        "paper_boundary": {
            "new_semantic_claim": False,
            "changes_reuse_theorem": False,
            "changes_verdict_semantics": False,
            "role": "bounded artifact feasibility refinement",
        },
        "execution_policy": "NOT_IMPLEMENTED",
        "selective_reuse_intervention": "NOT_IMPLEMENTED",
        "promotion_pass": promotion_pass,
        "verdict": "PASS" if promotion_pass else "FAIL",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "verdict": report["verdict"],
        "broker": broker_version,
        "negative_full_parent_p50_us": negative_ab["full_pipeline"]["parent_content_binding"]["p50_us"],
        "negative_full_fast_p50_us": negative_ab["full_pipeline"]["same_object_fast_path"]["p50_us"],
        "negative_ctor_parent_p50_us": negative_ab["wrapper_constructor"]["parent_content_binding"]["p50_us"],
        "negative_ctor_fast_p50_us": negative_ab["wrapper_constructor"]["same_object_fast_path"]["p50_us"],
        "positive_full_parent_p50_us": positive_ab["full_pipeline"]["parent_content_binding"]["p50_us"],
        "positive_full_fast_p50_us": positive_ab["full_pipeline"]["same_object_fast_path"]["p50_us"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
