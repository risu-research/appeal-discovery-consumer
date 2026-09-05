from __future__ import annotations

"""Aggregate exactly two independently validated N2b replicas."""

import argparse
import json
from pathlib import Path
from typing import Any

RESULT_SCHEMA = "agentmark.natural_controller.better_thermostat_decision_equivalence.v1"
VALIDATION_SCHEMA = "agentmark.n2b.independent_validation.v1"
AGGREGATE_SCHEMA = "agentmark.n2b.replicated_aggregate.v1"
TRIALS = 6
EXPECTED_IDENTITY = {
    "operation": "climate.set_preset_mode",
    "target_class": "climate",
    "variant": '{"preset_mode":"away"}',
}


def load(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def exact_away_rows(rows: list[dict[str, Any]]) -> bool:
    return len(rows) == TRIALS and all(
        row.get("climate_call_count") == 1
        and row.get("call_counts") == {"climate.set_preset_mode": 1}
        and row.get("identity") == EXPECTED_IDENTITY
        for row in rows
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("results", nargs=2)
    p.add_argument("--validations", nargs=2, required=True)
    p.add_argument("--image-ref-file", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    results = [load(path) for path in args.results]
    vals = [load(path) for path in args.validations]
    image_ref = Path(args.image_ref_file).read_text(encoding="utf-8").strip()

    results.sort(key=lambda x: x["replica"])
    vals.sort(key=lambda x: x["replica"])

    theories = [r["theory"] for r in results]
    protocols = [r["frozen_protocol"] for r in results]
    externals = [r["external_controller"] for r in results]
    ownerships = [r["controlled_device_ownership"] for r in results]

    source_rows = [row for r in results for row in r["source_native"]]
    target_rows = [row for r in results for row in r["target_native"]]
    replay_rows = [row for r in results for row in r["target_replay"]]
    control_rows = [row for r in results for row in r["no_shift_replay"]]

    replay_support_failures = sum(
        int(row["support"]["action"]["support_failure"]) for row in replay_rows
    )
    control_support_failures = sum(
        int(row["support"]["action"]["support_failure"]) for row in control_rows
    )

    gates = {
        "exactly_two_replicas_0_1": [r["replica"] for r in results] == [0, 1],
        "result_schema_exact_all": all(r["schema"] == RESULT_SCHEMA for r in results),
        "validation_schema_exact_all": all(v["schema"] == VALIDATION_SCHEMA for v in vals),
        "validation_replicas_0_1": [v["replica"] for v in vals] == [0, 1],
        "independent_validators_pass_all": all(
            v["verdict"] == "PASS"
            and v["producer_consistent_with_independent_validation"] is True
            for v in vals
        ),
        "producer_promoted_all": all(
            r["decision"] == "PROMOTED"
            and r["promotion_gates"]["promoted"] is True
            for r in results
        ),
        "theory_identical_across_replicas": theories[0] == theories[1],
        "raw_feedback_tv_exact_one_all": all(t["raw_feedback_tv"] == 1.0 for t in theories),
        "quotient_feedback_tv_exact_zero_all": all(
            t["quotient_feedback_tv"] == 0.0 for t in theories
        ),
        "tv_operation_exact_zero_all": all(t["TV_operation"] == 0.0 for t in theories),
        "tv_action_exact_zero_all": all(t["TV_action"] == 0.0 for t in theories),
        "pair_restricted_eta_action_exact_zero_all": all(
            t["pair_restricted_eta_action"] == 0.0 for t in theories
        ),
        "source_native_away_exact_12_of_12": len(source_rows) == 12 and all(
            row["identity"] == EXPECTED_IDENTITY for row in source_rows
        ),
        "target_native_away_exact_12_of_12": len(target_rows) == 12 and all(
            row["identity"] == EXPECTED_IDENTITY for row in target_rows
        ),
        "target_replay_away_exact_12_of_12": len(replay_rows) == 12 and all(
            row["identity"] == EXPECTED_IDENTITY for row in replay_rows
        ),
        "control_replay_away_exact_12_of_12": len(control_rows) == 12 and all(
            row["identity"] == EXPECTED_IDENTITY for row in control_rows
        ),
        "all_condition_row_structures_exact": (
            exact_away_rows(source_rows[:6])
            and exact_away_rows(source_rows[6:])
            and exact_away_rows(target_rows[:6])
            and exact_away_rows(target_rows[6:])
            and exact_away_rows(replay_rows[:6])
            and exact_away_rows(replay_rows[6:])
            and exact_away_rows(control_rows[:6])
            and exact_away_rows(control_rows[6:])
        ),
        "target_replay_action_support_failures_zero": replay_support_failures == 0,
        "control_replay_action_support_failures_zero": control_support_failures == 0,
        "external_controller_identical_across_replicas": externals[0] == externals[1],
        "ownership_summary_identical_across_replicas": ownerships[0] == ownerships[1],
        "protocol_identical_across_replicas": protocols[0] == protocols[1],
    }
    promoted = all(gates.values())

    out = {
        "schema": AGGREGATE_SCHEMA,
        "decision": "PROMOTED_REPLICATED" if promoted else "NOT_PROMOTED",
        "replicas": [r["replica"] for r in results],
        "home_assistant_image_ref": image_ref,
        "theory": theories[0] if theories[0] == theories[1] else {"replica_theories": theories},
        "counts": {
            "source_native": len(source_rows),
            "target_native": len(target_rows),
            "target_replay": len(replay_rows),
            "no_shift_replay": len(control_rows),
            "target_replay_action_support_failures": replay_support_failures,
            "control_replay_action_support_failures": control_support_failures,
        },
        "external_controller": externals[0] if externals[0] == externals[1] else externals,
        "controlled_device_ownership": ownerships[0] if ownerships[0] == ownerships[1] else ownerships,
        "frozen_protocol": protocols[0] if protocols[0] == protocols[1] else protocols,
        "replica_validations": vals,
        "promotion_gates": gates,
    }

    Path(args.out).write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2, sort_keys=True))
    if not promoted:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
