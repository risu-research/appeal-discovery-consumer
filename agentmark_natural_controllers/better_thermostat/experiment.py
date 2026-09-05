from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import time
from types import MappingProxyType
from typing import Any

from homeassistant import config_entries, loader
from homeassistant.components import automation
from homeassistant.const import EVENT_CALL_SERVICE, __version__ as HA_VERSION
from homeassistant.core import CoreState, Event, HomeAssistant, ServiceCall, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import trigger as trigger_helper
from homeassistant.setup import async_setup_component

from agentmark.kernel import ReactiveKernel
from agentmark.semantics import step_replay_validity, workload_shift_tv
from agentmark_natural_controllers.action_identity import (
    HAActionIdentity,
    canonical_action_identity,
)


EXPECTED_BLUEPRINT_SHA256 = "16d52ce11dec44fa9ca533d15f3cec1eb9646d59bf6a455bd905af63cdf86443"
BLUEPRINT_REL = "agentmark/better_thermostat_lean.yaml"
CLIMATE_ENTITY = "climate.agentmark_thermostat"
PRESENCE_ENTITY = "input_boolean.agentmark_presence"
MOTION_ENTITY = "binary_sensor.agentmark_motion"
NIGHT_ENTITY = "input_boolean.agentmark_night"
ENABLE_ENTITY = "input_boolean.agentmark_enable"
CURRENT_PRESET = "sleep"
HOME_VARIANT = '{"preset_mode":"home"}'
AWAY_VARIANT = '{"preset_mode":"away"}'
TRIALS = 6


def now_ns() -> int:
    return time.perf_counter_ns()


def action_kernel() -> ReactiveKernel:
    return ReactiveKernel(
        {
            "initial_state": "decision",
            "feedback_alphabet": ["HOME", "AWAY"],
            "states": {
                "decision": {
                    "HOME": [
                        {
                            "p": 1,
                            "operation": "climate.set_preset_mode",
                            "target_class": "climate",
                            "variant": HOME_VARIANT,
                            "next_state": "done",
                        }
                    ],
                    "AWAY": [
                        {
                            "p": 1,
                            "operation": "climate.set_preset_mode",
                            "target_class": "climate",
                            "variant": AWAY_VARIANT,
                            "next_state": "done",
                        }
                    ],
                },
                "done": {
                    "HOME": [
                        {"p": 1, "operation": "STOP", "next_state": "done"}
                    ],
                    "AWAY": [
                        {"p": 1, "operation": "STOP", "next_state": "done"}
                    ],
                },
            },
        }
    )


def _verdict_to_json(verdict: Any) -> dict[str, Any]:
    return {
        "source_probability": float(verdict.source_probability),
        "target_probability": float(verdict.target_probability),
        "source_consistent": bool(verdict.source_consistent),
        "target_supports_recorded_event": bool(verdict.target_supports_recorded_event),
        "support_failure": bool(verdict.support_failure),
    }


def replay_support(identity: HAActionIdentity, target_feedback: str) -> dict[str, Any]:
    kernel = action_kernel()
    operation = step_replay_validity(
        kernel,
        state="decision",
        source_feedback="HOME",
        target_feedback=target_feedback,
        recorded_event=identity.operation,
        projection="operation",
    )
    action = step_replay_validity(
        kernel,
        state="decision",
        source_feedback="HOME",
        target_feedback=target_feedback,
        recorded_event=identity.projected_key(),
        projection="action",
    )
    return {
        "target_feedback": target_feedback,
        "operation": _verdict_to_json(operation),
        "action": _verdict_to_json(action),
    }


class ActionLab:
    def __init__(self, hass: HomeAssistant, climate_entity: str):
        self.hass = hass
        self.climate_entity = climate_entity
        self.events: list[dict[str, Any]] = []
        self._unsubs: list[Any] = []

    def install(self) -> None:
        @callback
        def on_call(event: Event) -> None:
            domain = str(event.data.get("domain"))
            service = str(event.data.get("service"))
            if domain not in {"climate", "number", "system_log"}:
                return
            service_data = dict(event.data.get("service_data") or {})
            identity = canonical_action_identity(domain, service, service_data)
            presence = self.hass.states.get(PRESENCE_ENTITY)
            climate = self.hass.states.get(self.climate_entity)
            self.events.append(
                {
                    "t_ns": now_ns(),
                    "domain": domain,
                    "service": service,
                    "service_data": service_data,
                    "operation": identity.operation,
                    "target_class": identity.target_class,
                    "variant": identity.variant,
                    "context_id": str(event.context.id),
                    "context_parent_id": (
                        None
                        if event.context.parent_id is None
                        else str(event.context.parent_id)
                    ),
                    "presence_state_at_issue": None if presence is None else presence.state,
                    "climate_preset_before_issue": (
                        None
                        if climate is None
                        else climate.attributes.get("preset_mode")
                    ),
                }
            )

        self._unsubs.append(self.hass.bus.async_listen(EVENT_CALL_SERVICE, on_call))

        async def set_preset_mode(call: ServiceCall) -> None:
            preset = str(call.data.get("preset_mode", "")).strip()
            entity_value = call.data.get("entity_id", self.climate_entity)
            if isinstance(entity_value, (list, tuple)):
                entities = [str(item) for item in entity_value]
            else:
                entities = [str(entity_value)]
            if self.climate_entity not in entities:
                raise AssertionError(
                    f"set_preset_mode target does not contain {self.climate_entity}: {entities}"
                )
            old = self.hass.states.get(self.climate_entity)
            attrs = {} if old is None else dict(old.attributes)
            attrs["preset_mode"] = preset
            attrs.setdefault("temperature", 20.0)
            state = "heat" if old is None else old.state
            self.hass.states.async_set(
                self.climate_entity,
                state,
                attrs,
                context=call.context,
            )

        async def number_noop(call: ServiceCall) -> None:
            return None

        async def log_noop(call: ServiceCall) -> None:
            return None

        self.hass.services.async_register("climate", "set_preset_mode", set_preset_mode)
        self.hass.services.async_register("number", "set_value", number_noop)
        self.hass.services.async_register("system_log", "write", log_noop)

    def close(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()


async def wait_for_consequential_call(lab: ActionLab, timeout_s: float = 2.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not lab.events:
        if time.monotonic() >= deadline:
            raise TimeoutError("timed out waiting for Better Thermostat service action")
        await asyncio.sleep(0.001)


async def _make_config_entry(hass: HomeAssistant) -> config_entries.ConfigEntry:
    entry = config_entries.ConfigEntry(
        data={},
        discovery_keys=MappingProxyType({}),
        domain="better_thermostat",
        minor_version=1,
        options={},
        source=config_entries.SOURCE_USER,
        subentries_data=None,
        title="AgentMark Better Thermostat",
        unique_id="agentmark-better-thermostat",
        version=1,
    )
    await hass.config_entries.async_add(entry)
    return entry


async def make_hass(
    *,
    blueprint_source: Path,
    native_automation: bool,
    initial_presence: str,
) -> tuple[HomeAssistant, ActionLab, tempfile.TemporaryDirectory[str], dict[str, Any]]:
    temp = tempfile.TemporaryDirectory(prefix="agentmark-natural-bt-")
    hass = HomeAssistant(temp.name)
    loader.async_setup(hass)
    hass.config_entries = config_entries.ConfigEntries(hass, {})
    await hass.config_entries.async_initialize()
    await trigger_helper.async_setup(hass)
    hass.set_state(CoreState.running)

    entry = await _make_config_entry(hass)
    await asyncio.gather(dr.async_load(hass), er.async_load(hass))
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("better_thermostat", "agentmark-device")},
        name="AgentMark Better Thermostat",
    )
    entity = entity_registry.async_get_or_create(
        "climate",
        "better_thermostat",
        "agentmark-climate",
        suggested_object_id="agentmark_thermostat",
        config_entry=entry,
        device_id=device.id,
        original_name="AgentMark Thermostat",
    )
    if entity.entity_id != CLIMATE_ENTITY:
        raise AssertionError(
            f"unexpected native climate entity id: {entity.entity_id} != {CLIMATE_ENTITY}"
        )

    hass.states.async_set(
        CLIMATE_ENTITY,
        "heat",
        {"preset_mode": CURRENT_PRESET, "temperature": 20.0},
    )
    hass.states.async_set(PRESENCE_ENTITY, initial_presence)
    hass.states.async_set(MOTION_ENTITY, "off")
    hass.states.async_set(NIGHT_ENTITY, "off")
    hass.states.async_set(ENABLE_ENTITY, "on")

    lab = ActionLab(hass, CLIMATE_ENTITY)
    lab.install()

    if native_automation:
        destination = (
            Path(temp.name)
            / "blueprints"
            / "automation"
            / "agentmark"
            / "better_thermostat_lean.yaml"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(blueprint_source, destination)
        ok = await async_setup_component(
            hass,
            automation.DOMAIN,
            {
                "automation": {
                    "use_blueprint": {
                        "path": BLUEPRINT_REL,
                        "input": {
                            "climate_device": device.id,
                            "presence_group": PRESENCE_ENTITY,
                            "motion_group": MOTION_ENTITY,
                            "night_mode_entity": NIGHT_ENTITY,
                            "enable_switch": ENABLE_ENTITY,
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

    registry_evidence = {
        "config_entry_id": entry.entry_id,
        "config_entry_domain": entry.domain,
        "device_id": device.id,
        "device_identifiers": sorted([list(item) for item in device.identifiers]),
        "entity_registry_id": entity.id,
        "entity_id": entity.entity_id,
        "entity_platform": entity.platform,
        "entity_device_id": entity.device_id,
        "native_device_entity_link": entity.device_id == device.id,
    }
    return hass, lab, temp, registry_evidence


async def cleanup_hass(
    hass: HomeAssistant,
    lab: ActionLab,
    temp: tempfile.TemporaryDirectory[str],
) -> None:
    lab.close()
    try:
        await hass.async_stop()
    finally:
        temp.cleanup()


def summarize(
    *,
    label: str,
    lab: ActionLab,
    registry: dict[str, Any],
    expected_feedback: str,
) -> dict[str, Any]:
    counts = Counter(event["operation"] for event in lab.events)
    climate_calls = [
        event
        for event in lab.events
        if event["operation"] == "climate.set_preset_mode"
    ]
    identity = None
    if len(climate_calls) == 1:
        event = climate_calls[0]
        identity = {
            "operation": event["operation"],
            "target_class": event["target_class"],
            "variant": event["variant"],
        }
    return {
        "label": label,
        "expected_feedback": expected_feedback,
        "registry": registry,
        "call_counts": dict(sorted(counts.items())),
        "climate_call_count": len(climate_calls),
        "identity": identity,
        "raw_call_events": lab.events,
    }


async def run_native(
    *,
    blueprint_source: Path,
    feedback: str,
    label: str,
) -> dict[str, Any]:
    if feedback == "HOME":
        initial_presence, final_presence = "off", "on"
    elif feedback == "AWAY":
        initial_presence, final_presence = "on", "off"
    else:
        raise ValueError(feedback)

    hass, lab, temp, registry = await make_hass(
        blueprint_source=blueprint_source,
        native_automation=True,
        initial_presence=initial_presence,
    )
    try:
        hass.states.async_set(PRESENCE_ENTITY, final_presence)
        await wait_for_consequential_call(lab)
        await hass.async_block_till_done()
        return summarize(
            label=label,
            lab=lab,
            registry=registry,
            expected_feedback=feedback,
        )
    finally:
        await cleanup_hass(hass, lab, temp)


async def run_replay(
    *,
    blueprint_source: Path,
    source_service_data: dict[str, Any],
    target_feedback: str,
    label: str,
) -> dict[str, Any]:
    presence = "on" if target_feedback == "HOME" else "off"
    hass, lab, temp, registry = await make_hass(
        blueprint_source=blueprint_source,
        native_automation=False,
        initial_presence=presence,
    )
    try:
        await hass.services.async_call(
            "climate",
            "set_preset_mode",
            dict(source_service_data),
            blocking=True,
        )
        await hass.async_block_till_done()
        row = summarize(
            label=label,
            lab=lab,
            registry=registry,
            expected_feedback=target_feedback,
        )
        climate_calls = [
            event
            for event in lab.events
            if event["operation"] == "climate.set_preset_mode"
        ]
        if len(climate_calls) != 1:
            raise AssertionError(f"{label}: replay must issue exactly one climate call")
        event = climate_calls[0]
        identity = HAActionIdentity(
            operation=str(event["operation"]),
            target_class=event.get("target_class"),
            variant=str(event["variant"]),
        )
        row["support"] = replay_support(identity, target_feedback)
        return row
    finally:
        await cleanup_hass(hass, lab, temp)


def exact_identity(row: dict[str, Any], variant: str) -> bool:
    return row.get("identity") == {
        "operation": "climate.set_preset_mode",
        "target_class": "climate",
        "variant": variant,
    }


def no_extra_actions(row: dict[str, Any]) -> bool:
    return row["call_counts"] == {"climate.set_preset_mode": 1}


def source_service_data(source: dict[str, Any]) -> dict[str, Any]:
    events = [
        event
        for event in source["raw_call_events"]
        if event["operation"] == "climate.set_preset_mode"
    ]
    if len(events) != 1:
        raise AssertionError("source must have one climate.set_preset_mode event")
    return dict(events[0]["service_data"])


async def experiment(args: argparse.Namespace) -> dict[str, Any]:
    blueprint_source = Path(args.blueprint)
    blueprint_sha = hashlib.sha256(blueprint_source.read_bytes()).hexdigest()
    if blueprint_sha != EXPECTED_BLUEPRINT_SHA256:
        raise AssertionError(
            f"external blueprint hash mismatch: {blueprint_sha} != {EXPECTED_BLUEPRINT_SHA256}"
        )

    source = await run_native(
        blueprint_source=blueprint_source,
        feedback="HOME",
        label="source_native_home",
    )
    recorded_data = source_service_data(source)

    target_native: list[dict[str, Any]] = []
    target_replay: list[dict[str, Any]] = []
    controls: list[dict[str, Any]] = []
    for trial in range(args.trials):
        target_native.append(
            await run_native(
                blueprint_source=blueprint_source,
                feedback="AWAY",
                label=f"target_native_away_t{trial}",
            )
        )
        target_replay.append(
            await run_replay(
                blueprint_source=blueprint_source,
                source_service_data=recorded_data,
                target_feedback="AWAY",
                label=f"target_replay_home_t{trial}",
            )
        )
        controls.append(
            {
                "native": await run_native(
                    blueprint_source=blueprint_source,
                    feedback="HOME",
                    label=f"control_native_home_t{trial}",
                ),
                "replay": await run_replay(
                    blueprint_source=blueprint_source,
                    source_service_data=recorded_data,
                    target_feedback="HOME",
                    label=f"control_replay_home_t{trial}",
                ),
            }
        )

    kernel = action_kernel()
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
        and no_extra_actions(source)
        and exact_identity(source, HOME_VARIANT)
        and source["registry"]["native_device_entity_link"]
        and source["registry"]["entity_id"] == CLIMATE_ENTITY
    )
    target_native_ok = all(
        row["climate_call_count"] == 1
        and no_extra_actions(row)
        and exact_identity(row, AWAY_VARIANT)
        and row["registry"]["native_device_entity_link"]
        for row in target_native
    )
    target_replay_ok = all(
        row["climate_call_count"] == 1
        and no_extra_actions(row)
        and exact_identity(row, HOME_VARIANT)
        and not row["support"]["operation"]["support_failure"]
        and row["support"]["operation"]["target_probability"] == 1.0
        and row["support"]["action"]["support_failure"]
        and row["support"]["action"]["target_probability"] == 0.0
        for row in target_replay
    )
    controls_ok = all(
        exact_identity(pair["native"], HOME_VARIANT)
        and exact_identity(pair["replay"], HOME_VARIANT)
        and no_extra_actions(pair["native"])
        and no_extra_actions(pair["replay"])
        and not pair["replay"]["support"]["operation"]["support_failure"]
        and not pair["replay"]["support"]["action"]["support_failure"]
        and pair["replay"]["support"]["action"]["target_probability"] == 1.0
        for pair in controls
    )

    gates = {
        "external_source_hash_exact": blueprint_sha == EXPECTED_BLUEPRINT_SHA256,
        "ha_version_exact": HA_VERSION == "2026.9.0",
        "source_home_exact": source_ok,
        "target_native_away_exact_all": target_native_ok,
        "target_replay_home_exact_all": target_replay_ok,
        "operation_projection_supports_recorded_action_all": all(
            not row["support"]["operation"]["support_failure"]
            for row in target_replay
        ),
        "action_projection_rejects_recorded_action_all": all(
            row["support"]["action"]["support_failure"]
            for row in target_replay
        ),
        "tv_operation_exact_zero": tv_operation == 0,
        "tv_action_exact_one": tv_action == 1,
        "native_registry_link_all": (
            source["registry"]["native_device_entity_link"]
            and all(row["registry"]["native_device_entity_link"] for row in target_native)
            and all(row["registry"]["native_device_entity_link"] for row in target_replay)
            and all(
                pair[mode]["registry"]["native_device_entity_link"]
                for pair in controls
                for mode in ("native", "replay")
            )
        ),
        "no_feedback_shift_control_all": controls_ok,
    }
    gates["promoted"] = all(gates.values())

    result = {
        "schema": "agentmark.natural_controller.better_thermostat_action_identity.v1",
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
        "frozen_adapter": {
            "operation": "domain.service",
            "target_class": "resolved target entity domain class",
            "variant": "canonical JSON of rendered top-level non-target service data",
            "home_variant": HOME_VARIANT,
            "away_variant": AWAY_VARIANT,
        },
        "frozen_protocol": {
            "current_preset": CURRENT_PRESET,
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
    return result


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--blueprint", required=True)
    p.add_argument("--replica", type=int, required=True)
    p.add_argument("--trials", type=int, default=TRIALS)
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
