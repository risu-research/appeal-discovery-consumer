from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from .kernel import ReactiveKernel


@dataclass(frozen=True)
class QuotientResult:
    """Exact finite quotient used by AgentMark's replay semantics.

    ``state_to_block`` and ``blocks`` are the behavioral state quotient.
    ``state_feedback_classes`` partitions supported feedback symbols that induce
    the same full projected transition distribution at a given state after state
    minimization. ``global_feedback_classes`` is the corresponding partition
    when equivalence must hold at every controller state.

    Unsupported feedback is deliberately kept separate rather than silently
    merged with a supported class: replay validity is fail-closed.
    """

    state_to_block: dict[str, str]
    blocks: dict[str, tuple[str, ...]]
    state_feedback_classes: dict[str, tuple[tuple[str, ...], ...]]
    state_unsupported_feedback: dict[str, tuple[str, ...]]
    global_feedback_classes: tuple[tuple[str, ...], ...]
    minimized_spec: dict[str, Any]


def _sorted_classes(buckets: dict[Any, list[str]]) -> tuple[tuple[str, ...], ...]:
    classes = [tuple(sorted(values)) for values in buckets.values()]
    classes.sort(key=lambda values: values)
    return tuple(classes)


def _canonical_rows(
    kernel: ReactiveKernel,
    state: str,
    feedback: str,
    *,
    state_to_block: dict[str, str],
) -> list[dict[str, Any]]:
    """Return a deterministic, probability-preserving row representation."""

    merged: dict[tuple[str, str | None, int, str], Fraction] = defaultdict(Fraction)
    for atom in kernel.atoms(state, feedback, state_blocks=state_to_block):
        if atom.probability <= 0:
            continue
        event = atom.event
        key = (event.operation, event.target_class, event.delay_ms, event.next_state)
        merged[key] += atom.probability

    rows: list[dict[str, Any]] = []
    for (operation, target_class, delay_ms, next_state), probability in sorted(
        merged.items(),
        key=lambda item: repr(item[0]),
    ):
        row: dict[str, Any] = {
            "p": (
                probability.numerator
                if probability.denominator == 1
                else f"{probability.numerator}/{probability.denominator}"
            ),
            "operation": operation,
            "next_state": next_state,
        }
        if target_class is not None:
            row["target_class"] = target_class
        if delay_ms:
            row["delay_ms"] = delay_ms
        rows.append(row)
    return rows


def quotient(kernel: ReactiveKernel) -> QuotientResult:
    """Compute the exact finite behavioral quotient and feedback partitions.

    State partition refinement uses the full transition signature, including
    operation, target class, delay, and successor quotient block. Once stable,
    feedback symbols are partitioned by the same full signature. This is the
    strongest built-in equivalence; paper-facing analyses may intentionally
    project further (for example to operation identity) without weakening this
    structural quotient.
    """

    groups = [list(kernel.states)]
    changed = True
    while changed:
        changed = False
        mapping = {state: f"q{i}" for i, group in enumerate(groups) for state in group}
        refined: list[list[str]] = []
        for group in groups:
            buckets: dict[tuple[Any, ...], list[str]] = {}
            for state in group:
                signature = tuple(
                    kernel.canonical_signature(
                        state,
                        feedback,
                        state_blocks=mapping,
                        projection="full",
                    )
                    for feedback in kernel.feedback_alphabet
                )
                buckets.setdefault(signature, []).append(state)
            if len(buckets) > 1:
                changed = True
            refined.extend(buckets.values())
        groups = refined

    normalized_groups = [sorted(group) for group in groups]
    normalized_groups.sort(key=lambda group: group[0])
    state_to_block = {
        state: f"q{i}"
        for i, group in enumerate(normalized_groups)
        for state in group
    }
    blocks = {
        f"q{i}": tuple(group)
        for i, group in enumerate(normalized_groups)
    }

    state_feedback_classes: dict[str, tuple[tuple[str, ...], ...]] = {}
    state_unsupported_feedback: dict[str, tuple[str, ...]] = {}
    for state in kernel.states:
        buckets: dict[tuple[Any, ...], list[str]] = {}
        unsupported: list[str] = []
        for feedback in kernel.feedback_alphabet:
            if not kernel.has_feedback(state, feedback):
                unsupported.append(feedback)
                continue
            signature = kernel.canonical_signature(
                state,
                feedback,
                state_blocks=state_to_block,
                projection="full",
            )
            buckets.setdefault(signature, []).append(feedback)
        state_feedback_classes[state] = _sorted_classes(buckets)
        state_unsupported_feedback[state] = tuple(sorted(unsupported))

    global_buckets: dict[tuple[Any, ...], list[str]] = {}
    for feedback in kernel.feedback_alphabet:
        signature = tuple(
            (
                kernel.canonical_signature(
                    state,
                    feedback,
                    state_blocks=state_to_block,
                    projection="full",
                )
                if kernel.has_feedback(state, feedback)
                else (ReactiveKernel.MISSING,)
            )
            for state in kernel.states
        )
        global_buckets.setdefault(signature, []).append(feedback)
    global_feedback_classes = _sorted_classes(global_buckets)

    minimized_states: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for block, members in blocks.items():
        representative = members[0]
        by_feedback: dict[str, list[dict[str, Any]]] = {}
        for feedback in kernel.feedback_alphabet:
            if kernel.has_feedback(representative, feedback):
                by_feedback[feedback] = _canonical_rows(
                    kernel,
                    representative,
                    feedback,
                    state_to_block=state_to_block,
                )
        minimized_states[block] = by_feedback

    minimized_spec = {
        "initial_state": state_to_block[kernel.initial_state],
        "feedback_alphabet": list(kernel.feedback_alphabet),
        "states": minimized_states,
    }

    return QuotientResult(
        state_to_block=state_to_block,
        blocks=blocks,
        state_feedback_classes=state_feedback_classes,
        state_unsupported_feedback=state_unsupported_feedback,
        global_feedback_classes=global_feedback_classes,
        minimized_spec=minimized_spec,
    )
