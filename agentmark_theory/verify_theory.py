from __future__ import annotations

from fractions import Fraction
import itertools
import json

from agentmark.kernel import ReactiveKernel
from agentmark.minimize import quotient
from agentmark.semantics import (
    feedback_partition,
    live_workload_distribution,
    normalize_law,
    policy_sensitivity_eta,
    quotient_feedback_law,
    step_replay_validity,
    total_variation,
    trace_replay_validity,
    workload_shift_tv,
)


def deterministic_kernel(mapping: dict[str, str]) -> ReactiveKernel:
    return ReactiveKernel(
        {
            "initial_state": "s",
            "feedback_alphabet": list(mapping),
            "states": {
                "s": {
                    feedback: [
                        {"p": 1, "operation": operation, "next_state": "s"}
                    ]
                    for feedback, operation in mapping.items()
                }
            },
        }
    )


def stochastic_binary_kernel(prob_a0: dict[str, Fraction]) -> ReactiveKernel:
    return ReactiveKernel(
        {
            "initial_state": "s",
            "feedback_alphabet": list(prob_a0),
            "states": {
                "s": {
                    feedback: [
                        {"p": p, "operation": "a0", "next_state": "s"},
                        {"p": 1 - p, "operation": "a1", "next_state": "s"},
                    ]
                    for feedback, p in prob_a0.items()
                }
            },
        }
    )


def count_laws(symbols: list[str], total: int) -> list[dict[str, int]]:
    laws: list[dict[str, int]] = []
    for counts in itertools.product(range(total + 1), repeat=len(symbols)):
        if sum(counts) == total:
            laws.append(dict(zip(symbols, counts)))
    return laws


def verify_zero_mass_canonicality() -> int:
    with_zero = ReactiveKernel(
        {
            "initial_state": "s",
            "feedback_alphabet": ["x", "y"],
            "states": {
                "s": {
                    "x": [
                        {"p": 1, "operation": "a", "next_state": "s"},
                        {"p": 0, "operation": "never", "next_state": "s"},
                    ],
                    "y": [{"p": 1, "operation": "a", "next_state": "s"}],
                }
            },
        }
    )
    assert with_zero.canonical_signature("s", "x", projection="operation") == (
        with_zero.canonical_signature("s", "y", projection="operation")
    )
    part = feedback_partition(with_zero, "s", projection="operation")
    assert part.classes == (("x", "y"),)
    return 1


def verify_quotient_completion() -> int:
    kernel = ReactiveKernel(
        {
            "initial_state": "s0",
            "feedback_alphabet": ["visible", "miss"],
            "states": {
                "s0": {
                    "visible": [{"p": 1, "operation": "go", "next_state": "s0"}],
                    "miss": [{"p": 1, "operation": "stop", "next_state": "s1"}],
                },
                "s1": {
                    "visible": [{"p": 1, "operation": "go", "next_state": "s0"}],
                    "miss": [{"p": 1, "operation": "stop", "next_state": "s1"}],
                },
            },
        }
    )
    q = quotient(kernel)
    assert len(q.blocks) == 1
    assert q.state_feedback_classes["s0"] == (("miss",), ("visible",))
    assert q.global_feedback_classes == (("miss",), ("visible",))
    minimized = ReactiveKernel(q.minimized_spec)
    for feedback in kernel.feedback_alphabet:
        assert kernel.distribution(
            "s0",
            feedback,
            state_blocks=q.state_to_block,
            projection="full",
        ) == minimized.distribution(
            minimized.initial_state,
            feedback,
            projection="full",
        )
    return 1


def verify_action_identity_projection() -> int:
    """Same service name may still encode semantically distinct actions."""

    kernel = ReactiveKernel(
        {
            "initial_state": "s",
            "feedback_alphabet": ["home", "away"],
            "states": {
                "s": {
                    "home": [
                        {
                            "p": 1,
                            "operation": "climate.set_preset_mode",
                            "target_class": "climate",
                            "variant": "preset=home",
                            "next_state": "s",
                        }
                    ],
                    "away": [
                        {
                            "p": 1,
                            "operation": "climate.set_preset_mode",
                            "target_class": "climate",
                            "variant": "preset=away",
                            "next_state": "s",
                        }
                    ],
                }
            },
        }
    )

    operation_partition = feedback_partition(
        kernel,
        "s",
        projection="operation",
    )
    action_partition = feedback_partition(
        kernel,
        "s",
        projection="action",
    )
    assert operation_partition.classes == (("away", "home"),)
    assert action_partition.classes == (("away",), ("home",))

    operation_shift = workload_shift_tv(
        kernel,
        "s",
        {"home": 1},
        {"away": 1},
        projection="operation",
    )
    action_shift = workload_shift_tv(
        kernel,
        "s",
        {"home": 1},
        {"away": 1},
        projection="action",
    )
    assert operation_shift == 0
    assert action_shift == 1

    op_verdict = step_replay_validity(
        kernel,
        state="s",
        source_feedback="home",
        target_feedback="away",
        recorded_event="climate.set_preset_mode",
        projection="operation",
    )
    action_verdict = step_replay_validity(
        kernel,
        state="s",
        source_feedback="home",
        target_feedback="away",
        recorded_event=("climate.set_preset_mode", "climate", "preset=home"),
        projection="action",
    )
    assert op_verdict.target_supports_recorded_event
    assert not op_verdict.support_failure
    assert action_verdict.source_consistent
    assert action_verdict.support_failure

    q = quotient(kernel)
    minimized = ReactiveKernel(q.minimized_spec)
    for feedback in kernel.feedback_alphabet:
        assert kernel.distribution(
            "s",
            feedback,
            state_blocks=q.state_to_block,
            projection="full",
        ) == minimized.distribution(
            minimized.initial_state,
            feedback,
            projection="full",
        )

    return 5


def verify_deterministic_decision_quotient() -> tuple[int, int]:
    feedback = ["y0", "y1", "y2"]
    operations = ["a0", "a1"]
    laws = count_laws(feedback, total=3)
    quotient_cases = 0
    support_cases = 0

    for actions in itertools.product(operations, repeat=len(feedback)):
        mapping = dict(zip(feedback, actions))
        kernel = deterministic_kernel(mapping)
        partition = feedback_partition(kernel, "s", projection="operation")

        for source_law in laws:
            for target_law in laws:
                source_workload = live_workload_distribution(
                    kernel,
                    "s",
                    source_law,
                    projection="operation",
                )
                target_workload = live_workload_distribution(
                    kernel,
                    "s",
                    target_law,
                    projection="operation",
                )
                source_classes = quotient_feedback_law(source_law, partition)
                target_classes = quotient_feedback_law(target_law, partition)
                assert total_variation(source_workload, target_workload) == (
                    total_variation(source_classes, target_classes)
                )
                quotient_cases += 1

        for source_feedback in feedback:
            recorded = mapping[source_feedback]
            for target_feedback in feedback:
                verdict = step_replay_validity(
                    kernel,
                    state="s",
                    source_feedback=source_feedback,
                    target_feedback=target_feedback,
                    recorded_event=recorded,
                    projection="operation",
                )
                assert verdict.source_consistent
                assert verdict.target_supports_recorded_event == (
                    mapping[target_feedback] == recorded
                )
                assert verdict.support_failure == (
                    mapping[target_feedback] != recorded
                )
                support_cases += 1

    return quotient_cases, support_cases


def verify_insensitive_and_injective_extremes() -> tuple[int, int]:
    feedback = ["v", "m"]
    laws = count_laws(feedback, total=4)

    insensitive = deterministic_kernel({"v": "a", "m": "a"})
    insensitive_cases = 0
    for source_law in laws:
        for target_law in laws:
            assert workload_shift_tv(
                insensitive,
                "s",
                source_law,
                target_law,
                projection="operation",
            ) == 0
            insensitive_cases += 1
    assert policy_sensitivity_eta(insensitive, "s", projection="operation") == 0

    injective = deterministic_kernel({"v": "a0", "m": "a1"})
    injective_cases = 0
    for source_law in laws:
        for target_law in laws:
            input_tv = total_variation(
                normalize_law(source_law),
                normalize_law(target_law),
            )
            output_tv = workload_shift_tv(
                injective,
                "s",
                source_law,
                target_law,
                projection="operation",
            )
            assert output_tv == input_tv
            injective_cases += 1
    assert policy_sensitivity_eta(injective, "s", projection="operation") == 1

    return insensitive_cases, injective_cases


def verify_stochastic_contraction() -> int:
    feedback = ["y0", "y1"]
    probability_grid = [Fraction(0), Fraction(1, 2), Fraction(1)]
    laws = count_laws(feedback, total=4)
    cases = 0

    for probabilities in itertools.product(
        probability_grid,
        repeat=len(feedback),
    ):
        kernel = stochastic_binary_kernel(dict(zip(feedback, probabilities)))
        eta = policy_sensitivity_eta(kernel, "s", projection="operation")
        for source_law in laws:
            for target_law in laws:
                input_tv = total_variation(
                    normalize_law(source_law),
                    normalize_law(target_law),
                )
                output_tv = workload_shift_tv(
                    kernel,
                    "s",
                    source_law,
                    target_law,
                    projection="operation",
                )
                assert output_tv <= eta * input_tv
                cases += 1

    return cases


def verify_trace_fail_closed() -> int:
    kernel = deterministic_kernel({"visible": "act2", "miss": "verify"})
    report = trace_replay_validity(
        kernel,
        [
            {
                "state": "s",
                "source_feedback": "visible",
                "target_feedback": "miss",
                "event": "act2",
            }
        ],
        projection="operation",
    )
    assert report["support_failures"] == 1
    assert report["source_inconsistencies"] == 0
    assert not report["target_supports_entire_recorded_trace"]
    assert report["conditional_controller_likelihood_ratio"] == 0.0

    inconsistent = trace_replay_validity(
        kernel,
        [
            {
                "state": "s",
                "source_feedback": "visible",
                "target_feedback": "visible",
                "event": "impossible",
            }
        ],
        projection="operation",
    )
    assert inconsistent["support_failures"] == 0
    assert inconsistent["source_inconsistencies"] == 1
    assert not inconsistent["target_supports_entire_recorded_trace"]
    return 2


def main() -> None:
    summary: dict[str, int | str] = {
        "schema": "agentmark.theory_lock.verification.v1",
        "zero_mass_canonicality_cases": verify_zero_mass_canonicality(),
        "quotient_completion_cases": verify_quotient_completion(),
        "action_identity_cases": verify_action_identity_projection(),
    }
    quotient_cases, support_cases = verify_deterministic_decision_quotient()
    summary["deterministic_quotient_cases"] = quotient_cases
    summary["deterministic_support_cases"] = support_cases
    insensitive_cases, injective_cases = verify_insensitive_and_injective_extremes()
    summary["feedback_insensitive_cases"] = insensitive_cases
    summary["injective_feedback_cases"] = injective_cases
    summary["stochastic_contraction_cases"] = verify_stochastic_contraction()
    summary["trace_fail_closed_cases"] = verify_trace_fail_closed()
    summary["total_cases"] = sum(
        value
        for key, value in summary.items()
        if key.endswith("_cases") and key != "total_cases" and isinstance(value, int)
    )
    summary["verdict"] = "PASS"
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
