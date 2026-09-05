from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any, Mapping


EXPECTED_SHA = "16d52ce11dec44fa9ca533d15f3cec1eb9646d59bf6a455bd905af63cdf86443"
HOME_VARIANT = '{"preset_mode":"home"}'
AWAY_VARIANT = '{"preset_mode":"away"}'
TARGET_KEYS = frozenset({"entity_id", "device_id", "area_id", "floor_id", "label_id"})
EXPECTED_PROTOCOL = {
    "current_preset": "sleep",
    "source_feedback": "HOME",
    "target_feedback": "AWAY",
    "trials": 6,
    "writeback_enable": False,
    "writeback_bounds_enable": False,
    "boost_entity": "",
    "eco_entity": "",
    "activity_entity": "",
}


def canonical_variant_independent(service_data: Mapping[str, Any]) -> str:
    """Independent copy of the frozen adapter rule, not producer output."""
    semantic = {k: v for k, v in service_data.items() if k not in TARGET_KEYS}
    return json.dumps(
        semantic,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def target_class_independent(service_data: Mapping[str, Any]) -> str | None:
    raw = service_data.get("entity_id")
    if raw is None:
        return None
    values = [raw] if isinstance(raw, str) else list(raw)
    domains = sorted({str(v).split(".", 1)[0] for v in values if "." in str(v)})
    if len(domains) == 1:
        return domains[0]
    if not domains:
        return None
    return "mixed:" + ",".join(domains)


def assert_check(condition: bool, label: str, checks: dict[str, bool]) -> None:
    checks[label] = bool(condition)
    if not condition:
        raise AssertionError(label)


def raw_identity(row: dict[str, Any]) -> dict[str, Any]:
    events = row["raw_call_events"]
    counts = Counter(f"{e['domain']}.{e['service']}" for e in events)
    climate = [
        e for e in events
        if e.get("domain") == "climate" and e.get("service") == "set_preset_mode"
    ]
    if len(climate) != 1:
        raise AssertionError(f"{row['label']}: expected one raw climate call, got {dict(counts)}")
    event = climate[0]
    data = dict(event.get("service_data") or {})
    return {
        "counts": dict(sorted(counts.items())),
        "operation": "climate.set_preset_mode",
        "target_class": target_class_independent(data),
        "variant": canonical_variant_independent(data),
        "service_data": data,
        "contexts_nonempty": all(bool(str(e.get("context_id", ""))) for e in events),
        "presence_at_issue": event.get("presence_state_at_issue"),
        "pre_issue_preset": event.get("climate_preset_before_issue"),
        "registry_link": bool(row["registry"].get("native_device_entity_link")),
        "registry_entity": row["registry"].get("entity_id"),
    }


def is_only_climate(identity: dict[str, Any]) -> bool:
    return identity["counts"] == {"climate.set_preset_mode": 1}


def validate(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    checks: dict[str, bool] = {}

    assert_check(
        payload["schema"] == "agentmark.natural_controller.better_thermostat_action_identity.v1",
        "schema",
        checks,
    )
    assert_check(payload["environment"]["home_assistant_core_version"] == "2026.9.0", "ha_version", checks)
    assert_check(payload["external_controller"]["sha256"] == EXPECTED_SHA, "external_sha", checks)
    assert_check(payload["external_controller"]["source_edited"] is False, "source_unedited", checks)
    assert_check(payload["frozen_protocol"] == EXPECTED_PROTOCOL, "protocol_exact", checks)

    adapter = payload["frozen_adapter"]
    assert_check(adapter["home_variant"] == HOME_VARIANT, "adapter_home", checks)
    assert_check(adapter["away_variant"] == AWAY_VARIANT, "adapter_away", checks)

    source = raw_identity(payload["source"])
    assert_check(is_only_climate(source), "source_counts", checks)
    assert_check(source["operation"] == "climate.set_preset_mode", "source_operation", checks)
    assert_check(source["target_class"] == "climate", "source_target_class", checks)
    assert_check(source["variant"] == HOME_VARIANT, "source_home_variant", checks)
    assert_check(source["pre_issue_preset"] == "sleep", "source_pre_preset", checks)
    assert_check(source["registry_link"], "source_registry_link", checks)
    assert_check(source["registry_entity"] == "climate.agentmark_thermostat", "source_registry_entity", checks)
    assert_check(source["contexts_nonempty"], "source_context", checks)

    targets = payload["target_native"]
    replays = payload["target_replay"]
    controls = payload["no_feedback_shift_control"]
    assert_check(len(targets) == 6, "target_trial_count", checks)
    assert_check(len(replays) == 6, "replay_trial_count", checks)
    assert_check(len(controls) == 6, "control_trial_count", checks)

    target_ids = [raw_identity(row) for row in targets]
    replay_ids = [raw_identity(row) for row in replays]
    control_native_ids = [raw_identity(pair["native"]) for pair in controls]
    control_replay_ids = [raw_identity(pair["replay"]) for pair in controls]

    for i, ident in enumerate(target_ids):
        assert_check(is_only_climate(ident), f"target_t{i}_counts", checks)
        assert_check(ident["operation"] == source["operation"], f"target_t{i}_same_operation", checks)
        assert_check(ident["target_class"] == "climate", f"target_t{i}_target_class", checks)
        assert_check(ident["variant"] == AWAY_VARIANT, f"target_t{i}_away_variant", checks)
        assert_check(ident["pre_issue_preset"] == "sleep", f"target_t{i}_pre_preset", checks)
        assert_check(ident["registry_link"], f"target_t{i}_registry", checks)
        assert_check(ident["contexts_nonempty"], f"target_t{i}_context", checks)

    for i, ident in enumerate(replay_ids):
        assert_check(is_only_climate(ident), f"replay_t{i}_counts", checks)
        assert_check(ident["operation"] == source["operation"], f"replay_t{i}_same_operation", checks)
        assert_check(ident["target_class"] == "climate", f"replay_t{i}_target_class", checks)
        assert_check(ident["variant"] == HOME_VARIANT, f"replay_t{i}_recorded_home", checks)
        assert_check(ident["registry_link"], f"replay_t{i}_registry", checks)
        assert_check(ident["contexts_nonempty"], f"replay_t{i}_context", checks)
        # Independent support recomputation from the preregistered deterministic law.
        assert_check(ident["operation"] == target_ids[i]["operation"], f"replay_t{i}_operation_supported", checks)
        assert_check(ident["variant"] != target_ids[i]["variant"], f"replay_t{i}_action_unsupported", checks)

    for i, (native, replay) in enumerate(zip(control_native_ids, control_replay_ids, strict=True)):
        assert_check(is_only_climate(native) and is_only_climate(replay), f"control_t{i}_counts", checks)
        assert_check(native["variant"] == HOME_VARIANT, f"control_t{i}_native_home", checks)
        assert_check(replay["variant"] == HOME_VARIANT, f"control_t{i}_replay_home", checks)
        assert_check(native["operation"] == replay["operation"], f"control_t{i}_operation_support", checks)
        assert_check(native["target_class"] == replay["target_class"] == "climate", f"control_t{i}_target_support", checks)
        assert_check(native["variant"] == replay["variant"], f"control_t{i}_action_support", checks)

    # With two deterministic point masses, total variation is exactly 0 when
    # projected keys are identical and exactly 1 when they are disjoint.
    op_keys_source = {(source["operation"],): 1.0}
    op_keys_target = {(target_ids[0]["operation"],): 1.0}
    action_key_source = {(source["operation"], source["target_class"], source["variant"]): 1.0}
    action_key_target = {(target_ids[0]["operation"], target_ids[0]["target_class"], target_ids[0]["variant"]): 1.0}
    tv_operation = 0.5 * sum(abs(op_keys_source.get(k, 0.0) - op_keys_target.get(k, 0.0)) for k in set(op_keys_source) | set(op_keys_target))
    tv_action = 0.5 * sum(abs(action_key_source.get(k, 0.0) - action_key_target.get(k, 0.0)) for k in set(action_key_source) | set(action_key_target))
    assert_check(tv_operation == 0.0, "tv_operation_exact_zero", checks)
    assert_check(tv_action == 1.0, "tv_action_exact_one", checks)

    # Cross-check producer report but do not derive the verdict from it.
    assert_check(float(payload["theory"]["TV_operation"]) == 0.0, "producer_tv_operation", checks)
    assert_check(float(payload["theory"]["TV_action"]) == 1.0, "producer_tv_action", checks)
    assert_check(payload["decision"] == "PROMOTED", "producer_promoted", checks)
    assert_check(all(bool(v) for v in payload["promotion_gates"].values()), "producer_gates_all_true", checks)

    return {
        "schema": "agentmark.natural_controller.better_thermostat.validation.v1",
        "input": str(path),
        "replica": payload["replica"],
        "pass": all(checks.values()),
        "checks": checks,
        "recomputed": {
            "source_identity": {k: source[k] for k in ("operation", "target_class", "variant")},
            "target_identity": {k: target_ids[0][k] for k in ("operation", "target_class", "variant")},
            "TV_operation": tv_operation,
            "TV_action": tv_action,
            "target_trials": len(target_ids),
            "replay_trials": len(replay_ids),
            "control_trials": len(control_native_ids),
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("result")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    report = validate(Path(args.result))
    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"replica": report["replica"], "pass": report["pass"], "recomputed": report["recomputed"]}, indent=2, sort_keys=True))
    if not report["pass"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
