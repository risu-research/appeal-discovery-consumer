from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "replaymark" / "S2P3_EMBEDDED_TIMESTAMP_TAIL_LOCALIZATION.json"

Q2_FAILURE_SEAL_HEAD = "0b24288d85958fd7b4f3dcd418fd7dda85bd4efc"
Q2_EXECUTION_HEAD = "79577a00e78aa61a5d92c6d608a9f64601bdb1d9"
P2_HEAD = "22ec2da2e62c1fa7e9d1a5e02ff676188d90ab5e"
DEVICE_BLOB = "27240e65cb8e1a7d788cc5dea8484cbad8ec6653"
EXPERIMENT_BLOB = "a5c7483b198bc03f251d31b75750c27fad1f2d29"
EXPECTED_INCREMENT = {
    ".github/workflows/replaymark-runtime-gate-s2p3-tail-localization-protocol.yml",
    "replaymark/S2P3_EMBEDDED_TIMESTAMP_TAIL_LOCALIZATION.json",
    "replaymark/S2P3_EMBEDDED_TIMESTAMP_TAIL_LOCALIZATION.md",
    "replaymark_verification/verify_s2p3_embedded_timestamp_tail_localization_protocol.py",
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    parent = git("rev-parse", "HEAD^")
    if parent != Q2_FAILURE_SEAL_HEAD:
        raise SystemExit(f"P3 must be exact child of Q2 failure seal: {parent}")

    changed = set(git("diff", "--name-only", Q2_FAILURE_SEAL_HEAD, "HEAD").splitlines())
    if changed != EXPECTED_INCREMENT:
        raise SystemExit(f"undeclared P3 protocol increment: {sorted(changed)}")

    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    if protocol["schema"] != "replaymark.s2p3-embedded-timestamp-tail-localization-protocol.v1":
        raise SystemExit("foreign P3 protocol schema")
    if protocol["status"] != "FROZEN_BEFORE_P3_SOURCE_EXECUTION":
        raise SystemExit("P3 is not prospective")
    if protocol["next_gate"] != "S2P3E_EMBEDDED_TIMESTAMP_TAIL_LOCALIZATION_EXECUTION":
        raise SystemExit("wrong P3 next gate")

    authorities = protocol["authorities"]
    if authorities["q2_failure_seal_head"] != Q2_FAILURE_SEAL_HEAD:
        raise SystemExit("Q2 failure authority drift")
    if authorities["q2_execution_head"] != Q2_EXECUTION_HEAD:
        raise SystemExit("Q2 execution authority drift")
    if authorities["p2_protocol_head"] != P2_HEAD:
        raise SystemExit("P2 authority drift")

    if git("rev-parse", "HEAD:agentmark_e3b_lab/e3_mqtt/app/device.py") != DEVICE_BLOB:
        raise SystemExit("frozen device drift")
    if git("rev-parse", "HEAD:agentmark_e3b_lab/e3_mqtt/app/experiment.py") != EXPERIMENT_BLOB:
        raise SystemExit("frozen experiment harness drift")

    q2_seal = json.loads(
        (ROOT / "replaymark" / "S2Q2_SOURCE_LOAD_ENVELOPE_FAILURE_SEAL.json")
        .read_text(encoding="utf-8")
    )
    if q2_seal["status"] != "FROZEN_COMPLETE_SCIENTIFIC_FAILURE":
        raise SystemExit("Q2 failure seal status drift")
    if q2_seal["scientific_result"]["W_star_screen"] is not None:
        raise SystemExit("Q2 failure unexpectedly has W*")
    if q2_seal["scientific_result"]["D_star_ms"] is not None:
        raise SystemExit("Q2 failure unexpectedly has D*")

    device_source = (
        ROOT / "agentmark_e3b_lab/e3_mqtt/app/device.py"
    ).read_text(encoding="utf-8")
    ast.parse(device_source)
    if "ts_mono_ns" not in device_source or "time.monotonic_ns()" not in device_source:
        raise SystemExit("frozen device timestamp field unavailable")

    execution = protocol["source_only_execution"]
    if execution["waves"] != [16, 8, 4]:
        raise SystemExit("P3 wave set drift")
    expected_orders = [[16,8,4],[8,4,16],[4,16,8]]
    if [x["ordered_wave_sizes"] for x in execution["screening_schedule"]] != expected_orders:
        raise SystemExit("P3 schedule drift")
    if execution["total_rows"] != 1728 or execution["cells"] != 9:
        raise SystemExit("P3 row/cell plan drift")
    if execution["state_delay_ms"] != 0 or execution["shifted_target_executed"] is not False:
        raise SystemExit("P3 source-only boundary drift")
    if execution["act2_candidate_constructed"] is not False:
        raise SystemExit("P3 constructs ACT2")

    required = set(protocol["instrumentation"]["required_raw_timestamps"])
    expected_required = {
        "offer_mono_ns",
        "task_start_mono_ns",
        "act1_publish_call_mono_ns",
        "act1_puback_mono_ns",
        "device_state_publish_mono_ns_from_payload_ts_mono_ns",
        "state_on_recv_mono_ns",
    }
    if required != expected_required:
        raise SystemExit("P3 raw timestamp set drift")

    clock = protocol["clock_domain_qualification"]
    for key in [
        "capture_runner_time_namespace_link",
        "capture_runner_timens_offsets",
        "capture_device_time_namespace_link",
        "capture_device_timens_offsets",
        "require_runner_monotonic_offset_zero",
        "require_device_monotonic_offset_zero",
        "require_device_timestamp_not_after_runner_receive_for_every_row",
    ]:
        if clock[key] is not True:
            raise SystemExit(f"clock qualification weakened: {key}")

    anti = protocol["anti_repair"]
    if not all(v is True or v is False for v in anti.values()):
        raise SystemExit("P3 anti-repair lock malformed")
    required_true = [
        "Q2_failure_remains_authoritative",
        "first_complete_P3_execution_is_authoritative",
        "later_exact_repeats_are_replication_only",
        "no_80ms_threshold_relaxation",
        "no_broker_version_change",
        "no_candidate_insertion_after_freeze",
        "no_device_code_change",
        "no_qos_change",
        "no_target_execution",
        "no_target_informed_branching",
        "no_wave_rehabilitation",
    ]
    if not all(anti[k] is True for k in required_true):
        raise SystemExit("P3 anti-repair lock weakened")
    if anti["D_star_permitted"] is not False or anti["no_new_W_star"] is not True:
        raise SystemExit("P3 unexpectedly permits W*/D*")

    seal = json.loads((ROOT / "replaymark/CURRENT_RUNTIME_SEAL.json").read_text(encoding="utf-8"))
    if seal["optimization_policy"]["state"] != "FROZEN":
        raise SystemExit("runtime optimization freeze reopened")
    frozen = 0
    for group in seal["frozen_blobs"].values():
        for path, expected in group.items():
            if git("rev-parse", f"HEAD:{path}") != expected:
                raise SystemExit(f"S0 frozen blob drift: {path}")
            frozen += 1

    workflow = (
        ROOT / ".github/workflows/replaymark-runtime-gate-s2p3-tail-localization-protocol.yml"
    ).read_text(encoding="utf-8").lower()
    for token in ["docker compose", "runner_shadow", "set_state_delay("]:
        if token in workflow:
            raise SystemExit(f"protocol freeze workflow executes runtime token: {token}")

    report = {
        "schema": "replaymark.s2p3-tail-localization-protocol-freeze-gate.v1",
        "verdict": "PASS",
        "head": git("rev-parse", "HEAD"),
        "exact_q2_failure_parent": True,
        "declared_files_only": True,
        "protocol_sha256": sha256(PROTOCOL),
        "q2_failure_preserved": True,
        "q2_W_star": None,
        "q2_D_star": None,
        "device_blob": DEVICE_BLOB,
        "experiment_blob": EXPERIMENT_BLOB,
        "existing_device_timestamp_field": "ts_mono_ns",
        "source_rows_planned": 1728,
        "target_execution_permitted": False,
        "new_W_star_permitted": False,
        "D_star_permitted": False,
        "s0_frozen_blob_matches": frozen,
        "runtime_micro_optimization": "FROZEN",
        "next_gate": protocol["next_gate"],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
