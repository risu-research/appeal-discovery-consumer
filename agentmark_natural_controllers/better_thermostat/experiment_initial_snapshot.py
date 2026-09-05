from __future__ import annotations

"""N2 v4 producer: persisted HA ownership plus explicit pre-action snapshots.

The v3 producer established the full N2 outcome, but its independent validator
incorrectly treated an EVENT_CALL_SERVICE listener state read as a strict
pre-handler snapshot.  v4 leaves the scientific protocol and v3 runtime
unchanged and adds an explicit synchronous snapshot after make_hass() returns
and before the feedback transition / replay service call.
"""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from agentmark.semantics import workload_shift_tv
from agentmark_natural_controllers.better_thermostat import experiment_persisted_ownership as base


def initial_snapshot(hass: Any, registry: dict[str, Any]) -> dict[str, Any]:
    climate = hass.states.get(base.CLIMATE_ENTITY)
    presence = hass.states.get(base.PRESENCE_ENTITY)
    motion = hass.states.get(base.MOTION_ENTITY)
    night = hass.states.get(base.NIGHT_ENTITY)
    enable = hass.states.get(base.ENABLE_ENTITY)
    return {
        "captured_before_feedback_transition_or_replay_call": True,
        "climate_entity": base.CLIMATE_ENTITY,
        "climate_state": None if climate is None else climate.state,
        "climate_preset": None if climate is None else climate.attributes.get("preset_mode"),
        "presence_state": None if presence is None else presence.state,
        "motion_state": None if motion is None else motion.state,
        "night_state": None if night is None else night.state,
        "enable_state": None if enable is None else enable.state,
        "ownership_config_entry_state": registry["config_entry_state"],
        "ownership_config_entry_disabled_by": registry["config_entry_disabled_by"],
        "ownership_entry_registered": registry["config_entry_registered"],
        "entity_id": registry["entity_id"],
        "entity_platform": registry["entity_platform"],
    }


def snapshot_exact(snapshot: dict[str, Any], *, expected_presence: str) -> bool:
    return snapshot == {
        "captured_before_feedback_transition_or_replay_call": True,
        "climate_entity": base.CLIMATE_ENTITY,
        "climate_state": "heat",
        "climate_preset": base.CURRENT_PRESET,
        "presence_state": expected_presence,
        "motion_state": "off",
        "night_state": "off",
        "enable_state": "on",
        "ownership_config_entry_state": "not_loaded",
        "ownership_config_entry_disabled_by": "user",
        "ownership_entry_registered": True,
        "entity_id": base.CLIMATE_ENTITY,
        "entity_platform": base.BETTER_THERMOSTAT_DOMAIN,
    }


async def run_native(
    *,
    blueprint_source: Path,
    qualification: dict[str, Any],
    feedback: str,
    label: str,
) -> dict[str, Any]:
    if feedback == "HOME":
        initial_presence, final_presence = "off", "on"
    elif feedback == "AWAY":
        initial_presence, final_presence = "on", "off"
    else:
        raise ValueError(feedback)

    hass, lab, temp, registry = await base.make_hass(
        blueprint_source=blueprint_source,
        qualification=qualification,
        native_automation=True,
        initial_presence=initial_presence,
    )
    try:
        snapshot = initial_snapshot(hass, registry)
        if not snapshot_exact(snapshot, expected_presence=initial_presence):
            raise AssertionError(f"{label}: pre-action snapshot failed frozen initialization: {snapshot}")

        hass.states.async_set(base.PRESENCE_ENTITY, final_presence)
        await base.wait_for_action(lab)
        await hass.async_block_till_done()
        row = base.summarize(
            label=label,
            lab=lab,
            registry=registry,
            expected_feedback=feedback,
        )
        row["initial_snapshot"] = snapshot
        row["initial_snapshot_phase"] = "after_native_automation_setup_before_feedback_transition"
        return row
    finally:
        await base.cleanup_hass(hass, lab, temp)


async def run_replay(
    *,
    blueprint_source: Path,
    qualification: dict[str, Any],
    source_service_data: dict[str, Any],
    target_feedback: str,
    label: str,
) -> dict[str, Any]:
    presence = "on" if target_feedback == "HOME" else "off"
    hass, lab, temp, registry = await base.make_hass(
        blueprint_source=blueprint_source,
        qualification=qualification,
        native_automation=False,
        initial_presence=presence,
    )
    try:
        snapshot = initial_snapshot(hass, registry)
        if not snapshot_exact(snapshot, expected_presence=presence):
            raise AssertionError(f"{label}: pre-replay snapshot failed frozen initialization: {snapshot}")

        await hass.services.async_call(
            "climate",
            "set_preset_mode",
            dict(source_service_data),
            blocking=True,
        )
        await hass.async_block_till_done()
        row = base.summarize(
            label=label,
            lab=lab,
            registry=registry,
            expected_feedback=target_feedback,
        )
        row["initial_snapshot"] = snapshot
        row["initial_snapshot_phase"] = "before_recorded_replay_service_call"
        calls = [
            event
            for event in lab.events
            if event["operation"] == "climate.set_preset_mode"
        ]
        if len(calls) != 1:
            raise AssertionError(f"{label}: replay must issue exactly one climate call")
        event = calls[0]
        identity = base.HAActionIdentity(
            operation=str(event["operation"]),
            target_class=event.get("target_class"),
            variant=str(event["variant"]),
        )
        row["support"] = base.replay_support(identity, target_feedback)
        return row
    finally:
        await base.cleanup_hass(hass, lab, temp)


def all_snapshot_rows(
    source: dict[str, Any],
    target_native: list[dict[str, Any]],
    target_replay: list[dict[str, Any]],
    controls: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], str]]:
    rows: list[tuple[dict[str, Any], str]] = [(source, "off")]
    rows.extend((row, "on") for row in target_native)
    rows.extend((row, "off") for row in target_replay)
    rows.extend((pair["native"], "off") for pair in controls)
    rows.extend((pair["replay"], "on") for pair in controls)
    return rows


async def experiment(args: argparse.Namespace) -> dict[str, Any]:
    blueprint_source = Path(args.blueprint)
    component_source = Path(args.ownership_component)
    blueprint_sha = hashlib.sha256(blueprint_source.read_bytes()).hexdigest()
    if blueprint_sha != base.EXPECTED_BLUEPRINT_SHA256:
        raise AssertionError(
            f"external blueprint hash mismatch: {blueprint_sha} != {base.EXPECTED_BLUEPRINT_SHA256}"
        )

    qualification, qualification_temp, qualification_hass = await base.qualify_upstream_loader(
        component_source
    )
    try:
        source = await run_native(
            blueprint_source=blueprint_source,
            qualification=qualification,
            feedback="HOME",
            label="source_native_home",
        )
        recorded_data = base.source_service_data(source)

        target_native: list[dict[str, Any]] = []
        target_replay: list[dict[str, Any]] = []
        controls: list[dict[str, Any]] = []
        for trial in range(args.trials):
            target_native.append(
                await run_native(
                    blueprint_source=blueprint_source,
                    qualification=qualification,
                    feedback="AWAY",
                    label=f"target_native_away_t{trial}",
                )
            )
            target_replay.append(
                await run_replay(
                    blueprint_source=blueprint_source,
                    qualification=qualification,
                    source_service_data=recorded_data,
                    target_feedback="AWAY",
                    label=f"target_replay_home_t{trial}",
                )
            )
            controls.append(
                {
                    "native": await run_native(
                        blueprint_source=blueprint_source,
                        qualification=qualification,
                        feedback="HOME",
                        label=f"control_native_home_t{trial}",
                    ),
                    "replay": await run_replay(
                        blueprint_source=blueprint_source,
                        qualification=qualification,
                        source_service_data=recorded_data,
                        target_feedback="HOME",
                        label=f"control_replay_home_t{trial}",
                    ),
                }
            )

        kernel = base.action_kernel()
        tv_operation = workload_shift_tv(
            kernel,
            "decision",
            {"HOME": 1},
            {"AWAY": 1},
            projection="operation",
        )
        tv_action = workload_shift_tv(
            kernel,
            "decision",
            {"HOME": 1},
            {"AWAY": 1},
            projection="action",
        )

        source_ok = (
            source["climate_call_count"] == 1
            and base.no_extra_actions(source)
            and base.exact_identity(source, base.HOME_VARIANT)
            and base.ownership_ok(source)
        )
        target_native_ok = all(
            row["climate_call_count"] == 1
            and base.no_extra_actions(row)
            and base.exact_identity(row, base.AWAY_VARIANT)
            and base.ownership_ok(row)
            for row in target_native
        )
        target_replay_ok = all(
            row["climate_call_count"] == 1
            and base.no_extra_actions(row)
            and base.exact_identity(row, base.HOME_VARIANT)
            and base.ownership_ok(row)
            and not row["support"]["operation"]["support_failure"]
            and row["support"]["operation"]["target_probability"] == 1.0
            and row["support"]["action"]["support_failure"]
            and row["support"]["action"]["target_probability"] == 0.0
            for row in target_replay
        )
        controls_ok = all(
            base.exact_identity(pair["native"], base.HOME_VARIANT)
            and base.exact_identity(pair["replay"], base.HOME_VARIANT)
            and base.no_extra_actions(pair["native"])
            and base.no_extra_actions(pair["replay"])
            and base.ownership_ok(pair["native"])
            and base.ownership_ok(pair["replay"])
            and not pair["replay"]["support"]["operation"]["support_failure"]
            and not pair["replay"]["support"]["action"]["support_failure"]
            and pair["replay"]["support"]["action"]["target_probability"] == 1.0
            for pair in controls
        )

        all_rows = [source, *target_native, *target_replay]
        all_rows.extend(pair[key] for pair in controls for key in ("native", "replay"))
        tree_hashes = {
            row["registry"]["upstream_component_tree_sha256"] for row in all_rows
        }
        snapshot_rows = all_snapshot_rows(source, target_native, target_replay, controls)
        snapshots_ok = all(
            snapshot_exact(row["initial_snapshot"], expected_presence=presence)
            for row, presence in snapshot_rows
        )

        gates = {
            "external_source_hash_exact": blueprint_sha == base.EXPECTED_BLUEPRINT_SHA256,
            "ha_version_exact": base.HA_VERSION == "2026.9.0",
            "upstream_loader_qualified_before_outcome": qualification["qualification_before_outcome"] is True,
            "upstream_loader_domain_exact": qualification["ha_loader_resolved_domain"] == base.BETTER_THERMOSTAT_DOMAIN,
            "upstream_loader_version_exact": qualification["ha_loader_resolved_version"] == base.BETTER_THERMOSTAT_VERSION,
            "upstream_integration_setup_not_invoked": qualification["integration_setup_invoked"] is False,
            "persisted_disabled_ownership_all": all(base.ownership_ok(row) for row in all_rows),
            "upstream_component_tree_stable": len(tree_hashes) == 1,
            "pre_action_initial_snapshot_exact_all": snapshots_ok,
            "source_home_exact": source_ok,
            "target_native_away_exact_all": target_native_ok,
            "target_replay_home_exact_all": target_replay_ok,
            "operation_projection_supports_recorded_action_all": all(
                not row["support"]["operation"]["support_failure"] for row in target_replay
            ),
            "action_projection_rejects_recorded_action_all": all(
                row["support"]["action"]["support_failure"] for row in target_replay
            ),
            "tv_operation_exact_zero": tv_operation == 0,
            "tv_action_exact_one": tv_action == 1,
            "no_feedback_shift_control_all": controls_ok,
        }
        gates["promoted"] = all(gates.values())

        listener_diagnostics = {
            "source_call_observer_preset": source["raw_call_events"][0].get("climate_preset_before_issue"),
            "target_native_call_observer_presets": [
                row["raw_call_events"][0].get("climate_preset_before_issue") for row in target_native
            ],
            "target_replay_call_observer_presets": [
                row["raw_call_events"][0].get("climate_preset_before_issue") for row in target_replay
            ],
            "interpretation": "diagnostic_only_event_callback_observation_not_used_as_pre_action_state",
        }

        return {
            "schema": "agentmark.natural_controller.better_thermostat_action_identity.v4",
            "replica": args.replica,
            "decision": "PROMOTED" if gates["promoted"] else "NOT_PROMOTED",
            "environment": {"home_assistant_core_version": base.HA_VERSION},
            "external_controller": {
                "repository": "n3roGit/MyHomeAssistantMods",
                "commit": "57d56f076c05ccaa9553e6bd4b673b6d43a8cf7f",
                "path": "automation/BetterThermostatControl/BetterThermostat_RoomHeatControl_Lean.yaml",
                "sha256": blueprint_sha,
                "source_edited": False,
            },
            "controlled_device_ownership": {
                "mode": base.OWNERSHIP_MODE,
                "config_entry_registration_path": base.CONFIG_ENTRY_REGISTRATION_PATH,
                "upstream_repository": qualification["repository"],
                "upstream_commit": qualification["commit"],
                "upstream_version": qualification["version"],
                "upstream_manifest_sha256": qualification["manifest_sha256"],
                "component_tree_sha256": qualification["component_tree_sha256"],
                "loader_qualification": {
                    "domain": qualification["ha_loader_resolved_domain"],
                    "version": qualification["ha_loader_resolved_version"],
                    "before_outcome": True,
                    "integration_setup_invoked": False,
                },
                "config_entry_intentionally_disabled": True,
                "integration_internal_control_logic_executed": False,
            },
            "measurement_contract": {
                "pre_action_state_source": "explicit_initial_snapshot_before_feedback_transition_or_replay_call",
                "event_listener_state_read": "diagnostic_only_not_strict_pre_handler",
                "listener_diagnostics": listener_diagnostics,
            },
            "frozen_adapter": {
                "operation": "domain.service",
                "target_class": "resolved target entity domain class",
                "variant": "canonical JSON of rendered top-level non-target service data",
                "home_variant": base.HOME_VARIANT,
                "away_variant": base.AWAY_VARIANT,
            },
            "frozen_protocol": {
                "current_preset": base.CURRENT_PRESET,
                "source_feedback": "HOME",
                "target_feedback": "AWAY",
                "trials": args.trials,
                "writeback_enable": False,
                "writeback_bounds_enable": False,
                "boost_entity": "",
                "eco_entity": "",
                "activity_entity": "",
            },
            "source": source,
            "recorded_source_service_data": recorded_data,
            "target_native": target_native,
            "target_replay": target_replay,
            "no_feedback_shift_control": controls,
            "theory": {
                "TV_operation": float(tv_operation),
                "TV_action": float(tv_action),
            },
            "promotion_gates": gates,
        }
    finally:
        try:
            await qualification_hass.async_stop()
        finally:
            qualification_temp.cleanup()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--blueprint", required=True)
    p.add_argument("--ownership-component", required=True)
    p.add_argument("--replica", type=int, required=True)
    p.add_argument("--trials", type=int, default=base.TRIALS)
    p.add_argument("--out", required=True)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    result = asyncio.run(experiment(args))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "decision": result["decision"],
                "replica": result["replica"],
                "theory": result["theory"],
                "measurement_contract": result["measurement_contract"],
                "promotion_gates": result["promotion_gates"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    if result["decision"] != "PROMOTED":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
