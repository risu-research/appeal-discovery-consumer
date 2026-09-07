from __future__ import annotations

"""Live Gate S1 prospective execution-admission check on real Mosquitto.

This is intentionally not the selective-reuse capstone. It isolates one causal
question: once a complete E3b decision-boundary observation and an exact pre-send
ACT2 candidate are available, does the validated certificate alone open or close
the stage-2 publish sink?

Positive arm: confirmed_by_deadline -> VALID/REUSE -> ADMIT_REUSE -> one ACT2.
Negative arm: not_visible_by_deadline -> INVALID/DO_NOT_REUSE -> BLOCK_REUSE ->
zero ACT2. No fallback action is selected in either arm.
"""

import argparse
import json
from pathlib import Path
import threading
import time
import uuid
from typing import Any

from experiment import Harness
import ladder

from replaymark.execution_admission import ExecutionAdmissionDisposition
from replaymark.runtime_e3b_action import E3B_ACTION_CAPTURE_POINT, E3B_RAW_ACTION_SCHEMA
from replaymark.runtime_e3b_bridge import certify_e3b_shadow_reuse
from replaymark.runtime_e3b_correlation import correlate_e3b_runtime_pair
from replaymark.runtime_e3b_execution_gate import E3bCertifiedExecutionGate
from replaymark.runtime_e3b_observation import E3B_RAW_OBSERVATION_SCHEMA
from replaymark_oracle.e3b_integrated_runtime_oracle import integrated_expectation
from replaymark_oracle.execution_admission_oracle import expected_execution_admission
from replaymark_shadow import E3B_R1_SHADOW_CLOCK_DOMAIN, compile_e3b_r1_shadow_contract


SCHEMA = "replaymark.gate-s1-live-certified-execution-admission.v1"


class _RecordingPublishClient:
    """Record only gate-owned delegate calls, then forward unchanged."""

    def __init__(self, client: Any):
        self._client = client
        self._lock = threading.Lock()
        self.calls: list[dict[str, object]] = []

    def publish(
        self,
        topic: object,
        payload: object = None,
        qos: object = 0,
        retain: object = False,
        properties: object = None,
    ):
        with self._lock:
            self.calls.append(
                {
                    "topic": topic,
                    "payload": payload,
                    "qos": qos,
                    "retain": retain,
                    "properties": properties,
                }
            )
        return self._client.publish(
            topic,
            payload,
            qos=qos,
            retain=retain,
            properties=properties,
        )


def _publish_act1(harness: Harness, device: str) -> int:
    stamp = time.monotonic_ns()
    info = harness.client.publish(
        f"agentmark/{device}/command",
        '{"on": true}',
        qos=1,
        retain=False,
        properties=None,
    )
    info.wait_for_publish(timeout=5)
    return stamp


def _snapshot_observation(
    harness: Harness,
    *,
    device: str,
    command_publish_ns: int,
    deadline_ns: int,
) -> dict[str, object]:
    ladder.sleep_until(deadline_ns)
    closed_at = time.monotonic_ns()
    with harness.cv:
        rows = list(harness.state_events.get(device, ()))
    events: list[dict[str, object]] = []
    for index, event in enumerate(rows):
        recv = event.get("recv_mono_ns")
        if isinstance(recv, bool) or not isinstance(recv, int):
            raise TypeError("Harness state event lacks integer recv_mono_ns")
        if recv > closed_at:
            continue
        events.append(
            {
                "event_id": f"s1-live:{device}:{index}",
                "device": str(event.get("device")),
                "on": event.get("on"),
                "recv_mono_ns": recv,
                "clock_domain": E3B_R1_SHADOW_CLOCK_DOMAIN,
            }
        )
    return {
        "schema": E3B_RAW_OBSERVATION_SCHEMA,
        "clock_domain": E3B_R1_SHADOW_CLOCK_DOMAIN,
        "expected_device": device,
        "command_publish_mono_ns": command_publish_ns,
        "verify_deadline_mono_ns": deadline_ns,
        "closed_at_mono_ns": closed_at,
        "events": events,
    }


def _raw_act2(prefix: str, task_id: int) -> dict[str, object]:
    return {
        "schema": E3B_RAW_ACTION_SCHEMA,
        "capture_point": E3B_ACTION_CAPTURE_POINT,
        "clock_domain": E3B_R1_SHADOW_CLOCK_DOMAIN,
        "publish_mono_ns": time.monotonic_ns(),
        "topic": f"agentmark/{prefix}-{task_id}-b/command",
        "payload_utf8": '{"on": true}',
        "qos": 1,
        "retain": False,
        "properties": None,
    }


def _count_state_events(harness: Harness, devices: set[str]) -> int:
    with harness.cv:
        return sum(len(harness.state_events.get(device, ())) for device in devices)


def _run_arm(
    harness: Harness,
    gate: E3bCertifiedExecutionGate,
    contract: object,
    *,
    arm: str,
    state_delay_ms: float,
    tasks: int,
    wave_size: int,
    wave_period_ms: float,
    verify_ms: float,
    task_timeout_ms: int,
) -> dict[str, object]:
    harness.set_state_delay(state_delay_ms)
    prefix = f"s1-{arm}-{uuid.uuid4().hex[:8]}"
    rows_lock = threading.Lock()
    rows: list[dict[str, object]] = []

    def task(task_id: int, offer_ns: int) -> dict[str, object]:
        ladder.sleep_until(offer_ns)
        t0 = time.monotonic_ns()
        device_a = f"{prefix}-{task_id}-a"
        device_b = f"{prefix}-{task_id}-b"
        a1 = _publish_act1(harness, device_a)
        deadline = t0 + int(verify_ms * 1e6)
        if deadline <= a1:
            raise RuntimeError("verify deadline did not follow ACT1 publication")

        raw_observation = _snapshot_observation(
            harness,
            device=device_a,
            command_publish_ns=a1,
            deadline_ns=deadline,
        )
        raw_action = _raw_act2(prefix, task_id)

        pair = correlate_e3b_runtime_pair(raw_observation, raw_action)
        certificate = certify_e3b_shadow_reuse(contract, pair)

        independent = integrated_expectation(raw_observation, raw_action)
        admission_oracle = expected_execution_admission(
            certificate_exact=True,
            verdict=independent.verdict,
            reuse_disposition=independent.reuse_disposition,
        )
        receipt = gate.dispatch(
            contract,
            raw_observation,
            raw_action,
            certificate,
        )
        if receipt.execution_disposition.value != admission_oracle.outcome:
            raise AssertionError("production admission differs from independent literal oracle")

        b_effect = None
        if receipt.execution_disposition is ExecutionAdmissionDisposition.ADMIT_REUSE:
            b_effect = harness.wait_state_on_until(
                device_b,
                t0 + int(task_timeout_ms * 1e6),
                after_ns=int(raw_action["publish_mono_ns"]),
            )
            if b_effect is None:
                raise TimeoutError("admitted ACT2 produced no observable stage-2 state")
        row = {
            "task_id": task_id,
            "observation_token": pair.observation.evidence_token,
            "verdict": certificate.semantic_certificate.adjudication.verdict.value,
            "reuse_disposition": certificate.semantic_certificate.reuse_decision.disposition.value,
            "execution_disposition": receipt.execution_disposition.value,
            "publish_invocations": receipt.application_publish_invocations,
            "b_effect_observed": b_effect is not None,
            "certificate_fingerprint": certificate.fingerprint(),
            "admission_fingerprint": receipt.validated_admission_fingerprint,
            "receipt_fingerprint": receipt.fingerprint(),
        }
        with rows_lock:
            rows.append(row)
        return row

    ladder.offers(
        tasks,
        wave_size,
        wave_period_ms,
        lambda i, offer: task(i, offer),
    )
    rows.sort(key=lambda row: int(row["task_id"]))

    time.sleep(max(0.05, state_delay_ms / 1000.0 + 0.05))
    b_devices = {f"{prefix}-{i}-b" for i in range(tasks)}
    b_state_events = _count_state_events(harness, b_devices)

    return {
        "arm": arm,
        "state_delay_ms": state_delay_ms,
        "prefix": prefix,
        "tasks": tasks,
        "rows": rows,
        "admission_counts": {
            "ADMIT_REUSE": sum(
                row["execution_disposition"] == "ADMIT_REUSE" for row in rows
            ),
            "BLOCK_REUSE": sum(
                row["execution_disposition"] == "BLOCK_REUSE" for row in rows
            ),
        },
        "verdict_counts": {
            "VALID": sum(row["verdict"] == "VALID" for row in rows),
            "INVALID": sum(row["verdict"] == "INVALID" for row in rows),
            "UNRESOLVED": sum(row["verdict"] == "UNRESOLVED" for row in rows),
        },
        "application_publish_invocations": sum(
            int(row["publish_invocations"]) for row in rows
        ),
        "b_state_events": b_state_events,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--broker", default="mosquitto")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--tasks", type=int, default=16)
    parser.add_argument("--wave-size", type=int, default=8)
    parser.add_argument("--wave-period-ms", type=float, default=250)
    parser.add_argument("--verify-ms", type=float, default=100)
    parser.add_argument("--negative-delay-ms", type=float, default=180)
    parser.add_argument("--task-timeout-ms", type=int, default=1000)
    parser.add_argument(
        "--out",
        default="/results/e3b_s1_certified_execution_admission.json",
    )
    args = parser.parse_args()

    if args.negative_delay_ms <= args.verify_ms:
        raise ValueError("negative delay must exceed verify deadline")

    contract = compile_e3b_r1_shadow_contract()
    harness = Harness(args.broker, args.port)
    recording_client = _RecordingPublishClient(harness.client)
    gate = E3bCertifiedExecutionGate(recording_client)

    try:
        broker_version = harness.broker_version()
        positive = _run_arm(
            harness,
            gate,
            contract,
            arm="positive",
            state_delay_ms=0,
            tasks=args.tasks,
            wave_size=args.wave_size,
            wave_period_ms=args.wave_period_ms,
            verify_ms=args.verify_ms,
            task_timeout_ms=args.task_timeout_ms,
        )
        calls_after_positive = len(recording_client.calls)

        negative = _run_arm(
            harness,
            gate,
            contract,
            arm="negative",
            state_delay_ms=args.negative_delay_ms,
            tasks=args.tasks,
            wave_size=args.wave_size,
            wave_period_ms=args.wave_period_ms,
            verify_ms=args.verify_ms,
            task_timeout_ms=args.task_timeout_ms,
        )
        calls_after_negative = len(recording_client.calls)
    finally:
        harness.close()

    checks = {
        "positive_all_valid": positive["verdict_counts"] == {
            "VALID": args.tasks,
            "INVALID": 0,
            "UNRESOLVED": 0,
        },
        "positive_all_admitted": positive["admission_counts"] == {
            "ADMIT_REUSE": args.tasks,
            "BLOCK_REUSE": 0,
        },
        "positive_exact_delegate_count": positive["application_publish_invocations"]
        == args.tasks,
        "positive_effect_count": positive["b_state_events"] == args.tasks,
        "negative_all_invalid": negative["verdict_counts"] == {
            "VALID": 0,
            "INVALID": args.tasks,
            "UNRESOLVED": 0,
        },
        "negative_all_blocked": negative["admission_counts"] == {
            "ADMIT_REUSE": 0,
            "BLOCK_REUSE": args.tasks,
        },
        "negative_zero_delegate_count": negative["application_publish_invocations"] == 0,
        "negative_zero_stage2_effects": negative["b_state_events"] == 0,
        "gate_owned_publish_delta_positive": calls_after_positive == args.tasks,
        "gate_owned_publish_delta_negative": calls_after_negative
        == calls_after_positive,
        "all_admissions_consumed_once": gate.consumed_count == 2 * args.tasks,
    }
    report = {
        "schema": SCHEMA,
        "broker": broker_version,
        "contract_fingerprint": contract.fingerprint(),
        "tasks_per_arm": args.tasks,
        "verify_ms": args.verify_ms,
        "negative_delay_ms": args.negative_delay_ms,
        "positive": positive,
        "negative": negative,
        "gate_owned_delegate_calls": len(recording_client.calls),
        "fallback": "ABSENT",
        "regeneration": "ABSENT",
        "automatic_retry": "ABSENT",
        "broker_delivery_exactly_once_claim": False,
        "cross_process_deduplication_claim": False,
        "selective_capstone": "NOT_CLAIMED",
        "promotion_checks": checks,
        "promotion_pass": all(checks.values()),
        "verdict": "PASS" if all(checks.values()) else "FAIL",
    }

    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "broker": broker_version,
                "tasks_per_arm": args.tasks,
                "positive_admit": positive["admission_counts"]["ADMIT_REUSE"],
                "negative_block": negative["admission_counts"]["BLOCK_REUSE"],
                "gate_owned_delegate_calls": len(recording_client.calls),
                "negative_b_state_events": negative["b_state_events"],
                "promotion_pass": report["promotion_pass"],
                "verdict": report["verdict"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    if not report["promotion_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
