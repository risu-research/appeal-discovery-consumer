from __future__ import annotations

import argparse
import hashlib
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
from replaymark_shadow import E3B_R1_SHADOW_CLOCK_DOMAIN, compile_e3b_r1_shadow_contract

SCHEMA = "replaymark.s2p6-live-heterogeneous-target-capstone.v1"
POLICY_SEED = "replaymark.s2.policy-assignment.v1|s1=c93c8574eb62cb4dcde94890fdfc8f939b41e00a"
POLICY_PERMS = (
    ("ALWAYS_ADMIT", "ALWAYS_BLOCK", "REPLAYMARK"),
    ("ALWAYS_ADMIT", "REPLAYMARK", "ALWAYS_BLOCK"),
    ("ALWAYS_BLOCK", "ALWAYS_ADMIT", "REPLAYMARK"),
    ("ALWAYS_BLOCK", "REPLAYMARK", "ALWAYS_ADMIT"),
    ("REPLAYMARK", "ALWAYS_ADMIT", "ALWAYS_BLOCK"),
    ("REPLAYMARK", "ALWAYS_BLOCK", "ALWAYS_ADMIT"),
)
HISTORICAL_TEMPLATE_SHA256 = "e86d5f42a09b8257185b6e3608ac83c0ac41deeba7890b914c22b0441a8b8888"
TRIALS = 6
TASKS = 192
WAVE_SIZE = 32
WAVE_PERIOD_MS = 300.0
VERIFY_MS = 100.0
TASK_TIMEOUT_MS = 1000

class RecordingPublishClient:
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
        stamp = time.monotonic_ns()
        with self._lock:
            self.calls.append(
                {
                    "stamp_mono_ns": stamp,
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

def policy_for(trial: int, task_id: int) -> str:
    block = task_id // 3
    offset = task_id % 3
    digest = hashlib.sha256(
        f"{POLICY_SEED}|trial={trial}|block={block}".encode("utf-8")
    ).digest()
    selector = int.from_bytes(digest[:8], "big") % 6
    return POLICY_PERMS[selector][offset]

def publish_act1(harness: Harness, device: str) -> int:
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

def snapshot_observation(
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
                "event_id": f"s2p6-live:{device}:{index}",
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

def raw_act2(prefix: str, task_id: int) -> dict[str, object]:
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

def normalize_effects(
    harness: Harness,
    *,
    device: str,
    after_ns: int,
    deadline_ns: int,
) -> list[dict[str, object]]:
    with harness.cv:
        rows = list(harness.state_events.get(device, ()))
    out = []
    for event in rows:
        recv = event.get("recv_mono_ns")
        if isinstance(recv, int) and after_ns <= recv <= deadline_ns:
            out.append(
                {
                    "device": str(event.get("device")),
                    "on": event.get("on"),
                    "cause": str(event.get("cause")),
                    "ts_mono_ns": event.get("ts_mono_ns"),
                    "recv_mono_ns": recv,
                }
            )
    return out

def run_trial(
    harness: Harness,
    recording: RecordingPublishClient,
    gate: E3bCertifiedExecutionGate,
    contract: object,
    *,
    trial: int,
) -> dict[str, object]:
    prefix = f"s2p6-t{trial}-{uuid.uuid4().hex[:12]}"

    def observe(task_id: int, offer_ns: int) -> dict[str, object]:
        ladder.sleep_until(offer_ns)
        t0 = time.monotonic_ns()
        device_a = f"{prefix}-{task_id}-a"
        a1 = publish_act1(harness, device_a)
        deadline = t0 + int(VERIFY_MS * 1e6)
        timeout_deadline = t0 + int(TASK_TIMEOUT_MS * 1e6)
        if deadline <= a1:
            raise RuntimeError("verify deadline did not follow ACT1 publication")
        raw_observation = snapshot_observation(
            harness,
            device=device_a,
            command_publish_ns=a1,
            deadline_ns=deadline,
        )
        return {
            "trial": trial,
            "task_id": task_id,
            "policy": policy_for(trial, task_id),
            "offer_mono_ns": offer_ns,
            "task_start_mono_ns": t0,
            "act1_publish_mono_ns": a1,
            "verify_deadline_mono_ns": deadline,
            "task_timeout_deadline_mono_ns": timeout_deadline,
            "raw_observation": raw_observation,
        }

    observations = ladder.offers(
        TASKS,
        WAVE_SIZE,
        WAVE_PERIOD_MS,
        lambda task_id, offer: observe(task_id, offer),
    )
    freeze_complete_ns = time.monotonic_ns()

    max_a_timeout = max(int(row["task_timeout_deadline_mono_ns"]) for row in observations)
    ladder.sleep_until(max_a_timeout)
    a_eventual_missing: list[int] = []
    for row in observations:
        task_id = int(row["task_id"])
        device_a = f"{prefix}-{task_id}-a"
        with harness.cv:
            events = list(harness.state_events.get(device_a, ()))
        if not any(
            isinstance(event.get("recv_mono_ns"), int)
            and int(row["act1_publish_mono_ns"]) <= int(event["recv_mono_ns"]) <= int(row["task_timeout_deadline_mono_ns"])
            and event.get("on") is True
            for event in events
        ):
            a_eventual_missing.append(task_id)
    if a_eventual_missing:
        raise TimeoutError(f"A-side quiescence barrier incomplete tasks={a_eventual_missing}")
    a_quiescence_ns = time.monotonic_ns()

    rows: list[dict[str, object]] = []
    for observed in observations:
        task_id = int(observed["task_id"])
        policy = str(observed["policy"])
        raw_observation = observed["raw_observation"]
        raw_action = raw_act2(prefix, task_id)
        pair = correlate_e3b_runtime_pair(raw_observation, raw_action)
        certificate = certify_e3b_shadow_reuse(contract, pair)
        verdict = certificate.semantic_certificate.adjudication.verdict.value
        reuse_disposition = certificate.semantic_certificate.reuse_decision.disposition.value

        before = len(recording.calls)
        receipt_record = None
        if policy == "ALWAYS_ADMIT":
            info = recording.publish(
                raw_action["topic"],
                raw_action["payload_utf8"],
                qos=raw_action["qos"],
                retain=raw_action["retain"],
                properties=raw_action["properties"],
            )
            info.wait_for_publish(timeout=5)
            executed = True
            execution_disposition = "BASELINE_ADMIT"
        elif policy == "ALWAYS_BLOCK":
            executed = False
            execution_disposition = "BASELINE_BLOCK"
        elif policy == "REPLAYMARK":
            receipt = gate.dispatch(
                contract,
                raw_observation,
                raw_action,
                certificate,
            )
            receipt_record = receipt.canonical_record()
            executed = (
                receipt.execution_disposition
                is ExecutionAdmissionDisposition.ADMIT_REUSE
            )
            execution_disposition = receipt.execution_disposition.value
        else:
            raise AssertionError(f"unknown policy {policy}")
        delegate_delta = len(recording.calls) - before

        rows.append(
            {
                **observed,
                "raw_action": raw_action,
                "certificate_record": certificate.canonical_record(),
                "certificate_fingerprint": certificate.fingerprint(),
                "certificate_verdict": verdict,
                "certificate_reuse_disposition": reuse_disposition,
                "execution_disposition": execution_disposition,
                "executed": executed,
                "delegate_delta": delegate_delta,
                "receipt": receipt_record,
                "b_effect_deadline_mono_ns": int(raw_action["publish_mono_ns"]) + int(TASK_TIMEOUT_MS * 1e6),
            }
        )

    dispatch_complete_ns = time.monotonic_ns()
    max_b_deadline = max(int(row["b_effect_deadline_mono_ns"]) for row in rows)
    ladder.sleep_until(max_b_deadline)
    for row in rows:
        task_id = int(row["task_id"])
        row["b_effects"] = normalize_effects(
            harness,
            device=f"{prefix}-{task_id}-b",
            after_ns=int(row["raw_action"]["publish_mono_ns"]),
            deadline_ns=int(row["b_effect_deadline_mono_ns"]),
        )
    effect_barrier_ns = time.monotonic_ns()

    return {
        "trial": trial,
        "prefix": prefix,
        "rows": rows,
        "observation_freeze_complete_mono_ns": freeze_complete_ns,
        "a_quiescence_barrier_mono_ns": a_quiescence_ns,
        "dispatch_complete_mono_ns": dispatch_complete_ns,
        "b_effect_barrier_mono_ns": effect_barrier_ns,
    }

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--broker", default="mosquitto")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    contract = compile_e3b_r1_shadow_contract()
    harness = Harness(args.broker, args.port)
    recording = RecordingPublishClient(harness.client)
    gate = E3bCertifiedExecutionGate(recording)
    trials = []
    try:
        broker_version = harness.broker_version()
        for trial in range(TRIALS):
            trials.append(
                run_trial(
                    harness,
                    recording,
                    gate,
                    contract,
                    trial=trial,
                )
            )
    finally:
        harness.close()

    report = {
        "schema": SCHEMA,
        "broker": broker_version,
        "historical_template_sha256": HISTORICAL_TEMPLATE_SHA256,
        "parameters": {
            "trials": TRIALS,
            "tasks_per_trial": TASKS,
            "wave_size": WAVE_SIZE,
            "wave_period_ms": WAVE_PERIOD_MS,
            "verify_ms": VERIFY_MS,
            "task_timeout_ms": TASK_TIMEOUT_MS,
        },
        "trials": trials,
        "recording_client_calls": recording.calls,
        "recording_client_call_count": len(recording.calls),
        "replaymark_gate_consumed_count": gate.consumed_count,
        "fallback": "ABSENT",
        "regeneration": "ABSENT",
        "automatic_retry": "ABSENT",
        "independent_oracle_used_in_live_runner": False,
        "harness_closed_before_report": True,
    }
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "broker": broker_version,
                "trials": len(trials),
                "rows": sum(len(trial["rows"]) for trial in trials),
                "delegate_calls": len(recording.calls),
                "replaymark_gate_consumed_count": gate.consumed_count,
            },
            indent=2,
            sort_keys=True,
        )
    )

if __name__ == "__main__":
    main()
