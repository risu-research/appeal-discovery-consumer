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
import shutil
import tempfile

from homeassistant.components import automation
from homeassistant.core import HomeAssistant

from agentmark_natural_controllers.better_thermostat.bt_mqtt_e2e_qualify import (
    BLUEPRINT_REL,
    EVENTS,
    Observer,
    apply_event,
    bt_preset,
    call_preset,
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


async def install_external_automation_via_reload(
    hass: HomeAssistant,
    config_dir: Path,
    blueprint: Path,
    bt_device_id: str,
) -> str:
    """Install the frozen blueprint through Home Assistant's public reload path.

    Core bootstrap has already loaded the automation component. Calling
    async_setup_component again is therefore a no-op and does not process new
    automation config. A normal HA installation persists the automation config
    and invokes the registered automation.reload service, which re-reads and
    validates configuration.yaml and materializes automation entities. This
    diagnostic exercises exactly that path without touching controller logic.
    """
    destination = (
        config_dir
        / "blueprints"
        / "automation"
        / "agentmark"
        / "better_thermostat_lean.yaml"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(blueprint, destination)

    config = {
        "automation": {
            "use_blueprint": {
                "path": BLUEPRINT_REL,
                "input": {
                    "climate_device": bt_device_id,
                    "presence_group": "binary_sensor.replaymark_presence",
                    "motion_group": "binary_sensor.replaymark_motion",
                    "night_mode_entity": "input_boolean.replaymark_night",
                    "enable_switch": "input_boolean.replaymark_enable",
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

    await hass.services.async_call(
        automation.DOMAIN,
        "reload",
        {},
        blocking=True,
    )
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


async def main_async(args) -> dict:
    temp = tempfile.TemporaryDirectory(prefix="replaymark-bt-controller-diag-")
    config_dir = Path(temp.name)
    stack = await setup_hass(
        config_dir=config_dir,
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
    automation_entity = await install_external_automation_via_reload(
        hass,
        config_dir,
        args.blueprint,
        stack["bt_device_id"],
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
        "schema": "replaymark.bt_mqtt_controller_diagnostic.v2",
        "diagnostic_only": True,
        "installation_path": "configuration.yaml -> automation.reload",
        "automation_entity": automation_entity,
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
    args.out.write_text(
        json.dumps(result, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print("BT_MQTT_CONTROLLER_DIAGNOSTIC: COMPLETE")
    print(
        json.dumps(
            {
                "automation_entity": automation_entity,
                "automation_entities": after_install["automation_entities"],
                "step_presets": [s["after"]["bt_preset"] for s in steps],
                "climate_service_count": len(observer.service_events),
            },
            sort_keys=True,
            default=str,
        )
    )
    observer.close()
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
