from __future__ import annotations

"""Raw-definition oracle for ReplayMark three-valued adjudication.

This oracle deliberately bypasses production q compilation, evidence-image
compilation, support-envelope compilation, and the production adjudicator. It
queries each raw target world still admitted by EvidenceSpec and classifies the
recorded action directly from positive target support.
"""

from dataclasses import dataclass
from fractions import Fraction
from typing import Mapping

from replaymark.contracts import ClaimSpec, EvidenceSpec, ProjectedAction, TargetModel, Verdict


class OracleAdjudicationError(ValueError):
    pass


@dataclass(frozen=True)
class OracleAdjudication:
    token: str
    projected_action: ProjectedAction
    compatible_states: tuple[str, ...]
    supporting_states: tuple[str, ...]
    excluding_states: tuple[str, ...]
    verdict: Verdict

    def __post_init__(self) -> None:
        compatible = set(self.compatible_states)
        supporting = set(self.supporting_states)
        excluding = set(self.excluding_states)
        if supporting | excluding != compatible:
            raise ValueError("oracle witness worlds must partition compatible states")
        if supporting & excluding:
            raise ValueError("oracle supporting/excluding worlds must be disjoint")
        expected = (
            Verdict.VALID
            if supporting == compatible
            else Verdict.INVALID
            if not supporting
            else Verdict.UNRESOLVED
        )
        if self.verdict is not expected:
            raise ValueError("oracle verdict is inconsistent with raw witness worlds")


def _projected_support(
    target: TargetModel,
    claim: ClaimSpec,
    decision_state: str,
) -> set[ProjectedAction]:
    try:
        distribution = target.current_distribution(str(decision_state))
    except KeyError as exc:
        raise OracleAdjudicationError(
            f"target has no current semantics for {decision_state!r}"
        ) from exc
    if not isinstance(distribution, Mapping):
        raise TypeError("current_distribution must return a mapping")

    total = Fraction(0, 1)
    support: set[ProjectedAction] = set()
    for raw_key, raw_mass in distribution.items():
        mass = Fraction(raw_mass)
        if mass < 0:
            raise OracleAdjudicationError(
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
        raise OracleAdjudicationError(
            f"probability mass at current_distribution({decision_state!r}) "
            f"is {total}, expected exactly 1"
        )
    if not support:
        raise OracleAdjudicationError(
            f"empty positive projected support at {decision_state!r}"
        )
    return support


def definition_adjudicate(
    target: TargetModel,
    claim: ClaimSpec,
    evidence: EvidenceSpec,
    observation: str,
    recorded_action: ProjectedAction,
) -> OracleAdjudication:
    """Classify z directly over raw worlds in Omega(e).

    VALID means every compatible world supports z; INVALID means none do;
    UNRESOLVED means at least one supports z and at least one excludes it.
    """

    if not isinstance(target, TargetModel):
        raise TypeError("target does not satisfy ReplayMark TargetModel protocol")
    if not isinstance(claim, ClaimSpec):
        raise TypeError("claim must be ClaimSpec")
    if not isinstance(evidence, EvidenceSpec):
        raise TypeError("evidence must be EvidenceSpec")
    if not isinstance(recorded_action, ProjectedAction):
        raise TypeError("recorded_action must be ProjectedAction")

    projected = claim.project(recorded_action)
    try:
        compatible = evidence.compatible_states(observation)
    except KeyError as exc:
        raise OracleAdjudicationError(
            f"unknown evidence observation: {observation!r}"
        ) from exc

    admitted = set(str(state) for state in target.decision_states)
    unknown = tuple(sorted(set(compatible) - admitted))
    if unknown:
        raise OracleAdjudicationError(
            f"evidence names target states outside the definition domain: {unknown!r}"
        )

    supporting: list[str] = []
    excluding: list[str] = []
    for state in compatible:
        if projected in _projected_support(target, claim, state):
            supporting.append(state)
        else:
            excluding.append(state)

    if not compatible:
        raise AssertionError("EvidenceSpec invariant violated: empty Omega(e)")

    if len(supporting) == len(compatible):
        verdict = Verdict.VALID
    elif not supporting:
        verdict = Verdict.INVALID
    else:
        verdict = Verdict.UNRESOLVED

    return OracleAdjudication(
        token=str(observation),
        projected_action=projected,
        compatible_states=tuple(compatible),
        supporting_states=tuple(supporting),
        excluding_states=tuple(excluding),
        verdict=verdict,
    )


__all__ = (
    "OracleAdjudication",
    "OracleAdjudicationError",
    "definition_adjudicate",
)
