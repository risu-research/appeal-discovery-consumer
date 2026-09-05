from __future__ import annotations

import argparse
import json
from pathlib import Path


EXPECTED_CONTROLLER_SHA = "16d52ce11dec44fa9ca533d15f3cec1eb9646d59bf6a455bd905af63cdf86443"
EXPECTED_IMAGE = "ghcr.io/home-assistant/home-assistant@sha256:372d991e58882a1d8c68c07e9aa3f3b509276e695355f73ccdb03baa70407293"
EXPECTED_BT_COMMIT = "b86561f61e5ba1259fc63e590f4847e9ac743d7f"
EXPECTED_BT_VERSION = "1.9.2"
EXPECTED_BT_MANIFEST_SHA = "710144c3d972501cc38b5a28e013a13a4c90e356039ffaff0b94327c7829bb28"
EXPECTED_OWNERSHIP_MODE = "upstream-domain-pinned-disabled-config-entry-controlled-device"
EXPECTED_SOURCE_IDENTITY = {
    "operation": "climate.set_preset_mode",
    "target_class": "climate",
    "variant": '{"preset_mode":"home"}',
}
EXPECTED_TARGET_IDENTITY = {
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
    validations = [
        json.loads(Path(p).read_text(encoding="utf-8")) for p in args.validations
    ]
    image_ref = Path(args.image_ref_file).read_text(encoding="utf-8").strip()

    result_replicas = sorted(int(r["replica"]) for r in results)
    validation_replicas = sorted(int(v["replica"]) for v in validations)
    if result_replicas != [0, 1]:
        raise AssertionError(f"expected producer replicas [0,1], got {result_replicas}")
    if validation_replicas != [0, 1]:
        raise AssertionError(
            f"expected validator replicas [0,1], got {validation_replicas}"
        )
    if image_ref != EXPECTED_IMAGE:
        raise AssertionError(f"immutable HA image mismatch: {image_ref}")
    if not all(
        r["schema"]
        == "agentmark.natural_controller.better_thermostat_action_identity.v2"
        for r in results
    ):
        raise AssertionError("all producer artifacts must use N2 v2 ownership schema")
    if not all(
        v["schema"]
        == "agentmark.natural_controller.better_thermostat.validation.v2"
        for v in validations
    ):
        raise AssertionError("all validator artifacts must use N2 validation v2 schema")
    if not all(v["pass"] is True for v in validations):
        raise AssertionError("both independent validations must pass")
    if not all(r["decision"] == "PROMOTED" for r in results):
        raise AssertionError("both producers must promote")
    if not all(
        r["external_controller"]["sha256"] == EXPECTED_CONTROLLER_SHA for r in results
    ):
        raise AssertionError("external controller source mismatch")

    validation_by_replica = {int(v["replica"]): v for v in validations}
    result_by_replica = {int(r["replica"]): r for r in results}
    for rid in (0, 1):
        if rid not in validation_by_replica or not validation_by_replica[rid]["pass"]:
            raise AssertionError(f"producer replica {rid} lacks its passing validator")
        if rid not in result_by_replica:
            raise AssertionError(f"missing producer replica {rid}")

    source_identities = [
        validation_by_replica[i]["recomputed"]["source_identity"] for i in (0, 1)
    ]
    target_identities = [
        validation_by_replica[i]["recomputed"]["target_identity"] for i in (0, 1)
    ]
    tv_ops = [
        float(validation_by_replica[i]["recomputed"]["TV_operation"])
        for i in (0, 1)
    ]
    tv_actions = [
        float(validation_by_replica[i]["recomputed"]["TV_action"])
        for i in (0, 1)
    ]
    tree_hashes = [
        validation_by_replica[i]["recomputed"]["ownership_component_tree_sha256"]
        for i in (0, 1)
    ]
    upstreams = [validation_by_replica[i]["upstream_recomputed"] for i in (0, 1)]
    producer_owners = [result_by_replica[i]["controlled_device_ownership"] for i in (0, 1)]

    checks = {
        "source_identity_replicates": source_identities
        == [EXPECTED_SOURCE_IDENTITY, EXPECTED_SOURCE_IDENTITY],
        "target_identity_replicates": target_identities
        == [EXPECTED_TARGET_IDENTITY, EXPECTED_TARGET_IDENTITY],
        "same_operation_across_feedback": all(
            source_identities[i]["operation"] == target_identities[i]["operation"]
            for i in (0, 1)
        ),
        "different_full_action_across_feedback": all(
            (
                source_identities[i]["operation"],
                source_identities[i]["target_class"],
                source_identities[i]["variant"],
            )
            != (
                target_identities[i]["operation"],
                target_identities[i]["target_class"],
                target_identities[i]["variant"],
            )
            for i in (0, 1)
        ),
        "tv_operation_exact_zero_each_runner": tv_ops == [0.0, 0.0],
        "tv_action_exact_one_each_runner": tv_actions == [1.0, 1.0],
        "upstream_component_tree_replicates": len(set(tree_hashes)) == 1,
        "upstream_manifest_exact_each_runner": all(
            u["manifest_sha256"] == EXPECTED_BT_MANIFEST_SHA
            and u["domain"] == "better_thermostat"
            and u["version"] == EXPECTED_BT_VERSION
            for u in upstreams
        ),
        "upstream_commit_exact_in_producers": all(
            owner["upstream_commit"] == EXPECTED_BT_COMMIT
            for owner in producer_owners
        ),
        "ownership_mode_exact_in_producers": all(
            owner["mode"] == EXPECTED_OWNERSHIP_MODE
            and owner["config_entry_intentionally_disabled"] is True
            and owner["integration_internal_control_logic_executed"] is False
            for owner in producer_owners
        ),
        "producer_tree_matches_independent_tree": all(
            producer_owners[i]["component_tree_sha256"] == tree_hashes[i]
            for i in (0, 1)
        ),
        "two_independent_validators": all(v["pass"] for v in validations),
        "all_producer_gates_true": all(
            all(bool(value) for value in result["promotion_gates"].values())
            for result in results
        ),
    }
    if not all(checks.values()):
        raise AssertionError(f"N2 replication gates failed: {checks}")

    aggregate = {
        "schema": "agentmark.natural_controller.better_thermostat.replicated.v2",
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
            "mode": EXPECTED_OWNERSHIP_MODE,
            "upstream_repository": "KartoffelToby/better_thermostat",
            "upstream_commit": EXPECTED_BT_COMMIT,
            "upstream_version": EXPECTED_BT_VERSION,
            "upstream_manifest_sha256": EXPECTED_BT_MANIFEST_SHA,
            "component_tree_sha256": tree_hashes[0],
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
            "source_identities": source_identities,
            "target_identities": target_identities,
            "TV_operation_each_runner": tv_ops,
            "TV_action_each_runner": tv_actions,
            "TV_operation": 0.0,
            "TV_action": 1.0,
            "ownership_component_tree_sha256_each_runner": tree_hashes,
        },
        "replication_gates": checks,
        "runner_validations": [
            {
                "replica": int(v["replica"]),
                "upstream_recomputed": v["upstream_recomputed"],
                "recomputed": v["recomputed"],
            }
            for v in sorted(validations, key=lambda x: int(x["replica"]))
        ],
        "claim_boundary": (
            "N2 establishes, for this independently authored Home Assistant controller, "
            "that operation identity can remain unchanged while rendered consequential "
            "action semantics change. The upstream Better Thermostat domain is used for "
            "native registry ownership only; its PID/TRV control internals are intentionally "
            "not executed, and physical-device behavior is not claimed."
        ),
    }
    Path(args.out).write_text(
        json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "decision": aggregate["decision"],
                "recomputed": aggregate["recomputed_across_replicas"],
                "ownership": aggregate["controlled_device_ownership"],
                "replication_gates": checks,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
