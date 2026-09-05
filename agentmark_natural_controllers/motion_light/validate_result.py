from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import statistics
from typing import Any

from agentmark.kernel import ReactiveKernel
from agentmark.semantics import step_replay_validity


EXPECTED_SHA = "e07ac35fae7270131f118da767b036e7f7776672077691d9fbcd026e5a7e3f9c"
EXPECTED_PROTOCOL = {
    "source_feedback_ms": 60.0,
    "target_feedback_ms": 180.0,
    "source_turn_on_completion_delay_ms": 5.0,
    "target_turn_on_completion_delay_ms": 40.0,
    "turn_off_completion_delay_ms": 0.0,
    "blueprint_post_feedback_delay_s": 0.020,
    "trials": 6,
}


def kernel() -> ReactiveKernel:
    return ReactiveKernel(
        {
            "initial_state": "waiting",
            "feedback_alphabet": ["MOTION", "NO_MOTION"],
            "states": {
                "waiting": {
                    "MOTION": [{"p": 1, "operation": "WAIT", "next_state": "waiting"}],
                    "NO_MOTION": [{"p": 1, "operation": "light.turn_off", "next_state": "done"}],
                },
                "done": {
                    "MOTION": [{"p": 1, "operation": "STOP", "next_state": "done"}],
                    "NO_MOTION": [{"p": 1, "operation": "STOP", "next_state": "done"}],
                },
            },
        }
    )


def assert_check(condition: bool, label: str, checks: dict[str, bool]) -> None:
    checks[label] = bool(condition)
    if not condition:
        raise AssertionError(label)


def recompute_row(row: dict[str, Any]) -> dict[str, Any]:
    calls = row["raw_call_events"]
    counts = Counter(str(event["service"]) for event in calls)
    turn_on = [event for event in calls if event["service"] == "turn_on"]
    turn_off = [event for event in calls if event["service"] == "turn_off"]
    if len(turn_on) != 1 or len(turn_off) != 1:
        raise AssertionError(f"{row['label']}: invalid raw light call counts {dict(counts)}")
    off = turn_off[0]
    motion = off.get("motion_state_at_issue")
    target_feedback = "NO_MOTION" if motion == "off" else "MOTION"
    verdict = step_replay_validity(
        kernel(),
        state="waiting",
        source_feedback="NO_MOTION",
        target_feedback=target_feedback,
        recorded_event="light.turn_off",
        projection="operation",
    )
    raw_times = [float(event["t_ms"]) for event in calls]
    return {
        "counts": dict(sorted(counts.items())),
        "turn_on_issue_ms": float(turn_on[0]["t_ms"]),
        "turn_off_issue_ms": float(off["t_ms"]),
        "motion_state_at_turn_off": motion,
        "target_feedback": target_feedback,
        "support_failure": bool(verdict.support_failure),
        "source_probability": float(verdict.source_probability),
        "target_probability": float(verdict.target_probability),
        "contexts_nonempty": all(bool(str(event.get("context_id", ""))) for event in calls),
        "raw_call_times_monotonic": raw_times == sorted(raw_times),
    }


def validate(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    checks: dict[str, bool] = {}

    assert_check(payload["schema"] == "agentmark.natural_controller.motion_light.v1", "schema", checks)
    assert_check(payload["environment"]["home_assistant_core_version"] == "2026.9.0", "ha_version", checks)
    assert_check(payload["external_controller"]["sha256"] == EXPECTED_SHA, "external_sha", checks)
    assert_check(payload["external_controller"]["source_edited"] is False, "source_unedited", checks)
    assert_check(payload["frozen_protocol"] == EXPECTED_PROTOCOL, "protocol_exact", checks)

    inputs = payload["external_controller"]["blueprint_inputs"]
    assert_check(inputs["motion_entity"] == "binary_sensor.agentmark_motion", "motion_binding", checks)
    assert_check(inputs["light_target"] == {"entity_id": "light.agentmark_light"}, "light_binding", checks)
    assert_check(float(inputs["no_motion_wait_seconds"]) == 0.020, "delay_binding", checks)

    source = recompute_row(payload["source"])
    assert_check(source["counts"] == {"turn_off": 1, "turn_on": 1}, "source_counts", checks)
    assert_check(source["motion_state_at_turn_off"] == "off", "source_nomotion_before_off", checks)
    assert_check(not source["support_failure"], "source_support", checks)
    assert_check(source["turn_off_issue_ms"] < 130.0, "source_separation", checks)
    assert_check(source["contexts_nonempty"], "source_contexts", checks)
    assert_check(source["raw_call_times_monotonic"], "source_raw_monotonic", checks)

    decisive_recomputed: dict[str, list[dict[str, Any]]] = {}
    for mode in ("R0", "R1", "R2"):
        rows = payload["decisive"][mode]
        assert_check(len(rows) == 6, f"{mode}_trial_count", checks)
        decisive_recomputed[mode] = [recompute_row(row) for row in rows]
        for index, row in enumerate(decisive_recomputed[mode]):
            assert_check(row["counts"] == {"turn_off": 1, "turn_on": 1}, f"{mode}_t{index}_counts", checks)
            assert_check(row["contexts_nonempty"], f"{mode}_t{index}_contexts", checks)
            assert_check(row["raw_call_times_monotonic"], f"{mode}_t{index}_monotonic", checks)

    assert_check(all(row["support_failure"] for row in decisive_recomputed["R0"]), "R0_support_failure_all", checks)
    assert_check(all(row["motion_state_at_turn_off"] == "on" for row in decisive_recomputed["R0"]), "R0_motion_all", checks)
    assert_check(all(row["support_failure"] for row in decisive_recomputed["R1"]), "R1_support_failure_all", checks)
    assert_check(all(row["motion_state_at_turn_off"] == "on" for row in decisive_recomputed["R1"]), "R1_motion_all", checks)
    assert_check(all(not row["support_failure"] for row in decisive_recomputed["R2"]), "R2_support_preserved_all", checks)
    assert_check(all(row["motion_state_at_turn_off"] == "off" for row in decisive_recomputed["R2"]), "R2_nomotion_all", checks)

    r0_off = [row["turn_off_issue_ms"] for row in decisive_recomputed["R0"]]
    r1_off = [row["turn_off_issue_ms"] for row in decisive_recomputed["R1"]]
    r2_off = [row["turn_off_issue_ms"] for row in decisive_recomputed["R2"]]
    r1_shift = statistics.fmean(r1_off) - statistics.fmean(r0_off)
    r2_shift = statistics.fmean(r2_off) - source["turn_off_issue_ms"]
    assert_check(r1_shift >= 20.0, "R1_material_timing_shift", checks)
    assert_check(r2_shift >= 80.0, "R2_material_semantic_shift", checks)

    controls_recomputed: dict[str, list[dict[str, Any]]] = {}
    for mode in ("R0", "R1", "R2"):
        rows = payload["no_feedback_shift_control"][mode]
        assert_check(len(rows) == 6, f"noshift_{mode}_trial_count", checks)
        controls_recomputed[mode] = [recompute_row(row) for row in rows]
        for index, row in enumerate(controls_recomputed[mode]):
            assert_check(row["counts"] == {"turn_off": 1, "turn_on": 1}, f"noshift_{mode}_t{index}_counts", checks)
            assert_check(not row["support_failure"], f"noshift_{mode}_t{index}_support", checks)
            assert_check(row["motion_state_at_turn_off"] == "off", f"noshift_{mode}_t{index}_nomotion", checks)
            assert_check(row["contexts_nonempty"], f"noshift_{mode}_t{index}_contexts", checks)

    assert_check(payload["decision"] == "PROMOTED", "producer_promoted", checks)
    assert_check(all(bool(value) for value in payload["promotion_gates"].values()), "producer_gates_all_true", checks)

    return {
        "schema": "agentmark.natural_controller.motion_light.validation.v1",
        "input": str(path),
        "replica": payload["replica"],
        "pass": all(checks.values()),
        "checks": checks,
        "recomputed": {
            "source": source,
            "R0_support_failure_rate": sum(row["support_failure"] for row in decisive_recomputed["R0"]) / 6,
            "R1_support_failure_rate": sum(row["support_failure"] for row in decisive_recomputed["R1"]) / 6,
            "R2_support_failure_rate": sum(row["support_failure"] for row in decisive_recomputed["R2"]) / 6,
            "R0_turn_off_mean_ms": statistics.fmean(r0_off),
            "R1_turn_off_mean_ms": statistics.fmean(r1_off),
            "R2_turn_off_mean_ms": statistics.fmean(r2_off),
            "R1_minus_R0_mean_ms": r1_shift,
            "R2_minus_source_mean_ms": r2_shift,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("result")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    report = validate(Path(args.result))
    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"replica": report["replica"], "pass": report["pass"], "recomputed": report["recomputed"]}, indent=2, sort_keys=True))
    if not report["pass"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
