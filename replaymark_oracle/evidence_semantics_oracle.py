from __future__ import annotations

"""Definition oracle for evidence-semantics closure.

This oracle does not import the production evidence-semantics compiler. It shares
only the TargetModel state domain and the forward observation adapter semantics,
which are the intentional trusted semantic boundary for this stage.
"""

from dataclasses import dataclass

from replaymark.contracts import TargetModel


class OracleEvidenceSemanticsError(ValueError):
    pass


def _clean_token(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise OracleEvidenceSemanticsError("invalid evidence token in observation model")
    return value


def _read_support(model: object, state: str) -> tuple[str, ...]:
    if not hasattr(model, "observation_support"):
        raise TypeError("observation model has no observation_support method")
    raw = model.observation_support(state)
    if not isinstance(raw, tuple):
        raise TypeError("observation_support must return tuple[str, ...]")
    if not raw:
        raise OracleEvidenceSemanticsError(
            f"modeled world {state!r} has empty observation support"
        )
    clean = tuple(_clean_token(token) for token in raw)
    if len(set(clean)) != len(clean):
        raise OracleEvidenceSemanticsError(
            f"modeled world {state!r} has duplicate observation tokens"
        )
    return tuple(sorted(clean))


@dataclass(frozen=True)
class OracleEvidenceClosure:
    decision_states: tuple[str, ...]
    world_observation_supports: tuple[tuple[str, tuple[str, ...]], ...]
    observations: tuple[tuple[str, tuple[str, ...]], ...]

    def compatible_states(self, token: str) -> tuple[str, ...]:
        try:
            return dict(self.observations)[str(token)]
        except KeyError as exc:
            raise KeyError(f"unknown evidence observation: {token!r}") from exc


def definition_evidence_closure(
    target: TargetModel,
    observation_model: object,
) -> OracleEvidenceClosure:
    """Compute the literal inverse relation Omega(e) from forward O(w)."""

    if not isinstance(target, TargetModel):
        raise TypeError("target does not satisfy ReplayMark TargetModel protocol")
    states = tuple(sorted(str(state) for state in target.decision_states))
    if not states or len(set(states)) != len(states):
        raise OracleEvidenceSemanticsError("invalid target decision-state domain")

    world_rows = tuple(
        (state, _read_support(observation_model, state)) for state in states
    )
    tokens = sorted({token for _state, support in world_rows for token in support})

    inverse_rows: list[tuple[str, tuple[str, ...]]] = []
    for token in tokens:
        compatible = tuple(
            state for state, support in world_rows if token in support
        )
        if not compatible:
            raise AssertionError("forward relation produced an impossible inverse token")
        inverse_rows.append((token, compatible))

    return OracleEvidenceClosure(
        decision_states=states,
        world_observation_supports=world_rows,
        observations=tuple(inverse_rows),
    )


__all__ = (
    "OracleEvidenceClosure",
    "OracleEvidenceSemanticsError",
    "definition_evidence_closure",
)
