from __future__ import annotations

"""High-assurance gate for production shortest predictive-continuation witnesses."""

import argparse
from dataclasses import replace
from itertools import product
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from replaymark.contracts import ClaimSpec, EvidenceSpec, ProjectedAction
from replaymark.predictive_witness import (
    MalformedQuotientWitnessError,
    compile_predictive_witnesses,
)
from replaymark.q_compiler import compile_bounded_q
from replaymark_oracle.definition_q_oracle import (
    shortest_distinguishing_word,
    trace_law,
)
from replaymark_oracle.rstar_oracle import definition_rstar
from replaymark_verification.models import BetterThermostatFrozenModel, TableTargetModel


def _deterministic_trace(target, claim, state: str, word: tuple[str, ...]):
    law = trace_law(target, claim, state, word)
    if len(law) != 1 or next(iter(law.values())) != 1:
        raise AssertionError("expected deterministic trace law")
    return next(iter(law))


def thermostat_gate() -> dict[str, object]:
    target = BetterThermostatFrozenModel()
    claim = ClaimSpec(
        "bt-production-predictive-witness",
        ("operation",),
        4,
        "consequential-preset-service-action",
    )
    quotient = compile_bounded_q(target, claim)

    n2a = target.encode(False, False, False, "sleep")
    n2b = target.encode(False, True, False, "sleep")
    d2a = target.encode(False, False, True, "sleep")
    d2b = target.encode(False, True, True, "sleep")

    index0 = compile_predictive_witnesses(quotient, depth=0)
    index1 = compile_predictive_witnesses(quotient, depth=1)
    index2 = compile_predictive_witnesses(quotient, depth=2)

    assert index0.witness(n2a, n2b) is None
    n2 = index1.witness(n2a, n2b)
    assert n2 is not None
    assert n2.continuation_word == ("presence_toggle",)
    assert n2.first_separation_depth == 1
    assert n2.continuation_word == shortest_distinguishing_word(
        target, claim, n2a, n2b, 1
    )
    assert n2.left_trace == _deterministic_trace(
        target, claim, n2.left_state, n2.continuation_word
    )
    assert n2.right_trace == _deterministic_trace(
        target, claim, n2.right_state, n2.continuation_word
    )
    assert index1.witness(n2b, n2a) == n2

    assert index1.witness(d2a, d2b) is None
    d2 = index2.witness(d2a, d2b)
    assert d2 is not None
    assert d2.continuation_word == ("presence_toggle", "night_toggle")
    assert d2.first_separation_depth == 2
    assert d2.continuation_word == shortest_distinguishing_word(
        target, claim, d2a, d2b, 2
    )
    assert d2.left_trace == _deterministic_trace(
        target, claim, d2.left_state, d2.continuation_word
    )
    assert d2.right_trace == _deterministic_trace(
        target, claim, d2.right_state, d2.continuation_word
    )

    # Empty word is a real shortest witness when current projected outputs differ.
    current_left = target.encode(False, False, False, "sleep")
    current_right = target.encode(True, False, False, "sleep")
    current = index0.witness(current_left, current_right)
    assert current is not None
    assert current.continuation_word == ()
    assert current.first_separation_depth == 0
    assert current.left_trace != current.right_trace

    return {
        "q_counts": [layer.block_count for layer in quotient.layers],
        "n2b_shortest_word": list(n2.continuation_word),
        "n2b_first_separation_depth": n2.first_separation_depth,
        "depth2_shortest_word": list(d2.continuation_word),
        "depth2_first_separation_depth": d2.first_separation_depth,
        "empty_word_current_separation": True,
        "depth2_index_fingerprint": index2.fingerprint(),
    }


def tie_break_gate() -> dict[str, object]:
    """Semantic minimality is order invariant; canonical equal-length choice is not."""

    rows = (
        (2, 2),
        (3, 3),
        (2, 2),
        (3, 3),
    )
    forward = TableTargetModel(
        outputs=("A", "A", "B", "C"),
        continuations=("0", "1"),
        next_state=rows,
    )
    reverse = TableTargetModel(
        outputs=("A", "A", "B", "C"),
        continuations=("0", "1"),
        next_state=rows,
        continuation_order=("1", "0"),
    )
    claim = ClaimSpec("witness-tie-break", ("operation",), 1, "event")

    fq = compile_bounded_q(forward, claim)
    rq = compile_bounded_q(reverse, claim)
    fw = compile_predictive_witnesses(fq).witness("s0", "s1")
    rw = compile_predictive_witnesses(rq).witness("s0", "s1")
    assert fw is not None and rw is not None
    assert fw.witness_length == rw.witness_length == 1
    assert fw.continuation_word == ("0",)
    assert rw.continuation_word == ("1",)
    assert fw.continuation_word == shortest_distinguishing_word(
        forward, claim, "s0", "s1", 1
    )
    assert rw.continuation_word == shortest_distinguishing_word(
        reverse, claim, "s0", "s1", 1
    )
    assert fq.equivalent("s0", "s1", 1) == rq.equivalent("s0", "s1", 1) is False

    return {
        "minimum_length": 1,
        "forward_declared_order_choice": list(fw.continuation_word),
        "reverse_declared_order_choice": list(rw.continuation_word),
        "semantic_relation_unchanged": True,
        "canonical_tie_break_is_declared_continuation_order": True,
    }


def witness_semantics_split_gate() -> dict[str, object]:
    """Prove predictive witnesses and R* counterexamples are distinct objects."""

    target = TableTargetModel(
        outputs=("A", "B"),
        continuations=("x",),
        next_state=((0,), (1,)),
    )
    claim = ClaimSpec("witness-semantics-split", ("operation",), 0, "event")
    quotient = compile_bounded_q(target, claim)
    predictive = compile_predictive_witnesses(quotient).witness("s0", "s1")
    assert predictive is not None
    assert predictive.continuation_word == ()

    evidence = EvidenceSpec("oracle-only-rstar-counterexample", (("both", ("s0", "s1")),))
    recorded = ProjectedAction.from_mapping({"operation": "A"})
    reuse = definition_rstar(target, claim, evidence, "both", recorded)
    assert reuse.disposition.value == "DO_NOT_REUSE"
    assert reuse.maximality_counterexample == "s1"

    # The two certificates answer different questions and share no generic
    # shortest-witness surface.
    assert not hasattr(predictive, "observation")
    assert not hasattr(predictive, "projected_action")
    assert not hasattr(predictive, "maximality_counterexample")
    assert not hasattr(reuse, "continuation_word")
    assert isinstance(reuse.maximality_counterexample, str)
    assert isinstance(predictive.continuation_word, tuple)

    return {
        "predictive_object": "pairwise shortest continuation word",
        "reuse_counterexample_object": "one compatible raw world excluding recorded z",
        "predictive_depends_on_observation": False,
        "predictive_depends_on_historical_action": False,
        "reuse_counterexample_has_shortest_word_semantics": False,
    }


def fail_closed_gate() -> dict[str, bool]:
    target = TableTargetModel(
        outputs=("A", "A", "B"),
        continuations=("0", "1"),
        next_state=((1, 2), (1, 2), (2, 2)),
    )
    claim = ClaimSpec("witness-fail-closed", ("operation",), 2, "event")
    quotient = compile_bounded_q(target, claim)
    index = compile_predictive_witnesses(quotient)

    try:
        compile_predictive_witnesses(quotient, depth=3)
    except IndexError:
        deeper_rejected = True
    else:
        raise AssertionError("predictive witness compiler must not invent H+1")

    try:
        index.witness("s0", "not-a-state")
    except KeyError:
        unknown_world_rejected = True
    else:
        raise AssertionError("witness lookup must reject unknown worlds")

    malformed_rows = list(quotient.deterministic_successors)
    state, rows = malformed_rows[0]
    malformed_rows[0] = (state, rows[:-1])
    malformed = replace(quotient, deterministic_successors=tuple(malformed_rows))
    try:
        compile_predictive_witnesses(malformed)
    except MalformedQuotientWitnessError:
        malformed_successor_rejected = True
    else:
        raise AssertionError("witness synthesis must reject malformed q successors")

    return {
        "no_hidden_deeper_layer": deeper_rejected,
        "unknown_world_rejected": unknown_world_rejected,
        "malformed_q_successor_rejected": malformed_successor_rejected,
    }


def exhaustive_small_machine_gate() -> dict[str, object]:
    """All 3-state/2-input/2-output machines, all pairs, all depths 0..3."""

    outputs = ("A", "B")
    continuations = ("0", "1")
    claim = ClaimSpec("predictive-witness-exhaustive", ("operation",), 3, "event")
    machine_count = 0
    pair_depth_queries = 0
    produced_witnesses = 0
    equivalent_queries = 0
    minimality_depth_checks = 0
    trace_certificate_checks = 0
    symmetry_checks = 0
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
            states = target.decision_states

            for depth in range(4):
                index = compile_predictive_witnesses(quotient, depth=depth)
                for i, left in enumerate(states):
                    for right in states[i + 1 :]:
                        production = index.witness(left, right)
                        oracle_word = shortest_distinguishing_word(
                            target, claim, left, right, depth
                        )
                        if production is None:
                            assert oracle_word is None
                            assert quotient.equivalent(left, right, depth)
                            equivalent_queries += 1
                        else:
                            assert oracle_word is not None
                            assert production.continuation_word == oracle_word
                            assert not quotient.equivalent(left, right, depth)
                            assert production.first_separation_depth == len(oracle_word)
                            assert production.first_separation_depth <= depth
                            # First q split is exactly the shortest distinguishing length.
                            for earlier in range(production.first_separation_depth):
                                assert quotient.equivalent(left, right, earlier)
                            assert not quotient.equivalent(
                                left, right, production.first_separation_depth
                            )
                            minimality_depth_checks += 1

                            assert production.left_trace == _deterministic_trace(
                                target,
                                claim,
                                production.left_state,
                                production.continuation_word,
                            )
                            assert production.right_trace == _deterministic_trace(
                                target,
                                claim,
                                production.right_state,
                                production.continuation_word,
                            )
                            assert production.left_trace != production.right_trace
                            trace_certificate_checks += 1
                            produced_witnesses += 1

                        assert index.witness(right, left) == production
                        symmetry_checks += 1
                        pair_depth_queries += 1
            machine_count += 1

    assert machine_count == 5832
    assert pair_depth_queries == 5832 * 3 * 4 == 69984
    assert produced_witnesses + equivalent_queries == pair_depth_queries
    assert minimality_depth_checks == produced_witnesses
    assert trace_certificate_checks == produced_witnesses
    assert symmetry_checks == pair_depth_queries

    return {
        "machines": machine_count,
        "unordered_state_pairs_per_machine": 3,
        "depths": [0, 1, 2, 3],
        "production_vs_definition_witness_queries": pair_depth_queries,
        "produced_witnesses": produced_witnesses,
        "equivalent_queries": equivalent_queries,
        "minimum_depth_checks": minimality_depth_checks,
        "trace_certificate_checks": trace_certificate_checks,
        "symmetric_lookup_checks": symmetry_checks,
        "elapsed_seconds": round(time.perf_counter() - start, 6),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    args = parser.parse_args()

    report = {
        "schema": "replaymark.predictive-continuation-witness.gate.v1",
        "thermostat": thermostat_gate(),
        "canonical_tie_break": tie_break_gate(),
        "witness_semantics_split": witness_semantics_split_gate(),
        "fail_closed": fail_closed_gate(),
        "exhaustive_small_machine": exhaustive_small_machine_gate(),
        "verdict": "PASS",
    }
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
