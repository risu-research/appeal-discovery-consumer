from __future__ import annotations

import argparse
import hashlib
import json
import os
import threading
import time
import uuid
from pathlib import Path

import paho.mqtt.client as mqtt

# Applies only the documented Paho VERSION2 ReasonCode compatibility patch.
# It does not execute pilot.main() on import.
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

FROZEN_BATCHES = {166, 167, 250, 251}
FORBIDDEN_QUEUE_DIRECTIVES = {
    "max_queued_messages",
    "max_queued_bytes",
    "max_inflight_messages",
    "queue_qos0_messages",
}
DOCUMENTED_DEFAULT_QUEUE_MESSAGES = 1000


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def attest_config(path: Path) -> dict:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    directives = []
    forbidden_found = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name = stripped.split(None, 1)[0]
        directives.append(name)
        if name in FORBIDDEN_QUEUE_DIRECTIVES:
            forbidden_found.append(name)
    return {
        "sha256": sha256_bytes(raw),
        "directives": directives,
        "forbidden_queue_directives_found": sorted(set(forbidden_found)),
        "default_queue_policy_attested": len(forbidden_found) == 0,
    }


def read_broker_version(host: str, port: int) -> str:
    connected = threading.Event()
    got = threading.Event()
    box: dict[str, str] = {}

    c = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"replaymark-default-version-{uuid.uuid4().hex[:10]}",
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
    p.add_argument("--batch-size", type=int, required=True)
    p.add_argument("--replica", choices=["A", "B"], required=True)
    p.add_argument("--trials", type=int, default=6)
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
    p.add_argument("--config-path", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    if args.batch_size not in FROZEN_BATCHES:
        raise SystemExit(f"batch size outside frozen set: {args.batch_size}")
    if args.trials != 6:
        raise SystemExit("confirmatory trial count differs from frozen protocol")

    # pilot.run_condition uses args.tasks and args.queue_limit. The latter is
    # only a namespace label here; the broker receives no queue-count override.
    args.tasks = args.batch_size
    args.queue_limit = DOCUMENTED_DEFAULT_QUEUE_MESSAGES

    config_attestation = attest_config(Path(args.config_path))
    if not config_attestation["default_queue_policy_attested"]:
        raise SystemExit(
            "forbidden queue directive present: "
            + ",".join(config_attestation["forbidden_queue_directives_found"])
        )

    version = read_broker_version(args.broker, args.port)
    if version != "mosquitto version 2.1.2":
        raise SystemExit(f"unexpected broker version: {version!r}")

    trials = []
    implementation_passes: list[bool] = []
    for t in range(args.trials):
        order = MODE_ORDERS[t]
        trow = {"trial": t, "order": order, "conditions": {}}
        for mode in order:
            row = pilot.run_condition(args, mode)
            checks = implementation_check(mode, row, args.tasks)
            row["implementation_checks"] = checks
            row["implementation_pass"] = all(checks.values())
            implementation_passes.append(row["implementation_pass"])
            trow["conditions"][mode] = row
        trials.append(trow)

    report = {
        "schema": "replaymark.e3b.documented_default_capacity_flip.raw.v1",
        "status": "CONFIRMATORY_RAW",
        "protocol": "replaymark_e3b_default_flip/DEFAULT_FLIP_PROTOCOL.md",
        "git_sha": args.git_sha,
        "replica": args.replica,
        "batch_size": args.batch_size,
        "broker_version_sys": version,
        "broker_image_tag": "eclipse-mosquitto:2.1.2-alpine",
        "broker_image_digest": args.broker_image_digest,
        "documented_default_max_queued_messages": DOCUMENTED_DEFAULT_QUEUE_MESSAGES,
        "queue_capacity_explicitly_overridden": False,
        "config_attestation": config_attestation,
        "parameters": {
            "tasks": args.tasks,
            "trials": args.trials,
            "wave_size": args.wave_size,
            "wave_period_ms": args.wave_period_ms,
            "verify_ms": args.verify_ms,
            "target_delay_ms": args.target_delay_ms,
            "post_completion_gap_ms": args.gap_ms,
            "task_timeout_ms": args.timeout_ms,
            "drain_quiet_barrier_s": args.drain_quiet_s,
        },
        "trials": trials,
        "implementation_pass": all(implementation_passes),
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
                "batch_size": args.batch_size,
                "broker_version_sys": version,
                "broker_image_digest": args.broker_image_digest,
                "config_sha256": config_attestation["sha256"],
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
