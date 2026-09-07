from __future__ import annotations

"""Literal oracle for E3b historical-action realization.

This module intentionally imports none of replaymark.runtime_e3b_action or
replaymark.runtime_realization. It evaluates the frozen E3b publish definition
directly on plain mappings and returns plain definition-level output.
"""

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Mapping


SOURCE_SCHEMA = "replaymark.runtime.e3b-historical-action-record.v1"
CAPTURE_POINT = "paho.mqtt.Client.publish.pre-send"
FROZEN_PAYLOAD = '{"on": true}'


@dataclass(frozen=True)
class OracleE3bAction:
    ok: bool
    failure_code: str | None
    action_dimensions: tuple[tuple[str, object], ...] | None


class _DuplicateKey(ValueError):
    pass


def _strict_json(text: str) -> object:
    def hook(pairs: list[tuple[str, object]]) -> dict[str, object]:
        out: dict[str, object] = {}
        for key, value in pairs:
            if key in out:
                raise _DuplicateKey(key)
            out[key] = value
        return out

    return json.loads(text, object_pairs_hook=hook)


def _bad(code: str) -> OracleE3bAction:
    return OracleE3bAction(False, code, None)


def definition_realize_e3b_historical_action(raw: object) -> OracleE3bAction:
    if not isinstance(raw, Mapping):
        return _bad("MALFORMED_INPUT")

    required = {
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
    if required - set(raw):
        return _bad("MISSING_REQUIRED_FIELD")
    if set(raw) - required:
        return _bad("MALFORMED_INPUT")

    if raw["schema"] != SOURCE_SCHEMA or raw["capture_point"] != CAPTURE_POINT:
        return _bad("UNKNOWN_SEMANTIC_VALUE")

    domain = raw["clock_domain"]
    if (
        not isinstance(domain, str)
        or not domain.strip()
        or domain != domain.strip()
    ):
        return _bad("MALFORMED_INPUT")
    try:
        domain.encode("utf-8")
    except UnicodeEncodeError:
        return _bad("MALFORMED_INPUT")

    stamp = raw["publish_mono_ns"]
    if isinstance(stamp, bool) or not isinstance(stamp, int) or stamp < 0:
        return _bad("MALFORMED_INPUT")

    topic = raw["topic"]
    if (
        not isinstance(topic, str)
        or not topic.strip()
        or topic != topic.strip()
    ):
        return _bad("MALFORMED_INPUT")
    try:
        topic.encode("utf-8")
    except UnicodeEncodeError:
        return _bad("MALFORMED_INPUT")

    payload = raw["payload_utf8"]
    if not isinstance(payload, str):
        return _bad("MALFORMED_INPUT")
    try:
        payload.encode("utf-8")
    except UnicodeEncodeError:
        return _bad("MALFORMED_INPUT")

    qos = raw["qos"]
    if isinstance(qos, bool) or not isinstance(qos, int):
        return _bad("MALFORMED_INPUT")
    retain = raw["retain"]
    if not isinstance(retain, bool):
        return _bad("MALFORMED_INPUT")

    if qos != 1 or retain is not False or raw["properties"] is not None:
        return _bad("UNKNOWN_SEMANTIC_VALUE")

    try:
        decoded = _strict_json(payload)
    except (_DuplicateKey, json.JSONDecodeError):
        return _bad("MALFORMED_INPUT")
    if decoded != {"on": True} or payload != FROZEN_PAYLOAD:
        return _bad("UNKNOWN_SEMANTIC_VALUE")

    topic_match = re.fullmatch(r"agentmark/([^/]+)/command", topic)
    if topic_match is None:
        return _bad("UNKNOWN_SEMANTIC_VALUE")
    device = topic_match.group(1)
    if any(ch in device for ch in ("+", "#", "\x00")):
        return _bad("MALFORMED_INPUT")

    # Independent grammar implementation: unlike production's right-split,
    # the oracle uses one anchored regex with an ASCII canonical decimal.
    device_match = re.fullmatch(r"(.+)-(0|[1-9][0-9]*)-b", device)
    if device_match is None:
        return _bad("UNKNOWN_SEMANTIC_VALUE")
    prefix = device_match.group(1)
    task_id = int(device_match.group(2))

    payload_digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    action = {
        "operation": "ACT2",
        "target_class": "stage2",
        "variant": None,
        "delay_ms": 0,
        "concrete_target": device,
        "task_id": task_id,
        "task_prefix": prefix,
        "mqtt_topic": topic,
        "mqtt_qos": 1,
        "mqtt_retain": False,
        "mqtt_payload_sha256": payload_digest,
    }
    return OracleE3bAction(True, None, tuple(sorted(action.items())))


__all__ = ("OracleE3bAction", "definition_realize_e3b_historical_action")
