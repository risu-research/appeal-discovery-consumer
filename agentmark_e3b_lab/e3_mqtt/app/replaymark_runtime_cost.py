from __future__ import annotations

"""Empirical Runtime Cost Characterization for the frozen E3b R1 shadow path.

Measurement is deliberately separated from network execution. A live Mosquitto
run first materializes a frozen R1 corpus; the Harness is then closed before any
timed semantic stage begins.
"""

import argparse
from dataclasses import dataclass
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import threading
import time
import uuid

from experiment import Harness
import ladder

from replaymark.compiled_contract import ExplicitCompiledContract
from replaymark.rstar import maximal_certified_reuse
from replaymark.runtime_e3b_action import realize_e3b_historical_action
from replaymark.runtime_e3b_bridge import (
    E3B_SHADOW_BRIDGE_ID,
    E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST,
    E3B_SHADOW_RUNTIME_CERTIFICATE_SCHEMA,
    E3bShadowRuntimeReuseCertificate,
    certify_e3b_shadow_reuse,
)
from replaymark.runtime_e3b_correlation import correlate_e3b_runtime_pair
from replaymark.runtime_e3b_observation import realize_e3b_observation
from replaymark.runtime_realization import RuntimeReuseCertificate
from replaymark_oracle.e3b_integrated_runtime_oracle import integrated_expectation
from replaymark_verification.runtime_cost_measurement import (
    linear_fit,
    run_interleaved,
    summarize_ns,
    summary_is_ordered,
    timer_probe,
)
from replaymark_shadow import (
    _ClientProxy,
    _TimeProxy,
    ShadowTaskMaterial,
    compile_e3b_r1_shadow_contract,
    run_r1_shadow_condition,
)


SCHEMA = "replaymark.runtime-e3b-cost-characterization.v1"


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


def _cpu_model() -> str | None:
    path = Path("/proc/cpuinfo")
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.lower().startswith("model name") and ":" in line:
            return line.split(":", 1)[1].strip()
    return None


def _pin_single_cpu() -> dict[str, object]:
    if not hasattr(os, "sched_getaffinity") or not hasattr(os, "sched_setaffinity"):
        return {"supported": False, "pinned": False}
    before = sorted(os.sched_getaffinity(0))
    if not before:
        return {"supported": True, "pinned": False, "before": before}
    selected = before[0]
    try:
        os.sched_setaffinity(0, {selected})
    except OSError as exc:
        return {
            "supported": True,
            "pinned": False,
            "before": before,
            "error": str(exc),
        }
    after = sorted(os.sched_getaffinity(0))
    return {
        "supported": True,
        "pinned": after == [selected],
        "before": before,
        "after": after,
        "selected_cpu": selected,
    }


def _collect_live_materials(
    contract: ExplicitCompiledContract,
    *,
    broker: str,
    port: int,
    tasks: int,
    wave_size: int,
    wave_period_ms: float,
    verify_floor_ms: float,
    source_guard_ms: float,
    changed_delay_floor_ms: float,
    target_margin_ms: float,
    post_completion_gap_ms: float,
    task_timeout_ms: int,
) -> tuple[str | None, float, float, tuple[ShadowTaskMaterial, ...]]:
    harness = Harness(broker, port)
    try:
        version = harness.broker_version()
        harness.set_state_delay(0)
        source_prefix = f"cost-source-{uuid.uuid4().hex[:6]}"
        traces = ladder.offers(
            tasks,
            wave_size,
            wave_period_ms,
            lambda i, offer: ladder.source_task(
                harness,
                i,
                source_prefix,
                offer,
                post_completion_gap_ms,
                task_timeout_ms,
            ),
        )
        source_first = [float(row["first_completion_offset_ms"]) for row in traces]
        source_max = max(source_first)
        verify_ms = max(
            float(verify_floor_ms),
            float(math.ceil(source_max + source_guard_ms)),
        )
        target_delay_ms = max(
            float(changed_delay_floor_ms),
            verify_ms + target_margin_ms,
        )
        if target_delay_ms >= task_timeout_ms:
            raise RuntimeError("calibrated target delay collides with task timeout")

        harness.set_state_delay(target_delay_ms)
        prefix = f"cost-live-{uuid.uuid4().hex[:6]}"
        shadow = run_r1_shadow_condition(
            harness,
            traces,
            wave_size,
            wave_period_ms,
            prefix,
            verify_ms,
            post_completion_gap_ms,
            task_timeout_ms,
            contract,
        )
        if len(shadow.task_material) != tasks:
            raise AssertionError("live cost corpus is incomplete")
        if shadow.captured_publish_count != 2 * tasks:
            raise AssertionError("live cost corpus capture count is not two publishes/task")
        if [item.task_id for item in shadow.task_material] != list(range(tasks)):
            raise AssertionError("live cost corpus task IDs are not canonical")
        return version, verify_ms, target_delay_ms, shadow.task_material
    finally:
        harness.close()


@dataclass(frozen=True)
class CostCase:
    provenance: str
    task_id: int
    raw_observation: dict[str, object]
    raw_action: dict[str, object]
    pair: object
    adjudication: object
    reuse_decision: object
    certificate: E3bShadowRuntimeReuseCertificate
    certificate_bytes: bytes


def _make_case(
    *,
    provenance: str,
    task_id: int,
    raw_observation: dict[str, object],
    raw_action: dict[str, object],
    contract: ExplicitCompiledContract,
    expected_certificate: E3bShadowRuntimeReuseCertificate | None = None,
) -> CostCase:
    pair = correlate_e3b_runtime_pair(raw_observation, raw_action)
    certificate = certify_e3b_shadow_reuse(contract, pair)
    if (
        expected_certificate is not None
        and certificate.canonical_bytes() != expected_certificate.canonical_bytes()
    ):
        raise AssertionError("recomputed live certificate differs from frozen shadow output")
    adjudication = contract.adjudicate(
        pair.observation.evidence_token,
        pair.historical_action.action,
    )
    reuse = maximal_certified_reuse(adjudication)
    semantic = certificate.semantic_certificate
    if adjudication.canonical_bytes() != semantic.adjudication.canonical_bytes():
        raise AssertionError("precomputed adjudication differs from bridge result")
    if reuse.canonical_bytes() != semantic.reuse_decision.canonical_bytes():
        raise AssertionError("precomputed R* result differs from bridge result")
    return CostCase(
        provenance=provenance,
        task_id=task_id,
        raw_observation=raw_observation,
        raw_action=raw_action,
        pair=pair,
        adjudication=adjudication,
        reuse_decision=reuse,
        certificate=certificate,
        certificate_bytes=certificate.canonical_bytes(),
    )


def _derive_positive_observation(
    raw_observation: dict[str, object],
    *,
    task_id: int,
) -> dict[str, object]:
    out = dict(raw_observation)
    events = [dict(event) for event in raw_observation["events"]]
    command = int(raw_observation["command_publish_mono_ns"])
    deadline = int(raw_observation["verify_deadline_mono_ns"])
    if deadline <= command:
        raise AssertionError("frozen observation boundary is not positive-width")
    events.append(
        {
            "event_id": f"cost-positive:{task_id}",
            "device": raw_observation["expected_device"],
            "on": True,
            "recv_mono_ns": command + max(1, (deadline - command) // 2),
            "clock_domain": raw_observation["clock_domain"],
        }
    )
    out["events"] = events
    return out


def _build_cases(
    materials: tuple[ShadowTaskMaterial, ...],
    contract: ExplicitCompiledContract,
) -> tuple[list[CostCase], list[CostCase]]:
    negative: list[CostCase] = []
    positive: list[CostCase] = []
    for item in materials:
        neg = _make_case(
            provenance="live_negative",
            task_id=item.task_id,
            raw_observation=dict(item.raw_observation),
            raw_action=dict(item.raw_historical_action),
            contract=contract,
            expected_certificate=item.certificate,
        )
        neg_expectation = integrated_expectation(neg.raw_observation, neg.raw_action)
        if (
            neg_expectation.observation_token != "not_visible_by_deadline"
            or neg_expectation.verdict != "INVALID"
            or neg_expectation.reuse_disposition != "DO_NOT_REUSE"
        ):
            raise AssertionError("live cost corpus does not match independent negative oracle")
        negative.append(neg)

        pos_raw = _derive_positive_observation(
            neg.raw_observation,
            task_id=item.task_id,
        )
        pos = _make_case(
            provenance="derived_positive",
            task_id=item.task_id,
            raw_observation=pos_raw,
            raw_action=dict(neg.raw_action),
            contract=contract,
        )
        pos_expectation = integrated_expectation(pos.raw_observation, pos.raw_action)
        if (
            pos_expectation.observation_token != "confirmed_by_deadline"
            or pos_expectation.verdict != "VALID"
            or pos_expectation.reuse_disposition != "REUSE"
        ):
            raise AssertionError("derived positive corpus does not match independent oracle")
        positive.append(pos)
    return negative, positive


def _stage_functions(
    cases: list[CostCase],
    contract: ExplicitCompiledContract,
) -> dict[str, object]:
    contract_fp = contract.fingerprint()
    claim_fp = contract.claim_fingerprint

    def observation_realization(index: int):
        return realize_e3b_observation(cases[index].raw_observation)

    def historical_action_realization(index: int):
        return realize_e3b_historical_action(cases[index].raw_action)

    def correlate_api_total(index: int):
        return correlate_e3b_runtime_pair(
            cases[index].raw_observation,
            cases[index].raw_action,
        )

    def adjudicate(index: int):
        case = cases[index]
        return contract.adjudicate(
            case.pair.observation.evidence_token,
            case.pair.historical_action.action,
        )

    def rstar_from_adjudication(index: int):
        return maximal_certified_reuse(cases[index].adjudication)

    def certify_reuse_total(index: int):
        case = cases[index]
        return contract.certify_reuse(
            case.pair.observation.evidence_token,
            case.pair.historical_action.action,
        )

    def contract_fingerprint(_index: int):
        return contract.fingerprint()

    def claim_fingerprint(_index: int):
        return contract.claim_fingerprint

    def certificate_assembly(index: int):
        case = cases[index]
        semantic = RuntimeReuseCertificate(
            schema_version=case.certificate.semantic_certificate.schema_version,
            contract_fingerprint=contract_fp,
            claim_fingerprint=claim_fp,
            observation=case.pair.observation,
            historical_action=case.pair.historical_action,
            adjudication=case.adjudication,
            reuse_decision=case.reuse_decision,
        )
        return E3bShadowRuntimeReuseCertificate(
            schema_version=E3B_SHADOW_RUNTIME_CERTIFICATE_SCHEMA,
            bridge_id=E3B_SHADOW_BRIDGE_ID,
            bridge_semantic_digest=E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST,
            contract_fingerprint=contract_fp,
            claim_fingerprint=claim_fp,
            correlated_pair=case.pair,
            semantic_certificate=semantic,
        )

    def certificate_serialization(index: int):
        return cases[index].certificate.canonical_bytes()

    def certificate_hash_only(index: int):
        return hashlib.sha256(cases[index].certificate_bytes).hexdigest()

    def certificate_fingerprint_total(index: int):
        return cases[index].certificate.fingerprint()

    def bridge_total(index: int):
        return certify_e3b_shadow_reuse(contract, cases[index].pair)

    def full_offline_pipeline(index: int):
        case = cases[index]
        pair = correlate_e3b_runtime_pair(case.raw_observation, case.raw_action)
        return certify_e3b_shadow_reuse(contract, pair)

    return {
        "observation_realization": observation_realization,
        "historical_action_realization": historical_action_realization,
        "correlate_api_total": correlate_api_total,
        "adjudicate": adjudicate,
        "rstar_from_adjudication": rstar_from_adjudication,
        "certify_reuse_total": certify_reuse_total,
        "contract_fingerprint": contract_fingerprint,
        "claim_fingerprint": claim_fingerprint,
        "certificate_assembly": certificate_assembly,
        "certificate_serialization": certificate_serialization,
        "certificate_hash_only": certificate_hash_only,
        "certificate_fingerprint_total": certificate_fingerprint_total,
        "bridge_total": bridge_total,
        "full_offline_pipeline": full_offline_pipeline,
    }


def _capture_microbench(*, rounds: int = 320, inner: int = 64) -> dict[str, object]:
    class FakeClient:
        def __init__(self):
            self.calls = 0

        def publish(self, *args: object, **kwargs: object):
            self.calls += 1
            return self.calls

    class FakeClock:
        def __init__(self):
            self.value = 1000

        def monotonic_ns(self) -> int:
            self.value += 1
            return self.value

    client = FakeClient()
    tls = threading.local()
    tls.task_t0_ns = 777
    records: list[object] = []
    proxy = _ClientProxy(client, tls, records)
    args = (
        "agentmark/cost-0-a/command",
        '{"on": true}',
        1,
        False,
        None,
    )
    rng = random.Random(20260907)
    direct_samples: list[float] = []
    captured_samples: list[float] = []
    delta_samples: list[float] = []

    for _ in range(24):
        for _inner in range(inner):
            client.publish(*args)
            proxy.publish(*args)
        records.clear()

    gc_was_enabled = gc.isenabled()
    gc.disable()
    try:
        for _round in range(rounds):
            order = ["direct", "captured"]
            rng.shuffle(order)
            elapsed: dict[str, float] = {}
            for label in order:
                if label == "captured":
                    records.clear()
                start = time.perf_counter_ns()
                if label == "direct":
                    for _inner in range(inner):
                        client.publish(*args)
                else:
                    for _inner in range(inner):
                        proxy.publish(*args)
                total = time.perf_counter_ns() - start
                elapsed[label] = float(total) / inner
                if label == "captured" and len(records) != inner:
                    raise AssertionError("exact ClientProxy did not capture one row per publish")
            direct_samples.append(elapsed["direct"])
            captured_samples.append(elapsed["captured"])
            delta_samples.append(elapsed["captured"] - elapsed["direct"])
    finally:
        if gc_was_enabled:
            gc.enable()

    clock = FakeClock()
    clock_tls = threading.local()
    time_proxy = _TimeProxy(clock, clock_tls)
    direct_clock: list[float] = []
    unarmed_clock: list[float] = []
    armed_total: list[float] = []
    for _ in range(rounds):
        start = time.perf_counter_ns()
        for _inner in range(inner):
            clock.monotonic_ns()
        direct_clock.append((time.perf_counter_ns() - start) / inner)

        start = time.perf_counter_ns()
        for _inner in range(inner):
            time_proxy.monotonic_ns()
        unarmed_clock.append((time.perf_counter_ns() - start) / inner)

        start = time.perf_counter_ns()
        for _inner in range(inner):
            clock_tls.capture_next_t0 = True
            time_proxy.monotonic_ns()
        armed_total.append((time.perf_counter_ns() - start) / inner)

    return {
        "scope": {
            "publish_path": "exact production _ClientProxy around no-I/O fake delegate",
            "time_path": "exact production _TimeProxy around deterministic fake clock",
            "broker_io_included": False,
            "publish_delta_is_paired_same_round": True,
            "armed_time_proxy_includes_flag_setup": True,
        },
        "publish_direct": summarize_ns(direct_samples),
        "publish_captured": summarize_ns(captured_samples),
        "publish_incremental_delta": summarize_ns(delta_samples),
        "time_direct": summarize_ns(direct_clock),
        "time_proxy_unarmed": summarize_ns(unarmed_clock),
        "time_proxy_armed_with_flag_setup": summarize_ns(armed_total),
    }


def _benchmark_contract_compile(
    expected_fingerprint: str,
    *,
    samples: int = 15,
) -> dict[str, object]:
    durations: list[float] = []
    for _ in range(samples):
        start = time.perf_counter_ns()
        compiled = compile_e3b_r1_shadow_contract()
        durations.append(float(time.perf_counter_ns() - start))
        if compiled.fingerprint() != expected_fingerprint:
            raise AssertionError("recompiled contract fingerprint drifted during setup benchmark")
    return {
        "classification": "one_time_pre_runtime_setup_not_per_task_cost",
        "summary": summarize_ns(durations),
    }


def _run_full_pipeline(
    case: CostCase,
    contract: ExplicitCompiledContract,
    *,
    fingerprint: bool,
) -> str:
    pair = correlate_e3b_runtime_pair(case.raw_observation, case.raw_action)
    certificate = certify_e3b_shadow_reuse(contract, pair)
    if fingerprint:
        return certificate.fingerprint()
    return certificate.semantic_certificate.reuse_decision.disposition.value


def _scaling(
    cases: list[CostCase],
    contract: ExplicitCompiledContract,
    *,
    counts: tuple[int, ...] = (1, 4, 8, 16, 32, 64),
    rounds: int = 40,
) -> dict[str, object]:
    if max(counts) > len(cases):
        raise ValueError("scaling corpus is too small")
    rng = random.Random(20260908)
    modes = ("certificate_object", "certificate_plus_fingerprint")
    per_mode: dict[str, list[dict[str, object]]] = {mode: [] for mode in modes}
    median_points: dict[str, list[tuple[float, float]]] = {mode: [] for mode in modes}

    for n in counts:
        subset = cases[:n]
        for mode in modes:
            for _warmup in range(3):
                for case in subset:
                    _run_full_pipeline(
                        case,
                        contract,
                        fingerprint=(mode == "certificate_plus_fingerprint"),
                    )

        mode_samples: dict[str, list[float]] = {mode: [] for mode in modes}
        gc_was_enabled = gc.isenabled()
        gc.disable()
        try:
            for _round in range(rounds):
                order = list(modes)
                rng.shuffle(order)
                for mode in order:
                    start = time.perf_counter_ns()
                    sink = None
                    for case in subset:
                        sink = _run_full_pipeline(
                            case,
                            contract,
                            fingerprint=(mode == "certificate_plus_fingerprint"),
                        )
                    elapsed = time.perf_counter_ns() - start
                    if sink is None:
                        raise AssertionError("scaling batch did not execute")
                    mode_samples[mode].append(float(elapsed))
        finally:
            if gc_was_enabled:
                gc.enable()

        for mode in modes:
            summary = summarize_ns(mode_samples[mode])
            p50 = float(summary["p50_ns"])
            row = {
                "tasks": n,
                "batch": summary,
                "p50_ns_per_task": p50 / n,
                "p50_us_per_task": p50 / n / 1000.0,
                "p50_throughput_tasks_per_s": n * 1e9 / p50,
            }
            per_mode[mode].append(row)
            median_points[mode].append((float(n), p50))

    return {
        mode: {
            "points": per_mode[mode],
            "median_linear_fit": linear_fit(median_points[mode]),
        }
        for mode in modes
    }


def _semantic_digest(cases: list[CostCase]) -> str:
    return _sha256_json(
        [
            {
                "provenance": case.provenance,
                "task_id": case.task_id,
                "certificate_fingerprint": case.certificate.fingerprint(),
            }
            for case in cases
        ]
    )


def _recompute_semantic_digest(
    cases: list[CostCase],
    contract: ExplicitCompiledContract,
) -> str:
    rows = []
    for case in cases:
        pair = correlate_e3b_runtime_pair(case.raw_observation, case.raw_action)
        certificate = certify_e3b_shadow_reuse(contract, pair)
        rows.append(
            {
                "provenance": case.provenance,
                "task_id": case.task_id,
                "certificate_fingerprint": certificate.fingerprint(),
            }
        )
    return _sha256_json(rows)


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
    parser.add_argument(
        "--out",
        default="/results/e3b_runtime_cost_characterization.json",
    )
    args = parser.parse_args()

    if args.tasks != 64:
        raise ValueError("frozen cost characterization uses exactly 64 live tasks")
    if args.tasks % args.wave_size:
        raise ValueError("tasks must be divisible by wave size")

    contract = compile_e3b_r1_shadow_contract()
    contract_fp = contract.fingerprint()
    claim_fp = contract.claim_fingerprint

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
    mixed: list[CostCase] = []
    for neg, pos in zip(negative, positive):
        mixed.extend((neg, pos))
    semantic_before = _semantic_digest(mixed)

    affinity = _pin_single_cpu()
    clock_info = time.get_clock_info("perf_counter")
    timer = timer_probe()

    compile_cost = _benchmark_contract_compile(contract_fp)

    negative_stages = run_interleaved(
        _stage_functions(negative, contract),
        case_count=len(negative),
        rounds=args.rounds,
        inner=args.inner,
        warmup_rounds=20,
        seed=20260907,
    )
    positive_stages = run_interleaved(
        _stage_functions(positive, contract),
        case_count=len(positive),
        rounds=args.rounds,
        inner=args.inner,
        warmup_rounds=20,
        seed=20260908,
    )

    capture = _capture_microbench()
    scaling = _scaling(mixed, contract)
    semantic_after = _recompute_semantic_digest(mixed, contract)
    semantic_stable = semantic_before == semantic_after
    if not semantic_stable:
        raise AssertionError("benchmark execution changed semantic certificate identity")

    for label, stages in (
        ("live_negative", negative_stages),
        ("derived_positive", positive_stages),
    ):
        if not all(summary_is_ordered(summary) for summary in stages.values()):
            raise AssertionError(f"{label} timing summary percentile ordering failed")
        if not all(int(summary["samples"]) == args.rounds for summary in stages.values()):
            raise AssertionError(f"{label} timing sample count is incomplete")

    derived_residuals = {}
    for label, stages in (
        ("live_negative", negative_stages),
        ("derived_positive", positive_stages),
    ):
        residual = (
            float(stages["correlate_api_total"]["p50_ns"])
            - float(stages["observation_realization"]["p50_ns"])
            - float(stages["historical_action_realization"]["p50_ns"])
        )
        derived_residuals[label] = {
            "correlation_composition_residual_p50_ns": residual,
            "method": (
                "correlate_api_total_p50 - observation_realization_p50 "
                "- historical_action_realization_p50"
            ),
            "status": "DESCRIPTIVE_DERIVED_ESTIMATE_NOT_A_PRODUCTION_SEAM",
        }

    fastest_stage_p50 = min(
        float(summary["p50_ns"])
        for stages in (negative_stages, positive_stages)
        for summary in stages.values()
    )
    timer_ratio = float(timer["p99_ns"]) / fastest_stage_p50

    measurement_validity = {
        "network_closed_before_timed_semantic_benchmark": True,
        "single_cpu_pin_attempted": True,
        "semantic_certificates_stable_before_after": semantic_stable,
        "negative_live_cases": len(negative),
        "positive_definition_derived_cases": len(positive),
        "stage_samples_per_outcome": args.rounds,
        "calls_per_stage_sample": args.inner,
        "stage_order_randomized_deterministically": True,
        "gc_disabled_inside_hot_timing_loops": True,
        "fixed_latency_promotion_threshold": False,
        "optimization_performed": False,
        "timer_p99_to_fastest_stage_p50_ratio": timer_ratio,
    }
    promotion_pass = (
        broker_version == "mosquitto version 2.1.2"
        and len(negative) == 64
        and len(positive) == 64
        and semantic_stable
        and all(summary_is_ordered(summary) for summary in negative_stages.values())
        and all(summary_is_ordered(summary) for summary in positive_stages.values())
    )

    result = {
        "schema": SCHEMA,
        "authority_head": args.authority_head,
        "broker_version_sys": broker_version,
        "frozen_authorities": {
            "contract_fingerprint": contract_fp,
            "claim_fingerprint": claim_fp,
        },
        "live_corpus": {
            "tasks": args.tasks,
            "verify_ms": verify_ms,
            "target_delay_ms": target_delay_ms,
            "negative_live_cases": len(negative),
            "positive_definition_derived_cases": len(positive),
            "positive_cases_are_not_live_empirical_outcomes": True,
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
        "online_capture_microcost": capture,
        "one_time_setup": {
            "contract_compile": compile_cost,
        },
        "offline_stage_latency": {
            "live_negative": negative_stages,
            "derived_positive": positive_stages,
            "correlation_residual_estimate": derived_residuals,
            "semantic_note": (
                "certify_reuse_total includes its own adjudication by frozen API; "
                "rstar_from_adjudication measures R* from a precomputed adjudication."
            ),
        },
        "task_count_scaling": scaling,
        "semantic_identity": {
            "before_benchmark_sha256": semantic_before,
            "after_benchmark_sha256": semantic_after,
            "stable": semantic_stable,
        },
        "measurement_validity": measurement_validity,
        "policy_boundary": {
            "execution_policy": "NOT_IMPLEMENTED",
            "selective_reuse_intervention": "NOT_IMPLEMENTED",
            "optimization": "NOT_IMPLEMENTED",
            "performance_numbers_are_descriptive_not_promotion_thresholds": True,
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
    print(
        json.dumps(
            {
                "verdict": result["verdict"],
                "promotion_pass": promotion_pass,
                "broker": broker_version,
                "contract": contract_fp,
                "negative_cases": len(negative),
                "positive_cases": len(positive),
                "negative_full_pipeline_p50_us": negative_stages[
                    "full_offline_pipeline"
                ]["p50_us"],
                "negative_full_pipeline_p99_us": negative_stages[
                    "full_offline_pipeline"
                ]["p99_us"],
                "positive_full_pipeline_p50_us": positive_stages[
                    "full_offline_pipeline"
                ]["p50_us"],
                "positive_full_pipeline_p99_us": positive_stages[
                    "full_offline_pipeline"
                ]["p99_us"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
