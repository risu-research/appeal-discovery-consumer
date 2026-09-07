from __future__ import annotations

import argparse
import ast
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from replaymark.runtime_e3b_action import (
    E3B_ACTION_CAPTURE_POINT,
    E3B_FROZEN_ACT2_PAYLOAD_UTF8,
    E3B_RAW_ACTION_SCHEMA,
    realize_e3b_historical_action,
)
from replaymark.runtime_e3b_correlation import (
    E3B_TASK_CORRELATOR_ID,
    E3B_TASK_CORRELATOR_SEMANTIC_DIGEST,
    E3bCorrelatedRuntimePair,
    E3bTaskCorrelationError,
    E3bTaskCorrelationFailureCode,
    correlate_e3b_runtime_pair,
    e3b_task_correlator_rule_record,
)
from replaymark.runtime_e3b_observation import (
    E3B_RAW_OBSERVATION_SCHEMA,
    realize_e3b_observation,
)
from replaymark_oracle.e3b_correlation_oracle import definition_correlate_e3b_task


SCHEMA = "replaymark.runtime-e3b-same-task-gate.v1"


def _obs(
    *,
    prefix: str = "t0-R1_timing",
    task_id_text: str = "7",
    role: str = "a",
    domain: str = "mono:e3b",
    command: int = 100,
    deadline: int = 200,
    closed_at: int = 220,
    confirmed: bool = True,
) -> dict[str, object]:
    device = f"{prefix}-{task_id_text}-{role}"
    events: list[dict[str, object]] = []
    if confirmed:
        events.append(
            {
                "event_id": "state-on",
                "device": device,
                "on": True,
                "recv_mono_ns": 150,
                "clock_domain": domain,
            }
        )
    return {
        "schema": E3B_RAW_OBSERVATION_SCHEMA,
        "clock_domain": domain,
        "expected_device": device,
        "command_publish_mono_ns": command,
        "verify_deadline_mono_ns": deadline,
        "closed_at_mono_ns": closed_at,
        "events": events,
    }


def _act(
    *,
    prefix: str = "t0-R1_timing",
    task_id_text: str = "7",
    domain: str = "mono:e3b",
    publish: int = 210,
) -> dict[str, object]:
    return {
        "schema": E3B_RAW_ACTION_SCHEMA,
        "capture_point": E3B_ACTION_CAPTURE_POINT,
        "clock_domain": domain,
        "publish_mono_ns": publish,
        "topic": f"agentmark/{prefix}-{task_id_text}-b/command",
        "payload_utf8": E3B_FROZEN_ACT2_PAYLOAD_UTF8,
        "qos": 1,
        "retain": False,
        "properties": None,
    }


def _prod(obs: object, act: object) -> tuple[bool, str | None, str | None, int | None]:
    try:
        pair = correlate_e3b_runtime_pair(obs, act)
    except E3bTaskCorrelationError as exc:
        return False, exc.failure.code.value, None, None
    return (
        True,
        None,
        pair.correlation.task_prefix,
        pair.correlation.task_id,
    )


def named_gate() -> dict[str, object]:
    confirmed = correlate_e3b_runtime_pair(_obs(), _act())
    assert isinstance(confirmed, E3bCorrelatedRuntimePair)
    assert confirmed.correlation.task_prefix == "t0-R1_timing"
    assert confirmed.correlation.task_id == 7
    assert confirmed.correlation.observation_role == "a"
    assert confirmed.correlation.action_role == "b"
    assert confirmed.correlation.clock_domain == "mono:e3b"
    assert confirmed.correlation.observation_fingerprint == confirmed.observation.fingerprint()
    assert (
        confirmed.correlation.historical_action_fingerprint
        == confirmed.historical_action.fingerprint()
    )
    assert confirmed.observation == realize_e3b_observation(_obs())
    assert confirmed.historical_action == realize_e3b_historical_action(_act())

    absent = correlate_e3b_runtime_pair(_obs(confirmed=False), _act(publish=250))
    assert absent.correlation.task_prefix == "t0-R1_timing"
    assert absent.correlation.task_id == 7

    failures = {
        "prefix_cross_pair": (
            _obs(prefix="t0-R1_timing"),
            _act(prefix="t1-R1_timing"),
            E3bTaskCorrelationFailureCode.TASK_MISMATCH,
        ),
        "task_cross_pair": (
            _obs(task_id_text="7"),
            _act(task_id_text="8"),
            E3bTaskCorrelationFailureCode.TASK_MISMATCH,
        ),
        "wrong_observation_role": (
            _obs(role="b"),
            _act(),
            E3bTaskCorrelationFailureCode.ROLE_MISMATCH,
        ),
        "noncanonical_observation_task_id": (
            _obs(task_id_text="07"),
            _act(task_id_text="7"),
            E3bTaskCorrelationFailureCode.MALFORMED_IDENTITY,
        ),
        "cross_clock_pair": (
            _obs(domain="mono:a"),
            _act(domain="mono:b"),
            E3bTaskCorrelationFailureCode.CLOCK_DOMAIN_MISMATCH,
        ),
        "stage2_precedes_stage1": (
            _obs(command=100),
            _act(publish=99),
            E3bTaskCorrelationFailureCode.TEMPORAL_INCONSISTENCY,
        ),
    }
    observed: dict[str, str] = {}
    for name, (obs, act, expected) in failures.items():
        # These cases are intentionally chosen so both individual realizers
        # succeed; only the new pairwise relation must reject them.
        realize_e3b_observation(obs)
        realize_e3b_historical_action(act)
        try:
            correlate_e3b_runtime_pair(obs, act)
        except E3bTaskCorrelationError as exc:
            assert exc.failure.code is expected
            assert "verdict" not in exc.failure.canonical_record()
            observed[name] = exc.failure.code.value
        else:
            raise AssertionError(f"{name} should fail same-task correlation")

    obs = _obs()
    a1 = correlate_e3b_runtime_pair(obs, _act(publish=210))
    a2 = correlate_e3b_runtime_pair(obs, _act(publish=211))
    assert a1.correlation.task_prefix == a2.correlation.task_prefix
    assert a1.correlation.task_id == a2.correlation.task_id
    assert a1.correlation.historical_action_fingerprint != a2.correlation.historical_action_fingerprint
    assert a1.correlation.fingerprint() != a2.correlation.fingerprint()

    rule = e3b_task_correlator_rule_record()
    assert rule["identity"]["caller_supplied_same_task_flag"] == "forbidden"
    assert rule["identity"]["temporal_proximity_as_identity"] == "forbidden"
    assert rule["semantic_boundary"]["contract_call"] is False
    assert rule["semantic_boundary"]["execution_side_effect"] is False

    return {
        "canonical_same_task_pair": True,
        "negative_evidence_pair": True,
        "cross_pair_rejected": True,
        "role_pair_enforced": True,
        "canonical_task_id_enforced": True,
        "clock_domain_bound": True,
        "causal_order_bound": True,
        "proof_content_addressed_to_realized_values": True,
        "failure_codes": observed,
    }


def differential_gate() -> dict[str, object]:
    cases: list[tuple[dict[str, object], dict[str, object]]] = []
    prefixes = ("t0-R1_timing", "t5-R0_rigid", "x-y-z")
    obs_tasks = ("0", "1", "7", "07")
    act_tasks = ("0", "1", "7")
    obs_roles = ("a", "b")
    domains = ("mono:a", "mono:b")
    publishes = (99, 100, 210)

    for prefix in prefixes:
        for obs_task in obs_tasks:
            for act_task in act_tasks:
                for role in obs_roles:
                    for obs_domain in domains:
                        for act_domain in domains:
                            for publish in publishes:
                                obs = _obs(
                                    prefix=prefix,
                                    task_id_text=obs_task,
                                    role=role,
                                    domain=obs_domain,
                                )
                                act = _act(
                                    prefix=prefix,
                                    task_id_text=act_task,
                                    domain=act_domain,
                                    publish=publish,
                                )
                                # Observation realization admits these device labels;
                                # action realization is independently frozen and valid.
                                realize_e3b_observation(obs)
                                realize_e3b_historical_action(act)
                                cases.append((obs, act))

    # Add valid individual realizations that differ only by prefix.
    cases.extend(
        [
            (_obs(prefix="left", task_id_text="1"), _act(prefix="right", task_id_text="1")),
            (_obs(prefix="left", task_id_text="1"), _act(prefix="left", task_id_text="2")),
        ]
    )

    counts: Counter[str] = Counter()
    successful = 0
    for obs, act in cases:
        prod = _prod(obs, act)
        oracle_value = definition_correlate_e3b_task(obs, act)
        oracle = (
            oracle_value.ok,
            oracle_value.error_code,
            oracle_value.task_prefix,
            oracle_value.task_id,
        )
        assert prod == oracle, (obs, act, prod, oracle)
        if prod[0]:
            successful += 1
        else:
            assert prod[1] is not None
            counts[prod[1]] += 1

    return {
        "cases": len(cases),
        "successful": successful,
        "failure_counts": dict(sorted(counts.items())),
        "production_matches_independent_literal_oracle": True,
    }


def noninterference_gate() -> dict[str, object]:
    path = ROOT / "replaymark" / "runtime_e3b_correlation.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported.add(module)

    forbidden_suffixes = (
        "compiled_contract",
        "adjudicator",
        "rstar",
        "agentmark_e3b_lab.e3_mqtt.app.ladder",
        "paho.mqtt",
    )
    assert not any(
        module.endswith(suffix)
        for module in imported
        for suffix in forbidden_suffixes
    ), sorted(imported)

    return {
        "no_compiled_contract_import": True,
        "no_adjudicator_or_rstar_import": True,
        "no_e3b_execution_harness_import": True,
        "no_mqtt_client_import": True,
    }


def run() -> dict[str, object]:
    named = named_gate()
    differential = differential_gate()
    noninterference = noninterference_gate()
    return {
        "schema": SCHEMA,
        "verdict": "PASS",
        "correlator_id": E3B_TASK_CORRELATOR_ID,
        "correlator_semantic_digest": E3B_TASK_CORRELATOR_SEMANTIC_DIGEST,
        "named": named,
        "differential": differential,
        "noninterference": noninterference,
        "runtime_reuse_bridge": "NOT_IMPLEMENTED",
        "execution_policy": "NOT_IMPLEMENTED",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    args = parser.parse_args()
    report = run()
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
