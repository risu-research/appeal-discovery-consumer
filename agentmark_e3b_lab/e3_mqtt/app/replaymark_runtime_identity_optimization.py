from __future__ import annotations

"""Paired live-corpus A/B characterization of runtime contract-identity reuse.

This runner compares the exact pre-optimization bridge orchestration against the
optimized bridge on the same raw E3b corpus, same process, same contract, and
deterministically interleaved timing rounds. Network acquisition completes and
Harness.close() stops the Paho loop before any A/B timing begins.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import time

from replaymark.compiled_contract import ExplicitCompiledContract
from replaymark.runtime_contract_identity import (
    runtime_contract_identity_cache_info,
    verified_runtime_contract_identity,
)
from replaymark.runtime_e3b_bridge import (
    E3B_SHADOW_BRIDGE_ID,
    E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST,
    E3B_SHADOW_RUNTIME_CERTIFICATE_SCHEMA,
    E3bShadowRuntimeReuseCertificate,
    certify_e3b_shadow_reuse,
)
from replaymark.runtime_e3b_correlation import correlate_e3b_runtime_pair
from replaymark.runtime_realization import RuntimeReuseCertificate
from replaymark_verification.runtime_cost_measurement import (
    run_interleaved,
    summary_is_ordered,
    summarize_ns,
    timer_probe,
)

from replaymark_runtime_cost import (
    _build_cases,
    _collect_live_materials,
    _cpu_model,
    _pin_single_cpu,
)
from replaymark_shadow import compile_e3b_r1_shadow_contract

SCHEMA = "replaymark.runtime-contract-identity-optimization-ab.v1"
_RUNTIME_REUSE_CERTIFICATE_SCHEMA = "replaymark.runtime.reuse-certificate.v1"


def _legacy_recompute_bridge(contract: ExplicitCompiledContract, pair) -> E3bShadowRuntimeReuseCertificate:
    observation = pair.observation
    historical_action = pair.historical_action
    token = observation.evidence_token
    action = historical_action.action
    adjudication = contract.adjudicate(token, action)
    reuse_decision = contract.certify_reuse(token, action)
    semantic = RuntimeReuseCertificate(
        schema_version=_RUNTIME_REUSE_CERTIFICATE_SCHEMA,
        contract_fingerprint=contract.fingerprint(),
        claim_fingerprint=contract.claim_fingerprint,
        observation=observation,
        historical_action=historical_action,
        adjudication=adjudication,
        reuse_decision=reuse_decision,
    )
    return E3bShadowRuntimeReuseCertificate(
        schema_version=E3B_SHADOW_RUNTIME_CERTIFICATE_SCHEMA,
        bridge_id=E3B_SHADOW_BRIDGE_ID,
        bridge_semantic_digest=E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST,
        contract_fingerprint=contract.fingerprint(),
        claim_fingerprint=contract.claim_fingerprint,
        correlated_pair=pair,
        semantic_certificate=semantic,
    )


def _case_digest(cases) -> str:
    payload = [{
        "provenance": case.provenance,
        "task_id": case.task_id,
        "raw_observation": case.raw_observation,
        "raw_action": case.raw_action,
    } for case in cases]
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _ab_for_cases(cases, contract, *, rounds: int, inner: int, seed: int):
    verified_runtime_contract_identity(contract)

    def legacy(index: int):
        case = cases[index]
        pair = correlate_e3b_runtime_pair(case.raw_observation, case.raw_action)
        return _legacy_recompute_bridge(contract, pair)

    def optimized(index: int):
        case = cases[index]
        pair = correlate_e3b_runtime_pair(case.raw_observation, case.raw_action)
        return certify_e3b_shadow_reuse(contract, pair)

    for index in range(len(cases)):
        if legacy(index).canonical_bytes() != optimized(index).canonical_bytes():
            raise AssertionError("legacy/optimized certificate bytes differ before timing")

    summaries = run_interleaved(
        {"legacy_recompute": legacy, "optimized_cached": optimized},
        case_count=len(cases),
        rounds=rounds,
        inner=inner,
        warmup_rounds=20,
        seed=seed,
    )
    legacy_summary = summaries["legacy_recompute"]
    optimized_summary = summaries["optimized_cached"]
    if not summary_is_ordered(legacy_summary) or not summary_is_ordered(optimized_summary):
        raise AssertionError("paired A/B percentile ordering failed")
    legacy_p50 = float(legacy_summary["p50_ns"])
    optimized_p50 = float(optimized_summary["p50_ns"])
    return {
        "legacy_recompute": legacy_summary,
        "optimized_cached": optimized_summary,
        "descriptive_delta": {
            "p50_saved_ns": legacy_p50 - optimized_p50,
            "p50_saved_us": (legacy_p50 - optimized_p50) / 1000.0,
            "p50_ratio_legacy_over_optimized": legacy_p50 / optimized_p50,
            "status": "DESCRIPTIVE_PAIRED_MEASUREMENT_NOT_A_PROMOTION_THRESHOLD",
        },
    }


def _identity_lookup_microbench(*, samples: int = 31, hot_rounds: int = 400):
    cold_ns = []
    for _ in range(samples):
        contract = compile_e3b_r1_shadow_contract()
        start = time.perf_counter_ns()
        identity = verified_runtime_contract_identity(contract)
        cold_ns.append(float(time.perf_counter_ns() - start))
        if identity.contract_fingerprint != contract.fingerprint():
            raise AssertionError("cold identity acquisition returned wrong fingerprint")

    hot_contract = compile_e3b_r1_shadow_contract()
    verified_runtime_contract_identity(hot_contract)
    hot_ns = []
    for _ in range(hot_rounds):
        start = time.perf_counter_ns()
        verified_runtime_contract_identity(hot_contract)
        hot_ns.append(float(time.perf_counter_ns() - start))

    return {
        "cold_verified_identity_acquisition": summarize_ns(cold_ns),
        "hot_identity_lookup": summarize_ns(hot_ns),
        "cache_info_after_probe": runtime_contract_identity_cache_info(),
        "note": "cold includes one full contract fingerprint; hot is object-identity lookup only",
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
    parser.add_argument("--out", default="/results/e3b_runtime_contract_identity_optimization.json")
    args = parser.parse_args()

    if args.tasks != 64:
        raise ValueError("optimization characterization uses exactly 64 live tasks")
    if args.tasks % args.wave_size:
        raise ValueError("tasks must be divisible by wave size")

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
    corpus_digest = _case_digest([*negative, *positive])

    for case in [*negative, *positive]:
        legacy = _legacy_recompute_bridge(contract, case.pair)
        optimized = certify_e3b_shadow_reuse(contract, case.pair)
        if legacy.canonical_bytes() != optimized.canonical_bytes():
            raise AssertionError("complete-corpus legacy/optimized byte equivalence failed")

    affinity = _pin_single_cpu()
    timer = timer_probe()
    negative_ab = _ab_for_cases(negative, contract, rounds=args.rounds, inner=args.inner, seed=20260909)
    positive_ab = _ab_for_cases(positive, contract, rounds=args.rounds, inner=args.inner, seed=20260910)
    identity_probe = _identity_lookup_microbench()
    cache_info = runtime_contract_identity_cache_info()

    promotion_pass = (
        broker_version == "mosquitto version 2.1.2"
        and len(negative) == 64
        and len(positive) == 64
        and int(cache_info["size"]) <= int(cache_info["capacity"])
        and all(
            int(side["samples"]) == args.rounds
            for result in (negative_ab, positive_ab)
            for side in (result["legacy_recompute"], result["optimized_cached"])
        )
    )
    result = {
        "schema": SCHEMA,
        "authority_head": args.authority_head,
        "broker_version_sys": broker_version,
        "frozen_authorities": {
            "contract_fingerprint": contract_fp,
            "bridge_semantic_digest": E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST,
        },
        "live_corpus": {
            "tasks": args.tasks,
            "verify_ms": verify_ms,
            "target_delay_ms": target_delay_ms,
            "negative_live_cases": len(negative),
            "positive_definition_derived_cases": len(positive),
            "positive_cases_are_not_live_empirical_outcomes": True,
            "corpus_sha256": corpus_digest,
        },
        "measurement_environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cpu_model": _cpu_model(),
            "logical_cpu_count": os.cpu_count(),
            "affinity": affinity,
            "timer_probe": timer,
        },
        "paired_full_pipeline_ab": {
            "live_negative": negative_ab,
            "derived_positive": positive_ab,
        },
        "identity_lookup": identity_probe,
        "cache_info": cache_info,
        "semantic_equivalence": {
            "complete_128_case_canonical_certificate_bytes_exact": True,
            "bridge_semantic_digest_unchanged": True,
        },
        "measurement_validity": {
            "network_closed_before_timing": True,
            "same_process_same_contract_same_corpus_paired_ab": True,
            "deterministic_randomized_interleaving": True,
            "fixed_speed_promotion_threshold": False,
        },
        "policy_boundary": {
            "execution_policy": "NOT_IMPLEMENTED",
            "selective_reuse_intervention": "NOT_IMPLEMENTED",
            "further_optimization": "NOT_IMPLEMENTED",
        },
        "promotion_pass": promotion_pass,
        "verdict": "PASS" if promotion_pass else "FAIL",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "verdict": result["verdict"],
        "promotion_pass": promotion_pass,
        "broker": broker_version,
        "contract": contract_fp,
        "negative_legacy_p50_us": negative_ab["legacy_recompute"]["p50_us"],
        "negative_optimized_p50_us": negative_ab["optimized_cached"]["p50_us"],
        "positive_legacy_p50_us": positive_ab["legacy_recompute"]["p50_us"],
        "positive_optimized_p50_us": positive_ab["optimized_cached"]["p50_us"],
        "cache": cache_info,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
