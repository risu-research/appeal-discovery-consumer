from __future__ import annotations

"""High-assurance verification for theorem-induced maximal certified reuse R*."""

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

from replaymark.adjudicator import adjudicate_support
from replaymark.contracts import ClaimSpec, EvidenceSpec, ProjectedAction, Verdict
from replaymark.evidence_image import compile_evidence_image
from replaymark.q_compiler import compile_bounded_q
from replaymark.rstar import (
    RStarDecision,
    ReuseDisposition,
    maximal_certified_reuse,
)
from replaymark.support_envelope import compile_support_envelope
from replaymark_oracle.rstar_oracle import definition_rstar
from replaymark_verification.models import BetterThermostatFrozenModel, TableTargetModel


def _action(operation: str, **extra) -> ProjectedAction:
    dimensions = {"operation": operation}
    dimensions.update(extra)
    return ProjectedAction.from_mapping(dimensions)


def _production_rstar(envelope, claim, token: str, action: ProjectedAction):
    adjudication = adjudicate_support(envelope, claim, token, action)
    return adjudication, maximal_certified_reuse(adjudication)


def thermostat_gate() -> dict[str, object]:
    target = BetterThermostatFrozenModel()
    claim = ClaimSpec(
        "bt-rstar",
        ("operation",),
        2,
        "consequential-preset-service-action",
    )
    quotient = compile_bounded_q(target, claim)

    n2a = target.encode(False, False, False, "sleep")
    n2b = target.encode(False, True, False, "sleep")
    non_target_home = target.encode(True, False, False, "sleep")
    at_target_home = target.encode(True, False, False, "home")

    evidence = EvidenceSpec(
        "bt-rstar-fixture",
        (
            ("n2b-pair", (n2a, n2b)),
            ("mixed", (non_target_home, at_target_home)),
            ("strong-home", (non_target_home,)),
        ),
    )

    away = _action("SET_AWAY")
    home = _action("SET_HOME")
    no_action = _action("NO_ACTION")

    n2b_dispositions: list[str] = []
    n2b_q_counts: list[int] = []
    for depth in range(3):
        image = compile_evidence_image(quotient, evidence, depth=depth)
        envelope = compile_support_envelope(quotient, image)
        adjudication, decision = _production_rstar(
            envelope, claim, "n2b-pair", away
        )
        oracle = definition_rstar(target, claim, evidence, "n2b-pair", away)
        assert adjudication.verdict is Verdict.VALID
        assert decision.disposition is ReuseDisposition.REUSE
        assert decision.disposition.value == oracle.disposition.value
        assert oracle.maximality_counterexample is None
        n2b_dispositions.append(decision.disposition.value)
        n2b_q_counts.append(image.observation("n2b-pair").predictive_world_count)

    assert n2b_q_counts == [1, 2, 2]
    assert n2b_dispositions == ["REUSE", "REUSE", "REUSE"]

    image = compile_evidence_image(quotient, evidence, depth=2)
    envelope = compile_support_envelope(quotient, image)

    mixed_home_adj, mixed_home = _production_rstar(envelope, claim, "mixed", home)
    mixed_no_adj, mixed_no = _production_rstar(envelope, claim, "mixed", no_action)
    mixed_away_adj, mixed_away = _production_rstar(envelope, claim, "mixed", away)
    strong_home_adj, strong_home = _production_rstar(
        envelope, claim, "strong-home", home
    )
    strong_no_adj, strong_no = _production_rstar(
        envelope, claim, "strong-home", no_action
    )

    assert mixed_home_adj.verdict is Verdict.UNRESOLVED
    assert mixed_no_adj.verdict is Verdict.UNRESOLVED
    assert mixed_away_adj.verdict is Verdict.INVALID
    assert mixed_home.disposition is ReuseDisposition.DO_NOT_REUSE
    assert mixed_no.disposition is ReuseDisposition.DO_NOT_REUSE
    assert mixed_away.disposition is ReuseDisposition.DO_NOT_REUSE
    assert strong_home_adj.verdict is Verdict.VALID
    assert strong_home.disposition is ReuseDisposition.REUSE
    assert strong_no_adj.verdict is Verdict.INVALID
    assert strong_no.disposition is ReuseDisposition.DO_NOT_REUSE

    for token, action, production in (
        ("mixed", home, mixed_home),
        ("mixed", no_action, mixed_no),
        ("mixed", away, mixed_away),
        ("strong-home", home, strong_home),
        ("strong-home", no_action, strong_no),
    ):
        oracle = definition_rstar(target, claim, evidence, token, action)
        assert production.disposition.value == oracle.disposition.value
        if production.disposition is ReuseDisposition.DO_NOT_REUSE:
            assert oracle.maximality_counterexample is not None
        else:
            assert oracle.maximality_counterexample is None

    # Extra non-claim coordinates cannot change the theorem-induced decision.
    rich_home = _action("SET_HOME", variant="historical", delay_ms=999)
    _plain_adj, plain = _production_rstar(envelope, claim, "strong-home", home)
    _rich_adj, rich = _production_rstar(envelope, claim, "strong-home", rich_home)
    assert plain.canonical_bytes() == rich.canonical_bytes()
    assert plain.fingerprint() == rich.fingerprint()

    # INVALID and UNRESOLVED both forbid reuse but remain distinguishable facts.
    assert mixed_home.disposition is mixed_away.disposition
    assert mixed_home.verdict is not mixed_away.verdict
    assert mixed_home.canonical_bytes() != mixed_away.canonical_bytes()

    return {
        "n2b_q_image_counts": n2b_q_counts,
        "n2b_rstar": n2b_dispositions,
        "mixed_set_home_verdict": mixed_home.verdict.value,
        "mixed_set_home_rstar": mixed_home.disposition.value,
        "mixed_set_away_verdict": mixed_away.verdict.value,
        "mixed_set_away_rstar": mixed_away.disposition.value,
        "strong_set_home_rstar": strong_home.disposition.value,
        "projection_invariant": True,
        "blocked_reasons_preserved": True,
    }


class StochasticRStarModel:
    """Oracle-only fixture with supports {A,B} and {B,C}, plus zero mass."""

    @property
    def fingerprint(self) -> str:
        return "stochastic-rstar-oracle-fixture"

    @property
    def decision_states(self) -> tuple[str, ...]:
        return ("s0", "s1")

    @property
    def continuation_alphabet(self) -> tuple[str, ...]:
        return ()

    def current_distribution(self, decision_state: str):
        a = _action("A")
        b = _action("B")
        c = _action("C")
        zero = _action("ZERO")
        if decision_state == "s0":
            return {
                (a, "p0a"): Fraction(1, 2),
                (b, "p0b"): Fraction(1, 2),
                (zero, "p0z"): Fraction(0, 1),
            }
        if decision_state == "s1":
            return {
                (b, "p1b"): Fraction(1, 2),
                (c, "p1c"): Fraction(1, 2),
                (zero, "p1z"): Fraction(0, 1),
            }
        raise KeyError(decision_state)

    def advance_distribution(self, post_state: str, continuation: str):
        raise KeyError((post_state, continuation))


def stochastic_oracle_gate() -> dict[str, object]:
    target = StochasticRStarModel()
    claim = ClaimSpec("stochastic-rstar", ("operation",), 0, "event")
    evidence = EvidenceSpec("stochastic-rstar-evidence", (("both", ("s0", "s1")),))

    b = definition_rstar(target, claim, evidence, "both", _action("B"))
    a = definition_rstar(target, claim, evidence, "both", _action("A"))
    zero = definition_rstar(target, claim, evidence, "both", _action("ZERO"))

    assert b.disposition.value == "REUSE"
    assert not b.excluding_worlds
    assert a.disposition.value == "DO_NOT_REUSE"
    assert a.supporting_worlds == ("s0",)
    assert a.excluding_worlds == ("s1",)
    assert zero.disposition.value == "DO_NOT_REUSE"
    assert zero.supporting_worlds == ()
    assert zero.excluding_worlds == ("s0", "s1")

    return {
        "B": b.disposition.value,
        "A": a.disposition.value,
        "ZERO": zero.disposition.value,
        "A_counterexample": a.maximality_counterexample,
        "ZERO_excluding_worlds": list(zero.excluding_worlds),
    }


def structural_policy_separation_gate() -> dict[str, bool]:
    target = TableTargetModel(
        outputs=("A", "B"),
        continuations=("x",),
        next_state=((0,), (1,)),
    )
    claim = ClaimSpec("rstar-structure", ("operation",), 0, "event")
    evidence = EvidenceSpec("rstar-structure-evidence", (("both", ("s0", "s1")),))
    quotient = compile_bounded_q(target, claim)
    image = compile_evidence_image(quotient, evidence)
    envelope = compile_support_envelope(quotient, image)
    adjudication = adjudicate_support(envelope, claim, "both", _action("A"))
    decision = maximal_certified_reuse(adjudication)
    assert adjudication.verdict is Verdict.UNRESOLVED
    assert decision.disposition is ReuseDisposition.DO_NOT_REUSE

    # The theorem domain contains exactly two reuse choices; no fallback action.
    assert {item.value for item in ReuseDisposition} == {"REUSE", "DO_NOT_REUSE"}
    assert not hasattr(decision, "regenerate")
    assert not hasattr(decision, "refine_evidence")
    assert not hasattr(decision, "abort")

    opposite = ReuseDisposition.REUSE
    try:
        RStarDecision(
            schema_version=decision.schema_version,
            adjudication_fingerprint=decision.adjudication_fingerprint,
            support_envelope_fingerprint=decision.support_envelope_fingerprint,
            claim_fingerprint=decision.claim_fingerprint,
            evidence_fingerprint=decision.evidence_fingerprint,
            depth=decision.depth,
            token=decision.token,
            projected_action=decision.projected_action,
            verdict=decision.verdict,
            disposition=opposite,
        )
    except ValueError:
        inconsistent_certificate_rejected = True
    else:
        raise AssertionError("R* certificate must reject theorem-inconsistent disposition")

    try:
        maximal_certified_reuse(object())
    except TypeError:
        foreign_input_rejected = True
    else:
        raise AssertionError("R* must consume a sealed Adjudication")

    return {
        "binary_reuse_domain_only": True,
        "no_fallback_policy_surface": True,
        "inconsistent_certificate_rejected": inconsistent_certificate_rejected,
        "foreign_input_rejected": foreign_input_rejected,
    }


def exhaustive_maximality_gate() -> dict[str, object]:
    """Exhaust deterministic finite machines and prove pointwise maximality."""

    outputs = ("A", "B")
    continuations = ("0", "1")
    claim = ClaimSpec("rstar-exhaustive", ("operation",), 2, "event")
    states = ("s0", "s1", "s2")
    evidence = EvidenceSpec(
        "rstar-all-nonempty-subsets",
        tuple(
            (
                f"e{mask}",
                tuple(state for i, state in enumerate(states) if mask & (1 << i)),
            )
            for mask in range(1, 8)
        ),
    )
    recorded_actions = {name: _action(name) for name in outputs}

    machine_count = 0
    pair_count = 0
    reuse_count = 0
    do_not_reuse_count = 0
    blocked_with_counterexample = 0
    pointwise_maximality_checks = 0
    refinement_reuse_persistence_checks = 0
    verdict_counts = {verdict.value: 0 for verdict in Verdict}
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
            envelope = compile_support_envelope(quotient, image)
            by_mask_action: dict[tuple[int, str], ReuseDisposition] = {}

            for mask in range(1, 8):
                token = f"e{mask}"
                for name, recorded_action in recorded_actions.items():
                    adjudication = adjudicate_support(
                        envelope, claim, token, recorded_action
                    )
                    production = maximal_certified_reuse(adjudication)
                    oracle = definition_rstar(
                        target, claim, evidence, token, recorded_action
                    )
                    assert production.disposition.value == oracle.disposition.value
                    assert production.projected_action == oracle.projected_action

                    verdict_counts[adjudication.verdict.value] += 1
                    pair_count += 1
                    pointwise_maximality_checks += 1
                    by_mask_action[(mask, name)] = production.disposition

                    # Pointwise proof of maximality under DO_NOT_REUSE < REUSE:
                    # REUSE is sound exactly when no compatible world excludes z.
                    if oracle.excluding_worlds:
                        assert production.disposition is ReuseDisposition.DO_NOT_REUSE
                        assert oracle.maximality_counterexample is not None
                        do_not_reuse_count += 1
                        blocked_with_counterexample += 1
                    else:
                        assert production.disposition is ReuseDisposition.REUSE
                        assert set(oracle.supporting_worlds) == set(
                            oracle.compatible_worlds
                        )
                        reuse_count += 1

            # Under stronger evidence Omega(e') subset Omega(e), certified reuse
            # cannot be lost. Check every strict nonempty subset relation.
            for strong_mask in range(1, 8):
                for weak_mask in range(1, 8):
                    if strong_mask == weak_mask:
                        continue
                    if strong_mask & weak_mask != strong_mask:
                        continue
                    for name in outputs:
                        weak = by_mask_action[(weak_mask, name)]
                        strong = by_mask_action[(strong_mask, name)]
                        if weak is ReuseDisposition.REUSE:
                            assert strong is ReuseDisposition.REUSE
                        refinement_reuse_persistence_checks += 1

            machine_count += 1

    assert machine_count == 5832
    assert pair_count == 5832 * 7 * 2 == 81648
    assert pointwise_maximality_checks == pair_count
    assert reuse_count == 27702
    assert do_not_reuse_count == 53946
    assert blocked_with_counterexample == do_not_reuse_count
    assert verdict_counts == {
        "VALID": 27702,
        "INVALID": 27702,
        "UNRESOLVED": 26244,
    }
    assert refinement_reuse_persistence_checks == 5832 * 12 * 2 == 139968

    return {
        "machines": machine_count,
        "evidence_sets_per_machine": 7,
        "recorded_actions_per_evidence": 2,
        "production_vs_raw_oracle_pairs": pair_count,
        "pointwise_maximality_checks": pointwise_maximality_checks,
        "reuse": reuse_count,
        "do_not_reuse": do_not_reuse_count,
        "blocked_pairs_with_raw_counterexample": blocked_with_counterexample,
        "verdict_counts": verdict_counts,
        "strict_refinement_reuse_persistence_checks": refinement_reuse_persistence_checks,
        "horizon": 2,
        "elapsed_seconds": round(time.perf_counter() - start, 6),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    args = parser.parse_args()

    report = {
        "schema": "replaymark.rstar.maximal-certified-reuse.gate.v1",
        "thermostat": thermostat_gate(),
        "stochastic_definition_oracle": stochastic_oracle_gate(),
        "theorem_policy_separation": structural_policy_separation_gate(),
        "exhaustive_maximality": exhaustive_maximality_gate(),
        "verdict": "PASS",
    }
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
