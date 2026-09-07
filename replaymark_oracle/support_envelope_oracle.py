from __future__ import annotations

"""Definition-level support-envelope oracle.

This module deliberately bypasses production q/evidence/support compilers. For
each raw target world in Omega(e), it computes projected current support directly
from TargetModel.current_distribution and then takes literal intersection/union.

The oracle therefore also covers finite stochastic current decisions, even though
the production bounded-q pipeline intentionally remains deterministic in v1.
"""

from dataclasses import dataclass
from fractions import Fraction
import json
from typing import Mapping

from replaymark.contracts import ClaimSpec, EvidenceSpec, ProjectedAction, TargetModel


class OracleSupportEnvelopeError(ValueError):
    pass


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _action_key(action: ProjectedAction) -> bytes:
    return _canonical_json_bytes(action.as_dict())


def _sorted_actions(actions) -> tuple[ProjectedAction, ...]:
    unique: dict[bytes, ProjectedAction] = {}
    for action in actions:
        if not isinstance(action, ProjectedAction):
            raise TypeError("support elements must be ProjectedAction")
        unique[_action_key(action)] = action
    return tuple(unique[key] for key in sorted(unique))


def projected_current_support(
    target: TargetModel,
    claim: ClaimSpec,
    decision_state: str,
) -> tuple[ProjectedAction, ...]:
    """Literal S_C(w): positive projected support at one raw target world."""

    try:
        distribution = target.current_distribution(str(decision_state))
    except KeyError as exc:
        raise OracleSupportEnvelopeError(
            f"target has no current semantics for {decision_state!r}"
        ) from exc
    if not isinstance(distribution, Mapping):
        raise TypeError("current_distribution must return a mapping")

    total = Fraction(0, 1)
    support: set[ProjectedAction] = set()
    for raw_key, raw_mass in distribution.items():
        mass = Fraction(raw_mass)
        if mass < 0:
            raise OracleSupportEnvelopeError(
                f"negative probability at current_distribution({decision_state!r})"
            )
        total += mass
        if mass == 0:
            continue
        if not isinstance(raw_key, tuple) or len(raw_key) != 2:
            raise TypeError(
                "current_distribution keys must be (ProjectedAction, post_state)"
            )
        action, _post_state = raw_key
        if not isinstance(action, ProjectedAction):
            raise TypeError("current_distribution action is not ProjectedAction")
        support.add(claim.project(action))

    if total != 1:
        raise OracleSupportEnvelopeError(
            f"probability mass at current_distribution({decision_state!r}) "
            f"is {total}, expected exactly 1"
        )
    if not support:
        raise OracleSupportEnvelopeError(
            f"empty positive projected support at {decision_state!r}"
        )
    return _sorted_actions(support)


@dataclass(frozen=True)
class OracleObservationSupportEnvelope:
    token: str
    compatible_states: tuple[str, ...]
    world_supports: tuple[tuple[str, tuple[ProjectedAction, ...]], ...]
    guaranteed_support: tuple[ProjectedAction, ...]
    possible_support: tuple[ProjectedAction, ...]


@dataclass(frozen=True)
class OracleSupportEnvelope:
    observations: tuple[OracleObservationSupportEnvelope, ...]

    def observation(self, token: str) -> OracleObservationSupportEnvelope:
        token = str(token)
        for row in self.observations:
            if row.token == token:
                return row
        raise KeyError(f"unknown evidence observation: {token!r}")


def definition_support_envelope(
    target: TargetModel,
    claim: ClaimSpec,
    evidence: EvidenceSpec,
) -> OracleSupportEnvelope:
    """Compute S^- and S^+ literally over raw worlds in Omega(e)."""

    if not isinstance(target, TargetModel):
        raise TypeError("target does not satisfy ReplayMark TargetModel protocol")
    if not isinstance(claim, ClaimSpec):
        raise TypeError("claim must be ClaimSpec")
    if not isinstance(evidence, EvidenceSpec):
        raise TypeError("evidence must be EvidenceSpec")

    admitted = set(str(state) for state in target.decision_states)
    observations: list[OracleObservationSupportEnvelope] = []

    for token, compatible_states in evidence.observations:
        unknown = tuple(sorted(set(compatible_states) - admitted))
        if unknown:
            raise OracleSupportEnvelopeError(
                f"evidence token {token!r} names target states outside "
                f"the definition domain: {unknown!r}"
            )

        world_rows: list[tuple[str, tuple[ProjectedAction, ...]]] = []
        support_sets: list[set[ProjectedAction]] = []
        for state in compatible_states:
            support = projected_current_support(target, claim, state)
            world_rows.append((state, support))
            support_sets.append(set(support))

        if not support_sets:
            raise AssertionError("EvidenceSpec invariant violated: empty Omega(e)")

        guaranteed = set(support_sets[0])
        possible: set[ProjectedAction] = set()
        for support in support_sets:
            guaranteed.intersection_update(support)
            possible.update(support)

        if not possible:
            raise AssertionError("nonempty Omega(e) produced empty possible support")

        observations.append(
            OracleObservationSupportEnvelope(
                token=token,
                compatible_states=tuple(compatible_states),
                world_supports=tuple(world_rows),
                guaranteed_support=_sorted_actions(guaranteed),
                possible_support=_sorted_actions(possible),
            )
        )

    observations.sort(key=lambda row: row.token)
    return OracleSupportEnvelope(observations=tuple(observations))


__all__ = (
    "OracleObservationSupportEnvelope",
    "OracleSupportEnvelope",
    "OracleSupportEnvelopeError",
    "definition_support_envelope",
    "projected_current_support",
)
