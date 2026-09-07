from __future__ import annotations

import argparse
import ast
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "replaymark" / "S2P3_EMBEDDED_TIMESTAMP_TAIL_LOCALIZATION.json"
P3_PROTOCOL_HEAD = "496ceaead74df882e91b6c86670cc62329e6b88e"
P3_PROTOCOL_BLOB = "71f28ccdef82001a78e55b68a1dcee7f12c4768f"
DEVICE_BLOB = "27240e65cb8e1a7d788cc5dea8484cbad8ec6653"
EXPERIMENT_BLOB = "a5c7483b198bc03f251d31b75750c27fad1f2d29"
RUNNER = ROOT / "agentmark_e3b_lab/e3_mqtt/app/replaymark_s2p3_tail_localization.py"
EXPECTED_INCREMENT = {
    ".github/workflows/replaymark-runtime-gate-s2p3-tail-localization-execution.yml",
    "agentmark_e3b_lab/e3_mqtt/app/replaymark_s2p3_tail_localization.py",
    "replaymark/S2P3_EMBEDDED_TIMESTAMP_TAIL_LOCALIZATION_EXECUTION.md",
    "replaymark_verification/verify_s2p3_tail_localization.py",
}
SCHEDULE = [[16, 8, 4], [8, 4, 16], [4, 16, 8]]
SEGMENTS = [
    "scheduler_start_lateness_ms",
    "publish_call_overhead_ms",
    "forward_plus_device_ms",
    "post_device_observation_ms",
    "end_to_end_completion_ms",
    "puback_latency_ms",
]


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def pct(values: list[float], q: float) -> float:
    ys = sorted(values)
    pos = (len(ys) - 1) * q / 100.0
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return ys[lo]
    return ys[lo] * (hi - pos) + ys[hi] * (pos - lo)


def stats(values: list[float]) -> dict[str, float]:
    return {
        "p50": statistics.median(values),
        "p95": pct(values, 95),
        "p99": pct(values, 99),
        "max": max(values),
    }


def monotonic_offset_zero(text: str) -> bool:
    for line in text.splitlines():
        parts = line.split()
        if parts and parts[0] == "monotonic" and len(parts) >= 3:
            return int(parts[1]) == 0 and int(parts[2]) == 0
    return False


def preflight() -> dict[str, object]:
    if git("rev-parse", "HEAD^") != P3_PROTOCOL_HEAD:
        raise SystemExit("P3 execution must be exact child of P3 protocol authority")
    changed = set(git("diff", "--name-only", P3_PROTOCOL_HEAD, "HEAD").splitlines())
    if changed != EXPECTED_INCREMENT:
        raise SystemExit(f"undeclared P3 execution increment: {sorted(changed)}")
    if git("rev-parse", "HEAD:replaymark/S2P3_EMBEDDED_TIMESTAMP_TAIL_LOCALIZATION.json") != P3_PROTOCOL_BLOB:
        raise SystemExit("P3 protocol blob drift")
    if git("rev-parse", "HEAD:agentmark_e3b_lab/e3_mqtt/app/device.py") != DEVICE_BLOB:
        raise SystemExit("device blob drift")
    if git("rev-parse", "HEAD:agentmark_e3b_lab/e3_mqtt/app/experiment.py") != EXPERIMENT_BLOB:
        raise SystemExit("experiment blob drift")

    source = RUNNER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = []
    delay_literals = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "set_state_delay":
            if len(node.args) != 1 or not isinstance(node.args[0], ast.Constant):
                raise SystemExit("nonliteral set_state_delay")
            delay_literals.append(node.args[0].value)
    forbidden = [
        x for x in imports
        if x == "replaymark" or x.startswith("replaymark.")
        or x == "replaymark_oracle" or x.startswith("replaymark_oracle.")
    ]
    if forbidden:
        raise SystemExit(f"P3 runner imports semantic/oracle modules: {forbidden}")
    if delay_literals != [0]:
        raise SystemExit(f"P3 runner state delay drift: {delay_literals}")
    for token in ["-b/command", "D_star", "W_star"]:
        if token in source:
            raise SystemExit(f"P3 runner forbidden token: {token}")
    for token in ["ts_mono_ns", "act1_puback_mono_ns", "/proc/self/timens_offsets", "/proc/self/ns/time"]:
        if token not in source:
            raise SystemExit(f"P3 runner missing instrumentation: {token}")

    seal = json.loads((ROOT / "replaymark/CURRENT_RUNTIME_SEAL.json").read_text(encoding="utf-8"))
    if seal["optimization_policy"]["state"] != "FROZEN":
        raise SystemExit("runtime optimization reopened")
    frozen = 0
    for group in seal["frozen_blobs"].values():
        for path, expected in group.items():
            if git("rev-parse", f"HEAD:{path}") != expected:
                raise SystemExit(f"S0 frozen blob drift: {path}")
            frozen += 1
    return {
        "exact_p3_protocol_parent": True,
        "declared_files_only": True,
        "device_blob": DEVICE_BLOB,
        "experiment_blob": EXPERIMENT_BLOB,
        "runner_semantic_oracle_imports": 0,
        "runner_state_delay_literals": delay_literals,
        "s0_frozen_blob_matches": frozen,
        "runtime_micro_optimization": "FROZEN",
        "shifted_target_code_path_added": False,
    }


def verify_round(path: Path, expected_round: int) -> tuple[list[dict[str, object]], dict[str, object]]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    checks = {
        "schema": obj.get("schema") == "replaymark.s2p3-embedded-timestamp-tail-round.v1",
        "source_only": obj.get("source_only") is True,
        "target_absent": obj.get("shifted_target_executed") is False,
        "act2_absent": obj.get("act2_candidate_constructed") is False,
        "delay_zero": obj.get("state_delay_ms") == 0,
        "broker_exact": obj.get("broker") == "mosquitto version 2.1.2",
        "round": obj.get("round_index") == expected_round,
        "order": obj.get("frozen_order") == SCHEDULE[expected_round],
    }
    ns = obj.get("runner_time_namespace", {})
    checks["runner_ns_link"] = isinstance(ns.get("ns_time_link"), str) and ns["ns_time_link"].startswith("time:[")
    checks["runner_monotonic_offset_zero"] = monotonic_offset_zero(str(ns.get("timens_offsets", "")))

    cells = obj.get("cells")
    rows = []
    if not isinstance(cells, list) or len(cells) != 3:
        checks["cells"] = False
        return rows, checks
    checks["cells"] = True
    for position, cell in enumerate(cells):
        if cell.get("position") != position or cell.get("wave_size") != SCHEDULE[expected_round][position]:
            checks[f"cell_{position}_identity"] = False
            continue
        rs = cell.get("rows")
        if not isinstance(rs, list) or len(rs) != 192:
            checks[f"cell_{position}_rows"] = False
            continue
        checks[f"cell_{position}_identity"] = True
        checks[f"cell_{position}_rows"] = True
        rows.extend(rs)
    return rows, checks


def verify_device_info(path: Path) -> dict[str, object]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    return {
        "ns_link_valid": isinstance(obj.get("ns_time_link"), str) and obj["ns_time_link"].startswith("time:["),
        "monotonic_offset_zero": monotonic_offset_zero(str(obj.get("timens_offsets", ""))),
        "raw": obj,
    }


def scientific(round_paths: list[Path], device_paths: list[Path]) -> dict[str, object]:
    all_rows = []
    round_checks = []
    clock_checks = []
    unique_devices = set()
    per_cell_rows = defaultdict(list)
    for i, (rp, dp) in enumerate(zip(round_paths, device_paths)):
        rows, checks = verify_round(rp, i)
        dinfo = verify_device_info(dp)
        checks["device_ns_link"] = dinfo["ns_link_valid"]
        checks["device_monotonic_offset_zero"] = dinfo["monotonic_offset_zero"]
        round_checks.append(checks)
        clock_checks.extend([
            bool(checks["runner_monotonic_offset_zero"]),
            bool(dinfo["monotonic_offset_zero"]),
        ])
        for row in rows:
            all_rows.append(row)
            per_cell_rows[(i, int(row["position"]), int(row["wave_size"]))].append(row)

    row_valid = []
    additive_errors = []
    for row in all_rows:
        try:
            offer = int(row["offer_mono_ns"])
            start = int(row["task_start_mono_ns"])
            call = int(row["act1_publish_call_mono_ns"])
            ack = int(row["act1_puback_mono_ns"])
            dev = int(row["device_state_publish_mono_ns"])
            recv = int(row["state_on_recv_mono_ns"])
            device = str(row["device"])
            expected_end = (recv - start) / 1e6
            expected_pre = (dev - call) / 1e6
            expected_post = (recv - dev) / 1e6
            expected_pubover = (call - start) / 1e6
            expected_sched = (start - offer) / 1e6
            expected_ack = (ack - call) / 1e6
            values_ok = all(
                abs(float(row[k]) - v) <= 1e-9
                for k, v in [
                    ("end_to_end_completion_ms", expected_end),
                    ("forward_plus_device_ms", expected_pre),
                    ("post_device_observation_ms", expected_post),
                    ("publish_call_overhead_ms", expected_pubover),
                    ("scheduler_start_lateness_ms", expected_sched),
                    ("puback_latency_ms", expected_ack),
                ]
            )
            additive = abs(
                float(row["end_to_end_completion_ms"])
                - (
                    float(row["publish_call_overhead_ms"])
                    + float(row["forward_plus_device_ms"])
                    + float(row["post_device_observation_ms"])
                )
            )
            additive_errors.append(additive)
            order_ok = offer <= start <= call <= dev <= recv and call <= ack
            clock_checks.append(call <= dev <= recv)
            identity_ok = (
                row.get("completed_by_task_timeout") is True
                and row.get("event_on") is True
                and row.get("event_cause") == "command"
                and row.get("event_device") == device
                and device not in unique_devices
            )
            unique_devices.add(device)
            row_valid.append(values_ok and order_ok and identity_ok and additive <= 1e-9)
        except Exception:
            row_valid.append(False)

    structural = (
        len(all_rows) == 1728
        and len(unique_devices) == 1728
        and all(row_valid)
        and all(all(c.values()) for c in round_checks)
    )
    clock_valid = bool(clock_checks) and all(clock_checks)

    def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
        out = {}
        for seg in SEGMENTS:
            vals = [float(r[seg]) for r in rows]
            out[seg] = stats(vals)
        totals = [float(r["end_to_end_completion_ms"]) for r in rows]
        p95 = pct(totals, 95)
        tail = [r for r in rows if float(r["end_to_end_completion_ms"]) >= p95]
        pre_frac = [
            float(r["forward_plus_device_ms"]) / float(r["end_to_end_completion_ms"])
            for r in tail if float(r["end_to_end_completion_ms"]) > 0
        ]
        post_frac = [
            float(r["post_device_observation_ms"]) / float(r["end_to_end_completion_ms"])
            for r in tail if float(r["end_to_end_completion_ms"]) > 0
        ]
        out["tail"] = {
            "p95_boundary_ms": p95,
            "rows": len(tail),
            "median_forward_plus_device_fraction": statistics.median(pre_frac),
            "median_post_device_observation_fraction": statistics.median(post_frac),
        }
        out["visible_by_100ms"] = sum(bool(r["visible_by_verify_deadline"]) for r in rows)
        out["rows"] = len(rows)
        return out

    cells = {}
    for key, rows in sorted(per_cell_rows.items()):
        cells[f"r{key[0]}_p{key[1]}_w{key[2]}"] = summarize(rows)
    by_wave = {}
    for wave in [16, 8, 4]:
        rs = [r for r in all_rows if int(r["wave_size"]) == wave]
        by_wave[str(wave)] = summarize(rs)
    pooled = summarize(all_rows)

    pre_p99 = pooled["forward_plus_device_ms"]["p99"]
    post_p99 = pooled["post_device_observation_ms"]["p99"]
    pre_tail = pooled["tail"]["median_forward_plus_device_fraction"]
    post_tail = pooled["tail"]["median_post_device_observation_fraction"]

    if not clock_valid:
        classification = "CLOCK_DOMAIN_INVALID"
    elif post_p99 >= 4.0 * pre_p99 and post_tail >= 0.75:
        classification = "POST_DEVICE_DOMINANT"
    elif pre_p99 >= 4.0 * post_p99 and pre_tail >= 0.75:
        classification = "PRE_DEVICE_DOMINANT"
    else:
        classification = "MIXED_OR_UNLOCALIZED"

    return {
        "structural_complete": structural,
        "clock_domain_valid": clock_valid,
        "round_checks": round_checks,
        "rows": len(all_rows),
        "unique_devices": len(unique_devices),
        "max_additive_identity_error_ms": max(additive_errors) if additive_errors else None,
        "per_cell": cells,
        "per_wave": by_wave,
        "pooled": pooled,
        "localization_classification": classification,
        "q2_rehabilitated": False,
        "W_star": None,
        "D_star": None,
        "shifted_target_executed": False,
        "scientific_verdict": "PASS" if structural and clock_valid else "FAIL",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--round", action="append", default=[])
    parser.add_argument("--device-time-info", action="append", default=[])
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    report = {
        "schema": "replaymark.s2p3-tail-localization-verification.v1",
        "preflight": preflight(),
        "protocol_sha256": hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
    }
    if args.preflight_only:
        report["verdict"] = "PASS"
    else:
        if len(args.round) != 3 or len(args.device_time_info) != 3:
            raise SystemExit("exactly 3 round files and 3 device time-info files required")
        sci = scientific(
            [Path(x) for x in args.round],
            [Path(x) for x in args.device_time_info],
        )
        report["scientific"] = sci
        report["verdict"] = sci["scientific_verdict"]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
