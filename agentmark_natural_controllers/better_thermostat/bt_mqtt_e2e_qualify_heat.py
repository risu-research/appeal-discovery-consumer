#!/usr/bin/env python3
"""One-shot HEAT-enabled Phase-B qualification producer.

This producer is governed by the parent capstone protocol frozen at
851960e59aa3a68fb90ef199f1dbcfefe5fcd3c0 and the carrier-precondition
addendum frozen at a3008b0ebd0eb29a8fb913b8a1355c63c4a8d6c9 before any live
HEAT-enabled qualification result. It reuses the already-qualified stack
constructor and observers. The only semantic difference from the parent
producer is the preregistered, world-independent setup call that enables the
actual Better Thermostat entity in HEAT before the measurement window.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import tempfile
import time

from homeassistant.core import HomeAssistant

from agentmark_natural_controllers.better_thermostat.bt_mqtt_e2e_qualify import (
    ENABLE,
    EVENTS,
    HA_VERSION_EXPECTED,
    MOTION,
    NIGHT,
    PRESENCE,
    REPLAY_ACTIONS,
    SCHEMA,
    TARGET_ACTIONS,
    Observer,
    apply_event,
    bt_preset,
    call_preset,
    child_temperature,
    install_external_automation,
    setup_hass,
    wait_stable_preset,
    wait_until,
)

PARENT_PROTOCOL_FREEZE = "851960e59aa3a68fb90ef199f1dbcfefe5fcd3c0"
CARRIER_ADDENDUM_FREEZE = "a3008b0ebd0eb29a8fb913b8a1355c63c4a8d6c9"


async def activate_carrier(hass: HomeAssistant, stack: dict) -> None:
    """Enable the actual BT carrier through Home Assistant's public service."""
    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": stack["bt_entity"], "hvac_mode": "heat"},
        blocking=True,
    )
    await asyncio.wait_for(stack["bt"].control_queue_task.join(), timeout=20.0)
    await hass.async_block_till_done()
    state = hass.states.get(stack["bt_entity"])
    if state is None or state.state != "heat":
        raise RuntimeError(
            "preregistered carrier precondition failed to establish BT HEAT: "
            f"{None if state is None else state.state!r}"
        )


async def execute(
    mode: str,
    *,
    blueprint: Path,
    bt_source: Path,
    broker: str,
    namespace: str,
    result_dir: Path,
):
    temp = tempfile.TemporaryDirectory(prefix=f"replaymark-bt-mqtt-heat-{mode}-")
    config_dir = Path(temp.name)
    stack = await setup_hass(
        config_dir=config_dir,
        bt_source=bt_source,
        broker=broker,
        namespace=namespace,
    )
    hass: HomeAssistant = stack["hass"]
    bt = stack["bt"]
    observer = Observer(hass, stack["bt_entity"], stack["child_entity"])
    observer.install()

    # Preregistered world-independent carrier enablement. All effects from this
    # call and the following quiescent seed are setup traffic and are excluded
    # before READY / the independent Mosquitto observer.
    initial_bt_state = hass.states.get(stack["bt_entity"])
    initial_child_state = hass.states.get(stack["child_entity"])
    await activate_carrier(hass, stack)
    await call_preset(hass, stack["bt_entity"], "sleep")
    await wait_stable_preset(hass, stack["bt_entity"], bt, "sleep")
    post_setup_bt_state = hass.states.get(stack["bt_entity"])
    post_setup_child_state = hass.states.get(stack["child_entity"])

    automation_entity = None
    if mode == "target-native":
        automation_entity = await install_external_automation(
            hass, config_dir, blueprint, stack["bt_device_id"]
        )
        if bt_preset(hass, stack["bt_entity"]) != "sleep":
            raise RuntimeError("automation install disturbed initial preset")

    # Scientific measurement begins only after all setup/precondition effects
    # have been discarded from the in-process observer. The host starts the
    # independent broker observer after READY and before START.
    observer.clear()
    result_dir.mkdir(parents=True, exist_ok=True)
    ready = result_dir / "READY"
    start = result_dir / "START"
    ready.write_text(
        json.dumps(
            {
                "temp_topic": stack["temp_topic"],
                "mode": mode,
                "carrier_addendum_freeze": CARRIER_ADDENDUM_FREEZE,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    await wait_until(start.exists, timeout=30.0, label="START handshake not received")
    measurement_start_ns = time.perf_counter_ns()

    expected_presets = TARGET_ACTIONS if mode == "target-native" else REPLAY_ACTIONS
    for event, historical in zip(EVENTS, expected_presets):
        await apply_event(hass, event)
        if mode == "replay" and historical is not None:
            await call_preset(hass, stack["bt_entity"], historical)
        if historical is not None:
            await wait_stable_preset(hass, stack["bt_entity"], bt, historical)
        else:
            await asyncio.sleep(0.5)
            await hass.async_block_till_done()

    await asyncio.sleep(0.5)
    await hass.async_block_till_done()
    measurement_end_ns = time.perf_counter_ns()

    bt_calls = [
        e
        for e in observer.service_events
        if e["service"] == "set_preset_mode" and stack["bt_entity"] in e["targets"]
    ]
    temp_calls = [
        e
        for e in observer.service_events
        if e["service"] == "set_temperature" and stack["child_entity"] in e["targets"]
    ]
    mode_calls = [
        e
        for e in observer.service_events
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
            "protocol_freeze": PARENT_PROTOCOL_FREEZE,
            "selector_result_sha256": "07213a0d56e5f2d32b9eb3c2b2e6b20cb0aab31290f801f579905ea490161598",
        },
        "carrier_precondition": {
            "addendum_freeze": CARRIER_ADDENDUM_FREEZE,
            "method": "actual Better Thermostat climate.set_hvac_mode(heat)",
            "pre_bt_state": None if initial_bt_state is None else initial_bt_state.state,
            "pre_child_state": None if initial_child_state is None else initial_child_state.state,
            "post_setup_bt_state": None if post_setup_bt_state is None else post_setup_bt_state.state,
            "post_setup_bt_preset": None if post_setup_bt_state is None else post_setup_bt_state.attributes.get("preset_mode"),
            "post_setup_child_state": None if post_setup_child_state is None else post_setup_child_state.state,
            "post_setup_child_temperature": None if post_setup_child_state is None else post_setup_child_state.attributes.get("temperature"),
            "inside_measurement_window": False,
        },
        "carrier": {
            "bt_entity": stack["bt_entity"],
            "bt_device_id": stack["bt_device_id"],
            "bt_entry_state": str(stack["bt_entry"].state.value),
            "bt_entry_disabled_by": None
            if stack["bt_entry"].disabled_by is None
            else str(stack["bt_entry"].disabled_by.value),
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
    (result_dir / "RESULT.json").write_text(
        json.dumps(result, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    (result_dir / "DONE").write_text("done\n", encoding="utf-8")
    observer.close()
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("target-native", "replay"), required=True)
    ap.add_argument("--blueprint", type=Path, required=True)
    ap.add_argument("--bt-source", type=Path, required=True)
    ap.add_argument("--broker", default="mosquitto")
    ap.add_argument("--namespace", required=True)
    ap.add_argument("--result-dir", type=Path, required=True)
    args = ap.parse_args()
    result = asyncio.run(
        execute(
            args.mode,
            blueprint=args.blueprint,
            bt_source=args.bt_source,
            broker=args.broker,
            namespace=args.namespace,
            result_dir=args.result_dir,
        )
    )
    print("BT_MQTT_E2E_HEAT_QUALIFICATION_PRODUCER: PASS")
    print(
        json.dumps(
            {
                "mode": result["mode"],
                "adapter": result["carrier"]["adapter_module"],
                "bt_calls": len(result["bt_preset_service_events"]),
                "temp_calls": len(result["child_temperature_service_events"]),
                "temp_sequence": [
                    e["service_data"].get("temperature")
                    for e in result["child_temperature_service_events"]
                ],
                "final_preset": result["final_bt_preset"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
