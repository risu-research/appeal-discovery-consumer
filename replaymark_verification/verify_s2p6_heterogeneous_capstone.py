from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import subprocess

from replaymark_oracle.e3b_integrated_runtime_oracle import integrated_expectation

ROOT = Path(__file__).resolve().parents[1]
P6_HEAD = "4a458f2f5cc9163c6046cc6d20b3626cecfc4a81"
PROTOCOL = ROOT / "replaymark" / "S2P6_ORTHOGONAL_HETEROGENEOUS_TARGET_CAPSTONE.json"
TARGET = ROOT / "agentmark_e3b_lab" / "e3_mqtt" / "app" / "s2p6_heterogeneous_device.py"
RUNNER = ROOT / "agentmark_e3b_lab" / "e3_mqtt" / "app" / "replaymark_s2p6_heterogeneous_capstone.py"
WORKFLOW = ROOT / ".github" / "workflows" / "replaymark-runtime-gate-s2p6-heterogeneous-target-execution.yml"

EXPECTED_INCREMENT = {
    ".github/workflows/replaymark-runtime-gate-s2p6-heterogeneous-target-execution.yml",
    "agentmark_e3b_lab/e3_mqtt/app/s2p6_heterogeneous_device.py",
    "agentmark_e3b_lab/e3_mqtt/app/replaymark_s2p6_heterogeneous_capstone.py",
    "replaymark/S2P6_HETEROGENEOUS_TARGET_CAPSTONE_EXECUTION.md",
    "replaymark_verification/verify_s2p6_heterogeneous_capstone.py",
}
FROZEN_BLOBS = {
    "agentmark_e3b_lab/e3_mqtt/app/device.py": "27240e65cb8e1a7d788cc5dea8484cbad8ec6653",
    "agentmark_e3b_lab/e3_mqtt/app/experiment.py": "a5c7483b198bc03f251d31b75750c27fad1f2d29",
    "agentmark_e3b_lab/e3_mqtt/app/ladder.py": "fcc1768544714f1b11a497a856f8e18d4d2f07dd",
    "replaymark/runtime_e3b_observation.py": "de6cdc8ccdbb9b189e238cc5dbad173060fe17ab",
    "replaymark/runtime_e3b_action.py": "d5d483751eb06fd8b00f7bb2eff613a20f0f796c",
    "replaymark/runtime_e3b_correlation.py": "bbdc243eccf29c0a26b92bc78c0acdb96222da8e",
    "replaymark/runtime_e3b_execution_gate.py": "22748a5aa820e83e4700a339e8af297cdd9f9143",
    "replaymark_oracle/e3b_integrated_runtime_oracle.py": "9a9ebb86b7a82bdff3de6603235824fd0971e23b",
}
POLICY_PERMS = (
    ("ALWAYS_ADMIT", "ALWAYS_BLOCK", "REPLAYMARK"),
    ("ALWAYS_ADMIT", "REPLAYMARK", "ALWAYS_BLOCK"),
    ("ALWAYS_BLOCK", "ALWAYS_ADMIT", "REPLAYMARK"),
    ("ALWAYS_BLOCK", "REPLAYMARK", "ALWAYS_ADMIT"),
    ("REPLAYMARK", "ALWAYS_ADMIT", "ALWAYS_BLOCK"),
    ("REPLAYMARK", "ALWAYS_BLOCK", "ALWAYS_ADMIT"),
)
POLICY_SEED = "replaymark.s2.policy-assignment.v1|s1=c93c8574eb62cb4dcde94890fdfc8f939b41e00a"
CLASS_SEED = "replaymark.s2p6.target-class.v1|q3=ef370c38e6be82df340838be9db394559367c53e"
HISTORICAL_TEMPLATE_SHA256 = "e86d5f42a09b8257185b6e3608ac83c0ac41deeba7890b914c22b0441a8b8888"

def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

def policy_for(trial: int, task_id: int) -> str:
    block = task_id // 3
    offset = task_id % 3
    digest = hashlib.sha256(
        f"{POLICY_SEED}|trial={trial}|block={block}".encode("utf-8")
    ).digest()
    return POLICY_PERMS[int.from_bytes(digest[:8], "big") % 6][offset]

def reference_blocks(trial: int) -> frozenset[int]:
    ranked = sorted(
        (
            hashlib.sha256(
                f"{CLASS_SEED}|trial={trial}|block={block}".encode("utf-8")
            ).hexdigest(),
            block,
        )
        for block in range(64)
    )
    return frozenset(block for _digest, block in ranked[:32])

def target_class_for(trial: int, task_id: int) -> str:
    return "REFERENCE" if task_id // 3 in reference_blocks(trial) else "SHIFTED"

def preflight() -> dict[str, object]:
    if git("rev-parse", "HEAD^") != P6_HEAD:
        raise AssertionError("P6 execution must be exact child of frozen P6 protocol")
    changed = set(git("diff", "--name-only", P6_HEAD, "HEAD").splitlines())
    if changed != EXPECTED_INCREMENT:
        raise AssertionError(
            f"undeclared P6 execution increment: missing={sorted(EXPECTED_INCREMENT-changed)} "
            f"extra={sorted(changed-EXPECTED_INCREMENT)}"
        )
    frozen_matches = 0
    for path, expected in FROZEN_BLOBS.items():
        actual = git("rev-parse", f"HEAD:{path}")
        if actual != expected:
            raise AssertionError(f"frozen blob drift {path}: {actual} != {expected}")
        frozen_matches += 1

    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    if protocol["status"] != "FROZEN_BEFORE_ANY_HETEROGENEOUS_TARGET_EXECUTION":
        raise AssertionError("P6 protocol authority drift")
    target_source = TARGET.read_text(encoding="utf-8")
    runner_source = RUNNER.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")

    for forbidden in ("from replaymark", "import replaymark", "replaymark_oracle", "ALWAYS_ADMIT", "ALWAYS_BLOCK", "REPLAYMARK", "agentmark/control"):
        if forbidden in target_source:
            raise AssertionError(f"target receives forbidden policy/semantic surface: {forbidden}")
    if CLASS_SEED not in target_source or "REFERENCE_DELAY_MS = 0" not in target_source or "SHIFTED_DELAY_MS = 180" not in target_source:
        raise AssertionError("target class schedule/delay drift")
    for forbidden in (CLASS_SEED, '"REFERENCE"', '"SHIFTED"', "target_class", "replaymark_oracle", "set_state_delay", "agentmark/control"):
        if forbidden in runner_source:
            raise AssertionError(f"live runner contains hidden target/oracle surface: {forbidden}")
    if POLICY_SEED not in runner_source or HISTORICAL_TEMPLATE_SHA256 not in runner_source:
        raise AssertionError("runner policy/historical authority drift")

    if workflow.count("docker compose up -d mosquitto") != 1:
        raise AssertionError("workflow must start exactly one broker")
    if "docker compose up -d mosquitto device" in workflow or "docker compose up -d device" in workflow:
        raise AssertionError("original mutable-delay device must not run")
    if workflow.count("--name replaymark-s2p6-target") != 1:
        raise AssertionError("workflow must install one immutable heterogeneous target")
    if workflow.count("replaymark_s2p6_heterogeneous_capstone.py") != 3:
        raise AssertionError("capstone runner invocation/static/seal count drift")
    if "S2P6_TARGET_PROBE" in workflow:
        raise AssertionError("pre-capstone target probe is forbidden")
    stop_pos = workflow.find("docker rm -f replaymark-s2p6-target")
    eval_pos = workflow.find("verify_s2p6_heterogeneous_capstone.py --input")
    if stop_pos < 0 or eval_pos < 0 or stop_pos > eval_pos:
        raise AssertionError("target must be stopped before independent evaluation")
    return {
        "exact_p6_parent": True,
        "declared_files_only": True,
        "frozen_blob_matches": frozen_matches,
        "live_runner_target_class_blind": True,
        "live_runner_oracle_blind": True,
        "single_immutable_target_process": True,
        "original_device_not_started": True,
    }

def matching_effects(row: dict[str, object]) -> list[dict[str, object]]:
    action = row["raw_action"]
    task_id = int(row["task_id"])
    prefix = str(row["raw_observation"]["expected_device"]).rsplit("-", 2)[0]
    expected_device = f"{prefix}-{task_id}-b"
    after_ns = int(action["publish_mono_ns"])
    deadline_ns = int(row["b_effect_deadline_mono_ns"])
    out = []
    for event in row["b_effects"]:
        if (
            event.get("device") == expected_device
            and event.get("on") is True
            and event.get("cause") == "command"
            and isinstance(event.get("recv_mono_ns"), int)
            and after_ns <= int(event["recv_mono_ns"]) <= deadline_ns
        ):
            out.append(event)
    return out

def evaluate(report: dict[str, object]) -> dict[str, object]:
    checks: dict[str, bool] = {}
    checks["schema"] = report.get("schema") == "replaymark.s2p6-live-heterogeneous-target-capstone.v1"
    checks["broker"] = report.get("broker") == "mosquitto version 2.1.2"
    checks["historical_template"] = report.get("historical_template_sha256") == HISTORICAL_TEMPLATE_SHA256
    checks["no_live_oracle"] = report.get("independent_oracle_used_in_live_runner") is False
    checks["harness_closed"] = report.get("harness_closed_before_report") is True
    checks["no_fallback"] = (
        report.get("fallback") == "ABSENT"
        and report.get("regeneration") == "ABSENT"
        and report.get("automatic_retry") == "ABSENT"
    )

    trials = report.get("trials")
    if not isinstance(trials, list) or len(trials) != 6:
        raise AssertionError("P6 live report must contain six trials")

    rows_all: list[dict[str, object]] = []
    prefixes: set[str] = set()
    per_policy_safe: defaultdict[str, set[tuple[int, int]]] = defaultdict(set)
    per_policy_executed: defaultdict[str, set[tuple[int, int]]] = defaultdict(set)
    per_policy_assigned: defaultdict[str, set[tuple[int, int]]] = defaultdict(set)
    per_policy_unsafe: defaultdict[str, set[tuple[int, int]]] = defaultdict(set)
    class_oracle = Counter()
    per_trial_oracle = defaultdict(Counter)
    per_trial_policy_class = defaultdict(Counter)
    effect_failures: list[tuple[int, int, str]] = []
    cert_mismatches: list[tuple[int, int]] = []
    schedule_mismatches: list[tuple[int, int]] = []
    leakage_rows: list[tuple[int, int]] = []

    for trial_index, trial in enumerate(trials):
        if trial.get("trial") != trial_index:
            raise AssertionError("trial index drift")
        prefix = trial.get("prefix")
        if not isinstance(prefix, str) or not prefix.startswith(f"s2p6-t{trial_index}-"):
            raise AssertionError("trial prefix drift")
        if prefix in prefixes:
            raise AssertionError("trial namespace reused")
        prefixes.add(prefix)
        if not (
            int(trial["observation_freeze_complete_mono_ns"])
            <= int(trial["a_quiescence_barrier_mono_ns"])
            <= int(trial["dispatch_complete_mono_ns"])
            <= int(trial["b_effect_barrier_mono_ns"])
        ):
            raise AssertionError("trial phase ordering drift")
        rows = trial.get("rows")
        if not isinstance(rows, list) or len(rows) != 192:
            raise AssertionError("trial row count drift")

        for task_id, row in enumerate(rows):
            if row.get("trial") != trial_index or row.get("task_id") != task_id:
                raise AssertionError("task identity drift")
            expected_policy = policy_for(trial_index, task_id)
            if row.get("policy") != expected_policy:
                schedule_mismatches.append((trial_index, task_id))
            cls = target_class_for(trial_index, task_id)
            per_trial_policy_class[(trial_index, expected_policy)][cls] += 1

            raw_obs = row["raw_observation"]
            raw_action = row["raw_action"]
            raw_text = json.dumps({"observation": raw_obs, "action": raw_action}, sort_keys=True)
            if "REFERENCE" in raw_text or "SHIFTED" in raw_text or "target_class" in raw_text:
                leakage_rows.append((trial_index, task_id))

            if int(raw_action["publish_mono_ns"]) < int(trial["a_quiescence_barrier_mono_ns"]):
                raise AssertionError("ACT2 candidate exists before A-side quiescence barrier")
            if int(raw_obs["closed_at_mono_ns"]) > int(trial["observation_freeze_complete_mono_ns"]):
                raise AssertionError("observation snapshot was not frozen before freeze barrier")

            oracle = integrated_expectation(raw_obs, raw_action)
            oracle_safe = oracle.verdict == "VALID" and oracle.reuse_disposition == "REUSE"
            key = (trial_index, task_id)
            per_policy_assigned[expected_policy].add(key)
            if oracle_safe:
                per_policy_safe[expected_policy].add(key)
                per_trial_oracle[trial_index]["safe"] += 1
                class_oracle[f"{cls}_safe"] += 1
            else:
                per_policy_unsafe[expected_policy].add(key)
                per_trial_oracle[trial_index]["unsafe"] += 1
                class_oracle[f"{cls}_unsafe"] += 1

            if (
                row.get("certificate_verdict") != oracle.verdict
                or row.get("certificate_reuse_disposition") != oracle.reuse_disposition
            ):
                cert_mismatches.append((trial_index, task_id))

            executed = row.get("executed") is True
            if executed:
                per_policy_executed[expected_policy].add(key)
            expected_delegate = 1 if executed else 0
            if row.get("delegate_delta") != expected_delegate:
                raise AssertionError("delegate delta disagrees with executed flag")

            receipt = row.get("receipt")
            if expected_policy == "ALWAYS_ADMIT":
                if not executed or receipt is not None or row.get("execution_disposition") != "BASELINE_ADMIT":
                    raise AssertionError("Always-Admit semantics drift")
            elif expected_policy == "ALWAYS_BLOCK":
                if executed or receipt is not None or row.get("execution_disposition") != "BASELINE_BLOCK":
                    raise AssertionError("Always-Block semantics drift")
            else:
                if not isinstance(receipt, dict):
                    raise AssertionError("ReplayMark row lacks S1 execution receipt")
                expected_exec = oracle_safe
                if executed != expected_exec:
                    raise AssertionError("ReplayMark execution differs from independent oracle")
                if receipt.get("execution_disposition") != ("ADMIT_REUSE" if expected_exec else "BLOCK_REUSE"):
                    raise AssertionError("ReplayMark receipt disposition drift")
                if receipt.get("application_publish_invocations") != (1 if expected_exec else 0):
                    raise AssertionError("ReplayMark receipt publish-count drift")

            effects = matching_effects(row)
            if executed and not effects:
                effect_failures.append((trial_index, task_id, "executed_without_B_effect"))
            if not executed and effects:
                effect_failures.append((trial_index, task_id, "blocked_with_B_effect"))
            rows_all.append(row)

    checks["all_rows"] = len(rows_all) == 1152
    checks["fresh_prefixes"] = len(prefixes) == 6
    checks["policy_schedule_exact"] = not schedule_mismatches
    checks["no_target_class_leakage"] = not leakage_rows
    checks["certificate_matches_oracle"] = not cert_mismatches
    checks["effects_exact"] = not effect_failures

    for trial in range(6):
        checks[f"trial_{trial}_mixed"] = (
            per_trial_oracle[trial]["safe"] > 0 and per_trial_oracle[trial]["unsafe"] > 0
        )
        for policy in ("ALWAYS_ADMIT", "ALWAYS_BLOCK", "REPLAYMARK"):
            checks[f"trial_{trial}_{policy}_orthogonal"] = (
                per_trial_policy_class[(trial, policy)] == Counter({"REFERENCE": 32, "SHIFTED": 32})
            )

    for policy in ("ALWAYS_ADMIT", "ALWAYS_BLOCK", "REPLAYMARK"):
        checks[f"{policy}_assigned_384"] = len(per_policy_assigned[policy]) == 384
        checks[f"{policy}_safe_floor"] = len(per_policy_safe[policy]) >= 64
        checks[f"{policy}_unsafe_floor"] = len(per_policy_unsafe[policy]) >= 64

    checks["always_admit_all"] = per_policy_executed["ALWAYS_ADMIT"] == per_policy_assigned["ALWAYS_ADMIT"]
    checks["always_admit_unsafe_positive"] = bool(per_policy_executed["ALWAYS_ADMIT"] & per_policy_unsafe["ALWAYS_ADMIT"])
    checks["always_block_empty"] = not per_policy_executed["ALWAYS_BLOCK"]
    checks["always_block_unnecessary_positive"] = bool(per_policy_safe["ALWAYS_BLOCK"])
    checks["replaymark_exact_safe_set"] = per_policy_executed["REPLAYMARK"] == per_policy_safe["REPLAYMARK"]
    checks["replaymark_unsafe_zero"] = not (per_policy_executed["REPLAYMARK"] & per_policy_unsafe["REPLAYMARK"])
    checks["replaymark_unnecessary_block_zero"] = not (per_policy_safe["REPLAYMARK"] - per_policy_executed["REPLAYMARK"])
    checks["shifted_unsafe_positive"] = class_oracle["SHIFTED_unsafe"] > 0
    checks["reference_safe_positive"] = class_oracle["REFERENCE_safe"] > 0

    calls = report.get("recording_client_calls")
    if not isinstance(calls, list):
        raise AssertionError("recording client calls missing")
    executed_rows = [row for row in rows_all if row.get("executed") is True]
    checks["recording_call_count"] = len(calls) == len(executed_rows) == report.get("recording_client_call_count")
    expected_topics = Counter(
        (
            row["raw_action"]["topic"],
            row["raw_action"]["payload_utf8"],
            row["raw_action"]["qos"],
            row["raw_action"]["retain"],
            row["raw_action"]["properties"],
        )
        for row in executed_rows
    )
    actual_topics = Counter(
        (call.get("topic"), call.get("payload"), call.get("qos"), call.get("retain"), call.get("properties"))
        for call in calls
    )
    checks["recording_calls_match_exact_actions"] = actual_topics == expected_topics
    checks["gate_consumed_384"] = report.get("replaymark_gate_consumed_count") == 384

    verdict = "PASS" if all(checks.values()) else "FAIL"
    return {
        "schema": "replaymark.s2p6-heterogeneous-target-capstone-verification.v1",
        "verdict": verdict,
        "checks": checks,
        "counts": {
            "rows": len(rows_all),
            "recording_calls": len(calls),
            "oracle_by_class": dict(class_oracle),
            "safe_by_policy": {policy: len(per_policy_safe[policy]) for policy in ("ALWAYS_ADMIT", "ALWAYS_BLOCK", "REPLAYMARK")},
            "unsafe_by_policy": {policy: len(per_policy_unsafe[policy]) for policy in ("ALWAYS_ADMIT", "ALWAYS_BLOCK", "REPLAYMARK")},
            "executed_by_policy": {policy: len(per_policy_executed[policy]) for policy in ("ALWAYS_ADMIT", "ALWAYS_BLOCK", "REPLAYMARK")},
        },
        "failures": {
            "schedule_mismatches": schedule_mismatches,
            "certificate_mismatches": cert_mismatches,
            "effect_failures": effect_failures,
            "leakage_rows": leakage_rows,
        },
        "claims_not_made": [
            "hidden target class equals semantic truth task-by-task",
            "cross-process exactly-once",
            "broker-delivery exactly-once",
            "fallback quality",
            "regeneration quality",
            "latency speedup",
        ],
    }

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--input")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    pre = preflight()
    if args.preflight_only:
        report = {
            "schema": "replaymark.s2p6-execution-preflight.v1",
            "verdict": "PASS",
            "preflight": pre,
        }
    else:
        if not args.input:
            raise SystemExit("--input is required unless --preflight-only")
        live = json.loads(Path(args.input).read_text(encoding="utf-8"))
        report = evaluate(live)
        report["preflight"] = pre

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
