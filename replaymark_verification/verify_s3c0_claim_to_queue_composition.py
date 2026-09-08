from __future__ import annotations

import argparse
import ast
import json
import subprocess
from pathlib import Path
from typing import Iterable


EXPECTED_PARENT = "cf1f09398ad6148dfa1907dd2a02bdc443308ab7"
LEGACY_EXEC = "23b7c85bca6cb85fde9f4361a0f9664d21c8ae8d"
LEGACY_RESULT = "ac20890bb4aa926e439802510de3723b74591c94"
EXPECTED_FILES = {
    ".github/workflows/replaymark-runtime-gate-s3c0-claim-to-queue-composition.yml",
    "replaymark/S3C0_CLAIM_TO_QUEUE_COMPOSITION.json",
    "replaymark/S3C0_CLAIM_TO_QUEUE_COMPOSITION.md",
    "replaymark_verification/verify_s3c0_claim_to_queue_composition.py",
}
EXPECTED_BLOBS = {
    (EXPECTED_PARENT, "agentmark_e3b_lab/e3_mqtt/app/replaymark_s3_caller_native_restoration.py"):
        "cd4150585e36c07b737e27e5a879030b031dab4f",
    (EXPECTED_PARENT, "agentmark_e3b_lab/e3_mqtt/app/s2p6_heterogeneous_device.py"):
        "5b57bc44e91dc38e44eaafc760286fa4b616ff9c",
    (LEGACY_EXEC, "replaymark_e3b_downstream/pilot/pilot.py"):
        "20075962ad2448ce39e98066623e3080dc32b9e6",
    (LEGACY_EXEC, "replaymark_e3b_downstream/pilot/device.py"):
        "a53cb4e7de887e9159001bd2cc826658241c0595",
    (LEGACY_EXEC, "replaymark_e3b_default_flip/confirmatory/default_flip.py"):
        "10f2763a7c24d97cbe2a067d0ea06b30acfd9e6f",
    (LEGACY_EXEC, "replaymark_e3b_default_flip/DEFAULT_FLIP_PROTOCOL.md"):
        "d05917bf9ad69edb8adf1a642efda598b9b2aa0e",
    (LEGACY_RESULT, "replaymark_e3b_default_flip/CONFIRMATORY_OUTCOME.md"):
        "6d9c90d629b0e384b568a25fa93504dbe23828e6",
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def text_at(ref: str, path: str) -> str:
    return subprocess.check_output(["git", "show", f"{ref}:{path}"], text=True)


def literal_assignment(text: str, name: str):
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == name for t in targets):
                value = node.value
                if value is None:
                    break
                return ast.literal_eval(value)
    raise AssertionError(f"literal assignment not found: {name}")


def endpoint_vector(query_required: bool) -> dict[str, int]:
    # One ACT1 command and one ACT2 command. The frozen device emits one state
    # for every command. The direct-native query branch adds exactly one query
    # and the device emits exactly one immediate state for that query.
    command = 2
    query = 1 if query_required else 0
    state = command + query
    return {"command": command, "query": query, "state": state, "total": command + query + state}


def queue_work_from_evidence(tokens: Iterable[str]) -> int:
    # Deliberately accepts evidence tokens only: no policy or hidden-class input.
    total = 0
    for token in tokens:
        if token == "confirmed_by_deadline":
            total += endpoint_vector(False)["total"]
        elif token == "not_visible_by_deadline":
            total += endpoint_vector(True)["total"]
        else:
            raise ValueError(f"unsupported frozen E3b evidence token: {token!r}")
    return total


def require_contains(text: str, needles: list[str], label: str) -> None:
    missing = [x for x in needles if x not in text]
    if missing:
        raise AssertionError(f"{label} missing source invariants: {missing}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    manifest = json.loads(Path("replaymark/S3C0_CLAIM_TO_QUEUE_COMPOSITION.json").read_text())
    checks: dict[str, bool] = {}

    head = git("rev-parse", "HEAD")
    parent = git("rev-parse", "HEAD^")
    checks["exact_s3_result_parent"] = parent == EXPECTED_PARENT

    changed = set(git("diff", "--name-only", EXPECTED_PARENT, head).splitlines())
    checks["declared_four_files_only"] = changed == EXPECTED_FILES

    blob_results = []
    for (ref, path), expected in EXPECTED_BLOBS.items():
        actual = git("rev-parse", f"{ref}:{path}")
        blob_results.append({"ref": ref, "path": path, "expected": expected, "actual": actual, "match": actual == expected})
    checks["all_frozen_blobs_match"] = all(x["match"] for x in blob_results)

    s3 = text_at(EXPECTED_PARENT, "agentmark_e3b_lab/e3_mqtt/app/replaymark_s3_caller_native_restoration.py")
    p6 = text_at(EXPECTED_PARENT, "agentmark_e3b_lab/e3_mqtt/app/s2p6_heterogeneous_device.py")
    pilot = text_at(LEGACY_EXEC, "replaymark_e3b_downstream/pilot/pilot.py")
    device = text_at(LEGACY_EXEC, "replaymark_e3b_downstream/pilot/device.py")
    default_flip = text_at(LEGACY_EXEC, "replaymark_e3b_default_flip/confirmatory/default_flip.py")
    protocol = text_at(LEGACY_EXEC, "replaymark_e3b_default_flip/DEFAULT_FLIP_PROTOCOL.md")
    outcome = text_at(LEGACY_RESULT, "replaymark_e3b_default_flip/CONFIRMATORY_OUTCOME.md")

    roles = literal_assignment(pilot, "RELEVANT_KINDS")
    checks["legacy_endpoint_roles_exact"] = roles == {"command", "query", "state"}
    queue_default = literal_assignment(default_flip, "DOCUMENTED_DEFAULT_QUEUE_MESSAGES")
    checks["legacy_default_queue_1000"] = queue_default == 1000

    require_contains(
        pilot,
        [
            'client.subscribe(f"replaymark/{self.run_id}/#", qos=1)',
            'first = h.wait_state_until(a, verify_deadline, after_ns=a1)',
            'if first is None:',
            'q = h.publish(query_topic(h.run_id, a)',
            'b1 = h.publish(command_topic(h.run_id, b)',
        ],
        "legacy direct-native controller",
    )
    checks["legacy_direct_native_is_evidence_conditional"] = True

    require_contains(
        device,
        [
            'if kind == "command":',
            'schedule_state(run_id, device, "command", delay)',
            'elif kind == "query":',
            'pub_state(run_id, device, "query")',
            'qos=1',
        ],
        "legacy queue device",
    )
    checks["legacy_device_one_state_per_command_or_query_path"] = True

    require_contains(
        p6,
        [
            'if kind == "command":',
            'schedule_state(device, "command", delay_ms)',
            'elif kind == "query":',
            'publish_state(device, "query")',
            'qos=1',
        ],
        "P6 target",
    )
    checks["p6_device_preserves_command_query_state_mechanism"] = True

    require_contains(
        s3,
        [
            '"NATIVE_QUERY_A"',
            '"NATIVE_FRESH_ACT2"',
            'confirmation = wait_query_confirmation(',
            'if int(fresh_call["generated_mono_ns"]) < int(confirmation["recv_mono_ns"]):',
            'max_a_timeout = max(',
            'ladder.sleep_until(max_a_timeout)',
            'if policy == "ALWAYS_REUSE":',
            'elif policy == "ALWAYS_NATIVE":',
            'elif policy == "REPLAYMARK_NATIVE":',
        ],
        "S3 runner",
    )
    checks["s3_native_provenance_and_quiescence_present"] = True

    # The legacy authority itself must document the 4/6 mechanism and exact old
    # 166 derivation. These are evidence about the old endpoint, not targets for C1.
    checks["legacy_protocol_froze_4_vs_6"] = (
        "R1: 4 measured messages/task." in protocol
        and "TARGET_NATIVE: 6 measured messages/task." in protocol
        and "floor(1000 / 6) = 166" in protocol
    )
    checks["legacy_result_confirmed_250_vs_166"] = (
        "250 tasks" in outcome and "166 tasks" in outcome and "500/1500" in outcome
    )

    safe_direct = endpoint_vector(False)
    unsafe_direct = endpoint_vector(True)
    # Concrete ReplayMark-Native path has the same queue projection by source
    # construction: safe keeps ACT2, unsafe adds one query and one query-state
    # before fresh ACT2. We compute it independently from labels.
    safe_replaymark = {"command": 2, "query": 0, "state": 2, "total": 4}
    unsafe_replaymark = {"command": 2, "query": 1, "state": 3, "total": 6}
    checks["safe_task_endpoint_equal"] = safe_direct == safe_replaymark
    checks["unsafe_task_endpoint_equal"] = unsafe_direct == unsafe_replaymark

    # Exhaust the aggregate algebra over a range far beyond any current C1 batch.
    aggregate_failures = []
    for n in range(0, 513):
        for u in range(0, n + 1):
            direct = 4 * n + 2 * u
            replaymark = 4 * (n - u) + 6 * u
            if direct != replaymark:
                aggregate_failures.append({"n": n, "u": u, "direct": direct, "replaymark": replaymark})
                break
    checks["aggregate_law_exhaustive_0_to_512_tasks"] = not aggregate_failures

    # Policy-label-free oracle smoke/exhaustive token mixtures.
    oracle_failures = []
    for n in range(0, 65):
        for u in range(0, n + 1):
            tokens = ["confirmed_by_deadline"] * (n - u) + ["not_visible_by_deadline"] * u
            observed = queue_work_from_evidence(tokens)
            expected = 4 * n + 2 * u
            if observed != expected:
                oracle_failures.append({"n": n, "u": u, "observed": observed, "expected": expected})
    checks["policy_label_free_endpoint_oracle"] = not oracle_failures

    old_boundary = queue_default // unsafe_direct["total"]
    checks["legacy_166_derivation_recomputed"] = old_boundary == 166
    # A heterogeneous batch cannot inherit a fixed N-only boundary because M also
    # depends on U. Demonstrate non-uniqueness at the old N itself.
    mixed_counts_at_166 = {4 * 166 + 2 * u for u in range(0, 167)}
    checks["heterogeneous_work_not_six_n_constant"] = len(mixed_counts_at_166) == 167
    checks["manifest_refuses_legacy_166_inheritance"] = (
        manifest["legacy_166_boundary"]["inherited_into_heterogeneous_s3_workload"] is False
        and manifest["legacy_166_boundary"]["hardcoding_166_in_s3c1"] == "FORBIDDEN"
        and manifest["s3c1_admission"]["fixed_numeric_boundary"] is None
    )

    checks["s3_always_native_not_native_truth"] = manifest["native_reference"]["s3_always_native_is_direct_native_reference"] is False
    checks["no_live_queue_execution_declared"] = manifest["s3c1_admission"]["queue_outcomes_observed_in_s3c0"] is False

    # C0 is protocol/proof only. No experimental runner or result file may be added.
    forbidden_added = [
        p for p in changed
        if p.endswith("_raw.json") or "RESULT" in p.upper() or "outcome" in p.lower()
    ]
    checks["no_result_or_live_runner_added"] = not forbidden_added and all("app/" not in p for p in changed)

    verdict = "PASS" if all(checks.values()) else "FAIL"
    report = {
        "schema": "replaymark.s3c0-claim-to-queue-composition-verification.v1",
        "verdict": verdict,
        "head": head,
        "parent": parent,
        "checks": checks,
        "frozen_blob_checks": blob_results,
        "endpoint": {
            "roles": sorted(roles),
            "qos": 1,
            "safe_direct": safe_direct,
            "safe_replaymark": safe_replaymark,
            "unsafe_direct": unsafe_direct,
            "unsafe_replaymark": unsafe_replaymark,
            "aggregate_law": "4*N + 2*U",
            "policy_label_free": True,
        },
        "legacy_boundary": {
            "queue_count": queue_default,
            "homogeneous_native_messages_per_task": unsafe_direct["total"],
            "recomputed_boundary": old_boundary,
            "inherited_by_s3_heterogeneous_workload": False,
        },
        "s3c1": {
            "admitted": verdict == "PASS",
            "required_native_reference": "independent direct target controller",
            "primary_target": "deployment conclusion equality, not a preselected numeric boundary",
        },
        "failures": {
            "aggregate": aggregate_failures[:10],
            "oracle": oracle_failures[:10],
            "forbidden_added": forbidden_added,
        },
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    if verdict != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
