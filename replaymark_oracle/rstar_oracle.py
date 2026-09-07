from __future__ import annotations

"""Definition-level oracle for ReplayMark maximal certified reuse R*.

This oracle deliberately imports none of the production q, evidence-image,
support-envelope, adjudicator, or R* modules. It computes reuse entitlement
straight from raw compatible target worlds:

    REUSE iff every w in Omega(e) positively supports the recorded projected z.

For every non-reusable pair it exposes at least one excluding raw world. That is
the constructive pointwise witness that any extra fixed-evidence reuse would be
support-unsound.
"""

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from typing import Mapping

from replaymark.contracts import ClaimSpec, EvidenceSpec, ProjectedAction, TargetModel


class OracleReuseDisposition(str, Enum):
    REUSE = "REUSE"
    DO_NOT_REUSE = "DO_NOT_REUSE"


class OracleRStarError(ValueError):
    pass


def _projected_support(
    target: TargetModel,
    claim: ClaimSpec,
    decision_state: str,
) -> frozenset[ProjectedAction]:
    try:
        distribution = target.current_distribution(str(decision_state))
    except KeyError as exc:
        raise OracleRStarError(
            f"target has no current semantics for {decision_state!r}"
        ) from exc
    if not isinstance(distribution, Mapping):
        raise TypeError("current_distribution must return a mapping")

    total = Fraction(0, 1)
    support: set[ProjectedAction] = set()
    for raw_key, raw_mass in distribution.items():
        mass = Fraction(raw_mass)
        if mass < 0:
            raise OracleRStarError(
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
        raise OracleRStarError(
            f"probability mass at current_distribution({decision_state!r}) "
            f"is {total}, expected exactly 1"
        )
    if not support:
        raise OracleRStarError(
            f"empty positive projected support at {decision_state!r}"
        )
    return frozenset(support)


@dataclass(frozen=True)
class OracleRStarDecision:
    observation: str
    projected_action: ProjectedAction
    compatible_worlds: tuple[str, ...]
    supporting_worlds: tuple[str, ...]
    excluding_worlds: tuple[str, ...]
    disposition: OracleReuseDisposition

    def __post_init__(self) -> None:
        if not self.compatible_worlds:
            raise ValueError("R* oracle requires nonempty Omega(e)")
        if set(self.supporting_worlds) & set(self.excluding_worlds):
            raise ValueError("supporting/excluding world sets must be disjoint")
        if set(self.supporting_worlds) | set(self.excluding_worlds) != set(
            self.compatible_worlds
        ):
            raise ValueError("supporting/excluding worlds must partition Omega(e)")
        expected = (
            OracleReuseDisposition.REUSE
            if not self.excluding_worlds
            else OracleReuseDisposition.DO_NOT_REUSE
        )
        if self.disposition is not expected:
            raise ValueError("oracle disposition is inconsistent with raw-world support")

    @property
    def reuse_is_support_sound(self) -> bool:
        return not self.excluding_worlds

    @property
    def maximality_counterexample(self) -> str | None:
        """One world proving that any additional reuse would be unsound."""

        return self.excluding_worlds[0] if self.excluding_worlds else None


def definition_rstar(
    target: TargetModel,
    claim: ClaimSpec,
    evidence: EvidenceSpec,
    observation: str,
    recorded_action: ProjectedAction,
) -> OracleRStarDecision:
    """Compute R*(e,z) directly from raw target support, with no intermediates."""

    if not isinstance(target, TargetModel):
        raise TypeError("target does not satisfy ReplayMark TargetModel protocol")
    if not isinstance(claim, ClaimSpec):
        raise TypeError("claim must be ClaimSpec")
    if not isinstance(evidence, EvidenceSpec):
        raise TypeError("evidence must be EvidenceSpec")
    if not isinstance(recorded_action, ProjectedAction):
        raise TypeError("recorded_action must be ProjectedAction")

    projected = claim.project(recorded_action)
    compatible = evidence.compatible_states(observation)
    admitted = set(str(state) for state in target.decision_states)
    unknown = tuple(sorted(set(compatible) - admitted))
    if unknown:
        raise OracleRStarError(
            f"evidence token {observation!r} names target states outside "
            f"the definition domain: {unknown!r}"
        )

    supporting: list[str] = []
    excluding: list[str] = []
    for state in compatible:
        if projected in _projected_support(target, claim, state):
            supporting.append(state)
        else:
            excluding.append(state)

    disposition = (
        OracleReuseDisposition.REUSE
        if not excluding
        else OracleReuseDisposition.DO_NOT_REUSE
    )
    return OracleRStarDecision(
        observation=observation,
        projected_action=projected,
        compatible_worlds=tuple(compatible),
        supporting_worlds=tuple(supporting),
        excluding_worlds=tuple(excluding),
        disposition=disposition,
    )


__all__ = (
    "OracleRStarDecision",
    "OracleRStarError",
    "OracleReuseDisposition",
    "definition_rstar",
)
