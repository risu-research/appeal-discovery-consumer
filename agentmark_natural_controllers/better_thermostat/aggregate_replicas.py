from __future__ import annotations

import argparse
import json
from pathlib import Path


EXPECTED_SHA = "16d52ce11dec44fa9ca533d15f3cec1eb9646d59bf6a455bd905af63cdf86443"
EXPECTED_IMAGE = "ghcr.io/home-assistant/home-assistant@sha256:372d991e58882a1d8c68c07e9aa3f3b509276e695355f73ccdb03baa70407293"


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

    result_replicas = sorted(int(r["replica"]) for r in results)
    validation_replicas = sorted(int(v["replica"]) for v in validations)
    if result_replicas != [0, 1]:
        raise AssertionError(f"expected producer replicas [0,1], got {result_replicas}")
    if validation_replicas != [0, 1]:
        raise AssertionError(f"expected validator replicas [0,1], got {validation_replicas}")
    if image_ref != EXPECTED_IMAGE:
        raise AssertionError(f"immutable HA image mismatch: {image_ref}")
    if not all(v["pass"] is True for v in validations):
        raise AssertionError("both independent validations must pass")
    if not all(r["decision"] == "PROMOTED" for r in results):
        raise AssertionError("both producers must promote")
    if not all(r["external_controller"]["sha256"] == EXPECTED_SHA for r in results):
        raise AssertionError("external controller source mismatch")

    validation_by_replica = {int(v["replica"]): v for v in validations}
    for result in results:
        rid = int(result["replica"])
        if rid not in validation_by_replica or not validation_by_replica[rid]["pass"]:
            raise AssertionError(f"producer replica {rid} lacks its passing validator")

    # Recompute cross-replica invariants from independently recomputed identities.
    source_identities = [validation_by_replica[i]["recomputed"]["source_identity"] for i in (0, 1)]
    target_identities = [validation_by_replica[i]["recomputed"]["target_identity"] for i in (0, 1)]
    tv_ops = [float(validation_by_replica[i]["recomputed"]["TV_operation"]) for i in (0, 1)]
    tv_actions = [float(validation_by_replica[i]["recomputed"]["TV_action"]) for i in (0, 1)]

    checks = {
        "source_identity_replicates": source_identities[0] == source_identities[1] == {
            "operation": "climate.set_preset_mode",
            "target_class": "climate",
            "variant": '{"preset_mode":"home"}',
        },
        "target_identity_replicates": target_identities[0] == target_identities[1] == {
            "operation": "climate.set_preset_mode",
            "target_class": "climate",
            "variant": '{"preset_mode":"away"}',
        },
        "same_operation_across_feedback": all(
            source_identities[i]["operation"] == target_identities[i]["operation"]
            for i in (0, 1)
        ),
        "different_action_variant_across_feedback": all(
            source_identities[i]["variant"] != target_identities[i]["variant"]
            for i in (0, 1)
        ),
        "tv_operation_exact_zero_each_runner": tv_ops == [0.0, 0.0],
        "tv_action_exact_one_each_runner": tv_actions == [1.0, 1.0],
        "two_independent_validators": all(v["pass"] for v in validations),
        "all_producer_gates_true": all(
            all(bool(value) for value in result["promotion_gates"].values())
            for result in results
        ),
    }
    if not all(checks.values()):
        raise AssertionError(f"N2 replication gates failed: {checks}")

    aggregate = {
        "schema": "agentmark.natural_controller.better_thermostat.replicated.v1",
        "decision": "PROMOTED_REPLICATED",
        "replicas": [0, 1],
        "independent_validations_passed": 2,
        "home_assistant_image_ref": image_ref,
        "external_controller": {
            "repository": "n3roGit/MyHomeAssistantMods",
            "commit": "57d56f076c05ccaa9553e6bd4b673b6d43a8cf7f",
            "path": "automation/BetterThermostatControl/BetterThermostat_RoomHeatControl_Lean.yaml",
            "sha256": EXPECTED_SHA,
            "source_edited": False,
        },
        "trial_counts": {
            "native_target_per_replica": 6,
            "recorded_replay_per_replica": 6,
            "no_shift_controls_per_replica": 6,
        },
        "recomputed_across_replicas": {
            "source_identities": source_identities,
            "target_identities": target_identities,
            "TV_operation_each_runner": tv_ops,
            "TV_action_each_runner": tv_actions,
        },
        "replication_gates": checks,
        "runner_validations": [
            {
                "replica": int(v["replica"]),
                "recomputed": v["recomputed"],
            }
            for v in sorted(validations, key=lambda x: int(x["replica"]))
        ],
    }
    Path(args.out).write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"decision": aggregate["decision"], "recomputed": aggregate["recomputed_across_replicas"], "replication_gates": checks}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
