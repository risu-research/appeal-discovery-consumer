from __future__ import annotations

"""High-assurance differential verification for S^- / S^+ compilation."""

import argparse
from fractions import Fraction
from itertools import product
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from replaymark.contracts import ClaimSpec, EvidenceSpec, ProjectedAction
from replaymark.evidence_image import compile_evidence_image
from replaymark.q_compiler import compile_bounded_q
from replaymark.support_envelope import (
    ArtifactMismatchError,
    compile_support_envelope,
)
from replaymark_oracle.support_envelope_oracle import definition_support_envelope
from replaymark_verification.models import BetterThermostatFrozenModel, TableTargetModel


def _ops(actions: tuple[ProjectedAction, ...]) -> tuple[str, ...]:
    return tuple(str(action.as_dict()["operation"]) for action in actions)


def _assert_envelope_matches_oracle(target, claim, evidence, quotient, depth: int) -> None:
    image = compile_evidence_image(quotient, evidence, depth=depth)
    production = compile_support_envelope(quotient, image)
    oracle = definition_support_envelope(target, claim, evidence)
    for token, _ in evidence.observations:
        p = production.observation(token)
        o = oracle.observation(token)
        assert p.guaranteed_support == o.guaranteed_support, (
            token,
            p.guaranteed_support,
            o.guaranteed_support,
        )
        assert p.possible_support == o.possible_support, (
            token,
            p.possible_support,
            o.possible_support,
        )
        assert set(p.guaranteed_support).issubset(set(p.possible_support))
        assert p.possible_support


def thermostat_gate() -> dict[str, object]:
    target = BetterThermostatFrozenModel()
    claim = ClaimSpec(
        "bt-support-envelope",
        ("operation",),
        2,
        "consequential-preset-service-action",
    )
    quotient = compile_bounded_q(target, claim)

    n2a = target.encode(False, False, False, "sleep")
    n2b = target.encode(False, True, False, "sleep")

    nt_away = target.encode(True, False, False, "away")
    nt_comfort = target.encode(True, False, False, "comfort")
    nt_sleep = target.encode(True, False, False, "sleep")
    at_target = target.encode(True, False, False, "home")

    evidence = EvidenceSpec(
        "bt-support-envelope-fixture",
        (
            ("n2b-pair", (n2a, n2b)),
            ("overwritten-nontargets", (nt_away, nt_comfort, nt_sleep)),
            ("with-at-target", (nt_sleep, at_target)),
            ("stronger-single", (nt_sleep,)),
        ),
    )

    envelopes = []
    images = []
    for depth in range(3):
        _assert_envelope_matches_oracle(target, claim, evidence, quotient, depth)
        image = compile_evidence_image(quotient, evidence, depth=depth)
        envelope = compile_support_envelope(quotient, image)
        images.append(image)
        envelopes.append(envelope)

    # Predictive ambiguity appears at H=1, but the current support remains exact.
    assert [
        image.observation("n2b-pair").predictive_world_count for image in images
    ] == [1, 2, 2]
    for envelope in envelopes:
        row = envelope.observation("n2b-pair")
        assert _ops(row.guaranteed_support) == ("SET_AWAY",)
        assert _ops(row.possible_support) == ("SET_AWAY",)

    # Three raw non-target preset identities are overwritten by the same current decision.
    overwritten = envelopes[2].observation("overwritten-nontargets")
    assert _ops(overwritten.guaranteed_support) == ("SET_HOME",)
    assert _ops(overwritten.possible_support) == ("SET_HOME",)

    # Mixing one at-target world creates a genuine support disagreement.
    broad = envelopes[2].observation("with-at-target")
    assert broad.guaranteed_support == ()
    assert set(_ops(broad.possible_support)) == {"NO_ACTION", "SET_HOME"}

    # Stronger evidence restores an exact singleton envelope, exercising monotonicity.
    strong = envelopes[2].observation("stronger-single")
    assert set(broad.guaranteed_support).issubset(set(strong.guaranteed_support))
    assert set(strong.possible_support).issubset(set(broad.possible_support))
    assert _ops(strong.guaranteed_support) == ("SET_HOME",)
    assert _ops(strong.possible_support) == ("SET_HOME",)

    return {
        "q_counts": [layer.block_count for layer in quotient.layers],
        "n2b_q_image_counts": [
            image.observation("n2b-pair").predictive_world_count for image in images
        ],
        "n2b_guaranteed_support": list(_ops(envelopes[2].observation("n2b-pair").guaranteed_support)),
        "n2b_possible_support": list(_ops(envelopes[2].observation("n2b-pair").possible_support)),
        "overwritten_guaranteed_support": list(_ops(overwritten.guaranteed_support)),
        "with_at_target_guaranteed_support": list(_ops(broad.guaranteed_support)),
        "with_at_target_possible_support": sorted(_ops(broad.possible_support)),
        "support_envelope_fingerprint": envelopes[2].fingerprint(),
    }


class StochasticOverlapModel:
    """Oracle-only fixture: supports {A,B} and {B,C} on two compatible worlds."""

    @property
    def fingerprint(self) -> str:
        return "stochastic-overlap-support-oracle-fixture"

    @property
    def decision_states(self) -> tuple[str, ...]:
        return ("s0", "s1")

    @property
    def continuation_alphabet(self) -> tuple[str, ...]:
        return ()

    def current_distribution(self, decision_state: str):
        a = ProjectedAction.from_mapping({"operation": "A"})
        b = ProjectedAction.from_mapping({"operation": "B"})
        c = ProjectedAction.from_mapping({"operation": "C"})
        if decision_state == "s0":
            return {(a, "p0a"): Fraction(1, 2), (b, "p0b"): Fraction(1, 2)}
        if decision_state == "s1":
            return {(b, "p1b"): Fraction(1, 2), (c, "p1c"): Fraction(1, 2)}
        raise KeyError(decision_state)

    def advance_distribution(self, post_state: str, continuation: str):
        raise KeyError((post_state, continuation))


def stochastic_definition_gate() -> dict[str, object]:
    target = StochasticOverlapModel()
    claim = ClaimSpec("stochastic-support", ("operation",), 0, "event")
    evidence = EvidenceSpec("stochastic-evidence", (("both", ("s0", "s1")),))
    envelope = definition_support_envelope(target, claim, evidence).observation("both")
    assert _ops(envelope.guaranteed_support) == ("B",)
    assert set(_ops(envelope.possible_support)) == {"A", "B", "C"}
    return {
        "guaranteed_support": list(_ops(envelope.guaranteed_support)),
        "possible_support": sorted(_ops(envelope.possible_support)),
        "production_scope": "deterministic-q-pipeline-only",
    }


def artifact_binding_gate() -> dict[str, bool]:
    claim = ClaimSpec("binding", ("operation",), 1, "event")
    target_a = TableTargetModel(
        outputs=("A", "A"),
        continuations=("x",),
        next_state=((0,), (1,)),
    )
    target_b = TableTargetModel(
        outputs=("A", "B"),
        continuations=("x",),
        next_state=((0,), (1,)),
    )
    qa = compile_bounded_q(target_a, claim)
    qb = compile_bounded_q(target_b, claim)
    evidence = EvidenceSpec("binding-evidence", (("e", ("s0", "s1")),))
    image_a = compile_evidence_image(qa, evidence)

    try:
        compile_support_envelope(qb, image_a)
    except ArtifactMismatchError:
        mismatch_rejected = True
    else:
        raise AssertionError("support compiler must reject a foreign evidence image")

    envelope_a = compile_support_envelope(qa, image_a)
    envelope_a2 = compile_support_envelope(qa, compile_evidence_image(qa, evidence))
    assert envelope_a.canonical_bytes() == envelope_a2.canonical_bytes()
    assert envelope_a.fingerprint() == envelope_a2.fingerprint()

    return {
        "foreign_evidence_image_rejected": mismatch_rejected,
        "canonical_recompile_stable": True,
    }


def exhaustive_deterministic_gate() -> dict[str, object]:
    """All 3-state/2-input/2-output machines, all nonempty Omega(e), at H=2."""

    outputs = ("A", "B")
    continuations = ("0", "1")
    claim = ClaimSpec("support-exhaustive", ("operation",), 2, "event")
    states = ("s0", "s1", "s2")
    tokens_and_subsets = tuple(
        (
            f"e{mask}",
            tuple(state for i, state in enumerate(states) if mask & (1 << i)),
        )
        for mask in range(1, 8)
    )
    evidence = EvidenceSpec("all-nonempty-subsets", tokens_and_subsets)

    machine_count = 0
    envelope_rows_checked = 0
    monotonicity_pairs_checked = 0
    start = time.perf_counter()

    for output_assignment in product(outputs, repeat=3):
        for flat_next in product(range(3), repeat=6):
            rows = (
                (flat_next[0], flat_next[1]),
                (flat_next[2], flat_next[3]),
                (flat_next[4], flat_next[5]),
            )
            target = TableTargetModel(
                outputs=tuple(output_assignment),
                continuations=continuations,
                next_state=rows,
            )
            quotient = compile_bounded_q(target, claim)
            image = compile_evidence_image(quotient, evidence, depth=2)
            production = compile_support_envelope(quotient, image)
            oracle = definition_support_envelope(target, claim, evidence)

            for token, _subset in evidence.observations:
                p = production.observation(token)
                o = oracle.observation(token)
                assert p.guaranteed_support == o.guaranteed_support
                assert p.possible_support == o.possible_support
                envelope_rows_checked += 1

            # Exhaust every strict information refinement among the seven subsets.
            by_mask = {
                mask: production.observation(f"e{mask}") for mask in range(1, 8)
            }
            for strong_mask in range(1, 8):
                for weak_mask in range(1, 8):
                    if strong_mask == weak_mask:
                        continue
                    if strong_mask & weak_mask != strong_mask:
                        continue
                    strong = by_mask[strong_mask]
                    weak = by_mask[weak_mask]
                    assert set(weak.guaranteed_support).issubset(
                        set(strong.guaranteed_support)
                    )
                    assert set(strong.possible_support).issubset(
                        set(weak.possible_support)
                    )
                    monotonicity_pairs_checked += 1

            machine_count += 1

    assert machine_count == 5832
    assert envelope_rows_checked == 5832 * 7
    # 12 strict nonempty subset relations on a three-element universe per machine.
    assert monotonicity_pairs_checked == 5832 * 12

    return {
        "machines": machine_count,
        "evidence_sets_per_machine": 7,
        "compiler_oracle_envelopes": envelope_rows_checked,
        "strict_evidence_refinement_checks": monotonicity_pairs_checked,
        "horizon": 2,
        "elapsed_seconds": round(time.perf_counter() - start, 6),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    args = parser.parse_args()

    report = {
        "schema": "replaymark.support-envelope.compiler_oracle_gate.v1",
        "thermostat": thermostat_gate(),
        "stochastic_definition_oracle": stochastic_definition_gate(),
        "artifact_binding": artifact_binding_gate(),
        "exhaustive_deterministic": exhaustive_deterministic_gate(),
        "verdict": "PASS",
    }
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
