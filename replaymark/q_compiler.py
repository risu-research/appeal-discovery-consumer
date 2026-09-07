from __future__ import annotations

"""Bounded claim-predictive state compiler for finite deterministic targets.

The compiler first takes a compiler-owned semantic snapshot of the complete finite
TargetModel. q_{C,H} is then derived *from that snapshot*, not by re-querying the
provider. This binds the quotient to the exact semantics it consumed and removes
a provider-fingerprint/TOCTOU gap.
"""

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
from typing import Hashable, Mapping, TypeVar

from .contracts import ClaimSpec, ProjectedAction, TargetModel
from .target_provenance import ObservedTargetSemantics, observe_target_semantics


_SCHEMA = "replaymark.qch.deterministic.v2"
K = TypeVar("K", bound=Hashable)


class QCompileError(ValueError):
    """Base class for fail-closed bounded-q compilation errors."""


class NonDeterministicTargetError(QCompileError):
    """Raised when the deterministic compiler sees more than one positive branch."""


class IncompleteTargetError(QCompileError):
    """Raised when an admitted decision state/continuation has no total semantics."""


class InvalidTargetModelError(QCompileError):
    """Raised when the observed TargetModel boundary is malformed."""


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _checked_current_point_mass(
    rows: tuple[tuple[ProjectedAction, str, Fraction], ...],
    *,
    where: str,
) -> tuple[ProjectedAction, str]:
    if len(rows) != 1 or rows[0][2] != 1:
        raise NonDeterministicTargetError(
            "bounded q compiler v2 accepts deterministic point-mass targets only; "
            f"{where} has {len(rows)} positive branches"
        )
    action, post_state, _mass = rows[0]
    return action, post_state


def _checked_advance_point_mass(
    rows: tuple[tuple[str, Fraction], ...],
    *,
    where: str,
) -> str:
    if len(rows) != 1 or rows[0][1] != 1:
        raise NonDeterministicTargetError(
            "bounded q compiler v2 accepts deterministic point-mass targets only; "
            f"{where} has {len(rows)} positive branches"
        )
    return rows[0][0]


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
    target_semantic_digest: str
    target_snapshot_fingerprint: str
    target_domain_digest: str
    target_current_semantics_digest: str
    target_advance_semantics_digest: str
    decision_states: tuple[str, ...]
    continuation_alphabet: tuple[str, ...]
    layers: tuple[PartitionLayer, ...]
    current_projected_actions: tuple[tuple[str, ProjectedAction], ...]
    deterministic_successors: tuple[tuple[str, tuple[tuple[str, str], ...]], ...]
    first_observed_fixed_point: int | None

    @property
    def horizon(self) -> int:
        return self.claim.horizon

    @property
    def provider_fingerprint(self) -> str:
        """Provider-supplied metadata; not the semantic provenance authority."""
        return self.target_model_fingerprint

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
            "target_provenance": {
                "provider_fingerprint": self.target_model_fingerprint,
                "compiler_observed_semantic_digest": self.target_semantic_digest,
                "snapshot_fingerprint": self.target_snapshot_fingerprint,
                "component_digests": {
                    "domain": self.target_domain_digest,
                    "current": self.target_current_semantics_digest,
                    "advance": self.target_advance_semantics_digest,
                },
            },
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


def _compile_observed_q(
    observed: ObservedTargetSemantics,
    claim: ClaimSpec,
) -> BoundedQuotient:
    states = observed.decision_states
    continuations = observed.declared_continuation_order
    if claim.horizon > 0 and not continuations:
        raise IncompleteTargetError(
            "positive consequence horizon requires at least one admitted continuation"
        )

    current_actions: dict[str, ProjectedAction] = {}
    post_states: dict[str, str] = {}
    for state in states:
        full_action, post_state = _checked_current_point_mass(
            observed.current_law(state),
            where=f"observed current law for {state!r}",
        )
        current_actions[state] = claim.project(full_action)
        post_states[state] = post_state

    successors: dict[str, dict[str, str]] = {state: {} for state in states}
    if claim.horizon > 0:
        for state in states:
            post_state = post_states[state]
            for continuation in continuations:
                next_state = _checked_advance_point_mass(
                    observed.advance_law(post_state, continuation),
                    where=(
                        f"observed advance law for post_state={post_state!r}, "
                        f"continuation={continuation!r}"
                    ),
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
            tuple(
                (u, successors[state][u])
                for u in continuations
                if u in successors[state]
            ),
        )
        for state in states
    )
    return BoundedQuotient(
        schema_version=_SCHEMA,
        claim=claim,
        target_model_fingerprint=observed.provider_fingerprint,
        target_semantic_digest=observed.semantic_digest,
        target_snapshot_fingerprint=observed.fingerprint(),
        target_domain_digest=observed.domain_digest,
        target_current_semantics_digest=observed.current_semantics_digest,
        target_advance_semantics_digest=observed.advance_semantics_digest,
        decision_states=states,
        continuation_alphabet=continuations,
        layers=tuple(layers),
        current_projected_actions=tuple(
            (state, current_actions[state]) for state in states
        ),
        deterministic_successors=successor_rows,
        first_observed_fixed_point=first_fixed,
    )


def compile_bounded_q(
    target: TargetModel,
    claim: ClaimSpec,
) -> BoundedQuotient:
    """Observe the target once, then compile exactly q_{C,H} from that snapshot.

    The target semantic digest is compiler-derived from the complete finite
    two-phase model before claim projection. q compilation consumes only this
    sealed snapshot, so the digest and quotient cannot describe different target
    semantics because of a second provider query.
    """

    if not isinstance(target, TargetModel):
        raise TypeError("target does not satisfy ReplayMark TargetModel protocol")
    if not isinstance(claim, ClaimSpec):
        raise TypeError("claim must be ClaimSpec")
    observed = observe_target_semantics(target)
    return _compile_observed_q(observed, claim)


__all__ = (
    "BoundedQuotient",
    "PartitionLayer",
    "QCompileError",
    "NonDeterministicTargetError",
    "IncompleteTargetError",
    "InvalidTargetModelError",
    "compile_bounded_q",
)
