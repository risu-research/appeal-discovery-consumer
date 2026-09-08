from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
import threading
import time
import uuid
from typing import Any, Mapping

import paho.mqtt.client as mqtt

from replaymark.execution_admission import ExecutionAdmissionDisposition
from replaymark.runtime_e3b_action import E3B_ACTION_CAPTURE_POINT, E3B_RAW_ACTION_SCHEMA
from replaymark.runtime_e3b_bridge import certify_e3b_shadow_reuse
from replaymark.runtime_e3b_correlation import correlate_e3b_runtime_pair
from replaymark.runtime_e3b_execution_gate import E3bCertifiedExecutionGate
from replaymark.runtime_e3b_observation import E3B_RAW_OBSERVATION_SCHEMA
from replaymark_shadow import E3B_R1_SHADOW_CLOCK_DOMAIN, compile_e3b_r1_shadow_contract

from s3c1_direct_native import (
    CONFIRMED_BY_DEADLINE,
    NOT_VISIBLE_BY_DEADLINE,
    derive_evidence_token,
    execute_direct_native,
)


SCHEMA = "replaymark.s3c1-paired-four-arm-live-cell.v1"
PROTOCOL_HEAD = "274b870313696adaf2f80b52632e9b6ea854fd90"
PROTOCOL_SHA256 = "ac50c3b7ac69397c3af0c5344f85c5eeb7bd77ee5535af920db41564304e5d0f"
HISTORICAL_TEMPLATE_SHA256 = "e86d5f42a09b8257185b6e3608ac83c0ac41deeba7890b914c22b0441a8b8888"
BROKER_VERSION = "mosquitto version 2.1.2"
BROKER_CONFIG_SHA256 = "886f26936b560ebfbf584744c8c4f5f2dd3eeeba946313ad1d2f7f8848bf0858"
BROKER_IMAGE_DIGEST = "sha256:6f8d8a947c506f8a2290ec65cd4bd2bc7cb4d43fb5f6271f861cb013e2ef9797"
BATCH_SIZES = (192, 196, 200, 204, 208)
TRIALS = 6
REPLICAS = ("A", "B")
ARMS = ("ALWAYS_REUSE", "DIRECT_NATIVE", "REPLAYMARK_NATIVE", "ALWAYS_NATIVE")
ARM_CODES = {
    "ALWAYS_REUSE": "ru",
    "DIRECT_NATIVE": "dn",
    "REPLAYMARK_NATIVE": "rn",
    "ALWAYS_NATIVE": "an",
}
CODE_ARMS = {value: key for key, value in ARM_CODES.items()}
LOGICAL_WAVE_SIZE = 4
PHYSICAL_TWINS_PER_WAVE = 16
WAVE_PERIOD_MS = 500.0
VERIFY_MS = 100.0
TASK_TIMEOUT_MS = 1000
POST_CONFIRMATION_GAP_MS = 20.0
QUEUE_LIMIT = 1000
TERMINAL_ROLES = ("command", "query", "state")
FORBIDDEN_QUEUE_DIRECTIVES = (
    "max_queued_messages",
    "max_queued_bytes",
    "max_inflight_messages",
    "queue_qos0_messages",
)
DEVICE_RE = re.compile(
    r"^s3c1-r(?P<replica>[AB])-n(?P<batch>[0-9]+)-t(?P<trial>[0-9]+)-"
    r"(?P<nonce>[A-Za-z0-9]+)-(?P<arm>ru|dn|rn|an)-(?P<task>[0-9]+)-(?P<role>a|b)$"
)


def _sleep_until_ns(target_ns: int) -> None:
    while True:
        remaining = target_ns - time.monotonic_ns()
        if remaining <= 0:
            return
        time.sleep(min(remaining / 1e9, 0.02))


def _wait_connected(client: mqtt.Client, timeout_s: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not client.is_connected():
        if time.monotonic() >= deadline:
            raise TimeoutError("MQTT client did not connect")
        time.sleep(0.01)


def arm_prefix(replica: str, batch_size: int, trial: int, nonce: str, arm: str) -> str:
    if replica not in REPLICAS or batch_size not in BATCH_SIZES or trial not in range(TRIALS):
        raise ValueError("cell outside frozen S3-C1 matrix")
    return f"s3c1-r{replica}-n{batch_size}-t{trial}-{nonce}-{ARM_CODES[arm]}"


def device_for(replica: str, batch_size: int, trial: int, nonce: str, arm: str,
               task_id: int, role: str) -> str:
    if task_id not in range(batch_size) or role not in {"a", "b"}:
        raise ValueError("task/device outside frozen cell")
    return f"{arm_prefix(replica, batch_size, trial, nonce, arm)}-{task_id}-{role}"


def parse_device(device: str) -> dict[str, object]:
    match = DEVICE_RE.fullmatch(device)
    if match is None:
        raise ValueError("foreign device namespace")
    g = match.groupdict()
    batch = int(g["batch"])
    trial = int(g["trial"])
    task_id = int(g["task"])
    if str(batch) != g["batch"] or str(trial) != g["trial"] or str(task_id) != g["task"]:
        raise ValueError("non-canonical decimal namespace")
    if batch not in BATCH_SIZES or trial not in range(TRIALS) or task_id not in range(batch):
        raise ValueError("namespace outside frozen matrix")
    return {
        "replica": g["replica"],
        "batch_size": batch,
        "trial": trial,
        "nonce": g["nonce"],
        "arm": CODE_ARMS[g["arm"]],
        "task_id": task_id,
        "role": g["role"],
    }


class OnlineLedger:
    """Independent online observer plus the live application's MQTT publishing client."""

    def __init__(self, broker: str, port: int):
        self.cv = threading.Condition()
        self.events: list[dict[str, object]] = []
        self.state_events: dict[str, list[dict[str, object]]] = {}
        self.sys_values: dict[str, str] = {}
        self._subscribed = threading.Event()
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"s3c1-ledger-{uuid.uuid4().hex[:12]}",
            protocol=mqtt.MQTTv311,
        )
        self.client.on_connect = self._on_connect
        self.client.on_subscribe = self._on_subscribe
        self.client.on_message = self._on_message
        self.client.connect(broker, port, keepalive=30)
        self.client.loop_start()
        _wait_connected(self.client)
        if not self._subscribed.wait(10):
            raise TimeoutError("online ledger subscriptions were not acknowledged")

    def _on_connect(self, c, _userdata, _flags, reason_code, _properties) -> None:
        if reason_code != 0:
            return
        c.subscribe(
            [
                ("agentmark/+/command", 1),
                ("agentmark/+/query", 1),
                ("agentmark/+/state", 1),
                ("$SYS/broker/version", 0),
            ]
        )

    def _on_subscribe(self, _c, _userdata, _mid, _reason_codes, _properties) -> None:
        self._subscribed.set()

    def _on_message(self, _c, _userdata, msg) -> None:
        now = time.monotonic_ns()
        payload = msg.payload.decode("utf-8", errors="strict")
        if msg.topic == "$SYS/broker/version":
            with self.cv:
                self.sys_values[msg.topic] = payload
                self.cv.notify_all()
            return
        event = {
            "seq": None,
            "topic": msg.topic,
            "payload_utf8": payload,
            "qos": int(msg.qos),
            "retain": bool(msg.retain),
            "dup": bool(msg.dup),
            "recv_mono_ns": now,
        }
        parts = msg.topic.split("/")
        if len(parts) == 3 and parts[0] == "agentmark":
            event["device"] = parts[1]
            event["terminal_role"] = parts[2]
            if parts[2] == "state":
                body = json.loads(payload)
                event["state"] = {
                    "device": body.get("device"),
                    "on": body.get("on"),
                    "cause": body.get("cause"),
                    "ts_mono_ns": body.get("ts_mono_ns"),
                }
        with self.cv:
            event["seq"] = len(self.events)
            self.events.append(event)
            if event.get("terminal_role") == "state":
                device = str(event.get("device"))
                state = dict(event["state"])
                state["recv_mono_ns"] = now
                state["seq"] = event["seq"]
                self.state_events.setdefault(device, []).append(state)
            self.cv.notify_all()

    def broker_version(self, timeout_s: float = 5.0) -> str | None:
        deadline = time.monotonic() + timeout_s
        with self.cv:
            while "$SYS/broker/version" not in self.sys_values:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self.cv.wait(remaining)
            return self.sys_values["$SYS/broker/version"]

    def wait_query_confirmation(self, device: str, after_ns: int, timeout_ns: int) -> dict[str, object] | None:
        with self.cv:
            while True:
                matches = [
                    e for e in self.state_events.get(device, ())
                    if isinstance(e.get("recv_mono_ns"), int)
                    and after_ns <= int(e["recv_mono_ns"]) <= timeout_ns
                    and e.get("cause") == "query"
                    and e.get("on") is True
                ]
                if matches:
                    return dict(min(matches, key=lambda e: int(e["recv_mono_ns"])))
                remaining = timeout_ns - time.monotonic_ns()
                if remaining <= 0:
                    return None
                self.cv.wait(remaining / 1e9)

    def wait_command_state(self, device: str, after_ns: int, timeout_ns: int) -> bool:
        with self.cv:
            while True:
                if any(
                    isinstance(e.get("recv_mono_ns"), int)
                    and after_ns <= int(e["recv_mono_ns"]) <= timeout_ns
                    and e.get("cause") == "command"
                    and e.get("on") is True
                    for e in self.state_events.get(device, ())
                ):
                    return True
                remaining = timeout_ns - time.monotonic_ns()
                if remaining <= 0:
                    return False
                self.cv.wait(remaining / 1e9)

    def close(self) -> None:
        self.client.disconnect()
        self.client.loop_stop()


class PersistentArmCollector:
    """One broker-persistent offline session for exactly one arm's explicit device set."""

    def __init__(self, broker: str, port: int, *, cell_key: str, arm: str,
                 devices: list[str]):
        digest = hashlib.sha256(f"{cell_key}|{arm}".encode("utf-8")).hexdigest()[:20]
        self.client_id = f"s3c1q-{digest}"
        self.arm = arm
        self.devices = tuple(devices)
        self.filters = tuple(f"agentmark/{device}/#" for device in devices)
        self.deliveries: list[dict[str, object]] = []
        self.session_present_on_drain: bool | None = None
        self._prime = True
        self._connected = threading.Event()
        self._subscribed = threading.Event()
        self._last_message_mono = 0.0
        self._lock = threading.Lock()
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.client_id,
            clean_session=False,
            protocol=mqtt.MQTTv311,
        )
        self.client.on_connect = self._on_connect
        self.client.on_subscribe = self._on_subscribe
        self.client.on_message = self._on_message
        self.broker = broker
        self.port = port

    def _on_connect(self, c, _userdata, flags, reason_code, _properties) -> None:
        if reason_code != 0:
            return
        if self._prime:
            c.subscribe([(topic, 1) for topic in self.filters])
        else:
            self.session_present_on_drain = bool(getattr(flags, "session_present", False))
        self._connected.set()

    def _on_subscribe(self, _c, _userdata, _mid, _reason_codes, _properties) -> None:
        if self._prime:
            self._subscribed.set()

    def _on_message(self, _c, _userdata, msg) -> None:
        now = time.monotonic_ns()
        record = {
            "seq": None,
            "topic": msg.topic,
            "payload_utf8": msg.payload.decode("utf-8", errors="strict"),
            "qos": int(msg.qos),
            "retain": bool(msg.retain),
            "dup": bool(msg.dup),
            "recv_mono_ns": now,
        }
        with self._lock:
            record["seq"] = len(self.deliveries)
            self.deliveries.append(record)
            self._last_message_mono = time.monotonic()

    def prime_and_go_offline(self) -> None:
        self._prime = True
        self._connected.clear()
        self._subscribed.clear()
        self.client.connect(self.broker, self.port, keepalive=30)
        self.client.loop_start()
        if not self._connected.wait(10):
            raise TimeoutError("persistent collector did not connect for priming")
        if not self._subscribed.wait(10):
            raise TimeoutError("persistent collector filters were not acknowledged")
        self.client.disconnect()
        self.client.loop_stop()
        self._connected.clear()

    def reconnect_and_drain(self, quiet_s: float = 0.75, timeout_s: float = 30.0) -> dict[str, object]:
        self._prime = False
        self._connected.clear()
        self._last_message_mono = time.monotonic()
        self.client.connect(self.broker, self.port, keepalive=30)
        self.client.loop_start()
        if not self._connected.wait(10):
            raise TimeoutError("persistent collector did not reconnect")
        deadline = time.monotonic() + timeout_s
        while True:
            with self._lock:
                last = self._last_message_mono
                count = len(self.deliveries)
            now = time.monotonic()
            if now - last >= quiet_s:
                break
            if now >= deadline:
                break
            time.sleep(0.02)
        self.client.disconnect()
        self.client.loop_stop()
        return {
            "arm": self.arm,
            "client_id": self.client_id,
            "clean_session": False,
            "filters": list(self.filters),
            "session_present": self.session_present_on_drain,
            "delivery_count": len(self.deliveries),
            "deliveries": self.deliveries,
        }


class PublishRecorder:
    def __init__(self, client: mqtt.Client):
        self.client = client
        self.calls: list[dict[str, object]] = []
        self._lock = threading.Lock()

    def publish(self, *, arm: str, task_id: int, channel: str, topic: str,
                payload_utf8: str, qos: int = 1, retain: bool = False,
                properties: object = None, wait_for_publish: bool = True):
        stamp = time.monotonic_ns()
        record = {
            "seq": None,
            "arm": arm,
            "task_id": task_id,
            "channel": channel,
            "topic": topic,
            "payload_utf8": payload_utf8,
            "qos": qos,
            "retain": retain,
            "properties": properties,
            "publish_mono_ns": stamp,
        }
        with self._lock:
            record["seq"] = len(self.calls)
            self.calls.append(record)
        info = self.client.publish(
            topic, payload_utf8, qos=qos, retain=retain, properties=properties
        )
        if wait_for_publish:
            info.wait_for_publish(timeout=5)
        return record, info


class HistoricalSink:
    """The only sink owned by the frozen S1 gate; metadata is fixed to RM arm per gate."""

    def __init__(self, recorder: PublishRecorder, *, arm: str, task_id: int):
        self.recorder = recorder
        self.arm = arm
        self.task_id = task_id
        self.last_record: dict[str, object] | None = None

    def publish(self, topic: object, payload: object = None, qos: object = 0,
                retain: object = False, properties: object = None):
        record, info = self.recorder.publish(
            arm=self.arm,
            task_id=self.task_id,
            channel="HISTORICAL_ACT2",
            topic=str(topic),
            payload_utf8=str(payload),
            qos=int(qos),
            retain=bool(retain),
            properties=properties,
            wait_for_publish=False,
        )
        self.last_record = record
        return info


def _raw_historical_act2(prefix: str, task_id: int) -> dict[str, object]:
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


def _snapshot(ledger: OnlineLedger, *, device: str, command_publish_ns: int,
              deadline_ns: int, closed_at_ns: int) -> dict[str, object]:
    with ledger.cv:
        rows = list(ledger.state_events.get(device, ()))
    events = []
    for event in rows:
        recv = event.get("recv_mono_ns")
        if isinstance(recv, bool) or not isinstance(recv, int) or recv > closed_at_ns:
            continue
        events.append({
            "event_id": f"s3c1:{device}:{event['seq']}",
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
        "closed_at_mono_ns": closed_at_ns,
        "events": events,
    }


def _query_and_confirm(
    ledger: OnlineLedger,
    recorder: PublishRecorder,
    *,
    replica: str,
    batch_size: int,
    trial: int,
    nonce: str,
    arm: str,
    task_id: int,
) -> dict[str, object]:
    device_a = device_for(replica, batch_size, trial, nonce, arm, task_id, "a")
    call, _ = recorder.publish(
        arm=arm,
        task_id=task_id,
        channel="NATIVE_QUERY_A",
        topic=f"agentmark/{device_a}/query",
        payload_utf8="{}",
    )
    timeout_ns = int(call["publish_mono_ns"]) + int(TASK_TIMEOUT_MS * 1e6)
    confirmation = ledger.wait_query_confirmation(
        device_a, int(call["publish_mono_ns"]), timeout_ns
    )
    if confirmation is None:
        raise TimeoutError("query current-state confirmation not observed")
    gap_target = int(confirmation["recv_mono_ns"]) + int(POST_CONFIRMATION_GAP_MS * 1e6)
    _sleep_until_ns(gap_target)
    return {
        "query_call_seq": call["seq"],
        "confirmation": confirmation,
        "post_confirmation_gap_ms": POST_CONFIRMATION_GAP_MS,
    }


def _fresh_act2(
    recorder: PublishRecorder,
    *,
    replica: str,
    batch_size: int,
    trial: int,
    nonce: str,
    arm: str,
    task_id: int,
) -> dict[str, object]:
    device_b = device_for(replica, batch_size, trial, nonce, arm, task_id, "b")
    call, _ = recorder.publish(
        arm=arm,
        task_id=task_id,
        channel="NATIVE_FRESH_ACT2",
        topic=f"agentmark/{device_b}/command",
        payload_utf8='{"on": true}',
    )
    return call


def _broker_attestation(config_path: Path, supplied_image_digest: str) -> dict[str, object]:
    raw = config_path.read_bytes()
    text = raw.decode("utf-8")
    active = [
        line.strip().split()[0]
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    forbidden_present = sorted(set(active) & set(FORBIDDEN_QUEUE_DIRECTIVES))
    return {
        "config_path": str(config_path),
        "config_utf8": text,
        "config_sha256": hashlib.sha256(raw).hexdigest(),
        "forbidden_queue_directives_present": forbidden_present,
        "supplied_image_digest": supplied_image_digest,
    }


def run_cell(*, broker: str, port: int, replica: str, batch_size: int, trial: int,
             nonce: str, config_path: Path, broker_image_digest: str) -> dict[str, object]:
    if replica not in REPLICAS or batch_size not in BATCH_SIZES or trial not in range(TRIALS):
        raise ValueError("cell outside frozen matrix")
    if not nonce.isascii() or not nonce.isalnum():
        raise ValueError("nonce must be ASCII alphanumeric")

    cell_key = f"{replica}:{batch_size}:{trial}:{nonce}"
    ledger = OnlineLedger(broker, port)
    recorder = PublishRecorder(ledger.client)
    broker_version = ledger.broker_version()
    attestation = _broker_attestation(config_path, broker_image_digest)

    collectors: dict[str, PersistentArmCollector] = {}
    for arm in ARMS:
        devices = [
            device_for(replica, batch_size, trial, nonce, arm, task_id, role)
            for task_id in range(batch_size)
            for role in ("a", "b")
        ]
        collector = PersistentArmCollector(
            broker, port, cell_key=cell_key, arm=arm, devices=devices
        )
        collector.prime_and_go_offline()
        collectors[arm] = collector

    contract = compile_e3b_r1_shadow_contract()
    task_rows: dict[int, dict[str, object]] = {
        task_id: {"task_id": task_id, "arms": {}} for task_id in range(batch_size)
    }
    wave_reports: list[dict[str, object]] = []
    base_ns = time.monotonic_ns() + int(50e6)

    try:
        for wave_index, start_id in enumerate(range(0, batch_size, LOGICAL_WAVE_SIZE)):
            scheduled_ns = base_ns + int(wave_index * WAVE_PERIOD_MS * 1e6)
            _sleep_until_ns(scheduled_ns)
            wave_ids = list(range(start_id, min(start_id + LOGICAL_WAVE_SIZE, batch_size)))
            wave_start_ns = time.monotonic_ns()

            phase_a: dict[tuple[str, int], dict[str, int]] = {}
            for task_id in wave_ids:
                for arm in ARMS:
                    device_a = device_for(
                        replica, batch_size, trial, nonce, arm, task_id, "a"
                    )
                    call, _ = recorder.publish(
                        arm=arm,
                        task_id=task_id,
                        channel="ACT1",
                        topic=f"agentmark/{device_a}/command",
                        payload_utf8='{"on": true}',
                    )
                    act1_ns = int(call["publish_mono_ns"])
                    phase_a[(arm, task_id)] = {
                        "act1_publish_mono_ns": act1_ns,
                        "verify_deadline_mono_ns": act1_ns + int(VERIFY_MS * 1e6),
                        "timeout_deadline_mono_ns": act1_ns + int(TASK_TIMEOUT_MS * 1e6),
                    }

            max_deadline = max(v["verify_deadline_mono_ns"] for v in phase_a.values())
            _sleep_until_ns(max_deadline)
            closed_at = time.monotonic_ns()

            for task_id in wave_ids:
                for arm in ARMS:
                    timing = phase_a[(arm, task_id)]
                    device_a = device_for(
                        replica, batch_size, trial, nonce, arm, task_id, "a"
                    )
                    raw = _snapshot(
                        ledger,
                        device=device_a,
                        command_publish_ns=timing["act1_publish_mono_ns"],
                        deadline_ns=timing["verify_deadline_mono_ns"],
                        closed_at_ns=closed_at,
                    )
                    task_rows[task_id]["arms"][arm] = {
                        "raw_observation": raw,
                        "dispatch": {},
                        "errors": [],
                    }

            # Freeze/certify every RM candidate for the wave before any post-snapshot traffic.
            rm_prepared: dict[int, dict[str, object]] = {}
            for task_id in wave_ids:
                arm = "REPLAYMARK_NATIVE"
                prefix = arm_prefix(replica, batch_size, trial, nonce, arm)
                raw_action = _raw_historical_act2(prefix, task_id)
                raw_observation = task_rows[task_id]["arms"][arm]["raw_observation"]
                try:
                    pair = correlate_e3b_runtime_pair(raw_observation, raw_action)
                    certificate = certify_e3b_shadow_reuse(contract, pair)
                    rm_prepared[task_id] = {
                        "raw_action": raw_action,
                        "certificate": certificate,
                        "certificate_record": certificate.canonical_record(),
                        "certificate_fingerprint": certificate.fingerprint(),
                    }
                except Exception as exc:
                    task_rows[task_id]["arms"][arm]["errors"].append(
                        f"CERTIFY:{type(exc).__name__}:{exc}"
                    )

            b_command_stamps: list[tuple[str, int]] = []

            def dispatch_one(task_id: int, arm: str) -> tuple[str, int] | None:
                armrow = task_rows[task_id]["arms"][arm]
                try:
                    if arm == "ALWAYS_REUSE":
                        prefix = arm_prefix(replica, batch_size, trial, nonce, arm)
                        raw_action = _raw_historical_act2(prefix, task_id)
                        call, _ = recorder.publish(
                            arm=arm,
                            task_id=task_id,
                            channel="HISTORICAL_ACT2",
                            topic=str(raw_action["topic"]),
                            payload_utf8=str(raw_action["payload_utf8"]),
                            qos=int(raw_action["qos"]),
                            retain=bool(raw_action["retain"]),
                            properties=raw_action["properties"],
                        )
                        armrow["dispatch"] = {
                            "route": "BASELINE_ALWAYS_REUSE",
                            "raw_action": raw_action,
                            "historical_call_seq": call["seq"],
                        }
                        return (
                            device_for(replica, batch_size, trial, nonce, arm, task_id, "b"),
                            int(call["publish_mono_ns"]),
                        )

                    if arm == "DIRECT_NATIVE":
                        direct_token = derive_evidence_token(armrow["raw_observation"])
                        last_fresh: dict[str, object] = {}

                        def q() -> Mapping[str, object]:
                            return _query_and_confirm(
                                ledger, recorder, replica=replica, batch_size=batch_size,
                                trial=trial, nonce=nonce, arm=arm, task_id=task_id
                            )

                        def f() -> Mapping[str, object]:
                            fresh = _fresh_act2(
                                recorder, replica=replica, batch_size=batch_size,
                                trial=trial, nonce=nonce, arm=arm, task_id=task_id
                            )
                            last_fresh.clear()
                            last_fresh.update(fresh)
                            return fresh

                        decision = execute_direct_native(
                            direct_token, query_and_confirm=q, fresh_act2=f
                        )
                        armrow["dispatch"] = {
                            "route": decision.route,
                            "live_direct_evidence_token": direct_token,
                            "query_confirmation": decision.query_confirmation,
                            "fresh_act2_call_seq": decision.fresh_act2["seq"],
                        }
                        return (
                            device_for(replica, batch_size, trial, nonce, arm, task_id, "b"),
                            int(last_fresh["publish_mono_ns"]),
                        )

                    if arm == "REPLAYMARK_NATIVE":
                        prepared = rm_prepared[task_id]
                        raw_action = prepared["raw_action"]
                        certificate = prepared["certificate"]
                        sink = HistoricalSink(recorder, arm=arm, task_id=task_id)
                        gate = E3bCertifiedExecutionGate(sink)
                        receipt = gate.dispatch(
                            contract, armrow["raw_observation"], raw_action, certificate
                        )
                        disposition = receipt.execution_disposition
                        armrow["dispatch"] = {
                            "certificate_record": prepared["certificate_record"],
                            "certificate_fingerprint": prepared["certificate_fingerprint"],
                            "receipt": receipt.canonical_record(),
                            "gate_consumed_count": gate.consumed_count,
                        }
                        if disposition is ExecutionAdmissionDisposition.ADMIT_REUSE:
                            armrow["dispatch"]["route"] = "ADMIT_REUSE"
                            if sink.last_record is None:
                                raise RuntimeError("S1 admitted reuse without historical sink call")
                            bstamp = int(sink.last_record["publish_mono_ns"])
                        else:
                            armrow["dispatch"]["route"] = "BLOCK_REUSE_CALLER_NATIVE"
                            confirmation = _query_and_confirm(
                                ledger, recorder, replica=replica, batch_size=batch_size,
                                trial=trial, nonce=nonce, arm=arm, task_id=task_id
                            )
                            fresh = _fresh_act2(
                                recorder, replica=replica, batch_size=batch_size,
                                trial=trial, nonce=nonce, arm=arm, task_id=task_id
                            )
                            armrow["dispatch"]["query_confirmation"] = confirmation
                            armrow["dispatch"]["fresh_act2_call_seq"] = fresh["seq"]
                            bstamp = int(fresh["publish_mono_ns"])
                        return (
                            device_for(replica, batch_size, trial, nonce, arm, task_id, "b"),
                            bstamp,
                        )

                    if arm == "ALWAYS_NATIVE":
                        confirmation = _query_and_confirm(
                            ledger, recorder, replica=replica, batch_size=batch_size,
                            trial=trial, nonce=nonce, arm=arm, task_id=task_id
                        )
                        fresh = _fresh_act2(
                            recorder, replica=replica, batch_size=batch_size,
                            trial=trial, nonce=nonce, arm=arm, task_id=task_id
                        )
                        armrow["dispatch"] = {
                            "route": "BASELINE_ALWAYS_NATIVE",
                            "query_confirmation": confirmation,
                            "fresh_act2_call_seq": fresh["seq"],
                        }
                        return (
                            device_for(replica, batch_size, trial, nonce, arm, task_id, "b"),
                            int(fresh["publish_mono_ns"]),
                        )
                    raise AssertionError(f"unknown arm {arm}")
                except Exception as exc:
                    armrow["errors"].append(f"DISPATCH:{type(exc).__name__}:{exc}")
                    return None

            # The frozen 500ms wave period is feasible only if the 16 paired post-snapshot
            # paths are allowed to proceed concurrently. No arm result is fed to another.
            with ThreadPoolExecutor(max_workers=PHYSICAL_TWINS_PER_WAVE) as pool:
                futures = [
                    pool.submit(dispatch_one, task_id, arm)
                    for task_id in wave_ids
                    for arm in ARMS
                ]
                for future in as_completed(futures):
                    result = future.result()
                    if result is not None:
                        b_command_stamps.append(result)

            # Fail-closed quiescence accounting, but preserve raw workload rows rather than exclude failures.
            quiescence_missing: list[str] = []
            for task_id in wave_ids:
                for arm in ARMS:
                    timing = phase_a[(arm, task_id)]
                    device_a = device_for(
                        replica, batch_size, trial, nonce, arm, task_id, "a"
                    )
                    if not ledger.wait_command_state(
                        device_a,
                        timing["act1_publish_mono_ns"],
                        timing["timeout_deadline_mono_ns"],
                    ):
                        quiescence_missing.append(f"{arm}:{task_id}:a")
            for device_b, stamp in b_command_stamps:
                if not ledger.wait_command_state(
                    device_b, stamp, stamp + int(TASK_TIMEOUT_MS * 1e6)
                ):
                    quiescence_missing.append(f"{device_b}:b")
            time.sleep(0.05)
            wave_end_ns = time.monotonic_ns()
            next_scheduled = base_ns + int((wave_index + 1) * WAVE_PERIOD_MS * 1e6)
            overrun = wave_end_ns > next_scheduled and start_id + LOGICAL_WAVE_SIZE < batch_size
            wave_reports.append({
                "wave_index": wave_index,
                "task_ids": wave_ids,
                "scheduled_start_mono_ns": scheduled_ns,
                "actual_start_mono_ns": wave_start_ns,
                "snapshot_closed_at_mono_ns": closed_at,
                "post_decision_quiescence_mono_ns": wave_end_ns,
                "quiescence_missing": quiescence_missing,
                "next_wave_schedule_overrun": overrun,
            })

        workload_complete_ns = time.monotonic_ns()
    finally:
        # No scientific evaluation is imported or executed here.
        ledger.close()

    collector_reports: dict[str, object] = {}
    for arm in ARMS:
        try:
            collector_reports[arm] = collectors[arm].reconnect_and_drain()
        except Exception as exc:
            collector_reports[arm] = {
                "arm": arm,
                "client_id": collectors[arm].client_id,
                "clean_session": False,
                "filters": list(collectors[arm].filters),
                "session_present": False,
                "delivery_count": len(collectors[arm].deliveries),
                "deliveries": collectors[arm].deliveries,
                "drain_error": f"{type(exc).__name__}:{exc}",
            }

    return {
        "schema": SCHEMA,
        "protocol_head": PROTOCOL_HEAD,
        "protocol_sha256": PROTOCOL_SHA256,
        "historical_template_sha256": HISTORICAL_TEMPLATE_SHA256,
        "cell": {
            "replica": replica,
            "batch_size": batch_size,
            "trial": trial,
            "nonce": nonce,
        },
        "frozen_parameters": {
            "arms": list(ARMS),
            "logical_wave_size": LOGICAL_WAVE_SIZE,
            "physical_four_arm_twins_per_wave": PHYSICAL_TWINS_PER_WAVE,
            "wave_period_ms": WAVE_PERIOD_MS,
            "verify_deadline_ms": VERIFY_MS,
            "task_timeout_ms": TASK_TIMEOUT_MS,
            "post_confirmation_gap_ms": POST_CONFIRMATION_GAP_MS,
            "persistent_queue_limit": QUEUE_LIMIT,
        },
        "broker_attestation": {
            **attestation,
            "observed_version": broker_version,
            "required_version": BROKER_VERSION,
            "required_config_sha256": BROKER_CONFIG_SHA256,
            "required_image_digest": BROKER_IMAGE_DIGEST,
        },
        "tasks": [task_rows[i] for i in range(batch_size)],
        "waves": wave_reports,
        "application_publish_provenance": recorder.calls,
        "online_role_ledger": ledger.events,
        "persistent_collectors": collector_reports,
        "workload_complete_mono_ns": workload_complete_ns,
        "scientific_verdict_in_live_runner": False,
        "independent_oracle_used_in_live_runner": False,
        "fallback_inside_replaymark": False,
        "regeneration_inside_replaymark": False,
        "automatic_retry": "ABSENT",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--broker", default="mosquitto")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--replica", choices=REPLICAS, required=True)
    parser.add_argument("--batch-size", type=int, choices=BATCH_SIZES, required=True)
    parser.add_argument("--trial", type=int, choices=range(TRIALS), required=True)
    parser.add_argument("--nonce", default=None)
    parser.add_argument("--config-path", required=True)
    parser.add_argument("--broker-image-digest", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    nonce = args.nonce or uuid.uuid4().hex[:12]
    report = run_cell(
        broker=args.broker,
        port=args.port,
        replica=args.replica,
        batch_size=args.batch_size,
        trial=args.trial,
        nonce=nonce,
        config_path=Path(args.config_path),
        broker_image_digest=args.broker_image_digest,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
