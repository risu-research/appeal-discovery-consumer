#!/usr/bin/env python3
"""Outcome-blind diagnostic for the frozen Better-Thermostat controller cycle.

This is diagnostic-only evidence. It imports the Phase-B stack constructor but
never supplies downstream actions or adapts the frozen controller prediction.
It drives the four frozen continuation events through the unchanged external
automation, waits a fixed bounded interval after each event, and records what
Home Assistant / Better Thermostat actually did.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import tempfile

from homeassistant.components import automation
from homeassistant.core import HomeAssistant

from agentmark_natural_controllers.better_thermostat.bt_mqtt_e2e_qualify import (
    EVENTS,
    Observer,
    apply_event,
    bt_preset,
    call_preset,
    install_external_automation,
    setup_hass,
)


async def snapshot(hass: HomeAssistant, stack: dict, label: str) -> dict:
    bt_state = hass.states.get(stack["bt_entity"])
    child_state = hass.states.get(stack["child_entity"])
    automations = []
    for state in hass.states.async_all("automation"):
        automations.append(
            {
                "entity_id": state.entity_id,
                "state": state.state,
                "friendly_name": state.attributes.get("friendly_name"),
                "last_triggered": str(state.attributes.get("last_triggered")),
            }
        )
    return {
        "label": label,
        "components": sorted(hass.config.components),
        "automation_component_loaded": automation.DOMAIN in hass.config.components,
        "automation_entities": automations,
        "bt_entity": stack["bt_entity"],
        "bt_device_id": stack["bt_device_id"],
        "bt_state": None if bt_state is None else bt_state.state,
        "bt_preset": None if bt_state is None else bt_state.attributes.get("preset_mode"),
        "bt_temperature": None if bt_state is None else bt_state.attributes.get("temperature"),
        "child_state": None if child_state is None else child_state.state,
        "child_temperature": None if child_state is None else child_state.attributes.get("temperature"),
    }


async def main_async(args) -> dict:
    temp = tempfile.TemporaryDirectory(prefix="replaymark-bt-controller-diag-")
    stack = await setup_hass(
        config_dir=Path(temp.name),
        bt_source=args.bt_source,
        broker=args.broker,
        namespace="diagnose",
    )
    hass: HomeAssistant = stack["hass"]
    bt = stack["bt"]
    observer = Observer(hass, stack["bt_entity"], stack["child_entity"])
    observer.install()

    # Frozen target-world quiescent initial controller state only.
    await call_preset(hass, stack["bt_entity"], "sleep")
    await asyncio.wait_for(bt.control_queue_task.join(), timeout=20.0)
    await hass.async_block_till_done()

    before_install = await snapshot(hass, stack, "before_automation_install")
    await install_external_automation(
        hass, Path(temp.name), args.blueprint, stack["bt_device_id"]
    )
    after_install = await snapshot(hass, stack, "after_automation_install")

    # Diagnostic window starts only after setup. Do not assert any expected
    # preset or MQTT outcome. The exact same frozen events are driven once.
    observer.clear()
    steps = []
    for index, event in enumerate(EVENTS):
        before = await snapshot(hass, stack, f"before_{index}_{event}")
        before_services = len(observer.service_events)
        before_states = len(observer.state_events)
        await apply_event(hass, event)
        # Fixed observation interval, chosen independently of outcome.
        for _ in range(20):
            await asyncio.sleep(0.05)
        await hass.async_block_till_done()
        # Drain only BT work that was naturally queued by the live stack.
        await asyncio.wait_for(bt.control_queue_task.join(), timeout=20.0)
        await hass.async_block_till_done()
        after = await snapshot(hass, stack, f"after_{index}_{event}")
        steps.append(
            {
                "index": index,
                "event": event,
                "before": before,
                "after": after,
                "new_service_events": observer.service_events[before_services:],
                "new_state_events": observer.state_events[before_states:],
            }
        )

    result = {
        "schema": "replaymark.bt_mqtt_controller_diagnostic.v1",
        "diagnostic_only": True,
        "frozen_protocol": "851960e59aa3a68fb90ef199f1dbcfefe5fcd3c0",
        "frozen_events": list(EVENTS),
        "before_install": before_install,
        "after_install": after_install,
        "steps": steps,
        "all_climate_service_events": observer.service_events,
        "all_observed_state_events": observer.state_events,
        "final_preset": bt_preset(hass, stack["bt_entity"]),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, sort_keys=True, indent=2, default=str) + "\n")
    observer.close()
    print("BT_MQTT_CONTROLLER_DIAGNOSTIC: COMPLETE")
    print(json.dumps({
        "automation_entities": after_install["automation_entities"],
        "step_presets": [s["after"]["bt_preset"] for s in steps],
        "climate_service_count": len(observer.service_events),
    }, sort_keys=True, default=str))
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blueprint", type=Path, required=True)
    ap.add_argument("--bt-source", type=Path, required=True)
    ap.add_argument("--broker", default="mosquitto")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    asyncio.run(main_async(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
