from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import statistics
from typing import Any

from agentmark.certificate import high_confidence_replay_certificate, trace_compatibility
from agentmark.kernel import ReactiveKernel

MODES = ("R0", "R1", "R2")


def sensitive_kernel() -> ReactiveKernel:
    return ReactiveKernel({
        "initial_state": "decision",
        "feedback_alphabet": ["VISIBLE", "MISS"],
        "states": {
            "decision": {
                "VISIBLE": [{"p": 1, "operation": "ACT2", "next_state": "done"}],
                "MISS": [{"p": 1, "operation": "VERIFY", "next_state": "verified"}],
            },
            "verified": {
                "VISIBLE": [{"p": 1, "operation": "ACT2", "next_state": "done"}],
                "MISS": [{"p": 1, "operation": "ACT2", "next_state": "done"}],
            },
            "done": {
                "VISIBLE": [{"p": 1, "operation": "STOP", "next_state": "done"}],
                "MISS": [{"p": 1, "operation": "STOP", "next_state": "done"}],
            },
        },
    })


def insensitive_kernel() -> ReactiveKernel:
    return ReactiveKernel({
        "initial_state": "decision",
        "feedback_alphabet": ["VISIBLE", "MISS"],
        "states": {
            "decision": {
                "VISIBLE": [{"p": 1, "operation": "ACT2", "next_state": "done"}],
                "MISS": [{"p": 1, "operation": "ACT2", "next_state": "done"}],
            },
            "done": {
                "VISIBLE": [{"p": 1, "operation": "STOP", "next_state": "done"}],
                "MISS": [{"p": 1, "operation": "STOP", "next_state": "done"}],
            },
        },
    })


def assert_true(cond: bool, label: str, checks: dict[str, bool]) -> None:
    checks[label] = bool(cond)
    if not cond:
        raise AssertionError(label)


def calls_for(raw_calls: list[dict[str, Any]], run_id: str) -> list[dict[str, Any]]:
    return [e for e in raw_calls if str((e.get("service_data") or {}).get("run_id")) == run_id]


def states_for(raw_states: list[dict[str, Any]], run_id: str) -> list[dict[str, Any]]:
    return [e for e in raw_states if str((e.get("attributes") or {}).get("agentmark_run")) == run_id]


def verify_context_lineage(calls: list[dict[str, Any]], states: list[dict[str, Any]]) -> bool:
    by_key: dict[tuple[str, str], set[str]] = defaultdict(set)
    for e in calls:
        d = e["service_data"]
        by_key[(str(d.get("task_id")), str(e["service"]))].add(str(e["context_id"]))
    eligible = 0
    for e in states:
        attrs = e["attributes"]
        cause = attrs.get("cause")
        op = "act1" if cause == "act1_visible" else "act2" if cause == "act2_commit" else None
        if op is None:
            continue
        eligible += 1
        if str(e["context_id"]) not in by_key[(str(attrs.get("agentmark_task")), op)]:
            return False
    return eligible > 0


def summarize(rows: list[dict[str, Any]]) -> dict[str, float]:
    n = len(rows)
    return {
        "n": n,
        "miss_rate": sum(r["feedback_at_deadline"] == "MISS" for r in rows) / n,
        "support_violation_rate": sum(bool(r["support_violation"]) for r in rows) / n,
        "verify_fraction": sum(bool(r["verify_called"]) for r in rows) / n,
        "mean_shift_ms": statistics.fmean(float(r["act2_issue_shift_vs_source_ms"]) for r in rows),
        "max_abs_rigid_shift_ms": max(abs(float(r["act2_issue_shift_vs_source_ms"])) for r in rows),
    }


def check_replay_binding(rows: list[dict[str, Any]], source_by_idx: dict[int, dict[str, Any]]) -> bool:
    for r in rows:
        src = source_by_idx[int(r["task_index"])]
        if abs(float(r["source_act2_issue_ms"]) - float(src["act2_issue_ms"])) > 1e-9:
            return False
    return True


def validate(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    checks: dict[str, bool] = {}
    proto = payload["frozen_protocol"]
    tasks = int(proto["tasks"])
    trials = int(proto["trials"])
    verify_ms = float(proto["verify_deadline_ms"])
    source_delay = float(proto["source_delay_ms"])
    target_delay = float(proto["target_delay_ms"])

    assert_true(payload["schema"] == "agentmark.e3c.home_assistant.ecological.v1", "schema", checks)
    assert_true(payload["environment"]["home_assistant_core_version"] == "2026.9.0", "ha_version_exact", checks)
    assert_true(len(payload["source_trace"]) == tasks, "source_task_count", checks)
    assert_true(max(float(r["act1_complete_ms"]) for r in payload["source_trace"]) < verify_ms, "source_before_frozen_deadline", checks)
    source_by_idx = {int(r["task_index"]): r for r in payload["source_trace"]}

    raw_calls = payload["raw_native_events"]["call_service"]
    raw_states = payload["raw_native_events"]["state_changed"]
    raw_decisive = payload["raw_replay_rows"]["decisive"]

    sensitive = sensitive_kernel()
    all_mode_rows: dict[str, list[dict[str, Any]]] = {m: [] for m in MODES}
    trial_summaries = []

    for t in range(trials):
        tkey = str(t)
        row = {"trial": t}
        for mode in MODES:
            rows = raw_decisive[tkey][mode]
            all_mode_rows[mode].extend(rows)
            assert_true(len(rows) == tasks, f"t{t}_{mode}_task_count", checks)
            assert_true(check_replay_binding(rows, source_by_idx), f"t{t}_{mode}_source_trace_binding", checks)
            s = summarize(rows)
            run_id = f"decisive_t{t}_{mode.lower()}"
            calls = calls_for(raw_calls, run_id)
            states = states_for(raw_states, run_id)
            counts = Counter(str(e["service"]) for e in calls)
            expected = {"R0": {"act1": tasks, "act2": tasks}, "R1": {"act1": tasks, "act2": tasks}, "R2": {"act1": tasks, "verify": tasks, "act2": tasks}}[mode]
            assert_true(counts == Counter(expected), f"t{t}_{mode}_native_call_conservation", checks)
            assert_true(len(states) == 2 * tasks, f"t{t}_{mode}_native_state_conservation", checks)
            assert_true(verify_context_lineage(calls, states), f"t{t}_{mode}_context_lineage", checks)
            assert_true(s["miss_rate"] == 1.0, f"t{t}_{mode}_target_miss_all", checks)
            if mode in ("R0", "R1"):
                assert_true(s["support_violation_rate"] == 1.0, f"t{t}_{mode}_support_failure", checks)
                assert_true(s["verify_fraction"] == 0.0, f"t{t}_{mode}_no_verify", checks)
            else:
                assert_true(s["support_violation_rate"] == 0.0, f"t{t}_{mode}_support_preserved", checks)
                assert_true(s["verify_fraction"] == 1.0, f"t{t}_{mode}_verify_all", checks)
            row[mode] = {"summary": s, "native_counts": dict(counts)}
        r1_calls = sum(row["R1"]["native_counts"].values())
        r2_calls = sum(row["R2"]["native_counts"].values())
        assert_true(r2_calls * 2 == r1_calls * 3, f"t{t}_exact_1p5x_work", checks)
        trial_summaries.append(row)

    r0 = summarize(all_mode_rows["R0"])
    r1 = summarize(all_mode_rows["R1"])
    r2 = summarize(all_mode_rows["R2"])
    assert_true(r0["max_abs_rigid_shift_ms"] <= 35.0, "r0_rigid_timing_within_35ms", checks)
    assert_true(r1["mean_shift_ms"] >= max(25.0, (target_delay - source_delay) * 0.5), "r1_material_timing_feedback", checks)

    src_counts = {"VISIBLE": tasks * trials, "MISS": 0}
    tgt_counts = Counter(r["feedback_at_deadline"] for r in all_mode_rows["R1"])
    cert = high_confidence_replay_certificate(sensitive, "decision", src_counts, tgt_counts, delta=0.05, epsilon=0.05, projection="operation")
    assert_true(not cert["certified_safe_at_epsilon"], "sensitive_certificate_not_safe", checks)
    compat = trace_compatibility(sensitive, [{"state":"decision","source_feedback":"VISIBLE","target_feedback":r["feedback_at_deadline"],"operation":"ACT2"} for r in all_mode_rows["R1"]])
    assert_true(compat["support_failures"] == tasks * trials, "r1_agentmark_support_oracle_all_fail", checks)

    control_rows = payload["raw_replay_rows"]["controls"]
    for mode in MODES:
        rows = control_rows["no_feedback_shift"][mode]
        s = summarize(rows)
        run_id = f"control_noshift_{mode.lower()}"
        calls = calls_for(raw_calls, run_id)
        states = states_for(raw_states, run_id)
        counts = Counter(str(e["service"]) for e in calls)
        assert_true(s["miss_rate"] == 0.0, f"noshift_{mode}_visible_all", checks)
        assert_true(s["support_violation_rate"] == 0.0, f"noshift_{mode}_support_ok", checks)
        assert_true(s["verify_fraction"] == 0.0, f"noshift_{mode}_no_verify", checks)
        assert_true(counts == Counter({"act1":tasks,"act2":tasks}), f"noshift_{mode}_native_calls", checks)
        assert_true(len(states) == 2 * tasks, f"noshift_{mode}_native_states", checks)
        assert_true(verify_context_lineage(calls, states), f"noshift_{mode}_context_lineage", checks)

    for mode in MODES:
        rows = control_rows["feedback_insensitive"][mode]
        s = summarize(rows)
        run_id = f"control_insensitive_{mode.lower()}"
        calls = calls_for(raw_calls, run_id)
        states = states_for(raw_states, run_id)
        counts = Counter(str(e["service"]) for e in calls)
        assert_true(s["support_violation_rate"] == 0.0, f"insensitive_{mode}_support_ok", checks)
        assert_true(s["verify_fraction"] == 0.0, f"insensitive_{mode}_no_verify", checks)
        assert_true(counts == Counter({"act1":tasks,"act2":tasks}), f"insensitive_{mode}_native_calls", checks)
        assert_true(len(states) == 2 * tasks, f"insensitive_{mode}_native_states", checks)
        assert_true(verify_context_lineage(calls, states), f"insensitive_{mode}_context_lineage", checks)
    ins_rows = control_rows["feedback_insensitive"]["R1"]
    ins_tgt = Counter(r["feedback_at_deadline"] for r in ins_rows)
    ins_cert = high_confidence_replay_certificate(insensitive_kernel(), "decision", {"VISIBLE":tasks,"MISS":0}, ins_tgt, delta=0.05, epsilon=0.05, projection="operation")
    assert_true(ins_cert["certified_safe_at_epsilon"], "insensitive_certificate_safe", checks)

    assert_true(payload["decision"] == "PROMOTED", "producer_decision_promoted", checks)
    assert_true(all(payload["promotion_gates"].values()), "producer_promotion_gates_all_true", checks)

    return {
        "schema": "agentmark.e3c.home_assistant.independent_validation.v1",
        "input": str(path),
        "replica": payload.get("replica"),
        "pass": all(checks.values()),
        "checks": checks,
        "recomputed": {
            "aggregate": {"R0": r0, "R1": r1, "R2": r2},
            "sensitive_certificate": cert,
            "r1_trace_compatibility": compat,
            "feedback_insensitive_certificate": ins_cert,
            "trial_summaries": trial_summaries,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("result_json")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    report = validate(Path(args.result_json))
    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"pass": report["pass"], "replica": report["replica"], "aggregate": report["recomputed"]["aggregate"]}, indent=2, sort_keys=True))
    if not report["pass"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
