from __future__ import annotations

import argparse
import json
from pathlib import Path

EXPECTED_CONTROLLER_SHA = "16d52ce11dec44fa9ca533d15f3cec1eb9646d59bf6a455bd905af63cdf86443"
EXPECTED_IMAGE = "ghcr.io/home-assistant/home-assistant@sha256:372d991e58882a1d8c68c07e9aa3f3b509276e695355f73ccdb03baa70407293"
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
    ap = argparse.ArgumentParser()
    ap.add_argument("results", nargs=2)
    ap.add_argument("--validations", nargs=2, required=True)
    ap.add_argument("--image-ref-file", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    results = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.results]
    validations = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.validations]
    image_ref = Path(args.image_ref_file).read_text(encoding="utf-8").strip()

    result_by_id = {int(r["replica"]): r for r in results}
    val_by_id = {int(v["replica"]): v for v in validations}
    if sorted(result_by_id) != [0, 1] or sorted(val_by_id) != [0, 1]:
        raise AssertionError("aggregate requires exactly producer/validator replicas 0 and 1")
    if image_ref != EXPECTED_IMAGE:
        raise AssertionError(f"HA image mismatch: {image_ref}")
    if not all(r["schema"] == "agentmark.natural_controller.better_thermostat_action_identity.v3" for r in results):
        raise AssertionError("producer schema mismatch")
    if not all(v["schema"] == "agentmark.natural_controller.better_thermostat.validation.v3" for v in validations):
        raise AssertionError("validator schema mismatch")
    if not all(r["decision"] == "PROMOTED" for r in results):
        raise AssertionError("both producers must promote")
    if not all(v["pass"] is True for v in validations):
        raise AssertionError("both independent validators must pass")

    source_ids = [val_by_id[i]["recomputed"]["source_identity"] for i in (0, 1)]
    target_ids = [val_by_id[i]["recomputed"]["target_identity"] for i in (0, 1)]
    tv_ops = [float(val_by_id[i]["recomputed"]["TV_operation"]) for i in (0, 1)]
    tv_actions = [float(val_by_id[i]["recomputed"]["TV_action"]) for i in (0, 1)]
    tree_hashes = [val_by_id[i]["recomputed"]["ownership_component_tree_sha256"] for i in (0, 1)]
    owners = [result_by_id[i]["controlled_device_ownership"] for i in (0, 1)]
    upstreams = [val_by_id[i]["upstream_recomputed"] for i in (0, 1)]

    checks = {
        "source_identity_replicates": source_ids == [EXPECTED_SOURCE, EXPECTED_SOURCE],
        "target_identity_replicates": target_ids == [EXPECTED_TARGET, EXPECTED_TARGET],
        "same_operation_across_feedback": all(source_ids[i]["operation"] == target_ids[i]["operation"] for i in (0, 1)),
        "different_full_action_across_feedback": all(source_ids[i] != target_ids[i] for i in (0, 1)),
        "tv_operation_exact_zero_each_runner": tv_ops == [0.0, 0.0],
        "tv_action_exact_one_each_runner": tv_actions == [1.0, 1.0],
        "component_tree_replicates": len(set(tree_hashes)) == 1,
        "upstream_manifest_exact": all(u["manifest_sha256"] == EXPECTED_BT_MANIFEST_SHA and u["domain"] == "better_thermostat" and u["version"] == EXPECTED_BT_VERSION for u in upstreams),
        "ownership_mode_exact": all(o["mode"] == EXPECTED_MODE for o in owners),
        "registration_path_exact": all(o["config_entry_registration_path"] == EXPECTED_REGISTRATION_PATH for o in owners),
        "upstream_commit_exact": all(o["upstream_commit"] == EXPECTED_BT_COMMIT for o in owners),
        "upstream_version_exact": all(o["upstream_version"] == EXPECTED_BT_VERSION for o in owners),
        "producer_tree_matches_validator": all(owners[i]["component_tree_sha256"] == tree_hashes[i] for i in (0, 1)),
        "loader_qualified_before_outcome": all(o["loader_qualification"]["domain"] == "better_thermostat" and o["loader_qualification"]["version"] == EXPECTED_BT_VERSION and o["loader_qualification"]["before_outcome"] is True and o["loader_qualification"]["integration_setup_invoked"] is False for o in owners),
        "controlled_boundary_exact": all(o["config_entry_intentionally_disabled"] is True and o["integration_internal_control_logic_executed"] is False for o in owners),
        "external_controller_exact": all(r["external_controller"]["sha256"] == EXPECTED_CONTROLLER_SHA and r["external_controller"]["source_edited"] is False for r in results),
        "all_producer_gates_true": all(all(bool(v) for v in r["promotion_gates"].values()) for r in results),
        "two_independent_validators": all(v["pass"] is True for v in validations),
    }
    if not all(checks.values()):
        raise AssertionError(f"N2 v3 replication gates failed: {checks}")

    aggregate = {
        "schema": "agentmark.natural_controller.better_thermostat.replicated.v3",
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
                "upstream_recomputed": val_by_id[i]["upstream_recomputed"],
                "recomputed": val_by_id[i]["recomputed"],
            }
            for i in (0, 1)
        ],
        "claim_boundary": (
            "N2 establishes, for this independently authored Home Assistant controller, "
            "that operation identity remains unchanged while rendered consequential action "
            "semantics change under HOME versus AWAY feedback. Upstream Better Thermostat "
            "is independently source-pinned and loader-qualified for ownership provenance; "
            "its PID/TRV internals and physical-device behavior are intentionally outside "
            "the experiment boundary."
        ),
    }
    Path(args.out).write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"decision": aggregate["decision"], "recomputed": aggregate["recomputed_across_replicas"], "ownership": aggregate["controlled_device_ownership"], "replication_gates": checks}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
