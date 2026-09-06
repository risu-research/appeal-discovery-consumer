from __future__ import annotations

"""Independent validator for N2 horizon runtime realization.

This intentionally does not import the producer or its helper functions.  It
reconstructs the frozen output paths from raw Home Assistant state/service
events.  In particular, it does not infer a pre-handler thermostat preset by
reading the state registry inside EVENT_CALL_SERVICE; run 34010261833 showed
that location observes the post-handler registry state in HA 2026.9.0.
"""

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA = "replaymark.better_thermostat.horizon_runtime.v1"
VALIDATION_SCHEMA = "replaymark.better_thermostat.horizon_runtime.validation.v2"

PRESENCE = "input_boolean.agentmark_presence"
MOTION = "binary_sensor.agentmark_motion"
NIGHT = "input_boolean.agentmark_night"
CLIMATE = "climate.agentmark_thermostat"

EXPECTED_BLUEPRINT_SHA256 = "16d52ce11dec44fa9ca533d15f3cec1eb9646d59bf6a455bd905af63cdf86443"
EXPECTED_BT_COMMIT = "b86561f61e5ba1259fc63e590f4847e9ac743d7f"
EXPECTED_BT_VERSION = "1.9.2"
EXPECTED_BT_MANIFEST_SHA256 = "710144c3d972501cc38b5a28e013a13a4c90e356039ffaff0b94327c7829bb28"


def transitions(row: dict[str, Any], entity: str, old: str, new: str) -> list[dict[str, Any]]:
    return [
        e for e in row["state_events"]
        if e["entity_id"] == entity and e["old_state"] == old and e["new_state"] == new
    ]


def climate_transitions(row: dict[str, Any]) -> list[dict[str, Any]]:
    return [e for e in row["state_events"] if e["entity_id"] == CLIMATE]


def service_presets(row: dict[str, Any]) -> list[str]:
    out = []
    for e in row["service_events"]:
        if (e["domain"], e["service"]) != ("climate", "set_preset_mode"):
            raise AssertionError(f"unexpected service event: {e}")
        if e["operation"] != "climate.set_preset_mode" or e["target_class"] != "climate":
            raise AssertionError(f"unexpected action identity: {e}")
        out.append(str(e["service_data"].get("preset_mode")))
    return out


def registry_ok(row: dict[str, Any]) -> bool:
    r = row["registry"]
    return (
        r["ownership_mode"] == "upstream-qualified-persisted-disabled-config-entry-controlled-device"
        and r["upstream_component_commit"] == EXPECTED_BT_COMMIT
        and r["upstream_component_version"] == EXPECTED_BT_VERSION
        and r["upstream_manifest_sha256"] == EXPECTED_BT_MANIFEST_SHA256
        and r["ha_loader_resolved_domain"] == "better_thermostat"
        and r["ha_loader_resolved_version"] == EXPECTED_BT_VERSION
        and r["loader_qualification_before_outcome"] is True
        and r["loader_integration_setup_invoked"] is False
        and r["config_entry_domain"] == "better_thermostat"
        and r["config_entry_disabled_by"] == "user"
        and r["config_entry_state"] == "not_loaded"
        and r["config_entry_registered"] is True
        and r["entity_id"] == CLIMATE
        and r["entity_platform"] == "better_thermostat"
        and r["native_device_entity_link"] is True
        and r["native_entry_device_link"] is True
        and r["native_entry_entity_link"] is True
    )


def validate_depth1(row: dict[str, Any]) -> dict[str, Any]:
    motion = row["motion"]
    expected_final = "home" if motion == "off" else "comfort"
    services = row["service_events"]
    presets = service_presets(row)
    climates = climate_transitions(row)
    p_off = transitions(row, PRESENCE, "on", "off")
    p_on = transitions(row, PRESENCE, "off", "on")
    motion_changes = [e for e in row["state_events"] if e["entity_id"] == MOTION]
    night_changes = [e for e in row["state_events"] if e["entity_id"] == NIGHT]

    initial = row["initial_snapshot"]
    current = row["after_current_snapshot"]
    final = row["after_continuation_snapshot"]

    climate_path = [(e["old_preset"], e["new_preset"]) for e in climates]
    checks = {
        "identity_depth": row["depth"] == 1,
        "initial_exact": (
            initial["presence"] == "on" and initial["motion"] == motion
            and initial["night"] == "off" and initial["climate_preset"] == "sleep"
        ),
        "exact_presence_transitions": len(p_off) == 1 and len(p_on) == 1,
        "motion_stable": len(motion_changes) == 0,
        "night_stable": len(night_changes) == 0,
        "service_count_exact": len(services) == 2,
        "service_sequence_exact": presets == ["away", expected_final],
        "native_climate_transition_path_exact": climate_path == [
            ("sleep", "away"), ("away", expected_final)
        ],
        "current_snapshot_exact": (
            current["presence"] == "off" and current["motion"] == motion
            and current["night"] == "off" and current["climate_preset"] == "away"
        ),
        "final_snapshot_exact": (
            final["presence"] == "on" and final["motion"] == motion
            and final["night"] == "off" and final["climate_preset"] == expected_final
        ),
        "ordering_exact": (
            len(p_off) == 1 and len(p_on) == 1
            and len(services) == 2 and len(climates) == 2
            and p_off[0]["t_ns"] <= services[0]["t_ns"] <= climates[0]["t_ns"] <= current["t_ns"]
            and current["t_ns"] < p_on[0]["t_ns"] <= services[1]["t_ns"] <= climates[1]["t_ns"] <= final["t_ns"]
        ),
        "issue_feedback_exact": (
            len(services) == 2
            and services[0]["feedback_at_issue"] == {"presence": "off", "motion": motion, "night": "off"}
            and services[1]["feedback_at_issue"] == {"presence": "on", "motion": motion, "night": "off"}
        ),
        "climate_event_feedback_exact": (
            len(climates) == 2
            and climates[0]["feedback_after_event"] == {"presence": "off", "motion": motion, "night": "off"}
            and climates[1]["feedback_after_event"] == {"presence": "on", "motion": motion, "night": "off"}
        ),
        "ownership_exact": registry_ok(row),
    }
    return {"pass": all(checks.values()), "checks": checks, "climate_path": climate_path}


def validate_depth2(row: dict[str, Any]) -> dict[str, Any]:
    motion = row["motion"]
    expected_final = "home" if motion == "off" else "comfort"
    services = row["service_events"]
    presets = service_presets(row)
    climates = climate_transitions(row)
    p_on = transitions(row, PRESENCE, "off", "on")
    n_off = transitions(row, NIGHT, "on", "off")
    motion_changes = [e for e in row["state_events"] if e["entity_id"] == MOTION]

    initial = row["initial_snapshot"]
    step1 = row["after_step1_snapshot"]
    final = row["after_step2_snapshot"]
    services_before_or_at_step1 = [e for e in services if e["t_ns"] <= step1["t_ns"]]
    climates_before_or_at_step1 = [e for e in climates if e["t_ns"] <= step1["t_ns"]]
    climate_path = [(e["old_preset"], e["new_preset"]) for e in climates]

    checks = {
        "identity_depth": row["depth"] == 2,
        "initial_exact": (
            initial["presence"] == "off" and initial["motion"] == motion
            and initial["night"] == "on" and initial["climate_preset"] == "sleep"
        ),
        "exact_suffix_transitions": len(p_on) == 1 and len(n_off) == 1,
        "motion_stable": len(motion_changes) == 0,
        "step1_no_service_from_raw_events": len(services_before_or_at_step1) == 0,
        "step1_no_climate_transition_from_raw_events": len(climates_before_or_at_step1) == 0,
        "step1_snapshot_exact": (
            step1["presence"] == "on" and step1["motion"] == motion
            and step1["night"] == "on" and step1["climate_preset"] == "sleep"
        ),
        "service_count_exact": len(services) == 1,
        "service_sequence_exact": presets == [expected_final],
        "native_climate_transition_path_exact": climate_path == [("sleep", expected_final)],
        "final_snapshot_exact": (
            final["presence"] == "on" and final["motion"] == motion
            and final["night"] == "off" and final["climate_preset"] == expected_final
        ),
        "ordering_exact": (
            len(p_on) == 1 and len(n_off) == 1
            and len(services) == 1 and len(climates) == 1
            and p_on[0]["t_ns"] <= step1["t_ns"]
            and step1["t_ns"] < n_off[0]["t_ns"] <= services[0]["t_ns"] <= climates[0]["t_ns"] <= final["t_ns"]
        ),
        "issue_feedback_exact": (
            len(services) == 1
            and services[0]["feedback_at_issue"] == {"presence": "on", "motion": motion, "night": "off"}
        ),
        "climate_event_feedback_exact": (
            len(climates) == 1
            and climates[0]["feedback_after_event"] == {"presence": "on", "motion": motion, "night": "off"}
        ),
        "ownership_exact": registry_ok(row),
    }
    return {"pass": all(checks.values()), "checks": checks, "climate_path": climate_path}


def validate(report: dict[str, Any]) -> dict[str, Any]:
    if report["schema"] != SCHEMA:
        raise AssertionError(f"schema mismatch: {report['schema']}")
    if report["environment"]["home_assistant_core_version"] != "2026.9.0":
        raise AssertionError("HA version mismatch")
    if report["external_controller"]["sha256"] != EXPECTED_BLUEPRINT_SHA256:
        raise AssertionError("blueprint hash mismatch")
    if report["external_controller"]["source_edited"] is not False:
        raise AssertionError("external controller was marked edited")
    if report["trials_per_history"] != 6:
        raise AssertionError("trial count changed")

    d1_rows = report["depth1_rows"]
    d2_rows = report["depth2_rows"]
    if len(d1_rows) != 12 or len(d2_rows) != 12:
        raise AssertionError("expected 12 rows per depth per replica")

    d1_validated = [validate_depth1(row) for row in d1_rows]
    d2_validated = [validate_depth2(row) for row in d2_rows]
    counts = {
        "depth1_motion_off": sum(row["motion"] == "off" for row in d1_rows),
        "depth1_motion_on": sum(row["motion"] == "on" for row in d1_rows),
        "depth2_motion_off": sum(row["motion"] == "off" for row in d2_rows),
        "depth2_motion_on": sum(row["motion"] == "on" for row in d2_rows),
    }
    independent_rows_pass = all(v["pass"] for v in d1_validated + d2_validated)
    producer_promoted = report["decision"] == "PROMOTED"
    checks = {
        "condition_counts_exact": all(value == 6 for value in counts.values()),
        "independent_depth1_rows_pass": all(v["pass"] for v in d1_validated),
        "independent_depth2_rows_pass": all(v["pass"] for v in d2_validated),
        "producer_promoted": producer_promoted,
        "producer_gates_all": all(report["promotion_gates"].values()),
        "producer_validator_agree": independent_rows_pass == producer_promoted,
    }
    return {
        "schema": VALIDATION_SCHEMA,
        "replica": report["replica"],
        "decision": "PASS" if all(checks.values()) else "FAIL",
        "condition_counts": counts,
        "checks": checks,
        "depth1_validation": d1_validated,
        "depth2_validation": d2_validated,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("report")
    p.add_argument("--out", required=True)
    args = p.parse_args()
    result = validate(json.loads(Path(args.report).read_text()))
    Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"decision": result["decision"], "replica": result["replica"], "checks": result["checks"]}, indent=2, sort_keys=True))
    if result["decision"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
