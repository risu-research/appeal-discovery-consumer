from __future__ import annotations

"""Slow definition oracle for q_{C,H}.

The oracle deliberately enumerates continuation words and exact output-trace
laws. It shares only ReplayMark's public semantic types with production code and
does not import or imitate the bounded partition-refinement compiler.

Unlike compiler v1, this oracle can evaluate finite stochastic TargetModels:
two decision states are equivalent exactly when every continuation word through
H induces the same exact distribution over claim-projected output traces.
"""

from dataclasses import dataclass
from fractions import Fraction
from itertools import product
from typing import Mapping

from replaymark.contracts import ClaimSpec, ProjectedAction, TargetModel


Trace = tuple[ProjectedAction, ...]
Word = tuple[str, ...]


def _checked_law(distribution: Mapping[object, Fraction], *, where: str) -> list[tuple[object, Fraction]]:
    rows: list[tuple[object, Fraction]] = []
    total = Fraction(0, 1)
    for key, raw_mass in distribution.items():
        mass = Fraction(raw_mass)
        if mass < 0:
            raise ValueError(f"negative probability at {where}: {mass}")
        total += mass
        if mass > 0:
            rows.append((key, mass))
    if total != 1:
        raise ValueError(f"probability mass at {where} is {total}, expected exactly 1")
    if not rows:
        raise ValueError(f"empty positive support at {where}")
    return rows


def continuation_words(target: TargetModel, horizon: int) -> tuple[Word, ...]:
    if horizon < 0:
        raise ValueError("horizon must be >= 0")
    alphabet = tuple(str(x) for x in target.continuation_alphabet)
    if len(set(alphabet)) != len(alphabet):
        raise ValueError("continuation alphabet contains duplicates")
    words: list[Word] = [()]
    for length in range(1, horizon + 1):
        words.extend(tuple(x) for x in product(alphabet, repeat=length))
    return tuple(words)


def trace_law(
    target: TargetModel,
    claim: ClaimSpec,
    decision_state: str,
    continuation_word: Word,
) -> dict[Trace, Fraction]:
    """Evaluate the exact definition for one state and one future word."""

    decision_state = str(decision_state)
    current_rows = _checked_law(
        target.current_distribution(decision_state),
        where=f"current_distribution({decision_state!r})",
    )
    out: dict[Trace, Fraction] = {}
    for raw_key, current_mass in current_rows:
        if not isinstance(raw_key, tuple) or len(raw_key) != 2:
            raise TypeError("current_distribution keys must be (ProjectedAction, post_state)")
        action, post_state = raw_key
        if not isinstance(action, ProjectedAction):
            raise TypeError("current_distribution action is not ProjectedAction")
        projected = claim.project(action)
        post_state = str(post_state)

        if not continuation_word:
            trace = (projected,)
            out[trace] = out.get(trace, Fraction(0, 1)) + current_mass
            continue

        continuation = continuation_word[0]
        advance_rows = _checked_law(
            target.advance_distribution(post_state, continuation),
            where=f"advance_distribution({post_state!r},{continuation!r})",
        )
        for raw_next, advance_mass in advance_rows:
            next_state = str(raw_next)
            suffix_law = trace_law(
                target,
                claim,
                next_state,
                continuation_word[1:],
            )
            for suffix, suffix_mass in suffix_law.items():
                trace = (projected,) + suffix
                out[trace] = out.get(trace, Fraction(0, 1)) + (
                    current_mass * advance_mass * suffix_mass
                )

    total = sum(out.values(), Fraction(0, 1))
    if total != 1:
        raise AssertionError(f"definition oracle produced trace-law mass {total}, expected 1")
    return out


def _law_key(law: Mapping[Trace, Fraction]) -> tuple:
    rows = []
    for trace, mass in law.items():
        trace_key = tuple(action.canonical_key() for action in trace)
        rows.append((trace_key, mass.numerator, mass.denominator))
    rows.sort(key=repr)
    return tuple(rows)


def definition_signature(
    target: TargetModel,
    claim: ClaimSpec,
    decision_state: str,
    horizon: int,
) -> tuple[tuple[Word, object], ...]:
    return tuple(
        (
            word,
            _law_key(trace_law(target, claim, decision_state, word)),
        )
        for word in continuation_words(target, horizon)
    )


@dataclass(frozen=True)
class DefinitionPartition:
    depth: int
    blocks: tuple[tuple[str, ...], ...]

    @property
    def block_count(self) -> int:
        return len(self.blocks)

    def equivalent(self, left: str, right: str) -> bool:
        left = str(left)
        right = str(right)
        for block in self.blocks:
            if left in block:
                return right in block
        raise KeyError(f"unknown decision state: {left!r}")


def definition_partition(
    target: TargetModel,
    claim: ClaimSpec,
    horizon: int | None = None,
) -> DefinitionPartition:
    """Group states by the literal q_{C,H} definition, without refinement."""

    horizon = claim.horizon if horizon is None else int(horizon)
    if horizon < 0:
        raise ValueError("horizon must be >= 0")
    states = tuple(sorted(str(s) for s in target.decision_states))
    if not states:
        raise ValueError("TargetModel.decision_states must not be empty")

    buckets: dict[object, list[str]] = {}
    for state in states:
        sig = definition_signature(target, claim, state, horizon)
        buckets.setdefault(sig, []).append(state)
    blocks = [tuple(sorted(group)) for group in buckets.values()]
    blocks.sort()
    return DefinitionPartition(depth=horizon, blocks=tuple(blocks))


def shortest_distinguishing_word(
    target: TargetModel,
    claim: ClaimSpec,
    left: str,
    right: str,
    max_horizon: int,
) -> tuple[str, ...] | None:
    """Return the first definition-level distinguishing word, if any.

    Words are enumerated by increasing length and then by the TargetModel's
    declared continuation order. This is a verification diagnostic, not the
    production compiler's witness algorithm.
    """

    for word in continuation_words(target, max_horizon):
        if trace_law(target, claim, left, word) != trace_law(
            target, claim, right, word
        ):
            return word
    return None
