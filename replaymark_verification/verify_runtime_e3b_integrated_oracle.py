from __future__ import annotations

"""Static and differential gate for the independent integrated E3b oracle."""

import argparse
import ast
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from replaymark_oracle.e3b_integrated_runtime_oracle import (
    CONFIRMED,
    DO_NOT_REUSE,
    INVALID,
    NOT_VISIBLE,
    REUSE,
    VALID,
    historical_action,
    integrated_expectation,
    observation_token,
)


def _obs(*, confirmed: bool, task: int = 7) -> dict[str, object]:
    events: list[dict[str, object]] = []
    if confirmed:
        events.append(
            {
                "event_id": "e1",
                "device": f"oracle-{task}-a",
                "on": True,
                "recv_mono_ns": 150,
                "clock_domain": "mono:oracle",
            }
        )
    return {
        "schema": "replaymark.runtime.e3b-observation-record.v1",
        "clock_domain": "mono:oracle",
        "expected_device": f"oracle-{task}-a",
        "command_publish_mono_ns": 100,
        "verify_deadline_mono_ns": 200,
        "closed_at_mono_ns": 200,
        "events": events,
    }


def _action(*, task: int = 7) -> dict[str, object]:
    return {
        "schema": "replaymark.runtime.e3b-historical-action-record.v1",
        "capture_point": "paho.mqtt.Client.publish.pre-send",
        "clock_domain": "mono:oracle",
        "publish_mono_ns": 220,
        "topic": f"agentmark/oracle-{task}-b/command",
        "payload_utf8": '{"on": true}',
        "qos": 1,
        "retain": False,
        "properties": None,
    }


def named_semantics_gate() -> dict[str, object]:
    token0, identity0 = observation_token(_obs(confirmed=False))
    token1, identity1 = observation_token(_obs(confirmed=True))
    assert token0 == NOT_VISIBLE
    assert token1 == CONFIRMED
    assert identity0.task_id == identity1.task_id == 7

    action, action_identity = historical_action(_action())
    assert action == {
        "operation": "ACT2",
        "target_class": "stage2",
        "variant": None,
        "delay_ms": 0,
    }
    assert action_identity.task_id == 7
    assert action_identity.role == "b"

    negative = integrated_expectation(_obs(confirmed=False), _action())
    positive = integrated_expectation(_obs(confirmed=True), _action())
    assert negative.verdict == INVALID
    assert negative.reuse_disposition == DO_NOT_REUSE
    assert positive.verdict == VALID
    assert positive.reuse_disposition == REUSE

    return {
        "negative_token": negative.observation_token,
        "negative_verdict": negative.verdict,
        "negative_reuse": negative.reuse_disposition,
        "positive_token": positive.observation_token,
        "positive_verdict": positive.verdict,
        "positive_reuse": positive.reuse_disposition,
    }


def malformed_and_cross_task_gate() -> dict[str, object]:
    failures: dict[str, bool] = {}

    cross = _action(task=8)
    try:
        integrated_expectation(_obs(task=7, confirmed=False), cross)
    except ValueError:
        failures["cross_task"] = True
    else:
        raise AssertionError("cross-task pair admitted")

    wrong_payload = _action()
    wrong_payload["payload_utf8"] = '{"on":false}'
    try:
        historical_action(wrong_payload)
    except ValueError:
        failures["wrong_payload"] = True
    else:
        raise AssertionError("wrong payload admitted")

    wrong_qos = _action()
    wrong_qos["qos"] = 0
    try:
        historical_action(wrong_qos)
    except ValueError:
        failures["wrong_qos"] = True
    else:
        raise AssertionError("wrong qos admitted")

    noncanonical = _action()
    noncanonical["topic"] = "agentmark/oracle-07-b/command"
    try:
        historical_action(noncanonical)
    except ValueError:
        failures["noncanonical_task_id"] = True
    else:
        raise AssertionError("noncanonical task id admitted")

    duplicate = _obs(confirmed=False)
    duplicate["events"] = [
        {
            "event_id": "dup",
            "device": "oracle-7-a",
            "on": False,
            "recv_mono_ns": 150,
            "clock_domain": "mono:oracle",
        },
        {
            "event_id": "dup",
            "device": "oracle-7-a",
            "on": False,
            "recv_mono_ns": 160,
            "clock_domain": "mono:oracle",
        },
    ]
    try:
        observation_token(duplicate)
    except ValueError:
        failures["duplicate_event_id"] = True
    else:
        raise AssertionError("duplicate event id admitted")

    ambiguous = _obs(confirmed=False)
    ambiguous["events"] = [
        {
            "event_id": "a",
            "device": "oracle-7-a",
            "on": True,
            "recv_mono_ns": 150,
            "clock_domain": "mono:oracle",
        },
        {
            "event_id": "b",
            "device": "oracle-7-a",
            "on": True,
            "recv_mono_ns": 160,
            "clock_domain": "mono:oracle",
        },
    ]
    try:
        observation_token(ambiguous)
    except ValueError:
        failures["ambiguous_multiple_matches"] = True
    else:
        raise AssertionError("multiple matching events admitted")

    cross_clock = _action()
    cross_clock["clock_domain"] = "mono:other"
    try:
        integrated_expectation(_obs(confirmed=False), cross_clock)
    except ValueError:
        failures["cross_clock"] = True
    else:
        raise AssertionError("cross-clock pair admitted")

    return failures


def static_independence_gate() -> dict[str, object]:
    path = ROOT / "replaymark_oracle" / "e3b_integrated_runtime_oracle.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)

    forbidden_prefixes = (
        "replaymark",
        "agentmark",
        "paho",
        "ladder",
        "experiment",
    )
    offenders = sorted(
        module
        for module in imported
        if module.startswith(forbidden_prefixes)
    )
    assert not offenders, offenders
    return {
        "production_imports": 0,
        "forbidden_imports": offenders,
        "allowed_imports": sorted(imported),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    report = {
        "schema": "replaymark.runtime-e3b-integrated-oracle-gate.v1",
        "verdict": "PASS",
        "named_semantics": named_semantics_gate(),
        "malformed_and_cross_task": malformed_and_cross_task_gate(),
        "static_independence": static_independence_gate(),
    }
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
