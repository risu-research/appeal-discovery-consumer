from __future__ import annotations

"""Independent validator for corrected N2b v2 event-level feedback evidence."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from agentmark_natural_controllers.action_identity import canonical_action_identity
from agentmark_natural_controllers.better_thermostat import n2b_validate as v1

SCHEMA = "agentmark.natural_controller.better_thermostat_decision_equivalence.v2"
VALIDATION_SCHEMA = "agentmark.n2b.independent_validation.v2"
TRIALS = 6


def observer_identity_ok(issue: dict[str, Any]) -> bool:
    identity = canonical_action_identity(
        str(issue["domain"]), str(issue["service"]), dict(issue["service_data"])
    )
    return (
        issue["operation"] == identity.operation == v1.EXPECTED_OPERATION
        and issue["target_class"] == identity.target_class == v1.EXPECTED_TARGET_CLASS
        and issue["variant"] == identity.variant == v1.EXPECTED_VARIANT
    )


def native_row_ok_v2(row: dict[str, Any], *, motion: str, feedback: str) -> bool:
    expected = v1.expected_vector(motion)
    transitions = row.get("presence_transition_witnesses", [])
    issues = row.get("service_issue_feedback_witnesses", [])
    if len(transitions) != 1 or len(issues) != 1:
        return False
    transition = transitions[0]
    issue = issues[0]
    return (
        v1.base_row_ok(row)
        and row["expected_feedback"] == feedback
        and row["decision_feedback_vector"] == expected
        and v1.snapshot_ok(
            row["initial_snapshot"],
            phase="after_automation_setup_before_presence_transition",
            presence="on",
            motion=motion,
        )
        and transition["entity_id"] == "input_boolean.agentmark_presence"
        and transition["old_state"] == "on"
        and transition["new_state"] == "off"
        and transition["feedback"] == expected
        and issue["domain"] == "climate"
        and issue["service"] == "set_preset_mode"
        and observer_identity_ok(issue)
        and issue["feedback"] == expected
        and isinstance(transition["t_ns"], int)
        and isinstance(issue["t_ns"], int)
        and transition["t_ns"] <= issue["t_ns"]
        and row["post_action_feedback_snapshot"] == expected
    )


def validate(result_path: Path, component_root: Path) -> dict[str, Any]:
    result = json.loads(result_path.read_text(encoding="utf-8"))
    manifest_sha = hashlib.sha256((component_root / "manifest.json").read_bytes()).hexdigest()
    tree_sha = v1.deterministic_tree_sha256(component_root)
    protocol = result["frozen_protocol"]
    recorded = canonical_action_identity(
        "climate", "set_preset_mode", dict(result["recorded_source_service_data"])
    )
    source = result["source_native"]
    target = result["target_native"]
    replay = result["target_replay"]
    control = result["no_shift_replay"]
    measurement = result.get("measurement_contract", {})

    checks = {
        "schema_exact": result["schema"] == SCHEMA,
        "replica_nonnegative_integer": isinstance(result["replica"], int) and result["replica"] >= 0,
        "ha_version_exact": result["environment"] == {"home_assistant_core_version": v1.HA_VERSION},
        "external_controller_exact": result["external_controller"] == {
            "repository": "n3roGit/MyHomeAssistantMods",
            "commit": "57d56f076c05ccaa9553e6bd4b673b6d43a8cf7f",
            "path": "automation/BetterThermostatControl/BetterThermostat_RoomHeatControl_Lean.yaml",
            "sha256": v1.EXTERNAL_SHA,
            "source_edited": False,
        },
        "upstream_manifest_exact": manifest_sha == v1.BT_MANIFEST_SHA,
        "upstream_tree_exact": tree_sha == v1.BT_TREE_SHA,
        "controlled_ownership_summary_exact": (
            result["controlled_device_ownership"]["mode"] == v1.OWNERSHIP_MODE
            and result["controlled_device_ownership"]["config_entry_registration_path"] == v1.CONFIG_ENTRY_PATH
            and result["controlled_device_ownership"]["upstream_commit"] == v1.BT_COMMIT
            and result["controlled_device_ownership"]["upstream_version"] == v1.BT_VERSION
            and result["controlled_device_ownership"]["upstream_manifest_sha256"] == v1.BT_MANIFEST_SHA
            and result["controlled_device_ownership"]["component_tree_sha256"] == v1.BT_TREE_SHA
            and result["controlled_device_ownership"]["config_entry_intentionally_disabled"] is True
            and result["controlled_device_ownership"]["integration_internal_control_logic_executed"] is False
        ),
        "measurement_correction_exact": measurement == {
            "version": "n2b-v2-event-level-feedback-witness",
            "v1_failure_run": 33972326066,
            "strict_pre_handler_climate_snapshot_claimed": False,
            "feedback_entities_observed_at_presence_transition": True,
            "feedback_entities_observed_at_service_issue": True,
            "post_action_feedback_nonmutation_check": True,
        },
        "protocol_pair_exact": (
            protocol["current_preset"] == "sleep"
            and protocol["source_feedback_label"] == v1.FEEDBACK_A
            and protocol["target_feedback_label"] == v1.FEEDBACK_B
            and protocol["source_feedback_vector"] == v1.expected_vector("off")
            and protocol["target_feedback_vector"] == v1.expected_vector("on")
            and protocol["native_trigger_both"] == "presence on -> off"
            and protocol["trials_per_condition"] == TRIALS
            and protocol["writeback_enable"] is False
            and protocol["writeback_bounds_enable"] is False
            and protocol["boost_entity"] == ""
            and protocol["eco_entity"] == ""
            and protocol["activity_entity"] == ""
        ),
        "recorded_source_action_exact": (
            recorded.operation == v1.EXPECTED_OPERATION
            and recorded.target_class == v1.EXPECTED_TARGET_CLASS
            and recorded.variant == v1.EXPECTED_VARIANT
        ),
        "condition_cardinality_exact": (
            len(source) == TRIALS and len(target) == TRIALS
            and len(replay) == TRIALS and len(control) == TRIALS
        ),
        "source_native_event_witness_all_exact": len(source) == TRIALS and all(
            native_row_ok_v2(row, motion="off", feedback=v1.FEEDBACK_A) for row in source
        ),
        "target_native_event_witness_all_exact": len(target) == TRIALS and all(
            native_row_ok_v2(row, motion="on", feedback=v1.FEEDBACK_B) for row in target
        ),
        "target_replay_all_exact_supported": len(replay) == TRIALS and all(
            v1.replay_row_ok(row, motion="on", feedback=v1.FEEDBACK_B) for row in replay
        ),
        "no_shift_replay_all_exact_supported": len(control) == TRIALS and all(
            v1.replay_row_ok(row, motion="off", feedback=v1.FEEDBACK_A) for row in control
        ),
        "raw_feedback_vectors_distinct": v1.expected_vector("off") != v1.expected_vector("on"),
        "native_action_identity_equal_across_pair": all(
            row["identity"] == v1.EXPECTED_IDENTITY for row in [*source, *target]
        ),
        "theory_recomputed_exact": result["theory"] == v1.theory_expected(),
    }
    passed = all(checks.values())
    producer_gates = result.get("promotion_gates", {})
    validation = {
        "schema": VALIDATION_SCHEMA,
        "replica": result["replica"],
        "verdict": "PASS" if passed else "FAIL",
        "checks": checks,
        "recomputed_theory": v1.theory_expected(),
        "producer_decision_reported": result.get("decision"),
        "producer_promoted_reported": producer_gates.get("promoted"),
        "producer_consistent_with_independent_validation": (
            result.get("decision") == ("PROMOTED" if passed else "NOT_PROMOTED")
            and producer_gates.get("promoted") is passed
        ),
    }
    return validation


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
