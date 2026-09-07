from __future__ import annotations

"""Independent literal oracle for E3b integrated runtime conformance.

This module intentionally imports no ReplayMark, AgentMark, MQTT, or experiment
code. It re-states only the frozen E3b runtime facts needed to compare the live
production chain against an independently written definition.
"""

from dataclasses import dataclass
import hashlib
import json
from typing import Mapping, Sequence


CONFIRMED = "confirmed_by_deadline"
NOT_VISIBLE = "not_visible_by_deadline"
VALID = "VALID"
INVALID = "INVALID"
REUSE = "REUSE"
DO_NOT_REUSE = "DO_NOT_REUSE"

OBS_SCHEMA = "replaymark.runtime.e3b-observation-record.v1"
ACTION_SCHEMA = "replaymark.runtime.e3b-historical-action-record.v1"
CAPTURE_POINT = "paho.mqtt.Client.publish.pre-send"
ACT2_PAYLOAD = '{"on": true}'


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_json(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


@dataclass(frozen=True)
class LiteralTaskIdentity:
    prefix: str
    task_id: int
    role: str
    device: str


@dataclass(frozen=True)
class LiteralIntegratedExpectation:
    observation_token: str
    action_operation: str
    action_target_class: str
    action_variant: None
    action_delay_ms: int
    task_prefix: str
    task_id: int
    observation_role: str
    action_role: str
    verdict: str
    reuse_disposition: str

    def canonical_record(self) -> dict[str, object]:
        return {
            "observation_token": self.observation_token,
            "action": {
                "operation": self.action_operation,
                "target_class": self.action_target_class,
                "variant": self.action_variant,
                "delay_ms": self.action_delay_ms,
            },
            "task_prefix": self.task_prefix,
            "task_id": self.task_id,
            "observation_role": self.observation_role,
            "action_role": self.action_role,
            "verdict": self.verdict,
            "reuse_disposition": self.reuse_disposition,
        }


def _mapping(name: str, value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    if not all(isinstance(key, str) for key in value):
        raise ValueError(f"{name} keys must be strings")
    return value  # type: ignore[return-value]


def _canonical_ns(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _canonical_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{name} must be canonical non-empty text")
    return value


def parse_device(device: object, *, expected_role: str) -> LiteralTaskIdentity:
    text = _canonical_text("device", device)
    if any(ch in text for ch in ("+", "#", "\x00")):
        raise ValueError("device contains forbidden MQTT identifier characters")
    try:
        prefix, task_text, role = text.rsplit("-", 2)
    except ValueError as exc:
        raise ValueError("device does not encode prefix-task-role") from exc
    if not prefix or role != expected_role:
        raise ValueError("device role does not match frozen E3b role")
    if not task_text.isascii() or not task_text.isdigit():
        raise ValueError("task id is not canonical ASCII decimal")
    task_id = int(task_text)
    if str(task_id) != task_text:
        raise ValueError("task id has noncanonical decimal encoding")
    return LiteralTaskIdentity(prefix, task_id, role, text)


def observation_token(raw: object) -> tuple[str, LiteralTaskIdentity]:
    record = _mapping("observation", raw)
    expected_keys = {
        "schema",
        "clock_domain",
        "expected_device",
        "command_publish_mono_ns",
        "verify_deadline_mono_ns",
        "closed_at_mono_ns",
        "events",
    }
    if set(record) != expected_keys:
        raise ValueError("observation fields differ from frozen schema")
    if record["schema"] != OBS_SCHEMA:
        raise ValueError("foreign observation schema")
    clock = _canonical_text("clock_domain", record["clock_domain"])
    identity = parse_device(record["expected_device"], expected_role="a")
    command = _canonical_ns("command_publish_mono_ns", record["command_publish_mono_ns"])
    deadline = _canonical_ns("verify_deadline_mono_ns", record["verify_deadline_mono_ns"])
    closed = _canonical_ns("closed_at_mono_ns", record["closed_at_mono_ns"])
    if deadline <= command:
        raise ValueError("deadline must follow command publication")
    if closed < deadline:
        raise ValueError("snapshot is not closed through deadline")
    events = record["events"]
    if not isinstance(events, Sequence) or isinstance(events, (str, bytes, bytearray)):
        raise ValueError("events must be a sequence")

    seen_ids: set[str] = set()
    matches = 0
    for value in events:
        event = _mapping("event", value)
        expected_event_keys = {
            "event_id",
            "device",
            "on",
            "recv_mono_ns",
            "clock_domain",
        }
        if set(event) != expected_event_keys:
            raise ValueError("event fields differ from frozen schema")
        event_id = _canonical_text("event_id", event["event_id"])
        if event_id in seen_ids:
            raise ValueError("duplicate event id")
        seen_ids.add(event_id)
        device = _canonical_text("event device", event["device"])
        on = event["on"]
        if not isinstance(on, bool):
            raise ValueError("event on must be boolean")
        recv = _canonical_ns("recv_mono_ns", event["recv_mono_ns"])
        event_clock = _canonical_text("event clock_domain", event["clock_domain"])
        if event_clock != clock:
            raise ValueError("event crosses monotonic clock domain")
        if recv > closed:
            raise ValueError("event occurs after snapshot close")
        if device == identity.device and on is True and command <= recv <= deadline:
            matches += 1

    if matches == 0:
        return NOT_VISIBLE, identity
    if matches == 1:
        return CONFIRMED, identity
    raise ValueError("multiple distinct matching events are ambiguous")


def historical_action(raw: object) -> tuple[dict[str, object], LiteralTaskIdentity]:
    record = _mapping("historical action", raw)
    expected_keys = {
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
    if set(record) != expected_keys:
        raise ValueError("historical-action fields differ from frozen schema")
    if record["schema"] != ACTION_SCHEMA:
        raise ValueError("foreign historical-action schema")
    if record["capture_point"] != CAPTURE_POINT:
        raise ValueError("historical action is not captured at frozen pre-send boundary")
    _canonical_text("clock_domain", record["clock_domain"])
    _canonical_ns("publish_mono_ns", record["publish_mono_ns"])
    topic = _canonical_text("topic", record["topic"])
    parts = topic.split("/")
    if len(parts) != 3 or parts[0] != "agentmark" or parts[2] != "command":
        raise ValueError("topic is outside frozen E3b command family")
    identity = parse_device(parts[1], expected_role="b")
    if record["payload_utf8"] != ACT2_PAYLOAD:
        raise ValueError("payload differs from frozen ACT2 bytes")
    if record["qos"] != 1 or isinstance(record["qos"], bool):
        raise ValueError("QoS differs from frozen ACT2")
    if record["retain"] is not False:
        raise ValueError("retain differs from frozen ACT2")
    if record["properties"] is not None:
        raise ValueError("properties differ from frozen ACT2")
    return {
        "operation": "ACT2",
        "target_class": "stage2",
        "variant": None,
        "delay_ms": 0,
    }, identity


def integrated_expectation(
    raw_observation: object,
    raw_historical_action: object,
) -> LiteralIntegratedExpectation:
    token, obs_identity = observation_token(raw_observation)
    action, action_identity = historical_action(raw_historical_action)
    observation = _mapping("observation", raw_observation)
    historical = _mapping("historical action", raw_historical_action)

    if obs_identity.prefix != action_identity.prefix or obs_identity.task_id != action_identity.task_id:
        raise ValueError("stage-1 observation and stage-2 action are cross-task")
    if observation["clock_domain"] != historical["clock_domain"]:
        raise ValueError("observation/action clock domains differ")
    if int(historical["publish_mono_ns"]) < int(observation["command_publish_mono_ns"]):
        raise ValueError("stage-2 action precedes stage-1 command")

    if token == CONFIRMED:
        verdict, disposition = VALID, REUSE
    elif token == NOT_VISIBLE:
        verdict, disposition = INVALID, DO_NOT_REUSE
    else:
        raise AssertionError("literal oracle emitted unknown token")

    return LiteralIntegratedExpectation(
        observation_token=token,
        action_operation=str(action["operation"]),
        action_target_class=str(action["target_class"]),
        action_variant=None,
        action_delay_ms=int(action["delay_ms"]),
        task_prefix=obs_identity.prefix,
        task_id=obs_identity.task_id,
        observation_role=obs_identity.role,
        action_role=action_identity.role,
        verdict=verdict,
        reuse_disposition=disposition,
    )


__all__ = (
    "CONFIRMED",
    "NOT_VISIBLE",
    "VALID",
    "INVALID",
    "REUSE",
    "DO_NOT_REUSE",
    "LiteralTaskIdentity",
    "LiteralIntegratedExpectation",
    "canonical_json_bytes",
    "sha256_json",
    "parse_device",
    "observation_token",
    "historical_action",
    "integrated_expectation",
)
