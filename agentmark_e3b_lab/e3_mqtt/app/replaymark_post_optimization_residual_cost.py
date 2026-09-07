from __future__ import annotations

"""Post-optimization residual cost profile for the frozen E3b runtime path.

This module is measurement-only. It does not change ReplayMark semantics or
execution. A real Mosquitto run first materializes the frozen R1 corpus; the
network harness is then closed before any timed residual profiling begins.

Two complementary views are produced:
1. exact uninstrumented production-path timings; and
2. call-traced additive decomposition of the same production path.

The traced view distinguishes the bridge's direct adjudication from the second
adjudication performed inside ExplicitCompiledContract.certify_reuse().
Instrumentation inflation is reported explicitly, so traced absolute numbers are
used for structural attribution rather than substituted for the uninstrumented
production latency.
"""

import argparse
from contextlib import AbstractContextManager
import gc
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import time
from typing import Any, Callable

import replaymark.runtime_e3b_bridge as bridge_mod
import replaymark.runtime_e3b_correlation as correlation_mod
from replaymark.compiled_contract import ExplicitCompiledContract
from replaymark.rstar import maximal_certified_reuse
from replaymark.runtime_contract_identity import (
    runtime_contract_identity_cache_info,
    verified_runtime_contract_identity,
)
from replaymark.runtime_e3b_bridge import (
    E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST,
    E3B_SHADOW_RUNTIME_CERTIFICATE_SCHEMA,
    E3B_SHADOW_BRIDGE_ID,
    E3bShadowRuntimeReuseCertificate,
)
from replaymark.runtime_realization import RuntimeReuseCertificate
from replaymark_verification.runtime_cost_measurement import (
    run_interleaved,
    summarize_ns,
    summary_is_ordered,
    timer_probe,
)

from replaymark_runtime_cost import (
    CostCase,
    _build_cases,
    _collect_live_materials,
    _cpu_model,
    _pin_single_cpu,
)
from replaymark_shadow import compile_e3b_r1_shadow_contract


SCHEMA = "replaymark.runtime-post-optimization-residual-cost-profile.v1"
_RUNTIME_REUSE_CERTIFICATE_SCHEMA = "replaymark.runtime.reuse-certificate.v1"


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _case_digest(cases: list[CostCase]) -> str:
    return _sha256_json(
        [
            {
                "provenance": case.provenance,
                "task_id": case.task_id,
                "raw_observation": case.raw_observation,
                "raw_action": case.raw_action,
            }
            for case in cases
        ]
    )


def _semantic_digest(cases: list[CostCase]) -> str:
    return _sha256_json(
        [
            {
                "provenance": case.provenance,
                "task_id": case.task_id,
                "certificate_sha256": hashlib.sha256(case.certificate_bytes).hexdigest(),
            }
            for case in cases
        ]
    )


def _runtime_certificate_from_case(
    case: CostCase,
    *,
    contract_fingerprint: str,
    claim_fingerprint: str,
) -> RuntimeReuseCertificate:
    return RuntimeReuseCertificate(
        schema_version=_RUNTIME_REUSE_CERTIFICATE_SCHEMA,
        contract_fingerprint=contract_fingerprint,
        claim_fingerprint=claim_fingerprint,
        observation=case.pair.observation,
        historical_action=case.pair.historical_action,
        adjudication=case.adjudication,
        reuse_decision=case.reuse_decision,
    )


def _wrapper_certificate_from_case(
    case: CostCase,
    *,
    contract_fingerprint: str,
    claim_fingerprint: str,
) -> E3bShadowRuntimeReuseCertificate:
    return E3bShadowRuntimeReuseCertificate(
        schema_version=E3B_SHADOW_RUNTIME_CERTIFICATE_SCHEMA,
        bridge_id=E3B_SHADOW_BRIDGE_ID,
        bridge_semantic_digest=E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST,
        contract_fingerprint=contract_fingerprint,
        claim_fingerprint=claim_fingerprint,
        correlated_pair=case.pair,
        semantic_certificate=case.certificate.semantic_certificate,
    )


def _uninstrumented_functions(
    cases: list[CostCase],
    contract: ExplicitCompiledContract,
) -> dict[str, Callable[[int], Any]]:
    identity = verified_runtime_contract_identity(contract)
    contract_fp = identity.contract_fingerprint
    claim_fp = identity.claim_fingerprint

    def full_pipeline(index: int):
        case = cases[index]
        pair = correlation_mod.correlate_e3b_runtime_pair(
            case.raw_observation, case.raw_action
        )
        return bridge_mod.certify_e3b_shadow_reuse(contract, pair)

    def correlation_total(index: int):
        case = cases[index]
        return correlation_mod.correlate_e3b_runtime_pair(
            case.raw_observation, case.raw_action
        )

    def bridge_hot(index: int):
        return bridge_mod.certify_e3b_shadow_reuse(contract, cases[index].pair)

    def observation_realization(index: int):
        return correlation_mod.realize_e3b_observation(cases[index].raw_observation)

    def action_realization(index: int):
        return correlation_mod.realize_e3b_historical_action(cases[index].raw_action)

    def observation_parse(index: int):
        return correlation_mod.parse_e3b_observation_record(cases[index].raw_observation)

    def action_parse(index: int):
        return correlation_mod.parse_e3b_historical_action_record(cases[index].raw_action)

    def realized_observation_fingerprint(index: int):
        return cases[index].pair.observation.fingerprint()

    def realized_action_fingerprint(index: int):
        return cases[index].pair.historical_action.fingerprint()

    def identity_hot(_index: int):
        return verified_runtime_contract_identity(contract)

    def adjudicate(index: int):
        case = cases[index]
        return contract.adjudicate(
            case.pair.observation.evidence_token,
            case.pair.historical_action.action,
        )

    def certify_reuse_total(index: int):
        case = cases[index]
        return contract.certify_reuse(
            case.pair.observation.evidence_token,
            case.pair.historical_action.action,
        )

    def rstar_precomputed(index: int):
        return maximal_certified_reuse(cases[index].adjudication)

    def runtime_certificate_ctor(index: int):
        return _runtime_certificate_from_case(
            cases[index],
            contract_fingerprint=contract_fp,
            claim_fingerprint=claim_fp,
        )

    def wrapper_certificate_ctor(index: int):
        return _wrapper_certificate_from_case(
            cases[index],
            contract_fingerprint=contract_fp,
            claim_fingerprint=claim_fp,
        )

    def certificate_canonical_bytes(index: int):
        return cases[index].certificate.canonical_bytes()

    def certificate_fingerprint(index: int):
        return cases[index].certificate.fingerprint()

    return {
        "full_pipeline_object": full_pipeline,
        "correlation_total": correlation_total,
        "bridge_hot_total": bridge_hot,
        "observation_realization": observation_realization,
        "historical_action_realization": action_realization,
        "observation_parse": observation_parse,
        "historical_action_parse": action_parse,
        "realized_observation_fingerprint": realized_observation_fingerprint,
        "realized_action_fingerprint": realized_action_fingerprint,
        "identity_hot_lookup": identity_hot,
        "adjudication": adjudicate,
        "certify_reuse_total": certify_reuse_total,
        "rstar_from_precomputed_adjudication": rstar_precomputed,
        "runtime_certificate_constructor": runtime_certificate_ctor,
        "e3b_wrapper_certificate_constructor": wrapper_certificate_ctor,
        "certificate_canonical_bytes_not_in_object_path": certificate_canonical_bytes,
        "certificate_fingerprint_not_in_object_path": certificate_fingerprint,
    }


class _PhaseTracer(AbstractContextManager["_PhaseTracer"]):
    """Temporarily time exact call boundaries used by the production path."""

    def __init__(self) -> None:
        self.active = False
        self.frame: dict[str, float] | None = None
        self.sequence: list[str] = []
        self._certify_depth = 0
        self._saved: list[tuple[object, str, object]] = []

    def _record(self, label: str, elapsed_ns: int) -> None:
        if not self.active or self.frame is None:
            return
        self.frame[label] = self.frame.get(label, 0.0) + float(elapsed_ns)
        self.sequence.append(label)

    def _patch(self, owner: object, name: str, replacement: object) -> None:
        original = getattr(owner, name)
        self._saved.append((owner, name, original))
        setattr(owner, name, replacement)

    def __enter__(self) -> "_PhaseTracer":
        original_obs = correlation_mod.realize_e3b_observation
        original_action = correlation_mod.realize_e3b_historical_action
        original_identity = bridge_mod.verified_runtime_contract_identity
        original_adjudicate = ExplicitCompiledContract.adjudicate
        original_certify = ExplicitCompiledContract.certify_reuse
        original_runtime_init = RuntimeReuseCertificate.__init__
        original_wrapper_init = E3bShadowRuntimeReuseCertificate.__init__

        def timed_obs(*args: object, **kwargs: object):
            start = time.perf_counter_ns()
            try:
                return original_obs(*args, **kwargs)
            finally:
                self._record(
                    "observation_realization",
                    time.perf_counter_ns() - start,
                )

        def timed_action(*args: object, **kwargs: object):
            start = time.perf_counter_ns()
            try:
                return original_action(*args, **kwargs)
            finally:
                self._record(
                    "historical_action_realization",
                    time.perf_counter_ns() - start,
                )

        def timed_identity(*args: object, **kwargs: object):
            start = time.perf_counter_ns()
            try:
                return original_identity(*args, **kwargs)
            finally:
                self._record("identity_hot_lookup", time.perf_counter_ns() - start)

        def timed_adjudicate(
            contract: ExplicitCompiledContract,
            observation_token: str,
            historical_action: object,
        ):
            label = (
                "adjudication_nested_in_certify_reuse"
                if self._certify_depth
                else "adjudication_primary"
            )
            start = time.perf_counter_ns()
            try:
                return original_adjudicate(
                    contract,
                    observation_token,
                    historical_action,
                )
            finally:
                self._record(label, time.perf_counter_ns() - start)

        def timed_certify(
            contract: ExplicitCompiledContract,
            observation_token: str,
            historical_action: object,
        ):
            start = time.perf_counter_ns()
            self._certify_depth += 1
            try:
                return original_certify(
                    contract,
                    observation_token,
                    historical_action,
                )
            finally:
                self._certify_depth -= 1
                self._record("certify_reuse_total", time.perf_counter_ns() - start)

        def timed_runtime_init(instance: object, *args: object, **kwargs: object) -> None:
            start = time.perf_counter_ns()
            try:
                original_runtime_init(instance, *args, **kwargs)
            finally:
                self._record(
                    "runtime_certificate_constructor",
                    time.perf_counter_ns() - start,
                )

        def timed_wrapper_init(instance: object, *args: object, **kwargs: object) -> None:
            start = time.perf_counter_ns()
            try:
                original_wrapper_init(instance, *args, **kwargs)
            finally:
                self._record(
                    "e3b_wrapper_certificate_constructor",
                    time.perf_counter_ns() - start,
                )

        self._patch(correlation_mod, "realize_e3b_observation", timed_obs)
        self._patch(correlation_mod, "realize_e3b_historical_action", timed_action)
        self._patch(bridge_mod, "verified_runtime_contract_identity", timed_identity)
        self._patch(ExplicitCompiledContract, "adjudicate", timed_adjudicate)
        self._patch(ExplicitCompiledContract, "certify_reuse", timed_certify)
        self._patch(RuntimeReuseCertificate, "__init__", timed_runtime_init)
        self._patch(E3bShadowRuntimeReuseCertificate, "__init__", timed_wrapper_init)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool | None:
        self.active = False
        self.frame = None
        for owner, name, original in reversed(self._saved):
            setattr(owner, name, original)
        self._saved.clear()
        return None

    def trace_case(
        self,
        case: CostCase,
        contract: ExplicitCompiledContract,
    ) -> tuple[dict[str, float], E3bShadowRuntimeReuseCertificate]:
        self.frame = {}
        self.sequence = []
        self._certify_depth = 0
        self.active = True
        pipeline_start = time.perf_counter_ns()
        correlation_start = time.perf_counter_ns()
        pair = correlation_mod.correlate_e3b_runtime_pair(
            case.raw_observation,
            case.raw_action,
        )
        correlation_total = time.perf_counter_ns() - correlation_start

        bridge_start = time.perf_counter_ns()
        certificate = bridge_mod.certify_e3b_shadow_reuse(contract, pair)
        bridge_total = time.perf_counter_ns() - bridge_start
        pipeline_total = time.perf_counter_ns() - pipeline_start
        self.active = False

        frame = dict(self.frame)
        frame["correlation_total"] = float(correlation_total)
        frame["bridge_total"] = float(bridge_total)
        frame["pipeline_total"] = float(pipeline_total)
        frame["pipeline_orchestration_residual"] = float(
            pipeline_total - correlation_total - bridge_total
        )

        obs = frame.get("observation_realization", 0.0)
        action = frame.get("historical_action_realization", 0.0)
        frame["correlation_composition_exclusive"] = float(
            correlation_total - obs - action
        )

        nested = frame.get("adjudication_nested_in_certify_reuse", 0.0)
        certify_total = frame.get("certify_reuse_total", 0.0)
        frame["rstar_plus_certify_orchestration_exclusive"] = float(
            certify_total - nested
        )

        bridge_children = (
            frame.get("identity_hot_lookup", 0.0)
            + frame.get("adjudication_primary", 0.0)
            + certify_total
            + frame.get("runtime_certificate_constructor", 0.0)
            + frame.get("e3b_wrapper_certificate_constructor", 0.0)
        )
        frame["bridge_orchestration_exclusive"] = float(bridge_total - bridge_children)

        additive_labels = (
            "observation_realization",
            "historical_action_realization",
            "correlation_composition_exclusive",
            "identity_hot_lookup",
            "adjudication_primary",
            "adjudication_nested_in_certify_reuse",
            "rstar_plus_certify_orchestration_exclusive",
            "runtime_certificate_constructor",
            "e3b_wrapper_certificate_constructor",
            "bridge_orchestration_exclusive",
            "pipeline_orchestration_residual",
        )
        additive_sum = sum(frame.get(label, 0.0) for label in additive_labels)
        frame["additive_phase_sum"] = float(additive_sum)
        frame["closure_error"] = float(pipeline_total - additive_sum)

        if certificate.canonical_bytes() != case.certificate_bytes:
            raise AssertionError("traced production path changed certificate bytes")
        required = {
            "observation_realization",
            "historical_action_realization",
            "identity_hot_lookup",
            "adjudication_primary",
            "adjudication_nested_in_certify_reuse",
            "certify_reuse_total",
            "runtime_certificate_constructor",
            "e3b_wrapper_certificate_constructor",
        }
        if not required.issubset(frame):
            missing = sorted(required.difference(frame))
            raise AssertionError(f"traced production path missed phases: {missing}")
        return frame, certificate


ADDITIVE_PHASES = (
    "observation_realization",
    "historical_action_realization",
    "correlation_composition_exclusive",
    "identity_hot_lookup",
    "adjudication_primary",
    "adjudication_nested_in_certify_reuse",
    "rstar_plus_certify_orchestration_exclusive",
    "runtime_certificate_constructor",
    "e3b_wrapper_certificate_constructor",
    "bridge_orchestration_exclusive",
    "pipeline_orchestration_residual",
)


def _trace_profile(
    cases: list[CostCase],
    contract: ExplicitCompiledContract,
    *,
    repeats: int,
    seed: int,
) -> dict[str, object]:
    if repeats < 4:
        raise ValueError("trace profile requires at least four corpus repeats")
    verified_runtime_contract_identity(contract)

    samples: dict[str, list[float]] = {
        label: [] for label in (
            *ADDITIVE_PHASES,
            "correlation_total",
            "bridge_total",
            "pipeline_total",
            "additive_phase_sum",
            "closure_error",
            "certify_reuse_total",
        )
    }
    sequence_digests: set[str] = set()
    rng = random.Random(seed)
    order = list(range(len(cases)))

    with _PhaseTracer() as tracer:
        for _warmup in range(2):
            for index in order:
                tracer.trace_case(cases[index], contract)

        gc_was_enabled = gc.isenabled()
        gc.disable()
        try:
            for _repeat in range(repeats):
                rng.shuffle(order)
                for index in order:
                    frame, _certificate = tracer.trace_case(cases[index], contract)
                    for label in samples:
                        samples[label].append(float(frame[label]))
                    sequence_digests.add(
                        hashlib.sha256(
                            "|".join(tracer.sequence).encode("utf-8")
                        ).hexdigest()
                    )
        finally:
            if gc_was_enabled:
                gc.enable()

    summaries = {label: summarize_ns(values) for label, values in samples.items()}
    pipeline_p50 = float(summaries["pipeline_total"]["p50_ns"])
    ranking = []
    for label in ADDITIVE_PHASES:
        p50 = float(summaries[label]["p50_ns"])
        ranking.append(
            {
                "phase": label,
                "p50_ns": p50,
                "p50_us": p50 / 1000.0,
                "p50_share_of_traced_pipeline": p50 / pipeline_p50,
            }
        )
    ranking.sort(key=lambda row: float(row["p50_ns"]), reverse=True)

    max_abs_closure = max(abs(value) for value in samples["closure_error"])
    negative_exclusive_counts = {
        label: sum(1 for value in samples[label] if value < 0.0)
        for label in ADDITIVE_PHASES
    }
    return {
        "samples": len(samples["pipeline_total"]),
        "phase_summaries": summaries,
        "additive_phase_ranking": ranking,
        "sequence_digest_count": len(sequence_digests),
        "sequence_sha256": sorted(sequence_digests),
        "phase_conservation": {
            "max_abs_closure_error_ns": max_abs_closure,
            "negative_exclusive_counts": negative_exclusive_counts,
            "definition": "pipeline_total == sum(exclusive additive phases) + closure_error",
        },
    }


def _crosscheck_diagnostics(
    uninstrumented: dict[str, dict[str, float | int]],
    traced: dict[str, object],
) -> dict[str, object]:
    phases = traced["phase_summaries"]
    traced_pipeline = float(phases["pipeline_total"]["p50_ns"])
    uninstrumented_pipeline = float(uninstrumented["full_pipeline_object"]["p50_ns"])
    correlation_share = float(phases["correlation_total"]["p50_ns"]) / traced_pipeline
    bridge_share = float(phases["bridge_total"]["p50_ns"]) / traced_pipeline

    primary = float(phases["adjudication_primary"]["p50_ns"])
    nested = float(phases["adjudication_nested_in_certify_reuse"]["p50_ns"])
    ctor_sum = (
        float(phases["runtime_certificate_constructor"]["p50_ns"])
        + float(phases["e3b_wrapper_certificate_constructor"]["p50_ns"])
    )
    return {
        "instrumentation_inflation_ratio_p50": traced_pipeline / uninstrumented_pipeline,
        "uninstrumented_full_pipeline_p50_us": uninstrumented_pipeline / 1000.0,
        "traced_full_pipeline_p50_us": traced_pipeline / 1000.0,
        "traced_correlation_total_share": correlation_share,
        "traced_bridge_total_share": bridge_share,
        "duplicate_adjudication": {
            "production_path_contains_two_adjudications": True,
            "primary_p50_us": primary / 1000.0,
            "nested_p50_us": nested / 1000.0,
            "combined_p50_us_descriptive": (primary + nested) / 1000.0,
            "note": "combined medians are descriptive; per-call additive samples are preserved in traced phase summaries",
        },
        "certificate_object_construction": {
            "runtime_plus_e3b_wrapper_p50_us_descriptive": ctor_sum / 1000.0,
            "serialization_is_outside_0_45ms_object_path": True,
        },
        "correlation_crosscheck": {
            "uninstrumented_correlation_total_p50_us": float(
                uninstrumented["correlation_total"]["p50_us"]
            ),
            "uninstrumented_observation_realization_p50_us": float(
                uninstrumented["observation_realization"]["p50_us"]
            ),
            "uninstrumented_historical_action_realization_p50_us": float(
                uninstrumented["historical_action_realization"]["p50_us"]
            ),
            "uninstrumented_observation_parse_p50_us": float(
                uninstrumented["observation_parse"]["p50_us"]
            ),
            "uninstrumented_historical_action_parse_p50_us": float(
                uninstrumented["historical_action_parse"]["p50_us"]
            ),
        },
        "bridge_crosscheck": {
            "uninstrumented_bridge_hot_p50_us": float(
                uninstrumented["bridge_hot_total"]["p50_us"]
            ),
            "uninstrumented_identity_hot_p50_us": float(
                uninstrumented["identity_hot_lookup"]["p50_us"]
            ),
            "uninstrumented_adjudication_p50_us": float(
                uninstrumented["adjudication"]["p50_us"]
            ),
            "uninstrumented_certify_reuse_total_p50_us": float(
                uninstrumented["certify_reuse_total"]["p50_us"]
            ),
            "uninstrumented_rstar_precomputed_p50_us": float(
                uninstrumented["rstar_from_precomputed_adjudication"]["p50_us"]
            ),
            "uninstrumented_runtime_certificate_ctor_p50_us": float(
                uninstrumented["runtime_certificate_constructor"]["p50_us"]
            ),
            "uninstrumented_e3b_wrapper_ctor_p50_us": float(
                uninstrumented["e3b_wrapper_certificate_constructor"]["p50_us"]
            ),
        },
        "downstream_not_in_object_path": {
            "certificate_canonical_bytes_p50_us": float(
                uninstrumented["certificate_canonical_bytes_not_in_object_path"][
                    "p50_us"
                ]
            ),
            "certificate_fingerprint_p50_us": float(
                uninstrumented["certificate_fingerprint_not_in_object_path"]["p50_us"]
            ),
        },
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
    parser.add_argument("--trace-repeats", type=int, default=10)
    parser.add_argument("--authority-head", required=True)
    parser.add_argument(
        "--out",
        default="/results/e3b_post_optimization_residual_cost_profile.json",
    )
    args = parser.parse_args()

    if args.tasks != 64:
        raise ValueError("residual profile uses exactly 64 live tasks")
    if args.tasks % args.wave_size:
        raise ValueError("tasks must be divisible by wave size")

    contract = compile_e3b_r1_shadow_contract()
    contract_identity = verified_runtime_contract_identity(contract)
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
    mixed = [*negative, *positive]
    corpus_digest = _case_digest(mixed)
    semantic_before = _semantic_digest(mixed)

    for case in mixed:
        pair = correlation_mod.correlate_e3b_runtime_pair(
            case.raw_observation, case.raw_action
        )
        certificate = bridge_mod.certify_e3b_shadow_reuse(contract, pair)
        if certificate.canonical_bytes() != case.certificate_bytes:
            raise AssertionError("pre-profile production certificate drift")

    affinity = _pin_single_cpu()
    clock_info = time.get_clock_info("perf_counter")
    timer = timer_probe()

    uninstrumented: dict[str, object] = {}
    traced: dict[str, object] = {}
    diagnostics: dict[str, object] = {}
    for label, cases, seed in (
        ("live_negative", negative, 20260911),
        ("derived_positive", positive, 20260912),
    ):
        exact = run_interleaved(
            _uninstrumented_functions(cases, contract),
            case_count=len(cases),
            rounds=args.rounds,
            inner=args.inner,
            warmup_rounds=20,
            seed=seed,
        )
        trace = _trace_profile(
            cases,
            contract,
            repeats=args.trace_repeats,
            seed=seed + 100,
        )
        if not all(summary_is_ordered(summary) for summary in exact.values()):
            raise AssertionError(f"{label} uninstrumented percentile ordering failed")
        if not all(
            summary_is_ordered(summary)
            for summary in trace["phase_summaries"].values()
        ):
            raise AssertionError(f"{label} traced percentile ordering failed")
        uninstrumented[label] = exact
        traced[label] = trace
        diagnostics[label] = _crosscheck_diagnostics(exact, trace)

    semantic_after_cases: list[dict[str, object]] = []
    for case in mixed:
        pair = correlation_mod.correlate_e3b_runtime_pair(
            case.raw_observation, case.raw_action
        )
        cert = bridge_mod.certify_e3b_shadow_reuse(contract, pair)
        semantic_after_cases.append(
            {
                "provenance": case.provenance,
                "task_id": case.task_id,
                "certificate_sha256": hashlib.sha256(cert.canonical_bytes()).hexdigest(),
            }
        )
    semantic_after = _sha256_json(semantic_after_cases)
    semantic_stable = semantic_before == semantic_after

    cache_info = runtime_contract_identity_cache_info()
    all_trace_closure_exact = all(
        float(traced[label]["phase_conservation"]["max_abs_closure_error_ns"]) <= 0.0
        for label in traced
    )
    all_trace_exclusive_nonnegative = all(
        all(
            int(count) == 0
            for count in traced[label]["phase_conservation"][
                "negative_exclusive_counts"
            ].values()
        )
        for label in traced
    )

    promotion_pass = (
        broker_version == "mosquitto version 2.1.2"
        and len(negative) == 64
        and len(positive) == 64
        and semantic_stable
        and all_trace_closure_exact
        and all_trace_exclusive_nonnegative
        and int(cache_info["size"]) <= int(cache_info["capacity"])
        and all(
            int(summary["samples"]) == args.rounds
            for outcome in uninstrumented.values()
            for summary in outcome.values()
        )
    )

    result = {
        "schema": SCHEMA,
        "authority_head": args.authority_head,
        "broker_version_sys": broker_version,
        "frozen_authorities": {
            "contract_fingerprint": contract_identity.contract_fingerprint,
            "claim_fingerprint": contract_identity.claim_fingerprint,
            "bridge_semantic_digest": E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST,
            "optimization_parent": "5d9bbdc87bf926359f83457a0c8057676a4e5b65",
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
            "perf_counter_resolution_ns": clock_info.resolution * 1e9,
            "timer_probe": timer,
        },
        "exact_uninstrumented_production_path": uninstrumented,
        "call_traced_additive_decomposition": traced,
        "triangulated_diagnostics": diagnostics,
        "semantic_identity": {
            "before_profile_sha256": semantic_before,
            "after_profile_sha256": semantic_after,
            "stable": semantic_stable,
        },
        "cache_info": cache_info,
        "measurement_validity": {
            "network_closed_before_timing": True,
            "same_process_same_contract_same_corpus": True,
            "single_cpu_pin_attempted": True,
            "stage_order_randomized_deterministically": True,
            "gc_disabled_inside_hot_loops": True,
            "call_tracing_uses_exact_production_functions": True,
            "trace_instrumentation_inflation_reported_not_hidden": True,
            "additive_phase_conservation_exact": all_trace_closure_exact,
            "exclusive_phase_nonnegative": all_trace_exclusive_nonnegative,
            "fixed_speed_promotion_threshold": False,
            "optimization_performed": False,
        },
        "policy_boundary": {
            "execution_policy": "NOT_IMPLEMENTED",
            "selective_reuse_intervention": "NOT_IMPLEMENTED",
            "new_optimization": "NOT_IMPLEMENTED",
            "profile_numbers_are_descriptive_not_promotion_thresholds": True,
        },
        "promotion_pass": promotion_pass,
        "verdict": "PASS" if promotion_pass else "FAIL",
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    summary = {
        "verdict": result["verdict"],
        "promotion_pass": promotion_pass,
        "broker": broker_version,
        "contract": contract_identity.contract_fingerprint,
    }
    for label in ("live_negative", "derived_positive"):
        exact = uninstrumented[label]
        trace = traced[label]
        summary[label] = {
            "full_pipeline_p50_us": exact["full_pipeline_object"]["p50_us"],
            "correlation_p50_us": exact["correlation_total"]["p50_us"],
            "bridge_hot_p50_us": exact["bridge_hot_total"]["p50_us"],
            "traced_top_phases": trace["additive_phase_ranking"][:5],
            "instrumentation_inflation_ratio_p50": diagnostics[label][
                "instrumentation_inflation_ratio_p50"
            ],
            "duplicate_adjudication": diagnostics[label]["duplicate_adjudication"],
            "certificate_object_construction": diagnostics[label][
                "certificate_object_construction"
            ],
        }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
