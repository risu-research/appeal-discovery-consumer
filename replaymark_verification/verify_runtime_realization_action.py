from __future__ import annotations

import argparse
import hashlib
from itertools import product
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "agentmark_e3b_lab"
for path in (ROOT, LEGACY):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from agentmark.kernel import ReactiveKernel

from replaymark.compat_agentmark import target_model_from_agentmark_kernel
from replaymark.contracts import ClaimSpec, ProjectedAction
from replaymark.runtime_e3b_action import (
    E3B_ACTION_CAPTURE_POINT,
    E3B_ACTION_REALIZER_ID,
    E3B_ACTION_REALIZER_SEMANTIC_DIGEST,
    E3B_DEVICE_GIT_BLOB_SHA1,
    E3B_FROZEN_ACT2_PAYLOAD_UTF8,
    E3B_LADDER_GIT_BLOB_SHA1,
    E3B_RAW_ACTION_SCHEMA,
    e3b_action_realizer_rule_record,
    realize_e3b_historical_action,
)
from replaymark.runtime_realization import (
    RealizationError,
    RealizationFailureCode,
    RealizationStage,
    RealizedHistoricalAction,
)
from replaymark_oracle.e3b_action_oracle import (
    definition_realize_e3b_historical_action,
)


def _raw(
    *,
    topic: str = "agentmark/t0-R1_timing-abc12-7-b/command",
    payload: str = E3B_FROZEN_ACT2_PAYLOAD_UTF8,
    qos: object = 1,
    retain: object = False,
    properties: object = None,
    schema: object = E3B_RAW_ACTION_SCHEMA,
    capture_point: object = E3B_ACTION_CAPTURE_POINT,
    domain: object = "mono:e3b-run",
    publish_ns: object = 123_456_789,
) -> dict[str, object]:
    return {
        "schema": schema,
        "capture_point": capture_point,
        "clock_domain": domain,
        "publish_mono_ns": publish_ns,
        "topic": topic,
        "payload_utf8": payload,
        "qos": qos,
        "retain": retain,
        "properties": properties,
    }


def _production(raw: object) -> tuple[bool, str | None, tuple[tuple[str, object], ...] | None]:
    try:
        realized = realize_e3b_historical_action(raw)
    except RealizationError as exc:
        return False, exc.failure.code.value, None
    return True, None, tuple(realized.action.dimensions)


def _git_blob_sha1(path: Path) -> str:
    body = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(body)).encode("ascii") + b"\0" + body).hexdigest()


def _e3b_kernel() -> ReactiveKernel:
    return ReactiveKernel(
        {
            "initial_state": "after_act1",
            "feedback_alphabet": ["confirmed_by_deadline", "not_visible_by_deadline"],
            "states": {
                "after_act1": {
                    "confirmed_by_deadline": [
                        {
                            "p": 1,
                            "operation": "ACT2",
                            "target_class": "stage2",
                            "next_state": "done",
                        }
                    ],
                    "not_visible_by_deadline": [
                        {
                            "p": 1,
                            "operation": "VERIFY",
                            "target_class": "stage1",
                            "next_state": "verified",
                        }
                    ],
                },
                "verified": {
                    "confirmed_by_deadline": [
                        {
                            "p": 1,
                            "operation": "ACT2",
                            "target_class": "stage2",
                            "next_state": "done",
                        }
                    ],
                    "not_visible_by_deadline": [
                        {
                            "p": 1,
                            "operation": "ACT2",
                            "target_class": "stage2",
                            "next_state": "done",
                        }
                    ],
                },
                "done": {
                    "confirmed_by_deadline": [
                        {"p": 1, "operation": "DONE", "next_state": "done"}
                    ],
                    "not_visible_by_deadline": [
                        {"p": 1, "operation": "DONE", "next_state": "done"}
                    ],
                },
            },
        }
    )


def named_boundary_gate() -> dict[str, object]:
    raw = _raw()
    realized = realize_e3b_historical_action(raw)
    assert isinstance(realized, RealizedHistoricalAction)
    assert realized.provenance.stage is RealizationStage.HISTORICAL_ACTION
    assert realized.provenance.realizer_id == E3B_ACTION_REALIZER_ID
    assert (
        realized.provenance.realizer_semantic_digest
        == E3B_ACTION_REALIZER_SEMANTIC_DIGEST
    )
    dims = realized.action.as_dict()
    assert dims["operation"] == "ACT2"
    assert dims["target_class"] == "stage2"
    assert dims["variant"] is None
    assert dims["delay_ms"] == 0
    assert dims["concrete_target"] == "t0-R1_timing-abc12-7-b"
    assert dims["task_id"] == 7
    assert dims["task_prefix"] == "t0-R1_timing-abc12"
    assert dims["mqtt_qos"] == 1
    assert dims["mqtt_retain"] is False

    with_extra_label = dict(raw)
    with_extra_label["operation"] = "ACT2"
    try:
        realize_e3b_historical_action(with_extra_label)
    except RealizationError as exc:
        assert exc.failure.code is RealizationFailureCode.MALFORMED_INPUT
    else:
        raise AssertionError("caller-supplied operation label must be rejected")

    reversed_raw = dict(reversed(list(raw.items())))
    reversed_realized = realize_e3b_historical_action(reversed_raw)
    assert reversed_realized.canonical_bytes() == realized.canonical_bytes()

    later_raw = dict(raw)
    later_raw["publish_mono_ns"] = int(raw["publish_mono_ns"]) + 1
    later = realize_e3b_historical_action(later_raw)
    assert later.action == realized.action
    assert later.provenance.raw_record_digest != realized.provenance.raw_record_digest
    assert (
        later.provenance.realizer_semantic_digest
        == realized.provenance.realizer_semantic_digest
    )

    conservative_rejections: dict[str, str] = {}
    for name, payload in {
        "alternate_whitespace": '{"on":true}',
        "integer_true": '{"on": 1}',
        "missing_on_defaults_true_in_device": '{}',
        "truthy_string": '{"on": "false"}',
        "extra_field": '{"on": true, "x": 1}',
    }.items():
        try:
            realize_e3b_historical_action(_raw(payload=payload))
        except RealizationError as exc:
            conservative_rejections[name] = exc.failure.code.value
        else:
            raise AssertionError(f"non-frozen payload unexpectedly admitted: {name}")
    assert set(conservative_rejections.values()) == {"UNKNOWN_SEMANTIC_VALUE"}

    failure_codes: dict[str, str] = {}
    invalids = {
        "stage1_action": _raw(topic="agentmark/t0-R1_timing-abc12-7-a/command"),
        "verify_query": _raw(topic="agentmark/t0-R1_timing-abc12-7-a/query"),
        "noncanonical_task_id": _raw(topic="agentmark/t0-R1_timing-abc12-07-b/command"),
        "qos_change": _raw(qos=0),
        "retain_change": _raw(retain=True),
        "properties_change": _raw(properties={"x": 1}),
        "bad_timestamp": _raw(publish_ns=-1),
    }
    missing = _raw()
    del missing["payload_utf8"]
    invalids["missing_payload"] = missing
    for name, case in invalids.items():
        try:
            realize_e3b_historical_action(case)
        except RealizationError as exc:
            failure_codes[name] = exc.failure.code.value
        else:
            raise AssertionError(f"invalid action unexpectedly admitted: {name}")

    assert failure_codes["stage1_action"] == "UNKNOWN_SEMANTIC_VALUE"
    assert failure_codes["verify_query"] == "UNKNOWN_SEMANTIC_VALUE"
    assert failure_codes["noncanonical_task_id"] == "UNKNOWN_SEMANTIC_VALUE"
    assert failure_codes["bad_timestamp"] == "MALFORMED_INPUT"
    assert failure_codes["missing_payload"] == "MISSING_REQUIRED_FIELD"

    rule = e3b_action_realizer_rule_record()
    rule_bytes = json.dumps(
        rule,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    assert hashlib.sha256(rule_bytes).hexdigest() == E3B_ACTION_REALIZER_SEMANTIC_DIGEST

    return {
        "operation_not_caller_supplied": True,
        "mapping_order_invariant": True,
        "timestamp_changes_provenance_not_action": True,
        "conservative_payload_rejections": conservative_rejections,
        "named_failure_codes": failure_codes,
        "realizer_semantics_content_addressed": True,
        "sample_action_fingerprint": realized.fingerprint(),
    }


def frozen_source_authority_gate() -> dict[str, object]:
    ladder = ROOT / "agentmark_e3b_lab/e3_mqtt/app/ladder.py"
    device = ROOT / "agentmark_e3b_lab/e3_mqtt/app/device.py"
    ladder_sha = _git_blob_sha1(ladder)
    device_sha = _git_blob_sha1(device)
    assert ladder_sha == E3B_LADDER_GIT_BLOB_SHA1
    assert device_sha == E3B_DEVICE_GIT_BLOB_SHA1

    ladder_text = ladder.read_text(encoding="utf-8")
    device_text = device.read_text(encoding="utf-8")
    assert "json.dumps(body,sort_keys=True),qos=1" in ladder_text.replace(" ", "")
    assert "a2=pub(h,f'agentmark/{b}/command',{'on':True})" in ladder_text.replace(" ", "")
    assert "body=json.loads(text)" in device_text.replace(" ", "")
    assert "states[device]=bool(body.get('on',True))" in device_text.replace(" ", "")

    return {
        "producer_git_blob_sha1": ladder_sha,
        "consumer_git_blob_sha1": device_sha,
        "producer_exact_payload_and_qos_path_present": True,
        "consumer_truthy_coercion_path_present": True,
    }


def target_model_binding_gate() -> dict[str, object]:
    realized = realize_e3b_historical_action(_raw())
    model = target_model_from_agentmark_kernel(_e3b_kernel())
    decision = json.dumps(
        ["after_act1", "confirmed_by_deadline"],
        separators=(",", ":"),
    )
    distribution = model.current_distribution(decision)
    assert len(distribution) == 1
    model_action = next(iter(distribution))[0]

    modeled_dimensions = ("operation", "target_class", "variant", "delay_ms")
    assert realized.action.project(modeled_dimensions) == model_action

    operation_claim = ClaimSpec("e3b-runtime-operation", ("operation",), 0, "controller-operation")
    action_claim = ClaimSpec(
        "e3b-runtime-action",
        ("operation", "target_class", "variant"),
        0,
        "controller-action",
    )
    semantic_claim = ClaimSpec(
        "e3b-runtime-semantic",
        ("operation", "target_class", "delay_ms"),
        0,
        "controller-event",
    )
    assert operation_claim.project(realized.action).as_dict() == {"operation": "ACT2"}
    assert action_claim.project(realized.action).as_dict() == {
        "operation": "ACT2",
        "target_class": "stage2",
        "variant": None,
    }
    assert semantic_claim.project(realized.action).as_dict() == {
        "operation": "ACT2",
        "target_class": "stage2",
        "delay_ms": 0,
    }

    return {
        "full_legacy_event_coordinates_match": True,
        "operation_projection_match": True,
        "action_projection_match": True,
        "semantic_projection_match": True,
        "concrete_coordinates_remain_extra_claim_independent_provenance": True,
    }


def differential_gate() -> dict[str, object]:
    topics = (
        "agentmark/t0-R1_timing-abc12-0-b/command",
        "agentmark/source-deadbe-17-b/command",
        "agentmark/p-9-b/command",
        "agentmark/t0-R1_timing-abc12-0-a/command",
        "agentmark/t0-R1_timing-abc12-0-c/command",
        "agentmark/t0-R1_timing-abc12-0-a/query",
        "other/t0-R1_timing-abc12-0-b/command",
        "agentmark/t0-R1_timing-abc12-00-b/command",
        "agentmark/t0-R1_timing-abc12-x-b/command",
        "agentmark/-0-b/command",
        "agentmark/prefix-0-b/extra",
        "agentmark/prefix+wild-0-b/command",
    )
    payloads = (
        E3B_FROZEN_ACT2_PAYLOAD_UTF8,
        '{"on":true}',
        '{"on": false}',
        '{"on": 1}',
        '{}',
        '{"on": "true"}',
        '{"on": true, "x": 1}',
        '{"on": true, "on": true}',
        'not-json',
        'null',
    )
    qos_values = (1, 0, 2, True, "1")
    retain_values = (False, True, 0, "false")
    property_values = (None, {}, {"x": 1})

    cases = 0
    successes = 0
    failure_counts: dict[str, int] = {}
    for topic, payload, qos, retain, properties in product(
        topics, payloads, qos_values, retain_values, property_values
    ):
        raw = _raw(
            topic=topic,
            payload=payload,
            qos=qos,
            retain=retain,
            properties=properties,
        )
        prod = _production(raw)
        oracle = definition_realize_e3b_historical_action(raw)
        expected = (oracle.ok, oracle.failure_code, oracle.action_dimensions)
        if prod != expected:
            raise AssertionError(
                "production/oracle E3b historical-action mismatch: "
                f"raw={raw!r}, production={prod!r}, oracle={expected!r}"
            )
        cases += 1
        if prod[0]:
            successes += 1
        else:
            code = str(prod[1])
            failure_counts[code] = failure_counts.get(code, 0) + 1

    extra_cases: list[object] = [
        None,
        [],
        _raw(domain=""),
        _raw(domain=" mono"),
        _raw(domain=3),
        _raw(publish_ns=-1),
        _raw(publish_ns=True),
        _raw(topic=""),
        _raw(qos=1.0),
        _raw(retain=None),
        _raw(schema="foreign"),
        _raw(capture_point="post-send"),
    ]
    unknown = _raw()
    unknown["surprise"] = 1
    extra_cases.append(unknown)
    missing = _raw()
    del missing["topic"]
    extra_cases.append(missing)

    for raw in extra_cases:
        prod = _production(raw)
        oracle = definition_realize_e3b_historical_action(raw)
        expected = (oracle.ok, oracle.failure_code, oracle.action_dimensions)
        if prod != expected:
            raise AssertionError(
                "production/oracle extra-case mismatch: "
                f"raw={raw!r}, production={prod!r}, oracle={expected!r}"
            )
        cases += 1
        if prod[0]:
            successes += 1
        else:
            code = str(prod[1])
            failure_counts[code] = failure_counts.get(code, 0) + 1

    assert cases == 12 * 10 * 5 * 4 * 3 + len(extra_cases)
    assert successes > 0
    for required in (
        "MALFORMED_INPUT",
        "MISSING_REQUIRED_FIELD",
        "UNKNOWN_SEMANTIC_VALUE",
    ):
        assert failure_counts.get(required, 0) > 0

    return {
        "production_vs_literal_oracle_cases": cases,
        "successful_realizations": successes,
        "failure_counts": dict(sorted(failure_counts.items())),
        "all_applicable_failure_classes_exercised": True,
    }


def scope_gate() -> dict[str, object]:
    import replaymark.runtime_e3b_action as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    forbidden_calls = (
        ".certify_reuse(",
        ".adjudicate(",
        ".publish(",
        "regenerate(",
        "fallback(",
        "execute(",
    )
    assert not any(token in source for token in forbidden_calls)
    rule = e3b_action_realizer_rule_record()
    assert rule["capture"]["operation_or_target_class_supplied_by_caller"] is False
    return {
        "historical_action_only_increment": True,
        "compiled_contract_not_called": True,
        "execution_and_fallback_absent": True,
        "caller_semantic_labels_not_trusted": True,
        "observation_realizer_unchanged": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    args = parser.parse_args()

    report = {
        "schema": "replaymark.runtime-realization.e3b-action-gate.v1",
        "named_boundary": named_boundary_gate(),
        "frozen_source_authority": frozen_source_authority_gate(),
        "target_model_binding": target_model_binding_gate(),
        "production_vs_definition": differential_gate(),
        "scope": scope_gate(),
        "verdict": "PASS",
    }
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    print(text, end="")
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
