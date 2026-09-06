from __future__ import annotations

"""Runtime realization of ReplayMark's frozen N2 consequence-depth witnesses."""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import time
from typing import Any

from homeassistant.const import EVENT_CALL_SERVICE, EVENT_STATE_CHANGED, __version__ as HA_VERSION
from homeassistant.core import Event, callback

from agentmark_natural_controllers.action_identity import canonical_action_identity
from agentmark_natural_controllers.better_thermostat import experiment_persisted_ownership as base
from agentmark_natural_controllers.better_thermostat import n2b_experiment as n2b

SCHEMA = "replaymark.better_thermostat.horizon_runtime.v1"
DEPTH1_EXPECTED = {"off": "home", "on": "comfort"}
DEPTH2_EXPECTED = {"off": "home", "on": "comfort"}


def now_ns() -> int:
    return time.perf_counter_ns()


def current_snapshot(hass: Any, *, label: str) -> dict[str, Any]:
    def state(entity_id: str) -> Any:
        obj = hass.states.get(entity_id)
        return None if obj is None else obj.state

    climate = hass.states.get(base.CLIMATE_ENTITY)
    return {
        "label": label,
        "t_ns": now_ns(),
        "presence": state(base.PRESENCE_ENTITY),
        "motion": state(base.MOTION_ENTITY),
        "night": state(base.NIGHT_ENTITY),
        "enable": state(base.ENABLE_ENTITY),
        "climate_state": None if climate is None else climate.state,
        "climate_preset": None if climate is None else climate.attributes.get("preset_mode"),
    }


class HorizonObserver:
    """Passive event observer for trigger ordering and consequential service issue."""

    def __init__(self, hass: Any):
        self.hass = hass
        self.state_events: list[dict[str, Any]] = []
        self.service_events: list[dict[str, Any]] = []
        self._unsubs: list[Any] = []

    def feedback(self) -> dict[str, Any]:
        return {
            "presence": self.hass.states.get(base.PRESENCE_ENTITY).state,
            "motion": self.hass.states.get(base.MOTION_ENTITY).state,
            "night": self.hass.states.get(base.NIGHT_ENTITY).state,
        }

    def preset(self) -> Any:
        climate = self.hass.states.get(base.CLIMATE_ENTITY)
        return None if climate is None else climate.attributes.get("preset_mode")

    def install(self) -> None:
        relevant = {
            base.PRESENCE_ENTITY,
            base.MOTION_ENTITY,
            base.NIGHT_ENTITY,
            base.CLIMATE_ENTITY,
        }

        @callback
        def on_state(event: Event) -> None:
            entity_id = str(event.data.get("entity_id"))
            if entity_id not in relevant:
                return
            old_state = event.data.get("old_state")
            new_state = event.data.get("new_state")
            self.state_events.append({
                "t_ns": now_ns(),
                "entity_id": entity_id,
                "old_state": None if old_state is None else old_state.state,
                "new_state": None if new_state is None else new_state.state,
                "old_preset": None if old_state is None else old_state.attributes.get("preset_mode"),
                "new_preset": None if new_state is None else new_state.attributes.get("preset_mode"),
                "feedback_after_event": self.feedback(),
                "context_id": None if new_state is None else str(new_state.context.id),
                "context_parent_id": (
                    None
                    if new_state is None or new_state.context.parent_id is None
                    else str(new_state.context.parent_id)
                ),
            })

        @callback
        def on_service(event: Event) -> None:
            domain = str(event.data.get("domain"))
            service = str(event.data.get("service"))
            if (domain, service) != ("climate", "set_preset_mode"):
                return
            service_data = dict(event.data.get("service_data") or {})
            ident = canonical_action_identity(domain, service, service_data)
            self.service_events.append({
                "t_ns": now_ns(),
                "domain": domain,
                "service": service,
                "service_data": service_data,
                "operation": ident.operation,
                "target_class": ident.target_class,
                "variant": ident.variant,
                "feedback_at_issue": self.feedback(),
                "climate_preset_before_issue": self.preset(),
                "context_id": str(event.context.id),
                "context_parent_id": None if event.context.parent_id is None else str(event.context.parent_id),
            })

        self._unsubs.append(self.hass.bus.async_listen(EVENT_STATE_CHANGED, on_state))
        self._unsubs.append(self.hass.bus.async_listen(EVENT_CALL_SERVICE, on_service))

    def close(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()


async def wait_for_service_count(observer: HorizonObserver, count: int, timeout_s: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while len(observer.service_events) < count:
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError(f"timed out waiting for {count} climate service events")
        await asyncio.sleep(0.001)


async def fresh_native(
    *,
    blueprint_source: Path,
    qualification: dict[str, Any],
    presence: str,
    motion: str,
    night: str,
) -> tuple[Any, base.ActionLab, Any, dict[str, Any], HorizonObserver]:
    hass, lab, temp, registry = await base.make_hass(
        blueprint_source=blueprint_source,
        qualification=qualification,
        native_automation=False,
        initial_presence=presence,
    )
    hass.states.async_set(base.MOTION_ENTITY, motion)
    hass.states.async_set(base.NIGHT_ENTITY, night)

    observer = HorizonObserver(hass)
    observer.install()
    await n2b.install_native_automation(hass, temp, registry, blueprint_source)
    await hass.async_block_till_done()
    if observer.service_events or n2b.consequential_events(lab):
        raise AssertionError("consequential action occurred during seeding/automation installation")
    return hass, lab, temp, registry, observer


def service_presets(observer: HorizonObserver) -> list[str]:
    return [str(e["service_data"].get("preset_mode")) for e in observer.service_events]


async def run_depth1(
    *, blueprint_source: Path, qualification: dict[str, Any], motion: str, trial: int
) -> dict[str, Any]:
    hass, lab, temp, registry, observer = await fresh_native(
        blueprint_source=blueprint_source,
        qualification=qualification,
        presence="on",
        motion=motion,
        night="off",
    )
    try:
        initial = current_snapshot(hass, label="depth1_initial")
        if initial["climate_preset"] != "sleep":
            raise AssertionError(initial)

        hass.states.async_set(base.PRESENCE_ENTITY, "off")
        await wait_for_service_count(observer, 1)
        await hass.async_block_till_done()
        after_current = current_snapshot(hass, label="depth1_after_current_decision")

        hass.states.async_set(base.PRESENCE_ENTITY, "on")
        await wait_for_service_count(observer, 2)
        await hass.async_block_till_done()
        after_continuation = current_snapshot(hass, label="depth1_after_presence_on")

        expected = ["away", DEPTH1_EXPECTED[motion]]
        row = {
            "depth": 1,
            "trial": trial,
            "motion": motion,
            "expected_output_sequence": expected,
            "observed_service_presets": service_presets(observer),
            "initial_snapshot": initial,
            "after_current_snapshot": after_current,
            "after_continuation_snapshot": after_continuation,
            "state_events": list(observer.state_events),
            "service_events": list(observer.service_events),
            "raw_action_lab_events": list(lab.events),
            "registry": registry,
        }
        row["producer_pass"] = (
            row["observed_service_presets"] == expected
            and after_current["presence"] == "off"
            and after_current["motion"] == motion
            and after_current["night"] == "off"
            and after_current["climate_preset"] == "away"
            and after_continuation["presence"] == "on"
            and after_continuation["motion"] == motion
            and after_continuation["night"] == "off"
            and after_continuation["climate_preset"] == DEPTH1_EXPECTED[motion]
            and len(observer.service_events) == 2
            and base.ownership_ok({"registry": registry})
        )
        return row
    finally:
        observer.close()
        await base.cleanup_hass(hass, lab, temp)


async def run_depth2(
    *, blueprint_source: Path, qualification: dict[str, Any], motion: str, trial: int
) -> dict[str, Any]:
    hass, lab, temp, registry, observer = await fresh_native(
        blueprint_source=blueprint_source,
        qualification=qualification,
        presence="off",
        motion=motion,
        night="on",
    )
    try:
        initial = current_snapshot(hass, label="depth2_initial")
        if initial["climate_preset"] != "sleep":
            raise AssertionError(initial)

        hass.states.async_set(base.PRESENCE_ENTITY, "on")
        await hass.async_block_till_done()
        await asyncio.sleep(0)
        await hass.async_block_till_done()
        after_step1 = current_snapshot(hass, label="depth2_after_presence_on")
        service_count_after_step1 = len(observer.service_events)

        hass.states.async_set(base.NIGHT_ENTITY, "off")
        await wait_for_service_count(observer, 1)
        await hass.async_block_till_done()
        after_step2 = current_snapshot(hass, label="depth2_after_night_off")

        expected = ["NO_ACTION", DEPTH2_EXPECTED[motion]]
        observed = ["NO_ACTION", service_presets(observer)[0]] if observer.service_events else ["NO_ACTION"]
        row = {
            "depth": 2,
            "trial": trial,
            "motion": motion,
            "expected_output_sequence": expected,
            "observed_output_sequence": observed,
            "service_count_after_step1": service_count_after_step1,
            "initial_snapshot": initial,
            "after_step1_snapshot": after_step1,
            "after_step2_snapshot": after_step2,
            "state_events": list(observer.state_events),
            "service_events": list(observer.service_events),
            "raw_action_lab_events": list(lab.events),
            "registry": registry,
        }
        row["producer_pass"] = (
            service_count_after_step1 == 0
            and observed == expected
            and after_step1["presence"] == "on"
            and after_step1["motion"] == motion
            and after_step1["night"] == "on"
            and after_step1["climate_preset"] == "sleep"
            and after_step2["presence"] == "on"
            and after_step2["motion"] == motion
            and after_step2["night"] == "off"
            and after_step2["climate_preset"] == DEPTH2_EXPECTED[motion]
            and len(observer.service_events) == 1
            and base.ownership_ok({"registry": registry})
        )
        return row
    finally:
        observer.close()
        await base.cleanup_hass(hass, lab, temp)


def relation_check(row: dict[str, Any]) -> bool:
    states = row["state_events"]
    services = row["service_events"]

    def transitions(entity: str, old: str, new: str) -> list[dict[str, Any]]:
        return [
            e for e in states
            if e["entity_id"] == entity and e["old_state"] == old and e["new_state"] == new
        ]

    if row["depth"] == 1:
        p_off = transitions(base.PRESENCE_ENTITY, "on", "off")
        p_on = transitions(base.PRESENCE_ENTITY, "off", "on")
        return (
            len(p_off) == 1 and len(p_on) == 1 and len(services) == 2
            and p_off[0]["t_ns"] <= services[0]["t_ns"] < p_on[0]["t_ns"] <= services[1]["t_ns"]
        )
    p_on = transitions(base.PRESENCE_ENTITY, "off", "on")
    n_off = transitions(base.NIGHT_ENTITY, "on", "off")
    return (
        len(p_on) == 1 and len(n_off) == 1 and len(services) == 1
        and p_on[0]["t_ns"] < row["after_step1_snapshot"]["t_ns"] < n_off[0]["t_ns"] <= services[0]["t_ns"]
    )


async def experiment(args: argparse.Namespace) -> dict[str, Any]:
    blueprint_source = Path(args.blueprint)
    component_source = Path(args.ownership_component)
    blueprint_sha = hashlib.sha256(blueprint_source.read_bytes()).hexdigest()
    if blueprint_sha != base.EXPECTED_BLUEPRINT_SHA256:
        raise AssertionError(
            f"external blueprint hash mismatch: {blueprint_sha} != {base.EXPECTED_BLUEPRINT_SHA256}"
        )

    qualification, qualification_temp, qualification_hass = await base.qualify_upstream_loader(component_source)
    try:
        depth1: list[dict[str, Any]] = []
        depth2: list[dict[str, Any]] = []
        for trial in range(args.trials):
            order = ["off", "on"] if (trial + args.replica) % 2 == 0 else ["on", "off"]
            for motion in order:
                depth1.append(await run_depth1(
                    blueprint_source=blueprint_source,
                    qualification=qualification,
                    motion=motion,
                    trial=trial,
                ))
            for motion in reversed(order):
                depth2.append(await run_depth2(
                    blueprint_source=blueprint_source,
                    qualification=qualification,
                    motion=motion,
                    trial=trial,
                ))

        all_rows = depth1 + depth2
        tree_hashes = {row["registry"]["upstream_component_tree_sha256"] for row in all_rows}
        groups = [
            [r for r in depth1 if r["motion"] == "off"],
            [r for r in depth1 if r["motion"] == "on"],
            [r for r in depth2 if r["motion"] == "off"],
            [r for r in depth2 if r["motion"] == "on"],
        ]
        gates = {
            "ha_version_exact": HA_VERSION == "2026.9.0",
            "external_source_hash_exact": blueprint_sha == base.EXPECTED_BLUEPRINT_SHA256,
            "upstream_loader_qualified_before_outcome": qualification["qualification_before_outcome"] is True,
            "upstream_loader_domain_exact": qualification["ha_loader_resolved_domain"] == base.BETTER_THERMOSTAT_DOMAIN,
            "upstream_loader_version_exact": qualification["ha_loader_resolved_version"] == base.BETTER_THERMOSTAT_VERSION,
            "integration_internal_setup_not_invoked": qualification["integration_setup_invoked"] is False,
            "upstream_component_tree_stable": len(tree_hashes) == 1,
            "rows_per_condition_exact": all(len(group) == args.trials for group in groups),
            "depth1_current_away_all": all(r["observed_service_presets"][0] == "away" for r in depth1),
            "depth1_shortest_witness_realized_all": all(
                r["observed_service_presets"] == ["away", DEPTH1_EXPECTED[r["motion"]]] for r in depth1
            ),
            "depth2_first_step_no_action_all": all(r["service_count_after_step1"] == 0 for r in depth2),
            "depth2_second_step_separates_all": all(
                r["observed_output_sequence"] == ["NO_ACTION", DEPTH2_EXPECTED[r["motion"]]] for r in depth2
            ),
            "no_extra_consequential_actions_all": all(
                len(r["service_events"]) == (2 if r["depth"] == 1 else 1) for r in all_rows
            ),
            "event_ordering_exact_all": all(relation_check(r) for r in all_rows),
            "ownership_boundary_exact_all": all(base.ownership_ok(r) for r in all_rows),
            "producer_rows_pass_all": all(r["producer_pass"] for r in all_rows),
        }
        gates["promoted"] = all(gates.values())
        return {
            "schema": SCHEMA,
            "replica": args.replica,
            "decision": "PROMOTED" if gates["promoted"] else "NOT_PROMOTED",
            "environment": {"home_assistant_core_version": HA_VERSION},
            "external_controller": {
                "repository": "n3roGit/MyHomeAssistantMods",
                "commit": "57d56f076c05ccaa9553e6bd4b673b6d43a8cf7f",
                "path": "automation/BetterThermostatControl/BetterThermostat_RoomHeatControl_Lean.yaml",
                "sha256": blueprint_sha,
                "source_edited": False,
            },
            "ownership_component": qualification,
            "frozen_predictions": {
                "depth1": {
                    "current": ["away", "away"],
                    "suffix": ["presence_toggle"],
                    "separation": {"motion_off": "home", "motion_on": "comfort"},
                },
                "depth2": {
                    "current": ["NO_ACTION", "NO_ACTION"],
                    "suffix": ["presence_toggle", "night_toggle"],
                    "step1": ["NO_ACTION", "NO_ACTION"],
                    "separation": {"motion_off": "home", "motion_on": "comfort"},
                },
            },
            "trials_per_history": args.trials,
            "depth1_rows": depth1,
            "depth2_rows": depth2,
            "promotion_gates": gates,
        }
    finally:
        await qualification_hass.async_stop()
        qualification_temp.cleanup()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--blueprint", required=True)
    p.add_argument("--ownership-component", required=True)
    p.add_argument("--replica", type=int, required=True)
    p.add_argument("--trials", type=int, default=6)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    if args.trials != 6:
        raise ValueError("frozen protocol requires exactly 6 trials per history")
    report = asyncio.run(experiment(args))
    Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "decision": report["decision"],
        "replica": report["replica"],
        "promotion_gates": report["promotion_gates"],
    }, indent=2, sort_keys=True))
    if report["decision"] != "PROMOTED":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
