from __future__ import annotations

"""High-assurance differential verification for bounded q_{C,H} compilation."""

from itertools import product
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "agentmark_e3b_lab"
for path in (ROOT, LEGACY):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from agentmark.kernel import ReactiveKernel

from replaymark.compat_agentmark import (
    claim_from_agentmark_projection,
    target_model_from_agentmark_kernel,
)
from replaymark.contracts import ClaimSpec, TargetModel
from replaymark.q_compiler import (
    NonDeterministicTargetError,
    compile_bounded_q,
)
from replaymark_oracle.definition_q_oracle import (
    definition_partition,
    shortest_distinguishing_word,
    trace_law,
)
from replaymark_verification.models import (
    BetterThermostatFrozenModel,
    StochasticAdvanceModel,
    StochasticCurrentModel,
    TableTargetModel,
)


def same_relation(compiled_layer, oracle_partition, states: tuple[str, ...]) -> bool:
    for i, left in enumerate(states):
        for right in states[i:]:
            if compiled_layer.equivalent(left, right) != oracle_partition.equivalent(left, right):
                return False
    return True


def deterministic_trace_suffix(target: TargetModel, claim: ClaimSpec, state: str, word: tuple[str, ...]):
    law = trace_law(target, claim, state, word)
    if len(law) != 1 or next(iter(law.values())) != 1:
        raise AssertionError("expected deterministic trace law")
    trace = next(iter(law))
    return tuple(action.as_dict()["operation"] for action in trace[1:])


def e3b_gate() -> dict[str, object]:
    kernel = ReactiveKernel(
        {
            "initial_state": "after_act1",
            "feedback_alphabet": [
                "confirmed_by_deadline",
                "not_visible_by_deadline",
            ],
            "states": {
                "after_act1": {
                    "confirmed_by_deadline": [
                        {"p": 1, "operation": "ACT2", "target_class": "stage2", "next_state": "done"}
                    ],
                    "not_visible_by_deadline": [
                        {"p": 1, "operation": "VERIFY", "target_class": "stage1", "next_state": "verified"}
                    ],
                },
                "verified": {
                    "confirmed_by_deadline": [
                        {"p": 1, "operation": "ACT2", "target_class": "stage2", "next_state": "done"}
                    ],
                    "not_visible_by_deadline": [
                        {"p": 1, "operation": "ACT2", "target_class": "stage2", "next_state": "done"}
                    ],
                },
                "done": {
                    "confirmed_by_deadline": [
                        {"p": 1, "operation": "DONE", "next_state": "done"}
                    ],
                    "not_visible_by_deadline": [
                        {"p": 1, "operation": "DONE", "next_state": "done"}
                    ],
                },
            },
        }
    )
    target = target_model_from_agentmark_kernel(kernel)
    assert isinstance(target, TargetModel)
    claim = claim_from_agentmark_projection(
        "operation",
        horizon=3,
        claim_id="e3b-frozen-operation-q",
        consequence_endpoint="controller-operation",
    )
    compiled = compile_bounded_q(target, claim)
    counts = [layer.block_count for layer in compiled.layers]
    assert len(target.decision_states) == 6
    assert counts == [3, 3, 3, 3], counts
    assert compiled.first_observed_fixed_point == 0
    for depth in range(4):
        oracle = definition_partition(target, claim, depth)
        assert same_relation(compiled.layer(depth), oracle, target.decision_states)
    return {
        "decision_states": len(target.decision_states),
        "q_counts": counts,
        "first_observed_fixed_point": compiled.first_observed_fixed_point,
        "compiler_fingerprint": compiled.fingerprint(),
    }


def thermostat_gate() -> dict[str, object]:
    target = BetterThermostatFrozenModel()
    claim = ClaimSpec(
        "better-thermostat-frozen-preset-action",
        ("operation",),
        4,
        "consequential-preset-service-action",
    )
    compiled = compile_bounded_q(target, claim)
    counts = [layer.block_count for layer in compiled.layers]
    assert len(target.decision_states) == 32
    assert counts == [5, 14, 16, 16, 16], counts
    assert compiled.first_observed_fixed_point == 2

    for depth in range(5):
        oracle = definition_partition(target, claim, depth)
        assert same_relation(compiled.layer(depth), oracle, target.decision_states)

    stable = compiled.layer(4)
    for i, left in enumerate(target.decision_states):
        for right in target.decision_states[i:]:
            expected = target.stable_key(left) == target.stable_key(right)
            assert stable.equivalent(left, right) == expected

    n2a = target.encode(False, False, False, "sleep")
    n2b = target.encode(False, True, False, "sleep")
    witness1 = shortest_distinguishing_word(target, claim, n2a, n2b, 2)
    assert witness1 == ("presence_toggle",), witness1
    assert deterministic_trace_suffix(target, claim, n2a, witness1) == ("SET_HOME",)
    assert deterministic_trace_suffix(target, claim, n2b, witness1) == ("SET_COMFORT",)

    d2a = target.encode(False, False, True, "sleep")
    d2b = target.encode(False, True, True, "sleep")
    witness2 = shortest_distinguishing_word(target, claim, d2a, d2b, 2)
    assert witness2 == ("presence_toggle", "night_toggle"), witness2
    assert deterministic_trace_suffix(target, claim, d2a, witness2) == (
        "NO_ACTION",
        "SET_HOME",
    )
    assert deterministic_trace_suffix(target, claim, d2b, witness2) == (
        "NO_ACTION",
        "SET_COMFORT",
    )

    target56 = BetterThermostatFrozenModel(
        ("away", "home", "comfort", "sleep", "boost", "eco", "activity")
    )
    claim56 = ClaimSpec("bt-seven-presets", ("operation",), 3, "preset-action")
    compiled56 = compile_bounded_q(target56, claim56)
    assert len(target56.decision_states) == 56
    assert [x.block_count for x in compiled56.layers] == [5, 14, 16, 16]

    q1 = compile_bounded_q(
        target, ClaimSpec("bt-h1", ("operation",), 1, "preset-action")
    )
    q2 = compile_bounded_q(
        target, ClaimSpec("bt-h2", ("operation",), 2, "preset-action")
    )
    q3 = compile_bounded_q(
        target, ClaimSpec("bt-h3", ("operation",), 3, "preset-action")
    )
    assert [x.block_count for x in q1.layers] == [5, 14]
    assert [x.block_count for x in q2.layers] == [5, 14, 16]
    assert q1.first_observed_fixed_point is None
    assert q2.first_observed_fixed_point is None
    assert q3.first_observed_fixed_point == 2

    return {
        "decision_states": len(target.decision_states),
        "q_counts": counts,
        "first_observed_fixed_point": compiled.first_observed_fixed_point,
        "n2b_witness": list(witness1),
        "depth2_witness": list(witness2),
        "all_seven_preset_states": len(target56.decision_states),
        "all_seven_preset_q_counts": [x.block_count for x in compiled56.layers],
        "compiler_fingerprint": compiled.fingerprint(),
    }


def projection_gate() -> dict[str, int]:
    model = TableTargetModel(
        outputs=("climate.set_preset_mode", "climate.set_preset_mode"),
        variants=("preset=home", "preset=away"),
        continuations=("tick",),
        next_state=((0,), (1,)),
    )
    operation = ClaimSpec("op", ("operation",), 0, "service")
    action = ClaimSpec("action", ("operation", "variant"), 0, "service")
    op_q = compile_bounded_q(model, operation)
    action_q = compile_bounded_q(model, action)
    assert op_q.block_count() == 1
    assert action_q.block_count() == 2
    assert definition_partition(model, operation).block_count == 1
    assert definition_partition(model, action).block_count == 2
    return {"operation_classes": 1, "action_classes": 2}


def stochastic_fail_closed_gate() -> dict[str, bool]:
    operation0 = ClaimSpec("stoch-current", ("operation",), 0, "event")
    stochastic_current = StochasticCurrentModel()
    assert definition_partition(stochastic_current, operation0).block_count == 1
    try:
        compile_bounded_q(stochastic_current, operation0)
    except NonDeterministicTargetError:
        current_rejected = True
    else:
        raise AssertionError("compiler must fail closed on stochastic current action")

    operation1 = ClaimSpec("stoch-advance", ("operation",), 1, "event")
    stochastic_advance = StochasticAdvanceModel()
    definition_partition(stochastic_advance, operation1)
    try:
        compile_bounded_q(stochastic_advance, operation1)
    except NonDeterministicTargetError:
        advance_rejected = True
    else:
        raise AssertionError("compiler must fail closed on stochastic continuation")
    return {
        "stochastic_current_rejected": current_rejected,
        "stochastic_advance_rejected": advance_rejected,
    }


def exhaustive_small_machine_gate() -> dict[str, object]:
    """Exhaust every 3-state/2-input/2-output deterministic complete machine."""

    outputs = ("A", "B")
    continuations = ("0", "1")
    claim = ClaimSpec("exhaustive-small", ("operation",), 3, "output")
    machine_count = 0
    relation_layer_checks = 0
    start = time.perf_counter()

    for output_assignment in product(outputs, repeat=3):
        for flat_next in product(range(3), repeat=6):
            rows = (
                (flat_next[0], flat_next[1]),
                (flat_next[2], flat_next[3]),
                (flat_next[4], flat_next[5]),
            )
            model = TableTargetModel(
                outputs=tuple(output_assignment),
                continuations=continuations,
                next_state=rows,
            )
            compiled = compile_bounded_q(model, claim)
            states = model.decision_states
            for depth in range(4):
                oracle = definition_partition(model, claim, depth)
                if not same_relation(compiled.layer(depth), oracle, states):
                    raise AssertionError(
                        "compiler/oracle relation mismatch: "
                        f"outputs={output_assignment}, next={rows}, depth={depth}"
                    )
                relation_layer_checks += 1
            machine_count += 1

    assert machine_count == 5832
    assert relation_layer_checks == 23328

    sample_rows = ((1, 2), (2, 0), (0, 1))
    forward = TableTargetModel(
        outputs=("A", "A", "B"),
        continuations=continuations,
        next_state=sample_rows,
    )
    reverse = TableTargetModel(
        outputs=("A", "A", "B"),
        continuations=continuations,
        next_state=sample_rows,
        continuation_order=("1", "0"),
    )
    fq = compile_bounded_q(forward, claim)
    rq = compile_bounded_q(reverse, claim)
    for depth in range(4):
        for i, left in enumerate(forward.decision_states):
            for right in forward.decision_states[i:]:
                assert fq.equivalent(left, right, depth) == rq.equivalent(left, right, depth)

    elapsed = time.perf_counter() - start
    return {
        "machines": machine_count,
        "compiler_oracle_layer_relations": relation_layer_checks,
        "horizons": [0, 1, 2, 3],
        "continuation_order_invariance": True,
        "elapsed_seconds": round(elapsed, 6),
    }


def main() -> None:
    report = {
        "schema": "replaymark.qch.compiler_oracle_gate.v1",
        "e3b": e3b_gate(),
        "better_thermostat": thermostat_gate(),
        "projection": projection_gate(),
        "stochastic_boundary": stochastic_fail_closed_gate(),
        "exhaustive_small_machine": exhaustive_small_machine_gate(),
        "verdict": "PASS",
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
