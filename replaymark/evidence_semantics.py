from __future__ import annotations

"""Compiler-owned closure of replay-time evidence semantics.

Authoring direction is intentionally *forward*:

    target decision world w -> possible retained evidence tokens O(w)

ReplayMark, not the adapter author, derives the inverse epistemic set

    Omega(e) = {w : e in O(w)}.

This removes the dangerous manual step of enumerating compatible worlds per
observation. The compiler guarantees exact inversion relative to the declared
finite TargetModel domain and the ObservationSupportModel relation.

The remaining trust obligation is external semantic adequacy of O itself. For
support-sound reuse, an adapter may safely over-approximate real observation
possibility, but must not omit a real (world, token) edge.
"""

from dataclasses import dataclass
import hashlib
import json
from typing import Protocol, runtime_checkable

from .contracts import EvidenceSpec, TargetModel


_SCHEMA = "replaymark.evidence-semantics-closure.v1"
_RELATION_SCHEMA = "replaymark.observation-support-relation.v1"
_DOMAIN_SCHEMA = "replaymark.evidence-target-domain.v1"


class EvidenceSemanticsError(ValueError):
    """Base class for fail-closed evidence-semantics compilation errors."""


class InvalidObservationSemanticsError(EvidenceSemanticsError):
    """Raised when the forward observation relation is malformed."""


class IncompleteObservationSemanticsError(EvidenceSemanticsError):
    """Raised when a modeled world has no retained-evidence interpretation."""


class UnstableObservationSemanticsError(EvidenceSemanticsError):
    """Raised when the adapter is not referentially stable during compilation."""


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _token(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidObservationSemanticsError(f"{name} must be a non-empty string")
    if value != value.strip():
        raise InvalidObservationSemanticsError(
            f"{name} must not contain leading/trailing whitespace"
        )
    return value


@runtime_checkable
class ObservationSupportModel(Protocol):
    """Forward finite semantics of retained evidence.

    `observation_support(w)` returns every canonical evidence token that the
    retained-evidence mechanism may emit/preserve when the target is in modeled
    decision world `w`.

    Deterministic evidence returns a singleton tuple. Partial, noisy, or
    multi-mode evidence may return several tokens. The relation is support-level:
    probabilities are intentionally irrelevant to the current theorem.

    The method must be pure/referentially stable for the duration of compilation.
    """

    def observation_support(self, decision_state: str) -> tuple[str, ...]: ...


def _read_support(model: ObservationSupportModel, state: str) -> tuple[str, ...]:
    raw = model.observation_support(state)
    if not isinstance(raw, tuple):
        raise TypeError(
            "ObservationSupportModel.observation_support must return tuple[str, ...]"
        )
    if not raw:
        raise IncompleteObservationSemanticsError(
            f"decision world {state!r} has no retained-evidence token; "
            "represent uncertainty explicitly rather than leaving a world uncovered"
        )
    clean = tuple(_token("evidence token", item) for item in raw)
    if len(set(clean)) != len(clean):
        raise InvalidObservationSemanticsError(
            f"decision world {state!r} returned duplicate evidence tokens"
        )
    return tuple(sorted(clean))


def _invert_relation(
    world_supports: tuple[tuple[str, tuple[str, ...]], ...]
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    buckets: dict[str, list[str]] = {}
    for state, tokens in world_supports:
        for token in tokens:
            buckets.setdefault(token, []).append(state)
    inverse = [
        (token, tuple(sorted(states)))
        for token, states in buckets.items()
    ]
    inverse.sort(key=lambda row: row[0])
    return tuple(inverse)


def _domain_fingerprint(states: tuple[str, ...]) -> str:
    return _sha256({"schema": _DOMAIN_SCHEMA, "decision_states": list(states)})


def _relation_fingerprint(
    world_supports: tuple[tuple[str, tuple[str, ...]], ...]
) -> str:
    return _sha256(
        {
            "schema": _RELATION_SCHEMA,
            "world_observation_supports": [
                {"decision_state": state, "tokens": list(tokens)}
                for state, tokens in world_supports
            ],
        }
    )


@dataclass(frozen=True)
class CompiledEvidenceSemantics:
    """Auditable compiler-derived closure of the finite observation relation."""

    schema_version: str
    evidence_id: str
    target_domain_fingerprint: str
    relation_fingerprint: str
    decision_states: tuple[str, ...]
    world_observation_supports: tuple[tuple[str, tuple[str, ...]], ...]
    evidence_spec: EvidenceSpec

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_spec, EvidenceSpec):
            raise TypeError("evidence_spec must be EvidenceSpec")
        if self.evidence_spec.evidence_id != self.evidence_id:
            raise ValueError("compiled evidence id and EvidenceSpec id differ")
        if not self.decision_states:
            raise ValueError("compiled evidence semantics requires a nonempty target domain")
        if tuple(sorted(self.decision_states)) != self.decision_states:
            raise ValueError("decision_states must be canonical and sorted")
        if len(set(self.decision_states)) != len(self.decision_states):
            raise ValueError("decision_states contains duplicates")

        rows = tuple(sorted(self.world_observation_supports))
        if rows != self.world_observation_supports:
            raise ValueError("world_observation_supports must be canonical and sorted")
        if tuple(state for state, _ in rows) != self.decision_states:
            raise ValueError(
                "world_observation_supports must cover every target decision world exactly once"
            )
        for state, tokens in rows:
            if not tokens:
                raise ValueError(f"decision world {state!r} has empty observation support")
            if tuple(sorted(tokens)) != tokens or len(set(tokens)) != len(tokens):
                raise ValueError(f"decision world {state!r} has noncanonical token support")

        expected_domain = _domain_fingerprint(self.decision_states)
        if self.target_domain_fingerprint != expected_domain:
            raise ValueError("target-domain fingerprint does not match compiled worlds")
        expected_relation = _relation_fingerprint(rows)
        if self.relation_fingerprint != expected_relation:
            raise ValueError("relation fingerprint does not match compiled observation relation")

        expected_inverse = _invert_relation(rows)
        if self.evidence_spec.observations != expected_inverse:
            raise ValueError(
                "EvidenceSpec is not the exact inverse image of the forward observation relation"
            )

    @property
    def world_count(self) -> int:
        return len(self.decision_states)

    @property
    def observation_count(self) -> int:
        return len(self.evidence_spec.observations)

    @property
    def relation_edge_count(self) -> int:
        return sum(len(tokens) for _, tokens in self.world_observation_supports)

    def tokens_for_state(self, decision_state: str) -> tuple[str, ...]:
        state = str(decision_state)
        try:
            return dict(self.world_observation_supports)[state]
        except KeyError as exc:
            raise KeyError(f"unknown target decision world: {state!r}") from exc

    def compatible_states(self, observation: str) -> tuple[str, ...]:
        return self.evidence_spec.compatible_states(observation)

    def canonical_record(self) -> dict[str, object]:
        return {
            "schema": self.schema_version,
            "evidence_id": self.evidence_id,
            "target_domain_fingerprint": self.target_domain_fingerprint,
            "relation_fingerprint": self.relation_fingerprint,
            "decision_states": list(self.decision_states),
            "world_observation_supports": [
                {"decision_state": state, "tokens": list(tokens)}
                for state, tokens in self.world_observation_supports
            ],
            "derived_evidence_spec": self.evidence_spec.canonical_record(),
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.canonical_record())

    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def compile_evidence_semantics(
    target: TargetModel,
    observation_model: ObservationSupportModel,
    *,
    evidence_id: str,
) -> CompiledEvidenceSemantics:
    """Enumerate and invert a forward observation-support model exactly.

    The compiler owns `Omega(e)`. Adapter authors never enumerate compatible
    worlds per token. Every declared target world is queried, and a second pass
    in reverse world order must produce the same support relation. This catches
    accidental stateful/order-dependent evidence adapters before certification.
    """

    if not isinstance(target, TargetModel):
        raise TypeError("target does not satisfy ReplayMark TargetModel protocol")
    if not isinstance(observation_model, ObservationSupportModel):
        raise TypeError("observation_model does not satisfy ObservationSupportModel")
    evidence_id = _token("evidence_id", evidence_id)

    states = tuple(sorted(str(state) for state in target.decision_states))
    if not states:
        raise InvalidObservationSemanticsError(
            "TargetModel.decision_states must not be empty"
        )
    if len(set(states)) != len(states):
        raise InvalidObservationSemanticsError(
            "TargetModel.decision_states contains duplicate identifiers"
        )

    first: dict[str, tuple[str, ...]] = {}
    for state in states:
        first[state] = _read_support(observation_model, state)

    second: dict[str, tuple[str, ...]] = {}
    for state in reversed(states):
        second[state] = _read_support(observation_model, state)

    unstable = tuple(
        state for state in states if first[state] != second[state]
    )
    if unstable:
        raise UnstableObservationSemanticsError(
            "observation semantics changed across repeated compilation passes for: "
            + ", ".join(repr(state) for state in unstable)
        )

    world_supports = tuple((state, first[state]) for state in states)
    inverse = _invert_relation(world_supports)
    evidence_spec = EvidenceSpec(evidence_id=evidence_id, observations=inverse)

    return CompiledEvidenceSemantics(
        schema_version=_SCHEMA,
        evidence_id=evidence_id,
        target_domain_fingerprint=_domain_fingerprint(states),
        relation_fingerprint=_relation_fingerprint(world_supports),
        decision_states=states,
        world_observation_supports=world_supports,
        evidence_spec=evidence_spec,
    )


__all__ = (
    "CompiledEvidenceSemantics",
    "EvidenceSemanticsError",
    "IncompleteObservationSemanticsError",
    "InvalidObservationSemanticsError",
    "ObservationSupportModel",
    "UnstableObservationSemanticsError",
    "compile_evidence_semantics",
)
