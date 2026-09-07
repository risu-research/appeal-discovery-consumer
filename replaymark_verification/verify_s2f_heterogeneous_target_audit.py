import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RESULT_SEAL_HEAD = "60c444f32f98c9ee9ef42c8b06395ebf4ed9a902"
EXECUTION_HEAD = "e5e992b0a31c952017ee4209be2c0585a6cab500"
ARTIFACT_ID = 10034798750
ARTIFACT_RUN = 34168034341
ARTIFACT_SHA256 = "1319c41908d511ca9e8976973801350aab593199038b82752d8e4e7c78d0ecdb"
POLICY_SEED = "replaymark.s2.policy-assignment.v1|s1=c93c8574eb62cb4dcde94890fdfc8f939b41e00a"
CLASS_SEED = "replaymark.s2p6.target-class.v1|q3=ef370c38e6be82df340838be9db394559367c53e"
EXPECTED_INCREMENT = {
    ".github/workflows/replaymark-runtime-gate-s2f-heterogeneous-target-audit.yml",
    "replaymark/S2F_HETEROGENEOUS_TARGET_FALSIFICATION_AUDIT.json",
    "replaymark/S2F_HETEROGENEOUS_TARGET_FALSIFICATION_AUDIT.md",
    "replaymark_verification/verify_s2f_heterogeneous_target_audit.py",
}
PERMS = (
    ("ALWAYS_ADMIT", "ALWAYS_BLOCK", "REPLAYMARK"),
    ("ALWAYS_ADMIT", "REPLAYMARK", "ALWAYS_BLOCK"),
    ("ALWAYS_BLOCK", "ALWAYS_ADMIT", "REPLAYMARK"),
    ("ALWAYS_BLOCK", "REPLAYMARK", "ALWAYS_ADMIT"),
    ("REPLAYMARK", "ALWAYS_ADMIT", "ALWAYS_BLOCK"),
    ("REPLAYMARK", "ALWAYS_BLOCK", "ALWAYS_ADMIT"),
)
OBS_KEYS = {"schema", "clock_domain", "expected_device", "command_publish_mono_ns", "verify_deadline_mono_ns", "closed_at_mono_ns", "events"}
EVENT_KEYS = {"event_id", "device", "on", "recv_mono_ns", "clock_domain"}
ACTION_KEYS = {"schema", "capture_point", "clock_domain", "publish_mono_ns", "topic", "payload_utf8", "qos", "retain", "properties"}
POLICIES = ("ALWAYS_ADMIT", "ALWAYS_BLOCK", "REPLAYMARK")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ns(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("noncanonical monotonic timestamp")
    return value


def identity(device, role):
    if not isinstance(device, str) or not device or device != device.strip() or any(c in device for c in ("+", "#", "\x00")):
        raise ValueError("noncanonical device")
    try:
        prefix, task_text, actual_role = device.rsplit("-", 2)
    except ValueError as exc:
        raise ValueError("device lacks prefix-task-role") from exc
    if not prefix or actual_role != role or not task_text.isascii() or not task_text.isdigit():
        raise ValueError("device identity drift")
    task = int(task_text)
    if str(task) != task_text:
        raise ValueError("noncanonical task decimal")
    return prefix, task


def literal_safe(obs, action):
    if not isinstance(obs, dict) or set(obs) != OBS_KEYS or obs["schema"] != "replaymark.runtime.e3b-observation-record.v1":
        raise ValueError("observation schema drift")
    clock = obs["clock_domain"]
    if not isinstance(clock, str) or not clock:
        raise ValueError("clock-domain drift")
    prefix, task = identity(obs["expected_device"], "a")
    command, deadline, closed = map(ns, (obs["command_publish_mono_ns"], obs["verify_deadline_mono_ns"], obs["closed_at_mono_ns"]))
    if not command < deadline <= closed:
        raise ValueError("observation boundary ordering drift")
    if not isinstance(obs["events"], list):
        raise ValueError("events are not list")
    seen = set()
    matches = 0
    for event in obs["events"]:
        if not isinstance(event, dict) or set(event) != EVENT_KEYS:
            raise ValueError("event schema drift")
        eid = event["event_id"]
        if not isinstance(eid, str) or not eid or eid in seen:
            raise ValueError("event id invalid/duplicate")
        seen.add(eid)
        recv = ns(event["recv_mono_ns"])
        if event["clock_domain"] != clock or recv > closed or not isinstance(event["on"], bool):
            raise ValueError("event timing/type drift")
        if event["device"] == obs["expected_device"] and event["on"] is True and command <= recv <= deadline:
            matches += 1
    if matches > 1:
        raise ValueError("ambiguous multiple matching events")

    if not isinstance(action, dict) or set(action) != ACTION_KEYS or action["schema"] != "replaymark.runtime.e3b-historical-action-record.v1":
        raise ValueError("action schema drift")
    if action["capture_point"] != "paho.mqtt.Client.publish.pre-send" or action["clock_domain"] != clock:
        raise ValueError("action capture/clock drift")
    if ns(action["publish_mono_ns"]) < command:
        raise ValueError("stage-2 action predates stage-1 command")
    topic = action["topic"]
    if not isinstance(topic, str):
        raise ValueError("action topic type drift")
    parts = topic.split("/")
    if len(parts) != 3 or parts[0] != "agentmark" or parts[2] != "command":
        raise ValueError("action topic family drift")
    action_prefix, action_task = identity(parts[1], "b")
    if (action_prefix, action_task) != (prefix, task):
        raise ValueError("cross-task action")
    if action["payload_utf8"] != '{"on": true}' or action["qos"] != 1 or isinstance(action["qos"], bool) or action["retain"] is not False or action["properties"] is not None:
        raise ValueError("historical ACT2 bytes drift")
    return matches == 1, prefix, task


def policy_for(trial, task):
    block, offset = divmod(task, 3)
    digest = hashlib.sha256(f"{POLICY_SEED}|trial={trial}|block={block}".encode()).digest()
    return PERMS[int.from_bytes(digest[:8], "big") % 6][offset]


def reference_blocks(trial):
    ranked = sorted((hashlib.sha256(f"{CLASS_SEED}|trial={trial}|block={block}".encode()).hexdigest(), block) for block in range(64))
    return frozenset(block for _digest, block in ranked[:32])


def class_for(trial, task):
    return "REFERENCE" if task // 3 in reference_blocks(trial) else "SHIFTED"


def action_key(action):
    return (action["topic"], action["payload_utf8"], action["qos"], action["retain"], action["properties"])


def effect_count(row, prefix, task):
    action = row["raw_action"]
    after, deadline = ns(action["publish_mono_ns"]), ns(row["b_effect_deadline_mono_ns"])
    expected = f"{prefix}-{task}-b"
    effects = row.get("b_effects")
    if not isinstance(effects, list):
        raise ValueError("B effects missing")
    count = 0
    for event in effects:
        recv = event.get("recv_mono_ns") if isinstance(event, dict) else None
        if event.get("device") == expected and event.get("on") is True and event.get("cause") == "command" and isinstance(recv, int) and after <= recv <= deadline:
            count += 1
    return count


def preflight():
    if git("rev-parse", "HEAD^") != RESULT_SEAL_HEAD:
        raise AssertionError("S2-F must be exact child of P6 result seal")
    changed = set(git("diff", "--name-only", RESULT_SEAL_HEAD, "HEAD").splitlines())
    if changed != EXPECTED_INCREMENT:
        raise AssertionError(f"undeclared S2-F increment: missing={sorted(EXPECTED_INCREMENT-changed)} extra={sorted(changed-EXPECTED_INCREMENT)}")
    seal = json.loads((ROOT / "replaymark" / "S2P6_HETEROGENEOUS_TARGET_CAPSTONE_RESULT_SEAL.json").read_text())
    if seal.get("status") != "FROZEN_FIRST_COMPLETE_PASS" or seal["authority"]["execution_head"] != EXECUTION_HEAD:
        raise AssertionError("P6 result authority drift")
    if seal["artifact"]["id"] != ARTIFACT_ID or seal["artifact"]["sha256"] != ARTIFACT_SHA256:
        raise AssertionError("source artifact authority drift")

    source = Path(__file__).read_text()
    for forbidden in ("import replaymark", "from replaymark", "import agentmark", "from agentmark", "import paho", "from paho"):
        if forbidden in source:
            raise AssertionError(f"second literal auditor imports forbidden code: {forbidden}")
    workflow = (ROOT / ".github" / "workflows" / "replaymark-runtime-gate-s2f-heterogeneous-target-audit.yml").read_text()
    for token in ("docker compose", "s2p6_heterogeneous_device.py --broker", "replaymark_s2p6_heterogeneous_capstone.py --broker"):
        if token in workflow:
            raise AssertionError(f"S2-F re-executes target: {token}")
    for required in (str(ARTIFACT_ID), str(ARTIFACT_RUN), ARTIFACT_SHA256):
        if required not in workflow:
            raise AssertionError(f"workflow not pinned to source authority: {required}")
    return {"exact_result_seal_parent": True, "declared_files_only": True, "stdlib_only_literal_auditor": True, "new_live_execution": False, "source_artifact_pinned": True}


def audit(source_dir):
    raw_path = source_dir / "s2p6_live_raw.json"
    original_verify = source_dir / "p6_final_verification.json"
    seal_commit = source_dir / "SEAL_COMMIT.txt"
    for path in (raw_path, original_verify, seal_commit, source_dir / "SHA256SUMS"):
        if not path.is_file():
            raise AssertionError(f"artifact missing {path.name}")
    if EXECUTION_HEAD not in seal_commit.read_text():
        raise AssertionError("artifact commit binding drift")
    if json.loads(original_verify.read_text()).get("verdict") != "PASS":
        raise AssertionError("source artifact original verification is not PASS")

    raw_text = raw_path.read_text()
    if "REFERENCE" in raw_text or "SHIFTED" in raw_text or CLASS_SEED in raw_text:
        raise AssertionError("hidden target class leaked into live report")
    report = json.loads(raw_text)
    if report.get("schema") != "replaymark.s2p6-live-heterogeneous-target-capstone.v1" or report.get("broker") != "mosquitto version 2.1.2":
        raise AssertionError("live report identity drift")
    if (report.get("fallback"), report.get("regeneration"), report.get("automatic_retry")) != ("ABSENT", "ABSENT", "ABSENT"):
        raise AssertionError("fallback/regeneration/retry entered result")
    if report.get("independent_oracle_used_in_live_runner") is not False:
        raise AssertionError("live runner oracle leakage")

    calls = report.get("recording_client_calls")
    if not isinstance(calls, list):
        raise AssertionError("recording calls missing")
    calls_by_action = Counter((c.get("topic"), c.get("payload"), c.get("qos"), c.get("retain"), c.get("properties")) for c in calls)
    if any(n != 1 for n in calls_by_action.values()):
        raise AssertionError("duplicate exact application action")

    safe_count, unsafe_count, exec_count = Counter(), Counter(), Counter()
    class_truth = Counter()
    policy_class = defaultdict(Counter)
    assigned, safe_sets, exec_sets = defaultdict(set), defaultdict(set), defaultdict(set)
    trial_truth = defaultdict(Counter)
    ref_unsafe_replaymark = []
    semantic_mismatch, execution_mismatch, phase_failure, effect_failure, call_failure = [], [], [], [], []
    rows_seen = 0

    trials = report.get("trials")
    if not isinstance(trials, list) or len(trials) != 6:
        raise AssertionError("six trials required")
    for trial_index, trial in enumerate(trials):
        if trial.get("trial") != trial_index or not isinstance(trial.get("rows"), list) or len(trial["rows"]) != 192:
            raise AssertionError("trial structure drift")
        freeze, quiescence, dispatch_done, effects_done = map(ns, (trial["observation_freeze_complete_mono_ns"], trial["a_quiescence_barrier_mono_ns"], trial["dispatch_complete_mono_ns"], trial["b_effect_barrier_mono_ns"]))
        if not freeze <= quiescence <= dispatch_done <= effects_done:
            phase_failure.append((trial_index, "trial_order"))
        for task, row in enumerate(trial["rows"]):
            rows_seen += 1
            if row.get("trial") != trial_index or row.get("task_id") != task:
                raise AssertionError("row identity drift")
            policy = policy_for(trial_index, task)
            if row.get("policy") != policy:
                raise AssertionError("policy schedule drift")
            cls = class_for(trial_index, task)
            policy_class[(trial_index, policy)][cls] += 1
            safe, prefix, parsed_task = literal_safe(row["raw_observation"], row["raw_action"])
            if parsed_task != task:
                raise AssertionError("parsed task drift")
            key = (trial_index, task)
            assigned[policy].add(key)
            if safe:
                safe_count[policy] += 1; safe_sets[policy].add(key); class_truth[f"{cls}_safe"] += 1; trial_truth[trial_index]["safe"] += 1
            else:
                unsafe_count[policy] += 1; class_truth[f"{cls}_unsafe"] += 1; trial_truth[trial_index]["unsafe"] += 1
            if row.get("certificate_verdict") != ("VALID" if safe else "INVALID") or row.get("certificate_reuse_disposition") != ("REUSE" if safe else "DO_NOT_REUSE"):
                semantic_mismatch.append(key)

            exact = action_key(row["raw_action"])
            n_calls = calls_by_action.get(exact, 0)
            if n_calls not in (0, 1):
                call_failure.append((trial_index, task, n_calls))
            actual_exec = n_calls == 1
            if actual_exec:
                exec_count[policy] += 1; exec_sets[policy].add(key)
            if row.get("executed") is not actual_exec:
                execution_mismatch.append(key)
            if ns(row["raw_observation"]["closed_at_mono_ns"]) > freeze or ns(row["raw_action"]["publish_mono_ns"]) < quiescence:
                phase_failure.append((trial_index, task, "freeze_or_action_order"))
            if actual_exec:
                matching = [c for c in calls if (c.get("topic"), c.get("payload"), c.get("qos"), c.get("retain"), c.get("properties")) == exact]
                if len(matching) != 1 or ns(matching[0]["stamp_mono_ns"]) < quiescence:
                    phase_failure.append((trial_index, task, "sink_before_quiescence"))
            effects = effect_count(row, prefix, task)
            if (actual_exec and effects < 1) or ((not actual_exec) and effects != 0):
                effect_failure.append((trial_index, task, actual_exec, effects))
            if policy == "REPLAYMARK" and cls == "REFERENCE" and not safe:
                ref_unsafe_replaymark.append(key)

    for trial in range(6):
        if trial_truth[trial]["safe"] == 0 or trial_truth[trial]["unsafe"] == 0:
            raise AssertionError("trial not semantically mixed")
        for policy in POLICIES:
            if policy_class[(trial, policy)] != Counter({"REFERENCE": 32, "SHIFTED": 32}):
                raise AssertionError("policy/class orthogonality drift")

    checks = {
        "rows_1152": rows_seen == 1152,
        "recording_calls_match_report_count": len(calls) == report.get("recording_client_call_count"),
        "production_semantics_match_second_literal_auditor": not semantic_mismatch,
        "row_execution_matches_actual_sink": not execution_mismatch,
        "phase_order_exact": not phase_failure,
        "B_effects_exact": not effect_failure,
        "action_call_mismatches_zero": not call_failure,
        "always_admit_all": exec_sets["ALWAYS_ADMIT"] == assigned["ALWAYS_ADMIT"],
        "always_admit_unsafe_positive": bool(exec_sets["ALWAYS_ADMIT"] - safe_sets["ALWAYS_ADMIT"]),
        "always_block_empty": not exec_sets["ALWAYS_BLOCK"],
        "always_block_discards_safe_positive": bool(safe_sets["ALWAYS_BLOCK"]),
        "replaymark_exact_literal_safe_set": exec_sets["REPLAYMARK"] == safe_sets["REPLAYMARK"],
        "class_only_rule_falsified_on_replaymark_arm": len(ref_unsafe_replaymark) > 0,
        "replaymark_blocks_all_reference_but_unsafe": all(k not in exec_sets["REPLAYMARK"] for k in ref_unsafe_replaymark),
        "gate_consumed_384": report.get("replaymark_gate_consumed_count") == 384,
    }

    seal = json.loads((ROOT / "replaymark" / "S2P6_HETEROGENEOUS_TARGET_CAPSTONE_RESULT_SEAL.json").read_text())
    expected = seal["first_complete_result"]
    safe = {p: safe_count[p] for p in POLICIES}
    unsafe = {p: unsafe_count[p] for p in POLICIES}
    executed = {p: exec_count[p] for p in POLICIES}
    by_class = {"REFERENCE_safe": class_truth["REFERENCE_safe"], "REFERENCE_unsafe": class_truth["REFERENCE_unsafe"], "SHIFTED_safe": class_truth["SHIFTED_safe"], "SHIFTED_unsafe": class_truth["SHIFTED_unsafe"]}
    checks["sealed_safe_counts_reproduced"] = safe == expected["safe_by_policy"]
    checks["sealed_unsafe_counts_reproduced"] = unsafe == expected["unsafe_by_policy"]
    checks["sealed_executed_counts_reproduced"] = executed == expected["executed_by_policy"]
    checks["sealed_class_counts_reproduced"] = by_class == expected["oracle_by_hidden_target_class"]

    return {
        "schema": "replaymark.s2f-second-literal-falsification-audit.v1",
        "verdict": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "recomputed": {
            "safe_by_policy": safe,
            "unsafe_by_policy": unsafe,
            "executed_by_policy": executed,
            "oracle_by_hidden_target_class": by_class,
            "replaymark_reference_but_unsafe_tasks": [list(k) for k in ref_unsafe_replaymark],
            "class_only_reference_rule_unsafe_executions_on_replaymark_arm": len(ref_unsafe_replaymark),
        },
        "failures": {"semantic": semantic_mismatch, "execution": execution_mismatch, "phase": phase_failure, "effects": effect_failure, "calls": call_failure},
        "source": {"artifact_id": ARTIFACT_ID, "workflow_run": ARTIFACT_RUN, "artifact_zip_sha256": ARTIFACT_SHA256, "live_raw_sha256": sha256_file(raw_path)},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--source-dir")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    pre = preflight()
    if args.preflight_only:
        report = {"schema": "replaymark.s2f-audit-preflight.v1", "verdict": "PASS", "preflight": pre}
    else:
        if not args.source_dir:
            raise SystemExit("--source-dir required")
        report = audit(Path(args.source_dir)); report["preflight"] = pre
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    if report.get("verdict") != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
