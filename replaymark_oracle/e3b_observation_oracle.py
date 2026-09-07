from __future__ import annotations

"""Literal definition oracle for the E3b observation-realization boundary.

This oracle intentionally imports none of replaymark.runtime_e3b_observation or
replaymark.runtime_realization. It works directly on plain mappings.

Definition:
- a complete snapshot is closed at or after the verify deadline;
- one named monotonic clock domain is used throughout;
- the exact frozen E3b predicate is device match AND boolean on AND receive time
  in the inclusive [command, deadline] interval;
- zero matches -> not_visible_by_deadline;
- one match -> confirmed_by_deadline;
- duplicates, cross-clock data, insufficient closure, events after snapshot
  closure, or multiple distinct matches are rejected.
"""

from dataclasses import dataclass
from typing import Mapping


SOURCE_SCHEMA = "replaymark.runtime.e3b-observation-record.v1"
CONFIRMED = "confirmed_by_deadline"
NOT_VISIBLE = "not_visible_by_deadline"


@dataclass(frozen=True)
class OracleE3bObservation:
    ok: bool
    token: str | None
    error_code: str | None
    boundary_timestamp_ns: int | None
    source_event_timestamp_ns: int | None


def _bad(code: str) -> OracleE3bObservation:
    return OracleE3bObservation(
        ok=False,
        token=None,
        error_code=code,
        boundary_timestamp_ns=None,
        source_event_timestamp_ns=None,
    )


def definition_realize_e3b_observation(raw: object) -> OracleE3bObservation:
    if not isinstance(raw, Mapping):
        return _bad("MALFORMED_INPUT")

    required = {
        "schema",
        "clock_domain",
        "expected_device",
        "command_publish_mono_ns",
        "verify_deadline_mono_ns",
        "closed_at_mono_ns",
        "events",
    }
    if required - set(raw):
        return _bad("MISSING_REQUIRED_FIELD")
    if set(raw) - required:
        return _bad("MALFORMED_INPUT")
    if raw["schema"] != SOURCE_SCHEMA:
        return _bad("UNKNOWN_SEMANTIC_VALUE")

    domain = raw["clock_domain"]
    expected_device = raw["expected_device"]
    command = raw["command_publish_mono_ns"]
    deadline = raw["verify_deadline_mono_ns"]
    closed_at = raw["closed_at_mono_ns"]

    for value in (domain, expected_device):
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            return _bad("MALFORMED_INPUT")
    for value in (command, deadline, closed_at):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return _bad("MALFORMED_INPUT")
    if deadline <= command or closed_at < deadline:
        return _bad("OUT_OF_BOUNDARY")

    raw_events = raw["events"]
    if not isinstance(raw_events, (list, tuple)):
        return _bad("MALFORMED_INPUT")

    events: list[tuple[str, str, bool, int, str]] = []
    for item in raw_events:
        if not isinstance(item, Mapping):
            return _bad("MALFORMED_INPUT")
        fields = {"event_id", "device", "on", "recv_mono_ns", "clock_domain"}
        if fields - set(item):
            return _bad("MISSING_REQUIRED_FIELD")
        if set(item) - fields:
            return _bad("MALFORMED_INPUT")

        event_id = item["event_id"]
        device = item["device"]
        on = item["on"]
        recv = item["recv_mono_ns"]
        event_domain = item["clock_domain"]
        if (
            not isinstance(event_id, str)
            or not event_id.strip()
            or event_id != event_id.strip()
            or not isinstance(device, str)
            or not device.strip()
            or device != device.strip()
            or not isinstance(on, bool)
            or isinstance(recv, bool)
            or not isinstance(recv, int)
            or recv < 0
            or not isinstance(event_domain, str)
            or not event_domain.strip()
            or event_domain != event_domain.strip()
        ):
            return _bad("MALFORMED_INPUT")
        events.append((event_id, device, on, recv, event_domain))

    ids = [event[0] for event in events]
    if len(ids) != len(set(ids)):
        return _bad("DUPLICATE_INPUT")

    for _event_id, _device, _on, recv, event_domain in events:
        if event_domain != domain:
            return _bad("CLOCK_DOMAIN_MISMATCH")
        if recv > closed_at:
            return _bad("OUT_OF_BOUNDARY")

    matches = [
        event
        for event in events
        if event[1] == expected_device
        and event[2] is True
        and command <= event[3] <= deadline
    ]
    if len(matches) > 1:
        return _bad("AMBIGUOUS_REALIZATION")
    if not matches:
        return OracleE3bObservation(
            ok=True,
            token=NOT_VISIBLE,
            error_code=None,
            boundary_timestamp_ns=deadline,
            source_event_timestamp_ns=None,
        )
    return OracleE3bObservation(
        ok=True,
        token=CONFIRMED,
        error_code=None,
        boundary_timestamp_ns=deadline,
        source_event_timestamp_ns=matches[0][3],
    )


__all__ = ("OracleE3bObservation", "definition_realize_e3b_observation")
