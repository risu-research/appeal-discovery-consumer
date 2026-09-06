from __future__ import annotations

import argparse
import json
import os
import threading
import time
import uuid
from pathlib import Path

import paho.mqtt.client as mqtt

# Importing pilot_entry applies only the documented Paho VERSION2 ReasonCode
# compatibility patch. It does not execute pilot.main() when imported.
import pilot_entry  # noqa: F401
import pilot


MODE_ORDERS = [
    ["R1_TIMING", "TARGET_NATIVE", "R2_SEMANTIC"],
    ["TARGET_NATIVE", "R2_SEMANTIC", "R1_TIMING"],
    ["R2_SEMANTIC", "R1_TIMING", "TARGET_NATIVE"],
    ["R1_TIMING", "R2_SEMANTIC", "TARGET_NATIVE"],
    ["R2_SEMANTIC", "TARGET_NATIVE", "R1_TIMING"],
    ["TARGET_NATIVE", "R1_TIMING", "R2_SEMANTIC"],
]


def read_broker_version(host: str, port: int) -> str:
    connected = threading.Event()
    got = threading.Event()
    box: dict[str, str] = {}

    c = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"replaymark-version-{uuid.uuid4().hex[:10]}",
        protocol=mqtt.MQTTv311,
    )

    def on_connect(client, userdata, flags, reason_code, properties):
        value = getattr(reason_code, "value", reason_code)
        if value != 0:
            return
        connected.set()
        client.subscribe("$SYS/broker/version", qos=0)

    def on_message(client, userdata, msg):
        if msg.topic == "$SYS/broker/version":
            box["version"] = msg.payload.decode("utf-8", errors="replace")
            got.set()

    c.on_connect = on_connect
    c.on_message = on_message
    c.connect(host, port, keepalive=30)
    c.loop_start()
    try:
        if not connected.wait(8):
            raise TimeoutError("broker-version connect")
        if not got.wait(8):
            raise TimeoutError("broker-version SYS message")
        return box["version"]
    finally:
        c.disconnect()
        c.loop_stop()


def implementation_check(mode: str, row: dict, tasks: int) -> dict[str, bool]:
    expected_generated = 4 * tasks if mode == "R1_TIMING" else 6 * tasks
    expected_violation = 1.0 if mode == "R1_TIMING" else 0.0
    expected_verify = 0 if mode == "R1_TIMING" else tasks
    return {
        "generated_conservation": row["generated_qos1"] == expected_generated,
        "online_observer_conservation": row["generated_observer_count"] == expected_generated,
        "tasks_complete": row["success_rate"] == 1.0,
        "semantic_support_boundary": row["support_violation_fraction"] == expected_violation,
        "verify_multiplicity": row["verify_count"] == expected_verify,
        "persistent_session_present": row["collector_session_present"] is True,
        "collector_no_duplicates": row["collector_duplicate_deliveries"] == 0,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--broker", default=os.getenv("BROKER_HOST", "mosquitto"))
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--queue-limit", type=int, required=True)
    p.add_argument("--replica", choices=["A", "B"], required=True)
    p.add_argument("--trials", type=int, default=6)
    p.add_argument("--tasks", type=int, default=128)
    p.add_argument("--wave-size", type=int, default=32)
    p.add_argument("--wave-period-ms", type=int, default=300)
    p.add_argument("--verify-ms", type=int, default=100)
    p.add_argument("--target-delay-ms", type=int, default=150)
    p.add_argument("--gap-ms", type=float, default=20.0)
    p.add_argument("--timeout-ms", type=int, default=1200)
    p.add_argument("--drain-quiet-s", type=float, default=0.75)
    p.add_argument("--drain-timeout-s", type=float, default=20.0)
    p.add_argument("--broker-image-digest", required=True)
    p.add_argument("--git-sha", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    if args.queue_limit not in {511, 512, 767, 768}:
        raise SystemExit(f"queue limit outside frozen confirmatory set: {args.queue_limit}")
    if args.trials != 6 or args.tasks != 128:
        raise SystemExit("confirmatory trials/tasks differ from frozen protocol")

    version = read_broker_version(args.broker, args.port)
    if version != "mosquitto version 2.1.2":
        raise SystemExit(f"unexpected broker version: {version!r}")

    trials = []
    all_implementation_checks: list[bool] = []
    for t in range(args.trials):
        order = MODE_ORDERS[t % len(MODE_ORDERS)]
        trow = {"trial": t, "order": order, "conditions": {}}
        for mode in order:
            row = pilot.run_condition(args, mode)
            checks = implementation_check(mode, row, args.tasks)
            row["implementation_checks"] = checks
            row["implementation_pass"] = all(checks.values())
            all_implementation_checks.append(row["implementation_pass"])
            trow["conditions"][mode] = row
        trials.append(trow)

    report = {
        "schema": "replaymark.e3b.downstream.queue_confirmatory_raw.v1",
        "status": "CONFIRMATORY_RAW",
        "protocol": "replaymark_e3b_downstream/CONFIRMATORY_PROTOCOL.md",
        "git_sha": args.git_sha,
        "replica": args.replica,
        "queue_limit": args.queue_limit,
        "broker_version_sys": version,
        "broker_image_tag": "eclipse-mosquitto:2.1.2-alpine",
        "broker_image_digest": args.broker_image_digest,
        "parameters": {
            "tasks": args.tasks,
            "trials": args.trials,
            "wave_size": args.wave_size,
            "wave_period_ms": args.wave_period_ms,
            "verify_ms": args.verify_ms,
            "target_delay_ms": args.target_delay_ms,
            "post_completion_gap_ms": args.gap_ms,
            "task_timeout_ms": args.timeout_ms,
            "max_queued_messages": args.queue_limit,
            "max_queued_bytes": 0,
            "max_inflight_messages": 20,
            "queue_qos0_messages": False,
            "drain_quiet_barrier_s": args.drain_quiet_s,
        },
        "trials": trials,
        "implementation_pass": all(all_implementation_checks),
        "scientific_prediction_checked_by_runner": False,
        "created_unix_s": time.time(),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "schema": report["schema"],
                "replica": args.replica,
                "queue_limit": args.queue_limit,
                "broker_version_sys": version,
                "broker_image_digest": args.broker_image_digest,
                "implementation_pass": report["implementation_pass"],
                "trials": len(trials),
            },
            indent=2,
            sort_keys=True,
        )
    )
    if not report["implementation_pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
