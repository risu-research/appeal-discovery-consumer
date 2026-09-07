from __future__ import annotations

"""Live Mosquitto gate for the non-interfering ReplayMark R1 shadow hook."""

import argparse
from collections import Counter
import hashlib
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
from replaymark_shadow import (
    CapturedPublish,
    R1ShadowRun,
    _CaptureScope,
    _materialize_tasks,
    compile_e3b_r1_shadow_contract,
)


PUB = "$SYS/broker/publish/messages/received"
BYTES = "$SYS/broker/publish/bytes/received"
FROZEN_LADDER_GIT_BLOB_SHA1 = "fcc1768544714f1b11a497a856f8e18d4d2f07dd"
FROZEN_COMMAND_PAYLOAD_UTF8 = '{"on": true}'
_STABLE_RESULT_FIELDS = (
    "tasks",
    "success_rate",
    "support_violation_fraction",
    "branch_required_fraction",
    "verify_count",
    "semantic_operations",
)


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


def _git_blob_sha1(path: Path) -> str:
    body = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(body)).encode("ascii") + b"\0" + body
    ).hexdigest()


def _stable_result(result: dict[str, object]) -> dict[str, object]:
    return {name: result[name] for name in _STABLE_RESULT_FIELDS}


def _parse_device(device: str, prefix: str) -> tuple[int, str]:
    try:
        actual_prefix, task_text, role = device.rsplit("-", 2)
    except ValueError as exc:
        raise ValueError(f"malformed E3b device identity: {device!r}") from exc
    if actual_prefix != prefix:
        raise ValueError(f"device prefix mismatch: {actual_prefix!r} != {prefix!r}")
    if role not in ("a", "b"):
        raise ValueError(f"unexpected E3b device role: {role!r}")
    if not task_text.isascii() or not task_text.isdigit():
        raise ValueError(f"noncanonical E3b task id: {task_text!r}")
    task_id = int(task_text)
    if str(task_id) != task_text:
        raise ValueError(f"noncanonical E3b task id: {task_text!r}")
    return task_id, role


def _payload_utf8(payload: object) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, bytes):
        return payload.decode("utf-8")
    if isinstance(payload, bytearray):
        return bytes(payload).decode("utf-8")
    raise TypeError(f"captured MQTT payload is not UTF-8 text/bytes: {type(payload).__name__}")


def _command_wire_audit(
    records: tuple[CapturedPublish, ...],
    prefix: str,
    tasks: int,
) -> dict[str, object]:
    """Compare actual delegated Paho call material to the literal frozen R1 template."""

    actual: list[dict[str, object]] = []
    for record in records:
        if not isinstance(record.topic, str):
            raise TypeError("captured MQTT topic must be a string")
        parts = record.topic.split("/")
        if len(parts) != 3 or parts[0] != "agentmark" or parts[2] != "command":
            raise ValueError(f"unexpected captured command topic: {record.topic!r}")
        task_id, role = _parse_device(parts[1], prefix)
        actual.append(
            {
                "task_id": task_id,
                "role": role,
                "topic": record.topic,
                "payload_utf8": _payload_utf8(record.payload),
                "qos": record.qos,
                "retain": record.retain,
                "properties": record.properties,
            }
        )
    actual.sort(key=lambda row: (int(row["task_id"]), str(row["role"])))

    expected = [
        {
            "task_id": task_id,
            "role": role,
            "topic": f"agentmark/{prefix}-{task_id}-{role}/command",
            "payload_utf8": FROZEN_COMMAND_PAYLOAD_UTF8,
            "qos": 1,
            "retain": False,
            "properties": None,
        }
        for task_id in range(tasks)
        for role in ("a", "b")
    ]
    return {
        "matches_literal_frozen_r1": actual == expected,
        "actual_rows": len(actual),
        "expected_rows": len(expected),
        "actual_sha256": _sha256_json(actual),
        "expected_sha256": _sha256_json(expected),
    }


def _state_event_audit(harness: Harness, prefix: str, tasks: int) -> dict[str, object]:
    """Compare timestamp-free event semantics; timestamps are intentionally run-local."""

    rows: list[dict[str, object]] = []
    with harness.cv:
        items = [
            (str(device), list(events))
            for device, events in harness.state_events.items()
            if str(device).startswith(prefix + "-")
        ]
    for device, events in items:
        task_id, role = _parse_device(device, prefix)
        for event in events:
            rows.append(
                {
                    "task_id": task_id,
                    "role": role,
                    "device_suffix": f"{task_id}-{role}",
                    "body_device_suffix": str(event.get("device")).removeprefix(prefix + "-"),
                    "on": event.get("on"),
                    "cause": event.get("cause"),
                }
            )
    rows.sort(key=lambda row: (int(row["task_id"]), str(row["role"])))
    expected = [
        {
            "task_id": task_id,
            "role": role,
            "device_suffix": f"{task_id}-{role}",
            "body_device_suffix": f"{task_id}-{role}",
            "on": True,
            "cause": "command",
        }
        for task_id in range(tasks)
        for role in ("a", "b")
    ]
    return {
        "matches_literal_frozen_device_effect": rows == expected,
        "event_count": len(rows),
        "semantic_sha256": _sha256_json(rows),
        "expected_sha256": _sha256_json(expected),
    }


def _measure(harness: Harness, prefix: str, tasks: int, target_delay_ms: float, fn):
    harness.set_state_delay(target_delay_ms)
    before = harness.fresh_sys_snapshot()
    value = fn()
    time.sleep(target_delay_ms / 1000.0 + 0.05)
    after = harness.fresh_sys_snapshot()
    return value, _sys_delta(before, after), _state_event_audit(harness, prefix, tasks)


def _run_shadow_with_capture_records(
    harness: Harness,
    traces: list[dict[str, object]],
    wave_size: int,
    wave_period_ms: float,
    prefix: str,
    verify_ms: float,
    post_completion_gap_ms: float,
    task_timeout_ms: int,
    contract,
) -> tuple[R1ShadowRun, tuple[CapturedPublish, ...]]:
    """Verification view of the production hook, retaining the passive capture transcript."""

    with _CaptureScope(harness) as capture:
        legacy_result = ladder.cond(
            harness,
            "R1_timing",
            traces,
            wave_size,
            wave_period_ms,
            prefix,
            verify_ms,
            post_completion_gap_ms,
            task_timeout_ms,
        )
    materials = _materialize_tasks(harness, capture.records, verify_ms, contract)
    run = R1ShadowRun(
        legacy_result=legacy_result,
        task_material=materials,
        captured_publish_count=len(capture.records),
    )
    return run, tuple(capture.records)


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

    ladder_path = Path(ladder.__file__).resolve()
    ladder_blob = _git_blob_sha1(ladder_path)
    if ladder_blob != FROZEN_LADDER_GIT_BLOB_SHA1:
        raise RuntimeError(
            f"live runner loaded non-frozen ladder authority: {ladder_blob}"
        )

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
            base_prefix = f"b{trial:02d}-r1-shadow"
            shadow_prefix = f"s{trial:02d}-r1-shadow"
            if len(base_prefix) != len(shadow_prefix):
                raise AssertionError("paired prefixes must have equal length")

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
                return _run_shadow_with_capture_records(
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
            measured: dict[str, tuple[object, dict[str, float], dict[str, object]]] = {}
            for label in order:
                if label == "baseline":
                    measured[label] = _measure(
                        harness, base_prefix, args.tasks, target_delay_ms, baseline_run
                    )
                else:
                    measured[label] = _measure(
                        harness, shadow_prefix, args.tasks, target_delay_ms, shadow_run
                    )

            baseline, baseline_sys, baseline_event_audit = measured["baseline"]
            shadow_capture, shadow_sys, shadow_event_audit = measured["shadow"]
            if not isinstance(baseline, dict):
                raise TypeError("baseline R1 result must be a dict")
            shadow_result, captured_records = shadow_capture
            legacy = shadow_result.legacy_result

            stable_equal = _stable_result(baseline) == _stable_result(legacy)
            expected_publishes = float(4 * args.tasks)
            pub_equal = (
                float(baseline_sys.get(PUB, float("nan"))) == expected_publishes
                and float(shadow_sys.get(PUB, float("nan"))) == expected_publishes
            )
            event_count_equal = (
                int(baseline_event_audit["event_count"])
                == int(shadow_event_audit["event_count"])
                == 2 * args.tasks
            )
            event_semantics_exact = (
                baseline_event_audit["matches_literal_frozen_device_effect"] is True
                and shadow_event_audit["matches_literal_frozen_device_effect"] is True
                and baseline_event_audit["semantic_sha256"]
                == shadow_event_audit["semantic_sha256"]
            )
            wire_audit = _command_wire_audit(captured_records, shadow_prefix, args.tasks)
            wire_exact = wire_audit["matches_literal_frozen_r1"] is True

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
                item.raw_historical_action["payload_utf8"] == FROZEN_COMMAND_PAYLOAD_UTF8
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
                "exact_frozen_command_wire_material_preserved": wire_exact,
                "state_event_count_identical": event_count_equal,
                "state_event_semantics_identical": event_semantics_exact,
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
                            "baseline_event_audit": baseline_event_audit,
                            "shadow_event_audit": shadow_event_audit,
                            "wire_audit": wire_audit,
                            "verdicts": verdicts,
                            "dispositions": dispositions,
                            "tokens": tokens,
                        },
                        default=dict,
                        sort_keys=True,
                    )
                )

            baseline_bytes = baseline_sys.get(BYTES)
            shadow_bytes = shadow_sys.get(BYTES)
            byte_delta = None
            if isinstance(baseline_bytes, (int, float)) and isinstance(
                shadow_bytes, (int, float)
            ):
                byte_delta = float(shadow_bytes) - float(baseline_bytes)

            trials.append(
                {
                    "trial": trial,
                    "order": list(order),
                    "checks": checks,
                    "baseline_stable_result": _stable_result(baseline),
                    "shadow_stable_result": _stable_result(legacy),
                    "broker_publish_messages": {
                        "baseline": baseline_sys.get(PUB),
                        "shadow": shadow_sys.get(PUB),
                        "expected_each": expected_publishes,
                    },
                    "broker_publish_bytes_diagnostic_only": {
                        "baseline": baseline_bytes,
                        "shadow": shadow_bytes,
                        "shadow_minus_baseline": byte_delta,
                        "promotion_gate": False,
                        "reason": (
                            "Mosquitto $SYS byte counters are sampled asynchronously and "
                            "include timestamp-bearing device-state payloads; exact cross-run "
                            "equality is not a sound wire-equivalence oracle"
                        ),
                    },
                    "command_wire_audit": wire_audit,
                    "baseline_state_event_audit": baseline_event_audit,
                    "shadow_state_event_audit": shadow_event_audit,
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
        "schema": "replaymark.runtime-e3b-r1-shadow-hook-live.v2",
        "verdict": "PASS" if all_checks else "FAIL",
        "broker_version_sys": version,
        "frozen_ladder_git_blob_sha1": ladder_blob,
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
                "literal frozen application-controlled command wire material",
                "broker publish message count",
                "timestamp-free device state event semantics",
                "state event count",
            ],
            "raw_sys_publish_byte_equality": "DIAGNOSTIC_ONLY_NOT_PROMOTION_GATE",
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
