from __future__ import annotations

"""E3b raw monotonic observation -> canonical ReplayMark evidence token.

This increment realizes observations only. It does not realize historical
actions, call CompiledContract, or choose execution/fallback policy.

The source record is a complete monotonic snapshot closed at or after the verify
deadline. The realizer itself selects the exact E3b event predicate used by the
frozen harness: expected device, boolean `on is True`, and receive timestamp in
the inclusive interval [command_publish_mono_ns, verify_deadline_mono_ns].

This avoids trusting a caller to pre-filter "matching" events.
"""

from dataclasses import dataclass
import hashlib
import json
from typing import Mapping, Sequence, NoReturn

from .contracts import Scalar
from .runtime_realization import (
    RealizationError,
    RealizationFailure,
    RealizationFailureCode,
    RealizationStage,
    RealizedObservation,
    observation_provenance,
    realized_observation,
)


E3B_RAW_OBSERVATION_SCHEMA = "replaymark.runtime.e3b-observation-record.v1"
E3B_OBSERVATION_REALIZER_ID = "replaymark.e3b-observation-realizer.v1"
E3B_CONFIRMED_BY_DEADLINE = "confirmed_by_deadline"
E3B_NOT_VISIBLE_BY_DEADLINE = "not_visible_by_deadline"

_FAILURE_SCHEMA = "replaymark.runtime.realization-failure.v1"

_RULE_RECORD = {
    "schema": "replaymark.realizer-semantics.e3b-observation.v2",
    "source_schema": E3B_RAW_OBSERVATION_SCHEMA,
    "capture": {
        "record_is_complete_snapshot": True,
        "closed_at_mono_ns_must_be_at_or_after_deadline": True,
        "events_after_closed_at": "reject",
        "events_outside_decision_interval": "retained-but-ignored",
    },
    "selection": {
        "device": "event.device == expected_device",
        "state": "event.on is boolean true",
        "time": (
            "command_publish_mono_ns <= event.recv_mono_ns "
            "<= verify_deadline_mono_ns"
        ),
        "deadline_inclusive": True,
    },
    "clock": {
        "kind": "named-monotonic-domain",
        "all_timestamps_same_domain": True,
        "cross_domain_conversion": "forbidden",
    },
    "matching_event_cardinality": {
        "zero": E3B_NOT_VISIBLE_BY_DEADLINE,
        "one": E3B_CONFIRMED_BY_DEADLINE,
        "duplicate_event_id": "reject",
        "multiple_distinct_matches": "reject-as-ambiguous",
    },
    "absence": {
        "empty_or_no_matching_events_in_complete_closed_snapshot_is_negative_evidence": True,
        "missing_events_field_is_malformed": True,
        "insufficiently_closed_snapshot_is_malformed": True,
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


E3B_OBSERVATION_REALIZER_SEMANTIC_DIGEST = _sha256(
    _canonical_json_bytes(_RULE_RECORD)
)


def _token(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise TypeError(f"{name} must be a non-empty canonical string")
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
    except (TypeError, ValueError, OverflowError):
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
            stage=RealizationStage.OBSERVATION,
            code=code,
            realizer_id=E3B_OBSERVATION_REALIZER_ID,
            message=message,
            raw_record_digest=_best_effort_digest(raw),
            details=tuple(details),
        )
    )


def _unknown_keys(mapping: Mapping[object, object], expected: set[str]) -> list[object]:
    return sorted((key for key in mapping if key not in expected), key=repr)


@dataclass(frozen=True)
class E3bStateEvent:
    event_id: str
    device: str
    on: bool
    recv_mono_ns: int
    clock_domain: str

    def canonical_record(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "device": self.device,
            "on": self.on,
            "recv_mono_ns": self.recv_mono_ns,
            "clock_domain": self.clock_domain,
        }


@dataclass(frozen=True)
class E3bObservationRecord:
    schema_version: str
    clock_domain: str
    expected_device: str
    command_publish_mono_ns: int
    verify_deadline_mono_ns: int
    closed_at_mono_ns: int
    events: tuple[E3bStateEvent, ...]

    def canonical_record(self) -> dict[str, object]:
        return {
            "schema": self.schema_version,
            "clock_domain": self.clock_domain,
            "expected_device": self.expected_device,
            "command_publish_mono_ns": self.command_publish_mono_ns,
            "verify_deadline_mono_ns": self.verify_deadline_mono_ns,
            "closed_at_mono_ns": self.closed_at_mono_ns,
            "events": [event.canonical_record() for event in self.events],
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.canonical_record())

    def fingerprint(self) -> str:
        return _sha256(self.canonical_bytes())


def _parse_event(raw_event: object, *, raw_parent: object, index: int) -> E3bStateEvent:
    if not isinstance(raw_event, Mapping):
        _fail(
            code=RealizationFailureCode.MALFORMED_INPUT,
            message="E3b state event must be a mapping",
            raw=raw_parent,
            details=(("event_index", index),),
        )
    expected = {"event_id", "device", "on", "recv_mono_ns", "clock_domain"}
    missing = sorted(expected - set(raw_event))
    if missing:
        _fail(
            code=RealizationFailureCode.MISSING_REQUIRED_FIELD,
            message="E3b state event is missing required fields",
            raw=raw_parent,
            details=(("event_index", index), ("field", missing[0])),
        )
    unknown = _unknown_keys(raw_event, expected)
    if unknown:
        _fail(
            code=RealizationFailureCode.MALFORMED_INPUT,
            message="E3b state event contains unknown fields",
            raw=raw_parent,
            details=(("event_index", index), ("field", repr(unknown[0]))),
        )
    try:
        event_id = _token("event_id", raw_event["event_id"])
        device = _token("event device", raw_event["device"])
        on = raw_event["on"]
        if not isinstance(on, bool):
            raise TypeError("event on must be a boolean")
        recv = _ns("recv_mono_ns", raw_event["recv_mono_ns"])
        domain = _token("event clock_domain", raw_event["clock_domain"])
    except (TypeError, ValueError) as exc:
        _fail(
            code=RealizationFailureCode.MALFORMED_INPUT,
            message=str(exc),
            raw=raw_parent,
            details=(("event_index", index),),
        )
    return E3bStateEvent(
        event_id=event_id,
        device=device,
        on=on,
        recv_mono_ns=recv,
        clock_domain=domain,
    )


def parse_e3b_observation_record(raw: object) -> E3bObservationRecord:
    """Strictly parse one complete E3b observation snapshot."""

    if not isinstance(raw, Mapping):
        _fail(
            code=RealizationFailureCode.MALFORMED_INPUT,
            message="E3b observation record must be a mapping",
            raw=raw,
        )
    expected = {
        "schema",
        "clock_domain",
        "expected_device",
        "command_publish_mono_ns",
        "verify_deadline_mono_ns",
        "closed_at_mono_ns",
        "events",
    }
    missing = sorted(expected - set(raw))
    if missing:
        _fail(
            code=RealizationFailureCode.MISSING_REQUIRED_FIELD,
            message="E3b observation record is missing required fields",
            raw=raw,
            details=(("field", missing[0]),),
        )
    unknown = _unknown_keys(raw, expected)
    if unknown:
        _fail(
            code=RealizationFailureCode.MALFORMED_INPUT,
            message="E3b observation record contains unknown fields",
            raw=raw,
            details=(("field", repr(unknown[0])),),
        )

    if raw["schema"] != E3B_RAW_OBSERVATION_SCHEMA:
        _fail(
            code=RealizationFailureCode.UNKNOWN_SEMANTIC_VALUE,
            message="foreign E3b raw observation schema",
            raw=raw,
            details=(("schema", str(raw["schema"])),),
        )

    try:
        domain = _token("clock_domain", raw["clock_domain"])
        expected_device = _token("expected_device", raw["expected_device"])
        command = _ns("command_publish_mono_ns", raw["command_publish_mono_ns"])
        deadline = _ns("verify_deadline_mono_ns", raw["verify_deadline_mono_ns"])
        closed_at = _ns("closed_at_mono_ns", raw["closed_at_mono_ns"])
    except (TypeError, ValueError) as exc:
        _fail(
            code=RealizationFailureCode.MALFORMED_INPUT,
            message=str(exc),
            raw=raw,
        )

    if deadline <= command:
        _fail(
            code=RealizationFailureCode.OUT_OF_BOUNDARY,
            message="verify deadline must be strictly after command publication",
            raw=raw,
            details=(
                ("command_publish_mono_ns", command),
                ("verify_deadline_mono_ns", deadline),
            ),
        )
    if closed_at < deadline:
        _fail(
            code=RealizationFailureCode.OUT_OF_BOUNDARY,
            message="observation snapshot was closed before the verify deadline",
            raw=raw,
            details=(
                ("verify_deadline_mono_ns", deadline),
                ("closed_at_mono_ns", closed_at),
            ),
        )

    raw_events = raw["events"]
    if not isinstance(raw_events, (list, tuple)):
        _fail(
            code=RealizationFailureCode.MALFORMED_INPUT,
            message="events must be a finite sequence",
            raw=raw,
        )

    events = tuple(
        _parse_event(item, raw_parent=raw, index=index)
        for index, item in enumerate(raw_events)
    )

    ids = [event.event_id for event in events]
    if len(ids) != len(set(ids)):
        _fail(
            code=RealizationFailureCode.DUPLICATE_INPUT,
            message="duplicate E3b event_id in one observation snapshot",
            raw=raw,
        )

    for event in events:
        if event.clock_domain != domain:
            _fail(
                code=RealizationFailureCode.CLOCK_DOMAIN_MISMATCH,
                message="event timestamp belongs to a different monotonic clock domain",
                raw=raw,
                details=(
                    ("record_clock_domain", domain),
                    ("event_clock_domain", event.clock_domain),
                ),
            )
        if event.recv_mono_ns > closed_at:
            _fail(
                code=RealizationFailureCode.OUT_OF_BOUNDARY,
                message="event timestamp lies after the declared snapshot closure",
                raw=raw,
                details=(("event_id", event.event_id),),
            )

    return E3bObservationRecord(
        schema_version=E3B_RAW_OBSERVATION_SCHEMA,
        clock_domain=domain,
        expected_device=expected_device,
        command_publish_mono_ns=command,
        verify_deadline_mono_ns=deadline,
        closed_at_mono_ns=closed_at,
        events=events,
    )


def _matching_events(record: E3bObservationRecord) -> tuple[E3bStateEvent, ...]:
    matches = tuple(
        event
        for event in record.events
        if event.device == record.expected_device
        and event.on is True
        and record.command_publish_mono_ns
        <= event.recv_mono_ns
        <= record.verify_deadline_mono_ns
    )
    if len(matches) > 1:
        _fail(
            code=RealizationFailureCode.AMBIGUOUS_REALIZATION,
            message=(
                "multiple distinct matching state-on events occur inside one "
                "E3b decision boundary"
            ),
            raw=record.canonical_record(),
            details=(("matching_event_count", len(matches)),),
        )
    return matches


def realize_e3b_observation(raw: object) -> RealizedObservation:
    """Map a complete E3b monotonic snapshot to the frozen feedback token."""

    record = parse_e3b_observation_record(raw)
    matches = _matching_events(record)
    raw_digest = record.fingerprint()

    if not matches:
        token = E3B_NOT_VISIBLE_BY_DEADLINE
        source_event_timestamp_ns = None
    else:
        token = E3B_CONFIRMED_BY_DEADLINE
        source_event_timestamp_ns = matches[0].recv_mono_ns

    provenance = observation_provenance(
        realizer_id=E3B_OBSERVATION_REALIZER_ID,
        realizer_semantic_digest=E3B_OBSERVATION_REALIZER_SEMANTIC_DIGEST,
        source_schema=E3B_RAW_OBSERVATION_SCHEMA,
        raw_record_digest=raw_digest,
    )
    return realized_observation(
        evidence_token=token,
        clock_domain=record.clock_domain,
        boundary_timestamp_ns=record.verify_deadline_mono_ns,
        source_event_timestamp_ns=source_event_timestamp_ns,
        provenance=provenance,
    )


def e3b_observation_realizer_rule_record() -> dict[str, object]:
    """Return a defensive copy of the normative realizer semantics record."""

    return json.loads(_canonical_json_bytes(_RULE_RECORD).decode("utf-8"))


__all__ = (
    "E3B_RAW_OBSERVATION_SCHEMA",
    "E3B_OBSERVATION_REALIZER_ID",
    "E3B_OBSERVATION_REALIZER_SEMANTIC_DIGEST",
    "E3B_CONFIRMED_BY_DEADLINE",
    "E3B_NOT_VISIBLE_BY_DEADLINE",
    "E3bStateEvent",
    "E3bObservationRecord",
    "parse_e3b_observation_record",
    "realize_e3b_observation",
    "e3b_observation_realizer_rule_record",
)
