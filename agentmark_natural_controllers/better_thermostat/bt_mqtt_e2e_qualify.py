#!/usr/bin/env python3
"""Phase-B real-stack qualification for ReplayMark BT→MQTT capstone.

Runs inside the pinned Home Assistant image and talks to a real Mosquitto broker.
No ReplayMark action→MQTT bridge exists: the only measured publication path is
external automation/manual historical climate action → real Better Thermostat →
real child MQTT Climate service → Home Assistant MQTT entity publication.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import shutil
import tempfile
import time
from types import MappingProxyType
from typing import Any

from homeassistant import bootstrap, config_entries, loader
from homeassistant.components import automation, mqtt
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, EVENT_STATE_CHANGED
from homeassistant.core import CoreState, Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import recorder as recorder_helper
from homeassistant.setup import async_setup_component

HA_VERSION_EXPECTED = "2026.9.0"
BT_DOMAIN = "better_thermostat"
BLUEPRINT_REL = "agentmark/better_thermostat_lean.yaml"
TEMP_SENSOR = "sensor.replaymark_room_temperature"
PRESENCE = "binary_sensor.replaymark_presence"
MOTION = "binary_sensor.replaymark_motion"
NIGHT = "input_boolean.replaymark_night"
ENABLE = "input_boolean.replaymark_enable"
EVENTS = ("night_toggle", "motion_toggle", "motion_toggle", "night_toggle")
TARGET_ACTIONS = ("home", "comfort", "home", "sleep")
REPLAY_ACTIONS = ("away", None, None, "sleep")
TARGET_TEMPS = {"away": 16.0, "home": 20.0, "comfort": 21.0, "sleep": 18.0}
SCHEMA = "replaymark.bt_mqtt_e2e.qualification.v1"


def config_entry(*, domain: str, title: str, data: dict[str, Any], version: int, minor_version: int = 1, unique_id: str | None = None):
    return config_entries.ConfigEntry(
        data=data,
        discovery_keys=MappingProxyType({}),
        disabled_by=None,
        domain=domain,
        minor_version=minor_version,
        options={},
        source=config_entries.SOURCE_USER,
        subentries_data=None,
        title=title,
        unique_id=unique_id,
        version=version,
    )


async def wait_until(predicate, *, timeout: float, label: str):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        value = predicate()
        if value:
            return value
        await asyncio.sleep(0.05)
    value = predicate()
    if value:
        return value
    raise TimeoutError(label)


async def setup_hass(*, config_dir: Path, bt_source: Path, broker: str, namespace: str):
    custom_dst = config_dir / "custom_components" / BT_DOMAIN
    custom_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(bt_source, custom_dst)

    # Use the pinned Home Assistant release's own bootstrap path rather than a
    # hand-assembled partial HomeAssistant object. This initializes auth,
    # registries, config entries, triggers, storage, and core configuration via
    # the same core machinery that normal HA startup uses, while still keeping
    # the experiment's integration set minimal and deterministic.
    # MQTT setup in pinned HA reloads configuration.yaml through the normal
    # configuration loader. Materialize the minimal on-disk config expected by
    # a real HA instance; this contains no experiment/controller semantics.
    (config_dir / "configuration.yaml").write_text("{}\n")
    hass = HomeAssistant(str(config_dir))
    loader.async_setup(hass)
    if await bootstrap.async_from_config_dict({}, hass) is None:
        raise RuntimeError("Home Assistant core bootstrap returned false")

    # Production HA bootstrap pre-initializes recorder before setting up the
    # recorder integration whenever recorder is in the startup domain set.
    # The minimal core bootstrap above intentionally omitted recorder, so
    # restore that exact core precondition before qualifying BT's hard deps.
    recorder_helper.async_initialize_recorder(hass)

    # Qualify Better Thermostat's manifest-declared hard dependencies one by
    # one through HA's own setup path. This makes a dependency failure explicit
    # rather than collapsing it into a generic BT component setup failure.
    for dependency in ("climate", "recorder"):
        if not await async_setup_component(hass, dependency, {}):
            raise RuntimeError(
                f"Better Thermostat hard dependency setup failed: {dependency}"
            )
        if dependency not in hass.config.components:
            raise RuntimeError(
                f"Better Thermostat hard dependency missing after setup: {dependency}"
            )

    # With the hard dependencies established, qualify the untouched pinned BT
    # top-level component separately before any BT config entry exists.
    if not await async_setup_component(hass, BT_DOMAIN, {}):
        raise RuntimeError("Better Thermostat top-level component setup failed")
    if BT_DOMAIN not in hass.config.components:
        raise RuntimeError("Better Thermostat top-level component missing after setup")

    hass.set_state(CoreState.running)

    # Actual MQTT integration connected to the external Mosquitto process.
    mqtt_entry = config_entry(
        domain=mqtt.DOMAIN,
        title="ReplayMark MQTT",
        data={mqtt.CONF_BROKER: broker, "port": 1883},
        version=mqtt.CONFIG_ENTRY_VERSION,
        minor_version=mqtt.CONFIG_ENTRY_MINOR_VERSION,
        unique_id=f"replaymark-mqtt-{namespace}",
    )
    # HA 2026.9 ConfigEntries.async_add() is itself add+setup. Do not perform
    # a second setup call; require the normal lifecycle to reach LOADED.
    await hass.config_entries.async_add(mqtt_entry)
    if mqtt_entry.state is not config_entries.ConfigEntryState.LOADED:
        raise RuntimeError(
            f"MQTT config entry did not load: state={mqtt_entry.state.value} "
            f"reason={getattr(mqtt_entry, 'reason', None)!r}"
        )
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()

    # Real MQTT Climate entity via official MQTT discovery. Only the temperature
    # command topic is measured downstream. QoS 1 is part of the entity config.
    discovery_topic = f"homeassistant/climate/{namespace}_trv/config"
    temp_topic = f"replaymark/e2e/{namespace}/temperature/set"
    mode_topic = f"replaymark/e2e/{namespace}/mode/set"
    unique_id = f"replaymark_{namespace}_mqtt_trv"
    discovery = {
        "name": f"ReplayMark {namespace} MQTT TRV",
        "unique_id": unique_id,
        "temperature_command_topic": temp_topic,
        "mode_command_topic": mode_topic,
        "modes": ["off", "heat"],
        "min_temp": 5.0,
        "max_temp": 30.0,
        "temp_step": 0.5,
        "qos": 1,
        "retain": False,
        "optimistic": True,
    }
    # Retain only this setup-time discovery record. HA 2026.9 installs its
    # discovery subscriptions asynchronously; broker retention removes the
    # subscribe-before-publish race without altering the measured command topic.
    await mqtt.async_publish(hass, discovery_topic, json.dumps(discovery, sort_keys=True), 1, True)
    await hass.async_block_till_done()

    entity_registry = er.async_get(hass)
    child_entity = await wait_until(
        lambda: entity_registry.async_get_entity_id("climate", mqtt.DOMAIN, unique_id),
        timeout=15.0,
        label="MQTT Climate entity did not appear",
    )
    await wait_until(
        lambda: hass.states.get(child_entity), timeout=10.0, label="MQTT Climate state missing"
    )

    # Seed critical room sensor and feedback before Better Thermostat startup.
    hass.states.async_set(TEMP_SENSOR, "19.5", {"unit_of_measurement": "°C"})
    hass.states.async_set(PRESENCE, "on")
    hass.states.async_set(MOTION, "off")
    hass.states.async_set(NIGHT, "on")
    hass.states.async_set(ENABLE, "on")

    bt_data = {
        "name": f"ReplayMark {namespace} Better Thermostat",
        "thermostat": [
            {
                "trv": child_entity,
                "integration": "mqtt",
                "model": "MQTT",
                "advanced": {
                    "calibration": "target_temp_based",
                    "calibration_mode": "default",
                    "no_off_system_mode": False,
                },
            }
        ],
        "temperature_sensor": TEMP_SENSOR,
        "model": "MQTT",
        "target_temp_step": "0.5",
        "tolerance": 0.3,
        "off_temperature": 5,
    }
    bt_entry = config_entry(
        domain=BT_DOMAIN,
        title=f"ReplayMark {namespace} Better Thermostat",
        data=bt_data,
        version=18,
        minor_version=1,
        unique_id=f"replaymark-bt-{namespace}",
    )
    await hass.config_entries.async_add(bt_entry)
    if bt_entry.state is not config_entries.ConfigEntryState.LOADED:
        raise RuntimeError(
            f"Better Thermostat config entry did not load: state={bt_entry.state.value} "
            f"reason={getattr(bt_entry, 'reason', None)!r}"
        )
    await hass.async_block_till_done()

    bt = await wait_until(
        lambda: (hass.data.get(BT_DOMAIN, {}).get(bt_entry.entry_id, {}) or {}).get("climate"),
        timeout=20.0,
        label="Better Thermostat climate object missing",
    )
    await wait_until(
        lambda: (not getattr(bt, "startup_running", True))
        and getattr(bt, "_async_unsub_state_changed", None) is not None,
        timeout=60.0,
        label="Better Thermostat startup did not settle",
    )
    bt_entity = str(bt.entity_id)
    bt_reg = entity_registry.async_get(bt_entity)
    if bt_reg is None or bt_reg.device_id is None:
        raise RuntimeError("Better Thermostat registry/device ownership missing")

    child_reg = entity_registry.async_get(child_entity)
    if child_reg is None:
        raise RuntimeError("MQTT child registry entry missing")

    trv_obj = bt.real_trvs[child_entity]
    adapter_name = getattr(getattr(trv_obj, "adapter", None), "__name__", None)

    return {
        "hass": hass,
        "mqtt_entry": mqtt_entry,
        "bt_entry": bt_entry,
        "bt": bt,
        "bt_entity": bt_entity,
        "bt_device_id": bt_reg.device_id,
        "child_entity": child_entity,
        "child_platform": child_reg.platform,
        "temp_topic": temp_topic,
        "mode_topic": mode_topic,
        "adapter_name": adapter_name,
        "discovery_topic": discovery_topic,
    }


class Observer:
    def __init__(self, hass: HomeAssistant, bt_entity: str, child_entity: str):
        self.hass = hass
        self.bt_entity = bt_entity
        self.child_entity = child_entity
        self.service_events: list[dict[str, Any]] = []
        self.state_events: list[dict[str, Any]] = []
        self._unsubs = []

    def install(self):
        @callback
        def on_service(event: Event):
            domain = str(event.data.get("domain"))
            service = str(event.data.get("service"))
            data = dict(event.data.get("service_data") or {})
            if domain != "climate" or service not in {"set_preset_mode", "set_temperature", "set_hvac_mode"}:
                return
            raw = data.get("entity_id")
            targets = [raw] if isinstance(raw, str) else list(raw or [])
            self.service_events.append({
                "t_ns": time.perf_counter_ns(),
                "domain": domain,
                "service": service,
                "targets": [str(x) for x in targets],
                "service_data": data,
                "context_id": str(event.context.id),
                "context_parent_id": None if event.context.parent_id is None else str(event.context.parent_id),
            })

        @callback
        def on_state(event: Event):
            entity_id = str(event.data.get("entity_id"))
            if entity_id not in {self.bt_entity, self.child_entity, PRESENCE, MOTION, NIGHT}:
                return
            old = event.data.get("old_state")
            new = event.data.get("new_state")
            self.state_events.append({
                "t_ns": time.perf_counter_ns(),
                "entity_id": entity_id,
                "old_state": None if old is None else old.state,
                "new_state": None if new is None else new.state,
                "old_preset": None if old is None else old.attributes.get("preset_mode"),
                "new_preset": None if new is None else new.attributes.get("preset_mode"),
                "old_temperature": None if old is None else old.attributes.get("temperature"),
                "new_temperature": None if new is None else new.attributes.get("temperature"),
            })

        from homeassistant.const import EVENT_CALL_SERVICE
        self._unsubs.append(self.hass.bus.async_listen(EVENT_CALL_SERVICE, on_service))
        self._unsubs.append(self.hass.bus.async_listen(EVENT_STATE_CHANGED, on_state))

    def clear(self):
        self.service_events.clear()
        self.state_events.clear()

    def close(self):
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()


def bt_preset(hass: HomeAssistant, bt_entity: str):
    state = hass.states.get(bt_entity)
    return None if state is None else state.attributes.get("preset_mode")


def child_temperature(hass: HomeAssistant, child: str):
    state = hass.states.get(child)
    return None if state is None else state.attributes.get("temperature")


async def call_preset(hass: HomeAssistant, bt_entity: str, preset: str):
    await hass.services.async_call(
        "climate", "set_preset_mode", {"entity_id": bt_entity, "preset_mode": preset}, blocking=True
    )


async def wait_stable_preset(hass: HomeAssistant, bt_entity: str, bt: Any, preset: str):
    """Wait for BT's semantic preset state and its queued control cycle only.

    The producer deliberately does not require a child temperature write here:
    whether BT emits such a write is the Phase-B scientific outcome and is
    adjudicated independently from the raw service/MQTT evidence.
    """
    await wait_until(
        lambda: bt_preset(hass, bt_entity) == preset,
        timeout=10.0,
        label=f"BT preset did not become {preset}",
    )
    await asyncio.wait_for(bt.control_queue_task.join(), timeout=20.0)
    await hass.async_block_till_done()


async def install_external_automation(hass: HomeAssistant, config_dir: Path, blueprint: Path, bt_device_id: str):
    """Install the frozen blueprint through Home Assistant's native reload path.

    Core bootstrap has already loaded the automation component, so a second
    async_setup_component call would return successfully without processing new
    automation configuration. Persist the frozen blueprint instance into the
    live HA config and use the registered automation.reload service, which
    re-reads and validates configuration.yaml before materializing entities.
    """
    destination = config_dir / "blueprints" / "automation" / "agentmark" / "better_thermostat_lean.yaml"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(blueprint, destination)
    config = {
        "automation": {
            "use_blueprint": {
                "path": BLUEPRINT_REL,
                "input": {
                    "climate_device": bt_device_id,
                    "presence_group": PRESENCE,
                    "motion_group": MOTION,
                    "night_mode_entity": NIGHT,
                    "enable_switch": ENABLE,
                    "writeback_enable": False,
                    "writeback_bounds_enable": False,
                    "boost_entity": "",
                    "eco_entity": "",
                    "activity_entity": "",
                },
            }
        }
    }
    (config_dir / "configuration.yaml").write_text(
        json.dumps(config, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    await hass.services.async_call(automation.DOMAIN, "reload", {}, blocking=True)
    await hass.async_block_till_done()
    entities = automation.automations_with_blueprint(hass, BLUEPRINT_REL)
    if len(entities) != 1:
        raise RuntimeError(
            "official automation.reload did not materialize exactly one frozen "
            f"blueprint automation: {entities!r}"
        )
    entity_id = entities[0]
    state = hass.states.get(entity_id)
    if state is None or state.state != "on":
        raise RuntimeError(
            f"frozen blueprint automation not enabled after reload: {entity_id} "
            f"state={None if state is None else state.state!r}"
        )
    return entity_id


async def apply_event(hass: HomeAssistant, event: str):
    entity = {"night_toggle": NIGHT, "motion_toggle": MOTION, "presence_toggle": PRESENCE}[event]
    old = hass.states.get(entity)
    if old is None:
        raise RuntimeError(f"missing feedback entity {entity}")
    current = str(old.state)
    if current not in {"on", "off"}:
        raise RuntimeError(f"unexpected feedback state {entity}={current}")
    hass.states.async_set(entity, "off" if current == "on" else "on")


async def execute(mode: str, *, blueprint: Path, bt_source: Path, broker: str, namespace: str, result_dir: Path):
    temp = tempfile.TemporaryDirectory(prefix=f"replaymark-bt-mqtt-{mode}-")
    config_dir = Path(temp.name)
    stack = await setup_hass(config_dir=config_dir, bt_source=bt_source, broker=broker, namespace=namespace)
    hass: HomeAssistant = stack["hass"]
    bt = stack["bt"]
    observer = Observer(hass, stack["bt_entity"], stack["child_entity"])
    observer.install()

    # Establish only the selector-defined quiescent controller state outside
    # measurement. Child-command propagation is not a setup precondition; it is
    # the outcome Phase B exists to measure.
    await call_preset(hass, stack["bt_entity"], "sleep")
    await wait_stable_preset(hass, stack["bt_entity"], bt, "sleep")

    automation_entity = None
    if mode == "target-native":
        automation_entity = await install_external_automation(hass, config_dir, blueprint, stack["bt_device_id"])
        if bt_preset(hass, stack["bt_entity"]) != "sleep":
            raise RuntimeError("automation install disturbed initial preset")

    observer.clear()
    ready = result_dir / "READY"
    start = result_dir / "START"
    ready.write_text(json.dumps({"temp_topic": stack["temp_topic"], "mode": mode}) + "\n")
    await wait_until(start.exists, timeout=30.0, label="START handshake not received")
    measurement_start_ns = time.perf_counter_ns()

    expected_presets = TARGET_ACTIONS if mode == "target-native" else REPLAY_ACTIONS
    for event, historical in zip(EVENTS, expected_presets):
        await apply_event(hass, event)
        if mode == "replay" and historical is not None:
            await call_preset(hass, stack["bt_entity"], historical)
        if historical is not None:
            # Wait for the semantic controller action and the untouched BT
            # control cycle to finish, but never require a successful child
            # write. The independent validator owns the 1:1/0:0 verdict.
            await wait_stable_preset(hass, stack["bt_entity"], bt, historical)
        else:
            # Historical NO_ACTION: give any unintended asynchronous activity a
            # bounded opportunity to become visible in the raw observer stream.
            await asyncio.sleep(0.5)
            await hass.async_block_till_done()

    await asyncio.sleep(0.5)
    await hass.async_block_till_done()
    measurement_end_ns = time.perf_counter_ns()

    bt_calls = [
        e for e in observer.service_events
        if e["service"] == "set_preset_mode" and stack["bt_entity"] in e["targets"]
    ]
    temp_calls = [
        e for e in observer.service_events
        if e["service"] == "set_temperature" and stack["child_entity"] in e["targets"]
    ]
    mode_calls = [
        e for e in observer.service_events
        if e["service"] == "set_hvac_mode" and stack["child_entity"] in e["targets"]
    ]

    result = {
        "schema": SCHEMA,
        "mode": mode,
        "namespace": namespace,
        "authorities": {
            "ha_version": HA_VERSION_EXPECTED,
            "better_thermostat_commit": "b86561f61e5ba1259fc63e590f4847e9ac743d7f",
            "external_controller_commit": "57d56f076c05ccaa9553e6bd4b673b6d43a8cf7f",
            "protocol_freeze": "851960e59aa3a68fb90ef199f1dbcfefe5fcd3c0",
            "selector_result_sha256": "07213a0d56e5f2d32b9eb3c2b2e6b20cb0aab31290f801f579905ea490161598",
        },
        "carrier": {
            "bt_entity": stack["bt_entity"],
            "bt_device_id": stack["bt_device_id"],
            "bt_entry_state": str(stack["bt_entry"].state.value),
            "bt_entry_disabled_by": None if stack["bt_entry"].disabled_by is None else str(stack["bt_entry"].disabled_by.value),
            "child_entity": stack["child_entity"],
            "child_platform": stack["child_platform"],
            "adapter_module": stack["adapter_name"],
            "temp_topic": stack["temp_topic"],
            "mode_topic": stack["mode_topic"],
            "mqtt_entry_state": str(stack["mqtt_entry"].state.value),
            "external_automation_entity": automation_entity,
            "forbidden_custom_action_to_mqtt_bridge": False,
        },
        "frozen_events": list(EVENTS),
        "expected_presets": list(expected_presets),
        "measurement_start_ns": measurement_start_ns,
        "measurement_end_ns": measurement_end_ns,
        "bt_preset_service_events": bt_calls,
        "child_temperature_service_events": temp_calls,
        "child_hvac_mode_service_events": mode_calls,
        "all_observed_climate_service_events": observer.service_events,
        "observed_state_events": observer.state_events,
        "final_feedback": {
            "presence": hass.states.get(PRESENCE).state,
            "motion": hass.states.get(MOTION).state,
            "night": hass.states.get(NIGHT).state,
        },
        "final_bt_preset": bt_preset(hass, stack["bt_entity"]),
        "final_child_temperature": child_temperature(hass, stack["child_entity"]),
    }
    result_dir.mkdir(parents=True, exist_ok=True)
    (result_dir / "RESULT.json").write_text(json.dumps(result, sort_keys=True, indent=2, default=str) + "\n")
    (result_dir / "DONE").write_text("done\n")
    observer.close()
    # Process exit is the isolation boundary; no state is reused across modes.
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("target-native", "replay"), required=True)
    ap.add_argument("--blueprint", type=Path, required=True)
    ap.add_argument("--bt-source", type=Path, required=True)
    ap.add_argument("--broker", default="mosquitto")
    ap.add_argument("--namespace", required=True)
    ap.add_argument("--result-dir", type=Path, required=True)
    args = ap.parse_args()
    result = asyncio.run(execute(args.mode, blueprint=args.blueprint, bt_source=args.bt_source, broker=args.broker, namespace=args.namespace, result_dir=args.result_dir))
    print("BT_MQTT_E2E_QUALIFICATION_PRODUCER: PASS")
    print(json.dumps({
        "mode": result["mode"],
        "adapter": result["carrier"]["adapter_module"],
        "bt_calls": len(result["bt_preset_service_events"]),
        "temp_calls": len(result["child_temperature_service_events"]),
        "final_preset": result["final_bt_preset"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
