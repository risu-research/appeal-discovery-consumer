#!/usr/bin/env python3
"""Independent Phase-B validator for the BT→MQTT carrier qualification.

Imports no producer helpers. Consumes two raw runtime JSON files plus independent
Mosquitto-client observer logs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SCHEMA = "replaymark.bt_mqtt_e2e.qualification.v1"
EXPECTED = {
    "replay": {
        "presets": ["away", "sleep"],
        "temps": [16.0, 18.0],
        "messages": 2,
    },
    "target-native": {
        "presets": ["home", "comfort", "home", "sleep"],
        "temps": [20.0, 21.0, 20.0, 18.0],
        "messages": 4,
    },
}


def target_entity(event):
    targets = event.get("targets") or []
    return [str(x) for x in targets]


def preset_sequence(raw):
    bt = raw["carrier"]["bt_entity"]
    out = []
    for event in raw["bt_preset_service_events"]:
        if bt in target_entity(event):
            out.append(str(event["service_data"].get("preset_mode")))
    return out


def temp_sequence(raw):
    child = raw["carrier"]["child_entity"]
    out = []
    for event in raw["child_temperature_service_events"]:
        if child in target_entity(event):
            out.append(float(event["service_data"]["temperature"]))
    return out


def parse_observer(path: Path, expected_topic: str):
    rows = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        raw = raw.strip()
        if not raw:
            continue
        parts = raw.split("|", 2)
        if len(parts) != 3:
            raise RuntimeError(f"{path}:{lineno}: malformed observer row {raw!r}")
        qos_s, topic, payload = parts
        if topic != expected_topic:
            raise RuntimeError(f"{path}:{lineno}: unexpected topic {topic!r}")
        rows.append({"qos": int(qos_s), "topic": topic, "payload": payload})
    return rows


def close_floats(a, b):
    return len(a) == len(b) and all(abs(float(x) - float(y)) < 1e-9 for x, y in zip(a, b))


def validate_one(raw, observer_path, errors):
    mode = raw.get("mode")
    if mode not in EXPECTED:
        errors.append(f"unknown mode {mode}")
        return None
    exp = EXPECTED[mode]
    if raw.get("schema") != SCHEMA:
        errors.append(f"{mode}: schema")
    auth = raw.get("authorities", {})
    expected_auth = {
        "ha_version": "2026.9.0",
        "better_thermostat_commit": "b86561f61e5ba1259fc63e590f4847e9ac743d7f",
        "external_controller_commit": "57d56f076c05ccaa9553e6bd4b673b6d43a8cf7f",
        "protocol_freeze": "851960e59aa3a68fb90ef199f1dbcfefe5fcd3c0",
        "selector_result_sha256": "07213a0d56e5f2d32b9eb3c2b2e6b20cb0aab31290f801f579905ea490161598",
    }
    if auth != expected_auth:
        errors.append(f"{mode}: authority mismatch {auth}")

    carrier = raw.get("carrier", {})
    if carrier.get("bt_entry_state") != "loaded":
        errors.append(f"{mode}: BT entry not loaded: {carrier.get('bt_entry_state')}")
    if carrier.get("bt_entry_disabled_by") is not None:
        errors.append(f"{mode}: BT entry disabled")
    if carrier.get("mqtt_entry_state") != "loaded":
        errors.append(f"{mode}: MQTT entry not loaded: {carrier.get('mqtt_entry_state')}")
    if carrier.get("child_platform") != "mqtt":
        errors.append(f"{mode}: child platform {carrier.get('child_platform')}")
    if carrier.get("adapter_module") != "custom_components.better_thermostat.adapters.mqtt":
        errors.append(f"{mode}: adapter {carrier.get('adapter_module')}")
    if carrier.get("forbidden_custom_action_to_mqtt_bridge") is not False:
        errors.append(f"{mode}: forbidden bridge marker")

    if raw.get("frozen_events") != ["night_toggle", "motion_toggle", "motion_toggle", "night_toggle"]:
        errors.append(f"{mode}: event sequence")
    got_presets = preset_sequence(raw)
    if got_presets != exp["presets"]:
        errors.append(f"{mode}: preset services {got_presets} != {exp['presets']}")
    got_temps = temp_sequence(raw)
    if not close_floats(got_temps, exp["temps"]):
        errors.append(f"{mode}: child temperature services {got_temps} != {exp['temps']}")

    rows = parse_observer(observer_path, carrier["temp_topic"])
    if len(rows) != exp["messages"]:
        errors.append(f"{mode}: MQTT count {len(rows)} != {exp['messages']}")
    if any(row["qos"] != 1 for row in rows):
        errors.append(f"{mode}: non-QoS1 MQTT row {rows}")
    payloads = []
    for row in rows:
        try:
            payloads.append(float(row["payload"]))
        except ValueError:
            errors.append(f"{mode}: nonnumeric MQTT payload {row['payload']!r}")
    if not close_floats(payloads, exp["temps"]):
        errors.append(f"{mode}: MQTT payloads {payloads} != {exp['temps']}")

    if raw.get("final_feedback") != {"presence": "on", "motion": "off", "night": "on"}:
        errors.append(f"{mode}: final feedback not reset-free {raw.get('final_feedback')}")
    if raw.get("final_bt_preset") != "sleep":
        errors.append(f"{mode}: final BT preset")
    if abs(float(raw.get("final_child_temperature")) - 18.0) > 1e-9:
        errors.append(f"{mode}: final child temperature")

    # No setup message may be visible because the observer is started only after READY.
    # Exact equality of child service writes and independent broker-observer rows is the
    # protocol's 1:1/0:0 carrier requirement for the selected cycle.
    if len(got_temps) != len(rows):
        errors.append(f"{mode}: service/message conservation {len(got_temps)} != {len(rows)}")
    return {
        "mode": mode,
        "preset_sequence": got_presets,
        "temperature_service_sequence": got_temps,
        "mqtt_payload_sequence": payloads,
        "mqtt_qos": [row["qos"] for row in rows],
        "count": len(rows),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--native", type=Path, required=True)
    ap.add_argument("--native-observer", type=Path, required=True)
    ap.add_argument("--replay", type=Path, required=True)
    ap.add_argument("--replay-observer", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    native = json.loads(args.native.read_text(encoding="utf-8"))
    replay = json.loads(args.replay.read_text(encoding="utf-8"))
    errors = []
    summary = []
    summary.append(validate_one(native, args.native_observer, errors))
    summary.append(validate_one(replay, args.replay_observer, errors))

    if native.get("mode") != "target-native" or replay.get("mode") != "replay":
        errors.append("mode assignment")

    if not errors:
        n = next(row for row in summary if row["mode"] == "target-native")
        r = next(row for row in summary if row["mode"] == "replay")
        if n["count"] != 4 or r["count"] != 2:
            errors.append("2x count relation")
        if n["count"] != 2 * r["count"]:
            errors.append("native/replay exact 2x amplification")

    certificate = {
        "schema": "replaymark.bt_mqtt_e2e.qualification.validation.v1",
        "qualification_pass": not errors,
        "errors": errors,
        "rows": summary,
        "gates": {
            "E1_natural_carrier": not errors,
            "E2_selected_cycle_semantics": not errors,
            "E3_qualification_workload_realization": not errors,
        },
        "capacity_phase_admitted": not errors,
        "capacity_predictions_if_admitted": None if errors else {
            "queue_Q": 1000,
            "replay_messages_per_cycle": 2,
            "native_messages_per_cycle": 4,
            "replay_lossless_cycle_capacity": 500,
            "native_lossless_cycle_capacity": 250,
            "confirmatory_cycle_counts": [250, 251, 500, 501],
            "primary_flip_at_cycles": 500,
            "primary_replay_generated_delivered_lost": [1000, 1000, 0],
            "primary_native_generated_delivered_lost": [2000, 1000, 1000],
        },
        "scope": "Phase-B carrier qualification only; no queue-capacity outcome is claimed here.",
    }
    args.out.write_text(json.dumps(certificate, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if errors:
        print("BT_MQTT_E2E_QUALIFICATION_VALIDATION: FAIL")
        for error in errors:
            print("ERROR", error)
        return 1
    print("BT_MQTT_E2E_QUALIFICATION_VALIDATION: PASS")
    print("replay=2 MQTT QoS1 commands/cycle; target-native=4; exact amplification=2x")
    print("Phase C mechanically admitted: boundaries 250/251/500/501; capacity not yet executed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
