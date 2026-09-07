from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess


SCHEMA = "replaymark.s2q-source-calibration-verification.v1"
S2P_HEAD = "ce92490e546e25cae980b7c84806ff655f2c947d"
S2P_PROTOCOL_BLOB = "0a2160ed7fa7e50ba5641fa251b334e9e0cb7beb"
RUNNER = Path("agentmark_e3b_lab/e3_mqtt/app/replaymark_s2q_source_calibration.py")
PROTOCOL = Path("replaymark/S2_MIXED_CAPSTONE_PROTOCOL.json")
EXPECTED_INCREMENT = {
    ".github/workflows/replaymark-runtime-gate-s2q-source-calibration.yml",
    "agentmark_e3b_lab/e3_mqtt/app/replaymark_s2q_source_calibration.py",
    "replaymark/S2Q_SOURCE_ONLY_CALIBRATION.md",
    "replaymark_verification/verify_s2q_source_calibration.py",
}


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def _percentile(values: list[float], q: float) -> float:
    ys = sorted(values)
    pos = (len(ys) - 1) * q / 100.0
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return ys[lo]
    return ys[lo] * (hi - pos) + ys[hi] * (pos - lo)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _preflight() -> dict[str, object]:
    parent = _git("rev-parse", "HEAD^")
    if parent != S2P_HEAD:
        raise SystemExit(f"S2-Q must be exact child of S2-P: {parent} != {S2P_HEAD}")

    changed = set(_git("diff", "--name-only", S2P_HEAD, "HEAD").splitlines())
    if changed != EXPECTED_INCREMENT:
        raise SystemExit(
            "undeclared S2-Q increment: "
            f"missing={sorted(EXPECTED_INCREMENT - changed)} "
            f"extra={sorted(changed - EXPECTED_INCREMENT)}"
        )

    protocol_blob = _git("rev-parse", f"HEAD:{PROTOCOL}")
    if protocol_blob != S2P_PROTOCOL_BLOB:
        raise SystemExit("S2-P protocol blob drift")
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    if protocol["status"] != "FROZEN_BEFORE_SOURCE_CALIBRATION_AND_TARGET_OUTCOMES":
        raise SystemExit("S2-P prospective status drift")
    if protocol["phase_order"][1] != "S2Q_SOURCE_ONLY_CALIBRATION_AND_DSTAR_SEAL":
        raise SystemExit("S2-Q phase-order authority drift")

    s0_manifest = json.loads(
        Path("replaymark/CURRENT_RUNTIME_SEAL.json").read_text(encoding="utf-8")
    )
    if s0_manifest["optimization_policy"]["state"] != "FROZEN":
        raise SystemExit("runtime micro-optimization freeze drift")
    s0_matches = 0
    for rows in s0_manifest["frozen_blobs"].values():
        for path, expected in rows.items():
            actual = _git("rev-parse", f"HEAD:{path}")
            if actual != expected:
                raise SystemExit(f"S0 frozen blob drift: {path}")
            s0_matches += 1

    s1_matches = 0
    for path, expected in protocol["s1_frozen_blobs"].items():
        actual = _git("rev-parse", f"HEAD:{path}")
        if actual != expected:
            raise SystemExit(f"S1 frozen blob drift: {path}")
        s1_matches += 1

    source = RUNNER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: list[str] = []
    state_delay_args: list[object] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "set_state_delay":
                if len(node.args) != 1 or not isinstance(node.args[0], ast.Constant):
                    raise SystemExit("S2-Q set_state_delay is not a literal single argument")
                state_delay_args.append(node.args[0].value)

    forbidden_imports = [
        name
        for name in imports
        if name == "replaymark"
        or name.startswith("replaymark.")
        or name == "replaymark_oracle"
        or name.startswith("replaymark_oracle.")
    ]
    if forbidden_imports:
        raise SystemExit(f"source-only runner imports semantic/oracle code: {forbidden_imports}")
    if state_delay_args != [0]:
        raise SystemExit(f"source-only runner must set exactly delay 0 once: {state_delay_args}")
    if "-b/command" in source or "runner_derived_preview" not in source:
        raise SystemExit("source-only static boundary violation")

    return {
        "exact_s2p_parent": True,
        "declared_files_only": True,
        "s2p_protocol_blob": protocol_blob,
        "s0_frozen_blob_matches": s0_matches,
        "s1_frozen_blob_matches": s1_matches,
        "runtime_micro_optimization": "FROZEN",
        "runner_semantic_oracle_imports": 0,
        "runner_state_delay_literals": state_delay_args,
        "shifted_target_code_path_added": False,
    }


def _scientific_verify(result_path: Path) -> dict[str, object]:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    calibration = protocol["source_only_calibration"]
    result = json.loads(result_path.read_text(encoding="utf-8"))

    expected_params = {
        "replicates": calibration["replicates"],
        "tasks_per_replicate": calibration["tasks_per_replicate"],
        "wave_size": calibration["wave_size"],
        "wave_period_ms": calibration["wave_period_ms"],
        "verify_ms": calibration["verify_ms"],
        "task_timeout_ms": calibration["task_timeout_ms"],
    }
    structural_checks = {
        "schema": result.get("schema") == "replaymark.s2q-source-only-calibration.v1",
        "source_only": result.get("source_only") is True,
        "shifted_target_not_executed": result.get("shifted_target_executed") is False,
        "act2_candidate_not_constructed": result.get("act2_candidate_constructed") is False,
        "state_delay_zero": result.get("state_delay_ms") == 0,
        "parameters_exact": result.get("parameters") == expected_params,
        "broker_exact": result.get("broker") == "mosquitto version 2.1.2",
    }

    replicates = result.get("replicates")
    rows: list[dict[str, object]] = []
    row_checks: list[bool] = []
    if isinstance(replicates, list) and len(replicates) == calibration["replicates"]:
        for rep_index, rep in enumerate(replicates):
            rep_rows = rep.get("rows") if isinstance(rep, dict) else None
            if not isinstance(rep_rows, list) or len(rep_rows) != calibration["tasks_per_replicate"]:
                row_checks.append(False)
                continue
            if rep.get("replicate") != rep_index:
                row_checks.append(False)
            for task_id, row in enumerate(rep_rows):
                rows.append(row)
                try:
                    t0 = int(row["t0_mono_ns"])
                    publish = int(row["act1_publish_mono_ns"])
                    verify_deadline = int(row["verify_deadline_mono_ns"])
                    timeout_deadline = int(row["task_timeout_deadline_mono_ns"])
                    recv = row["state_on_recv_mono_ns"]
                    recv_int = None if recv is None else int(recv)
                    expected_device = str(row["device"])
                    completion = row["completion_offset_ms"]
                    completion_ok = (
                        recv_int is None and completion is None
                    ) or (
                        recv_int is not None
                        and completion is not None
                        and abs(float(completion) - ((recv_int - t0) / 1e6)) <= 1e-12
                    )
                    visible_expected = recv_int is not None and recv_int <= verify_deadline
                    row_checks.append(
                        row.get("replicate") == rep_index
                        and row.get("task_id") == task_id
                        and row.get("state_delay_ms") == 0
                        and expected_device.endswith(f"-{task_id}-a")
                        and publish >= t0
                        and verify_deadline == t0 + int(calibration["verify_ms"] * 1e6)
                        and timeout_deadline
                        == t0 + int(calibration["task_timeout_ms"] * 1e6)
                        and completion_ok
                        and row.get("visible_by_verify_deadline") is visible_expected
                        and (
                            recv_int is None
                            or (
                                row.get("completed_by_task_timeout") is True
                                and recv_int <= timeout_deadline
                                and row.get("event_on") is True
                                and row.get("event_device") == expected_device
                            )
                        )
                    )
                except (KeyError, TypeError, ValueError):
                    row_checks.append(False)
    else:
        row_checks.append(False)

    expected_count = calibration["pooled_sample_count"]
    complete_rows = [row for row in rows if row.get("completion_offset_ms") is not None]
    offsets = [float(row["completion_offset_ms"]) for row in complete_rows]
    row_count_exact = len(rows) == expected_count
    all_complete = len(offsets) == expected_count and all(
        row.get("completed_by_task_timeout") is True for row in rows
    )
    all_visible = len(rows) == expected_count and all(
        row.get("visible_by_verify_deadline") is True for row in rows
    )

    median_ms = statistics.median(offsets) if offsets else None
    p99_ms = _percentile(offsets, 99.0) if offsets else None
    d_star_ms = None
    if median_ms is not None:
        d_star_ms = math.floor((float(calibration["verify_ms"]) - median_ms) + 0.5)

    preview = result.get("runner_derived_preview", {})
    preview_checks = {
        "row_count": preview.get("row_count") == len(rows),
        "completion_count": preview.get("completion_count") == len(offsets),
        "all_tasks_complete": preview.get("all_tasks_complete") is all_complete,
        "all_visible": preview.get("all_source_state_visible_by_verify_deadline") is all_visible,
        "median": median_ms is not None
        and abs(float(preview.get("pooled_median_source_completion_ms")) - median_ms) <= 1e-12,
        "p99": p99_ms is not None
        and abs(float(preview.get("pooled_completion_p99_ms")) - p99_ms) <= 1e-12,
        "dstar": preview.get("D_star_ms") == d_star_ms,
    }

    qualification = {
        "all_576_rows_present": row_count_exact,
        "all_rows_structurally_valid": bool(row_checks) and all(row_checks),
        "all_tasks_complete": all_complete,
        "all_source_state_visible_by_verify_deadline": all_visible,
        "pooled_completion_p99_ms_at_most_80": p99_ms is not None
        and p99_ms <= float(calibration["qualification"]["pooled_completion_p99_ms_max"]),
        "dstar_minimum": d_star_ms is not None
        and d_star_ms >= int(calibration["dstar_rule"]["must_satisfy_min_ms"]),
        "dstar_below_verify_boundary": d_star_ms is not None
        and d_star_ms < int(calibration["dstar_rule"]["must_satisfy_max_exclusive_ms"]),
        "runner_preview_recomputed_exactly": all(preview_checks.values()),
    }

    return {
        "structural_checks": structural_checks,
        "qualification": qualification,
        "source_rows": len(rows),
        "pooled_median_source_completion_ms": median_ms,
        "pooled_completion_p99_ms": p99_ms,
        "D_star_ms": d_star_ms,
        "result_sha256": _sha256(result_path),
        "scientific_verdict": "PASS"
        if all(structural_checks.values()) and all(qualification.values())
        else "FAIL",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    preflight = _preflight()
    report: dict[str, object] = {
        "schema": SCHEMA,
        "preflight": preflight,
        "protocol_sha256": _sha256(PROTOCOL),
    }
    if args.preflight_only:
        report["verdict"] = "PASS"
    else:
        if not args.result:
            raise SystemExit("--result is required unless --preflight-only")
        scientific = _scientific_verify(Path(args.result))
        report["scientific"] = scientific
        report["verdict"] = scientific["scientific_verdict"]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
