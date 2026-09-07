import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PARENT = "75d5d4379fdda221c0b9661f799d7779d6bba9f2"
EXPECTED_INCREMENT = {
    ".github/workflows/replaymark-runtime-gate-s3-caller-native-restoration-execution.yml",
    "agentmark_e3b_lab/e3_mqtt/app/replaymark_s3_caller_native_restoration.py",
    "replaymark/S3_CALLER_OWNED_NATIVE_RESTORATION_EXECUTION.md",
    "replaymark_verification/verify_s3_caller_native_restoration.py",
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
POLICY_SEED = "replaymark.s2.policy-assignment.v1|s1=c93c8574eb62cb4dcde94890fdfc8f939b41e00a"
CLASS_SEED = "replaymark.s2p6.target-class.v1|q3=ef370c38e6be82df340838be9db394559367c53e"
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
POLICIES = tuple(RELABEL.values())
HISTORICAL_TEMPLATE_SHA256 = "e86d5f42a09b8257185b6e3608ac83c0ac41deeba7890b914c22b0441a8b8888"
OBS_KEYS = {"schema", "clock_domain", "expected_device", "command_publish_mono_ns", "verify_deadline_mono_ns", "closed_at_mono_ns", "events"}
EVENT_KEYS = {"event_id", "device", "on", "recv_mono_ns", "clock_domain"}
ACTION_KEYS = {"schema", "capture_point", "clock_domain", "publish_mono_ns", "topic", "payload_utf8", "qos", "retain", "properties"}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def ns(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("noncanonical monotonic timestamp")
    return value


def identity(device, role):
    if not isinstance(device, str) or not device or device != device.strip() or any(c in device for c in ("+", "#", "\x00")):
        raise ValueError("noncanonical device")
    prefix, task_text, actual_role = device.rsplit("-", 2)
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
    prefix, task = identity(obs["expected_device"], "a")
    command, deadline, closed = map(ns, (obs["command_publish_mono_ns"], obs["verify_deadline_mono_ns"], obs["closed_at_mono_ns"]))
    if not command < deadline <= closed:
        raise ValueError("observation boundary ordering drift")
    if not isinstance(obs["events"], list):
        raise ValueError("events not list")
    seen, matches = set(), 0
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
        raise ValueError("ambiguous matching events")

    if not isinstance(action, dict) or set(action) != ACTION_KEYS or action["schema"] != "replaymark.runtime.e3b-historical-action-record.v1":
        raise ValueError("action schema drift")
    if action["capture_point"] != "paho.mqtt.Client.publish.pre-send" or action["clock_domain"] != clock:
        raise ValueError("action capture/clock drift")
    if ns(action["publish_mono_ns"]) < command:
        raise ValueError("action predates ACT1")
    parts = action["topic"].split("/") if isinstance(action["topic"], str) else []
    if len(parts) != 3 or parts[0] != "agentmark" or parts[2] != "command":
        raise ValueError("action topic drift")
    action_prefix, action_task = identity(parts[1], "b")
    if (action_prefix, action_task) != (prefix, task):
        raise ValueError("cross-task action")
    if action["payload_utf8"] != '{"on": true}' or action["qos"] != 1 or isinstance(action["qos"], bool) or action["retain"] is not False or action["properties"] is not None:
        raise ValueError("historical ACT2 bytes drift")
    return matches == 1, prefix, task


def policy_for(trial, task):
    block, offset = divmod(task, 3)
    digest = hashlib.sha256(f"{POLICY_SEED}|trial={trial}|block={block}".encode()).digest()
    return RELABEL[P6_PERMS[int.from_bytes(digest[:8], "big") % 6][offset]]


def reference_blocks(trial):
    ranked = sorted((hashlib.sha256(f"{CLASS_SEED}|trial={trial}|block={block}".encode()).hexdigest(), block) for block in range(64))
    return frozenset(block for _digest, block in ranked[:32])


def class_for(trial, task):
    return "REFERENCE" if task // 3 in reference_blocks(trial) else "SHIFTED"


def parse_topic_task(topic, role, kind):
    if not isinstance(topic, str):
        raise ValueError("topic not string")
    parts = topic.split("/")
    if len(parts) != 3 or parts[0] != "agentmark" or parts[2] != kind:
        raise ValueError("topic family drift")
    return identity(parts[1], role)


def effect_count(row, prefix, task):
    start = row.get("b_effect_start_mono_ns")
    deadline = row.get("b_effect_deadline_mono_ns")
    if start is None:
        return 0
    start, deadline = ns(start), ns(deadline)
    expected = f"{prefix}-{task}-b"
    effects = row.get("b_effects")
    if not isinstance(effects, list):
        raise ValueError("B effects missing")
    return sum(
        1 for event in effects
        if isinstance(event, dict)
        and event.get("device") == expected
        and event.get("on") is True
        and event.get("cause") == "command"
        and isinstance(event.get("recv_mono_ns"), int)
        and start <= int(event["recv_mono_ns"]) <= deadline
    )


def preflight():
    if git("rev-parse", "HEAD^") != PARENT:
        raise AssertionError("S3 execution must be exact child of S3-P")
    changed = set(git("diff", "--name-only", PARENT, "HEAD").splitlines())
    if changed != EXPECTED_INCREMENT:
        raise AssertionError(f"undeclared S3 increment missing={sorted(EXPECTED_INCREMENT-changed)} extra={sorted(changed-EXPECTED_INCREMENT)}")
    for path, expected in FROZEN_BLOBS.items():
        if git("rev-parse", f"HEAD:{path}") != expected:
            raise AssertionError(f"frozen blob drift {path}")
    runner = (ROOT / "agentmark_e3b_lab/e3_mqtt/app/replaymark_s3_caller_native_restoration.py").read_text()
    forbidden = (CLASS_SEED, "REFERENCE", "SHIFTED", "replaymark_oracle")
    if any(token in runner for token in forbidden):
        raise AssertionError("live S3 runner contains hidden class/oracle material")
    if "E3bCertifiedExecutionGate(historical)" not in runner:
        raise AssertionError("ReplayMark gate is not bound only to historical channel")
    workflow = (ROOT / ".github/workflows/replaymark-runtime-gate-s3-caller-native-restoration-execution.yml").read_text()
    if "s2p6_heterogeneous_device.py" not in workflow:
        raise AssertionError("exact P6 target not reused")
    return {"exact_s3p_parent": True, "declared_files_only": True, "frozen_blobs": len(FROZEN_BLOBS), "runner_class_blind": True, "runner_oracle_blind": True, "p6_target_reused": True}


def audit(report):
    if report.get("schema") != "replaymark.s3-live-caller-native-restoration.v1" or report.get("broker") != "mosquitto version 2.1.2":
        raise AssertionError("report identity drift")
    if report.get("historical_template_sha256") != HISTORICAL_TEMPLATE_SHA256:
        raise AssertionError("historical template drift")
    if report.get("caller_owns_native_recovery") is not True or report.get("fallback_inside_replaymark") is not False or report.get("regeneration_inside_replaymark") is not False or report.get("automatic_retry") != "ABSENT":
        raise AssertionError("policy boundary drift")
    raw_text = json.dumps(report, sort_keys=True)
    if "REFERENCE" in raw_text or "SHIFTED" in raw_text or CLASS_SEED in raw_text:
        raise AssertionError("hidden class leaked into live report")

    historical_calls = report.get("historical_calls")
    native_calls = report.get("native_calls")
    if not isinstance(historical_calls, list) or not isinstance(native_calls, list):
        raise AssertionError("provenance channels missing")
    if any(c.get("channel") != "HISTORICAL_ACT2" for c in historical_calls):
        raise AssertionError("historical channel contamination")
    if any(c.get("channel") not in ("NATIVE_QUERY_A", "NATIVE_FRESH_ACT2") for c in native_calls):
        raise AssertionError("native channel contamination")

    hist_by_task, query_by_task, fresh_by_task = {}, {}, {}
    for call in historical_calls:
        prefix, task = parse_topic_task(call.get("topic"), "b", "command")
        key = (prefix, task)
        if key in hist_by_task:
            raise AssertionError("duplicate historical application call")
        hist_by_task[key] = call
        if call.get("payload") != '{"on": true}' or call.get("qos") != 1 or call.get("retain") is not False or call.get("properties") is not None:
            raise AssertionError("historical sink bytes drift")
    for call in native_calls:
        if call.get("channel") == "NATIVE_QUERY_A":
            prefix, task = parse_topic_task(call.get("topic"), "a", "query")
            dest = query_by_task
            if call.get("payload") != "{}":
                raise AssertionError("native query bytes drift")
        else:
            prefix, task = parse_topic_task(call.get("topic"), "b", "command")
            dest = fresh_by_task
            if call.get("payload") != '{"on": true}':
                raise AssertionError("native fresh ACT2 bytes drift")
        key = (prefix, task)
        if key in dest:
            raise AssertionError("duplicate native application call")
        dest[key] = call
        if call.get("qos") != 1 or call.get("retain") is not False or call.get("properties") is not None:
            raise AssertionError("native call QoS/retain/properties drift")
        if ns(call.get("generated_mono_ns")) > ns(call.get("stamp_mono_ns")):
            raise AssertionError("native generation after publish stamp")

    assigned, safe_sets, hist_sets, native_sets, restored_sets = defaultdict(set), defaultdict(set), defaultdict(set), defaultdict(set), defaultdict(set)
    safe_count, unsafe_count = Counter(), Counter()
    class_truth = Counter()
    policy_class = defaultdict(Counter)
    trial_truth = defaultdict(Counter)
    failures = {"semantic": [], "execution": [], "native": [], "phase": [], "effects": [], "provenance": []}
    rows_seen = 0

    trials = report.get("trials")
    if not isinstance(trials, list) or len(trials) != 6:
        raise AssertionError("six trials required")
    prefixes = set()
    for trial_index, trial in enumerate(trials):
        prefix = trial.get("prefix")
        if not isinstance(prefix, str) or prefix in prefixes:
            raise AssertionError("trial prefix not fresh")
        prefixes.add(prefix)
        if trial.get("trial") != trial_index or not isinstance(trial.get("rows"), list) or len(trial["rows"]) != 192:
            raise AssertionError("trial structure drift")
        freeze, quiescence, cert_done, dispatch_done, effects_done = map(ns, (
            trial["observation_freeze_complete_mono_ns"], trial["a_quiescence_barrier_mono_ns"],
            trial["certification_complete_mono_ns"], trial["dispatch_complete_mono_ns"], trial["b_effect_barrier_mono_ns"]
        ))
        if not freeze <= quiescence <= cert_done <= dispatch_done <= effects_done:
            failures["phase"].append((trial_index, "trial_order"))
        for task, row in enumerate(trial["rows"]):
            rows_seen += 1
            if row.get("trial") != trial_index or row.get("task_id") != task:
                raise AssertionError("row identity drift")
            policy = policy_for(trial_index, task)
            if row.get("policy") != policy:
                raise AssertionError("policy schedule drift")
            cls = class_for(trial_index, task)
            policy_class[(trial_index, policy)][cls] += 1
            safe, parsed_prefix, parsed_task = literal_safe(row["raw_observation"], row["raw_action"])
            if parsed_prefix != prefix or parsed_task != task:
                raise AssertionError("same-task prefix drift")
            key = (trial_index, task)
            assigned[policy].add(key)
            if safe:
                safe_sets[policy].add(key); safe_count[policy] += 1; class_truth[f"{cls}_safe"] += 1; trial_truth[trial_index]["safe"] += 1
            else:
                unsafe_count[policy] += 1; class_truth[f"{cls}_unsafe"] += 1; trial_truth[trial_index]["unsafe"] += 1
            if row.get("certificate_verdict") != ("VALID" if safe else "INVALID") or row.get("certificate_reuse_disposition") != ("REUSE" if safe else "DO_NOT_REUSE"):
                failures["semantic"].append(key)
            if row.get("execution_failure") is not None:
                failures["execution"].append((key, row.get("execution_failure")))
            if row.get("native_failure") is not None:
                failures["native"].append((key, row.get("native_failure")))
            if ns(row["raw_observation"]["closed_at_mono_ns"]) > freeze or ns(row["raw_action"]["publish_mono_ns"]) < quiescence:
                failures["phase"].append((key, "freeze_or_candidate_order"))

            app_key = (prefix, task)
            hist = app_key in hist_by_task
            query = app_key in query_by_task
            fresh = app_key in fresh_by_task
            if hist:
                hist_sets[policy].add(key)
                if ns(hist_by_task[app_key]["stamp_mono_ns"]) < cert_done:
                    failures["phase"].append((key, "historical_before_certification_complete"))
            if query or fresh:
                native_sets[policy].add(key)
            if query != fresh:
                failures["provenance"].append((key, "partial_native_path"))

            if query and fresh:
                qcall, fcall = query_by_task[app_key], fresh_by_task[app_key]
                provenance = row.get("native_provenance")
                if not isinstance(provenance, dict):
                    failures["provenance"].append((key, "native_provenance_missing"))
                else:
                    confirmation = provenance.get("query_confirmation")
                    if not isinstance(confirmation, dict):
                        failures["provenance"].append((key, "confirmation_missing"))
                    else:
                        qstamp = ns(qcall["stamp_mono_ns"])
                        recv = ns(confirmation.get("recv_mono_ns"))
                        generated = ns(fcall["generated_mono_ns"])
                        fstamp = ns(fcall["stamp_mono_ns"])
                        expected_a = f"{prefix}-{task}-a"
                        if not (qstamp <= recv <= generated <= fstamp):
                            failures["provenance"].append((key, "native_causal_order"))
                        if confirmation.get("device") != expected_a or confirmation.get("cause") != "query" or confirmation.get("on") is not True:
                            failures["provenance"].append((key, "native_confirmation_content"))
                        events = row.get("native_a_events")
                        if not isinstance(events, list) or not any(
                            e.get("device") == expected_a and e.get("cause") == "query" and e.get("on") is True and e.get("recv_mono_ns") == recv
                            for e in events if isinstance(e, dict)
                        ):
                            failures["provenance"].append((key, "confirmation_not_in_raw_A_events"))
                if hist:
                    failures["provenance"].append((key, "historical_and_native_both_executed"))

            effects = effect_count(row, prefix, task)
            if effects >= 1:
                restored_sets[policy].add(key)
            else:
                failures["effects"].append(key)
            start = row.get("b_effect_start_mono_ns")
            if start is not None and ns(start) < cert_done:
                failures["phase"].append((key, "B_dispatch_before_certification_complete"))

            if policy == "ALWAYS_REUSE" and (not hist or query or fresh):
                failures["provenance"].append((key, "always_reuse_path_drift"))
            if policy == "ALWAYS_NATIVE" and (hist or not query or not fresh):
                failures["provenance"].append((key, "always_native_path_drift"))
            if policy == "REPLAYMARK_NATIVE":
                if safe and (not hist or query or fresh):
                    failures["provenance"].append((key, "safe_replaymark_path_drift"))
                if (not safe) and (hist or not query or not fresh):
                    failures["provenance"].append((key, "unsafe_replaymark_path_drift"))

    for trial in range(6):
        if trial_truth[trial]["safe"] == 0 or trial_truth[trial]["unsafe"] == 0:
            raise AssertionError("trial not semantically mixed")
        for policy in POLICIES:
            if policy_class[(trial, policy)] != Counter({"REFERENCE": 32, "SHIFTED": 32}):
                raise AssertionError("policy/class orthogonality drift")

    checks = {
        "rows_1152": rows_seen == 1152,
        "policy_assignment_384_each": all(len(assigned[p]) == 384 for p in POLICIES),
        "semantic_mismatches_zero": not failures["semantic"],
        "execution_failures_zero": not failures["execution"],
        "native_failures_zero": not failures["native"],
        "phase_failures_zero": not failures["phase"],
        "effect_failures_zero": not failures["effects"],
        "provenance_failures_zero": not failures["provenance"],
        "historical_count_matches_report": len(historical_calls) == report.get("historical_call_count"),
        "native_count_matches_report": len(native_calls) == report.get("native_call_count"),
        "always_reuse_historical_all": hist_sets["ALWAYS_REUSE"] == assigned["ALWAYS_REUSE"],
        "always_reuse_native_empty": not native_sets["ALWAYS_REUSE"],
        "always_reuse_unsafe_positive": bool(hist_sets["ALWAYS_REUSE"] - safe_sets["ALWAYS_REUSE"]),
        "always_native_historical_empty": not hist_sets["ALWAYS_NATIVE"],
        "always_native_native_all": native_sets["ALWAYS_NATIVE"] == assigned["ALWAYS_NATIVE"],
        "always_native_unnecessary_positive": bool(native_sets["ALWAYS_NATIVE"] & safe_sets["ALWAYS_NATIVE"]),
        "replaymark_historical_equals_safe": hist_sets["REPLAYMARK_NATIVE"] == safe_sets["REPLAYMARK_NATIVE"],
        "replaymark_native_equals_unsafe": native_sets["REPLAYMARK_NATIVE"] == assigned["REPLAYMARK_NATIVE"] - safe_sets["REPLAYMARK_NATIVE"],
        "replaymark_unsafe_historical_zero": not (hist_sets["REPLAYMARK_NATIVE"] - safe_sets["REPLAYMARK_NATIVE"]),
        "replaymark_unnecessary_native_zero": not (native_sets["REPLAYMARK_NATIVE"] & safe_sets["REPLAYMARK_NATIVE"]),
        "all_tasks_restored": all(restored_sets[p] == assigned[p] for p in POLICIES),
        "gate_consumed_384": report.get("replaymark_gate_consumed_count") == 384,
    }
    counts = {
        "safe_by_policy": {p: safe_count[p] for p in POLICIES},
        "unsafe_by_policy": {p: unsafe_count[p] for p in POLICIES},
        "historical_reuse_by_policy": {p: len(hist_sets[p]) for p in POLICIES},
        "native_path_by_policy": {p: len(native_sets[p]) for p in POLICIES},
        "restored_by_policy": {p: len(restored_sets[p]) for p in POLICIES},
        "unsafe_historical_by_policy": {p: len(hist_sets[p] - safe_sets[p]) for p in POLICIES},
        "unnecessary_native_by_policy": {p: len(native_sets[p] & safe_sets[p]) for p in POLICIES},
        "oracle_by_hidden_target_class": {
            "REFERENCE_safe": class_truth["REFERENCE_safe"],
            "REFERENCE_unsafe": class_truth["REFERENCE_unsafe"],
            "SHIFTED_safe": class_truth["SHIFTED_safe"],
            "SHIFTED_unsafe": class_truth["SHIFTED_unsafe"],
        },
        "historical_application_calls": len(historical_calls),
        "native_query_calls": sum(1 for c in native_calls if c.get("channel") == "NATIVE_QUERY_A"),
        "native_fresh_act2_calls": sum(1 for c in native_calls if c.get("channel") == "NATIVE_FRESH_ACT2"),
    }
    return {
        "schema": "replaymark.s3-caller-native-restoration-verification.v1",
        "verdict": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "counts": counts,
        "failures": failures,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--input")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    pre = preflight()
    if args.preflight_only:
        report = {"schema": "replaymark.s3-execution-preflight.v1", "verdict": "PASS", "preflight": pre}
    else:
        if not args.input:
            raise SystemExit("--input required")
        source = Path(args.input)
        report = audit(json.loads(source.read_text()))
        report["preflight"] = pre
        report["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    if report.get("verdict") != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
