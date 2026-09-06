from __future__ import annotations

import argparse
import json
import os
import statistics
import threading
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import paho.mqtt.client as mqtt


RELEVANT_KINDS = {"command", "query", "state"}


def sleep_until(ns: int) -> None:
    while True:
        remaining = ns - time.monotonic_ns()
        if remaining <= 0:
            return
        time.sleep(remaining / 1e9)


def percentile(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    ys = sorted(xs)
    if len(ys) == 1:
        return ys[0]
    pos = (len(ys) - 1) * p / 100.0
    lo = int(pos)
    hi = min(lo + 1, len(ys) - 1)
    frac = pos - lo
    return ys[lo] * (1 - frac) + ys[hi] * frac


class Harness:
    def __init__(self, broker: str, port: int, run_id: str):
        self.broker = broker
        self.port = port
        self.run_id = run_id
        self.cv = threading.Condition()
        self.connected = threading.Event()
        self.subscribed = threading.Event()
        self.states: dict[str, list[dict]] = defaultdict(list)
        self.relevant_count = 0
        self.relevant_topics: dict[str, int] = defaultdict(int)
        self.control_acks: set[str] = set()
        self.duplicate_inbound = 0
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"downstream-runner-{run_id}-{uuid.uuid4().hex[:8]}",
            protocol=mqtt.MQTTv311,
        )
        self.client.on_connect = self._on_connect
        self.client.on_subscribe = self._on_subscribe
        self.client.on_message = self._on_message
        self.client.connect(broker, port, keepalive=30)
        self.client.loop_start()
        if not self.connected.wait(8):
            raise TimeoutError("runner connect")
        rc, _ = self.client.subscribe(
            [(f"replaymark/{run_id}/#", 1), ("replaymark/control/ack", 1)]
        )
        if rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"runner subscribe rc={rc}")
        if not self.subscribed.wait(8):
            raise TimeoutError("runner subscribe")

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if int(reason_code) != 0:
            raise RuntimeError(f"runner connect reason={reason_code}")
        self.connected.set()

    def _on_subscribe(self, client, userdata, mid, reason_codes, properties):
        self.subscribed.set()

    def _on_message(self, client, userdata, msg):
        now = time.monotonic_ns()
        if getattr(msg, "dup", False):
            self.duplicate_inbound += 1
        if msg.topic == "replaymark/control/ack":
            try:
                body = json.loads(msg.payload.decode("utf-8"))
                nonce = body.get("nonce")
            except Exception:
                nonce = None
            if nonce:
                with self.cv:
                    self.control_acks.add(str(nonce))
                    self.cv.notify_all()
            return

        prefix = f"replaymark/{self.run_id}/"
        if not msg.topic.startswith(prefix):
            return
        kind = msg.topic.rsplit("/", 1)[-1]
        if kind not in RELEVANT_KINDS:
            return
        with self.cv:
            self.relevant_count += 1
            self.relevant_topics[kind] += 1
            if kind == "state":
                try:
                    body = json.loads(msg.payload.decode("utf-8"))
                except Exception:
                    body = {}
                device = str(body.get("device", msg.topic.split("/")[-2]))
                self.states[device].append(
                    {
                        "recv_mono_ns": now,
                        "body": body,
                        "topic": msg.topic,
                        "dup": bool(getattr(msg, "dup", False)),
                    }
                )
            self.cv.notify_all()

    def publish(self, topic: str, body: dict, qos: int = 1) -> int:
        ts = time.monotonic_ns()
        info = self.client.publish(topic, json.dumps(body, sort_keys=True), qos=qos)
        info.wait_for_publish(timeout=5)
        if not info.is_published():
            raise TimeoutError(f"publish {topic}")
        return ts

    def set_state_delay(self, delay_ms: int) -> None:
        for attempt in range(4):
            nonce = uuid.uuid4().hex
            self.publish(
                "replaymark/control",
                {"nonce": nonce, "state_delay_ms": int(delay_ms)},
                qos=1,
            )
            deadline = time.monotonic() + 3
            with self.cv:
                while nonce not in self.control_acks and time.monotonic() < deadline:
                    self.cv.wait(timeout=0.1)
                if nonce in self.control_acks:
                    return
            time.sleep(0.2 * (attempt + 1))
        raise TimeoutError("device control ack")

    def wait_state_until(self, device: str, deadline_ns: int, after_ns: int) -> dict | None:
        with self.cv:
            while True:
                candidates = [
                    e for e in self.states.get(device, []) if e["recv_mono_ns"] >= after_ns
                ]
                if candidates:
                    return min(candidates, key=lambda e: e["recv_mono_ns"])
                remaining = (deadline_ns - time.monotonic_ns()) / 1e9
                if remaining <= 0:
                    return None
                self.cv.wait(timeout=min(remaining, 0.05))

    def wait_relevant_count(self, expected: int, timeout_s: float) -> int:
        deadline = time.monotonic() + timeout_s
        with self.cv:
            while self.relevant_count < expected and time.monotonic() < deadline:
                self.cv.wait(timeout=0.05)
            return self.relevant_count

    def close(self) -> None:
        try:
            self.client.disconnect()
        finally:
            self.client.loop_stop()


class OfflineCollector:
    def __init__(self, broker: str, port: int, run_id: str):
        self.broker = broker
        self.port = port
        self.run_id = run_id
        self.client_id = f"downstream-offline-{run_id}"
        self.phase = "prime"
        self.connected = threading.Event()
        self.subscribed = threading.Event()
        self.disconnected = threading.Event()
        self.session_present_on_drain = False
        self.cv = threading.Condition()
        self.relevant_count = 0
        self.relevant_topics: dict[str, int] = defaultdict(int)
        self.duplicate_count = 0
        self.last_relevant_mono: float | None = None
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.client_id,
            clean_session=False,
            protocol=mqtt.MQTTv311,
        )
        self.client.on_connect = self._on_connect
        self.client.on_subscribe = self._on_subscribe
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if int(reason_code) != 0:
            return
        if self.phase == "drain":
            self.session_present_on_drain = bool(getattr(flags, "session_present", False))
        self.connected.set()
        if self.phase == "prime":
            client.subscribe(f"replaymark/{self.run_id}/#", qos=1)

    def _on_subscribe(self, client, userdata, mid, reason_codes, properties):
        self.subscribed.set()

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        self.disconnected.set()

    def _on_message(self, client, userdata, msg):
        kind = msg.topic.rsplit("/", 1)[-1]
        if kind not in RELEVANT_KINDS:
            return
        with self.cv:
            self.relevant_count += 1
            self.relevant_topics[kind] += 1
            if getattr(msg, "dup", False):
                self.duplicate_count += 1
            self.last_relevant_mono = time.monotonic()
            self.cv.notify_all()

    def prime_and_disconnect(self) -> None:
        self.phase = "prime"
        self.connected.clear()
        self.subscribed.clear()
        self.disconnected.clear()
        self.client.connect(self.broker, self.port, keepalive=30)
        self.client.loop_start()
        if not self.connected.wait(8):
            raise TimeoutError("collector prime connect")
        if not self.subscribed.wait(8):
            raise TimeoutError("collector prime subscribe")
        self.client.disconnect()
        if not self.disconnected.wait(8):
            raise TimeoutError("collector prime disconnect")
        self.client.loop_stop()

    def reconnect_and_drain(self, quiet_s: float = 0.75, timeout_s: float = 20.0) -> dict:
        self.phase = "drain"
        self.connected.clear()
        self.disconnected.clear()
        with self.cv:
            self.relevant_count = 0
            self.relevant_topics.clear()
            self.duplicate_count = 0
            self.last_relevant_mono = None
        self.client.connect(self.broker, self.port, keepalive=30)
        self.client.loop_start()
        if not self.connected.wait(8):
            raise TimeoutError("collector drain connect")
        if not self.session_present_on_drain:
            raise RuntimeError("persistent session was not present on reconnect")

        deadline = time.monotonic() + timeout_s
        while True:
            with self.cv:
                count = self.relevant_count
                last = self.last_relevant_mono
            now = time.monotonic()
            if count > 0 and last is not None and now - last >= quiet_s:
                break
            if now >= deadline:
                raise TimeoutError(
                    f"collector drain did not reach quiet barrier count={count} last={last}"
                )
            time.sleep(0.05)

        self.client.disconnect()
        if not self.disconnected.wait(8):
            raise TimeoutError("collector drain disconnect")
        self.client.loop_stop()
        return {
            "delivered_qos1": self.relevant_count,
            "delivered_by_kind": dict(sorted(self.relevant_topics.items())),
            "duplicate_deliveries": self.duplicate_count,
            "session_present": self.session_present_on_drain,
            "quiet_barrier_s": quiet_s,
        }


def offers(n: int, wave_size: int, wave_period_ms: int, fn):
    base = time.monotonic_ns() + 100_000_000
    rows = []
    with ThreadPoolExecutor(max_workers=n) as pool:
        futures = [
            pool.submit(fn, i, base + (i // wave_size) * int(wave_period_ms * 1e6))
            for i in range(n)
        ]
        for future in as_completed(futures):
            rows.append(future.result())
    return sorted(rows, key=lambda row: row["task_id"])


def command_topic(run_id: str, device: str) -> str:
    return f"replaymark/{run_id}/{device}/command"


def query_topic(run_id: str, device: str) -> str:
    return f"replaymark/{run_id}/{device}/query"


def r1_task(
    h: Harness,
    i: int,
    offer_ns: int,
    verify_ms: int,
    gap_ms: float,
    timeout_ms: int,
) -> dict:
    sleep_until(offer_ns)
    t0 = time.monotonic_ns()
    a = f"task-{i}-a"
    b = f"task-{i}-b"
    deadline = t0 + int(timeout_ms * 1e6)
    verify_deadline = t0 + int(verify_ms * 1e6)

    a1 = h.publish(command_topic(h.run_id, a), {"on": True, "op_id": f"{i}:ACT1"})
    first = h.wait_state_until(a, deadline, after_ns=a1)
    if first is None:
        return {"task_id": i, "success": False, "branch_required": True, "violation": True, "verify": 0}
    branch_required = first["recv_mono_ns"] > verify_deadline
    sleep_until(first["recv_mono_ns"] + int(gap_ms * 1e6))
    b1 = h.publish(command_topic(h.run_id, b), {"on": True, "op_id": f"{i}:ACT2"})
    second = h.wait_state_until(b, deadline, after_ns=b1)
    return {
        "task_id": i,
        "success": second is not None,
        "branch_required": branch_required,
        "violation": branch_required,
        "verify": 0,
        "latency_ms": ((second or first)["recv_mono_ns"] - t0) / 1e6,
    }


def native_task(
    h: Harness,
    i: int,
    offer_ns: int,
    verify_ms: int,
    gap_ms: float,
    timeout_ms: int,
) -> dict:
    """Direct target-controller execution, intentionally separate from the R2 interpreter."""
    sleep_until(offer_ns)
    t0 = time.monotonic_ns()
    a = f"task-{i}-a"
    b = f"task-{i}-b"
    deadline = t0 + int(timeout_ms * 1e6)
    verify_deadline = t0 + int(verify_ms * 1e6)

    a1 = h.publish(command_topic(h.run_id, a), {"on": True, "op_id": f"{i}:ACT1"})
    first = h.wait_state_until(a, verify_deadline, after_ns=a1)
    branch_required = first is None
    verify_count = 0
    if first is None:
        q = h.publish(query_topic(h.run_id, a), {"op_id": f"{i}:VERIFY"})
        verify_count = 1
        first = h.wait_state_until(a, deadline, after_ns=q)
        if first is None:
            return {"task_id": i, "success": False, "branch_required": True, "violation": False, "verify": 1}

    sleep_until(first["recv_mono_ns"] + int(gap_ms * 1e6))
    b1 = h.publish(command_topic(h.run_id, b), {"on": True, "op_id": f"{i}:ACT2"})
    second = h.wait_state_until(b, deadline, after_ns=b1)
    return {
        "task_id": i,
        "success": second is not None,
        "branch_required": branch_required,
        "violation": False,
        "verify": verify_count,
        "latency_ms": ((second or first)["recv_mono_ns"] - t0) / 1e6,
    }


KERNEL = {
    ("after_act1", "confirmed_by_deadline"): ("ACT2", "done"),
    ("after_act1", "not_visible_by_deadline"): ("VERIFY", "verified"),
    ("verified", "confirmed_by_deadline"): ("ACT2", "done"),
    ("verified", "not_visible_by_deadline"): ("ACT2", "done"),
}


def r2_task(
    h: Harness,
    i: int,
    offer_ns: int,
    verify_ms: int,
    gap_ms: float,
    timeout_ms: int,
) -> dict:
    """Semantic replay through an explicit table interpreter, not through native_task()."""
    sleep_until(offer_ns)
    t0 = time.monotonic_ns()
    a = f"task-{i}-a"
    b = f"task-{i}-b"
    deadline = t0 + int(timeout_ms * 1e6)
    verify_deadline = t0 + int(verify_ms * 1e6)

    a1 = h.publish(command_topic(h.run_id, a), {"on": True, "op_id": f"{i}:ACT1"})
    first = h.wait_state_until(a, verify_deadline, after_ns=a1)
    feedback = "confirmed_by_deadline" if first is not None else "not_visible_by_deadline"
    state = "after_act1"
    operation, state = KERNEL[(state, feedback)]
    branch_required = operation == "VERIFY"
    verify_count = 0

    if operation == "VERIFY":
        q = h.publish(query_topic(h.run_id, a), {"op_id": f"{i}:VERIFY"})
        verify_count = 1
        first = h.wait_state_until(a, deadline, after_ns=q)
        if first is None:
            return {"task_id": i, "success": False, "branch_required": True, "violation": False, "verify": 1}
        operation, state = KERNEL[(state, "confirmed_by_deadline")]

    if operation != "ACT2" or state != "done":
        raise RuntimeError(f"kernel ended at operation={operation} state={state}")
    sleep_until(first["recv_mono_ns"] + int(gap_ms * 1e6))
    b1 = h.publish(command_topic(h.run_id, b), {"on": True, "op_id": f"{i}:ACT2"})
    second = h.wait_state_until(b, deadline, after_ns=b1)
    return {
        "task_id": i,
        "success": second is not None,
        "branch_required": branch_required,
        "violation": False,
        "verify": verify_count,
        "latency_ms": ((second or first)["recv_mono_ns"] - t0) / 1e6,
    }


def run_condition(args, mode: str) -> dict:
    run_id = f"q{args.queue_limit}-{mode.lower()}-{uuid.uuid4().hex[:8]}"
    h = Harness(args.broker, args.port, run_id)
    collector = OfflineCollector(args.broker, args.port, run_id)
    try:
        h.set_state_delay(args.target_delay_ms)
        collector.prime_and_disconnect()

        if mode == "R1_TIMING":
            fn = lambda i, o: r1_task(h, i, o, args.verify_ms, args.gap_ms, args.timeout_ms)
            expected = 4 * args.tasks
        elif mode == "TARGET_NATIVE":
            fn = lambda i, o: native_task(h, i, o, args.verify_ms, args.gap_ms, args.timeout_ms)
            expected = 6 * args.tasks
        elif mode == "R2_SEMANTIC":
            fn = lambda i, o: r2_task(h, i, o, args.verify_ms, args.gap_ms, args.timeout_ms)
            expected = 6 * args.tasks
        else:
            raise ValueError(mode)

        rows = offers(args.tasks, args.wave_size, args.wave_period_ms, fn)
        observed = h.wait_relevant_count(expected, timeout_s=10)
        if observed != expected:
            raise RuntimeError(
                f"generated-message conservation failed mode={mode} expected={expected} observed={observed} topics={dict(h.relevant_topics)}"
            )

        drain = collector.reconnect_and_drain(
            quiet_s=args.drain_quiet_s,
            timeout_s=args.drain_timeout_s,
        )
        success_rate = sum(bool(row["success"]) for row in rows) / len(rows)
        violation_fraction = sum(bool(row["violation"]) for row in rows) / len(rows)
        branch_fraction = sum(bool(row["branch_required"]) for row in rows) / len(rows)
        verify_count = sum(int(row["verify"]) for row in rows)
        latencies = [float(row["latency_ms"]) for row in rows if row.get("success") and row.get("latency_ms") is not None]
        delivered = int(drain["delivered_qos1"])
        return {
            "mode": mode,
            "run_id": run_id,
            "tasks": args.tasks,
            "generated_qos1": expected,
            "generated_observer_count": observed,
            "generated_by_kind": dict(sorted(h.relevant_topics.items())),
            "delivered_qos1": delivered,
            "delivered_by_kind": drain["delivered_by_kind"],
            "loss": expected - delivered,
            "lossless": expected == delivered,
            "success_rate": success_rate,
            "support_violation_fraction": violation_fraction,
            "branch_required_fraction": branch_fraction,
            "verify_count": verify_count,
            "p99_task_latency_ms": percentile(latencies, 99),
            "collector_session_present": drain["session_present"],
            "collector_duplicate_deliveries": drain["duplicate_deliveries"],
            "runner_duplicate_inbound": h.duplicate_inbound,
            "drain_quiet_barrier_s": drain["quiet_barrier_s"],
        }
    finally:
        h.close()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--broker", default=os.getenv("BROKER_HOST", "mosquitto"))
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--queue-limit", type=int, required=True)
    p.add_argument("--tasks", type=int, default=128)
    p.add_argument("--wave-size", type=int, default=32)
    p.add_argument("--wave-period-ms", type=int, default=300)
    p.add_argument("--verify-ms", type=int, default=100)
    p.add_argument("--target-delay-ms", type=int, default=150)
    p.add_argument("--gap-ms", type=float, default=20.0)
    p.add_argument("--timeout-ms", type=int, default=1200)
    p.add_argument("--drain-quiet-s", type=float, default=0.75)
    p.add_argument("--drain-timeout-s", type=float, default=20.0)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    modes = ["R1_TIMING", "TARGET_NATIVE", "R2_SEMANTIC"]
    results = []
    for mode in modes:
        results.append(run_condition(args, mode))

    by_mode = {row["mode"]: row for row in results}
    checks = {
        "r1_generated_exact_512": by_mode["R1_TIMING"]["generated_qos1"] == 512,
        "native_generated_exact_768": by_mode["TARGET_NATIVE"]["generated_qos1"] == 768,
        "r2_generated_exact_768": by_mode["R2_SEMANTIC"]["generated_qos1"] == 768,
        "all_tasks_success": all(row["success_rate"] == 1.0 for row in results),
        "r1_support_invalid": by_mode["R1_TIMING"]["support_violation_fraction"] == 1.0,
        "native_support_valid": by_mode["TARGET_NATIVE"]["support_violation_fraction"] == 0.0,
        "r2_support_valid": by_mode["R2_SEMANTIC"]["support_violation_fraction"] == 0.0,
        "native_r2_same_semantic_multiplicity": by_mode["TARGET_NATIVE"]["verify_count"] == by_mode["R2_SEMANTIC"]["verify_count"] == args.tasks,
        "persistent_sessions_present": all(row["collector_session_present"] for row in results),
        "no_collector_duplicates": all(row["collector_duplicate_deliveries"] == 0 for row in results),
    }

    report = {
        "schema": "replaymark.e3b.downstream.queue_capacity_pilot.v1",
        "status": "EXPLORATORY_NOT_CONFIRMATORY",
        "queue_limit": args.queue_limit,
        "parameters": {
            "broker": "eclipse-mosquitto:2.1.2-alpine",
            "tasks": args.tasks,
            "wave_size": args.wave_size,
            "wave_period_ms": args.wave_period_ms,
            "verify_ms": args.verify_ms,
            "target_delay_ms": args.target_delay_ms,
            "post_completion_gap_ms": args.gap_ms,
            "task_timeout_ms": args.timeout_ms,
            "max_queued_messages": args.queue_limit,
            "drain_quiet_barrier_s": args.drain_quiet_s,
        },
        "conditions": results,
        "implementation_checks": checks,
        "pilot_usable": all(checks.values()),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["pilot_usable"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
