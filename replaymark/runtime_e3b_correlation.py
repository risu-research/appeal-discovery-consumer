from __future__ import annotations

"""E3b same-task correlation between already-frozen runtime realizers.

This module closes one composition seam only:

    raw stage-1 observation + raw stage-2 candidate action
        -> individually realized values
        -> proof that both belong to the same canonical E3b task/context

It deliberately does not import or call ExplicitCompiledContract, adjudication,
R*, execution, MQTT publish, or fallback policy.  Correlation failure is a
pre-semantic runtime binding failure, not semantic UNRESOLVED.
"""

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from typing import Mapping

from .runtime_e3b_action import (
    E3B_ACTION_REALIZER_ID,
    E3B_ACTION_REALIZER_SEMANTIC_DIGEST,
    E3B_RAW_ACTION_SCHEMA,
    parse_e3b_historical_action_record,
    realize_e3b_historical_action,
)
from .runtime_e3b_observation import (
    E3B_OBSERVATION_REALIZER_ID,
    E3B_OBSERVATION_REALIZER_SEMANTIC_DIGEST,
    E3B_RAW_OBSERVATION_SCHEMA,
    parse_e3b_observation_record,
    realize_e3b_observation,
)
from .runtime_realization import RealizedHistoricalAction, RealizedObservation


E3B_TASK_CORRELATION_SCHEMA = "replaymark.runtime.e3b-task-correlation-proof.v1"
E3B_CORRELATED_PAIR_SCHEMA = "replaymark.runtime.e3b-correlated-pair.v1"
E3B_TASK_CORRELATOR_ID = "replaymark.e3b-task-correlator.v1"
E3B_TASK_CORRELATION_FAILURE_SCHEMA = (
    "replaymark.runtime.e3b-task-correlation-failure.v1"
)

_RULE_RECORD = {
    "schema": "replaymark.runtime.e3b-task-correlation-semantics.v1",
    "inputs": {
        "observation": E3B_RAW_OBSERVATION_SCHEMA,
        "historical_action": E3B_RAW_ACTION_SCHEMA,
        "individual_realizers_must_succeed": True,
    },
    "identity": {
        "observation_device_grammar": "<prefix>-<canonical-decimal-task-id>-a",
        "action_device_grammar": "<prefix>-<canonical-decimal-task-id>-b",
        "prefix_must_match_exactly": True,
        "task_id_must_match_exactly": True,
        "caller_supplied_same_task_flag": "forbidden",
        "temporal_proximity_as_identity": "forbidden",
    },
    "context": {
        "clock_domain_must_match": True,
        "action_publish_must_not_precede_stage1_command_publish": True,
    },
    "semantic_boundary": {
        "contract_call": False,
        "adjudication": False,
        "rstar": False,
        "execution_side_effect": False,
        "fallback_policy": False,
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


E3B_TASK_CORRELATOR_SEMANTIC_DIGEST = _sha256(_canonical_json_bytes(_RULE_RECORD))


def _token(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{name} must be a non-empty canonical string")
    return value


def _digest(name: str, value: object) -> str:
    value = _token(name, value)
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError(f"{name} must be lowercase sha256 hex")
    return value


class E3bTaskCorrelationFailureCode(str, Enum):
    MALFORMED_IDENTITY = "MALFORMED_IDENTITY"
    ROLE_MISMATCH = "ROLE_MISMATCH"
    TASK_MISMATCH = "TASK_MISMATCH"
    CLOCK_DOMAIN_MISMATCH = "CLOCK_DOMAIN_MISMATCH"
    TEMPORAL_INCONSISTENCY = "TEMPORAL_INCONSISTENCY"
    INTERNAL_INCONSISTENCY = "INTERNAL_INCONSISTENCY"


@dataclass(frozen=True)
class E3bTaskCorrelationFailure:
    schema_version: str
    code: E3bTaskCorrelationFailureCode
    message: str
    observation_raw_digest: str
    action_raw_digest: str
    details: tuple[tuple[str, str | int], ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != E3B_TASK_CORRELATION_FAILURE_SCHEMA:
            raise ValueError("foreign E3b task-correlation failure schema")
        if not isinstance(self.code, E3bTaskCorrelationFailureCode):
            raise TypeError("code must be E3bTaskCorrelationFailureCode")
        _token("message", self.message)
        _digest("observation_raw_digest", self.observation_raw_digest)
        _digest("action_raw_digest", self.action_raw_digest)
        seen: set[str] = set()
        normalized: list[tuple[str, str | int]] = []
        for key, value in self.details:
            key = _token("detail name", key)
            if key in seen:
                raise ValueError(f"duplicate detail name: {key!r}")
            if isinstance(value, bool) or not isinstance(value, (str, int)):
                raise TypeError("correlation detail must be str or int")
            seen.add(key)
            normalized.append((key, value))
        object.__setattr__(self, "details", tuple(sorted(normalized)))

    def canonical_record(self) -> dict[str, object]:
        return {
            "schema": self.schema_version,
            "code": self.code.value,
            "message": self.message,
            "observation_raw_digest": self.observation_raw_digest,
            "action_raw_digest": self.action_raw_digest,
            "details": [
                {"name": key, "value": value} for key, value in self.details
            ],
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.canonical_record())

    def fingerprint(self) -> str:
        return _sha256(self.canonical_bytes())


class E3bTaskCorrelationError(ValueError):
    def __init__(self, failure: E3bTaskCorrelationFailure):
        if not isinstance(failure, E3bTaskCorrelationFailure):
            raise TypeError("failure must be E3bTaskCorrelationFailure")
        self.failure = failure
        super().__init__(f"{failure.code.value}: {failure.message}")


@dataclass(frozen=True)
class _TaskIdentity:
    prefix: str
    task_id: int
    role: str
    device: str


@dataclass(frozen=True)
class E3bTaskCorrelationProof:
    schema_version: str
    correlator_id: str
    correlator_semantic_digest: str
    task_prefix: str
    task_id: int
    observation_role: str
    action_role: str
    clock_domain: str
    observation_command_publish_mono_ns: int
    observation_boundary_timestamp_ns: int
    action_publish_mono_ns: int
    observation_fingerprint: str
    historical_action_fingerprint: str
    observation_raw_digest: str
    action_raw_digest: str

    def __post_init__(self) -> None:
        if self.schema_version != E3B_TASK_CORRELATION_SCHEMA:
            raise ValueError("foreign E3b task-correlation proof schema")
        if self.correlator_id != E3B_TASK_CORRELATOR_ID:
            raise ValueError("foreign E3b task correlator")
        if self.correlator_semantic_digest != E3B_TASK_CORRELATOR_SEMANTIC_DIGEST:
            raise ValueError("foreign E3b task-correlation semantics")
        _token("task_prefix", self.task_prefix)
        if isinstance(self.task_id, bool) or not isinstance(self.task_id, int):
            raise TypeError("task_id must be an integer")
        if self.task_id < 0:
            raise ValueError("task_id must be >= 0")
        if self.observation_role != "a" or self.action_role != "b":
            raise ValueError("correlation proof requires the frozen a -> b role pair")
        _token("clock_domain", self.clock_domain)
        for name, value in (
            ("observation_command_publish_mono_ns", self.observation_command_publish_mono_ns),
            ("observation_boundary_timestamp_ns", self.observation_boundary_timestamp_ns),
            ("action_publish_mono_ns", self.action_publish_mono_ns),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.observation_boundary_timestamp_ns <= self.observation_command_publish_mono_ns:
            raise ValueError("observation boundary must follow stage-1 command publication")
        if self.action_publish_mono_ns < self.observation_command_publish_mono_ns:
            raise ValueError("stage-2 action cannot precede the stage-1 command")
        for name, value in (
            ("observation_fingerprint", self.observation_fingerprint),
            ("historical_action_fingerprint", self.historical_action_fingerprint),
            ("observation_raw_digest", self.observation_raw_digest),
            ("action_raw_digest", self.action_raw_digest),
        ):
            _digest(name, value)

    def canonical_record(self) -> dict[str, object]:
        return {
            "schema": self.schema_version,
            "correlator_id": self.correlator_id,
            "correlator_semantic_digest": self.correlator_semantic_digest,
            "task_prefix": self.task_prefix,
            "task_id": self.task_id,
            "observation_role": self.observation_role,
            "action_role": self.action_role,
            "clock_domain": self.clock_domain,
            "observation_command_publish_mono_ns": self.observation_command_publish_mono_ns,
            "observation_boundary_timestamp_ns": self.observation_boundary_timestamp_ns,
            "action_publish_mono_ns": self.action_publish_mono_ns,
            "observation_fingerprint": self.observation_fingerprint,
            "historical_action_fingerprint": self.historical_action_fingerprint,
            "observation_raw_digest": self.observation_raw_digest,
            "action_raw_digest": self.action_raw_digest,
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.canonical_record())

    def fingerprint(self) -> str:
        return _sha256(self.canonical_bytes())


@dataclass(frozen=True)
class E3bCorrelatedRuntimePair:
    schema_version: str
    observation: RealizedObservation
    historical_action: RealizedHistoricalAction
    correlation: E3bTaskCorrelationProof

    def __post_init__(self) -> None:
        if self.schema_version != E3B_CORRELATED_PAIR_SCHEMA:
            raise ValueError("foreign E3b correlated-pair schema")
        if not isinstance(self.observation, RealizedObservation):
            raise TypeError("observation must be RealizedObservation")
        if not isinstance(self.historical_action, RealizedHistoricalAction):
            raise TypeError("historical_action must be RealizedHistoricalAction")
        if not isinstance(self.correlation, E3bTaskCorrelationProof):
            raise TypeError("correlation must be E3bTaskCorrelationProof")
        if self.correlation.observation_fingerprint != self.observation.fingerprint():
            raise ValueError("correlation is bound to a different realized observation")
        if (
            self.correlation.historical_action_fingerprint
            != self.historical_action.fingerprint()
        ):
            raise ValueError("correlation is bound to a different realized historical action")

    def canonical_record(self) -> dict[str, object]:
        return {
            "schema": self.schema_version,
            "observation": self.observation.canonical_record(),
            "historical_action": self.historical_action.canonical_record(),
            "correlation": self.correlation.canonical_record(),
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.canonical_record())

    def fingerprint(self) -> str:
        return _sha256(self.canonical_bytes())


def _parse_device_identity(
    device: str,
    *,
    expected_role: str,
    observation_raw_digest: str,
    action_raw_digest: str,
) -> _TaskIdentity:
    if any(ch in device for ch in ("/", "+", "#", "\x00")):
        _raise_correlation(
            code=E3bTaskCorrelationFailureCode.MALFORMED_IDENTITY,
            message="E3b device identity contains a forbidden MQTT identity character",
            observation_raw_digest=observation_raw_digest,
            action_raw_digest=action_raw_digest,
            details=(("device", device),),
        )
    try:
        prefix, task_text, role = device.rsplit("-", 2)
    except ValueError:
        _raise_correlation(
            code=E3bTaskCorrelationFailureCode.MALFORMED_IDENTITY,
            message="E3b device identity does not encode prefix/task/role",
            observation_raw_digest=observation_raw_digest,
            action_raw_digest=action_raw_digest,
            details=(("device", device),),
        )
    if not prefix:
        _raise_correlation(
            code=E3bTaskCorrelationFailureCode.MALFORMED_IDENTITY,
            message="E3b task prefix is empty",
            observation_raw_digest=observation_raw_digest,
            action_raw_digest=action_raw_digest,
            details=(("device", device),),
        )
    if role != expected_role:
        _raise_correlation(
            code=E3bTaskCorrelationFailureCode.ROLE_MISMATCH,
            message="runtime record has the wrong E3b task role for this stage",
            observation_raw_digest=observation_raw_digest,
            action_raw_digest=action_raw_digest,
            details=(("device", device), ("expected_role", expected_role), ("role", role)),
        )
    if not task_text.isascii() or not task_text.isdigit():
        _raise_correlation(
            code=E3bTaskCorrelationFailureCode.MALFORMED_IDENTITY,
            message="E3b task id is not canonical ASCII decimal",
            observation_raw_digest=observation_raw_digest,
            action_raw_digest=action_raw_digest,
            details=(("task_id_text", task_text),),
        )
    task_id = int(task_text)
    if str(task_id) != task_text:
        _raise_correlation(
            code=E3bTaskCorrelationFailureCode.MALFORMED_IDENTITY,
            message="E3b task id has a noncanonical decimal encoding",
            observation_raw_digest=observation_raw_digest,
            action_raw_digest=action_raw_digest,
            details=(("task_id_text", task_text),),
        )
    return _TaskIdentity(prefix=prefix, task_id=task_id, role=role, device=device)


def _action_device(topic: str) -> str:
    parts = topic.split("/")
    if len(parts) != 3 or parts[0] != "agentmark" or parts[2] != "command":
        raise AssertionError("action realizer admitted a non-E3b command topic")
    return parts[1]


def _raise_correlation(
    *,
    code: E3bTaskCorrelationFailureCode,
    message: str,
    observation_raw_digest: str,
    action_raw_digest: str,
    details: tuple[tuple[str, str | int], ...] = (),
) -> None:
    raise E3bTaskCorrelationError(
        E3bTaskCorrelationFailure(
            schema_version=E3B_TASK_CORRELATION_FAILURE_SCHEMA,
            code=code,
            message=message,
            observation_raw_digest=observation_raw_digest,
            action_raw_digest=action_raw_digest,
            details=details,
        )
    )


def correlate_e3b_runtime_pair(
    raw_observation: object,
    raw_historical_action: object,
) -> E3bCorrelatedRuntimePair:
    """Realize and same-task-bind one E3b observation/action pair.

    Individual realization errors propagate unchanged.  Only after both frozen
    realizers succeed does this function evaluate the new pairwise correlation
    relation.  It never calls the semantic contract.
    """

    observation = realize_e3b_observation(raw_observation)
    historical_action = realize_e3b_historical_action(raw_historical_action)

    observation_record = parse_e3b_observation_record(raw_observation)
    action_record = parse_e3b_historical_action_record(raw_historical_action)
    observation_raw_digest = observation_record.fingerprint()
    action_raw_digest = action_record.fingerprint()

    if (
        observation.provenance.realizer_id != E3B_OBSERVATION_REALIZER_ID
        or observation.provenance.realizer_semantic_digest
        != E3B_OBSERVATION_REALIZER_SEMANTIC_DIGEST
        or observation.provenance.raw_record_digest != observation_raw_digest
    ):
        _raise_correlation(
            code=E3bTaskCorrelationFailureCode.INTERNAL_INCONSISTENCY,
            message="observation realization provenance does not bind to the supplied raw record",
            observation_raw_digest=observation_raw_digest,
            action_raw_digest=action_raw_digest,
        )
    if (
        historical_action.provenance.realizer_id != E3B_ACTION_REALIZER_ID
        or historical_action.provenance.realizer_semantic_digest
        != E3B_ACTION_REALIZER_SEMANTIC_DIGEST
        or historical_action.provenance.raw_record_digest != action_raw_digest
    ):
        _raise_correlation(
            code=E3bTaskCorrelationFailureCode.INTERNAL_INCONSISTENCY,
            message="historical-action realization provenance does not bind to the supplied raw record",
            observation_raw_digest=observation_raw_digest,
            action_raw_digest=action_raw_digest,
        )

    observation_identity = _parse_device_identity(
        observation_record.expected_device,
        expected_role="a",
        observation_raw_digest=observation_raw_digest,
        action_raw_digest=action_raw_digest,
    )
    action_identity = _parse_device_identity(
        _action_device(action_record.topic),
        expected_role="b",
        observation_raw_digest=observation_raw_digest,
        action_raw_digest=action_raw_digest,
    )

    if (
        observation_identity.prefix != action_identity.prefix
        or observation_identity.task_id != action_identity.task_id
    ):
        _raise_correlation(
            code=E3bTaskCorrelationFailureCode.TASK_MISMATCH,
            message="stage-1 observation and stage-2 action belong to different E3b tasks",
            observation_raw_digest=observation_raw_digest,
            action_raw_digest=action_raw_digest,
            details=(
                ("observation_prefix", observation_identity.prefix),
                ("observation_task_id", observation_identity.task_id),
                ("action_prefix", action_identity.prefix),
                ("action_task_id", action_identity.task_id),
            ),
        )

    if observation_record.clock_domain != action_record.clock_domain:
        _raise_correlation(
            code=E3bTaskCorrelationFailureCode.CLOCK_DOMAIN_MISMATCH,
            message="correlated E3b records use different monotonic clock domains",
            observation_raw_digest=observation_raw_digest,
            action_raw_digest=action_raw_digest,
            details=(
                ("observation_clock_domain", observation_record.clock_domain),
                ("action_clock_domain", action_record.clock_domain),
            ),
        )

    if action_record.publish_mono_ns < observation_record.command_publish_mono_ns:
        _raise_correlation(
            code=E3bTaskCorrelationFailureCode.TEMPORAL_INCONSISTENCY,
            message="stage-2 candidate action precedes the same task's stage-1 command",
            observation_raw_digest=observation_raw_digest,
            action_raw_digest=action_raw_digest,
            details=(
                ("stage1_command_publish_mono_ns", observation_record.command_publish_mono_ns),
                ("stage2_publish_mono_ns", action_record.publish_mono_ns),
            ),
        )

    action_coordinates: Mapping[str, object] = historical_action.action.as_dict()
    if (
        action_coordinates.get("task_prefix") != action_identity.prefix
        or action_coordinates.get("task_id") != action_identity.task_id
        or action_coordinates.get("concrete_target") != action_identity.device
    ):
        _raise_correlation(
            code=E3bTaskCorrelationFailureCode.INTERNAL_INCONSISTENCY,
            message="realized action coordinates disagree with independently parsed task identity",
            observation_raw_digest=observation_raw_digest,
            action_raw_digest=action_raw_digest,
        )

    proof = E3bTaskCorrelationProof(
        schema_version=E3B_TASK_CORRELATION_SCHEMA,
        correlator_id=E3B_TASK_CORRELATOR_ID,
        correlator_semantic_digest=E3B_TASK_CORRELATOR_SEMANTIC_DIGEST,
        task_prefix=observation_identity.prefix,
        task_id=observation_identity.task_id,
        observation_role="a",
        action_role="b",
        clock_domain=observation_record.clock_domain,
        observation_command_publish_mono_ns=observation_record.command_publish_mono_ns,
        observation_boundary_timestamp_ns=observation.boundary_timestamp_ns,
        action_publish_mono_ns=action_record.publish_mono_ns,
        observation_fingerprint=observation.fingerprint(),
        historical_action_fingerprint=historical_action.fingerprint(),
        observation_raw_digest=observation_raw_digest,
        action_raw_digest=action_raw_digest,
    )
    return E3bCorrelatedRuntimePair(
        schema_version=E3B_CORRELATED_PAIR_SCHEMA,
        observation=observation,
        historical_action=historical_action,
        correlation=proof,
    )


def e3b_task_correlator_rule_record() -> dict[str, object]:
    return json.loads(_canonical_json_bytes(_RULE_RECORD).decode("utf-8"))


__all__ = (
    "E3B_TASK_CORRELATION_SCHEMA",
    "E3B_CORRELATED_PAIR_SCHEMA",
    "E3B_TASK_CORRELATOR_ID",
    "E3B_TASK_CORRELATOR_SEMANTIC_DIGEST",
    "E3bTaskCorrelationFailureCode",
    "E3bTaskCorrelationFailure",
    "E3bTaskCorrelationError",
    "E3bTaskCorrelationProof",
    "E3bCorrelatedRuntimePair",
    "correlate_e3b_runtime_pair",
    "e3b_task_correlator_rule_record",
)
