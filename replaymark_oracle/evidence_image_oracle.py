from __future__ import annotations

"""Definition-level oracle for evidence images.

This module deliberately does not import replaymark.evidence_image or
replaymark.q_compiler. It computes q_{C,h} by the independent continuation-word
definition oracle, then takes the literal set image of Omega(e).
"""

from dataclasses import dataclass

from replaymark.contracts import ClaimSpec, EvidenceSpec, TargetModel
from replaymark_oracle.definition_q_oracle import definition_partition


class OracleEvidenceOutsideDomainError(ValueError):
    pass


@dataclass(frozen=True)
class OracleObservationImage:
    token: str
    compatible_states: tuple[str, ...]
    semantic_blocks: tuple[tuple[str, ...], ...]

    @property
    def predictive_world_count(self) -> int:
        return len(self.semantic_blocks)


@dataclass(frozen=True)
class OracleEvidenceImage:
    depth: int
    observations: tuple[OracleObservationImage, ...]

    def observation(self, token: str) -> OracleObservationImage:
        token = str(token)
        for row in self.observations:
            if row.token == token:
                return row
        raise KeyError(f"unknown evidence observation: {token!r}")


def definition_evidence_image(
    target: TargetModel,
    claim: ClaimSpec,
    evidence: EvidenceSpec,
    *,
    depth: int | None = None,
) -> OracleEvidenceImage:
    """Compute q_{C,h}[Omega(e)] from the mathematical definition."""

    if not isinstance(target, TargetModel):
        raise TypeError("target does not satisfy ReplayMark TargetModel protocol")
    if not isinstance(claim, ClaimSpec):
        raise TypeError("claim must be ClaimSpec")
    if not isinstance(evidence, EvidenceSpec):
        raise TypeError("evidence must be EvidenceSpec")
    if isinstance(depth, bool):
        raise TypeError("oracle evidence-image depth must be an integer or None")

    depth = claim.horizon if depth is None else int(depth)
    if depth < 0 or depth > claim.horizon:
        raise IndexError(
            f"oracle evidence-image depth {depth} outside claim horizon "
            f"[0,{claim.horizon}]"
        )

    partition = definition_partition(target, claim, depth)
    admitted = set(str(state) for state in target.decision_states)
    state_to_semantic_block: dict[str, tuple[str, ...]] = {}
    for block in partition.blocks:
        for state in block:
            state_to_semantic_block[state] = block

    observations: list[OracleObservationImage] = []
    for token, compatible_states in evidence.observations:
        unknown = tuple(sorted(set(compatible_states) - admitted))
        if unknown:
            raise OracleEvidenceOutsideDomainError(
                f"evidence token {token!r} names target states outside "
                f"the definition domain: {unknown!r}"
            )
        semantic_blocks = tuple(
            sorted(
                {
                    state_to_semantic_block[state]
                    for state in compatible_states
                }
            )
        )
        if not semantic_blocks:
            raise AssertionError("nonempty Omega(e) produced empty definition image")
        observations.append(
            OracleObservationImage(
                token=token,
                compatible_states=tuple(compatible_states),
                semantic_blocks=semantic_blocks,
            )
        )

    observations.sort(key=lambda row: row.token)
    return OracleEvidenceImage(depth=depth, observations=tuple(observations))


__all__ = (
    "OracleEvidenceImage",
    "OracleEvidenceOutsideDomainError",
    "OracleObservationImage",
    "definition_evidence_image",
)
