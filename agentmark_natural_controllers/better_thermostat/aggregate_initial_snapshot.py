from __future__ import annotations

import argparse
import json
from pathlib import Path

EXPECTED_IMAGE = "ghcr.io/home-assistant/home-assistant@sha256:372d991e58882a1d8c68c07e9aa3f3b509276e695355f73ccdb03baa70407293"
EXPECTED_CONTROLLER_SHA = "16d52ce11dec44fa9ca533d15f3cec1eb9646d59bf6a455bd905af63cdf86443"
EXPECTED_BT_COMMIT = "b86561f61e5ba1259fc63e590f4847e9ac743d7f"
EXPECTED_BT_VERSION = "1.9.2"
EXPECTED_BT_MANIFEST_SHA = "710144c3d972501cc38b5a28e013a13a4c90e356039ffaff0b94327c7829bb28"
EXPECTED_MODE = "upstream-qualified-persisted-disabled-config-entry-controlled-device"
EXPECTED_REGISTRATION_PATH = "core.config_entries Store -> ConfigEntries.async_initialize"
EXPECTED_SOURCE = {
    "operation": "climate.set_preset_mode",
    "target_class": "climate",
    "variant": '{"preset_mode":"home"}',
}
EXPECTED_TARGET = {
    "operation": "climate.set_preset_mode",
    "target_class": "climate",
    "variant": '{"preset_mode":"away"}',
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", nargs=2)
    parser.add_argument("--validations", nargs=2, required=True)
    parser.add_argument("--image-ref-file", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    results = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.results]
    validations = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.validations]
    image_ref = Path(args.image_ref_file).read_text(encoding="utf-8").strip()

    result_by_replica = {int(row["replica"]): row for row in results}
    validation_by_replica = {int(row["replica"]): row for row in validations}
    if sorted(result_by_replica) != [0, 1]:
        raise AssertionError("need exactly producer replicas 0 and 1")
    if sorted(validation_by_replica) != [0, 1]:
        raise AssertionError("need exactly validator replicas 0 and 1")
    if image_ref != EXPECTED_IMAGE:
        raise AssertionError(f"HA image mismatch: {image_ref}")
    if not all(row["schema"] == "agentmark.natural_controller.better_thermostat_action_identity.v4" for row in results):
        raise AssertionError("producer schema mismatch")
    if not all(row["schema"] == "agentmark.natural_controller.better_thermostat.validation.v4" for row in validations):
        raise AssertionError("validator schema mismatch")
    if not all(row["decision"] == "PROMOTED" for row in results):
        raise AssertionError("both producers must promote")
    if not all(row["pass"] is True for row in validations):
        raise AssertionError("both independent validators must pass")

    source_ids = [validation_by_replica[i]["recomputed"]["source_identity"] for i in (0, 1)]
    target_ids = [validation_by_replica[i]["recomputed"]["target_identity"] for i in (0, 1)]
    tv_ops = [float(validation_by_replica[i]["recomputed"]["TV_operation"]) for i in (0, 1)]
    tv_actions = [float(validation_by_replica[i]["recomputed"]["TV_action"]) for i in (0, 1)]
    tree_hashes = [validation_by_replica[i]["recomputed"]["ownership_component_tree_sha256"] for i in (0, 1)]
    owners = [result_by_replica[i]["controlled_device_ownership"] for i in (0, 1)]

    checks = {
        "source_identity_replicates": source_ids == [EXPECTED_SOURCE, EXPECTED_SOURCE],
        "target_identity_replicates": target_ids == [EXPECTED_TARGET, EXPECTED_TARGET],
        "same_operation_across_feedback": all(source_ids[i]["operation"] == target_ids[i]["operation"] for i in (0, 1)),
        "different_full_action_across_feedback": all(source_ids[i] != target_ids[i] for i in (0, 1)),
        "tv_operation_exact_zero_each_runner": tv_ops == [0.0, 0.0],
        "tv_action_exact_one_each_runner": tv_actions == [1.0, 1.0],
        "pre_action_snapshots_exact_each_runner": all(validation_by_replica[i]["recomputed"]["pre_action_snapshots_all_exact"] is True for i in (0, 1)),
        "event_callback_preset_explicitly_diagnostic_only": all(validation_by_replica[i]["observer_ordering_diagnostics"]["used_for_promotion"] is False for i in (0, 1)),
        "component_tree_replicates": len(set(tree_hashes)) == 1,
        "upstream_manifest_exact": all(validation_by_replica[i]["upstream_recomputed"]["manifest_sha256"] == EXPECTED_BT_MANIFEST_SHA and validation_by_replica[i]["upstream_recomputed"]["domain"] == "better_thermostat" and validation_by_replica[i]["upstream_recomputed"]["version"] == EXPECTED_BT_VERSION for i in (0, 1)),
        "ownership_mode_exact": all(owner["mode"] == EXPECTED_MODE for owner in owners),
        "registration_path_exact": all(owner["config_entry_registration_path"] == EXPECTED_REGISTRATION_PATH for owner in owners),
        "upstream_commit_exact": all(owner["upstream_commit"] == EXPECTED_BT_COMMIT for owner in owners),
        "upstream_version_exact": all(owner["upstream_version"] == EXPECTED_BT_VERSION for owner in owners),
        "producer_tree_matches_validator": all(owners[i]["component_tree_sha256"] == tree_hashes[i] for i in (0, 1)),
        "loader_qualified_before_outcome": all(owner["loader_qualification"]["domain"] == "better_thermostat" and owner["loader_qualification"]["version"] == EXPECTED_BT_VERSION and owner["loader_qualification"]["before_outcome"] is True and owner["loader_qualification"]["integration_setup_invoked"] is False for owner in owners),
        "controlled_boundary_exact": all(owner["config_entry_intentionally_disabled"] is True and owner["integration_internal_control_logic_executed"] is False for owner in owners),
        "external_controller_exact": all(row["external_controller"]["sha256"] == EXPECTED_CONTROLLER_SHA and row["external_controller"]["source_edited"] is False for row in results),
        "all_producer_gates_true": all(all(bool(value) for value in row["promotion_gates"].values()) for row in results),
        "two_independent_validators": all(row["pass"] is True for row in validations),
    }
    if not all(checks.values()):
        raise AssertionError(f"N2 v4 replication gates failed: {checks}")

    aggregate = {
        "schema": "agentmark.natural_controller.better_thermostat.replicated.v4",
        "decision": "PROMOTED_REPLICATED",
        "replicas": [0, 1],
        "independent_validations_passed": 2,
        "home_assistant_image_ref": image_ref,
        "external_controller": {
            "repository": "n3roGit/MyHomeAssistantMods",
            "commit": "57d56f076c05ccaa9553e6bd4b673b6d43a8cf7f",
            "path": "automation/BetterThermostatControl/BetterThermostat_RoomHeatControl_Lean.yaml",
            "sha256": EXPECTED_CONTROLLER_SHA,
            "source_edited": False,
        },
        "controlled_device_ownership": {
            "mode": EXPECTED_MODE,
            "config_entry_registration_path": EXPECTED_REGISTRATION_PATH,
            "upstream_repository": "KartoffelToby/better_thermostat",
            "upstream_commit": EXPECTED_BT_COMMIT,
            "upstream_version": EXPECTED_BT_VERSION,
            "upstream_manifest_sha256": EXPECTED_BT_MANIFEST_SHA,
            "component_tree_sha256": tree_hashes[0],
            "loader_qualification_before_outcome": True,
            "integration_setup_invoked": False,
            "config_entry_intentionally_disabled": True,
            "integration_internal_control_logic_executed": False,
        },
        "measurement_contract": {
            "pre_action_state": "explicit synchronous snapshot before feedback transition or replay service call",
            "event_callback_state_read": "diagnostic only; not treated as strict pre-handler state",
        },
        "trial_counts": {
            "native_target_per_replica": 6,
            "recorded_replay_per_replica": 6,
            "no_shift_controls_per_replica": 6,
            "native_target_total": 12,
            "recorded_replay_total": 12,
            "no_shift_controls_total": 12,
        },
        "recomputed_across_replicas": {
            "source_identities": source_ids,
            "target_identities": target_ids,
            "TV_operation_each_runner": tv_ops,
            "TV_action_each_runner": tv_actions,
            "TV_operation": 0.0,
            "TV_action": 1.0,
            "ownership_component_tree_sha256_each_runner": tree_hashes,
        },
        "replication_gates": checks,
        "runner_validations": [
            {
                "replica": i,
                "upstream_recomputed": validation_by_replica[i]["upstream_recomputed"],
                "observer_ordering_diagnostics": validation_by_replica[i]["observer_ordering_diagnostics"],
                "recomputed": validation_by_replica[i]["recomputed"],
            }
            for i in (0, 1)
        ],
        "claim_boundary": (
            "N2 establishes, for this independently authored Home Assistant controller, "
            "that operation identity remains unchanged while rendered consequential action "
            "semantics change under HOME versus AWAY feedback: TV_operation=0 and "
            "TV_action=1. Upstream Better Thermostat is exact-source-pinned and "
            "Home-Assistant-loader-qualified for registry ownership provenance; its PID/TRV "
            "internals and physical-device behavior are intentionally outside this experiment."
        ),
    }
    Path(args.out).write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"decision": aggregate["decision"], "recomputed": aggregate["recomputed_across_replicas"], "measurement_contract": aggregate["measurement_contract"], "replication_gates": checks}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
