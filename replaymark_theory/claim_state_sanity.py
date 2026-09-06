#!/usr/bin/env python3
"""Finite semantic sanity check for ReplayMark claim-predictive state.

Research-only, not manuscript evidence.

This checker models the exact N2/N2b decision slice of pinned external blueprint
n3roGit/MyHomeAssistantMods@57d56f076c05ccaa9553e6bd4b673b6d43a8cf7f
with boost=night=eco=activity=False. The remaining state is
(presence, motion), and target_preset follows the pinned priority logic:
absence -> away; else motion -> comfort; else home.

Input events are presence/motion state changes, both of which are actual triggers
in the pinned blueprint. We compute finite-horizon behavioral partitions and a
shortest distinguishing suffix.
"""

from collections import deque
from itertools import product

STATES = tuple(product((False, True), repeat=2))
INPUTS = (
    ("presence", False),
    ("presence", True),
    ("motion", False),
    ("motion", True),
)


def output(state):
    presence, motion = state
    if not presence:
        return "away"
    if motion:
        return "comfort"
    return "home"


def step(state, inp):
    presence, motion = state
    name, value = inp
    if name == "presence":
        presence = value
    elif name == "motion":
        motion = value
    else:
        raise ValueError(inp)
    next_state = (presence, motion)
    return next_state, output(next_state)


def signature(state, horizon):
    """Current output plus all continuation behavior through horizon steps."""
    if horizon == 0:
        return (output(state),)
    return (
        output(state),
        tuple((inp, signature(step(state, inp)[0], horizon - 1)) for inp in INPUTS),
    )


def partition(horizon):
    groups = {}
    for state in STATES:
        groups.setdefault(signature(state, horizon), []).append(state)
    return tuple(tuple(v) for v in groups.values())


def output_word(state, word):
    result = []
    current = state
    for inp in word:
        current, out = step(current, inp)
        result.append(out)
    return tuple(result)


def shortest_distinguishing_suffix(a, b, max_depth=8):
    if output(a) != output(b):
        return tuple(), (output(a),), (output(b),)
    queue = deque([(a, b, tuple())])
    seen = {(a, b)}
    while queue:
        sa, sb, word = queue.popleft()
        if len(word) >= max_depth:
            continue
        for inp in INPUTS:
            na, oa = step(sa, inp)
            nb, ob = step(sb, inp)
            nword = word + (inp,)
            if oa != ob:
                return nword, output_word(a, nword), output_word(b, nword)
            pair = (na, nb)
            if pair not in seen:
                seen.add(pair)
                queue.append((na, nb, nword))
    return None


def main():
    a = (False, False)  # N2b source-side feedback slice
    b = (False, True)   # N2b target-side feedback slice

    assert output(a) == output(b) == "away"
    p0 = partition(0)
    p1 = partition(1)
    p2 = partition(2)
    assert len(p0) == 3, p0
    assert any(set(group) == {a, b} for group in p0), p0
    assert len(p1) == 4, p1
    assert len(p2) == 4, p2

    witness = shortest_distinguishing_suffix(a, b)
    assert witness is not None
    word, out_a, out_b = witness
    assert word == (("presence", True),), witness
    assert out_a == ("home",), witness
    assert out_b == ("comfort",), witness

    print("CLAIM-STATE SANITY: PASS")
    print("H=0 partition:", p0)
    print("H=1 partition:", p1)
    print("H=2 partition:", p2)
    print("N2b current outputs:", output(a), output(b))
    print("Shortest distinguishing suffix:", word)
    print("Outputs after suffix:", out_a, out_b)


if __name__ == "__main__":
    main()
