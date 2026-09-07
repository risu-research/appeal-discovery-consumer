from __future__ import annotations

"""High-assurance gate for compiler-owned evidence-semantics closure."""

from itertools import product
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from replaymark.adjudicator import adjudicate_support
from replaymark.contracts import ClaimSpec, EvidenceSpec, ProjectedAction
from replaymark.evidence_image import compile_evidence_image
from replaymark.evidence_semantics import (
    IncompleteObservationSemanticsError,
    InvalidObservationSemanticsError,
    UnstableObservationSemanticsError,
    compile_evidence_semantics,
)
from replaymark.q_compiler import compile_bounded_q
from replaymark.rstar import ReuseDisposition, maximal_certified_reuse
from replaymark.support_envelope import compile_support_envelope
from replaymark_oracle.evidence_semantics_oracle import definition_evidence_closure
from replaymark_verification.evidence_models import FiniteObservationSupportModel
from replaymark_verification.models import BetterThermostatFrozenModel, TableTargetModel


def _action(op: str) -> ProjectedAction:
    return ProjectedAction.from_mapping({"operation": op})


def exhaustive_relation_inversion_gate() -> dict[str, int]:
    """Exhaust every total nonempty relation: 3 worlds -> nonempty subsets of 3 tokens."""

    target = TableTargetModel(
        outputs=("A", "B", "C"),
        continuations=("x",),
        next_state=((0,), (1,), (2,)),
    )
    states = target.decision_states
    tokens = ("e0", "e1", "e2")
    nonempty_supports = tuple(
        tuple(tokens[i] for i in range(3) if mask & (1 << i))
        for mask in range(1, 8)
    )

    relations = 0
    inverse_rows = 0
    edge_checks = 0
    for assignment in product(nonempty_supports, repeat=3):
        model = FiniteObservationSupportModel(
            {state: tuple(reversed(support)) for state, support in zip(states, assignment)}
        )
        production = compile_evidence_semantics(target, model, evidence_id="exhaustive")
        oracle = definition_evidence_closure(target, model)
        assert production.world_observation_supports == oracle.world_observation_supports
        assert production.evidence_spec.observations == oracle.observations

        for state, support in production.world_observation_supports:
            for token in support:
                assert state in production.compatible_states(token)
                edge_checks += 1
        for token, compatible in production.evidence_spec.observations:
            for state in compatible:
                assert token in production.tokens_for_state(state)
                edge_checks += 1
            inverse_rows += 1
        relations += 1

    assert relations == 7 ** 3 == 343
    return {
        "worlds": 3,
        "tokens": 3,
        "all_total_nonempty_relations": relations,
        "inverse_rows_checked": inverse_rows,
        "bidirectional_edge_checks": edge_checks,
    }


class ThermostatObservationModel:
    """Two retained-evidence modes, both derived forward from each raw world.

    `hide-motion` observes presence, night, and current preset.
    `hide-preset` observes presence, motion, and night.
    Every world therefore has two possible retained-evidence tokens.
    """

    def observation_support(self, decision_state: str) -> tuple[str, ...]:
        presence, motion, night, preset = json.loads(str(decision_state))
        hide_motion = json.dumps(
            ["hide-motion", presence, night, preset], separators=(",", ":")
        ).lower()
        hide_preset = json.dumps(
            ["hide-preset", presence, motion, night], separators=(",", ":")
        ).lower()
        return (hide_preset, hide_motion)  # deliberately noncanonical order


def thermostat_end_to_end_gate() -> dict[str, object]:
    target = BetterThermostatFrozenModel()
    observation_model = ThermostatObservationModel()
    evidence = compile_evidence_semantics(
        target, observation_model, evidence_id="bt-forward-observation-semantics"
    )
    oracle = definition_evidence_closure(target, observation_model)
    assert evidence.evidence_spec.observations == oracle.observations

    n2a = target.encode(False, False, False, "sleep")
    n2b = target.encode(False, True, False, "sleep")
    n2_token = json.dumps(
        ["hide-motion", False, False, "sleep"], separators=(",", ":")
    ).lower()
    assert evidence.compatible_states(n2_token) == tuple(sorted((n2a, n2b)))

    hide_preset_token = json.dumps(
        ["hide-preset", True, False, False], separators=(",", ":")
    ).lower()
    hidden_preset_worlds = evidence.compatible_states(hide_preset_token)
    assert len(hidden_preset_worlds) == 4
    assert {json.loads(state)[3] for state in hidden_preset_worlds} == {
        "away", "home", "comfort", "sleep"
    }

    claim = ClaimSpec("bt-evidence-closure", ("operation",), 2, "preset-action")
    quotient = compile_bounded_q(target, claim)
    image = compile_evidence_image(quotient, evidence, depth=2)
    envelope = compile_support_envelope(quotient, image)

    n2_decision = maximal_certified_reuse(
        adjudicate_support(envelope, claim, n2_token, _action("SET_AWAY"))
    )
    assert n2_decision.disposition is ReuseDisposition.REUSE

    mixed_home = adjudicate_support(
        envelope, claim, hide_preset_token, _action("SET_HOME")
    )
    mixed_away = adjudicate_support(
        envelope, claim, hide_preset_token, _action("SET_AWAY")
    )
    assert mixed_home.verdict.value == "UNRESOLVED"
    assert mixed_away.verdict.value == "INVALID"
    assert maximal_certified_reuse(mixed_home).disposition is ReuseDisposition.DO_NOT_REUSE
    assert maximal_certified_reuse(mixed_away).disposition is ReuseDisposition.DO_NOT_REUSE

    return {
        "target_worlds": evidence.world_count,
        "observation_tokens": evidence.observation_count,
        "relation_edges": evidence.relation_edge_count,
        "n2b_derived_omega_size": len(evidence.compatible_states(n2_token)),
        "hide_preset_derived_omega_size": len(hidden_preset_worlds),
        "n2b_rstar": n2_decision.disposition.value,
        "hide_preset_set_home": mixed_home.verdict.value,
        "hide_preset_set_away": mixed_away.verdict.value,
        "relation_fingerprint": evidence.relation_fingerprint,
    }


def manual_omission_trap_gate() -> dict[str, object]:
    target = TableTargetModel(
        outputs=("A", "A", "B"),
        continuations=("x",),
        next_state=((0,), (1,), (2,)),
    )
    model = FiniteObservationSupportModel(
        {"s0": ("e",), "s1": ("e",), "s2": ("e",)}
    )
    derived = compile_evidence_semantics(target, model, evidence_id="omission-trap")
    assert derived.compatible_states("e") == ("s0", "s1", "s2")

    manually_omitted = EvidenceSpec("omission-trap", (("e", ("s0", "s1")),))
    claim = ClaimSpec("omission", ("operation",), 0, "event")
    quotient = compile_bounded_q(target, claim)
    try:
        compile_evidence_image(quotient, manually_omitted)  # type: ignore[arg-type]
    except TypeError:
        manual_rejected = True
    else:
        raise AssertionError("manual inverse must not enter production certification")

    image = compile_evidence_image(quotient, derived)
    envelope = compile_support_envelope(quotient, image)
    decision = adjudicate_support(envelope, claim, "e", _action("A"))
    assert decision.verdict.value == "UNRESOLVED"

    return {
        "manual_inverse_worlds": 2,
        "compiler_derived_worlds": 3,
        "manual_inverse_rejected_by_production": manual_rejected,
        "correct_closed_world_verdict": decision.verdict.value,
    }


def conservative_overapproximation_gate() -> dict[str, object]:
    target = TableTargetModel(
        outputs=("A", "B", "C"),
        continuations=("x",),
        next_state=((0,), (1,), (2,)),
    )
    exact = FiniteObservationSupportModel(
        {"s0": ("e",), "s1": ("other1",), "s2": ("other2",)}
    )
    conservative = FiniteObservationSupportModel(
        {"s0": ("e",), "s1": ("e", "other1"), "s2": ("other2",)}
    )
    exact_c = compile_evidence_semantics(target, exact, evidence_id="exact")
    conservative_c = compile_evidence_semantics(
        target, conservative, evidence_id="conservative"
    )
    exact_worlds = set(exact_c.compatible_states("e"))
    conservative_worlds = set(conservative_c.compatible_states("e"))
    assert exact_worlds < conservative_worlds
    return {
        "exact_omega_size": len(exact_worlds),
        "conservative_omega_size": len(conservative_worlds),
        "real_worlds_subset_of_conservative_model": True,
    }


def malformed_adapter_gate() -> dict[str, bool]:
    target = TableTargetModel(
        outputs=("A", "B"),
        continuations=("x",),
        next_state=((0,), (1,)),
    )

    class Empty:
        def observation_support(self, state: str) -> tuple[str, ...]:
            return () if state == "s1" else ("e",)

    try:
        compile_evidence_semantics(target, Empty(), evidence_id="empty")
    except IncompleteObservationSemanticsError:
        empty_rejected = True
    else:
        raise AssertionError("uncovered modeled world must fail closed")

    class Duplicate:
        def observation_support(self, state: str) -> tuple[str, ...]:
            return ("e", "e")

    try:
        compile_evidence_semantics(target, Duplicate(), evidence_id="dup")
    except InvalidObservationSemanticsError:
        duplicate_rejected = True
    else:
        raise AssertionError("duplicate observation token must fail closed")

    class Stateful:
        def __init__(self):
            self.calls = 0
        def observation_support(self, state: str) -> tuple[str, ...]:
            self.calls += 1
            return ("early",) if self.calls <= 2 else ("late",)

    try:
        compile_evidence_semantics(target, Stateful(), evidence_id="stateful")
    except UnstableObservationSemanticsError:
        unstable_rejected = True
    else:
        raise AssertionError("stateful/order-dependent observation semantics must fail")

    class ListReturn:
        def observation_support(self, state: str):
            return ["e"]

    try:
        compile_evidence_semantics(target, ListReturn(), evidence_id="list")
    except TypeError:
        noncanonical_return_rejected = True
    else:
        raise AssertionError("observation support must use immutable tuple semantics")

    return {
        "empty_world_support_rejected": empty_rejected,
        "duplicate_token_rejected": duplicate_rejected,
        "unstable_adapter_rejected": unstable_rejected,
        "noncanonical_return_rejected": noncanonical_return_rejected,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    args = parser.parse_args()
    report = {
        "schema": "replaymark.evidence-semantics-closure.gate.v1",
        "exhaustive_relation_inversion": exhaustive_relation_inversion_gate(),
        "thermostat_end_to_end": thermostat_end_to_end_gate(),
        "manual_omission_trap": manual_omission_trap_gate(),
        "conservative_overapproximation": conservative_overapproximation_gate(),
        "malformed_adapters": malformed_adapter_gate(),
        "verdict": "PASS",
    }
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
