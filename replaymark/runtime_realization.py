from __future__ import annotations

"""Runtime realization boundary values.

This module freezes the semantic seam between raw runtime artifacts and the
already-proved ReplayMark CompiledContract.  It deliberately defines value
certificates and structured realization failures only.  It does not parse any
specific substrate, execute an action, choose a fallback, or reinterpret
semantic UNRESOLVED as a realization failure.

The first concrete observation realizer is implemented separately for E3b.
Historical-action realization and the bridge that constructs
RuntimeReuseCertificate are future steps.
"""

from dataclasses import dataclass
from enum import Enum
import hashlib
import json

from .adjudicator import Adjudication
from .contracts import ProjectedAction, Scalar
from .rstar import RStarDecision


_PROVENANCE_SCHEMA = "replaymark.runtime.realization-provenance.v1"
_OBSERVATION_SCHEMA = "replaymark.runtime.realized-observation.v1"
_ACTION_SCHEMA = "replaymark.runtime.realized-historical-action.v1"
_RUNTIME_CERT_SCHEMA = "replaymark.runtime.reuse-certificate.v1"
_FAILURE_SCHEMA = "replaymark.runtime.realization-failure.v1"


def _token(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{name} must be a non-empty canonical string")
    return value


def _ns(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer nanosecond timestamp")
    if value < 0:
        raise ValueError(f"{name} must be >= 0")
    return value


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _details_record(details: tuple[tuple[str, Scalar], ...]) -> list[dict[str, object]]:
    return [{"name": key, "value": value} for key, value in details]


class RealizationStage(str, Enum):
    OBSERVATION = "OBSERVATION"
    HISTORICAL_ACTION = "HISTORICAL_ACTION"


class RealizationFailureCode(str, Enum):
    """Failure classes before semantic adjudication.

    None of these values is a ReplayMark Verdict. A realization failure means
    the semantic contract has no admitted `(e, z)` input yet.
    """

    MALFORMED_INPUT = "MALFORMED_INPUT"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    DUPLICATE_INPUT = "DUPLICATE_INPUT"
    CLOCK_DOMAIN_MISMATCH = "CLOCK_DOMAIN_MISMATCH"
    OUT_OF_BOUNDARY = "OUT_OF_BOUNDARY"
    AMBIGUOUS_REALIZATION = "AMBIGUOUS_REALIZATION"
    UNKNOWN_SEMANTIC_VALUE = "UNKNOWN_SEMANTIC_VALUE"
    INTERNAL_INCONSISTENCY = "INTERNAL_INCONSISTENCY"


@dataclass(frozen=True)
class RealizationFailure:
    schema_version: str
    stage: RealizationStage
    code: RealizationFailureCode
    realizer_id: str
    message: str
    raw_record_digest: str | None
    details: tuple[tuple[str, Scalar], ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != _FAILURE_SCHEMA:
            raise ValueError("foreign realization-failure schema")
        if not isinstance(self.stage, RealizationStage):
            raise TypeError("stage must be RealizationStage")
        if not isinstance(self.code, RealizationFailureCode):
            raise TypeError("code must be RealizationFailureCode")
        _token("realizer_id", self.realizer_id)
        _token("message", self.message)
        if self.raw_record_digest is not None:
            digest = _token("raw_record_digest", self.raw_record_digest)
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise ValueError("raw_record_digest must be lowercase sha256 hex")
        seen: set[str] = set()
        normalized: list[tuple[str, Scalar]] = []
        for key, value in self.details:
            key = _token("failure detail name", key)
            if key in seen:
                raise ValueError(f"duplicate failure detail: {key!r}")
            if isinstance(value, float) or not (
                value is None or isinstance(value, (str, int, bool))
            ):
                raise TypeError("failure detail values must be canonical scalar values")
            seen.add(key)
            normalized.append((key, value))
        object.__setattr__(self, "details", tuple(sorted(normalized)))

    def canonical_record(self) -> dict[str, object]:
        return {
            "schema": self.schema_version,
            "stage": self.stage.value,
            "code": self.code.value,
            "realizer_id": self.realizer_id,
            "message": self.message,
            "raw_record_digest": self.raw_record_digest,
            "details": _details_record(self.details),
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.canonical_record())

    def fingerprint(self) -> str:
        return _sha256_bytes(self.canonical_bytes())


class RealizationError(ValueError):
    """Raised when raw runtime data cannot be admitted to semantic adjudication."""

    def __init__(self, failure: RealizationFailure):
        if not isinstance(failure, RealizationFailure):
            raise TypeError("failure must be RealizationFailure")
        self.failure = failure
        super().__init__(
            f"{failure.stage.value}:{failure.code.value}: {failure.message}"
        )


@dataclass(frozen=True)
class RealizationProvenance:
    """Content-addressed provenance of one successful realization."""

    schema_version: str
    stage: RealizationStage
    realizer_id: str
    realizer_semantic_digest: str
    source_schema: str
    raw_record_digest: str

    def __post_init__(self) -> None:
        if self.schema_version != _PROVENANCE_SCHEMA:
            raise ValueError("foreign realization-provenance schema")
        if not isinstance(self.stage, RealizationStage):
            raise TypeError("stage must be RealizationStage")
        _token("realizer_id", self.realizer_id)
        _token("source_schema", self.source_schema)
        for name, value in (
            ("realizer_semantic_digest", self.realizer_semantic_digest),
            ("raw_record_digest", self.raw_record_digest),
        ):
            digest = _token(name, value)
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise ValueError(f"{name} must be lowercase sha256 hex")

    def canonical_record(self) -> dict[str, object]:
        return {
            "schema": self.schema_version,
            "stage": self.stage.value,
            "realizer_id": self.realizer_id,
            "realizer_semantic_digest": self.realizer_semantic_digest,
            "source_schema": self.source_schema,
            "raw_record_digest": self.raw_record_digest,
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.canonical_record())

    def fingerprint(self) -> str:
        return _sha256_bytes(self.canonical_bytes())


@dataclass(frozen=True)
class RealizedObservation:
    """A canonical evidence token plus the runtime boundary that justified it."""

    schema_version: str
    evidence_token: str
    clock_domain: str
    boundary_timestamp_ns: int
    source_event_timestamp_ns: int | None
    provenance: RealizationProvenance

    def __post_init__(self) -> None:
        if self.schema_version != _OBSERVATION_SCHEMA:
            raise ValueError("foreign realized-observation schema")
        _token("evidence_token", self.evidence_token)
        _token("clock_domain", self.clock_domain)
        boundary = _ns("boundary_timestamp_ns", self.boundary_timestamp_ns)
        if self.source_event_timestamp_ns is not None:
            source = _ns("source_event_timestamp_ns", self.source_event_timestamp_ns)
            if source > boundary:
                raise ValueError(
                    "source event occurs after the realized observation boundary"
                )
        if not isinstance(self.provenance, RealizationProvenance):
            raise TypeError("provenance must be RealizationProvenance")
        if self.provenance.stage is not RealizationStage.OBSERVATION:
            raise ValueError("observation requires OBSERVATION realization provenance")

    def canonical_record(self) -> dict[str, object]:
        return {
            "schema": self.schema_version,
            "evidence_token": self.evidence_token,
            "clock_domain": self.clock_domain,
            "boundary_timestamp_ns": self.boundary_timestamp_ns,
            "source_event_timestamp_ns": self.source_event_timestamp_ns,
            "provenance": self.provenance.canonical_record(),
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.canonical_record())

    def fingerprint(self) -> str:
        return _sha256_bytes(self.canonical_bytes())


@dataclass(frozen=True)
class RealizedHistoricalAction:
    """Claim-independent canonicalization of one concrete historical action.

    The action may contain coordinates beyond a benchmark claim. The compiled
    contract remains responsible for claim projection. No action realizer is
    implemented in the current observation-only increment.
    """

    schema_version: str
    action: ProjectedAction
    provenance: RealizationProvenance

    def __post_init__(self) -> None:
        if self.schema_version != _ACTION_SCHEMA:
            raise ValueError("foreign realized-historical-action schema")
        if not isinstance(self.action, ProjectedAction):
            raise TypeError("action must be ProjectedAction")
        if not isinstance(self.provenance, RealizationProvenance):
            raise TypeError("provenance must be RealizationProvenance")
        if self.provenance.stage is not RealizationStage.HISTORICAL_ACTION:
            raise ValueError(
                "historical action requires HISTORICAL_ACTION realization provenance"
            )

    def canonical_record(self) -> dict[str, object]:
        return {
            "schema": self.schema_version,
            "action": self.action.as_dict(),
            "provenance": self.provenance.canonical_record(),
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.canonical_record())

    def fingerprint(self) -> str:
        return _sha256_bytes(self.canonical_bytes())


@dataclass(frozen=True)
class RuntimeReuseCertificate:
    """Audit chain joining realization provenance to a semantic R* result.

    This type contains no execution choice. In particular DO_NOT_REUSE is not
    converted to regenerate/fallback/abort, and a realization failure cannot be
    represented as semantic UNRESOLVED.
    """

    schema_version: str
    contract_fingerprint: str
    claim_fingerprint: str
    observation: RealizedObservation
    historical_action: RealizedHistoricalAction
    adjudication: Adjudication
    reuse_decision: RStarDecision

    def __post_init__(self) -> None:
        if self.schema_version != _RUNTIME_CERT_SCHEMA:
            raise ValueError("foreign runtime reuse-certificate schema")
        _token("contract_fingerprint", self.contract_fingerprint)
        _token("claim_fingerprint", self.claim_fingerprint)
        if not isinstance(self.observation, RealizedObservation):
            raise TypeError("observation must be RealizedObservation")
        if not isinstance(self.historical_action, RealizedHistoricalAction):
            raise TypeError("historical_action must be RealizedHistoricalAction")
        if not isinstance(self.adjudication, Adjudication):
            raise TypeError("adjudication must be Adjudication")
        if not isinstance(self.reuse_decision, RStarDecision):
            raise TypeError("reuse_decision must be RStarDecision")

        if self.adjudication.claim_fingerprint != self.claim_fingerprint:
            raise ValueError("adjudication is bound to a different claim")
        if self.reuse_decision.claim_fingerprint != self.claim_fingerprint:
            raise ValueError("R* decision is bound to a different claim")
        if self.adjudication.token != self.observation.evidence_token:
            raise ValueError("adjudication token does not match realized observation")
        if self.reuse_decision.token != self.observation.evidence_token:
            raise ValueError("R* token does not match realized observation")
        if self.reuse_decision.adjudication_fingerprint != self.adjudication.fingerprint():
            raise ValueError("R* decision is not derived from the embedded adjudication")
        if self.reuse_decision.projected_action != self.adjudication.projected_action:
            raise ValueError("R* and adjudication projected actions disagree")
        if self.reuse_decision.verdict is not self.adjudication.verdict:
            raise ValueError("R* decision does not preserve adjudication verdict")
        if self.reuse_decision.depth != self.adjudication.depth:
            raise ValueError("R* and adjudication depths disagree")
        if (
            self.reuse_decision.support_envelope_fingerprint
            != self.adjudication.support_envelope_fingerprint
        ):
            raise ValueError("R* and adjudication support authorities disagree")
        if self.reuse_decision.evidence_fingerprint != self.adjudication.evidence_fingerprint:
            raise ValueError("R* and adjudication evidence authorities disagree")

        full = self.historical_action.action.as_dict()
        for dimension, value in self.adjudication.projected_action.dimensions:
            if dimension not in full or full[dimension] != value:
                raise ValueError(
                    "adjudication projection is inconsistent with realized historical action"
                )

    def canonical_record(self) -> dict[str, object]:
        return {
            "schema": self.schema_version,
            "contract_fingerprint": self.contract_fingerprint,
            "claim_fingerprint": self.claim_fingerprint,
            "observation": self.observation.canonical_record(),
            "historical_action": self.historical_action.canonical_record(),
            "adjudication": self.adjudication.canonical_record(),
            "reuse_decision": self.reuse_decision.canonical_record(),
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.canonical_record())

    def fingerprint(self) -> str:
        return _sha256_bytes(self.canonical_bytes())


def observation_provenance(
    *,
    realizer_id: str,
    realizer_semantic_digest: str,
    source_schema: str,
    raw_record_digest: str,
) -> RealizationProvenance:
    return RealizationProvenance(
        schema_version=_PROVENANCE_SCHEMA,
        stage=RealizationStage.OBSERVATION,
        realizer_id=realizer_id,
        realizer_semantic_digest=realizer_semantic_digest,
        source_schema=source_schema,
        raw_record_digest=raw_record_digest,
    )


def historical_action_provenance(
    *,
    realizer_id: str,
    realizer_semantic_digest: str,
    source_schema: str,
    raw_record_digest: str,
) -> RealizationProvenance:
    return RealizationProvenance(
        schema_version=_PROVENANCE_SCHEMA,
        stage=RealizationStage.HISTORICAL_ACTION,
        realizer_id=realizer_id,
        realizer_semantic_digest=realizer_semantic_digest,
        source_schema=source_schema,
        raw_record_digest=raw_record_digest,
    )


def realized_observation(
    *,
    evidence_token: str,
    clock_domain: str,
    boundary_timestamp_ns: int,
    source_event_timestamp_ns: int | None,
    provenance: RealizationProvenance,
) -> RealizedObservation:
    return RealizedObservation(
        schema_version=_OBSERVATION_SCHEMA,
        evidence_token=evidence_token,
        clock_domain=clock_domain,
        boundary_timestamp_ns=boundary_timestamp_ns,
        source_event_timestamp_ns=source_event_timestamp_ns,
        provenance=provenance,
    )


__all__ = (
    "RealizationStage",
    "RealizationFailureCode",
    "RealizationFailure",
    "RealizationError",
    "RealizationProvenance",
    "RealizedObservation",
    "RealizedHistoricalAction",
    "RuntimeReuseCertificate",
)
