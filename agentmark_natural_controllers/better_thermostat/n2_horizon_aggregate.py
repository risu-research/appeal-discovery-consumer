from __future__ import annotations

"""Aggregate two independently validated N2 horizon runtime replicas."""

import argparse
import json
from pathlib import Path
from typing import Any

REPORT_SCHEMA = "replaymark.better_thermostat.horizon_runtime.v1"
VALIDATION_SCHEMA = "replaymark.better_thermostat.horizon_runtime.validation.v2"
AGG_SCHEMA = "replaymark.better_thermostat.horizon_runtime.aggregate.v2"


def load(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def summarize_rows(rows: list[dict[str, Any]], depth: int, motion: str) -> dict[str, Any]:
    selected = [r for r in rows if r["depth"] == depth and r["motion"] == motion]
    sequences = [
        r["observed_service_presets"] if depth == 1 else r["observed_output_sequence"]
        for r in selected
    ]
    return {
        "cells": len(selected),
        "all_producer_pass": all(r["producer_pass"] for r in selected),
        "unique_sequences": sorted({json.dumps(s) for s in sequences}),
    }


def aggregate(reports: list[dict[str, Any]], vals: list[dict[str, Any]], image_ref: str) -> dict[str, Any]:
    if len(reports) != 2 or len(vals) != 2:
        raise AssertionError("exactly two reports and two validations required")
    if any(r["schema"] != REPORT_SCHEMA for r in reports):
        raise AssertionError("report schema mismatch")
    if any(v["schema"] != VALIDATION_SCHEMA for v in vals):
        raise AssertionError("validation schema mismatch")

    report_by_replica = {int(r["replica"]): r for r in reports}
    val_by_replica = {int(v["replica"]): v for v in vals}
    if set(report_by_replica) != {0, 1} or set(val_by_replica) != {0, 1}:
        raise AssertionError("replicas must be exactly {0,1}")

    all_rows: list[dict[str, Any]] = []
    for replica in (0, 1):
        all_rows.extend(report_by_replica[replica]["depth1_rows"])
        all_rows.extend(report_by_replica[replica]["depth2_rows"])

    source_hashes = {r["external_controller"]["sha256"] for r in reports}
    tree_hashes = {r["ownership_component"]["component_tree_sha256"] for r in reports}
    versions = {r["environment"]["home_assistant_core_version"] for r in reports}

    d1_off = summarize_rows(all_rows, 1, "off")
    d1_on = summarize_rows(all_rows, 1, "on")
    d2_off = summarize_rows(all_rows, 2, "off")
    d2_on = summarize_rows(all_rows, 2, "on")

    checks = {
        "replica_reports_promoted": all(report_by_replica[i]["decision"] == "PROMOTED" for i in (0, 1)),
        "independent_validators_pass": all(val_by_replica[i]["decision"] == "PASS" for i in (0, 1)),
        "ha_image_digest_exact": image_ref == "ghcr.io/home-assistant/home-assistant@sha256:372d991e58882a1d8c68c07e9aa3f3b509276e695355f73ccdb03baa70407293",
        "ha_version_same_and_exact": versions == {"2026.9.0"},
        "external_controller_hash_same": len(source_hashes) == 1,
        "ownership_component_tree_same": len(tree_hashes) == 1,
        "depth1_motion_off_12_cells": d1_off["cells"] == 12,
        "depth1_motion_on_12_cells": d1_on["cells"] == 12,
        "depth2_motion_off_12_cells": d2_off["cells"] == 12,
        "depth2_motion_on_12_cells": d2_on["cells"] == 12,
        "depth1_off_sequence_exact": d1_off["unique_sequences"] == ['["away", "home"]'],
        "depth1_on_sequence_exact": d1_on["unique_sequences"] == ['["away", "comfort"]'],
        "depth2_off_sequence_exact": d2_off["unique_sequences"] == ['["NO_ACTION", "home"]'],
        "depth2_on_sequence_exact": d2_on["unique_sequences"] == ['["NO_ACTION", "comfort"]'],
        "all_rows_producer_pass": all(r["producer_pass"] for r in all_rows),
    }
    promoted = all(checks.values())

    return {
        "schema": AGG_SCHEMA,
        "decision": "PROMOTED" if promoted else "NOT_PROMOTED",
        "home_assistant_image_ref": image_ref,
        "replicas": [0, 1],
        "total_runtime_cells": len(all_rows),
        "cells": {
            "depth1_motion_off": d1_off,
            "depth1_motion_on": d1_on,
            "depth2_motion_off": d2_off,
            "depth2_motion_on": d2_on,
        },
        "frozen_shortest_witnesses": {
            "n2b_depth1": {
                "shared_current_output": "away",
                "suffix": ["presence_toggle"],
                "motion_off_output": "home",
                "motion_on_output": "comfort",
                "realized_in_live_ha": promoted,
            },
            "depth2": {
                "shared_step1_output": "NO_ACTION",
                "suffix": ["presence_toggle", "night_toggle"],
                "motion_off_output": "home",
                "motion_on_output": "comfort",
                "realized_in_live_ha": promoted,
            },
        },
        "promotion_checks": checks,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("reports", nargs=2)
    p.add_argument("--validations", nargs=2, required=True)
    p.add_argument("--image-ref-file", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    result = aggregate(
        [load(path) for path in args.reports],
        [load(path) for path in args.validations],
        Path(args.image_ref_file).read_text().strip(),
    )
    Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "decision": result["decision"],
        "total_runtime_cells": result["total_runtime_cells"],
        "promotion_checks": result["promotion_checks"],
    }, indent=2, sort_keys=True))
    if result["decision"] != "PROMOTED":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
