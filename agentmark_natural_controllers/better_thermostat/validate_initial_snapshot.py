from __future__ import annotations

"""Independent N2 v4 validator.

Raw rendered service calls and explicit pre-action snapshots are recomputed
without trusting producer summary identities or producer promotion gates.  The
EVENT_CALL_SERVICE observer's climate_preset_before_issue field is retained as
diagnostic evidence only because v3 demonstrated that callback scheduling does
not define a strict pre-handler observation point.
"""

import argparse
import json
from pathlib import Path
from typing import Any

from agentmark_natural_controllers.better_thermostat import validate_persisted_ownership as v3

EXPECTED_SCHEMA = "agentmark.natural_controller.better_thermostat_action_identity.v4"
VALIDATION_SCHEMA = "agentmark.natural_controller.better_thermostat.validation.v4"
EXPECTED_MODE = "upstream-qualified-persisted-disabled-config-entry-controlled-device"
EXPECTED_REGISTRATION_PATH = "core.config_entries Store -> ConfigEntries.async_initialize"


def check(condition: bool, label: str, checks: dict[str, bool]) -> None:
    checks[label] = bool(condition)
    if not condition:
        raise AssertionError(label)


def expected_snapshot(presence: str) -> dict[str, Any]:
    return {
        "captured_before_feedback_transition_or_replay_call": True,
        "climate_entity": "climate.agentmark_thermostat",
        "climate_state": "heat",
        "climate_preset": "sleep",
        "presence_state": presence,
        "motion_state": "off",
        "night_state": "off",
        "enable_state": "on",
        "ownership_config_entry_state": "not_loaded",
        "ownership_config_entry_disabled_by": "user",
        "ownership_entry_registered": True,
        "entity_id": "climate.agentmark_thermostat",
        "entity_platform": "better_thermostat",
    }


def validate_snapshot(
    row: dict[str, Any],
    *,
    expected_presence: str,
    expected_phase: str,
    prefix: str,
    checks: dict[str, bool],
) -> None:
    check(row.get("initial_snapshot") == expected_snapshot(expected_presence), f"{prefix}_initial_snapshot_exact", checks)
    check(row.get("initial_snapshot_phase") == expected_phase, f"{prefix}_snapshot_phase", checks)


def validate_ownership(
    ident: dict[str, Any],
    upstream: dict[str, Any],
    prefix: str,
    checks: dict[str, bool],
) -> None:
    reg = ident["registry"]
    check(reg.get("ownership_mode") == EXPECTED_MODE, f"{prefix}_ownership_mode", checks)
    check(reg.get("config_entry_registration_path") == EXPECTED_REGISTRATION_PATH, f"{prefix}_registration_path", checks)
    check(reg.get("upstream_component_repository") == "KartoffelToby/better_thermostat", f"{prefix}_upstream_repo", checks)
    check(reg.get("upstream_component_commit") == v3.EXPECTED_BT_COMMIT, f"{prefix}_upstream_commit", checks)
    check(reg.get("upstream_component_version") == v3.EXPECTED_BT_VERSION, f"{prefix}_upstream_version", checks)
    check(reg.get("upstream_manifest_sha256") == upstream["manifest_sha256"], f"{prefix}_manifest_sha", checks)
    check(reg.get("upstream_component_tree_sha256") == upstream["tree_sha256"], f"{prefix}_tree_sha", checks)
    check(reg.get("ha_loader_resolved_domain") == v3.EXPECTED_BT_DOMAIN, f"{prefix}_loader_domain", checks)
    check(reg.get("ha_loader_resolved_version") == v3.EXPECTED_BT_VERSION, f"{prefix}_loader_version", checks)
    check(reg.get("loader_qualification_before_outcome") is True, f"{prefix}_loader_before_outcome", checks)
    check(reg.get("loader_integration_setup_invoked") is False, f"{prefix}_loader_no_setup", checks)
    check(reg.get("config_entry_domain") == v3.EXPECTED_BT_DOMAIN, f"{prefix}_entry_domain", checks)
    check(reg.get("config_entry_disabled_by") == "user", f"{prefix}_entry_disabled", checks)
    check(reg.get("config_entry_state") == "not_loaded", f"{prefix}_entry_not_loaded", checks)
    check(reg.get("config_entry_registered") is True, f"{prefix}_entry_registered", checks)
    check(reg.get("device_config_entry_id") == reg.get("config_entry_id"), f"{prefix}_device_entry", checks)
    check(reg.get("device_identifiers") == [[v3.EXPECTED_BT_DOMAIN, "agentmark-device"]], f"{prefix}_device_identifier", checks)
    check(reg.get("entity_id") == "climate.agentmark_thermostat", f"{prefix}_entity_id", checks)
    check(reg.get("entity_platform") == v3.EXPECTED_BT_DOMAIN, f"{prefix}_entity_platform", checks)
    check(reg.get("entity_config_entry_id") == reg.get("config_entry_id"), f"{prefix}_entity_entry", checks)
    check(reg.get("entity_device_id") == reg.get("device_id"), f"{prefix}_entity_device", checks)
    check(reg.get("native_device_entity_link") is True, f"{prefix}_native_device_entity", checks)
    check(reg.get("native_entry_device_link") is True, f"{prefix}_native_entry_device", checks)
    check(reg.get("native_entry_entity_link") is True, f"{prefix}_native_entry_entity", checks)
    check(ident["target_entities"] == ["climate.agentmark_thermostat"], f"{prefix}_raw_target_exact", checks)
    check(ident["context_nonempty"], f"{prefix}_context", checks)


def validate(path: Path, component: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    upstream = v3.verify_upstream(component)
    checks: dict[str, bool] = {}

    check(payload["schema"] == EXPECTED_SCHEMA, "schema_v4", checks)
    check(payload["environment"]["home_assistant_core_version"] == "2026.9.0", "ha_version", checks)
    check(payload["external_controller"]["sha256"] == v3.EXPECTED_CONTROLLER_SHA, "controller_sha", checks)
    check(payload["external_controller"]["source_edited"] is False, "controller_unedited", checks)
    check(payload["frozen_protocol"] == v3.EXPECTED_PROTOCOL, "protocol_exact", checks)

    owner = payload["controlled_device_ownership"]
    check(owner["mode"] == EXPECTED_MODE, "owner_mode", checks)
    check(owner["config_entry_registration_path"] == EXPECTED_REGISTRATION_PATH, "owner_registration_path", checks)
    check(owner["upstream_repository"] == "KartoffelToby/better_thermostat", "owner_repo", checks)
    check(owner["upstream_commit"] == v3.EXPECTED_BT_COMMIT, "owner_commit", checks)
    check(owner["upstream_version"] == v3.EXPECTED_BT_VERSION, "owner_version", checks)
    check(owner["upstream_manifest_sha256"] == upstream["manifest_sha256"], "owner_manifest", checks)
    check(owner["component_tree_sha256"] == upstream["tree_sha256"], "owner_tree", checks)
    check(owner["loader_qualification"]["domain"] == v3.EXPECTED_BT_DOMAIN, "owner_loader_domain", checks)
    check(owner["loader_qualification"]["version"] == v3.EXPECTED_BT_VERSION, "owner_loader_version", checks)
    check(owner["loader_qualification"]["before_outcome"] is True, "owner_loader_before_outcome", checks)
    check(owner["loader_qualification"]["integration_setup_invoked"] is False, "owner_loader_no_setup", checks)
    check(owner["config_entry_intentionally_disabled"] is True, "owner_disabled", checks)
    check(owner["integration_internal_control_logic_executed"] is False, "owner_no_bt_internal_logic", checks)

    measurement = payload["measurement_contract"]
    check(measurement["pre_action_state_source"] == "explicit_initial_snapshot_before_feedback_transition_or_replay_call", "measurement_snapshot_source", checks)
    check(measurement["event_listener_state_read"] == "diagnostic_only_not_strict_pre_handler", "measurement_observer_diagnostic_only", checks)

    source_row = payload["source"]
    source = v3.identity_from_raw(source_row)
    check(source["counts"] == {"climate.set_preset_mode": 1}, "source_counts", checks)
    check(source["operation"] == "climate.set_preset_mode", "source_operation", checks)
    check(source["target_class"] == "climate", "source_target_class", checks)
    check(source["variant"] == v3.HOME_VARIANT, "source_home_variant", checks)
    check(source["presence_at_issue"] == "on", "source_feedback_at_issue_home", checks)
    validate_snapshot(source_row, expected_presence="off", expected_phase="after_native_automation_setup_before_feedback_transition", prefix="source", checks=checks)
    validate_ownership(source, upstream, "source", checks)

    target_rows = payload["target_native"]
    replay_rows = payload["target_replay"]
    controls = payload["no_feedback_shift_control"]
    check(len(target_rows) == len(replay_rows) == len(controls) == 6, "trial_counts_exact", checks)

    targets = [v3.identity_from_raw(row) for row in target_rows]
    replays = [v3.identity_from_raw(row) for row in replay_rows]
    control_native = [v3.identity_from_raw(pair["native"]) for pair in controls]
    control_replay = [v3.identity_from_raw(pair["replay"]) for pair in controls]

    for i, (row, ident) in enumerate(zip(target_rows, targets, strict=True)):
        check(ident["counts"] == {"climate.set_preset_mode": 1}, f"target_{i}_counts", checks)
        check(ident["operation"] == source["operation"], f"target_{i}_same_operation", checks)
        check(ident["target_class"] == "climate", f"target_{i}_target_class", checks)
        check(ident["variant"] == v3.AWAY_VARIANT, f"target_{i}_away_variant", checks)
        check(ident["presence_at_issue"] == "off", f"target_{i}_feedback_at_issue_away", checks)
        validate_snapshot(row, expected_presence="on", expected_phase="after_native_automation_setup_before_feedback_transition", prefix=f"target_{i}", checks=checks)
        validate_ownership(ident, upstream, f"target_{i}", checks)

    for i, (row, ident) in enumerate(zip(replay_rows, replays, strict=True)):
        check(ident["counts"] == {"climate.set_preset_mode": 1}, f"replay_{i}_counts", checks)
        check(ident["operation"] == source["operation"], f"replay_{i}_same_operation", checks)
        check(ident["target_class"] == "climate", f"replay_{i}_target_class", checks)
        check(ident["variant"] == v3.HOME_VARIANT, f"replay_{i}_recorded_home_variant", checks)
        check(ident["presence_at_issue"] == "off", f"replay_{i}_target_feedback_away", checks)
        validate_snapshot(row, expected_presence="off", expected_phase="before_recorded_replay_service_call", prefix=f"replay_{i}", checks=checks)
        validate_ownership(ident, upstream, f"replay_{i}", checks)
        check(ident["operation"] == targets[i]["operation"], f"replay_{i}_operation_supported", checks)
        check((ident["operation"], ident["target_class"], ident["variant"]) != (targets[i]["operation"], targets[i]["target_class"], targets[i]["variant"]), f"replay_{i}_full_action_unsupported", checks)

    for i, pair in enumerate(controls):
        native_row, replay_row = pair["native"], pair["replay"]
        native, replay = control_native[i], control_replay[i]
        check(native["counts"] == {"climate.set_preset_mode": 1}, f"control_{i}_native_counts", checks)
        check(replay["counts"] == {"climate.set_preset_mode": 1}, f"control_{i}_replay_counts", checks)
        check(native["variant"] == replay["variant"] == v3.HOME_VARIANT, f"control_{i}_home_action_equal", checks)
        check(native["presence_at_issue"] == replay["presence_at_issue"] == "on", f"control_{i}_feedback_home", checks)
        validate_snapshot(native_row, expected_presence="off", expected_phase="after_native_automation_setup_before_feedback_transition", prefix=f"control_{i}_native", checks=checks)
        validate_snapshot(replay_row, expected_presence="on", expected_phase="before_recorded_replay_service_call", prefix=f"control_{i}_replay", checks=checks)
        validate_ownership(native, upstream, f"control_{i}_native", checks)
        validate_ownership(replay, upstream, f"control_{i}_replay", checks)

    source_op = {(source["operation"],): 1.0}
    target_op = {(targets[0]["operation"],): 1.0}
    source_action = {(source["operation"], source["target_class"], source["variant"]): 1.0}
    target_action = {(targets[0]["operation"], targets[0]["target_class"], targets[0]["variant"]): 1.0}
    tv_op = 0.5 * sum(abs(source_op.get(k, 0.0) - target_op.get(k, 0.0)) for k in set(source_op) | set(target_op))
    tv_action = 0.5 * sum(abs(source_action.get(k, 0.0) - target_action.get(k, 0.0)) for k in set(source_action) | set(target_action))
    check(tv_op == 0.0, "tv_operation_exact_zero", checks)
    check(tv_action == 1.0, "tv_action_exact_one", checks)

    check(float(payload["theory"]["TV_operation"]) == 0.0, "producer_tv_operation", checks)
    check(float(payload["theory"]["TV_action"]) == 1.0, "producer_tv_action", checks)
    check(payload["decision"] == "PROMOTED", "producer_promoted", checks)
    check(all(bool(value) for value in payload["promotion_gates"].values()), "producer_gates_all_true", checks)

    diagnostics = {
        "source_event_callback_preset": source["pre_issue_preset"],
        "target_native_event_callback_presets": [ident["pre_issue_preset"] for ident in targets],
        "target_replay_event_callback_presets": [ident["pre_issue_preset"] for ident in replays],
        "used_for_promotion": False,
    }

    return {
        "schema": VALIDATION_SCHEMA,
        "replica": payload["replica"],
        "pass": all(checks.values()),
        "checks": checks,
        "upstream_recomputed": upstream,
        "observer_ordering_diagnostics": diagnostics,
        "recomputed": {
            "source_identity": {key: source[key] for key in ("operation", "target_class", "variant")},
            "target_identity": {key: targets[0][key] for key in ("operation", "target_class", "variant")},
            "TV_operation": tv_op,
            "TV_action": tv_action,
            "target_trials": len(targets),
            "replay_trials": len(replays),
            "control_trials": len(controls),
            "ownership_mode": EXPECTED_MODE,
            "ownership_component_tree_sha256": upstream["tree_sha256"],
            "pre_action_snapshots_all_exact": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("result")
    parser.add_argument("--ownership-component", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    report = validate(Path(args.result), Path(args.ownership_component))
    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"replica": report["replica"], "pass": report["pass"], "observer_ordering_diagnostics": report["observer_ordering_diagnostics"], "recomputed": report["recomputed"]}, indent=2, sort_keys=True))
    if not report["pass"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
