from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict

import paho.mqtt.client as mqtt

BROKER = os.getenv("BROKER_HOST", "mosquitto")
PORT = int(os.getenv("BROKER_PORT", "1883"))

states: dict[tuple[str, str], bool] = defaultdict(bool)
state_delay_ms = 150
lock = threading.Lock()
client: mqtt.Client | None = None


def state_topic(run_id: str, device: str) -> str:
    return f"replaymark/{run_id}/{device}/state"


def pub_state(run_id: str, device: str, cause: str) -> None:
    assert client is not None
    with lock:
        value = states[(run_id, device)]
    client.publish(
        state_topic(run_id, device),
        json.dumps(
            {
                "run_id": run_id,
                "device": device,
                "on": value,
                "cause": cause,
                "ts_mono_ns": time.monotonic_ns(),
            },
            sort_keys=True,
        ),
        qos=1,
    )


def schedule_state(run_id: str, device: str, cause: str, delay_ms: int) -> None:
    if delay_ms <= 0:
        pub_state(run_id, device, cause)
        return
    timer = threading.Timer(delay_ms / 1000.0, pub_state, args=(run_id, device, cause))
    timer.daemon = True
    timer.start()


def on_connect(c, userdata, flags, reason_code, properties) -> None:
    c.subscribe("replaymark/+/+/command", qos=1)
    c.subscribe("replaymark/+/+/query", qos=1)
    c.subscribe("replaymark/control", qos=1)


def on_message(c, userdata, msg) -> None:
    global state_delay_ms

    text = msg.payload.decode("utf-8", errors="replace")
    if msg.topic == "replaymark/control":
        body = json.loads(text)
        with lock:
            state_delay_ms = int(body.get("state_delay_ms", 150))
        c.publish(
            "replaymark/control/ack",
            json.dumps(
                {"nonce": body.get("nonce"), "state_delay_ms": state_delay_ms},
                sort_keys=True,
            ),
            qos=1,
        )
        return

    parts = msg.topic.split("/")
    if len(parts) != 4 or parts[0] != "replaymark":
        return
    _, run_id, device, kind = parts

    if kind == "command":
        body = json.loads(text)
        with lock:
            states[(run_id, device)] = bool(body.get("on", True))
            delay = state_delay_ms
        schedule_state(run_id, device, "command", delay)
    elif kind == "query":
        pub_state(run_id, device, "query")


def main() -> None:
    global client
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="replaymark-downstream-device",
        protocol=mqtt.MQTTv311,
    )
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, PORT, keepalive=30)
    client.loop_forever()


if __name__ == "__main__":
    main()
