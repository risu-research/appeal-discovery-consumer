from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "replaymark" / "S2P6_ORTHOGONAL_HETEROGENEOUS_TARGET_CAPSTONE.json"
Q3_HEAD = "ef370c38e6be82df340838be9db394559367c53e"
EXPECTED_INCREMENT = {
    ".github/workflows/replaymark-runtime-gate-s2p6-heterogeneous-target-protocol.yml",
    "replaymark/S2P6_ORTHOGONAL_HETEROGENEOUS_TARGET_CAPSTONE.json",
    "replaymark/S2P6_ORTHOGONAL_HETEROGENEOUS_TARGET_CAPSTONE.md",
    "replaymark_verification/verify_s2p6_heterogeneous_target_protocol.py",
}
EXPECTED_POLICY_SHA = "ec91b78a6720ef9b4e83da12f9b8cf37c1d05028bb6ebaf0e4c6a274ff372d1e"
EXPECTED_CLASS_BLOCKS_SHA = "27c137dc2573a040596be5fbec3eedc4edad3e020e73d586660c1043880502e7"
EXPECTED_JOINT_SHA = "f94fafcf932baa74f37979485af1d1f494ecde7ad0491ad35d6536478496a750"
EXPECTED_TEMPLATE_SHA = "e86d5f42a09b8257185b6e3608ac83c0ac41deeba7890b914c22b0441a8b8888"

FROZEN_BLOBS = {
    "replaymark/runtime_e3b_observation.py": "de6cdc8ccdbb9b189e238cc5dbad173060fe17ab",
    "replaymark/runtime_e3b_action.py": "d5d483751eb06fd8b00f7bb2eff613a20f0f796c",
    "replaymark/runtime_e3b_correlation.py": "bbdc243eccf29c0a26b92bc78c0acdb96222da8e",
    "replaymark/runtime_e3b_execution_gate.py": "22748a5aa820e83e4700a339e8af297cdd9f9143",
    "replaymark_oracle/e3b_integrated_runtime_oracle.py": "9a9ebb86b7a82bdff3de6603235824fd0971e23b",
    "agentmark_e3b_lab/e3_mqtt/app/device.py": "27240e65cb8e1a7d788cc5dea8484cbad8ec6653",
    "agentmark_e3b_lab/e3_mqtt/app/ladder.py": "fcc1768544714f1b11a497a856f8e18d4d2f07dd",
}
POLICY_PERMS = [
    ["ALWAYS_ADMIT", "ALWAYS_BLOCK", "REPLAYMARK"],
    ["ALWAYS_ADMIT", "REPLAYMARK", "ALWAYS_BLOCK"],
    ["ALWAYS_BLOCK", "ALWAYS_ADMIT", "REPLAYMARK"],
    ["ALWAYS_BLOCK", "REPLAYMARK", "ALWAYS_ADMIT"],
    ["REPLAYMARK", "ALWAYS_ADMIT", "ALWAYS_BLOCK"],
    ["REPLAYMARK", "ALWAYS_BLOCK", "ALWAYS_ADMIT"],
]

def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")

def sha256_obj(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()

def verify_git_boundary(protocol: dict[str, object]) -> dict[str, object]:
    parent = git("rev-parse", "HEAD^")
    if parent != Q3_HEAD:
        raise AssertionError(f"P6 must be exact child of Q3 failure seal: {parent}")
    changed = set(git("diff", "--name-only", Q3_HEAD, "HEAD").splitlines())
    if changed != EXPECTED_INCREMENT:
        raise AssertionError(f"undeclared P6 increment: missing={sorted(EXPECTED_INCREMENT-changed)} extra={sorted(changed-EXPECTED_INCREMENT)}")
    matches = 0
    for path, expected in FROZEN_BLOBS.items():
        actual = git("rev-parse", f"HEAD:{path}")
        if actual != expected:
            raise AssertionError(f"frozen authority drift {path}: {actual} != {expected}")
        matches += 1
    q3 = json.loads((ROOT / "replaymark" / "S2Q3_BOUNDARY_COMPLETE_SOURCE_FAILURE_SEAL.json").read_text(encoding="utf-8"))
    if q3.get("status") != "FROZEN_COMPLETE_SCIENTIFIC_FAILURE":
        raise AssertionError("Q3 failure is not preserved")
    if protocol["authorities"]["q3_failure_seal_head"] != Q3_HEAD:
        raise AssertionError("P6 does not bind exact Q3 failure authority")
    return {"exact_q3_parent": True, "declared_files_only": True, "frozen_blob_matches": matches, "q3_failure_preserved": True}

def regenerate(protocol: dict[str, object]) -> dict[str, object]:
    pa = protocol["policy_assignment"]
    ta = protocol["target_configuration"]["class_assignment"]
    if pa["permutation_order"] != POLICY_PERMS:
        raise AssertionError("policy permutation table drift")
    policy_seed = pa["seed"]
    class_seed = ta["seed"]
    policy_rows = []
    joint_rows = []
    reference_blocks = {}
    balance = defaultdict(Counter)
    for trial in range(6):
        ranked = sorted((hashlib.sha256(f"{class_seed}|trial={trial}|block={block}".encode()).hexdigest(), block) for block in range(64))
        refs = {block for _, block in ranked[:32]}
        reference_blocks[str(trial)] = sorted(refs)
        for block in range(64):
            selector = int.from_bytes(hashlib.sha256(f"{policy_seed}|trial={trial}|block={block}".encode()).digest()[:8], "big") % 6
            permutation = POLICY_PERMS[selector]
            cls = "REFERENCE" if block in refs else "SHIFTED"
            for offset, policy in enumerate(permutation):
                task_id = 3 * block + offset
                policy_rows.append({"trial": trial, "task_id": task_id, "policy": policy})
                joint_rows.append({"trial": trial, "block": block, "task_id": task_id, "policy": policy, "target_class": cls})
                balance[(trial, policy)][cls] += 1
    if sha256_obj(policy_rows) != EXPECTED_POLICY_SHA:
        raise AssertionError("inherited policy schedule digest drift")
    if sha256_obj(reference_blocks) != EXPECTED_CLASS_BLOCKS_SHA:
        raise AssertionError("target-class block-map digest drift")
    if sha256_obj(joint_rows) != EXPECTED_JOINT_SHA:
        raise AssertionError("joint schedule digest drift")
    if reference_blocks != ta["reference_blocks_by_trial"]:
        raise AssertionError("materialized target-class schedule drift")
    for trial in range(6):
        for policy in ("ALWAYS_ADMIT", "ALWAYS_BLOCK", "REPLAYMARK"):
            if balance[(trial, policy)] != Counter({"REFERENCE": 32, "SHIFTED": 32}):
                raise AssertionError(f"orthogonality failure trial={trial} policy={policy}")
    return {"policy_rows": len(policy_rows), "joint_rows": len(joint_rows), "policy_schedule_sha256": EXPECTED_POLICY_SHA, "class_blocks_sha256": EXPECTED_CLASS_BLOCKS_SHA, "joint_schedule_sha256": EXPECTED_JOINT_SHA, "per_policy_per_trial_reference": 32, "per_policy_per_trial_shifted": 32, "exact_orthogonality": True}

def verify_protocol(protocol: dict[str, object]) -> dict[str, object]:
    if protocol.get("schema") != "replaymark.s2p6-orthogonal-heterogeneous-target-capstone-protocol.v1":
        raise AssertionError("foreign P6 protocol schema")
    if protocol.get("status") != "FROZEN_BEFORE_ANY_HETEROGENEOUS_TARGET_EXECUTION":
        raise AssertionError("P6 was not frozen prospectively")
    if any(protocol["p6_boundary"].values()):
        raise AssertionError("P6 protocol boundary unexpectedly enables runtime surface")
    target = protocol["target_configuration"]
    if target["kind"] != "ONE_IMMUTABLE_HETEROGENEOUS_E3B_TARGET" or target["verify_ms"] != 100.0:
        raise AssertionError("target/evidence boundary drift")
    if target["class_behavior"] != {"REFERENCE": {"state_delay_ms": 0}, "SHIFTED": {"state_delay_ms": 180}}:
        raise AssertionError("frozen class behavior drift")
    impl = target["target_implementation_contract"]
    for name in ("additive_lab_only_target", "frozen_device_py_unchanged", "same_command_query_state_wire_semantics_as_frozen_device", "no_agentmark_control_mutation_during_run", "no_policy_input", "no_certificate_input", "no_oracle_input", "no_target_class_label_on_state_wire", "no_runtime_adaptation"):
        if impl[name] is not True:
            raise AssertionError(f"target implementation contract weakened: {name}")
    if any(protocol["anti_leakage"].values()):
        raise AssertionError("anti-leakage invariant weakened")
    hist = protocol["historical_decision"]
    if sha256_obj(hist["template"]) != EXPECTED_TEMPLATE_SHA or hist["template_sha256"] != EXPECTED_TEMPLATE_SHA:
        raise AssertionError("historical ACT2 template drift")
    if hist["caller_action_override"] is not False:
        raise AssertionError("caller action substitution reopened")
    replaymark = protocol["promotion_criteria"]["REPLAYMARK"]
    if replaymark != {"executed_set_equals_independent_oracle_safe_set": True, "unsafe_execution_count": 0, "unnecessary_block_count": 0}:
        raise AssertionError("ReplayMark exact-set promotion rule drift")
    if protocol["fallback"] != "ABSENT" or protocol["regeneration"] != "ABSENT" or protocol["automatic_retry"] != "ABSENT":
        raise AssertionError("fallback/regeneration/retry entered P6")
    return {"prospective_freeze": True, "target_executed": False, "source_calibration": "ABSENT", "D_star": "ABSENT", "evidence_boundary_ms": 100.0, "historical_template_sha256": EXPECTED_TEMPLATE_SHA}

def verify_no_runtime_workflow() -> dict[str, object]:
    workflow = (ROOT / ".github" / "workflows" / "replaymark-runtime-gate-s2p6-heterogeneous-target-protocol.yml").read_text(encoding="utf-8")
    for token in ("docker compose", "mosquitto", "device_heterogeneous", "runner_shadow", "set_state_delay", "replaymark_s2p6_live"):
        if token in workflow:
            raise AssertionError(f"P6 protocol workflow contains runtime token: {token}")
    return {"experiment_runner_added": False, "target_implementation_added": False, "heterogeneous_target_executed": False, "target_outcomes_visible": False}

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    report = {"schema": "replaymark.s2p6-protocol-freeze-gate.v1", "verdict": "PASS", "protocol_sha256": hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(), "git_boundary": verify_git_boundary(protocol), "protocol_boundary": verify_protocol(protocol), "orthogonal_schedule": regenerate(protocol), "no_runtime_increment": verify_no_runtime_workflow(), "next_gate": "S2E_P6_FIRST_COMPLETE_HETEROGENEOUS_TARGET_CAPSTONE"}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
