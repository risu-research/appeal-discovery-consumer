from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import math
from typing import Any, Iterable, Mapping

from .kernel import ReactiveKernel
from .minimize import quotient


ProjectedEvent = Any


@dataclass(frozen=True)
class FeedbackPartition:
    state: str
    projection: str
    classes: tuple[tuple[str, ...], ...]
    unsupported: tuple[str, ...]


@dataclass(frozen=True)
class StepReplayValidity:
    state: str
    source_feedback: str
    target_feedback: str
    recorded_event: ProjectedEvent
    source_probability: Fraction
    target_probability: Fraction
    source_consistent: bool
    target_supports_recorded_event: bool
    support_failure: bool
    log_target_over_source: float | None


def total_variation(
    left: Mapping[ProjectedEvent, Fraction | int | float],
    right: Mapping[ProjectedEvent, Fraction | int | float],
) -> Fraction:
    keys = set(left) | set(right)
    return Fraction(1, 2) * sum(
        (
            abs(Fraction(left.get(key, 0)) - Fraction(right.get(key, 0)))
            for key in keys
        ),
        Fraction(0, 1),
    )


def normalize_law(
    law: Mapping[str, Fraction | int | float],
) -> dict[str, Fraction]:
    out = {
        str(symbol): Fraction(value)
        for symbol, value in law.items()
        if Fraction(value) > 0
    }
    total = sum(out.values(), Fraction(0, 1))
    if total <= 0:
        raise ValueError("law must have positive mass")
    return {symbol: value / total for symbol, value in out.items()}


def feedback_partition(
    kernel: ReactiveKernel,
    state: str,
    *,
    projection: str = "operation",
) -> FeedbackPartition:
    """Partition feedback by the projected controller behavior it induces."""

    q = quotient(kernel)
    buckets: dict[tuple[Any, ...], list[str]] = {}
    unsupported: list[str] = []

    for feedback in kernel.feedback_alphabet:
        if not kernel.has_feedback(state, feedback):
            unsupported.append(feedback)
            continue
        signature = kernel.canonical_signature(
            state,
            feedback,
            state_blocks=q.state_to_block,
            projection=projection,
        )
        buckets.setdefault(signature, []).append(feedback)

    classes = [tuple(sorted(values)) for values in buckets.values()]
    classes.sort(key=lambda values: values)
    return FeedbackPartition(
        state=str(state),
        projection=projection,
        classes=tuple(classes),
        unsupported=tuple(sorted(unsupported)),
    )


def quotient_feedback_law(
    law: Mapping[str, Fraction | int | float],
    partition: FeedbackPartition,
) -> dict[tuple[str, ...], Fraction]:
    """Push a feedback law onto decision-equivalence classes."""

    normalized = normalize_law(law)
    illegal = set(normalized) & set(partition.unsupported)
    if illegal:
        raise ValueError(f"law assigns mass to unsupported feedback: {sorted(illegal)}")

    known = {symbol for cls in partition.classes for symbol in cls}
    unknown = set(normalized) - known
    if unknown:
        raise ValueError(f"law contains feedback outside the partition: {sorted(unknown)}")

    return {
        cls: sum((normalized.get(symbol, Fraction(0, 1)) for symbol in cls), Fraction(0, 1))
        for cls in partition.classes
    }


def live_workload_distribution(
    kernel: ReactiveKernel,
    state: str,
    feedback_law: Mapping[str, Fraction | int | float],
    *,
    projection: str = "operation",
) -> dict[ProjectedEvent, Fraction]:
    """Push a feedback distribution through the live controller kernel."""

    normalized = normalize_law(feedback_law)
    q = quotient(kernel)
    out: dict[ProjectedEvent, Fraction] = {}

    for feedback, feedback_mass in normalized.items():
        if not kernel.has_feedback(state, feedback):
            raise ValueError(
                f"controller has no transition for state={state!r}, feedback={feedback!r}"
            )
        distribution = kernel.distribution(
            state,
            feedback,
            state_blocks=q.state_to_block,
            projection=projection,
        )
        for event, event_mass in distribution.items():
            out[event] = out.get(event, Fraction(0, 1)) + feedback_mass * event_mass
    return out


def workload_shift_tv(
    kernel: ReactiveKernel,
    state: str,
    source_feedback_law: Mapping[str, Fraction | int | float],
    target_feedback_law: Mapping[str, Fraction | int | float],
    *,
    projection: str = "operation",
) -> Fraction:
    return total_variation(
        live_workload_distribution(
            kernel,
            state,
            source_feedback_law,
            projection=projection,
        ),
        live_workload_distribution(
            kernel,
            state,
            target_feedback_law,
            projection=projection,
        ),
    )


def policy_sensitivity_eta(
    kernel: ReactiveKernel,
    state: str,
    *,
    projection: str = "operation",
) -> Fraction:
    """Dobrushin coefficient of feedback -> projected controller behavior."""

    q = quotient(kernel)
    feedback = [
        symbol
        for symbol in kernel.feedback_alphabet
        if kernel.has_feedback(state, symbol)
    ]
    best = Fraction(0, 1)
    for i, left_symbol in enumerate(feedback):
        left = kernel.distribution(
            state,
            left_symbol,
            state_blocks=q.state_to_block,
            projection=projection,
        )
        for right_symbol in feedback[i + 1 :]:
            right = kernel.distribution(
                state,
                right_symbol,
                state_blocks=q.state_to_block,
                projection=projection,
            )
            best = max(best, total_variation(left, right))
    return best


def projected_event_probability(
    kernel: ReactiveKernel,
    state: str,
    feedback: str,
    event: ProjectedEvent,
    *,
    projection: str = "operation",
) -> Fraction:
    if not kernel.has_feedback(state, feedback):
        return Fraction(0, 1)
    q = quotient(kernel)
    distribution = kernel.distribution(
        state,
        feedback,
        state_blocks=q.state_to_block,
        projection=projection,
    )
    return Fraction(distribution.get(event, Fraction(0, 1)))


def step_replay_validity(
    kernel: ReactiveKernel,
    *,
    state: str,
    source_feedback: str,
    target_feedback: str,
    recorded_event: ProjectedEvent,
    projection: str = "operation",
) -> StepReplayValidity:
    """Evaluate whether one source-recorded event remains target-admissible.

    A row is a support failure only when the recorded event is valid under the
    source controller but has zero probability under the controller conditioned
    on target feedback. Source-inconsistent rows are kept separate and fail
    closed rather than being counted as target failures.
    """

    source_probability = projected_event_probability(
        kernel,
        state,
        source_feedback,
        recorded_event,
        projection=projection,
    )
    target_probability = projected_event_probability(
        kernel,
        state,
        target_feedback,
        recorded_event,
        projection=projection,
    )

    source_consistent = source_probability > 0
    target_supports = target_probability > 0
    support_failure = source_consistent and not target_supports

    if not source_consistent:
        log_ratio = None
    elif not target_supports:
        log_ratio = -math.inf
    else:
        log_ratio = math.log(float(target_probability / source_probability))

    return StepReplayValidity(
        state=str(state),
        source_feedback=str(source_feedback),
        target_feedback=str(target_feedback),
        recorded_event=recorded_event,
        source_probability=source_probability,
        target_probability=target_probability,
        source_consistent=source_consistent,
        target_supports_recorded_event=target_supports,
        support_failure=support_failure,
        log_target_over_source=log_ratio,
    )


def trace_replay_validity(
    kernel: ReactiveKernel,
    rows: Iterable[Mapping[str, Any]],
    *,
    projection: str = "operation",
    event_key: str = "event",
) -> dict[str, Any]:
    """Fail-closed target-support audit for a recorded controller trace."""

    details: list[dict[str, Any]] = []
    failures = 0
    source_inconsistencies = 0
    cumulative_log_ratio = 0.0

    for index, row in enumerate(rows):
        verdict = step_replay_validity(
            kernel,
            state=str(row["state"]),
            source_feedback=str(row["source_feedback"]),
            target_feedback=str(row["target_feedback"]),
            recorded_event=row[event_key],
            projection=projection,
        )
        if not verdict.source_consistent:
            source_inconsistencies += 1
        if verdict.support_failure:
            failures += 1

        step_log_ratio = verdict.log_target_over_source
        if step_log_ratio == -math.inf:
            cumulative_log_ratio = -math.inf
        elif step_log_ratio is not None and math.isfinite(cumulative_log_ratio):
            cumulative_log_ratio += step_log_ratio

        details.append(
            {
                "index": index,
                "state": verdict.state,
                "source_feedback": verdict.source_feedback,
                "target_feedback": verdict.target_feedback,
                "recorded_event": verdict.recorded_event,
                "source_probability": float(verdict.source_probability),
                "target_probability": float(verdict.target_probability),
                "source_consistent": verdict.source_consistent,
                "target_supports_recorded_event": verdict.target_supports_recorded_event,
                "support_failure": verdict.support_failure,
                "log_target_over_source": step_log_ratio,
            }
        )

    entire_trace_supported = failures == 0 and source_inconsistencies == 0
    likelihood_ratio = (
        0.0
        if cumulative_log_ratio == -math.inf
        else math.exp(cumulative_log_ratio)
    )
    return {
        "schema": "agentmark.replay_validity.v1",
        "projection": projection,
        "rows": details,
        "support_failures": failures,
        "source_inconsistencies": source_inconsistencies,
        "target_supports_entire_recorded_trace": entire_trace_supported,
        "conditional_controller_log_likelihood_ratio": cumulative_log_ratio,
        "conditional_controller_likelihood_ratio": likelihood_ratio,
    }
