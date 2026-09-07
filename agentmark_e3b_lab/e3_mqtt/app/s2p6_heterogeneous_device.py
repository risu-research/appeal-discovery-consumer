from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import threading
import time

import paho.mqtt.client as mqtt

CLASS_SEED = "replaymark.s2p6.target-class.v1|q3=ef370c38e6be82df340838be9db394559367c53e"
REFERENCE_DELAY_MS = 0
SHIFTED_DELAY_MS = 180
TRIALS = 6
BLOCKS_PER_TRIAL = 64
TASKS_PER_TRIAL = 192

states: defaultdict[str, bool] = defaultdict(bool)
lock = threading.Lock()
client: mqtt.Client | None = None

def reference_blocks(trial: int) -> frozenset[int]:
    ranked = sorted(
        (
            hashlib.sha256(
                f"{CLASS_SEED}|trial={trial}|block={block}".encode("utf-8")
            ).hexdigest(),
            block,
        )
        for block in range(BLOCKS_PER_TRIAL)
    )
    return frozenset(block for _digest, block in ranked[: BLOCKS_PER_TRIAL // 2])

REFERENCE_BLOCKS = tuple(reference_blocks(trial) for trial in range(TRIALS))

def delay_for_device(device: str) -> int:
    try:
        prefix, task_text, role = device.rsplit("-", 2)
    except ValueError as exc:
        raise ValueError("P6 device must encode prefix-task-role") from exc
    parts = prefix.split("-")
    if len(parts) != 3 or parts[0] != "s2p6" or not parts[1].startswith("t"):
        raise ValueError("P6 device prefix does not match frozen namespace grammar")
    if role not in ("a", "b"):
        raise ValueError("P6 device role must be a or b")
    if not task_text.isascii() or not task_text.isdigit() or str(int(task_text)) != task_text:
        raise ValueError("P6 task id must be canonical decimal")
    trial_text = parts[1][1:]
    if not trial_text.isascii() or not trial_text.isdigit():
        raise ValueError("P6 trial id is malformed")
    trial = int(trial_text)
    task_id = int(task_text)
    if trial not in range(TRIALS) or task_id not in range(TASKS_PER_TRIAL):
        raise ValueError("P6 trial/task outside frozen range")
    block = task_id // 3
    return REFERENCE_DELAY_MS if block in REFERENCE_BLOCKS[trial] else SHIFTED_DELAY_MS

def publish_state(device: str, cause: str) -> None:
    assert client is not None
    with lock:
        value = states[device]
    client.publish(
        f"agentmark/{device}/state",
        json.dumps(
            {
                "device": device,
                "on": value,
                "cause": cause,
                "ts_mono_ns": time.monotonic_ns(),
            },
            sort_keys=True,
        ),
        qos=1,
    )

def schedule_state(device: str, cause: str, delay_ms: int) -> None:
    if delay_ms <= 0:
        publish_state(device, cause)
        return
    timer = threading.Timer(delay_ms / 1000.0, publish_state, args=(device, cause))
    timer.daemon = True
    timer.start()

def on_connect(c, _userdata, _flags, _reason_code, _properties) -> None:
    c.subscribe("agentmark/+/command", qos=1)
    c.subscribe("agentmark/+/query", qos=1)
    print(json.dumps({"ready": True}, sort_keys=True), flush=True)

def on_message(_c, _userdata, msg) -> None:
    text = msg.payload.decode("utf-8", errors="strict")
    parts = msg.topic.split("/")
    if len(parts) != 3 or parts[0] != "agentmark":
        return
    _, device, kind = parts
    try:
        delay_ms = delay_for_device(device)
    except ValueError:
        return
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
        client_id="replaymark-s2p6-heterogeneous-target",
    )
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.broker, args.port, keepalive=30)
    client.loop_forever()

if __name__ == "__main__":
    main()
