from __future__ import annotations

"""Live Mosquitto gate for the non-interfering ReplayMark R1 shadow hook."""

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import statistics
import time
import uuid

from experiment import Harness, _sys_delta, percentile
import ladder
from replaymark.contracts import Verdict
from replaymark.rstar import ReuseDisposition
from replaymark_shadow import compile_e3b_r1_shadow_contract, run_r1_shadow_condition


PUB = "$SYS/broker/publish/messages/received"
BYTES = "$SYS/broker/publish/bytes/received"
_STABLE_RESULT_FIELDS = (
    "tasks",
    "success_rate",
    "support_violation_fraction",
    "branch_required_fraction",
    "verify_count",
    "semantic_operations",
)


def _stable_result(result: dict[str, object]) -> dict[str, object]:
    return {name: result[name] for name in _STABLE_RESULT_FIELDS}


def _event_count(harness: Harness, prefix: str) -> int:
    with harness.cv:
        return sum(
            len(events)
            for device, events in harness.state_events.items()
            if str(device).startswith(prefix + "-")
        )


def _measure(harness: Harness, prefix: str, target_delay_ms: float, fn):
    harness.set_state_delay(target_delay_ms)
    before = harness.fresh_sys_snapshot()
    value = fn()
    time.sleep(target_delay_ms / 1000.0 + 0.05)
    after = harness.fresh_sys_snapshot()
    return value, _sys_delta(before, after), _event_count(harness, prefix)


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
    parser.add_argument("--paired-trials", type=int, default=3)
    parser.add_argument("--out", default="/results/e3b_r1_shadow_hook.json")
    args = parser.parse_args()
    if args.tasks % args.wave_size:
        raise ValueError("tasks must be divisible by wave size")

    contract = compile_e3b_r1_shadow_contract()
    harness = Harness(args.broker, args.port)
    try:
        version = harness.broker_version()
        harness.set_state_delay(0)
        source_prefix = f"source-shadow-{uuid.uuid4().hex[:6]}"
        traces = ladder.offers(
            args.tasks,
            args.wave_size,
            args.wave_period_ms,
            lambda i, offer: ladder.source_task(
                harness,
                i,
                source_prefix,
                offer,
                args.post_completion_gap_ms,
                args.task_timeout_ms,
            ),
        )
        source_first = [float(row["first_completion_offset_ms"]) for row in traces]
        source_max = max(source_first)
        verify_ms = max(
            float(args.verify_floor_ms),
            float(math.ceil(source_max + args.source_guard_ms)),
        )
        target_delay_ms = max(
            float(args.changed_delay_floor_ms),
            verify_ms + args.target_margin_ms,
        )
        if target_delay_ms >= args.task_timeout_ms:
            raise RuntimeError("calibrated target delay collides with task timeout")

        trials: list[dict[str, object]] = []
        for trial in range(args.paired_trials):
            # Equal-length prefixes make device-state payload lengths identical.
            base_prefix = f"b{trial:02d}-r1-shadow"
            shadow_prefix = f"s{trial:02d}-r1-shadow"
            if len(base_prefix) != len(shadow_prefix):
                raise AssertionError("paired prefixes must have equal byte length")

            def baseline_run():
                return ladder.cond(
                    harness,
                    "R1_timing",
                    traces,
                    args.wave_size,
                    args.wave_period_ms,
                    base_prefix,
                    verify_ms,
                    args.post_completion_gap_ms,
                    args.task_timeout_ms,
                )

            def shadow_run():
                return run_r1_shadow_condition(
                    harness,
                    traces,
                    args.wave_size,
                    args.wave_period_ms,
                    shadow_prefix,
                    verify_ms,
                    args.post_completion_gap_ms,
                    args.task_timeout_ms,
                    contract,
                )

            order = ("baseline", "shadow") if trial % 2 == 0 else ("shadow", "baseline")
            measured: dict[str, tuple[object, dict[str, float], int]] = {}
            for label in order:
                if label == "baseline":
                    measured[label] = _measure(
                        harness, base_prefix, target_delay_ms, baseline_run
                    )
                else:
                    measured[label] = _measure(
                        harness, shadow_prefix, target_delay_ms, shadow_run
                    )

            baseline, baseline_sys, baseline_events = measured["baseline"]
            shadow, shadow_sys, shadow_events = measured["shadow"]
            if not isinstance(baseline, dict):
                raise TypeError("baseline R1 result must be a dict")
            shadow_result = shadow
            legacy = shadow_result.legacy_result

            stable_equal = _stable_result(baseline) == _stable_result(legacy)
            expected_publishes = float(4 * args.tasks)
            pub_equal = (
                float(baseline_sys.get(PUB, float("nan"))) == expected_publishes
                and float(shadow_sys.get(PUB, float("nan"))) == expected_publishes
            )
            bytes_equal = (
                BYTES in baseline_sys
                and BYTES in shadow_sys
                and float(baseline_sys[BYTES]) == float(shadow_sys[BYTES])
            )
            event_equal = baseline_events == shadow_events == 2 * args.tasks

            materials = shadow_result.task_material
            verdicts = Counter(
                item.certificate.semantic_certificate.adjudication.verdict.value
                for item in materials
            )
            dispositions = Counter(
                item.certificate.semantic_certificate.reuse_decision.disposition.value
                for item in materials
            )
            tokens = Counter(
                item.certificate.correlated_pair.observation.evidence_token
                for item in materials
            )
            task_ids = [item.task_id for item in materials]
            exact_action_capture = all(
                item.raw_historical_action["payload_utf8"] == '{"on": true}'
                and item.raw_historical_action["qos"] == 1
                and item.raw_historical_action["retain"] is False
                and item.raw_historical_action["properties"] is None
                for item in materials
            )
            pair_bindings = all(
                item.certificate.correlated_pair.correlation.task_prefix == shadow_prefix
                and item.certificate.correlated_pair.correlation.task_id == item.task_id
                for item in materials
            )
            certificates_correct = (
                len(materials) == args.tasks
                and task_ids == list(range(args.tasks))
                and verdicts == Counter({Verdict.INVALID.value: args.tasks})
                and dispositions
                == Counter({ReuseDisposition.DO_NOT_REUSE.value: args.tasks})
                and tokens == Counter({"not_visible_by_deadline": args.tasks})
                and shadow_result.captured_publish_count == 2 * args.tasks
                and exact_action_capture
                and pair_bindings
            )

            checks = {
                "legacy_execution_result_fields_identical": stable_equal,
                "broker_publish_workload_identical": pub_equal,
                "broker_publish_bytes_identical": bytes_equal,
                "state_event_count_identical": event_equal,
                "one_certificate_per_r1_task": len(materials) == args.tasks,
                "shadow_capture_exactly_two_commands_per_task": (
                    shadow_result.captured_publish_count == 2 * args.tasks
                ),
                "all_shadow_verdicts_match_frozen_r1_oracle": certificates_correct,
            }
            if not all(checks.values()):
                raise AssertionError(
                    json.dumps(
                        {
                            "trial": trial,
                            "checks": checks,
                            "baseline": baseline,
                            "shadow_legacy": legacy,
                            "baseline_sys": baseline_sys,
                            "shadow_sys": shadow_sys,
                            "baseline_events": baseline_events,
                            "shadow_events": shadow_events,
                            "verdicts": verdicts,
                            "dispositions": dispositions,
                            "tokens": tokens,
                        },
                        default=dict,
                        sort_keys=True,
                    )
                )

            trials.append(
                {
                    "trial": trial,
                    "order": list(order),
                    "checks": checks,
                    "baseline_stable_result": _stable_result(baseline),
                    "shadow_stable_result": _stable_result(legacy),
                    "baseline_sys": {PUB: baseline_sys.get(PUB), BYTES: baseline_sys.get(BYTES)},
                    "shadow_sys": {PUB: shadow_sys.get(PUB), BYTES: shadow_sys.get(BYTES)},
                    "baseline_state_events": baseline_events,
                    "shadow_state_events": shadow_events,
                    "certificate_count": len(materials),
                    "verdict_counts": dict(verdicts),
                    "reuse_disposition_counts": dict(dispositions),
                    "token_counts": dict(tokens),
                    "sample_certificate_fingerprint": materials[0].certificate.fingerprint(),
                    "timing_observation_only": {
                        "baseline_p99_ms": baseline["p99_ms"],
                        "shadow_p99_ms": legacy["p99_ms"],
                        "baseline_act2_mean_ms": baseline["act2_mean_ms"],
                        "shadow_act2_mean_ms": legacy["act2_mean_ms"],
                    },
                }
            )
    finally:
        harness.close()

    all_checks = all(all(row["checks"].values()) for row in trials)
    p99_deltas = [
        float(row["timing_observation_only"]["shadow_p99_ms"])
        - float(row["timing_observation_only"]["baseline_p99_ms"])
        for row in trials
    ]
    report = {
        "schema": "replaymark.runtime-e3b-r1-shadow-hook-live.v1",
        "verdict": "PASS" if all_checks else "FAIL",
        "broker_version_sys": version,
        "contract_fingerprint": contract.fingerprint(),
        "claim_fingerprint": contract.claim_fingerprint,
        "parameters": {
            **vars(args),
            "calibrated_verify_ms": verify_ms,
            "calibrated_target_delay_ms": target_delay_ms,
            "source_first_completion_p99_ms": percentile(source_first, 99),
            "source_first_completion_max_ms": source_max,
        },
        "noninterference_contract": {
            "canonical_ladder_source_modified": False,
            "semantic_certification_during_network_execution": False,
            "execution_or_fallback_policy": "NOT_IMPLEMENTED",
            "required_equivalence": [
                "legacy stable result fields",
                "broker publish message count",
                "broker publish byte count",
                "state event count",
            ],
        },
        "trials": trials,
        "timing_not_a_promotion_gate_yet": {
            "p99_delta_ms_mean": statistics.mean(p99_deltas),
            "p99_delta_ms_values": p99_deltas,
        },
        "promotion_pass": all_checks,
    }
    if not report["promotion_pass"]:
        raise SystemExit(2)
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "verdict": report["verdict"],
                "broker": version,
                "contract_fingerprint": contract.fingerprint(),
                "paired_trials": args.paired_trials,
                "tasks_per_arm": args.tasks,
                "promotion_pass": report["promotion_pass"],
                "p99_delta_ms_mean_observation_only": statistics.mean(p99_deltas),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
