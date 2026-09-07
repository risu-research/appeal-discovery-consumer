from __future__ import annotations

import ast
from collections import Counter
import hashlib
import itertools
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PARENT = "313d24099546eb672eeabb5d449a476b261087be"
EXPECTED_INCREMENT = {
    ".github/workflows/replaymark-runtime-gate-s3p-caller-native-restoration-protocol.yml",
    "replaymark/S3P_CALLER_OWNED_NATIVE_RESTORATION_PROTOCOL.json",
    "replaymark/S3P_CALLER_OWNED_NATIVE_RESTORATION_PROTOCOL.md",
    "replaymark_verification/verify_s3p_caller_native_restoration_protocol.py",
}
FROZEN_BLOBS = {
    "replaymark/execution_admission.py": "015b2cfb7f084562eaead2dedd2fae00628eaffa",
    "replaymark/runtime_e3b_action.py": "d5d483751eb06fd8b00f7bb2eff613a20f0f796c",
    "agentmark_e3b_lab/e3_mqtt/app/s2p6_heterogeneous_device.py": "5b57bc44e91dc38e44eaafc760286fa4b616ff9c",
    "replaymark/runtime_e3b_observation.py": "de6cdc8ccdbb9b189e238cc5dbad173060fe17ab",
    "replaymark/runtime_e3b_bridge.py": "5c2b13f35edcae9ce42fa062f51f1b6ce46747bf",
    "replaymark/runtime_e3b_execution_gate.py": "22748a5aa820e83e4700a339e8af297cdd9f9143",
    "replaymark/runtime_e3b_correlation.py": "bbdc243eccf29c0a26b92bc78c0acdb96222da8e",
    "agentmark_e3b_lab/e3_mqtt/app/ladder.py": "fcc1768544714f1b11a497a856f8e18d4d2f07dd",
}
P6_POLICY_SEED = "replaymark.s2.policy-assignment.v1|s1=c93c8574eb62cb4dcde94890fdfc8f939b41e00a"
P6_CLASS_SEED = "replaymark.s2p6.target-class.v1|q3=ef370c38e6be82df340838be9db394559367c53e"
P6_PERMS = (
    ("ALWAYS_ADMIT", "ALWAYS_BLOCK", "REPLAYMARK"),
    ("ALWAYS_ADMIT", "REPLAYMARK", "ALWAYS_BLOCK"),
    ("ALWAYS_BLOCK", "ALWAYS_ADMIT", "REPLAYMARK"),
    ("ALWAYS_BLOCK", "REPLAYMARK", "ALWAYS_ADMIT"),
    ("REPLAYMARK", "ALWAYS_ADMIT", "ALWAYS_BLOCK"),
    ("REPLAYMARK", "ALWAYS_BLOCK", "ALWAYS_ADMIT"),
)
RELABEL = {
    "ALWAYS_ADMIT": "ALWAYS_REUSE",
    "ALWAYS_BLOCK": "ALWAYS_NATIVE",
    "REPLAYMARK": "REPLAYMARK_NATIVE",
}
EXPECTED_SCHEDULE_SHA256 = "27503b245e2d978f1884f717248d32336602c3f1c8e22ee379ba4442fcbcc047"
POLICIES = tuple(RELABEL.values())


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def canonical_sha(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def p6_policy_for(trial: int, task_id: int) -> str:
    block, offset = divmod(task_id, 3)
    digest = hashlib.sha256(
        f"{P6_POLICY_SEED}|trial={trial}|block={block}".encode("utf-8")
    ).digest()
    return P6_PERMS[int.from_bytes(digest[:8], "big") % 6][offset]


def reference_blocks(trial: int) -> frozenset[int]:
    ranked = sorted(
        (
            hashlib.sha256(
                f"{P6_CLASS_SEED}|trial={trial}|block={block}".encode("utf-8")
            ).hexdigest(),
            block,
        )
        for block in range(64)
    )
    return frozenset(block for _digest, block in ranked[:32])


def schedule_record() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for trial in range(6):
        references = reference_blocks(trial)
        for block in range(64):
            target_class = "REFERENCE" if block in references else "SHIFTED"
            for offset in range(3):
                task_id = 3 * block + offset
                rows.append(
                    {
                        "trial": trial,
                        "task_id": task_id,
                        "block": block,
                        "policy": RELABEL[p6_policy_for(trial, task_id)],
                        "target_class": target_class,
                    }
                )
    return rows


def verify_target_query_path() -> None:
    path = ROOT / "agentmark_e3b_lab/e3_mqtt/app/s2p6_heterogeneous_device.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    on_message = functions.get("on_message")
    if on_message is None:
        raise AssertionError("frozen heterogeneous target lost on_message")

    query_direct = False
    query_scheduled = False
    command_scheduled = False
    for node in ast.walk(on_message):
        if not isinstance(node, ast.If):
            continue
        text = ast.unparse(node.test)
        branch = ast.unparse(ast.Module(body=node.body, type_ignores=[]))
        if "kind == 'query'" in text or 'kind == "query"' in text:
            query_direct = "publish_state(device, 'query')" in branch or 'publish_state(device, "query")' in branch
            query_scheduled = "schedule_state" in branch
        if "kind == 'command'" in text or 'kind == "command"' in text:
            command_scheduled = "schedule_state" in branch
    if not query_direct or query_scheduled or not command_scheduled:
        raise AssertionError(
            "frozen target no longer has direct query/current-state path distinct from delayed command path"
        )


def main() -> None:
    if git("rev-parse", "HEAD^") != PARENT:
        raise AssertionError("S3-P must be exact child of completed S2-F seal")
    changed = set(git("diff", "--name-only", PARENT, "HEAD").splitlines())
    if changed != EXPECTED_INCREMENT:
        raise AssertionError(
            f"undeclared S3-P increment: missing={sorted(EXPECTED_INCREMENT-changed)} "
            f"extra={sorted(changed-EXPECTED_INCREMENT)}"
        )

    blob_checks = {}
    for path, expected in FROZEN_BLOBS.items():
        actual = git("rev-parse", f"HEAD:{path}")
        if actual != expected:
            raise AssertionError(f"frozen blob drift {path}: {actual} != {expected}")
        blob_checks[path] = actual

    s2f = json.loads(
        (ROOT / "replaymark/S2F_HETEROGENEOUS_TARGET_FALSIFICATION_AUDIT_RESULT_SEAL.json").read_text(encoding="utf-8")
    )
    if s2f.get("status") != "FROZEN_COMPLETE_PASS" or s2f["s2_closure"]["status"] != "CLOSED_PASS":
        raise AssertionError("S2-F closure authority is not complete PASS")

    protocol = json.loads(
        (ROOT / "replaymark/S3P_CALLER_OWNED_NATIVE_RESTORATION_PROTOCOL.json").read_text(encoding="utf-8")
    )
    if protocol.get("status") != "FROZEN_BEFORE_S3_LIVE_EXECUTION":
        raise AssertionError("S3-P status drift")
    if protocol["q_lineage"]["status"] != "RETIRED_BY_EVIDENCE" or protocol["q_lineage"]["Q4"] != "not_admitted":
        raise AssertionError("retired Q lineage was reopened")
    if protocol["protocol"]["fallback_inside_replaymark"] or protocol["protocol"]["regeneration_inside_replaymark"]:
        raise AssertionError("S3-P moved fallback/regeneration inside ReplayMark")
    if protocol["target_assignment"]["inherit_exact_p6_class_schedule"] is not True:
        raise AssertionError("S3-P does not inherit exact P6 target schedule")
    if protocol["policy_assignment"]["relabel"] != RELABEL:
        raise AssertionError("S3-P policy relabel drift")

    rows = schedule_record()
    if len(rows) != 1152 or canonical_sha(rows) != EXPECTED_SCHEDULE_SHA256:
        raise AssertionError("S3 joint policy/target schedule digest drift")
    if protocol["policy_assignment"]["s3_joint_policy_target_schedule_sha256"] != EXPECTED_SCHEDULE_SHA256:
        raise AssertionError("protocol schedule digest does not match verifier")

    balance = Counter((row["trial"], row["policy"], row["target_class"]) for row in rows)
    for trial in range(6):
        for policy in POLICIES:
            if balance[(trial, policy, "REFERENCE")] != 32 or balance[(trial, policy, "SHIFTED")] != 32:
                raise AssertionError(f"S3 policy/class imbalance trial={trial} policy={policy}")

    for trial in range(6):
        for block in range(64):
            block_rows = [row for row in rows if row["trial"] == trial and row["block"] == block]
            if {row["policy"] for row in block_rows} != set(POLICIES):
                raise AssertionError(f"one-each policy invariant failed trial={trial} block={block}")
            if len({row["target_class"] for row in block_rows}) != 1:
                raise AssertionError(f"block target class split trial={trial} block={block}")

    verify_target_query_path()

    workflow = (
        ROOT / ".github/workflows/replaymark-runtime-gate-s3p-caller-native-restoration-protocol.yml"
    ).read_text(encoding="utf-8")
    forbidden_runtime_tokens = (
        "docker compose",
        "mosquitto",
        "s2p6_heterogeneous_device.py --broker",
        "replaymark_s3",
    )
    for token in forbidden_runtime_tokens:
        if token in workflow:
            raise AssertionError(f"protocol-freeze workflow executes S3 runtime: {token}")

    report = {
        "schema": "replaymark.s3p-protocol-freeze-verification.v1",
        "verdict": "PASS",
        "exact_parent": PARENT,
        "changed_files": sorted(changed),
        "frozen_blob_matches": blob_checks,
        "schedule": {
            "rows": len(rows),
            "sha256": canonical_sha(rows),
            "per_policy_per_trial_reference": 32,
            "per_policy_per_trial_shifted": 32,
            "new_randomization": False,
        },
        "boundaries": {
            "exact_p6_target_reused": True,
            "direct_native_query_path_present": True,
            "caller_owns_native_path": True,
            "fallback_inside_replaymark": False,
            "regeneration_inside_replaymark": False,
            "q4_admitted": False,
            "live_s3_execution": False,
        },
    }
    out = ROOT / "s3p_protocol_freeze_verification.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
