from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics


EXPECTED_SHA = "e07ac35fae7270131f118da767b036e7f7776672077691d9fbcd026e5a7e3f9c"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("results", nargs=2)
    ap.add_argument("--validations", nargs=2, required=True)
    ap.add_argument("--image-ref-file", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    results = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.results]
    validations = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.validations]
    image_ref = Path(args.image_ref_file).read_text(encoding="utf-8").strip()

    if len({int(row["replica"]) for row in results}) != 2:
        raise AssertionError("need two distinct result replicas")
    if len({int(row["replica"]) for row in validations}) != 2:
        raise AssertionError("need two distinct validation replicas")
    if not all(bool(row["pass"]) for row in validations):
        raise AssertionError("all independent validations must pass")
    if not all(row["decision"] == "PROMOTED" for row in results):
        raise AssertionError("all producers must promote")
    if not all(row["external_controller"]["sha256"] == EXPECTED_SHA for row in results):
        raise AssertionError("external source mismatch")
    if not all(row["environment"]["home_assistant_core_version"] == "2026.9.0" for row in results):
        raise AssertionError("HA version mismatch")
    if "@sha256:" not in image_ref:
        raise AssertionError("aggregate image reference is not digest pinned")

    by_replica_validation = {int(row["replica"]): row for row in validations}
    for result in results:
        replica = int(result["replica"])
        if replica not in by_replica_validation or not by_replica_validation[replica]["pass"]:
            raise AssertionError(f"replica {replica} missing passing validation")

    all_r0 = [row for result in results for row in result["decisive"]["R0"]]
    all_r1 = [row for result in results for row in result["decisive"]["R1"]]
    all_r2 = [row for result in results for row in result["decisive"]["R2"]]

    def failure_rate(rows):
        return sum(bool(row["support"]["support_failure"]) for row in rows) / len(rows)

    aggregate = {
        "schema": "agentmark.natural_controller.motion_light.replicated.v1",
        "decision": "PROMOTED_REPLICATED",
        "replicas": sorted(int(row["replica"]) for row in results),
        "independent_validations_passed": 2,
        "home_assistant_image_ref": image_ref,
        "external_controller": {
            "repository": "home-assistant/core",
            "commit": "0cb25fe4727b5466743285f048eb6aa75fd02bbb",
            "path": "homeassistant/components/automation/blueprints/motion_light.yaml",
            "sha256": EXPECTED_SHA,
            "source_edited": False,
        },
        "trial_counts": {
            "per_mode_per_replica": 6,
            "per_mode_total": 12,
        },
        "recomputed_across_replicas": {
            "R0_support_failure_rate": failure_rate(all_r0),
            "R1_support_failure_rate": failure_rate(all_r1),
            "R2_support_failure_rate": failure_rate(all_r2),
            "R0_turn_off_mean_ms": statistics.fmean(float(row["turn_off_issue_ms"]) for row in all_r0),
            "R1_turn_off_mean_ms": statistics.fmean(float(row["turn_off_issue_ms"]) for row in all_r1),
            "R2_turn_off_mean_ms": statistics.fmean(float(row["turn_off_issue_ms"]) for row in all_r2),
            "runner_R1_minus_R0_mean_ms": [float(row["aggregate"]["R1_minus_R0_mean_ms"]) for row in results],
            "runner_R2_minus_source_mean_ms": [float(row["aggregate"]["R2_minus_source_mean_ms"]) for row in results],
        },
        "runner_summaries": [
            {
                "replica": int(result["replica"]),
                "source_turn_off_issue_ms": float(result["source"]["turn_off_issue_ms"]),
                "producer_aggregate": result["aggregate"],
                "validation_recomputed": by_replica_validation[int(result["replica"])]["recomputed"],
            }
            for result in sorted(results, key=lambda row: int(row["replica"]))
        ],
    }

    checks = {
        "R0_support_failure_all": aggregate["recomputed_across_replicas"]["R0_support_failure_rate"] == 1.0,
        "R1_support_failure_all": aggregate["recomputed_across_replicas"]["R1_support_failure_rate"] == 1.0,
        "R2_support_preserved_all": aggregate["recomputed_across_replicas"]["R2_support_failure_rate"] == 0.0,
        "R1_material_each_runner": all(value >= 20.0 for value in aggregate["recomputed_across_replicas"]["runner_R1_minus_R0_mean_ms"]),
        "R2_material_each_runner": all(value >= 80.0 for value in aggregate["recomputed_across_replicas"]["runner_R2_minus_source_mean_ms"]),
        "two_independent_validators": aggregate["independent_validations_passed"] == 2,
    }
    aggregate["replication_gates"] = checks
    if not all(checks.values()):
        raise AssertionError(f"replication gates failed: {checks}")

    Path(args.out).write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"decision": aggregate["decision"], "recomputed": aggregate["recomputed_across_replicas"], "replication_gates": checks}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
