from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Sequence


CONFIRMED_BY_DEADLINE = "confirmed_by_deadline"
NOT_VISIBLE_BY_DEADLINE = "not_visible_by_deadline"


@dataclass(frozen=True)
class DirectNativeDecision:
    evidence_token: str
    route: str
    query_confirmation: Mapping[str, object] | None
    fresh_act2: Mapping[str, object]


def _strict_ns(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer nanosecond timestamp")
    return value


def derive_evidence_token(raw_snapshot: Mapping[str, object]) -> str:
    """Independent live DIRECT_NATIVE decision rule over its own frozen snapshot."""
    required = {
        "schema",
        "clock_domain",
        "expected_device",
        "command_publish_mono_ns",
        "verify_deadline_mono_ns",
        "closed_at_mono_ns",
        "events",
    }
    if set(raw_snapshot) != required:
        raise ValueError("direct snapshot fields are not exact")
    if raw_snapshot["schema"] != "replaymark.runtime.e3b-observation-record.v1":
        raise ValueError("foreign observation schema")
    domain = raw_snapshot["clock_domain"]
    device = raw_snapshot["expected_device"]
    if not isinstance(domain, str) or not domain:
        raise ValueError("clock domain malformed")
    if not isinstance(device, str) or not device:
        raise ValueError("expected device malformed")
    command = _strict_ns(raw_snapshot["command_publish_mono_ns"], "command_publish_mono_ns")
    deadline = _strict_ns(raw_snapshot["verify_deadline_mono_ns"], "verify_deadline_mono_ns")
    closed_at = _strict_ns(raw_snapshot["closed_at_mono_ns"], "closed_at_mono_ns")
    if deadline <= command or closed_at < deadline:
        raise ValueError("snapshot boundary malformed")

    events = raw_snapshot["events"]
    if not isinstance(events, Sequence) or isinstance(events, (str, bytes, bytearray)):
        raise ValueError("events must be a finite sequence")
    seen: set[str] = set()
    matches = 0
    for event in events:
        if not isinstance(event, Mapping):
            raise ValueError("state event must be a mapping")
        if set(event) != {"event_id", "device", "on", "recv_mono_ns", "clock_domain"}:
            raise ValueError("state event fields are not exact")
        event_id = event["event_id"]
        if not isinstance(event_id, str) or not event_id or event_id in seen:
            raise ValueError("event_id malformed or duplicate")
        seen.add(event_id)
        recv = _strict_ns(event["recv_mono_ns"], "event recv_mono_ns")
        if event["clock_domain"] != domain or recv > closed_at:
            raise ValueError("event clock/closure boundary malformed")
        if (
            event["device"] == device
            and event["on"] is True
            and command <= recv <= deadline
        ):
            matches += 1
    if matches > 1:
        raise ValueError("ambiguous direct evidence: multiple matching state events")
    return CONFIRMED_BY_DEADLINE if matches == 1 else NOT_VISIBLE_BY_DEADLINE


def execute_direct_native(
    evidence_token: str,
    *,
    query_and_confirm: Callable[[], Mapping[str, object]],
    fresh_act2: Callable[[], Mapping[str, object]],
) -> DirectNativeDecision:
    if evidence_token == CONFIRMED_BY_DEADLINE:
        fresh = fresh_act2()
        return DirectNativeDecision(
            evidence_token=evidence_token,
            route="FRESH_ACT2_NO_QUERY",
            query_confirmation=None,
            fresh_act2=fresh,
        )
    if evidence_token == NOT_VISIBLE_BY_DEADLINE:
        confirmation = query_and_confirm()
        fresh = fresh_act2()
        return DirectNativeDecision(
            evidence_token=evidence_token,
            route="QUERY_CONFIRM_THEN_FRESH_ACT2",
            query_confirmation=confirmation,
            fresh_act2=fresh,
        )
    raise ValueError("unknown direct evidence token")


__all__ = (
    "CONFIRMED_BY_DEADLINE",
    "NOT_VISIBLE_BY_DEADLINE",
    "DirectNativeDecision",
    "derive_evidence_token",
    "execute_direct_native",
)
