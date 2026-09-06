#!/usr/bin/env python3
"""Deterministic source-model selector for the frozen BT→MQTT capstone.

This script executes Section 3 of BT_MQTT_E2E_CAPSTONE_PROTOCOL.md.  It has no
Home Assistant/MQTT dependency and observes no runtime outcome.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path

PRESETS = ("away", "home", "comfort", "sleep")
PRESET_ORDER = {name: i for i, name in enumerate(PRESETS)}
EVENTS = ("presence_toggle", "motion_toggle", "night_toggle")
EVENT_ORDER = {name: i for i, name in enumerate(EVENTS)}
MAX_LEN = 8
SCHEMA = "replaymark.bt_mqtt_e2e.selector.v1"


def desired(presence: bool, motion: bool, night: bool) -> str:
    if night:
        return "sleep"
    if not presence:
        return "away"
    if motion:
        return "comfort"
    return "home"


def state_key(state: tuple[bool, bool, bool, str]) -> tuple[int, int, int, int]:
    p, m, n, preset = state
    return (int(p), int(m), int(n), PRESET_ORDER[preset])


def state_obj(state: tuple[bool, bool, bool, str]) -> dict[str, object]:
    p, m, n, preset = state
    return {
        "presence": p,
        "motion": m,
        "night": n,
        "current_preset": preset,
    }


def event_seq_key(seq: tuple[str, ...]) -> tuple[int, ...]:
    return tuple(EVENT_ORDER[e] for e in seq)


def step(
    state: tuple[bool, bool, bool, str], event: str
) -> tuple[tuple[bool, bool, bool, str], str]:
    p, m, n, cur = state
    if event == "presence_toggle":
        p = not p
    elif event == "motion_toggle":
        m = not m
    elif event == "night_toggle":
        n = not n
    else:
        raise ValueError(event)
    target = desired(p, m, n)
    action = "NO_ACTION" if cur == target else f"SET_{target.upper()}"
    if action != "NO_ACTION":
        cur = target
    return (p, m, n, cur), action


def run(
    state: tuple[bool, bool, bool, str], seq: tuple[str, ...]
) -> tuple[list[str], tuple[bool, bool, bool, str]]:
    actions: list[str] = []
    for event in seq:
        state, action = step(state, event)
        actions.append(action)
    return actions, state


def action_count(actions: list[str]) -> int:
    return sum(action != "NO_ACTION" for action in actions)


def quiescent_states() -> list[tuple[bool, bool, bool, str]]:
    out = []
    for p, m, n in itertools.product((False, True), repeat=3):
        target = desired(p, m, n)
        out.append((p, m, n, target))
    return sorted(out, key=state_key)


def eligible_pairs():
    pairs = []
    for left, right in itertools.combinations(quiescent_states(), 2):
        source, target = sorted((left, right), key=state_key)
        if source[3] != target[3]:
            continue
        feedback_hamming = sum(a != b for a, b in zip(source[:3], target[:3]))
        if feedback_hamming != 1:
            continue
        pairs.append((source, target))
    return sorted(set(pairs), key=lambda pair: (state_key(pair[0]), state_key(pair[1])))


def candidate_record(source, target, seq, source_actions, target_actions, source_final, target_final):
    sr = action_count(source_actions)
    tn = action_count(target_actions)
    return {
        "length": len(seq),
        "absolute_action_count_difference": abs(sr - tn),
        "source_state": state_obj(source),
        "target_state": state_obj(target),
        "events": list(seq),
        "source_actions": source_actions,
        "target_actions": target_actions,
        "source_action_count": sr,
        "target_action_count": tn,
        "source_final_state": state_obj(source_final),
        "target_final_state": state_obj(target_final),
    }


def select(*, require_cycle: bool):
    candidates = []
    counts_by_length = {}
    pairs = eligible_pairs()
    for length in range(1, MAX_LEN + 1):
        length_candidates = []
        for source, target in pairs:
            for seq in itertools.product(EVENTS, repeat=length):
                source_actions, source_final = run(source, seq)
                target_actions, target_final = run(target, seq)
                sr = action_count(source_actions)
                tn = action_count(target_actions)
                if sr == tn:
                    continue
                if require_cycle and not (
                    source_final == source and target_final == target
                ):
                    continue
                length_candidates.append(
                    (
                        source,
                        target,
                        seq,
                        source_actions,
                        target_actions,
                        source_final,
                        target_final,
                    )
                )
        counts_by_length[str(length)] = len(length_candidates)
        candidates.extend(length_candidates)

    if not candidates:
        raise RuntimeError("no eligible candidate")

    candidates.sort(
        key=lambda c: (
            len(c[2]),
            -abs(action_count(c[3]) - action_count(c[4])),
            state_key(c[0]),
            state_key(c[1]),
            event_seq_key(c[2]),
        )
    )
    chosen = candidates[0]
    record = candidate_record(*chosen)
    record["eligible_candidate_counts_by_length"] = counts_by_length
    record["no_shorter_candidate_proof"] = all(
        counts_by_length[str(i)] == 0 for i in range(1, record["length"])
    )
    return record


def canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, indent=2) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    primary = select(require_cycle=True)
    secondary = select(require_cycle=False)
    result = {
        "schema": SCHEMA,
        "controller_authority": {
            "repository": "n3roGit/MyHomeAssistantMods",
            "commit": "57d56f076c05ccaa9553e6bd4b673b6d43a8cf7f",
            "path": "automation/BetterThermostatControl/BetterThermostat_RoomHeatControl_Lean.yaml",
            "sha256": "16d52ce11dec44fa9ca533d15f3cec1eb9646d59bf6a455bd905af63cdf86443",
        },
        "state_count": 32,
        "quiescent_state_count": len(quiescent_states()),
        "eligible_pair_count": len(eligible_pairs()),
        "event_order": list(EVENTS),
        "primary_reset_free_cycle": primary,
        "secondary_shortest_prefix": secondary,
    }
    payload = canonical_json(result)
    result_path = args.output_dir / "BT_MQTT_E2E_SELECTOR_RESULTS.json"
    result_path.write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(payload.encode()).hexdigest()

    p = primary
    s = secondary
    report = f"""# Better Thermostat → MQTT capstone selector result\n\n"
    report += f"- Schema: `{SCHEMA}`\n"
    report += f"- 32-state scope; quiescent states: **{len(quiescent_states())}**; eligible pairs: **{len(eligible_pairs())}**\n"
    report += f"- Primary shortest reset-free count-separating cycle length: **{p['length']}**\n"
    report += f"- Primary source actions: `{p['source_actions']}` → count **{p['source_action_count']}**\n"
    report += f"- Primary target-native actions: `{p['target_actions']}` → count **{p['target_action_count']}**\n"
    report += f"- Primary events: `{p['events']}`\n"
    report += f"- Primary no-shorter-cycle proof: **{p['no_shorter_candidate_proof']}**\n"
    report += f"- Primary eligible-cycle counts by length: `{p['eligible_candidate_counts_by_length']}`\n\n"
    report += f"## Selected source state\n\n`{p['source_state']}`\n\n"
    report += f"## Selected target state\n\n`{p['target_state']}`\n\n"
    report += f"## Secondary shortest count-separating prefix\n\n"
    report += f"- length **{s['length']}**, events `{s['events']}`\n"
    report += f"- source `{s['source_actions']}` ({s['source_action_count']})\n"
    report += f"- target `{s['target_actions']}` ({s['target_action_count']})\n\n"
    report += f"Result JSON SHA-256: `{digest}`\n"
    (args.output_dir / "BT_MQTT_E2E_SELECTOR_REPORT.md").write_text(report, encoding="utf-8")

    print("BT_MQTT_E2E_SELECTOR: PASS")
    print(
        f"primary length={p['length']} source={p['source_action_count']} "
        f"target={p['target_action_count']} events={','.join(p['events'])}"
    )
    print(f"result_sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
