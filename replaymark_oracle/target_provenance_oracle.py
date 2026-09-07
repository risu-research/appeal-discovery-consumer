from __future__ import annotations

"""Literal definition oracle for compiler-observed target semantic provenance.

This module does not import replaymark.target_provenance. It independently reads
the finite TargetModel, removes zero-mass branches, canonicalizes exact positive
laws, and computes the same named component/root digests.
"""

from fractions import Fraction
import hashlib
import json
from typing import Mapping

from replaymark.contracts import ProjectedAction, TargetModel


_DOMAIN_SCHEMA = "replaymark.target-semantics-domain.v1"
_CURRENT_SCHEMA = "replaymark.target-current-law.v1"
_ADVANCE_SCHEMA = "replaymark.target-advance-law.v1"
_ROOT_SCHEMA = "replaymark.target-semantic-root.v1"


def _bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _hash(value: object) -> str:
    return hashlib.sha256(_bytes(value)).hexdigest()


def _fraction(raw: object) -> Fraction:
    if isinstance(raw, bool) or not isinstance(raw, (int, Fraction)):
        raise TypeError("oracle requires exact Fraction/int probability mass")
    value = Fraction(raw)
    if value < 0:
        raise ValueError("negative probability")
    return value


def _current_law(target: TargetModel, state: str) -> tuple[tuple[ProjectedAction, str, Fraction], ...]:
    distribution = target.current_distribution(state)
    if not isinstance(distribution, Mapping):
        raise TypeError("current_distribution must return Mapping")
    total = Fraction(0, 1)
    rows = []
    for key, raw_mass in distribution.items():
        mass = _fraction(raw_mass)
        total += mass
        if mass == 0:
            continue
        if not isinstance(key, tuple) or len(key) != 2:
            raise TypeError("positive current key must be (ProjectedAction, post_state)")
        action, post_state = key
        if not isinstance(action, ProjectedAction) or not isinstance(post_state, str):
            raise TypeError("invalid positive current branch")
        rows.append((action, post_state, mass))
    if total != 1 or not rows:
        raise ValueError("invalid current probability law")
    rows.sort(key=lambda x: (x[0].canonical_key(), x[1], x[2].numerator, x[2].denominator))
    return tuple(rows)


def _advance_law(
    target: TargetModel,
    post_state: str,
    continuation: str,
    admitted: set[str],
) -> tuple[tuple[str, Fraction], ...]:
    distribution = target.advance_distribution(post_state, continuation)
    if not isinstance(distribution, Mapping):
        raise TypeError("advance_distribution must return Mapping")
    total = Fraction(0, 1)
    rows = []
    for next_state, raw_mass in distribution.items():
        mass = _fraction(raw_mass)
        total += mass
        if mass == 0:
            continue
        if not isinstance(next_state, str) or next_state not in admitted:
            raise ValueError("positive advance branch reaches invalid state")
        rows.append((next_state, mass))
    if total != 1 or not rows:
        raise ValueError("invalid advance probability law")
    rows.sort(key=lambda x: (x[0], x[1].numerator, x[1].denominator))
    return tuple(rows)


def definition_target_semantic_digests(target: TargetModel) -> dict[str, str]:
    """Compute the positive-law semantic root directly from TargetModel calls."""

    if not isinstance(target, TargetModel):
        raise TypeError("target does not satisfy TargetModel protocol")
    states = tuple(sorted(target.decision_states))
    continuations = tuple(target.continuation_alphabet)
    if not states or len(set(states)) != len(states):
        raise ValueError("invalid target state domain")
    if len(set(continuations)) != len(continuations):
        raise ValueError("duplicate continuation symbol")
    if any(not isinstance(x, str) or not x for x in states + continuations):
        raise TypeError("state/continuation identifiers must be nonempty strings")

    current = tuple((state, _current_law(target, state)) for state in states)
    post_states = tuple(sorted({post for _, law in current for _, post, _ in law}))
    admitted = set(states)
    advance = tuple(
        (post, continuation, _advance_law(target, post, continuation, admitted))
        for post in post_states
        for continuation in sorted(continuations)
    )

    domain_record = {
        "schema": _DOMAIN_SCHEMA,
        "decision_states": list(states),
        "continuation_symbols": list(sorted(continuations)),
    }
    current_record = {
        "schema": _CURRENT_SCHEMA,
        "current_laws": [
            {
                "decision_state": state,
                "branches": [
                    {
                        "action": action.as_dict(),
                        "post_state": post,
                        "mass": {"numerator": mass.numerator, "denominator": mass.denominator},
                    }
                    for action, post, mass in law
                ],
            }
            for state, law in current
        ],
    }
    advance_record = {
        "schema": _ADVANCE_SCHEMA,
        "advance_laws": [
            {
                "post_state": post,
                "continuation": continuation,
                "branches": [
                    {
                        "next_decision_state": nxt,
                        "mass": {"numerator": mass.numerator, "denominator": mass.denominator},
                    }
                    for nxt, mass in law
                ],
            }
            for post, continuation, law in advance
        ],
    }
    domain_digest = _hash(domain_record)
    current_digest = _hash(current_record)
    advance_digest = _hash(advance_record)
    root = _hash(
        {
            "schema": _ROOT_SCHEMA,
            "domain_digest": domain_digest,
            "current_semantics_digest": current_digest,
            "advance_semantics_digest": advance_digest,
        }
    )
    return {
        "domain": domain_digest,
        "current": current_digest,
        "advance": advance_digest,
        "root": root,
    }


__all__ = ("definition_target_semantic_digests",)
