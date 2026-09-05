from __future__ import annotations

"""Independent validator for AgentMark N2b decision-equivalence evidence."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from agentmark.kernel import ReactiveKernel
from agentmark.semantics import (
    feedback_partition,
    policy_sensitivity_eta,
    quotient_feedback_law,
    step_replay_validity,
    total_variation,
    workload_shift_tv,
)
from agentmark_natural_controllers.action_identity import canonical_action_identity

SCHEMA = "agentmark.natural_controller.better_thermostat_decision_equivalence.v1"
HA_VERSION = "2026.9.0"
EXTERNAL_SHA = "16d52ce11dec44fa9ca533d15f3cec1eb9646d59bf6a455bd905af63cdf86443"
BT_COMMIT = "b86561f61e5ba1259fc63e590f4847e9ac743d7f"
BT_VERSION = "1.9.2"
BT_MANIFEST_SHA = "710144c3d972501cc38b5a28e013a13a4c90e356039ffaff0b94327c7829bb28"
BT_TREE_SHA = "bc648881395399a4d1957380409e1b8ad3c0c056ba9ae30a53b39d5439fef2c0"
OWNERSHIP_MODE = "upstream-qualified-persisted-disabled-config-entry-controlled-device"
CONFIG_ENTRY_PATH = "core.config_entries Store -> ConfigEntries.async_initialize"
FEEDBACK_A = "AWAY_MOTION_OFF"
FEEDBACK_B = "AWAY_MOTION_ON"
EXPECTED_OPERATION = "climate.set_preset_mode"
EXPECTED_TARGET_CLASS = "climate"
EXPECTED_VARIANT = '{"preset_mode":"away"}'
EXPECTED_IDENTITY = {
    "operation": EXPECTED_OPERATION,
    "target_class": EXPECTED_TARGET_CLASS,
    "variant": EXPECTED_VARIANT,
}
TRIALS = 6


def deterministic_tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if not files:
        raise AssertionError(f"empty upstream component tree: {root}")
    for path in files:
        rel = path.relative_to(root).as_posix().encode("utf-8")
        body = path.read_bytes()
        digest.update(len(rel).to_bytes(8, "big"))
        digest.update(rel)
        digest.update(len(body).to_bytes(8, "big"))
        digest.update(body)
    return digest.hexdigest()


def pair_kernel() -> ReactiveKernel:
    away = {
        "p": 1,
        "operation": EXPECTED_OPERATION,
        "target_class": EXPECTED_TARGET_CLASS,
        "variant": EXPECTED_VARIANT,
        "next_state": "done",
    }
    return ReactiveKernel({
        "initial_state": "decision",
        "feedback_alphabet": [FEEDBACK_A, FEEDBACK_B],
        "states": {
            "decision": {FEEDBACK_A: [dict(away)], FEEDBACK_B: [dict(away)]},
            "done": {
                FEEDBACK_A: [{"p": 1, "operation": "STOP", "next_state": "done"}],
                FEEDBACK_B: [{"p": 1, "operation": "STOP", "next_state": "done"}],
            },
        },
    })


def expected_vector(motion: str) -> dict[str, Any]:
    return {
        "presence": "off",
        "motion": motion,
        "night": "off",
        "boost": False,
        "eco": False,
        "activity": False,
    }


def ownership_ok(row: dict[str, Any]) -> bool:
    reg = row["registry"]
    return (
        reg["ownership_mode"] == OWNERSHIP_MODE
        and reg["config_entry_registration_path"] == CONFIG_ENTRY_PATH
        and reg["upstream_component_commit"] == BT_COMMIT
        and reg["upstream_component_version"] == BT_VERSION
        and reg["upstream_manifest_sha256"] == BT_MANIFEST_SHA
        and reg["ha_loader_resolved_domain"] == "better_thermostat"
        and reg["ha_loader_resolved_version"] == BT_VERSION
        and reg["loader_qualification_before_outcome"] is True
        and reg["loader_integration_setup_invoked"] is False
        and reg["config_entry_domain"] == "better_thermostat"
        and reg["config_entry_disabled_by"] == "user"
        and reg["config_entry_state"] == "not_loaded"
        and reg["config_entry_registered"] is True
        and reg["device_identifiers"] == [["better_thermostat", "agentmark-device"]]
        and reg["entity_id"] == "climate.agentmark_thermostat"
        and reg["entity_platform"] == "better_thermostat"
        and reg["native_device_entity_link"] is True
        and reg["native_entry_device_link"] is True
        and reg["native_entry_entity_link"] is True
    )


def snapshot_ok(snapshot: dict[str, Any], *, phase: str, presence: str, motion: str) -> bool:
    return snapshot == {
        "phase": phase,
        "climate_entity": "climate.agentmark_thermostat",
        "climate_state": "heat",
        "climate_preset": "sleep",
        "presence_state": presence,
        "motion_state": motion,
        "night_state": "off",
        "enable_state": "on",
        "ownership_config_entry_state": "not_loaded",
        "ownership_config_entry_disabled_by": "user",
        "ownership_entry_registered": True,
        "entity_id": "climate.agentmark_thermostat",
        "entity_platform": "better_thermostat",
    }


def row_identity_recomputed(row: dict[str, Any]) -> bool:
    calls = [e for e in row["raw_call_events"] if e["operation"] == EXPECTED_OPERATION]
    if len(calls) != 1:
        return False
    event = calls[0]
    identity = canonical_action_identity(
        str(event["domain"]), str(event["service"]), dict(event["service_data"])
    )
    recomputed = {
        "operation": identity.operation,
        "target_class": identity.target_class,
        "variant": identity.variant,
    }
    return recomputed == EXPECTED_IDENTITY and row["identity"] == EXPECTED_IDENTITY


def base_row_ok(row: dict[str, Any]) -> bool:
    return (
        row["call_counts"] == {EXPECTED_OPERATION: 1}
        and row["climate_call_count"] == 1
        and row_identity_recomputed(row)
        and ownership_ok(row)
    )


def native_row_ok(row: dict[str, Any], *, motion: str, feedback: str) -> bool:
    return (
        base_row_ok(row)
        and row["expected_feedback"] == feedback
        and row["decision_feedback_vector"] == expected_vector(motion)
        and snapshot_ok(
            row["initial_snapshot"],
            phase="after_automation_setup_before_presence_transition",
            presence="on",
            motion=motion,
        )
        and snapshot_ok(
            row["decision_feedback_snapshot"],
            phase="after_presence_transition_before_event_loop_yield",
            presence="off",
            motion=motion,
        )
    )


def expected_support(target_feedback: str) -> dict[str, Any]:
    kernel = pair_kernel()
    op = step_replay_validity(
        kernel,
        state="decision",
        source_feedback=FEEDBACK_A,
        target_feedback=target_feedback,
        recorded_event=EXPECTED_OPERATION,
        projection="operation",
    )
    action = step_replay_validity(
        kernel,
        state="decision",
        source_feedback=FEEDBACK_A,
        target_feedback=target_feedback,
        recorded_event=(EXPECTED_OPERATION, EXPECTED_TARGET_CLASS, EXPECTED_VARIANT),
        projection="action",
    )
    def j(v: Any) -> dict[str, Any]:
        return {
            "source_probability": float(v.source_probability),
            "target_probability": float(v.target_probability),
            "source_consistent": bool(v.source_consistent),
            "target_supports_recorded_event": bool(v.target_supports_recorded_event),
            "support_failure": bool(v.support_failure),
        }
    return {
        "source_feedback": FEEDBACK_A,
        "target_feedback": target_feedback,
        "operation": j(op),
        "action": j(action),
    }


def replay_row_ok(row: dict[str, Any], *, motion: str, feedback: str) -> bool:
    return (
        base_row_ok(row)
        and row["expected_feedback"] == feedback
        and row["decision_feedback_vector"] == expected_vector(motion)
        and snapshot_ok(
            row["replay_feedback_snapshot"],
            phase="before_recorded_replay_service_call",
            presence="off",
            motion=motion,
        )
        and row["support"] == expected_support(feedback)
    )


def theory_expected() -> dict[str, Any]:
    kernel = pair_kernel()
    left = {FEEDBACK_A: 1}
    right = {FEEDBACK_B: 1}
    partition = feedback_partition(kernel, "decision", projection="action")
    q_left = quotient_feedback_law(left, partition)
    q_right = quotient_feedback_law(right, partition)
    return {
        "feedback_A": FEEDBACK_A,
        "feedback_B": FEEDBACK_B,
        "action_feedback_classes": [list(cls) for cls in partition.classes],
        "unsupported_feedback": list(partition.unsupported),
        "raw_feedback_tv": float(total_variation(left, right)),
        "quotient_feedback_tv": float(total_variation(q_left, q_right)),
        "TV_operation": float(workload_shift_tv(
            kernel, "decision", left, right, projection="operation"
        )),
        "TV_action": float(workload_shift_tv(
            kernel, "decision", left, right, projection="action"
        )),
        "pair_restricted_eta_action": float(policy_sensitivity_eta(
            kernel, "decision", projection="action"
        )),
        "source_quotient_law": {"|".join(k): float(v) for k, v in q_left.items()},
        "target_quotient_law": {"|".join(k): float(v) for k, v in q_right.items()},
    }


def validate(result_path: Path, component_root: Path) -> dict[str, Any]:
    result = json.loads(result_path.read_text(encoding="utf-8"))
    manifest_sha = hashlib.sha256((component_root / "manifest.json").read_bytes()).hexdigest()
    tree_sha = deterministic_tree_sha256(component_root)
    protocol = result["frozen_protocol"]
    recorded = canonical_action_identity(
        "climate", "set_preset_mode", dict(result["recorded_source_service_data"])
    )
    source = result["source_native"]
    target = result["target_native"]
    replay = result["target_replay"]
    control = result["no_shift_replay"]

    checks = {
        "schema_exact": result["schema"] == SCHEMA,
        "replica_nonnegative_integer": isinstance(result["replica"], int) and result["replica"] >= 0,
        "ha_version_exact": result["environment"] == {"home_assistant_core_version": HA_VERSION},
        "external_controller_exact": result["external_controller"] == {
            "repository": "n3roGit/MyHomeAssistantMods",
            "commit": "57d56f076c05ccaa9553e6bd4b673b6d43a8cf7f",
            "path": "automation/BetterThermostatControl/BetterThermostat_RoomHeatControl_Lean.yaml",
            "sha256": EXTERNAL_SHA,
            "source_edited": False,
        },
        "upstream_manifest_exact": manifest_sha == BT_MANIFEST_SHA,
        "upstream_tree_exact": tree_sha == BT_TREE_SHA,
        "controlled_ownership_summary_exact": (
            result["controlled_device_ownership"]["mode"] == OWNERSHIP_MODE
            and result["controlled_device_ownership"]["config_entry_registration_path"] == CONFIG_ENTRY_PATH
            and result["controlled_device_ownership"]["upstream_commit"] == BT_COMMIT
            and result["controlled_device_ownership"]["upstream_version"] == BT_VERSION
            and result["controlled_device_ownership"]["upstream_manifest_sha256"] == BT_MANIFEST_SHA
            and result["controlled_device_ownership"]["component_tree_sha256"] == BT_TREE_SHA
            and result["controlled_device_ownership"]["config_entry_intentionally_disabled"] is True
            and result["controlled_device_ownership"]["integration_internal_control_logic_executed"] is False
        ),
        "protocol_pair_exact": (
            protocol["current_preset"] == "sleep"
            and protocol["source_feedback_label"] == FEEDBACK_A
            and protocol["target_feedback_label"] == FEEDBACK_B
            and protocol["source_feedback_vector"] == expected_vector("off")
            and protocol["target_feedback_vector"] == expected_vector("on")
            and protocol["native_trigger_both"] == "presence on -> off"
            and protocol["trials_per_condition"] == TRIALS
            and protocol["writeback_enable"] is False
            and protocol["writeback_bounds_enable"] is False
            and protocol["boost_entity"] == ""
            and protocol["eco_entity"] == ""
            and protocol["activity_entity"] == ""
        ),
        "recorded_source_action_exact": (
            recorded.operation == EXPECTED_OPERATION
            and recorded.target_class == EXPECTED_TARGET_CLASS
            and recorded.variant == EXPECTED_VARIANT
        ),
        "condition_cardinality_exact": (
            len(source) == TRIALS and len(target) == TRIALS
            and len(replay) == TRIALS and len(control) == TRIALS
        ),
        "source_native_all_exact": len(source) == TRIALS and all(
            native_row_ok(row, motion="off", feedback=FEEDBACK_A) for row in source
        ),
        "target_native_all_exact": len(target) == TRIALS and all(
            native_row_ok(row, motion="on", feedback=FEEDBACK_B) for row in target
        ),
        "target_replay_all_exact_supported": len(replay) == TRIALS and all(
            replay_row_ok(row, motion="on", feedback=FEEDBACK_B) for row in replay
        ),
        "no_shift_replay_all_exact_supported": len(control) == TRIALS and all(
            replay_row_ok(row, motion="off", feedback=FEEDBACK_A) for row in control
        ),
        "raw_feedback_vectors_distinct": expected_vector("off") != expected_vector("on"),
        "native_action_identity_equal_across_pair": all(
            row["identity"] == EXPECTED_IDENTITY for row in [*source, *target]
        ),
        "theory_recomputed_exact": result["theory"] == theory_expected(),
    }
    passed = all(checks.values())
    producer_gates = result.get("promotion_gates", {})
    return {
        "schema": "agentmark.n2b.independent_validation.v1",
        "replica": result["replica"],
        "verdict": "PASS" if passed else "FAIL",
        "checks": checks,
        "recomputed_theory": theory_expected(),
        "producer_decision_reported": result.get("decision"),
        "producer_promoted_reported": producer_gates.get("promoted"),
        "producer_consistent_with_independent_validation": (
            result.get("decision") == ("PROMOTED" if passed else "NOT_PROMOTED")
            and producer_gates.get("promoted") is passed
        ),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("result")
    p.add_argument("--ownership-component", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    validation = validate(Path(args.result), Path(args.ownership_component))
    Path(args.out).write_text(
        json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(validation, indent=2, sort_keys=True))
    if validation["verdict"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
