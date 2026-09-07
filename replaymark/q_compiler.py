from __future__ import annotations

"""Bounded claim-predictive state compiler for finite deterministic targets.

This module implements exactly q_{C,H}: current claim-projected output plus all
claim-projected output continuations through the *declared* horizon H. It does
not run to an unrequested fixed point and it does not reuse AgentMark's legacy
full-behavior minimizer.
"""

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
from typing import Hashable, Mapping, TypeVar

from .contracts import ClaimSpec, ProjectedAction, TargetModel


_SCHEMA = "replaymark.qch.deterministic.v1"
K = TypeVar("K", bound=Hashable)


class QCompileError(ValueError):
    """Base class for fail-closed bounded-q compilation errors."""


class NonDeterministicTargetError(QCompileError):
    """Raised when the deterministic compiler sees more than one positive branch."""


class IncompleteTargetError(QCompileError):
    """Raised when an admitted decision state/continuation has no total semantics."""


class InvalidTargetModelError(QCompileError):
    """Raised when the TargetModel boundary is malformed or probability mass is invalid."""


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _checked_point_mass(
    distribution: Mapping[K, Fraction],
    *,
    where: str,
) -> K:
    positive: list[tuple[K, Fraction]] = []
    total = Fraction(0, 1)
    for key, raw_mass in distribution.items():
        mass = Fraction(raw_mass)
        if mass < 0:
            raise InvalidTargetModelError(f"negative probability at {where}: {mass}")
        total += mass
        if mass > 0:
            positive.append((key, mass))
    if total != 1:
        raise InvalidTargetModelError(
            f"probability mass at {where} is {total}, expected exactly 1"
        )
    if not positive:
        raise IncompleteTargetError(f"no positive semantic branch at {where}")
    if len(positive) != 1 or positive[0][1] != 1:
        raise NonDeterministicTargetError(
            f"bounded q compiler v1 accepts deterministic point-mass targets only; "
            f"{where} has {len(positive)} positive branches"
        )
    return positive[0][0]


def _partition_groups(state_to_block: Mapping[str, str]) -> tuple[tuple[str, ...], ...]:
    buckets: dict[str, list[str]] = {}
    for state, block in state_to_block.items():
        buckets.setdefault(block, []).append(state)
    groups = [tuple(sorted(members)) for members in buckets.values()]
    groups.sort()
    return tuple(groups)


def _same_partition(left: "PartitionLayer", right: "PartitionLayer") -> bool:
    return _partition_groups(dict(left.state_to_block)) == _partition_groups(
        dict(right.state_to_block)
    )


def _make_layer(
    depth: int,
    states: tuple[str, ...],
    signatures: Mapping[str, Hashable],
) -> "PartitionLayer":
    buckets: dict[Hashable, list[str]] = {}
    for state in states:
        buckets.setdefault(signatures[state], []).append(state)
    groups = [tuple(sorted(members)) for members in buckets.values()]
    groups.sort()
    blocks: list[tuple[str, tuple[str, ...]]] = []
    state_to_block: list[tuple[str, str]] = []
    for index, members in enumerate(groups):
        block_id = f"q{depth}_{index}"
        blocks.append((block_id, members))
        state_to_block.extend((state, block_id) for state in members)
    state_to_block.sort()
    return PartitionLayer(
        depth=depth,
        state_to_block=tuple(state_to_block),
        blocks=tuple(blocks),
    )


@dataclass(frozen=True)
class PartitionLayer:
    """One exact horizon-indexed partition relation."""

    depth: int
    state_to_block: tuple[tuple[str, str], ...]
    blocks: tuple[tuple[str, tuple[str, ...]], ...]

    @property
    def block_count(self) -> int:
        return len(self.blocks)

    def block_of(self, decision_state: str) -> str:
        try:
            return dict(self.state_to_block)[str(decision_state)]
        except KeyError as exc:
            raise KeyError(f"unknown decision state: {decision_state!r}") from exc

    def equivalent(self, left: str, right: str) -> bool:
        return self.block_of(left) == self.block_of(right)

    def canonical_record(self) -> dict[str, object]:
        return {
            "depth": self.depth,
            "blocks": [
                {"id": block, "decision_states": list(members)}
                for block, members in self.blocks
            ],
        }


@dataclass(frozen=True)
class BoundedQuotient:
    """Auditable result of exact bounded deterministic q_{C,H} compilation."""

    schema_version: str
    claim: ClaimSpec
    target_model_fingerprint: str
    decision_states: tuple[str, ...]
    continuation_alphabet: tuple[str, ...]
    layers: tuple[PartitionLayer, ...]
    current_projected_actions: tuple[tuple[str, ProjectedAction], ...]
    deterministic_successors: tuple[tuple[str, tuple[tuple[str, str], ...]], ...]
    first_observed_fixed_point: int | None

    @property
    def horizon(self) -> int:
        return self.claim.horizon

    def layer(self, depth: int | None = None) -> PartitionLayer:
        depth = self.horizon if depth is None else int(depth)
        if depth < 0 or depth > self.horizon:
            raise IndexError(
                f"depth {depth} outside compiled horizon [0,{self.horizon}]"
            )
        return self.layers[depth]

    def block_count(self, depth: int | None = None) -> int:
        return self.layer(depth).block_count

    def equivalent(self, left: str, right: str, depth: int | None = None) -> bool:
        return self.layer(depth).equivalent(left, right)

    def canonical_record(self) -> dict[str, object]:
        return {
            "schema": self.schema_version,
            "claim": self.claim.canonical_record(),
            "claim_fingerprint": self.claim.fingerprint(),
            "target_model_fingerprint": self.target_model_fingerprint,
            "horizon": self.horizon,
            "decision_states": list(self.decision_states),
            "continuation_alphabet": list(self.continuation_alphabet),
            "current_projected_actions": [
                {"decision_state": state, "action": action.as_dict()}
                for state, action in self.current_projected_actions
            ],
            "deterministic_successors": [
                {
                    "decision_state": state,
                    "successors": [
                        {"continuation": continuation, "next_decision_state": nxt}
                        for continuation, nxt in rows
                    ],
                }
                for state, rows in self.deterministic_successors
            ],
            "layers": [layer.canonical_record() for layer in self.layers],
            "first_observed_fixed_point": self.first_observed_fixed_point,
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_json_bytes(self.canonical_record())

    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def compile_bounded_q(
    target: TargetModel,
    claim: ClaimSpec,
) -> BoundedQuotient:
    """Compile exactly q_{C,H} for a finite deterministic two-phase target.

    The algorithm is bounded Moore-style refinement:

      q_0(s) = current claim-projected output
      q_h(s) = (current output, q_{h-1}(next(s,u)) for every admitted u)

    It computes layers 0..H and performs no hidden H+1 lookahead. A fixed point
    is reported only if equality of two adjacent *computed* partition relations
    was observed within that requested horizon.
    """

    if not isinstance(target, TargetModel):
        raise TypeError("target does not satisfy ReplayMark TargetModel protocol")
    if not isinstance(claim, ClaimSpec):
        raise TypeError("claim must be ClaimSpec")

    states = tuple(sorted(str(s) for s in target.decision_states))
    if not states:
        raise InvalidTargetModelError("TargetModel.decision_states must not be empty")
    if len(set(states)) != len(states):
        raise InvalidTargetModelError("TargetModel.decision_states contains duplicates")

    continuations = tuple(str(u) for u in target.continuation_alphabet)
    if len(set(continuations)) != len(continuations):
        raise InvalidTargetModelError("TargetModel.continuation_alphabet contains duplicates")
    if claim.horizon > 0 and not continuations:
        raise IncompleteTargetError(
            "positive consequence horizon requires at least one admitted continuation"
        )

    state_set = set(states)
    current_actions: dict[str, ProjectedAction] = {}
    post_states: dict[str, str] = {}
    for state in states:
        try:
            key = _checked_point_mass(
                target.current_distribution(state),
                where=f"current_distribution({state!r})",
            )
        except KeyError as exc:
            raise IncompleteTargetError(
                f"missing current semantics for decision state {state!r}"
            ) from exc
        if not isinstance(key, tuple) or len(key) != 2:
            raise InvalidTargetModelError(
                "current_distribution keys must be (ProjectedAction, post_state)"
            )
        action, post_state = key
        if not isinstance(action, ProjectedAction):
            raise InvalidTargetModelError(
                f"current action at {state!r} is not ProjectedAction"
            )
        current_actions[state] = claim.project(action)
        post_states[state] = str(post_state)

    successors: dict[str, dict[str, str]] = {state: {} for state in states}
    if claim.horizon > 0:
        for state in states:
            post_state = post_states[state]
            for continuation in continuations:
                try:
                    nxt = _checked_point_mass(
                        target.advance_distribution(post_state, continuation),
                        where=(
                            f"advance_distribution({post_state!r},"
                            f" {continuation!r}) from {state!r}"
                        ),
                    )
                except KeyError as exc:
                    raise IncompleteTargetError(
                        "admitted continuation lacks target semantics: "
                        f"state={state!r}, post={post_state!r}, "
                        f"continuation={continuation!r}"
                    ) from exc
                next_state = str(nxt)
                if next_state not in state_set:
                    raise InvalidTargetModelError(
                        "advance_distribution reached undeclared decision state: "
                        f"{next_state!r}"
                    )
                successors[state][continuation] = next_state

    signatures0: dict[str, Hashable] = {
        state: current_actions[state].canonical_key() for state in states
    }
    layers: list[PartitionLayer] = [_make_layer(0, states, signatures0)]
    first_fixed: int | None = None

    for depth in range(1, claim.horizon + 1):
        previous = layers[-1]
        previous_blocks = dict(previous.state_to_block)
        signatures: dict[str, Hashable] = {}
        for state in states:
            successor_signature = tuple(
                (
                    continuation,
                    previous_blocks[successors[state][continuation]],
                )
                for continuation in continuations
            )
            signatures[state] = (
                current_actions[state].canonical_key(),
                successor_signature,
            )
        layer = _make_layer(depth, states, signatures)
        if first_fixed is None and _same_partition(previous, layer):
            first_fixed = depth - 1
        layers.append(layer)

    successor_rows = tuple(
        (
            state,
            tuple((u, successors[state][u]) for u in continuations if u in successors[state]),
        )
        for state in states
    )
    return BoundedQuotient(
        schema_version=_SCHEMA,
        claim=claim,
        target_model_fingerprint=str(target.fingerprint),
        decision_states=states,
        continuation_alphabet=continuations,
        layers=tuple(layers),
        current_projected_actions=tuple(
            (state, current_actions[state]) for state in states
        ),
        deterministic_successors=successor_rows,
        first_observed_fixed_point=first_fixed,
    )


__all__ = (
    "BoundedQuotient",
    "PartitionLayer",
    "QCompileError",
    "NonDeterministicTargetError",
    "IncompleteTargetError",
    "InvalidTargetModelError",
    "compile_bounded_q",
)
