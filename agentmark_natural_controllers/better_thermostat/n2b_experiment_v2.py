from __future__ import annotations

"""N2b v2 producer: event-level feedback witnesses after invalid v1 observer.

Scientific pair, projection, expected action, theory predictions, trial count,
external controller, HA image, and ownership boundary are unchanged. Only the
measurement location for native decision feedback is corrected.
"""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import time
from typing import Any

from homeassistant.const import EVENT_CALL_SERVICE, EVENT_STATE_CHANGED
from homeassistant.core import Event, callback

from agentmark_natural_controllers.action_identity import canonical_action_identity
from agentmark_natural_controllers.better_thermostat import experiment_persisted_ownership as base
from agentmark_natural_controllers.better_thermostat import n2b_experiment as v1

SCHEMA = "agentmark.natural_controller.better_thermostat_decision_equivalence.v2"
TRIALS = 6


def now_ns() -> int:
    return time.perf_counter_ns()


def read_feedback(hass: Any) -> dict[str, Any]:
    presence = hass.states.get(base.PRESENCE_ENTITY)
    motion = hass.states.get(base.MOTION_ENTITY)
    night = hass.states.get(base.NIGHT_ENTITY)
    return {
        "presence": None if presence is None else presence.state,
        "motion": None if motion is None else motion.state,
        "night": None if night is None else night.state,
        "boost": False,
        "eco": False,
        "activity": False,
    }


class DecisionFeedbackObserver:
    """Observe trigger transition and feedback at consequential service issue."""

    def __init__(self, hass: Any):
        self.hass = hass
        self.presence_transitions: list[dict[str, Any]] = []
        self.service_issues: list[dict[str, Any]] = []
        self._unsubs: list[Any] = []

    def install(self) -> None:
        @callback
        def on_state_changed(event: Event) -> None:
            if str(event.data.get("entity_id")) != base.PRESENCE_ENTITY:
                return
            old_state = event.data.get("old_state")
            new_state = event.data.get("new_state")
            old = None if old_state is None else old_state.state
            new = None if new_state is None else new_state.state
            if old == "on" and new == "off":
                self.presence_transitions.append({
                    "t_ns": now_ns(),
                    "entity_id": base.PRESENCE_ENTITY,
                    "old_state": old,
                    "new_state": new,
                    "feedback": read_feedback(self.hass),
                    "context_id": None if new_state is None else str(new_state.context.id),
                    "context_parent_id": (
                        None
                        if new_state is None or new_state.context.parent_id is None
                        else str(new_state.context.parent_id)
                    ),
                })

        @callback
        def on_call_service(event: Event) -> None:
            domain = str(event.data.get("domain"))
            service = str(event.data.get("service"))
            if (domain, service) != ("climate", "set_preset_mode"):
                return
            service_data = dict(event.data.get("service_data") or {})
            identity = canonical_action_identity(domain, service, service_data)
            self.service_issues.append({
                "t_ns": now_ns(),
                "domain": domain,
                "service": service,
                "service_data": service_data,
                "operation": identity.operation,
                "target_class": identity.target_class,
                "variant": identity.variant,
                "feedback": read_feedback(self.hass),
                "context_id": str(event.context.id),
                "context_parent_id": (
                    None if event.context.parent_id is None else str(event.context.parent_id)
                ),
            })

        self._unsubs.append(self.hass.bus.async_listen(EVENT_STATE_CHANGED, on_state_changed))
        self._unsubs.append(self.hass.bus.async_listen(EVENT_CALL_SERVICE, on_call_service))

    def close(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()


async def make_native_hass(
    *,
    blueprint_source: Path,
    qualification: dict[str, Any],
    motion: str,
) -> tuple[Any, base.ActionLab, Any, dict[str, Any], DecisionFeedbackObserver]:
    # Seed raw feedback before installing automation so motion initialization is
    # never itself the native trigger.
    hass, lab, temp, registry = await base.make_hass(
        blueprint_source=blueprint_source,
        qualification=qualification,
        native_automation=False,
        initial_presence="on",
    )
    hass.states.async_set(base.MOTION_ENTITY, motion)
    observer = DecisionFeedbackObserver(hass)
    observer.install()
    await v1.install_native_automation(hass, temp, registry, blueprint_source)
    return hass, lab, temp, registry, observer


async def run_native_v2(
    *,
    blueprint_source: Path,
    qualification: dict[str, Any],
    motion: str,
    feedback_label: str,
    label: str,
) -> dict[str, Any]:
    hass, lab, temp, registry, observer = await make_native_hass(
        blueprint_source=blueprint_source,
        qualification=qualification,
        motion=motion,
    )
    try:
        initial_phase = "after_automation_setup_before_presence_transition"
        initial = v1.state_snapshot(hass, registry, initial_phase)
        if not v1.snapshot_exact(
            initial,
            phase=initial_phase,
            presence="on",
            motion=motion,
        ):
            raise AssertionError(f"{label}: initial snapshot mismatch: {initial}")
        if v1.consequential_events(lab) or observer.service_issues:
            raise AssertionError(f"{label}: consequential action occurred before frozen trigger")

        # Frozen trigger is identical in both conditions. HA 2026.9.0 may run
        # the automation eagerly before async_set returns; v2 observes the
        # transition and service event directly rather than inventing a
        # caller-visible microstep that the runtime does not expose.
        hass.states.async_set(base.PRESENCE_ENTITY, "off")
        await v1.wait_for_climate_action(lab)
        await hass.async_block_till_done()

        row = base.summarize(
            label=label,
            lab=lab,
            registry=registry,
            expected_feedback=feedback_label,
        )
        row["initial_snapshot"] = initial
        row["presence_transition_witnesses"] = list(observer.presence_transitions)
        row["service_issue_feedback_witnesses"] = list(observer.service_issues)
        row["post_action_feedback_snapshot"] = read_feedback(hass)
        row["decision_feedback_vector"] = v1.feedback_vector(motion)
        return row
    finally:
        observer.close()
        await base.cleanup_hass(hass, lab, temp)


def native_feedback_evidence_ok(row: dict[str, Any], *, motion: str) -> bool:
    expected = v1.feedback_vector(motion)
    transitions = row["presence_transition_witnesses"]
    issues = row["service_issue_feedback_witnesses"]
    if len(transitions) != 1 or len(issues) != 1:
        return False
    transition = transitions[0]
    issue = issues[0]
    return (
        v1.snapshot_exact(
            row["initial_snapshot"],
            phase="after_automation_setup_before_presence_transition",
            presence="on",
            motion=motion,
        )
        and transition["entity_id"] == base.PRESENCE_ENTITY
        and transition["old_state"] == "on"
        and transition["new_state"] == "off"
        and transition["feedback"] == expected
        and issue["operation"] == "climate.set_preset_mode"
        and issue["target_class"] == "climate"
        and issue["variant"] == base.AWAY_VARIANT
        and issue["feedback"] == expected
        and transition["t_ns"] <= issue["t_ns"]
        and row["post_action_feedback_snapshot"] == expected
        and row["decision_feedback_vector"] == expected
    )


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

        first_source = await run_native_v2(
            blueprint_source=blueprint_source,
            qualification=qualification,
            motion="off",
            feedback_label=v1.FEEDBACK_A,
            label="source_native_yA_t0",
        )
        source_native.append(first_source)
        recorded_data = base.source_service_data(first_source)

        for trial in range(1, args.trials):
            source_native.append(await run_native_v2(
                blueprint_source=blueprint_source,
                qualification=qualification,
                motion="off",
                feedback_label=v1.FEEDBACK_A,
                label=f"source_native_yA_t{trial}",
            ))

        for trial in range(args.trials):
            target_native.append(await run_native_v2(
                blueprint_source=blueprint_source,
                qualification=qualification,
                motion="on",
                feedback_label=v1.FEEDBACK_B,
                label=f"target_native_yB_t{trial}",
            ))
            target_replay.append(await v1.run_replay(
                blueprint_source=blueprint_source,
                qualification=qualification,
                source_service_data=recorded_data,
                motion="on",
                target_feedback=v1.FEEDBACK_B,
                label=f"target_replay_yA_action_under_yB_t{trial}",
            ))
            no_shift_replay.append(await v1.run_replay(
                blueprint_source=blueprint_source,
                qualification=qualification,
                source_service_data=recorded_data,
                motion="off",
                target_feedback=v1.FEEDBACK_A,
                label=f"control_replay_yA_under_yA_t{trial}",
            ))

        theory = v1.theory_summary()
        source_ok = all(
            v1.identity_ok(row)
            and native_feedback_evidence_ok(row, motion="off")
            for row in source_native
        )
        target_native_ok = all(
            v1.identity_ok(row)
            and native_feedback_evidence_ok(row, motion="on")
            for row in target_native
        )
        target_replay_ok = all(
            v1.identity_ok(row)
            and v1.replay_snapshot_ok(row, "on")
            and v1.replay_support_ok(row)
            and row["decision_feedback_vector"] == v1.feedback_vector("on")
            for row in target_replay
        )
        no_shift_ok = all(
            v1.identity_ok(row)
            and v1.replay_snapshot_ok(row, "off")
            and v1.replay_support_ok(row)
            and row["decision_feedback_vector"] == v1.feedback_vector("off")
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
            and theory["action_feedback_classes"] == [sorted([v1.FEEDBACK_A, v1.FEEDBACK_B])]
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
            "raw_feedback_vectors_distinct": v1.feedback_vector("off") != v1.feedback_vector("on"),
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
            "schema": SCHEMA,
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
                "version": "n2b-v2-event-level-feedback-witness",
                "v1_failure_run": 33972326066,
                "strict_pre_handler_climate_snapshot_claimed": False,
                "feedback_entities_observed_at_presence_transition": True,
                "feedback_entities_observed_at_service_issue": True,
                "post_action_feedback_nonmutation_check": True,
            },
            "frozen_adapter": {
                "operation": "domain.service",
                "target_class": "resolved target entity domain class",
                "variant": "canonical JSON of rendered top-level non-target service data",
                "expected_variant": base.AWAY_VARIANT,
            },
            "frozen_protocol": {
                "current_preset": base.CURRENT_PRESET,
                "source_feedback_label": v1.FEEDBACK_A,
                "target_feedback_label": v1.FEEDBACK_B,
                "source_feedback_vector": v1.feedback_vector("off"),
                "target_feedback_vector": v1.feedback_vector("on"),
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
