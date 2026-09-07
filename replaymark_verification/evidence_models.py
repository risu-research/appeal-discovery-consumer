from __future__ import annotations

"""Verification-only observation models and migration helpers.

Production ReplayMark never accepts a hand-authored inverse Omega(e). Historical
verification fixtures do contain such expected inverse relations, so this module
turns them into *forward* observation models and checks that the new compiler
re-derives the expected inverse. Uncovered fixture worlds receive unique fallback
tokens so the forward model remains total without changing any named fixture
Omega(e).
"""

from dataclasses import dataclass

from replaymark.contracts import EvidenceSpec, TargetModel
from replaymark.evidence_semantics import compile_evidence_semantics


@dataclass
class FiniteObservationSupportModel:
    world_supports: dict[str, tuple[str, ...]]

    def observation_support(self, decision_state: str) -> tuple[str, ...]:
        try:
            return self.world_supports[str(decision_state)]
        except KeyError as exc:
            raise KeyError(decision_state) from exc


def model_from_expected_inverse(
    target: TargetModel,
    expected: EvidenceSpec,
) -> FiniteObservationSupportModel:
    states = tuple(sorted(str(state) for state in target.decision_states))
    admitted = set(states)
    for token, compatible in expected.observations:
        unknown = set(compatible) - admitted
        if unknown:
            raise ValueError(
                f"verification fixture token {token!r} names unknown states: "
                f"{tuple(sorted(unknown))!r}"
            )

    by_state: dict[str, list[str]] = {state: [] for state in states}
    for token, compatible in expected.observations:
        for state in compatible:
            by_state[state].append(token)

    world_supports: dict[str, tuple[str, ...]] = {}
    for state in states:
        tokens = by_state[state]
        if not tokens:
            # Verification-only totalization. This token is unique to this world,
            # so it cannot alter any named expected Omega(e).
            tokens = [f"__fixture_other__:{state}"]
        world_supports[state] = tuple(sorted(tokens))
    return FiniteObservationSupportModel(world_supports)


def compile_expected_evidence(
    target: TargetModel,
    expected: EvidenceSpec,
):
    model = model_from_expected_inverse(target, expected)
    compiled = compile_evidence_semantics(
        target,
        model,
        evidence_id=expected.evidence_id,
    )
    for token, compatible in expected.observations:
        assert compiled.compatible_states(token) == compatible
    return compiled


__all__ = (
    "FiniteObservationSupportModel",
    "compile_expected_evidence",
    "model_from_expected_inverse",
)
