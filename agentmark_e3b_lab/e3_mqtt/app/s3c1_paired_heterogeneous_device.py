from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
import threading
import time

import paho.mqtt.client as mqtt


CLASS_SEED = "replaymark.s3c1.paired-target-class.v1|c0=94584db84bebd73e664f19f0fe2d3b9f5998c813"
BATCH_SIZES = (192, 196, 200, 204, 208)
TRIALS = 6
REFERENCE_DELAY_MS = 0
SHIFTED_DELAY_MS = 180
ARM_CODES = frozenset({"ru", "dn", "rn", "an"})

states: defaultdict[str, bool] = defaultdict(bool)
lock = threading.Lock()
client: mqtt.Client | None = None


@dataclass(frozen=True)
class DeviceRef:
    replica: str
    batch_size: int
    trial: int
    nonce: str
    arm_code: str
    task_id: int
    role: str


def shifted_tasks(batch_size: int, trial: int) -> frozenset[int]:
    if batch_size not in BATCH_SIZES:
        raise ValueError("batch size outside frozen S3-C1 ladder")
    if trial not in range(TRIALS):
        raise ValueError("trial outside frozen S3-C1 range")
    ranked = sorted(
        (
            hashlib.sha256(
                f"{CLASS_SEED}|batch={batch_size}|trial={trial}|task={task_id}".encode("utf-8")
            ).hexdigest(),
            task_id,
        )
        for task_id in range(batch_size)
    )
    return frozenset(task_id for _digest, task_id in ranked[: batch_size // 2])


_SHIFTED = {
    (batch_size, trial): shifted_tasks(batch_size, trial)
    for batch_size in BATCH_SIZES
    for trial in range(TRIALS)
}


def _canonical_uint(text: str, what: str) -> int:
    if not text or not text.isascii() or not text.isdigit():
        raise ValueError(f"{what} must be canonical decimal")
    value = int(text)
    if str(value) != text:
        raise ValueError(f"{what} must be canonical decimal")
    return value


def parse_device(device: str) -> DeviceRef:
    parts = device.split("-")
    if len(parts) != 8 or parts[0] != "s3c1":
        raise ValueError("foreign S3-C1 namespace")
    replica_token, batch_token, trial_token, nonce, arm_code, task_text, role = parts[1:]
    if replica_token not in {"rA", "rB"}:
        raise ValueError("replica outside frozen set")
    if not batch_token.startswith("n"):
        raise ValueError("batch token malformed")
    if not trial_token.startswith("t"):
        raise ValueError("trial token malformed")
    if not nonce or not nonce.isascii() or not nonce.isalnum():
        raise ValueError("nonce must be non-empty ASCII alphanumeric")
    if arm_code not in ARM_CODES:
        raise ValueError("arm code outside frozen set")
    if role not in {"a", "b"}:
        raise ValueError("role must be a or b")

    batch_size = _canonical_uint(batch_token[1:], "batch size")
    trial = _canonical_uint(trial_token[1:], "trial")
    task_id = _canonical_uint(task_text, "task id")
    if batch_size not in BATCH_SIZES:
        raise ValueError("batch size outside frozen ladder")
    if trial not in range(TRIALS):
        raise ValueError("trial outside frozen range")
    if task_id not in range(batch_size):
        raise ValueError("task id outside frozen cell")

    return DeviceRef(
        replica=replica_token[1:],
        batch_size=batch_size,
        trial=trial,
        nonce=nonce,
        arm_code=arm_code,
        task_id=task_id,
        role=role,
    )


def delay_for_task(batch_size: int, trial: int, task_id: int) -> int:
    """Class selection intentionally has no arm/policy/certificate/oracle input."""
    if task_id not in range(batch_size):
        raise ValueError("task outside frozen cell")
    return SHIFTED_DELAY_MS if task_id in _SHIFTED[(batch_size, trial)] else REFERENCE_DELAY_MS


def delay_for_device(device: str) -> int:
    ref = parse_device(device)
    return delay_for_task(ref.batch_size, ref.trial, ref.task_id)


def publish_state(device: str, cause: str) -> None:
    assert client is not None
    with lock:
        value = states[device]
    payload = json.dumps(
        {
            "device": device,
            "on": value,
            "cause": cause,
            "ts_mono_ns": time.monotonic_ns(),
        },
        sort_keys=True,
    )
    client.publish(f"agentmark/{device}/state", payload, qos=1, retain=False)


def schedule_state(device: str, cause: str, delay_ms: int) -> None:
    if delay_ms <= 0:
        publish_state(device, cause)
        return
    timer = threading.Timer(delay_ms / 1000.0, publish_state, args=(device, cause))
    timer.daemon = True
    timer.start()


def on_connect(c, _userdata, _flags, reason_code, _properties) -> None:
    if reason_code != 0:
        raise RuntimeError(f"target connect failed: {reason_code}")
    c.subscribe("agentmark/+/command", qos=1)
    c.subscribe("agentmark/+/query", qos=1)
    print(json.dumps({"ready": True, "gate": "S3-C1"}, sort_keys=True), flush=True)


def on_message(_c, _userdata, msg) -> None:
    parts = msg.topic.split("/")
    if len(parts) != 3 or parts[0] != "agentmark":
        return
    _, device, kind = parts
    try:
        delay_ms = delay_for_device(device)
    except ValueError:
        return

    text = msg.payload.decode("utf-8", errors="strict")
    if kind == "command":
        body = json.loads(text)
        with lock:
            states[device] = bool(body.get("on", True))
        schedule_state(device, "command", delay_ms)
    elif kind == "query":
        publish_state(device, "query")


def main() -> None:
    global client
    parser = argparse.ArgumentParser()
    parser.add_argument("--broker", default="mosquitto")
    parser.add_argument("--port", type=int, default=1883)
    args = parser.parse_args()

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="replaymark-s3c1-paired-target",
        protocol=mqtt.MQTTv311,
    )
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.broker, args.port, keepalive=30)
    client.loop_forever()


if __name__ == "__main__":
    main()
