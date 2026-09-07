from __future__ import annotations

"""Live task-by-task Integrated Frozen Runtime Conformance gate for E3b R1."""

import argparse
from collections import Counter
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import time
import uuid

from experiment import Harness, _sys_delta, percentile
import ladder

from replaymark.runtime_e3b_action import (
    E3B_ACTION_REALIZER_ID,
    E3B_ACTION_REALIZER_SEMANTIC_DIGEST,
    E3B_LADDER_GIT_BLOB_SHA1,
)
from replaymark.runtime_e3b_bridge import (
    E3B_SHADOW_BRIDGE_ID,
    E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST,
    certify_e3b_shadow_reuse,
)
from replaymark.runtime_e3b_correlation import (
    E3B_TASK_CORRELATOR_ID,
    E3B_TASK_CORRELATOR_SEMANTIC_DIGEST,
    E3bTaskCorrelationError,
    correlate_e3b_runtime_pair,
)
from replaymark.runtime_e3b_observation import (
    E3B_OBSERVATION_REALIZER_ID,
    E3B_OBSERVATION_REALIZER_SEMANTIC_DIGEST,
)
from replaymark.runtime_realization import RealizationError
from replaymark_oracle.e3b_integrated_runtime_oracle import (
    CONFIRMED,
    REUSE,
    VALID,
    integrated_expectation,
    sha256_json,
)
from replaymark_shadow import compile_e3b_r1_shadow_contract, run_r1_shadow_condition


PUB = "$SYS/broker/publish/messages/received"
_STABLE_RESULT_FIELDS = (
    "tasks",
    "success_rate",
    "support_violation_fraction",
    "branch_required_fraction",
    "verify_count",
    "semantic_operations",
)


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _stable_result(result: dict[str, object]) -> dict[str, object]:
    return {name: result[name] for name in _STABLE_RESULT_FIELDS}


def _event_count(harness: Harness, prefix: str) -> int:
    with harness.cv:
        return sum(
            len(events)
            for device, events in harness.state_events.items()
            if str(device).startswith(prefix + "-")
        )


def _task_row(*, trial: int, item, contract) -> dict[str, object]:
    raw_observation = item.raw_observation
    raw_action = item.raw_historical_action
    certificate = item.certificate
    pair = certificate.correlated_pair
    semantic = certificate.semantic_certificate
    expectation = integrated_expectation(raw_observation, raw_action)

    obs_raw_digest = sha256_json(raw_observation)
    action_raw_digest = sha256_json(raw_action)
    full_action = pair.historical_action.action.as_dict()
    expected_device_b = str(raw_action["topic"]).split("/")[1]

    direct_adjudication = contract.adjudicate(
        pair.observation.evidence_token,
        pair.historical_action.action,
    )
    direct_reuse = contract.certify_reuse(
        pair.observation.evidence_token,
        pair.historical_action.action,
    )

    checks = {
        "oracle_observation_token_exact": (
            pair.observation.evidence_token == expectation.observation_token
        ),
        "oracle_action_operation_exact": (
            full_action.get("operation") == expectation.action_operation
        ),
        "oracle_action_target_class_exact": (
            full_action.get("target_class") == expectation.action_target_class
        ),
        "oracle_action_variant_exact": (
            full_action.get("variant") is expectation.action_variant
        ),
        "oracle_action_delay_exact": (
            full_action.get("delay_ms") == expectation.action_delay_ms
        ),
        "oracle_task_prefix_exact": (
            pair.correlation.task_prefix == expectation.task_prefix
            and full_action.get("task_prefix") == expectation.task_prefix
        ),
        "oracle_task_id_exact": (
            pair.correlation.task_id == expectation.task_id
            and full_action.get("task_id") == expectation.task_id
            and item.task_id == expectation.task_id
        ),
        "oracle_role_pair_exact": (
            pair.correlation.observation_role == expectation.observation_role == "a"
            and pair.correlation.action_role == expectation.action_role == "b"
        ),
        "oracle_verdict_exact": (
            semantic.adjudication.verdict.value == expectation.verdict
        ),
        "oracle_reuse_disposition_exact": (
            semantic.reuse_decision.disposition.value == expectation.reuse_disposition
        ),
        "observation_raw_digest_bound": (
            pair.observation.provenance.raw_record_digest == obs_raw_digest
            and pair.correlation.observation_raw_digest == obs_raw_digest
        ),
        "action_raw_digest_bound": (
            pair.historical_action.provenance.raw_record_digest == action_raw_digest
            and pair.correlation.action_raw_digest == action_raw_digest
        ),
        "observation_realizer_authority_bound": (
            pair.observation.provenance.realizer_id == E3B_OBSERVATION_REALIZER_ID
            and pair.observation.provenance.realizer_semantic_digest
            == E3B_OBSERVATION_REALIZER_SEMANTIC_DIGEST
        ),
        "action_realizer_authority_bound": (
            pair.historical_action.provenance.realizer_id == E3B_ACTION_REALIZER_ID
            and pair.historical_action.provenance.realizer_semantic_digest
            == E3B_ACTION_REALIZER_SEMANTIC_DIGEST
        ),
        "correlator_authority_bound": (
            pair.correlation.correlator_id == E3B_TASK_CORRELATOR_ID
            and pair.correlation.correlator_semantic_digest
            == E3B_TASK_CORRELATOR_SEMANTIC_DIGEST
        ),
        "bridge_authority_bound": (
            certificate.bridge_id == E3B_SHADOW_BRIDGE_ID
            and certificate.bridge_semantic_digest == E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST
        ),
        "correlation_binds_realized_observation": (
            pair.correlation.observation_fingerprint == pair.observation.fingerprint()
        ),
        "correlation_binds_realized_action": (
            pair.correlation.historical_action_fingerprint
            == pair.historical_action.fingerprint()
        ),
        "correlation_binds_raw_timestamps": (
            pair.correlation.observation_command_publish_mono_ns
            == raw_observation["command_publish_mono_ns"]
            and pair.correlation.observation_boundary_timestamp_ns
            == raw_observation["verify_deadline_mono_ns"]
            == pair.observation.boundary_timestamp_ns
            and pair.correlation.action_publish_mono_ns == raw_action["publish_mono_ns"]
        ),
        "clock_domain_end_to_end_exact": (
            raw_observation["clock_domain"]
            == raw_action["clock_domain"]
            == pair.observation.clock_domain
            == pair.correlation.clock_domain
        ),
        "concrete_target_exact": full_action.get("concrete_target") == expected_device_b,
        "mqtt_qos_exact": full_action.get("mqtt_qos") == 1,
        "mqtt_retain_exact": full_action.get("mqtt_retain") is False,
        "semantic_certificate_binds_pair": (
            semantic.observation.fingerprint() == pair.observation.fingerprint()
            and semantic.historical_action.fingerprint()
            == pair.historical_action.fingerprint()
        ),
        "contract_fingerprint_end_to_end_exact": (
            certificate.contract_fingerprint
            == semantic.contract_fingerprint
            == contract.fingerprint()
        ),
        "claim_fingerprint_end_to_end_exact": (
            certificate.claim_fingerprint
            == semantic.claim_fingerprint
            == contract.claim_fingerprint
        ),
        "bridge_adjudication_exact_frozen_contract_bytes": (
            semantic.adjudication.canonical_bytes()
            == direct_adjudication.canonical_bytes()
        ),
        "bridge_rstar_exact_frozen_contract_bytes": (
            semantic.reuse_decision.canonical_bytes() == direct_reuse.canonical_bytes()
        ),
        "semantic_projection_is_operation_act2": (
            semantic.adjudication.projected_action.as_dict() == {"operation": "ACT2"}
            and semantic.reuse_decision.projected_action.as_dict()
            == {"operation": "ACT2"}
        ),
    }

    row_core = {
        "trial": trial,
        "task_id": item.task_id,
        "task_prefix": expectation.task_prefix,
        "independent_expectation": expectation.canonical_record(),
        "raw": {
            "observation_sha256": obs_raw_digest,
            "historical_action_sha256": action_raw_digest,
        },
        "stage_fingerprints": {
            "realized_observation": pair.observation.fingerprint(),
            "realized_historical_action": pair.historical_action.fingerprint(),
            "same_task_correlation": pair.correlation.fingerprint(),
            "runtime_semantic_certificate": semantic.fingerprint(),
            "e3b_chained_certificate": certificate.fingerprint(),
        },
        "actual": {
            "evidence_token": pair.observation.evidence_token,
            "verdict": semantic.adjudication.verdict.value,
            "reuse_disposition": semantic.reuse_decision.disposition.value,
        },
        "checks": checks,
    }
    return {
        **row_core,
        "row_sha256": _sha256(row_core),
        "pass": all(checks.values()),
    }


def _falsification_gate(first, second, contract) -> dict[str, object]:
    try:
        integrated_expectation(first.raw_observation, second.raw_historical_action)
    except ValueError:
        oracle_cross_task_rejected = True
    else:
        raise AssertionError("independent oracle admitted a cross-task pair")

    try:
        correlate_e3b_runtime_pair(first.raw_observation, second.raw_historical_action)
    except E3bTaskCorrelationError:
        production_cross_task_rejected = True
    else:
        raise AssertionError("production correlator admitted a cross-task pair")

    bad_action = dict(first.raw_historical_action)
    bad_action["payload_utf8"] = '{"on":false}'
    try:
        integrated_expectation(first.raw_observation, bad_action)
    except ValueError:
        oracle_payload_mutation_rejected = True
    else:
        raise AssertionError("independent oracle admitted wrong payload")
    try:
        correlate_e3b_runtime_pair(first.raw_observation, bad_action)
    except RealizationError:
        production_payload_mutation_rejected = True
    else:
        raise AssertionError("production realizer admitted wrong payload")

    try:
        replace(first.certificate, correlated_pair=second.certificate.correlated_pair)
    except ValueError:
        detached_certificate_rejected = True
    else:
        raise AssertionError("detached semantic certificate was accepted")

    confirmed_raw = dict(first.raw_observation)
    confirmed_events = list(first.raw_observation["events"])
    command = int(first.raw_observation["command_publish_mono_ns"])
    deadline = int(first.raw_observation["verify_deadline_mono_ns"])
    confirmed_events.append(
        {
            "event_id": "integrated-falsification-confirmed",
            "device": first.raw_observation["expected_device"],
            "on": True,
            "recv_mono_ns": command + max(1, (deadline - command) // 2),
            "clock_domain": first.raw_observation["clock_domain"],
        }
    )
    confirmed_raw["events"] = confirmed_events
    oracle_confirmed = integrated_expectation(confirmed_raw, first.raw_historical_action)
    if (
        oracle_confirmed.observation_token != CONFIRMED
        or oracle_confirmed.verdict != VALID
        or oracle_confirmed.reuse_disposition != REUSE
    ):
        raise AssertionError("literal oracle did not flip on positive evidence")
    confirmed_pair = correlate_e3b_runtime_pair(
        confirmed_raw,
        first.raw_historical_action,
    )
    confirmed_certificate = certify_e3b_shadow_reuse(contract, confirmed_pair)
    if (
        confirmed_certificate.semantic_certificate.adjudication.verdict.value != VALID
        or confirmed_certificate.semantic_certificate.reuse_decision.disposition.value
        != REUSE
    ):
        raise AssertionError("production chain did not flip on positive evidence")

    return {
        "oracle_cross_task_rejected": oracle_cross_task_rejected,
        "production_cross_task_rejected": production_cross_task_rejected,
        "oracle_payload_mutation_rejected": oracle_payload_mutation_rejected,
        "production_payload_mutation_rejected": production_payload_mutation_rejected,
        "detached_certificate_rejected": detached_certificate_rejected,
        "positive_evidence_flips_oracle_to_valid_reuse": True,
        "positive_evidence_flips_production_to_valid_reuse": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--broker", default="mosquitto")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--tasks", type=int, default=64)
    parser.add_argument("--wave-size", type=int, default=16)
    parser.add_argument("--wave-period-ms", type=float, default=300)
    parser.add_argument("--verify-floor-ms", type=float, default=100)
    parser.add_argument("--source-guard-ms", type=float, default=20)
    parser.add_argument("--changed-delay-floor-ms", type=float, default=150)
    parser.add_argument("--target-margin-ms", type=float, default=50)
    parser.add_argument("--post-completion-gap-ms", type=float, default=20)
    parser.add_argument("--task-timeout-ms", type=int, default=1200)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument(
        "--out",
        default="/results/e3b_integrated_frozen_runtime_conformance.json",
    )
    args = parser.parse_args()
    if args.tasks % args.wave_size:
        raise ValueError("tasks must be divisible by wave size")
    if args.tasks < 2:
        raise ValueError("at least two tasks are required for cross-task falsification")

    contract = compile_e3b_r1_shadow_contract()
    harness = Harness(args.broker, args.port)
    all_rows: list[dict[str, object]] = []
    trials: list[dict[str, object]] = []
    first_material = None
    second_material = None
    try:
        version = harness.broker_version()
        harness.set_state_delay(0)
        source_prefix = f"ifrc-source-{uuid.uuid4().hex[:6]}"
        traces = ladder.offers(
            args.tasks,
            args.wave_size,
            args.wave_period_ms,
            lambda i, offer: ladder.source_task(
                harness,
                i,
                source_prefix,
                offer,
                args.post_completion_gap_ms,
                args.task_timeout_ms,
            ),
        )
        source_first = [float(row["first_completion_offset_ms"]) for row in traces]
        source_max = max(source_first)
        verify_ms = max(
            float(args.verify_floor_ms),
            float(math.ceil(source_max + args.source_guard_ms)),
        )
        target_delay_ms = max(
            float(args.changed_delay_floor_ms),
            verify_ms + args.target_margin_ms,
        )
        if target_delay_ms >= args.task_timeout_ms:
            raise RuntimeError("calibrated target delay collides with task timeout")

        for trial in range(args.trials):
            prefix = f"ifrc-{trial:02d}"
            harness.set_state_delay(target_delay_ms)
            before = harness.fresh_sys_snapshot()
            shadow = run_r1_shadow_condition(
                harness,
                traces,
                args.wave_size,
                args.wave_period_ms,
                prefix,
                verify_ms,
                args.post_completion_gap_ms,
                args.task_timeout_ms,
                contract,
            )
            time.sleep(target_delay_ms / 1000.0 + 0.05)
            after = harness.fresh_sys_snapshot()
            sys_delta = _sys_delta(before, after)
            event_count = _event_count(harness, prefix)

            materials = shadow.task_material
            if len(materials) != args.tasks:
                raise AssertionError("shadow run did not yield one material per task")
            if [item.task_id for item in materials] != list(range(args.tasks)):
                raise AssertionError("task materials are not canonical task-id order")
            if shadow.captured_publish_count != 2 * args.tasks:
                raise AssertionError("shadow capture count differs from two commands per task")

            expected_publishes = float(4 * args.tasks)
            publish_count = float(sys_delta.get(PUB, float("nan")))
            if publish_count != expected_publishes:
                raise AssertionError(
                    f"integrated shadow run changed broker workload: "
                    f"{publish_count} != {expected_publishes}"
                )
            if event_count != 2 * args.tasks:
                raise AssertionError(
                    f"integrated shadow run state-event count changed: "
                    f"{event_count} != {2 * args.tasks}"
                )

            trial_rows = [
                _task_row(trial=trial, item=item, contract=contract)
                for item in materials
            ]
            if not all(row["pass"] for row in trial_rows):
                failed = [row for row in trial_rows if not row["pass"]]
                raise AssertionError(
                    json.dumps({"failed_rows": failed[:3]}, sort_keys=True)
                )
            all_rows.extend(trial_rows)
            if first_material is None:
                first_material, second_material = materials[0], materials[1]

            trial_digest_input = {
                "trial": trial,
                "row_sha256": [row["row_sha256"] for row in trial_rows],
            }
            trials.append(
                {
                    "trial": trial,
                    "task_count": len(materials),
                    "legacy_stable_result": _stable_result(shadow.legacy_result),
                    "captured_publish_count": shadow.captured_publish_count,
                    "broker_publish_messages_received": publish_count,
                    "state_event_count": event_count,
                    "verdict_counts": dict(
                        Counter(row["actual"]["verdict"] for row in trial_rows)
                    ),
                    "reuse_disposition_counts": dict(
                        Counter(
                            row["actual"]["reuse_disposition"] for row in trial_rows
                        )
                    ),
                    "token_counts": dict(
                        Counter(row["actual"]["evidence_token"] for row in trial_rows)
                    ),
                    "trial_matrix_sha256": _sha256(trial_digest_input),
                }
            )
    finally:
        harness.close()

    if first_material is None or second_material is None:
        raise AssertionError("live conformance produced no task material")
    falsification = _falsification_gate(first_material, second_material, contract)

    if len(all_rows) != args.tasks * args.trials:
        raise AssertionError("integrated matrix coverage is incomplete")
    if not all(row["pass"] for row in all_rows):
        raise AssertionError("integrated matrix contains a nonconforming row")

    expected_checks = len(all_rows[0]["checks"])
    if any(len(row["checks"]) != expected_checks for row in all_rows):
        raise AssertionError("task rows do not share one frozen check schema")

    matrix_manifest = {
        "schema": "replaymark.runtime-e3b-integrated-conformance-matrix.v1",
        "contract_fingerprint": contract.fingerprint(),
        "claim_fingerprint": contract.claim_fingerprint,
        "frozen_ladder_git_blob_sha1": E3B_LADDER_GIT_BLOB_SHA1,
        "observation_realizer_semantic_digest": E3B_OBSERVATION_REALIZER_SEMANTIC_DIGEST,
        "action_realizer_semantic_digest": E3B_ACTION_REALIZER_SEMANTIC_DIGEST,
        "correlator_semantic_digest": E3B_TASK_CORRELATOR_SEMANTIC_DIGEST,
        "bridge_semantic_digest": E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST,
        "row_sha256": [row["row_sha256"] for row in all_rows],
    }
    matrix_sha256 = _sha256(matrix_manifest)
    verdicts = Counter(row["actual"]["verdict"] for row in all_rows)
    dispositions = Counter(row["actual"]["reuse_disposition"] for row in all_rows)
    tokens = Counter(row["actual"]["evidence_token"] for row in all_rows)

    report = {
        "schema": "replaymark.runtime-e3b-integrated-frozen-conformance.v1",
        "verdict": "PASS",
        "broker_version_sys": version,
        "scope": {
            "execution_policy": "NOT_IMPLEMENTED",
            "fallback_regeneration": "NOT_IMPLEMENTED",
            "latency_promotion": "NOT_IMPLEMENTED",
            "matrix_is_task_by_task": True,
            "independent_literal_oracle_has_no_production_imports": True,
        },
        "parameters": {
            **vars(args),
            "calibrated_verify_ms": verify_ms,
            "calibrated_target_delay_ms": target_delay_ms,
            "source_first_completion_p99_ms": percentile(source_first, 99),
            "source_first_completion_max_ms": source_max,
        },
        "frozen_authorities": {
            "contract_fingerprint": contract.fingerprint(),
            "claim_fingerprint": contract.claim_fingerprint,
            "ladder_git_blob_sha1": E3B_LADDER_GIT_BLOB_SHA1,
            "observation_realizer_id": E3B_OBSERVATION_REALIZER_ID,
            "observation_realizer_semantic_digest": E3B_OBSERVATION_REALIZER_SEMANTIC_DIGEST,
            "action_realizer_id": E3B_ACTION_REALIZER_ID,
            "action_realizer_semantic_digest": E3B_ACTION_REALIZER_SEMANTIC_DIGEST,
            "correlator_id": E3B_TASK_CORRELATOR_ID,
            "correlator_semantic_digest": E3B_TASK_CORRELATOR_SEMANTIC_DIGEST,
            "bridge_id": E3B_SHADOW_BRIDGE_ID,
            "bridge_semantic_digest": E3B_SHADOW_BRIDGE_SEMANTIC_DIGEST,
        },
        "coverage": {
            "trials": args.trials,
            "tasks_per_trial": args.tasks,
            "task_rows": len(all_rows),
            "checks_per_task_row": expected_checks,
            "total_boolean_conformance_checks": len(all_rows) * expected_checks,
            "all_task_rows_pass": True,
        },
        "aggregate": {
            "verdict_counts": dict(verdicts),
            "reuse_disposition_counts": dict(dispositions),
            "token_counts": dict(tokens),
        },
        "trials": trials,
        "falsification": falsification,
        "matrix_manifest": matrix_manifest,
        "matrix_sha256": matrix_sha256,
        "rows": all_rows,
        "promotion_pass": True,
    }
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "verdict": "PASS",
                "broker": version,
                "task_rows": len(all_rows),
                "checks_per_task_row": expected_checks,
                "matrix_sha256": matrix_sha256,
                "contract_fingerprint": contract.fingerprint(),
                "verdict_counts": dict(verdicts),
                "reuse_disposition_counts": dict(dispositions),
                "promotion_pass": True,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
