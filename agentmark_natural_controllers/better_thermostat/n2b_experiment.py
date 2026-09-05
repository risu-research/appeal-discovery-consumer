from __future__ import annotations

"""N2b producer: natural Better Thermostat decision-equivalence negative.

Preregistered before native outcome. It reuses the sealed N2 ownership and
authenticity boundary but selects two different raw feedback vectors that the
pinned external controller is predicted to map to the same action.
"""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

from homeassistant.components import automation
from homeassistant.setup import async_setup_component

from agentmark.kernel import ReactiveKernel
from agentmark.semantics import (
    feedback_partition,
    policy_sensitivity_eta,
    quotient_feedback_law,
    step_replay_validity,
    total_variation,
    workload_shift_tv,
)
from agentmark_natural_controllers.better_thermostat import experiment_persisted_ownership as base

FEEDBACK_A = "AWAY_MOTION_OFF"
FEEDBACK_B = "AWAY_MOTION_ON"
EXPECTED_VARIANT = base.AWAY_VARIANT
TRIALS = 6


def pair_kernel() -> ReactiveKernel:
    away = {
        "p": 1,
        "operation": "climate.set_preset_mode",
        "target_class": "climate",
        "variant": EXPECTED_VARIANT,
        "next_state": "done",
    }
    return ReactiveKernel({
        "initial_state": "decision",
        "feedback_alphabet": [FEEDBACK_A, FEEDBACK_B],
        "states": {
            "decision": {FEEDBACK_A: [dict(away)], FEEDBACK_B: [dict(away)]},
            "done": {
                FEEDBACK_A: [{"p": 1, "operation": "STOP", "next_state": "done"}],
                FEEDBACK_B: [{"p": 1, "operation": "STOP", "next_state": "done"}],
            },
        },
    })


def _verdict_json(verdict: Any) -> dict[str, Any]:
    return {
        "source_probability": float(verdict.source_probability),
        "target_probability": float(verdict.target_probability),
        "source_consistent": bool(verdict.source_consistent),
        "target_supports_recorded_event": bool(verdict.target_supports_recorded_event),
        "support_failure": bool(verdict.support_failure),
    }


def replay_support(identity: base.HAActionIdentity, target_feedback: str) -> dict[str, Any]:
    kernel = pair_kernel()
    op = step_replay_validity(
        kernel,
        state="decision",
        source_feedback=FEEDBACK_A,
        target_feedback=target_feedback,
        recorded_event=identity.operation,
        projection="operation",
    )
    action = step_replay_validity(
        kernel,
        state="decision",
        source_feedback=FEEDBACK_A,
        target_feedback=target_feedback,
        recorded_event=identity.projected_key(),
        projection="action",
    )
    return {
        "source_feedback": FEEDBACK_A,
        "target_feedback": target_feedback,
        "operation": _verdict_json(op),
        "action": _verdict_json(action),
    }


def consequential_events(lab: base.ActionLab) -> list[dict[str, Any]]:
    return [
        event for event in lab.events
        if event["operation"] in {"climate.set_preset_mode", "number.set_value"}
    ]


async def wait_for_climate_action(lab: base.ActionLab, timeout_s: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while True:
        if any(event["operation"] == "climate.set_preset_mode" for event in lab.events):
            return
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("timed out waiting for Better Thermostat climate action")
        await asyncio.sleep(0.001)


async def install_native_automation(
    hass: Any,
    temp: Any,
    registry: dict[str, Any],
    blueprint_source: Path,
) -> None:
    destination = (
        Path(temp.name) / "blueprints" / "automation" / "agentmark" /
        "better_thermostat_lean.yaml"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(blueprint_source, destination)
    ok = await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            "automation": {
                "use_blueprint": {
                    "path": base.BLUEPRINT_REL,
                    "input": {
                        "climate_device": registry["device_id"],
                        "presence_group": base.PRESENCE_ENTITY,
                        "motion_group": base.MOTION_ENTITY,
                        "night_mode_entity": base.NIGHT_ENTITY,
                        "enable_switch": base.ENABLE_ENTITY,
                        "writeback_enable": False,
                        "writeback_bounds_enable": False,
                        "boost_entity": "",
                        "eco_entity": "",
                        "activity_entity": "",
                    },
                }
            }
        },
    )
    if not ok:
        raise RuntimeError("native Better Thermostat automation setup returned false")
    await hass.async_block_till_done()


async def make_hass_for_pair(
    *,
    blueprint_source: Path,
    qualification: dict[str, Any],
    native_automation: bool,
    initial_presence: str,
    initial_motion: str,
) -> tuple[Any, base.ActionLab, Any, dict[str, Any]]:
    # Start from sealed N2 bootstrap with automation disabled, seed motion, then
    # install the automation. This prevents seeding motion from becoming a trigger.
    hass, lab, temp, registry = await base.make_hass(
        blueprint_source=blueprint_source,
        qualification=qualification,
        native_automation=False,
        initial_presence=initial_presence,
    )
    hass.states.async_set(base.MOTION_ENTITY, initial_motion)
    if native_automation:
        await install_native_automation(hass, temp, registry, blueprint_source)
    return hass, lab, temp, registry


def state_snapshot(hass: Any, registry: dict[str, Any], phase: str) -> dict[str, Any]:
    climate = hass.states.get(base.CLIMATE_ENTITY)
    presence = hass.states.get(base.PRESENCE_ENTITY)
    motion = hass.states.get(base.MOTION_ENTITY)
    night = hass.states.get(base.NIGHT_ENTITY)
    enable = hass.states.get(base.ENABLE_ENTITY)
    return {
        "phase": phase,
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


def snapshot_exact(
    snapshot: dict[str, Any], *, phase: str, presence: str, motion: str
) -> bool:
    return snapshot == {
        "phase": phase,
        "climate_entity": base.CLIMATE_ENTITY,
        "climate_state": "heat",
        "climate_preset": base.CURRENT_PRESET,
        "presence_state": presence,
        "motion_state": motion,
        "night_state": "off",
        "enable_state": "on",
        "ownership_config_entry_state": "not_loaded",
        "ownership_config_entry_disabled_by": "user",
        "ownership_entry_registered": True,
        "entity_id": base.CLIMATE_ENTITY,
        "entity_platform": base.BETTER_THERMOSTAT_DOMAIN,
    }


def feedback_vector(motion: str) -> dict[str, Any]:
    return {
        "presence": "off",
        "motion": motion,
        "night": "off",
        "boost": False,
        "eco": False,
        "activity": False,
    }


async def run_native(
    *,
    blueprint_source: Path,
    qualification: dict[str, Any],
    motion: str,
    feedback_label: str,
    label: str,
) -> dict[str, Any]:
    hass, lab, temp, registry = await make_hass_for_pair(
        blueprint_source=blueprint_source,
        qualification=qualification,
        native_automation=True,
        initial_presence="on",
        initial_motion=motion,
    )
    try:
        initial_phase = "after_automation_setup_before_presence_transition"
        initial = state_snapshot(hass, registry, initial_phase)
        if not snapshot_exact(initial, phase=initial_phase, presence="on", motion=motion):
            raise AssertionError(f"{label}: initial snapshot mismatch: {initial}")
        if consequential_events(lab):
            raise AssertionError(f"{label}: consequential action occurred before frozen trigger")

        # Same trigger dimension in source and target: presence on -> off.
        hass.states.async_set(base.PRESENCE_ENTITY, "off")
        decision_phase = "after_presence_transition_before_event_loop_yield"
        decision = state_snapshot(hass, registry, decision_phase)
        if not snapshot_exact(decision, phase=decision_phase, presence="off", motion=motion):
            raise AssertionError(f"{label}: decision feedback snapshot mismatch: {decision}")
        if consequential_events(lab):
            raise AssertionError(
                f"{label}: consequential action observed before decision-feedback snapshot"
            )

        await wait_for_climate_action(lab)
        await hass.async_block_till_done()
        row = base.summarize(
            label=label,
            lab=lab,
            registry=registry,
            expected_feedback=feedback_label,
        )
        row["initial_snapshot"] = initial
        row["decision_feedback_snapshot"] = decision
        row["decision_feedback_vector"] = feedback_vector(motion)
        return row
    finally:
        await base.cleanup_hass(hass, lab, temp)


async def run_replay(
    *,
    blueprint_source: Path,
    qualification: dict[str, Any],
    source_service_data: dict[str, Any],
    motion: str,
    target_feedback: str,
    label: str,
) -> dict[str, Any]:
    hass, lab, temp, registry = await make_hass_for_pair(
        blueprint_source=blueprint_source,
        qualification=qualification,
        native_automation=False,
        initial_presence="off",
        initial_motion=motion,
    )
    try:
        phase = "before_recorded_replay_service_call"
        snapshot = state_snapshot(hass, registry, phase)
        if not snapshot_exact(snapshot, phase=phase, presence="off", motion=motion):
            raise AssertionError(f"{label}: replay target snapshot mismatch: {snapshot}")
        if consequential_events(lab):
            raise AssertionError(f"{label}: consequential action occurred before replay")

        await hass.services.async_call(
            "climate", "set_preset_mode", dict(source_service_data), blocking=True
        )
        await hass.async_block_till_done()
        row = base.summarize(
            label=label,
            lab=lab,
            registry=registry,
            expected_feedback=target_feedback,
        )
        row["replay_feedback_snapshot"] = snapshot
        row["decision_feedback_vector"] = feedback_vector(motion)
        calls = [
            event for event in lab.events
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
        row["support"] = replay_support(identity, target_feedback)
        return row
    finally:
        await base.cleanup_hass(hass, lab, temp)


def identity_ok(row: dict[str, Any]) -> bool:
    return (
        row["climate_call_count"] == 1
        and base.no_extra_actions(row)
        and base.exact_identity(row, EXPECTED_VARIANT)
        and base.ownership_ok(row)
    )


def native_snapshot_ok(row: dict[str, Any], motion: str) -> bool:
    return (
        snapshot_exact(
            row["initial_snapshot"],
            phase="after_automation_setup_before_presence_transition",
            presence="on",
            motion=motion,
        )
        and snapshot_exact(
            row["decision_feedback_snapshot"],
            phase="after_presence_transition_before_event_loop_yield",
            presence="off",
            motion=motion,
        )
    )


def replay_snapshot_ok(row: dict[str, Any], motion: str) -> bool:
    return snapshot_exact(
        row["replay_feedback_snapshot"],
        phase="before_recorded_replay_service_call",
        presence="off",
        motion=motion,
    )


def replay_support_ok(row: dict[str, Any]) -> bool:
    support = row["support"]
    return (
        not support["operation"]["support_failure"]
        and support["operation"]["source_probability"] == 1.0
        and support["operation"]["target_probability"] == 1.0
        and not support["action"]["support_failure"]
        and support["action"]["source_probability"] == 1.0
        and support["action"]["target_probability"] == 1.0
    )


def theory_summary() -> dict[str, Any]:
    kernel = pair_kernel()
    source_law = {FEEDBACK_A: 1}
    target_law = {FEEDBACK_B: 1}
    partition = feedback_partition(kernel, "decision", projection="action")
    q_source = quotient_feedback_law(source_law, partition)
    q_target = quotient_feedback_law(target_law, partition)
    return {
        "feedback_A": FEEDBACK_A,
        "feedback_B": FEEDBACK_B,
        "action_feedback_classes": [list(cls) for cls in partition.classes],
        "unsupported_feedback": list(partition.unsupported),
        "raw_feedback_tv": float(total_variation(source_law, target_law)),
        "quotient_feedback_tv": float(total_variation(q_source, q_target)),
        "TV_operation": float(workload_shift_tv(
            kernel, "decision", source_law, target_law, projection="operation"
        )),
        "TV_action": float(workload_shift_tv(
            kernel, "decision", source_law, target_law, projection="action"
        )),
        "pair_restricted_eta_action": float(policy_sensitivity_eta(
            kernel, "decision", projection="action"
        )),
        "source_quotient_law": {"|".join(k): float(v) for k, v in q_source.items()},
        "target_quotient_law": {"|".join(k): float(v) for k, v in q_target.items()},
    }


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
        source_native: list[dict[str, Any]] = []
        target_native: list[dict[str, Any]] = []
        target_replay: list[dict[str, Any]] = []
        no_shift_replay: list[dict[str, Any]] = []

        first_source = await run_native(
            blueprint_source=blueprint_source,
            qualification=qualification,
            motion="off",
            feedback_label=FEEDBACK_A,
            label="source_native_yA_t0",
        )
        source_native.append(first_source)
        recorded_data = base.source_service_data(first_source)

        for trial in range(1, args.trials):
            source_native.append(await run_native(
                blueprint_source=blueprint_source,
                qualification=qualification,
                motion="off",
                feedback_label=FEEDBACK_A,
                label=f"source_native_yA_t{trial}",
            ))

        for trial in range(args.trials):
            target_native.append(await run_native(
                blueprint_source=blueprint_source,
                qualification=qualification,
                motion="on",
                feedback_label=FEEDBACK_B,
                label=f"target_native_yB_t{trial}",
            ))
            target_replay.append(await run_replay(
                blueprint_source=blueprint_source,
                qualification=qualification,
                source_service_data=recorded_data,
                motion="on",
                target_feedback=FEEDBACK_B,
                label=f"target_replay_yA_action_under_yB_t{trial}",
            ))
            no_shift_replay.append(await run_replay(
                blueprint_source=blueprint_source,
                qualification=qualification,
                source_service_data=recorded_data,
                motion="off",
                target_feedback=FEEDBACK_A,
                label=f"control_replay_yA_under_yA_t{trial}",
            ))

        theory = theory_summary()
        source_ok = all(
            identity_ok(row)
            and native_snapshot_ok(row, "off")
            and row["decision_feedback_vector"] == feedback_vector("off")
            for row in source_native
        )
        target_native_ok = all(
            identity_ok(row)
            and native_snapshot_ok(row, "on")
            and row["decision_feedback_vector"] == feedback_vector("on")
            for row in target_native
        )
        target_replay_ok = all(
            identity_ok(row)
            and replay_snapshot_ok(row, "on")
            and replay_support_ok(row)
            and row["decision_feedback_vector"] == feedback_vector("on")
            for row in target_replay
        )
        no_shift_ok = all(
            identity_ok(row)
            and replay_snapshot_ok(row, "off")
            and replay_support_ok(row)
            and row["decision_feedback_vector"] == feedback_vector("off")
            for row in no_shift_replay
        )
        all_rows = [*source_native, *target_native, *target_replay, *no_shift_replay]
        tree_hashes = {row["registry"]["upstream_component_tree_sha256"] for row in all_rows}
        theory_ok = (
            theory["raw_feedback_tv"] == 1.0
            and theory["quotient_feedback_tv"] == 0.0
            and theory["TV_operation"] == 0.0
            and theory["TV_action"] == 0.0
            and theory["pair_restricted_eta_action"] == 0.0
            and theory["action_feedback_classes"] == [sorted([FEEDBACK_A, FEEDBACK_B])]
            and theory["unsupported_feedback"] == []
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
            "raw_feedback_vectors_distinct": feedback_vector("off") != feedback_vector("on"),
            "source_native_yA_away_exact_all": source_ok,
            "target_native_yB_away_exact_all": target_native_ok,
            "target_replay_away_supported_exact_all": target_replay_ok,
            "no_shift_replay_yA_supported_exact_all": no_shift_ok,
            "native_source_target_action_identity_equal_all": all(
                row["identity"] == source_native[0]["identity"] for row in target_native
            ),
            "decision_equivalence_theory_exact": theory_ok,
        }
        gates["promoted"] = all(gates.values())

        return {
            "schema": "agentmark.natural_controller.better_thermostat_decision_equivalence.v1",
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
            "frozen_adapter": {
                "operation": "domain.service",
                "target_class": "resolved target entity domain class",
                "variant": "canonical JSON of rendered top-level non-target service data",
                "expected_variant": EXPECTED_VARIANT,
            },
            "frozen_protocol": {
                "current_preset": base.CURRENT_PRESET,
                "source_feedback_label": FEEDBACK_A,
                "target_feedback_label": FEEDBACK_B,
                "source_feedback_vector": feedback_vector("off"),
                "target_feedback_vector": feedback_vector("on"),
                "native_trigger_both": "presence on -> off",
                "trials_per_condition": args.trials,
                "writeback_enable": False,
                "writeback_bounds_enable": False,
                "boost_entity": "",
                "eco_entity": "",
                "activity_entity": "",
            },
            "recorded_source_service_data": recorded_data,
            "source_native": source_native,
            "target_native": target_native,
            "target_replay": target_replay,
            "no_shift_replay": no_shift_replay,
            "theory": theory,
            "promotion_gates": gates,
        }
    finally:
        await qualification_hass.async_stop()
        qualification_temp.cleanup()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--blueprint", required=True)
    p.add_argument("--ownership-component", required=True)
    p.add_argument("--replica", type=int, required=True)
    p.add_argument("--trials", type=int, default=TRIALS)
    p.add_argument("--out", required=True)
    return p.parse_args()


async def main() -> None:
    args = parse_args()
    result = await experiment(args)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "schema": result["schema"],
        "replica": result["replica"],
        "decision": result["decision"],
        "theory": result["theory"],
        "promotion_gates": result["promotion_gates"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
