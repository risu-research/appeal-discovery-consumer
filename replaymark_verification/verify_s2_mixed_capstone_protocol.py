from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "replaymark" / "S2_MIXED_CAPSTONE_PROTOCOL.json"
S1_HEAD = "c93c8574eb62cb4dcde94890fdfc8f939b41e00a"
S0_HEAD = "8716db916c49578ee69930b973a44f892f975307"
S0_OPTIMIZATION_AUTHORITY = "25d317392b9ce6aaaedc190ef6aff8bc38d555b5"
S0_SEAL_MANIFEST_BLOB = "044ba2bd2f904921422485c746875cbe9c059933"
EXPECTED_SCHEDULE_SHA256 = "ec91b78a6720ef9b4e83da12f9b8cf37c1d05028bb6ebaf0e4c6a274ff372d1e"
EXPECTED_INCREMENT = {
    ".github/workflows/replaymark-runtime-gate-s2p-mixed-capstone-protocol.yml",
    "replaymark/S2_MIXED_CAPSTONE_PROTOCOL.json",
    "replaymark/S2_MIXED_CAPSTONE_PROTOCOL.md",
    "replaymark_verification/verify_s2_mixed_capstone_protocol.py",
}
S1_FROZEN_BLOBS = {
    ".github/workflows/replaymark-runtime-gate-s1-certified-execution-admission.yml": "7f85d5e83c791941bd03c9757b5ffa28608558c4",
    "agentmark_e3b_lab/e3_mqtt/app/replaymark_s1_admission_live.py": "4095bea2d7771fd0d52eb9027512baca2b945574",
    "replaymark/S1_CERTIFIED_EXECUTION_ADMISSION.md": "7b20d2cf24a6ae47801a84644a2a909356f05264",
    "replaymark/execution_admission.py": "015b2cfb7f084562eaead2dedd2fae00628eaffa",
    "replaymark/runtime_e3b_execution_gate.py": "22748a5aa820e83e4700a339e8af297cdd9f9143",
    "replaymark_oracle/execution_admission_oracle.py": "5850b10217265e24defe1d83d8981e7de8bcffcf",
    "replaymark_verification/verify_runtime_e3b_execution_admission.py": "9219f79f8acfdf19da3bd762c02dc2771b248e46",
}

def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")

def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()

def verify_git_boundary(protocol: dict[str, object]) -> dict[str, object]:
    parent = git("rev-parse", "HEAD^")
    if parent != S1_HEAD:
        raise AssertionError(f"S2-P must be exact child of S1: {parent} != {S1_HEAD}")
    changed = set(git("diff", "--name-only", S1_HEAD, "HEAD").splitlines())
    if changed != EXPECTED_INCREMENT:
        raise AssertionError(f"undeclared S2-P increment: missing={sorted(EXPECTED_INCREMENT - changed)} extra={sorted(changed - EXPECTED_INCREMENT)}")
    seal_blob = git("rev-parse", "HEAD:replaymark/CURRENT_RUNTIME_SEAL.json")
    if seal_blob != S0_SEAL_MANIFEST_BLOB:
        raise AssertionError("S0 runtime-seal manifest blob drift")
    seal = json.loads((ROOT / "replaymark" / "CURRENT_RUNTIME_SEAL.json").read_text(encoding="utf-8"))
    if seal["authority"]["commit"] != S0_OPTIMIZATION_AUTHORITY:
        raise AssertionError("S0 optimization authority drift")
    if seal["optimization_policy"]["state"] != "FROZEN":
        raise AssertionError("S0 runtime micro-optimization freeze reopened")
    frozen_matches = 0
    for group, rows in seal["frozen_blobs"].items():
        for path, expected in rows.items():
            actual = git("rev-parse", f"HEAD:{path}")
            if actual != expected:
                raise AssertionError(f"S0 frozen blob drift {group}:{path}: {actual} != {expected}")
            frozen_matches += 1
    s1_matches = 0
    for path, expected in S1_FROZEN_BLOBS.items():
        actual = git("rev-parse", f"HEAD:{path}")
        if actual != expected:
            raise AssertionError(f"S1 frozen blob drift {path}: {actual} != {expected}")
        s1_matches += 1
    authorities = protocol["authorities"]
    if authorities["s1_execution_admission_head"] != S1_HEAD:
        raise AssertionError("protocol does not bind exact S1 authority")
    if authorities["s0_seal_head"] != S0_HEAD:
        raise AssertionError("protocol does not bind exact S0 seal")
    if authorities["s0_optimization_authority"] != S0_OPTIMIZATION_AUTHORITY:
        raise AssertionError("protocol does not bind exact S0 optimization authority")
    return {"exact_s1_parent": True, "declared_files_only": True, "s0_frozen_blob_matches": frozen_matches, "s1_frozen_blob_matches": s1_matches, "runtime_micro_optimization": "FROZEN"}

def verify_protocol_boundary(protocol: dict[str, object]) -> dict[str, object]:
    if protocol["schema"] != "replaymark.s2-mixed-capstone-protocol.v1":
        raise AssertionError("foreign S2 protocol schema")
    if protocol["gate"] != "S2P_PRE_FROZEN_MIXED_CAPSTONE_PROTOCOL":
        raise AssertionError("wrong S2 protocol gate")
    if protocol["status"] != "FROZEN_BEFORE_SOURCE_CALIBRATION_AND_TARGET_OUTCOMES":
        raise AssertionError("protocol was not frozen prospectively")
    boundary = protocol["s2p_boundary"]
    for key in {"source_calibration_executed", "target_execution_permitted", "target_outcome_visibility_permitted", "new_semantic_theorem", "fallback_or_regeneration", "runtime_micro_optimization", "experiment_runner_added"}:
        if boundary[key] is not False:
            raise AssertionError(f"S2-P boundary unexpectedly enables {key}")
    if protocol["phase_order"] != ["S2P_PROTOCOL_FREEZE", "S2Q_SOURCE_ONLY_CALIBRATION_AND_DSTAR_SEAL", "S2E_LIVE_MIXED_CAPSTONE_FIRST_COMPLETE_RUN", "S2F_POST_EXECUTION_FALSIFICATION_AUDIT"]:
        raise AssertionError("S2 phase order drift")
    calibration = protocol["source_only_calibration"]
    if calibration["state_delay_ms"] != 0 or calibration["verify_ms"] != 100.0:
        raise AssertionError("source calibration boundary drift")
    if calibration["replicates"] != 3 or calibration["tasks_per_replicate"] != 192 or calibration["pooled_sample_count"] != 576:
        raise AssertionError("calibration sample plan drift")
    if calibration["wave_size"] != 32 or calibration["wave_period_ms"] != 300.0:
        raise AssertionError("calibration workload-shape drift")
    if calibration["qualification"]["pooled_completion_p99_ms_max"] != 80.0:
        raise AssertionError("source qualification p99 bound drift")
    dstar = calibration["dstar_rule"]
    if dstar["computed_once"] is not True or dstar["seal_before_any_target_outcome"] is not True or dstar["alternate_formula_forbidden"] is not True or dstar["retune_after_target_outcome_forbidden"] is not True:
        raise AssertionError("D_star prospective-seal rule drift")
    live = protocol["live_mixed_evaluation"]
    if live["verify_ms"] != 100.0 or live["trials"] != 6 or live["tasks_per_trial"] != 192 or live["total_tasks"] != 1152:
        raise AssertionError("live target plan drift")
    if live["wave_size"] != 32 or live["wave_period_ms"] != 300.0:
        raise AssertionError("live workload-shape drift")
    if live["task_specific_delay_forbidden"] is not True or live["adaptive_delay_forbidden"] is not True:
        raise AssertionError("target delay is not fixed")
    if not all(live["observation_phase"].values()):
        raise AssertionError("evidence-before-dispatch barrier is incomplete")
    dispatch = live["dispatch_phase"]
    if dispatch["automatic_retry"] is not False or dispatch["fallback"] is not False or dispatch["regeneration"] is not False or dispatch["broker_exactly_once_claim"] is not False:
        raise AssertionError("S2 dispatch boundary drift")
    evaluation = protocol["independent_evaluation"]
    if evaluation["oracle_imports_replaymark_production"] is not False or evaluation["live_dispatch_runner_imports_oracle"] is not False:
        raise AssertionError("oracle isolation drift")
    if evaluation["oracle_evaluation_time"] != "after all live dispatch is complete and the harness is closed":
        raise AssertionError("oracle evaluation timing drift")
    qualification = protocol["qualification_before_promotion"]
    if qualification["pooled_safe_fraction_min_inclusive"] != 0.20 or qualification["pooled_safe_fraction_max_inclusive"] != 0.80:
        raise AssertionError("mixed qualification interval drift")
    if qualification["each_policy_aggregate_safe_min"] != 64 or qualification["each_policy_aggregate_unsafe_min"] != 64:
        raise AssertionError("policy mixture floor drift")
    if qualification["qualification_failure_may_not_trigger_Dstar_retune"] is not True:
        raise AssertionError("qualification failure can trigger outcome fishing")
    replaymark = protocol["promotion_criteria"]["REPLAYMARK"]
    if replaymark != {"executed_task_set_equals_independent_oracle_safe_set": True, "safe_retention_rate": 1.0, "unnecessary_block_count": 0, "unsafe_execution_count": 0, "unsafe_execution_rate": 0.0}:
        raise AssertionError("ReplayMark exact-set promotion rule drift")
    return {"prospective_freeze": True, "source_only_calibration_fixed": True, "one_fixed_target_delay_required": True, "all_evidence_frozen_before_dispatch": True, "independent_oracle_after_execution": True, "post_hoc_retuning_forbidden": True, "latency_threshold": None}

def verify_policy_schedule(protocol: dict[str, object]) -> dict[str, object]:
    assignment = protocol["policy_assignment"]
    seed = assignment["seed"]
    permutations = assignment["permutation_order"]
    expected_policies = {"ALWAYS_ADMIT", "ALWAYS_BLOCK", "REPLAYMARK"}
    if len(permutations) != 6:
        raise AssertionError("policy permutation table must contain six rows")
    for permutation in permutations:
        if set(permutation) != expected_policies or len(permutation) != 3:
            raise AssertionError("invalid policy permutation")
    rows = []
    counts = defaultdict(Counter)
    for trial in range(6):
        for block in range(64):
            payload = f"{seed}|trial={trial}|block={block}".encode("utf-8")
            selector = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") % 6
            permutation = permutations[selector]
            for offset, policy in enumerate(permutation):
                task_id = block * 3 + offset
                rows.append({"trial": trial, "task_id": task_id, "policy": policy})
                counts[trial][policy] += 1
    schedule_digest = sha256_bytes(canonical_json_bytes(rows))
    if schedule_digest != EXPECTED_SCHEDULE_SHA256 or schedule_digest != assignment["schedule_sha256"]:
        raise AssertionError("policy schedule digest drift")
    for trial in range(6):
        if counts[trial] != Counter({"ALWAYS_ADMIT": 64, "ALWAYS_BLOCK": 64, "REPLAYMARK": 64}):
            raise AssertionError(f"unbalanced policy assignment in trial {trial}")
    return {"schedule_rows": len(rows), "schedule_sha256": schedule_digest, "trials": 6, "tasks_per_trial": 192, "tasks_per_policy_per_trial": 64, "outcome_blind": assignment["outcome_blind"], "certificate_blind": assignment["certificate_blind"]}

def verify_no_result_bearing_increment() -> dict[str, object]:
    for path in EXPECTED_INCREMENT:
        if path.endswith(("_result.json", "_results.json", "_live.py", "_experiment.py", "_runner.py")):
            raise AssertionError(f"result-bearing or execution file in S2-P: {path}")
    workflow = (ROOT / ".github" / "workflows" / "replaymark-runtime-gate-s2p-mixed-capstone-protocol.yml").read_text(encoding="utf-8")
    for token in ("docker compose", "runner_shadow", "set_state_delay(", "replaymark_s2_admission_live"):
        if token in workflow:
            raise AssertionError(f"S2-P workflow contains runtime execution token: {token}")
    return {"experiment_runner_added": False, "source_calibration_executed": False, "shifted_target_executed": False, "result_files_added": 0}

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    report = {
        "schema": "replaymark.s2p-protocol-freeze-gate.v1",
        "verdict": "PASS",
        "protocol_sha256": sha256_bytes(PROTOCOL_PATH.read_bytes()),
        "git_boundary": verify_git_boundary(protocol),
        "protocol_boundary": verify_protocol_boundary(protocol),
        "policy_schedule": verify_policy_schedule(protocol),
        "no_result_bearing_increment": verify_no_result_bearing_increment(),
        "next_gate": "S2Q_SOURCE_ONLY_CALIBRATION_AND_DSTAR_SEAL",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
