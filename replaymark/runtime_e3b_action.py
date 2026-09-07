from __future__ import annotations

"""Strict E3b historical-decision -> concrete MQTT action realization.

This module implements exactly one runtime-boundary arrow:

    concrete target-run candidate publish
        -> RealizedHistoricalAction

It does not observe target feedback, invoke CompiledContract, certify reuse,
execute or block the publish, or choose any fallback.

The E3b experiment does not byte-replay a source MQTT packet. It retains the
historical controller decision ACT2 and reconstructs a fresh task-local stage-2
publish in the target run. The realizer therefore certifies that the *actual
candidate publish invocation* is an exact concrete instantiation of that frozen
ACT2 decision before semantic certification is attempted.
"""

from dataclasses import dataclass
import hashlib
import json
from typing import Mapping, NoReturn, Sequence

from .contracts import ProjectedAction, Scalar
from .runtime_realization import (
    RealizationError,
    RealizationFailure,
    RealizationFailureCode,
    RealizationStage,
    RealizedHistoricalAction,
    historical_action_provenance,
)


E3B_RAW_ACTION_SCHEMA = "replaymark.runtime.e3b-historical-action-record.v1"
E3B_ACTION_CAPTURE_POINT = "paho.mqtt.Client.publish.pre-send"
E3B_ACTION_REALIZER_ID = "replaymark.e3b-historical-action-realizer.v1"
E3B_FROZEN_ACT2_PAYLOAD_UTF8 = '{"on": true}'

# Exact historical source authorities from the frozen E3b experiment. The rule
# record binds the realizer to the code that constructs the publish and the code
# that consumes it, rather than to a human-readable provider label alone.
E3B_LADDER_GIT_BLOB_SHA1 = "fcc1768544714f1b11a497a856f8e18d4d2f07dd"
E3B_DEVICE_GIT_BLOB_SHA1 = "27240e65cb8e1a7d788cc5dea8484cbad8ec6653"

_FAILURE_SCHEMA = "replaymark.runtime.realization-failure.v1"
_ACTION_SCHEMA = "replaymark.runtime.realized-historical-action.v1"

_RULE_RECORD = {
    "schema": "replaymark.realizer-semantics.e3b-historical-action.v1",
    "source_schema": E3B_RAW_ACTION_SCHEMA,
    "capture": {
        "point": E3B_ACTION_CAPTURE_POINT,
        "meaning": "resolved application publish-call arguments before send",
        "broker_delivery_or_ack_certified": False,
        "operation_or_target_class_supplied_by_caller": False,
    },
    "source_authorities": {
        "producer_path": "agentmark_e3b_lab/e3_mqtt/app/ladder.py",
        "producer_git_blob_sha1": E3B_LADDER_GIT_BLOB_SHA1,
        "consumer_path": "agentmark_e3b_lab/e3_mqtt/app/device.py",
        "consumer_git_blob_sha1": E3B_DEVICE_GIT_BLOB_SHA1,
    },
    "frozen_candidate": {
        "topic_grammar": "agentmark/<prefix>-<canonical-decimal-task-id>-b/command",
        "stage_role": "b",
        "payload_utf8_exact": E3B_FROZEN_ACT2_PAYLOAD_UTF8,
        "qos": 1,
        "retain": False,
        "properties": None,
    },
    "derived_modeled_coordinates": {
        "operation": "ACT2",
        "target_class": "stage2",
        "variant": None,
        "delay_ms": 0,
    },
    "conservatism": {
        "semantically_similar_alternate_json_encodings": "reject",
        "alternate_payloads_that_device_might_coerce_true": "reject",
        "stage1_command_or_query": "reject",
        "unknown_transport_options": "reject",
    },
    "historical_semantics": {
        "retained_object": "controller decision ACT2",
        "source_packet_bytes_reused": False,
        "target_run_concrete_device_is_fresh": True,
    },
}


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


E3B_ACTION_REALIZER_SEMANTIC_DIGEST = _sha256(_canonical_json_bytes(_RULE_RECORD))


def _token(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise TypeError(f"{name} must be a non-empty canonical string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise TypeError(f"{name} must be valid UTF-8 text") from exc
    return value


def _ns(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer nanosecond timestamp")
    if value < 0:
        raise ValueError(f"{name} must be >= 0")
    return value


def _best_effort_digest(raw: object) -> str | None:
    try:
        return _sha256(_canonical_json_bytes(raw))
    except (TypeError, ValueError, OverflowError, UnicodeEncodeError):
        return None


def _fail(
    *,
    code: RealizationFailureCode,
    message: str,
    raw: object,
    details: Sequence[tuple[str, Scalar]] = (),
) -> NoReturn:
    raise RealizationError(
        RealizationFailure(
            schema_version=_FAILURE_SCHEMA,
            stage=RealizationStage.HISTORICAL_ACTION,
            code=code,
            realizer_id=E3B_ACTION_REALIZER_ID,
            message=message,
            raw_record_digest=_best_effort_digest(raw),
            details=tuple(details),
        )
    )


def _unknown_keys(mapping: Mapping[object, object], expected: set[str]) -> list[object]:
    return sorted((key for key in mapping if key not in expected), key=repr)


class _DuplicateJsonKey(ValueError):
    pass


def _strict_json_object(text: str) -> object:
    def hook(pairs: list[tuple[str, object]]) -> dict[str, object]:
        out: dict[str, object] = {}
        for key, value in pairs:
            if key in out:
                raise _DuplicateJsonKey(key)
            out[key] = value
        return out

    return json.loads(text, object_pairs_hook=hook)


def _parse_stage2_device(topic: str, *, raw: object) -> tuple[str, int, str]:
    parts = topic.split("/")
    if len(parts) != 3 or parts[0] != "agentmark" or parts[2] != "command":
        _fail(
            code=RealizationFailureCode.UNKNOWN_SEMANTIC_VALUE,
            message="MQTT topic is not the frozen E3b command topic family",
            raw=raw,
            details=(("topic", topic),),
        )
    device = parts[1]
    if not device or any(ch in device for ch in ("+", "#", "\x00")):
        _fail(
            code=RealizationFailureCode.MALFORMED_INPUT,
            message="E3b command topic contains an invalid device identifier",
            raw=raw,
            details=(("topic", topic),),
        )
    try:
        prefix, task_text, role = device.rsplit("-", 2)
    except ValueError:
        _fail(
            code=RealizationFailureCode.UNKNOWN_SEMANTIC_VALUE,
            message="device id does not encode the frozen E3b task role",
            raw=raw,
            details=(("device", device),),
        )
    if not prefix or role != "b":
        _fail(
            code=RealizationFailureCode.UNKNOWN_SEMANTIC_VALUE,
            message="candidate publish is not an E3b stage-2 action",
            raw=raw,
            details=(("device", device), ("role", role)),
        )
    if not task_text.isascii() or not task_text.isdigit():
        _fail(
            code=RealizationFailureCode.UNKNOWN_SEMANTIC_VALUE,
            message="E3b task id is not canonical decimal",
            raw=raw,
            details=(("task_id_text", task_text),),
        )
    task_id = int(task_text)
    if str(task_id) != task_text:
        _fail(
            code=RealizationFailureCode.UNKNOWN_SEMANTIC_VALUE,
            message="E3b task id has a noncanonical decimal encoding",
            raw=raw,
            details=(("task_id_text", task_text),),
        )
    return prefix, task_id, device


@dataclass(frozen=True)
class E3bHistoricalActionRecord:
    schema_version: str
    capture_point: str
    clock_domain: str
    publish_mono_ns: int
    topic: str
    payload_utf8: str
    qos: int
    retain: bool
    properties: None

    def canonical_record(self) -> dict[str, object]:
        return {
            "schema": self.schema_version,
            "capture_point": self.capture_point,
            "clock_domain": self.clock_domain,
            "publish_mono_ns": self.publish_mono_ns,
            "topic": self.topic,
            "payload_utf8": self.payload_utf8,
            "qos": self.qos,
            "retain": self.retain,
            "properties": self.properties,
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.canonical_record())

    def fingerprint(self) -> str:
        return _sha256(self.canonical_bytes())


def parse_e3b_historical_action_record(raw: object) -> E3bHistoricalActionRecord:
    """Strictly parse one resolved pre-send E3b MQTT publish invocation."""

    if not isinstance(raw, Mapping):
        _fail(
            code=RealizationFailureCode.MALFORMED_INPUT,
            message="E3b historical-action record must be a mapping",
            raw=raw,
        )
    expected = {
        "schema",
        "capture_point",
        "clock_domain",
        "publish_mono_ns",
        "topic",
        "payload_utf8",
        "qos",
        "retain",
        "properties",
    }
    missing = sorted(expected - set(raw))
    if missing:
        _fail(
            code=RealizationFailureCode.MISSING_REQUIRED_FIELD,
            message="E3b historical-action record is missing required fields",
            raw=raw,
            details=(("field", missing[0]),),
        )
    unknown = _unknown_keys(raw, expected)
    if unknown:
        _fail(
            code=RealizationFailureCode.MALFORMED_INPUT,
            message="E3b historical-action record contains unknown fields",
            raw=raw,
            details=(("field", repr(unknown[0])),),
        )

    if raw["schema"] != E3B_RAW_ACTION_SCHEMA:
        _fail(
            code=RealizationFailureCode.UNKNOWN_SEMANTIC_VALUE,
            message="foreign E3b historical-action schema",
            raw=raw,
            details=(("schema", str(raw["schema"])),),
        )
    if raw["capture_point"] != E3B_ACTION_CAPTURE_POINT:
        _fail(
            code=RealizationFailureCode.UNKNOWN_SEMANTIC_VALUE,
            message="historical action was captured at an unsupported boundary",
            raw=raw,
            details=(("capture_point", str(raw["capture_point"])),),
        )

    try:
        domain = _token("clock_domain", raw["clock_domain"])
        publish_ns = _ns("publish_mono_ns", raw["publish_mono_ns"])
        topic = _token("topic", raw["topic"])
        payload = raw["payload_utf8"]
        if not isinstance(payload, str):
            raise TypeError("payload_utf8 must be a string")
        try:
            payload.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise TypeError("payload_utf8 must be valid UTF-8 text") from exc
        qos = raw["qos"]
        if isinstance(qos, bool) or not isinstance(qos, int):
            raise TypeError("qos must be an integer")
        retain = raw["retain"]
        if not isinstance(retain, bool):
            raise TypeError("retain must be a boolean")
    except (TypeError, ValueError) as exc:
        _fail(
            code=RealizationFailureCode.MALFORMED_INPUT,
            message=str(exc),
            raw=raw,
        )

    if qos != 1:
        _fail(
            code=RealizationFailureCode.UNKNOWN_SEMANTIC_VALUE,
            message="candidate publish does not use the frozen E3b QoS-1 action",
            raw=raw,
            details=(("qos", qos),),
        )
    if retain is not False:
        _fail(
            code=RealizationFailureCode.UNKNOWN_SEMANTIC_VALUE,
            message="candidate publish changes the frozen E3b retain semantics",
            raw=raw,
            details=(("retain", retain),),
        )
    if raw["properties"] is not None:
        _fail(
            code=RealizationFailureCode.UNKNOWN_SEMANTIC_VALUE,
            message="candidate publish carries MQTT properties absent from the frozen action",
            raw=raw,
        )

    try:
        parsed_payload = _strict_json_object(payload)
    except (_DuplicateJsonKey, json.JSONDecodeError) as exc:
        _fail(
            code=RealizationFailureCode.MALFORMED_INPUT,
            message=f"payload_utf8 is not strict duplicate-free JSON: {exc}",
            raw=raw,
        )
    if parsed_payload != {"on": True}:
        _fail(
            code=RealizationFailureCode.UNKNOWN_SEMANTIC_VALUE,
            message="payload does not denote the frozen E3b ACT2 body",
            raw=raw,
        )
    if payload != E3B_FROZEN_ACT2_PAYLOAD_UTF8:
        _fail(
            code=RealizationFailureCode.UNKNOWN_SEMANTIC_VALUE,
            message="payload is semantically similar but not the exact frozen producer encoding",
            raw=raw,
        )

    # Parse and validate the stage-2 role now, so no caller-provided `operation`
    # or `target_class` field is ever trusted.
    _parse_stage2_device(topic, raw=raw)

    return E3bHistoricalActionRecord(
        schema_version=E3B_RAW_ACTION_SCHEMA,
        capture_point=E3B_ACTION_CAPTURE_POINT,
        clock_domain=domain,
        publish_mono_ns=publish_ns,
        topic=topic,
        payload_utf8=payload,
        qos=qos,
        retain=retain,
        properties=None,
    )


def realize_e3b_historical_action(raw: object) -> RealizedHistoricalAction:
    """Certify one concrete candidate publish as the frozen E3b ACT2 decision."""

    record = parse_e3b_historical_action_record(raw)
    prefix, task_id, device = _parse_stage2_device(record.topic, raw=record.canonical_record())
    payload_digest = _sha256(record.payload_utf8.encode("utf-8"))

    # The first four coordinates are exactly the legacy TargetModel event
    # coordinates. Remaining coordinates preserve concrete substrate identity
    # without changing claim projection.
    action = ProjectedAction.from_mapping(
        {
            "operation": "ACT2",
            "target_class": "stage2",
            "variant": None,
            "delay_ms": 0,
            "concrete_target": device,
            "task_id": task_id,
            "task_prefix": prefix,
            "mqtt_topic": record.topic,
            "mqtt_qos": record.qos,
            "mqtt_retain": record.retain,
            "mqtt_payload_sha256": payload_digest,
        }
    )
    provenance = historical_action_provenance(
        realizer_id=E3B_ACTION_REALIZER_ID,
        realizer_semantic_digest=E3B_ACTION_REALIZER_SEMANTIC_DIGEST,
        source_schema=E3B_RAW_ACTION_SCHEMA,
        raw_record_digest=record.fingerprint(),
    )
    return RealizedHistoricalAction(
        schema_version=_ACTION_SCHEMA,
        action=action,
        provenance=provenance,
    )


def e3b_action_realizer_rule_record() -> dict[str, object]:
    """Return a defensive copy of the normative realizer semantics record."""

    return json.loads(_canonical_json_bytes(_RULE_RECORD).decode("utf-8"))


__all__ = (
    "E3B_RAW_ACTION_SCHEMA",
    "E3B_ACTION_CAPTURE_POINT",
    "E3B_ACTION_REALIZER_ID",
    "E3B_ACTION_REALIZER_SEMANTIC_DIGEST",
    "E3B_FROZEN_ACT2_PAYLOAD_UTF8",
    "E3B_LADDER_GIT_BLOB_SHA1",
    "E3B_DEVICE_GIT_BLOB_SHA1",
    "E3bHistoricalActionRecord",
    "parse_e3b_historical_action_record",
    "realize_e3b_historical_action",
    "e3b_action_realizer_rule_record",
)
