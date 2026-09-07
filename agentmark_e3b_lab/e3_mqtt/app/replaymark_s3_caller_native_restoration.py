from __future__ import annotations

import argparse
import hashlib
import json
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

SCHEMA = "replaymark.s3-live-caller-native-restoration.v1"
POLICY_SEED = "replaymark.s2.policy-assignment.v1|s1=c93c8574eb62cb4dcde94890fdfc8f939b41e00a"
P6_PERMS = (
    ("ALWAYS_ADMIT", "ALWAYS_BLOCK", "REPLAYMARK"),
    ("ALWAYS_ADMIT", "REPLAYMARK", "ALWAYS_BLOCK"),
    ("ALWAYS_BLOCK", "ALWAYS_ADMIT", "REPLAYMARK"),
    ("ALWAYS_BLOCK", "REPLAYMARK", "ALWAYS_ADMIT"),
    ("REPLAYMARK", "ALWAYS_ADMIT", "ALWAYS_BLOCK"),
    ("REPLAYMARK", "ALWAYS_BLOCK", "ALWAYS_ADMIT"),
)
RELABEL = {
    "ALWAYS_ADMIT": "ALWAYS_REUSE",
    "ALWAYS_BLOCK": "ALWAYS_NATIVE",
    "REPLAYMARK": "REPLAYMARK_NATIVE",
}
HISTORICAL_TEMPLATE_SHA256 = "e86d5f42a09b8257185b6e3608ac83c0ac41deeba7890b914c22b0441a8b8888"
TRIALS = 6
TASKS = 192
WAVE_SIZE = 32
WAVE_PERIOD_MS = 300.0
VERIFY_MS = 100.0
TASK_TIMEOUT_MS = 1000


class HistoricalRecorder:
    def __init__(self, client: Any):
        self._client = client
        self._lock = threading.Lock()
        self.calls: list[dict[str, object]] = []

    def publish(self, topic: object, payload: object = None, qos: object = 0,
                retain: object = False, properties: object = None):
        stamp = time.monotonic_ns()
        record = {
            "channel": "HISTORICAL_ACT2",
            "stamp_mono_ns": stamp,
            "topic": topic,
            "payload": payload,
            "qos": qos,
            "retain": retain,
            "properties": properties,
        }
        with self._lock:
            self.calls.append(record)
        return self._client.publish(topic, payload, qos=qos, retain=retain, properties=properties)


class NativeRecorder:
    def __init__(self, client: Any):
        self._client = client
        self._lock = threading.Lock()
        self.calls: list[dict[str, object]] = []

    def _publish(self, channel: str, *, generated_mono_ns: int, topic: str,
                 payload: str, qos: int, retain: bool, properties: object):
        stamp = time.monotonic_ns()
        record = {
            "channel": channel,
            "generated_mono_ns": generated_mono_ns,
            "stamp_mono_ns": stamp,
            "topic": topic,
            "payload": payload,
            "qos": qos,
            "retain": retain,
            "properties": properties,
        }
        with self._lock:
            self.calls.append(record)
        return self._client.publish(topic, payload, qos=qos, retain=retain, properties=properties)

    def query_a(self, topic: str):
        generated = time.monotonic_ns()
        return self._publish(
            "NATIVE_QUERY_A",
            generated_mono_ns=generated,
            topic=topic,
            payload="{}",
            qos=1,
            retain=False,
            properties=None,
        )

    def fresh_act2(self, topic: str):
        generated = time.monotonic_ns()
        return self._publish(
            "NATIVE_FRESH_ACT2",
            generated_mono_ns=generated,
            topic=topic,
            payload='{"on": true}',
            qos=1,
            retain=False,
            properties=None,
        )


def policy_for(trial: int, task_id: int) -> str:
    block, offset = divmod(task_id, 3)
    digest = hashlib.sha256(
        f"{POLICY_SEED}|trial={trial}|block={block}".encode("utf-8")
    ).digest()
    return RELABEL[P6_PERMS[int.from_bytes(digest[:8], "big") % 6][offset]]


def publish_act1(harness: Harness, device: str) -> int:
    stamp = time.monotonic_ns()
    info = harness.client.publish(
        f"agentmark/{device}/command", '{"on": true}', qos=1, retain=False, properties=None
    )
    info.wait_for_publish(timeout=5)
    return stamp


def snapshot_observation(harness: Harness, *, device: str, command_publish_ns: int,
                         deadline_ns: int) -> dict[str, object]:
    ladder.sleep_until(deadline_ns)
    closed_at = time.monotonic_ns()
    with harness.cv:
        rows = list(harness.state_events.get(device, ()))
    events = []
    for index, event in enumerate(rows):
        recv = event.get("recv_mono_ns")
        if isinstance(recv, bool) or not isinstance(recv, int) or recv > closed_at:
            continue
        events.append({
            "event_id": f"s3-live:{device}:{index}",
            "device": str(event.get("device")),
            "on": event.get("on"),
            "recv_mono_ns": recv,
            "clock_domain": E3B_R1_SHADOW_CLOCK_DOMAIN,
        })
    return {
        "schema": E3B_RAW_OBSERVATION_SCHEMA,
        "clock_domain": E3B_R1_SHADOW_CLOCK_DOMAIN,
        "expected_device": device,
        "command_publish_mono_ns": command_publish_ns,
        "verify_deadline_mono_ns": deadline_ns,
        "closed_at_mono_ns": closed_at,
        "events": events,
    }


def raw_historical_act2(prefix: str, task_id: int) -> dict[str, object]:
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


def wait_query_confirmation(harness: Harness, *, device: str, after_ns: int,
                            deadline_ns: int) -> dict[str, object] | None:
    with harness.cv:
        while True:
            matches = [
                e for e in harness.state_events.get(device, ())
                if isinstance(e.get("recv_mono_ns"), int)
                and after_ns <= int(e["recv_mono_ns"]) <= deadline_ns
                and e.get("cause") == "query"
                and e.get("on") is True
            ]
            if matches:
                event = min(matches, key=lambda e: int(e["recv_mono_ns"]))
                return {
                    "device": str(event.get("device")),
                    "on": event.get("on"),
                    "cause": str(event.get("cause")),
                    "ts_mono_ns": event.get("ts_mono_ns"),
                    "recv_mono_ns": int(event["recv_mono_ns"]),
                }
            remaining = deadline_ns - time.monotonic_ns()
            if remaining <= 0:
                return None
            harness.cv.wait(remaining / 1e9)


def caller_native_recover(harness: Harness, recorder: NativeRecorder, *,
                          prefix: str, task_id: int) -> dict[str, object]:
    device_a = f"{prefix}-{task_id}-a"
    query_topic = f"agentmark/{device_a}/query"
    before = len(recorder.calls)
    info = recorder.query_a(query_topic)
    info.wait_for_publish(timeout=5)
    query_call = recorder.calls[-1]
    if len(recorder.calls) != before + 1 or query_call["channel"] != "NATIVE_QUERY_A":
        raise RuntimeError("native query provenance drift")
    query_deadline = int(query_call["stamp_mono_ns"]) + int(TASK_TIMEOUT_MS * 1e6)
    confirmation = wait_query_confirmation(
        harness, device=device_a, after_ns=int(query_call["stamp_mono_ns"]), deadline_ns=query_deadline
    )
    if confirmation is None:
        raise TimeoutError("native query confirmation timeout")
    if time.monotonic_ns() < int(confirmation["recv_mono_ns"]):
        raise RuntimeError("monotonic confirmation ordering failure")
    fresh_topic = f"agentmark/{prefix}-{task_id}-b/command"
    info = recorder.fresh_act2(fresh_topic)
    info.wait_for_publish(timeout=5)
    fresh_call = recorder.calls[-1]
    if fresh_call["channel"] != "NATIVE_FRESH_ACT2":
        raise RuntimeError("native ACT2 provenance drift")
    if int(fresh_call["generated_mono_ns"]) < int(confirmation["recv_mono_ns"]):
        raise RuntimeError("fresh ACT2 generated before current-state confirmation")
    return {
        "query_call": query_call,
        "query_confirmation": confirmation,
        "fresh_act2_call": fresh_call,
    }


def normalized_events(harness: Harness, *, device: str, after_ns: int,
                      deadline_ns: int) -> list[dict[str, object]]:
    with harness.cv:
        rows = list(harness.state_events.get(device, ()))
    out = []
    for event in rows:
        recv = event.get("recv_mono_ns")
        if isinstance(recv, int) and after_ns <= recv <= deadline_ns:
            out.append({
                "device": str(event.get("device")),
                "on": event.get("on"),
                "cause": str(event.get("cause")),
                "ts_mono_ns": event.get("ts_mono_ns"),
                "recv_mono_ns": recv,
            })
    return out


def run_trial(harness: Harness, historical: HistoricalRecorder, native: NativeRecorder,
              gate: E3bCertifiedExecutionGate, contract: object, *, trial: int) -> dict[str, object]:
    prefix = f"s2p6-t{trial}-{uuid.uuid4().hex[:12]}"

    def observe(task_id: int, offer_ns: int) -> dict[str, object]:
        ladder.sleep_until(offer_ns)
        start = time.monotonic_ns()
        device_a = f"{prefix}-{task_id}-a"
        act1 = publish_act1(harness, device_a)
        deadline = start + int(VERIFY_MS * 1e6)
        timeout_deadline = start + int(TASK_TIMEOUT_MS * 1e6)
        if deadline <= act1:
            raise RuntimeError("verify deadline did not follow ACT1")
        return {
            "trial": trial,
            "task_id": task_id,
            "policy": policy_for(trial, task_id),
            "offer_mono_ns": offer_ns,
            "task_start_mono_ns": start,
            "act1_publish_mono_ns": act1,
            "verify_deadline_mono_ns": deadline,
            "task_timeout_deadline_mono_ns": timeout_deadline,
            "raw_observation": snapshot_observation(
                harness, device=device_a, command_publish_ns=act1, deadline_ns=deadline
            ),
        }

    observations = ladder.offers(
        TASKS, WAVE_SIZE, WAVE_PERIOD_MS, lambda task_id, offer: observe(task_id, offer)
    )
    freeze_complete = time.monotonic_ns()
    max_a_timeout = max(int(row["task_timeout_deadline_mono_ns"]) for row in observations)
    ladder.sleep_until(max_a_timeout)
    missing = []
    for row in observations:
        device_a = f"{prefix}-{int(row['task_id'])}-a"
        with harness.cv:
            events = list(harness.state_events.get(device_a, ()))
        if not any(
            isinstance(e.get("recv_mono_ns"), int)
            and int(row["act1_publish_mono_ns"]) <= int(e["recv_mono_ns"]) <= int(row["task_timeout_deadline_mono_ns"])
            and e.get("on") is True
            for e in events
        ):
            missing.append(int(row["task_id"]))
    if missing:
        raise TimeoutError(f"A-side quiescence incomplete tasks={missing}")
    quiescence = time.monotonic_ns()

    rows: list[dict[str, object]] = []
    for observed in observations:
        task_id = int(observed["task_id"])
        raw_action = raw_historical_act2(prefix, task_id)
        pair = correlate_e3b_runtime_pair(observed["raw_observation"], raw_action)
        certificate = certify_e3b_shadow_reuse(contract, pair)
        rows.append({
            **observed,
            "raw_action": raw_action,
            "certificate_record": certificate.canonical_record(),
            "certificate_fingerprint": certificate.fingerprint(),
            "certificate_verdict": certificate.semantic_certificate.adjudication.verdict.value,
            "certificate_reuse_disposition": certificate.semantic_certificate.reuse_decision.disposition.value,
            "certificate_object": certificate,
            "receipt": None,
            "execution_failure": None,
            "native_failure": None,
            "historical_executed": False,
            "native_entered": False,
            "native_provenance": None,
        })
    certification_complete = time.monotonic_ns()

    for row in rows:
        task_id = int(row["task_id"])
        policy = str(row["policy"])
        raw_action = row["raw_action"]
        certificate = row.pop("certificate_object")
        before_h = len(historical.calls)
        before_n = len(native.calls)
        try:
            if policy == "ALWAYS_REUSE":
                info = historical.publish(
                    raw_action["topic"], raw_action["payload_utf8"], qos=raw_action["qos"],
                    retain=raw_action["retain"], properties=raw_action["properties"]
                )
                info.wait_for_publish(timeout=5)
                row["historical_executed"] = True
                row["execution_disposition"] = "BASELINE_REUSE"
            elif policy == "ALWAYS_NATIVE":
                row["execution_disposition"] = "BASELINE_NATIVE"
                row["native_entered"] = True
                row["native_provenance"] = caller_native_recover(
                    harness, native, prefix=prefix, task_id=task_id
                )
            elif policy == "REPLAYMARK_NATIVE":
                receipt = gate.dispatch(
                    contract, row["raw_observation"], raw_action, certificate
                )
                row["receipt"] = receipt.canonical_record()
                if receipt.execution_disposition is ExecutionAdmissionDisposition.ADMIT_REUSE:
                    row["execution_disposition"] = "ADMIT_REUSE"
                    row["historical_executed"] = True
                else:
                    row["execution_disposition"] = "BLOCK_REUSE_CALLER_NATIVE"
                    row["native_entered"] = True
                    row["native_provenance"] = caller_native_recover(
                        harness, native, prefix=prefix, task_id=task_id
                    )
            else:
                raise AssertionError(f"unknown policy {policy}")
        except Exception as exc:
            if row["native_entered"]:
                row["native_failure"] = f"{type(exc).__name__}: {exc}"
            else:
                row["execution_failure"] = f"{type(exc).__name__}: {exc}"
        row["historical_call_delta"] = len(historical.calls) - before_h
        row["native_call_delta"] = len(native.calls) - before_n

        b_start = None
        if row["historical_call_delta"] == 1:
            b_start = int(historical.calls[-1]["stamp_mono_ns"])
        elif row["native_provenance"] is not None:
            b_start = int(row["native_provenance"]["fresh_act2_call"]["stamp_mono_ns"])
        row["b_effect_start_mono_ns"] = b_start
        row["b_effect_deadline_mono_ns"] = (
            b_start + int(TASK_TIMEOUT_MS * 1e6) if b_start is not None else time.monotonic_ns()
        )

    dispatch_complete = time.monotonic_ns()
    max_b_deadline = max(int(row["b_effect_deadline_mono_ns"]) for row in rows)
    ladder.sleep_until(max_b_deadline)
    for row in rows:
        task_id = int(row["task_id"])
        if row["b_effect_start_mono_ns"] is None:
            row["b_effects"] = []
        else:
            row["b_effects"] = normalized_events(
                harness,
                device=f"{prefix}-{task_id}-b",
                after_ns=int(row["b_effect_start_mono_ns"]),
                deadline_ns=int(row["b_effect_deadline_mono_ns"]),
            )
        if row["native_entered"]:
            row["native_a_events"] = normalized_events(
                harness,
                device=f"{prefix}-{task_id}-a",
                after_ns=certification_complete,
                deadline_ns=dispatch_complete,
            )
        else:
            row["native_a_events"] = []
    effect_barrier = time.monotonic_ns()

    return {
        "trial": trial,
        "prefix": prefix,
        "rows": rows,
        "observation_freeze_complete_mono_ns": freeze_complete,
        "a_quiescence_barrier_mono_ns": quiescence,
        "certification_complete_mono_ns": certification_complete,
        "dispatch_complete_mono_ns": dispatch_complete,
        "b_effect_barrier_mono_ns": effect_barrier,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--broker", default="mosquitto")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    contract = compile_e3b_r1_shadow_contract()
    harness = Harness(args.broker, args.port)
    historical = HistoricalRecorder(harness.client)
    native = NativeRecorder(harness.client)
    gate = E3bCertifiedExecutionGate(historical)
    trials = []
    try:
        broker_version = harness.broker_version()
        for trial in range(TRIALS):
            trials.append(run_trial(harness, historical, native, gate, contract, trial=trial))
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
        "historical_calls": historical.calls,
        "historical_call_count": len(historical.calls),
        "native_calls": native.calls,
        "native_call_count": len(native.calls),
        "replaymark_gate_consumed_count": gate.consumed_count,
        "caller_owns_native_recovery": True,
        "fallback_inside_replaymark": False,
        "regeneration_inside_replaymark": False,
        "automatic_retry": "ABSENT",
        "independent_oracle_used_in_live_runner": False,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write("\n")


if __name__ == "__main__":
    main()
