#!/usr/bin/env python3
"""Independent validator for BT_MQTT_E2E selector output.

Deliberately does not import bt_mqtt_e2e_select_cycle.py.
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

PRESETS = ("away", "home", "comfort", "sleep")
PORDER = {p: i for i, p in enumerate(PRESETS)}
EVENTS = ("presence_toggle", "motion_toggle", "night_toggle")
EORDER = {e: i for i, e in enumerate(EVENTS)}
MAX_LEN = 8


def target(s):
    p, m, n, _ = s
    return "sleep" if n else ("away" if not p else ("comfort" if m else "home"))


def key(s):
    return (int(s[0]), int(s[1]), int(s[2]), PORDER[s[3]])


def transition(s, event):
    p, m, n, cur = s
    toggles = {
        "presence_toggle": (not p, m, n),
        "motion_toggle": (p, not m, n),
        "night_toggle": (p, m, not n),
    }
    p, m, n = toggles[event]
    wanted = "sleep" if n else ("away" if not p else ("comfort" if m else "home"))
    if cur == wanted:
        return (p, m, n, cur), "NO_ACTION"
    return (p, m, n, wanted), "SET_" + wanted.upper()


def execute(s, seq):
    actions = []
    for event in seq:
        s, a = transition(s, event)
        actions.append(a)
    return s, actions


def count(actions):
    return sum(x != "NO_ACTION" for x in actions)


def initial_states():
    states = []
    for p, m, n in itertools.product((False, True), repeat=3):
        wanted = "sleep" if n else ("away" if not p else ("comfort" if m else "home"))
        states.append((p, m, n, wanted))
    return sorted(states, key=key)


def pairs():
    out = []
    for a, b in itertools.combinations(initial_states(), 2):
        a, b = sorted((a, b), key=key)
        if a[3] != b[3]:
            continue
        if sum(x != y for x, y in zip(a[:3], b[:3])) != 1:
            continue
        out.append((a, b))
    return sorted(set(out), key=lambda ab: (key(ab[0]), key(ab[1])))


def enumerate_candidates(cycle):
    all_rows = []
    by_len = {}
    for length in range(1, MAX_LEN + 1):
        rows = []
        for source, tgt in pairs():
            for seq in itertools.product(EVENTS, repeat=length):
                sf, sa = execute(source, seq)
                tf, ta = execute(tgt, seq)
                if count(sa) == count(ta):
                    continue
                if cycle and not (sf == source and tf == tgt):
                    continue
                rows.append((source, tgt, seq, sf, tf, sa, ta))
        by_len[str(length)] = len(rows)
        all_rows.extend(rows)
    all_rows.sort(
        key=lambda r: (
            len(r[2]),
            -abs(count(r[5]) - count(r[6])),
            key(r[0]),
            key(r[1]),
            tuple(EORDER[e] for e in r[2]),
        )
    )
    return all_rows[0], by_len


def state_dict(s):
    return {"presence": s[0], "motion": s[1], "night": s[2], "current_preset": s[3]}


def expected_record(row, by_len):
    source, tgt, seq, sf, tf, sa, ta = row
    length = len(seq)
    return {
        "length": length,
        "absolute_action_count_difference": abs(count(sa) - count(ta)),
        "source_state": state_dict(source),
        "target_state": state_dict(tgt),
        "events": list(seq),
        "source_actions": sa,
        "target_actions": ta,
        "source_action_count": count(sa),
        "target_action_count": count(ta),
        "source_final_state": state_dict(sf),
        "target_final_state": state_dict(tf),
        "eligible_candidate_counts_by_length": by_len,
        "no_shorter_candidate_proof": all(by_len[str(i)] == 0 for i in range(1, length)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("result", type=Path)
    args = ap.parse_args()
    got = json.loads(args.result.read_text(encoding="utf-8"))
    errors = []

    if got.get("schema") != "replaymark.bt_mqtt_e2e.selector.v1":
        errors.append("schema")
    if got.get("state_count") != 32:
        errors.append("state_count")
    if got.get("quiescent_state_count") != 8:
        errors.append("quiescent_state_count")
    if got.get("eligible_pair_count") != len(pairs()):
        errors.append("eligible_pair_count")

    prow, pcounts = enumerate_candidates(True)
    srow, scounts = enumerate_candidates(False)
    pexpected = expected_record(prow, pcounts)
    sexpected = expected_record(srow, scounts)
    if got.get("primary_reset_free_cycle") != pexpected:
        errors.append("primary_reset_free_cycle")
    if got.get("secondary_shortest_prefix") != sexpected:
        errors.append("secondary_shortest_prefix")

    # Explicit independent invariants for the selected primary cycle.
    primary = pexpected
    if primary["length"] != 4:
        errors.append("primary_length_not_4")
    if primary["source_action_count"] != 2 or primary["target_action_count"] != 4:
        errors.append("primary_count_not_2_vs_4")
    if primary["source_final_state"] != primary["source_state"]:
        errors.append("source_not_reset_free")
    if primary["target_final_state"] != primary["target_state"]:
        errors.append("target_not_reset_free")
    if any(pcounts[str(i)] != 0 for i in (1, 2, 3)):
        errors.append("shorter_cycle_exists")

    if errors:
        raise SystemExit("BT_MQTT_E2E_SELECTION_VALIDATION: FAIL " + ",".join(errors))
    print("BT_MQTT_E2E_SELECTION_VALIDATION: PASS")
    print("eligible_pairs=", len(pairs()))
    print("primary_events=", primary["events"])
    print("source_actions=", primary["source_actions"])
    print("target_actions=", primary["target_actions"])
    print("counts=2_vs_4 reset_free=true no_shorter_cycle=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
