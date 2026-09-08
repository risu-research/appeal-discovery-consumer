from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys


PROTOCOL_HEAD = "274b870313696adaf2f80b52632e9b6ea854fd90"
PROTOCOL_TREE = "d224364fd416c8823bf0b2cc11ec684ffb60e724"
PROTOCOL_SHA256 = "ac50c3b7ac69397c3af0c5344f85c5eeb7bd77ee5535af920db41564304e5d0f"
SCHEDULE_SHA256 = "3330c82c66cd344e01b48ac16e96e5fb4b4cb3a6b55ea880fe6285621e039af8"
SCHEDULE_SEED = "replaymark.s3c1.paired-target-class.v1|c0=94584db84bebd73e664f19f0fe2d3b9f5998c813"
BROKER_CONFIG = (
    "listener 1883 0.0.0.0\n"
    "allow_anonymous true\n"
    "persistence false\n"
    "sys_interval 1\n"
    "log_type error\n"
    "log_type warning\n"
    "log_type notice\n"
)
BROKER_CONFIG_SHA256 = "886f26936b560ebfbf584744c8c4f5f2dd3eeeba946313ad1d2f7f8848bf0858"
BROKER_IMAGE_DIGEST = "sha256:6f8d8a947c506f8a2290ec65cd4bd2bc7cb4d43fb5f6271f861cb013e2ef9797"
BATCHES = (192, 196, 200, 204, 208)
TRIALS = 6
REPLICAS = ("A", "B")
ARMS = ("ALWAYS_REUSE", "DIRECT_NATIVE", "REPLAYMARK_NATIVE", "ALWAYS_NATIVE")
ARM_CODES = {
    "ALWAYS_REUSE": "ru",
    "DIRECT_NATIVE": "dn",
    "REPLAYMARK_NATIVE": "rn",
    "ALWAYS_NATIVE": "an",
}
CHANGED = {
    ".github/workflows/replaymark-runtime-gate-s3c1-implementation-conformance.yml",
    "agentmark_e3b_lab/e3_mqtt/app/replaymark_s3c1_paired_deployment.py",
    "agentmark_e3b_lab/e3_mqtt/app/s3c1_direct_native.py",
    "agentmark_e3b_lab/e3_mqtt/app/s3c1_paired_heterogeneous_device.py",
    "replaymark_verification/verify_s3c1_implementation_conformance.py",
    "replaymark_verification/verify_s3c1_paired_deployment.py",
}
FROZEN_BLOBS = {
    "replaymark/S3C1_PAIRED_FOUR_ARM_DEPLOYMENT_PROTOCOL.json": "2b9654e325376b63e39e8171ff75371c235d6eb2",
    "replaymark/S3C1_PAIRED_FOUR_ARM_DEPLOYMENT_PROTOCOL.md": "2c0a0234b29f524c0cfdb5256b872cbbe6de9d92",
    "replaymark_verification/verify_s3c1_paired_four_arm_deployment_protocol.py": "4acbd8d4b963d4cf882e637e0889dde649e62f80",
    ".github/workflows/replaymark-runtime-gate-s3c1-paired-four-arm-deployment-protocol.yml": "58092c1a88006e61ac03d7486e9c14de505f1491",
    "replaymark/S3C0_CLAIM_TO_QUEUE_COMPOSITION_RESULT_SEAL.json": "6590883c26977cc66487e7111097ec0a6b3266db",
    "replaymark/S3_CALLER_OWNED_NATIVE_RESTORATION_RESULT_SEAL.json": "35658806601f84a67199cd691607d0ead388952b",
    "agentmark_e3b_lab/e3_mqtt/app/replaymark_s3_caller_native_restoration.py": "cd4150585e36c07b737e27e5a879030b031dab4f",
    "agentmark_e3b_lab/e3_mqtt/app/s2p6_heterogeneous_device.py": "5b57bc44e91dc38e44eaafc760286fa4b616ff9c",
    "replaymark/runtime_e3b_execution_gate.py": "22748a5aa820e83e4700a339e8af297cdd9f9143",
    "replaymark/runtime_e3b_action.py": "d5d483751eb06fd8b00f7bb2eff613a20f0f796c",
    "replaymark/runtime_e3b_observation.py": "de6cdc8ccdbb9b189e238cc5dbad173060fe17ab",
    "replaymark/runtime_e3b_correlation.py": "bbdc243eccf29c0a26b92bc78c0acdb96222da8e",
    "replaymark/runtime_e3b_bridge.py": "5c2b13f35edcae9ce42fa062f51f1b6ce46747bf",
    "agentmark_e3b_lab/e3_mqtt/mosquitto/mosquitto.conf": "0b68187c4590e780409048ea8c9e3144d34ccaa6",
}
CROSS_HISTORY_BLOBS = {
    ("23b7c85bca6cb85fde9f4361a0f9664d21c8ae8d", "replaymark_e3b_default_flip/DEFAULT_FLIP_PROTOCOL.md"):
        "d05917bf9ad69edb8adf1a642efda598b9b2aa0e",
    ("ac20890bb4aa926e439802510de3723b74591c94", "replaymark_e3b_default_flip/CONFIRMATORY_OUTCOME.md"):
        "6d9c90d629b0e384b568a25fa93504dbe23828e6",
}


def g(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            out.add(node.module or "")
    return out


def _function_args(path: Path, name: str) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return [arg.arg for arg in node.args.args]
    raise AssertionError(f"missing function {name}")


def _schedule_rows():
    rows = []
    for n in BATCHES:
        for trial in range(TRIALS):
            ranked = sorted(
                (
                    sha256(f"{SCHEDULE_SEED}|batch={n}|trial={trial}|task={task}".encode("utf-8")),
                    task,
                )
                for task in range(n)
            )
            shifted = {task for _digest, task in ranked[: n // 2]}
            rows.extend(
                {
                    "batch_size": n,
                    "trial": trial,
                    "task_id": task,
                    "class": "SHIFTED" if task in shifted else "REFERENCE",
                }
                for task in range(n)
            )
    return rows


def _shifted(n: int, trial: int) -> set[int]:
    ranked = sorted(
        (
            sha256(f"{SCHEDULE_SEED}|batch={n}|trial={trial}|task={task}".encode("utf-8")),
            task,
        )
        for task in range(n)
    )
    return {task for _digest, task in ranked[: n // 2]}


def _device(replica: str, n: int, trial: int, nonce: str, arm: str, task: int, role: str) -> str:
    return f"s3c1-r{replica}-n{n}-t{trial}-{nonce}-{ARM_CODES[arm]}-{task}-{role}"


def _app_event(seq: int, arm: str, task: int, channel: str, topic: str, stamp: int, payload: str):
    return {
        "seq": seq, "arm": arm, "task_id": task, "channel": channel,
        "topic": topic, "payload_utf8": payload, "qos": 1, "retain": False,
        "properties": None, "publish_mono_ns": stamp,
    }


def _online_event(seq: int, topic: str, payload: str, recv: int):
    return {
        "seq": seq, "topic": topic, "payload_utf8": payload, "qos": 1,
        "retain": False, "dup": False, "recv_mono_ns": recv,
    }


def synthetic_cell(replica: str, n: int, trial: int) -> dict[str, object]:
    nonce = f"syn{replica}{n}{trial}"
    shifted = _shifted(n, trial)
    app: list[dict[str, object]] = []
    online: list[dict[str, object]] = []
    tasks = [{"task_id": task, "arms": {}} for task in range(n)]
    waves = []
    app_seq = 0
    online_seq = 0
    base = 10_000_000_000 + (0 if replica == "A" else 10_000_000_000) + n * 10_000_000 + trial * 1_000_000

    def emit_call(arm: str, task: int, channel: str, topic: str, stamp: int, payload: str):
        nonlocal app_seq, online_seq
        row = _app_event(app_seq, arm, task, channel, topic, stamp, payload)
        app_seq += 1
        app.append(row)
        online.append(_online_event(online_seq, topic, payload, stamp + 1_000))
        online_seq += 1
        return row

    def emit_state(device: str, cause: str, recv: int):
        nonlocal online_seq
        payload = json.dumps(
            {"device": device, "on": True, "cause": cause, "ts_mono_ns": recv - 500},
            sort_keys=True,
        )
        online.append(_online_event(online_seq, f"agentmark/{device}/state", payload, recv))
        online_seq += 1
        return {
            "event_id": f"synthetic:{device}:{recv}",
            "device": device,
            "on": True,
            "recv_mono_ns": recv,
            "clock_domain": "replaymark.e3b-r1-shadow.monotonic.v1",
        }

    for wave_index, start in enumerate(range(0, n, 4)):
        ids = list(range(start, start + 4))
        wave_start = base + wave_index * 500_000_000
        timings = {}
        a_state = {}
        offset = 0
        for task in ids:
            for arm in ARMS:
                a = _device(replica, n, trial, nonce, arm, task, "a")
                stamp = wave_start + offset * 10_000
                offset += 1
                emit_call(arm, task, "ACT1", f"agentmark/{a}/command", stamp, '{"on": true}')
                safe = task not in shifted
                recv = stamp + (10_000_000 if safe else 180_000_000)
                a_state[(arm, task)] = emit_state(a, "command", recv)
                timings[(arm, task)] = (stamp, stamp + 100_000_000)
        common_close = max(deadline for _stamp, deadline in timings.values())

        for task in ids:
            safe = task not in shifted
            for arm in ARMS:
                stamp, deadline = timings[(arm, task)]
                events = [a_state[(arm, task)]] if safe else []
                raw = {
                    "schema": "replaymark.runtime.e3b-observation-record.v1",
                    "clock_domain": "replaymark.e3b-r1-shadow.monotonic.v1",
                    "expected_device": _device(replica, n, trial, nonce, arm, task, "a"),
                    "command_publish_mono_ns": stamp,
                    "verify_deadline_mono_ns": deadline,
                    "closed_at_mono_ns": common_close,
                    "events": events,
                }
                tasks[task]["arms"][arm] = {"raw_observation": raw, "dispatch": {}, "errors": []}

        b_state_times = []
        for lane, task in enumerate(ids):
            action_cursor = common_close + 1_000_000 + lane * 100_000
            safe = task not in shifted

            arm = "ALWAYS_REUSE"
            b = _device(replica, n, trial, nonce, arm, task, "b")
            emit_call(arm, task, "HISTORICAL_ACT2", f"agentmark/{b}/command", action_cursor, '{"on": true}')
            recv = action_cursor + (10_000_000 if safe else 180_000_000)
            emit_state(b, "command", recv); b_state_times.append(recv); action_cursor += 1_000_000

            arm = "DIRECT_NATIVE"
            if not safe:
                a = _device(replica, n, trial, nonce, arm, task, "a")
                emit_call(arm, task, "NATIVE_QUERY_A", f"agentmark/{a}/query", action_cursor, "{}")
                qrecv = action_cursor + 1_000_000
                emit_state(a, "query", qrecv)
                action_cursor = qrecv + 20_000_000
            b = _device(replica, n, trial, nonce, arm, task, "b")
            emit_call(arm, task, "NATIVE_FRESH_ACT2", f"agentmark/{b}/command", action_cursor, '{"on": true}')
            recv = action_cursor + (10_000_000 if safe else 180_000_000)
            emit_state(b, "command", recv); b_state_times.append(recv); action_cursor += 1_000_000

            arm = "REPLAYMARK_NATIVE"
            b = _device(replica, n, trial, nonce, arm, task, "b")
            if safe:
                emit_call(arm, task, "HISTORICAL_ACT2", f"agentmark/{b}/command", action_cursor, '{"on": true}')
            else:
                a = _device(replica, n, trial, nonce, arm, task, "a")
                emit_call(arm, task, "NATIVE_QUERY_A", f"agentmark/{a}/query", action_cursor, "{}")
                qrecv = action_cursor + 1_000_000
                emit_state(a, "query", qrecv)
                action_cursor = qrecv + 20_000_000
                emit_call(arm, task, "NATIVE_FRESH_ACT2", f"agentmark/{b}/command", action_cursor, '{"on": true}')
            recv = action_cursor + (10_000_000 if safe else 180_000_000)
            emit_state(b, "command", recv); b_state_times.append(recv); action_cursor += 1_000_000

            arm = "ALWAYS_NATIVE"
            a = _device(replica, n, trial, nonce, arm, task, "a")
            b = _device(replica, n, trial, nonce, arm, task, "b")
            emit_call(arm, task, "NATIVE_QUERY_A", f"agentmark/{a}/query", action_cursor, "{}")
            qrecv = action_cursor + 1_000_000
            emit_state(a, "query", qrecv)
            action_cursor = qrecv + 20_000_000
            emit_call(arm, task, "NATIVE_FRESH_ACT2", f"agentmark/{b}/command", action_cursor, '{"on": true}')
            recv = action_cursor + (10_000_000 if safe else 180_000_000)
            emit_state(b, "command", recv); b_state_times.append(recv); action_cursor += 1_000_000

        quiescence = max(max(b_state_times), max(
            int(a_state[(arm, task)]["recv_mono_ns"]) for task in ids for arm in ARMS
        )) + 50_000_000
        waves.append({
            "wave_index": wave_index,
            "task_ids": ids,
            "scheduled_start_mono_ns": wave_start,
            "actual_start_mono_ns": wave_start,
            "snapshot_closed_at_mono_ns": common_close,
            "post_decision_quiescence_mono_ns": quiescence,
            "quiescence_missing": [],
            "next_wave_schedule_overrun": False,
        })

    online.sort(key=lambda e: (int(e["recv_mono_ns"]), int(e["seq"])))
    for seq, event in enumerate(online):
        event["seq"] = seq

    collectors = {}
    for arm in ARMS:
        arm_events = []
        for event in online:
            topic = str(event["topic"])
            if f"-{ARM_CODES[arm]}-" in topic:
                arm_events.append(copy.deepcopy(event))
        deliveries = arm_events[: min(len(arm_events), 1000)]
        devices = sorted(
            _device(replica, n, trial, nonce, arm, task, role)
            for task in range(n) for role in ("a", "b")
        )
        collectors[arm] = {
            "arm": arm,
            "client_id": f"synthetic-{replica}-{n}-{trial}-{ARM_CODES[arm]}",
            "clean_session": False,
            "filters": [f"agentmark/{d}/#" for d in devices],
            "session_present": True,
            "delivery_count": len(deliveries),
            "deliveries": deliveries,
        }

    return {
        "schema": "replaymark.s3c1-paired-four-arm-live-cell.v1",
        "protocol_head": PROTOCOL_HEAD,
        "protocol_sha256": PROTOCOL_SHA256,
        "historical_template_sha256": "e86d5f42a09b8257185b6e3608ac83c0ac41deeba7890b914c22b0441a8b8888",
        "cell": {"replica": replica, "batch_size": n, "trial": trial, "nonce": nonce},
        "frozen_parameters": {
            "arms": list(ARMS), "logical_wave_size": 4, "physical_four_arm_twins_per_wave": 16,
            "wave_period_ms": 500.0, "verify_deadline_ms": 100.0, "task_timeout_ms": 1000,
            "post_confirmation_gap_ms": 20.0, "persistent_queue_limit": 1000,
        },
        "broker_attestation": {
            "config_path": "synthetic/mosquitto.conf",
            "config_utf8": BROKER_CONFIG,
            "config_sha256": BROKER_CONFIG_SHA256,
            "forbidden_queue_directives_present": [],
            "supplied_image_digest": BROKER_IMAGE_DIGEST,
            "observed_version": "mosquitto version 2.1.2",
            "required_version": "mosquitto version 2.1.2",
            "required_config_sha256": BROKER_CONFIG_SHA256,
            "required_image_digest": BROKER_IMAGE_DIGEST,
        },
        "tasks": tasks,
        "waves": waves,
        "application_publish_provenance": app,
        "online_role_ledger": online,
        "persistent_collectors": collectors,
        "workload_complete_mono_ns": max(w["post_decision_quiescence_mono_ns"] for w in waves),
        "scientific_verdict_in_live_runner": False,
        "independent_oracle_used_in_live_runner": False,
        "fallback_inside_replaymark": False,
        "regeneration_inside_replaymark": False,
        "automatic_retry": "ABSENT",
    }


def _load_validator():
    path = Path("replaymark_verification/verify_s3c1_paired_deployment.py")
    spec = importlib.util.spec_from_file_location("s3c1_independent_validator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load independent validator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    checks: dict[str, bool] = {}
    detail: dict[str, object] = {}

    checks["exact_parent_protocol_head"] = g("rev-parse", "HEAD^") == PROTOCOL_HEAD
    checks["exact_parent_protocol_tree"] = g("show", "-s", "--format=%T", "HEAD^") == PROTOCOL_TREE
    changed = set(filter(None, g("diff", "--name-only", "HEAD^", "HEAD").splitlines()))
    checks["exact_six_additive_implementation_files"] = changed == CHANGED
    detail["changed_paths"] = sorted(changed)

    frozen = []
    for path, expected in FROZEN_BLOBS.items():
        actual = g("rev-parse", f"HEAD:{path}")
        frozen.append({"path": path, "expected": expected, "actual": actual, "match": actual == expected})
    checks["all_protocol_runtime_and_queue_blobs_unchanged"] = all(row["match"] for row in frozen)
    detail["frozen_blobs"] = frozen

    cross = []
    for (ref, path), expected in CROSS_HISTORY_BLOBS.items():
        actual = g("rev-parse", f"{ref}:{path}")
        cross.append({"ref": ref, "path": path, "expected": expected, "actual": actual, "match": actual == expected})
    checks["cross_history_queue_authorities_exact"] = all(row["match"] for row in cross)
    detail["cross_history_blobs"] = cross

    protocol_bytes = Path("replaymark/S3C1_PAIRED_FOUR_ARM_DEPLOYMENT_PROTOCOL.json").read_bytes()
    checks["protocol_bytes_exact"] = sha256(protocol_bytes) == PROTOCOL_SHA256

    rows = _schedule_rows()
    schedule_sha = sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    checks["independent_schedule_digest_exact"] = schedule_sha == SCHEDULE_SHA256
    checks["schedule_exact_half_each_cell"] = all(
        len(_shifted(n, trial)) == n // 2 for n in BATCHES for trial in range(TRIALS)
    )
    detail["schedule_sha256"] = schedule_sha

    target = Path("agentmark_e3b_lab/e3_mqtt/app/s3c1_paired_heterogeneous_device.py")
    direct = Path("agentmark_e3b_lab/e3_mqtt/app/s3c1_direct_native.py")
    runner = Path("agentmark_e3b_lab/e3_mqtt/app/replaymark_s3c1_paired_deployment.py")
    validator = Path("replaymark_verification/verify_s3c1_paired_deployment.py")
    target_imports, direct_imports = _imports(target), _imports(direct)
    runner_imports, validator_imports = _imports(runner), _imports(validator)

    checks["target_has_no_replaymark_or_oracle_import"] = not any(
        name.startswith("replaymark") or "oracle" in name for name in target_imports
    )
    checks["direct_reference_has_no_replaymark_runner_target_or_oracle_import"] = not any(
        name.startswith("replaymark") or "replaymark_s3c1" in name or
        "s3c1_paired_heterogeneous_device" in name or "oracle" in name
        for name in direct_imports
    )
    checks["independent_validator_has_no_replaymark_runner_or_production_import"] = not any(
        name.startswith("replaymark") or "replaymark_s3c1" in name
        for name in validator_imports
    )
    checks["runner_imports_direct_and_frozen_replaymark_but_not_target_or_validator"] = (
        "s3c1_direct_native" in runner_imports
        and "replaymark.runtime_e3b_execution_gate" in runner_imports
        and "replaymark.runtime_e3b_bridge" in runner_imports
        and "replaymark.runtime_e3b_correlation" in runner_imports
        and "s3c1_paired_heterogeneous_device" not in runner_imports
        and "replaymark_verification.verify_s3c1_paired_deployment" not in runner_imports
    )

    checks["target_class_function_has_no_arm_input"] = _function_args(target, "delay_for_task") == [
        "batch_size", "trial", "task_id"
    ]
    target_text = target.read_text(encoding="utf-8")
    checks["target_wire_has_no_class_label"] = '"class"' not in target_text and "'class'" not in target_text
    checks["target_fixed_delays_and_query_semantics"] = all(
        token in target_text for token in [
            "REFERENCE_DELAY_MS = 0", "SHIFTED_DELAY_MS = 180",
            'publish_state(device, "query")', 'schedule_state(device, "command", delay_ms)',
        ]
    )

    direct_text = direct.read_text(encoding="utf-8")
    checks["direct_rule_is_exact_two_branch_no_history_certificate"] = all(
        token in direct_text for token in [
            "CONFIRMED_BY_DEADLINE", "NOT_VISIBLE_BY_DEADLINE",
            'route="FRESH_ACT2_NO_QUERY"', 'route="QUERY_CONFIRM_THEN_FRESH_ACT2"',
        ]
    ) and "certificate" not in direct_text.lower() and "historical" not in direct_text.lower()

    runner_text = runner.read_text(encoding="utf-8")
    checks["runner_frozen_matrix_constants_exact"] = all(
        token in runner_text for token in [
            "BATCH_SIZES = (192, 196, 200, 204, 208)", 'REPLICAS = ("A", "B")',
            "LOGICAL_WAVE_SIZE = 4", "PHYSICAL_TWINS_PER_WAVE = 16",
            "WAVE_PERIOD_MS = 500.0", "VERIFY_MS = 100.0",
            "TASK_TIMEOUT_MS = 1000", "POST_CONFIRMATION_GAP_MS = 20.0",
            "QUEUE_LIMIT = 1000",
        ]
    )
    checks["runner_four_isolated_persistent_sessions_and_no_broad_filter"] = (
        'f"agentmark/{device}/#"' in runner_text
        and "clean_session=False" in runner_text
        and '"agentmark/#"' not in runner_text
        and "session_present_on_drain" in runner_text
    )
    checks["runner_snapshot_barrier_before_dispatch"] = (
        runner_text.index("# Freeze/certify every RM candidate for the wave before any post-snapshot traffic.")
        > runner_text.index("closed_at = time.monotonic_ns()")
        and runner_text.index("with ThreadPoolExecutor(max_workers=PHYSICAL_TWINS_PER_WAVE)")
        > runner_text.index("# Freeze/certify every RM candidate")
    )
    checks["runner_parallel_16_twin_dispatch_preserves_500ms_barrier_budget"] = (
        "ThreadPoolExecutor(max_workers=PHYSICAL_TWINS_PER_WAVE)" in runner_text
        and "for task_id in wave_ids\n                    for arm in ARMS" in runner_text
        and "next_wave_schedule_overrun" in runner_text
    )
    checks["runner_no_scientific_validator_or_target_class_input"] = (
        "validate_cell" not in runner_text and "validate_matrix" not in runner_text
        and "_shifted(" not in runner_text and "target_class" not in runner_text
        and '"scientific_verdict_in_live_runner": False' in runner_text
        and '"independent_oracle_used_in_live_runner": False' in runner_text
    )
    checks["runner_no_retry_fallback_regeneration"] = (
        '"automatic_retry": "ABSENT"' in runner_text
        and '"fallback_inside_replaymark": False' in runner_text
        and '"regeneration_inside_replaymark": False' in runner_text
        and "retry" not in runner_text.lower().replace('"automatic_retry": "absent"', "")
    )

    workflow = Path(".github/workflows/replaymark-runtime-gate-s3c1-implementation-conformance.yml").read_text(encoding="utf-8")
    low = workflow.lower()
    checks["conformance_workflow_cannot_execute_live_target_or_queue"] = not any(
        token in low for token in [
            "docker ", "mosquitto_pub", "mosquitto_sub", "--broker mosquitto",
            "workflow_dispatch",
        ]
    )
    checks["no_execution_workflow_or_result_added"] = not any(
        "execution" in path.lower() or "result" in path.lower() for path in changed
    )

    module = _load_validator()
    synthetic = [
        synthetic_cell(replica, n, trial)
        for replica in REPLICAS for n in BATCHES for trial in range(TRIALS)
    ]
    matrix = module.validate_matrix(synthetic)
    checks["validator_accepts_only_full_frozen_synthetic_positive_matrix"] = matrix["verdict"] == "PASS"
    detail["synthetic_matrix_checks"] = matrix["checks"]

    missing = synthetic[:-1]
    checks["validator_rejects_missing_canonical_cell"] = module.validate_matrix(missing)["verdict"] == "FAIL"

    evidence_mut = copy.deepcopy(synthetic[0])
    victim = next(
        row for row in evidence_mut["tasks"]
        if row["arms"]["DIRECT_NATIVE"]["raw_observation"]["events"] == []
    )
    rm_raw = victim["arms"]["REPLAYMARK_NATIVE"]["raw_observation"]
    command = rm_raw["command_publish_mono_ns"]
    rm_raw["events"] = [{
        "event_id": "mutation:pairing",
        "device": rm_raw["expected_device"],
        "on": True,
        "recv_mono_ns": command + 1_000_000,
        "clock_domain": rm_raw["clock_domain"],
    }]
    checks["validator_rejects_taskwise_evidence_mismatch"] = module.validate_cell(evidence_mut)["verdict"] == "FAIL"

    duplicate_mut = copy.deepcopy(synthetic[0])
    duplicate_mut["persistent_collectors"]["ALWAYS_REUSE"]["deliveries"].append(
        copy.deepcopy(duplicate_mut["persistent_collectors"]["ALWAYS_REUSE"]["deliveries"][0])
    )
    checks["validator_rejects_duplicate_queue_delivery"] = module.validate_cell(duplicate_mut)["verdict"] == "FAIL"

    session_mut = copy.deepcopy(synthetic[0])
    session_mut["persistent_collectors"]["DIRECT_NATIVE"]["session_present"] = False
    checks["validator_rejects_missing_persistent_session"] = module.validate_cell(session_mut)["verdict"] == "FAIL"

    generated_mut = copy.deepcopy(synthetic[0])
    exemplar = copy.deepcopy(next(
        event for event in generated_mut["online_role_ledger"]
        if "-dn-" in str(event["topic"]) and str(event["topic"]).endswith("/query")
    ))
    exemplar["seq"] = 99999999
    exemplar["recv_mono_ns"] = int(exemplar["recv_mono_ns"]) + 123
    exemplar["payload_utf8"] = '{"mutation":true}'
    generated_mut["online_role_ledger"].append(exemplar)
    checks["validator_rejects_direct_rm_generated_divergence"] = module.validate_cell(generated_mut)["verdict"] == "FAIL"

    barrier_mut = copy.deepcopy(synthetic[0])
    first_wave_close = barrier_mut["waves"][0]["snapshot_closed_at_mono_ns"]
    bad = next(
        c for c in barrier_mut["application_publish_provenance"]
        if c["task_id"] in barrier_mut["waves"][0]["task_ids"] and c["channel"] != "ACT1"
    )
    bad["publish_mono_ns"] = first_wave_close - 1
    checks["validator_rejects_decision_before_common_snapshot_barrier"] = module.validate_cell(barrier_mut)["verdict"] == "FAIL"

    summary_mut = copy.deepcopy(synthetic[0])
    summary_mut["runner_summary"] = {"verdict": "FAIL", "classification": "fabricated"}
    checks["validator_ignores_runner_summary_fields"] = module.validate_cell(summary_mut)["verdict"] == "PASS"

    implementation_blobs = {
        path: g("rev-parse", f"HEAD:{path}")
        for path in sorted(CHANGED)
    }
    detail["implementation_blobs"] = implementation_blobs

    verdict = "PASS" if all(checks.values()) else "FAIL"
    report = {
        "schema": "replaymark.s3c1-implementation-conformance-verification.v1",
        "head": g("rev-parse", "HEAD"),
        "parent": g("rev-parse", "HEAD^"),
        "protocol_sha256": sha256(protocol_bytes),
        "schedule_sha256": schedule_sha,
        "checks": checks,
        "detail": detail,
        "live_target_executed": False,
        "live_queue_executed": False,
        "target_outcomes_visible": False,
        "scientific_result_file_present": False,
        "next_only_if_pass": "S3-C1 first-complete 60-cell execution workflow may be added as the exact child of this conformance authority.",
        "verdict": verdict,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if verdict == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
