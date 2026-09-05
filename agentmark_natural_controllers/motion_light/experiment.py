from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import tempfile
import time
from typing import Any

from homeassistant import config_entries, loader
from homeassistant.components import automation
from homeassistant.const import EVENT_CALL_SERVICE, EVENT_STATE_CHANGED, __version__ as HA_VERSION
from homeassistant.core import CoreState, Event, HomeAssistant, ServiceCall, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import trigger as trigger_helper
from homeassistant.setup import async_setup_component

from agentmark.kernel import ReactiveKernel
from agentmark.semantics import step_replay_validity


MOTION_ENTITY = "binary_sensor.agentmark_motion"
LIGHT_ENTITY = "light.agentmark_light"
BLUEPRINT_REL = "agentmark/motion_light.yaml"
EXPECTED_BLUEPRINT_SHA256 = "e07ac35fae7270131f118da767b036e7f7776672077691d9fbcd026e5a7e3f9c"
SOURCE_FEEDBACK_MS = 60.0
TARGET_FEEDBACK_MS = 180.0
SOURCE_ON_DELAY_MS = 5.0
TARGET_ON_DELAY_MS = 40.0
OFF_DELAY_MS = 0.0
BLUEPRINT_DELAY_S = 0.020
TRIALS = 6


def now_ns() -> int:
    return time.perf_counter_ns()


def ns_to_ms(value: int) -> float:
    return value / 1_000_000.0


async def sleep_until_ns(deadline_ns: int) -> None:
    remaining = (deadline_ns - now_ns()) / 1_000_000_000.0
    if remaining > 0:
        await asyncio.sleep(remaining)


def motion_kernel() -> ReactiveKernel:
    return ReactiveKernel(
        {
            "initial_state": "waiting",
            "feedback_alphabet": ["MOTION", "NO_MOTION"],
            "states": {
                "waiting": {
                    "MOTION": [
                        {"p": 1, "operation": "WAIT", "next_state": "waiting"}
                    ],
                    "NO_MOTION": [
                        {
                            "p": 1,
                            "operation": "light.turn_off",
                            "next_state": "done",
                        }
                    ],
                },
                "done": {
                    "MOTION": [
                        {"p": 1, "operation": "STOP", "next_state": "done"}
                    ],
                    "NO_MOTION": [
                        {"p": 1, "operation": "STOP", "next_state": "done"}
                    ],
                },
            },
        }
    )


def support_verdict(motion_state: str | None) -> dict[str, Any]:
    target_feedback = "NO_MOTION" if motion_state == "off" else "MOTION"
    verdict = step_replay_validity(
        motion_kernel(),
        state="waiting",
        source_feedback="NO_MOTION",
        target_feedback=target_feedback,
        recorded_event="light.turn_off",
        projection="operation",
    )
    return {
        "target_feedback": target_feedback,
        "source_probability": float(verdict.source_probability),
        "target_probability": float(verdict.target_probability),
        "source_consistent": verdict.source_consistent,
        "support_failure": verdict.support_failure,
    }


class LightLab:
    def __init__(self, hass: HomeAssistant, *, turn_on_delay_ms: float):
        self.hass = hass
        self.turn_on_delay_ms = turn_on_delay_ms
        self.t0_ns: int | None = None
        self.call_events: list[dict[str, Any]] = []
        self.state_events: list[dict[str, Any]] = []
        self.completions: list[dict[str, Any]] = []
        self._unsubs: list[Any] = []

    def install(self) -> None:
        @callback
        def on_call(event: Event) -> None:
            data = event.data
            if data.get("domain") != "light" or data.get("service") not in {
                "turn_on",
                "turn_off",
            }:
                return
            motion = self.hass.states.get(MOTION_ENTITY)
            self.call_events.append(
                {
                    "t_ns": now_ns(),
                    "service": str(data.get("service")),
                    "service_data": dict(data.get("service_data") or {}),
                    "context_id": str(event.context.id),
                    "context_parent_id": (
                        None
                        if event.context.parent_id is None
                        else str(event.context.parent_id)
                    ),
                    "motion_state_at_issue": None if motion is None else motion.state,
                }
            )

        @callback
        def on_state(event: Event) -> None:
            entity_id = event.data.get("entity_id")
            if entity_id not in {MOTION_ENTITY, LIGHT_ENTITY}:
                return
            new_state = event.data.get("new_state")
            self.state_events.append(
                {
                    "t_ns": now_ns(),
                    "entity_id": entity_id,
                    "state": None if new_state is None else new_state.state,
                    "context_id": str(event.context.id),
                }
            )

        self._unsubs.append(self.hass.bus.async_listen(EVENT_CALL_SERVICE, on_call))
        self._unsubs.append(self.hass.bus.async_listen(EVENT_STATE_CHANGED, on_state))

        async def turn_on(call: ServiceCall) -> None:
            await asyncio.sleep(self.turn_on_delay_ms / 1000.0)
            self.hass.states.async_set(LIGHT_ENTITY, "on", context=call.context)
            self.completions.append(
                {
                    "t_ns": now_ns(),
                    "service": "turn_on",
                    "context_id": str(call.context.id),
                }
            )

        async def turn_off(call: ServiceCall) -> None:
            if OFF_DELAY_MS > 0:
                await asyncio.sleep(OFF_DELAY_MS / 1000.0)
            self.hass.states.async_set(LIGHT_ENTITY, "off", context=call.context)
            self.completions.append(
                {
                    "t_ns": now_ns(),
                    "service": "turn_off",
                    "context_id": str(call.context.id),
                }
            )

        self.hass.services.async_register("light", "turn_on", turn_on)
        self.hass.services.async_register("light", "turn_off", turn_off)

    def close(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    def relative_calls(self, t0_ns: int) -> list[dict[str, Any]]:
        return [
            {**event, "t_ms": ns_to_ms(int(event["t_ns"]) - t0_ns)}
            for event in self.call_events
        ]

    def relative_states(self, t0_ns: int) -> list[dict[str, Any]]:
        return [
            {**event, "t_ms": ns_to_ms(int(event["t_ns"]) - t0_ns)}
            for event in self.state_events
        ]

    def relative_completions(self, t0_ns: int) -> list[dict[str, Any]]:
        return [
            {**event, "t_ms": ns_to_ms(int(event["t_ns"]) - t0_ns)}
            for event in self.completions
        ]


async def wait_for_call_count(lab: LightLab, count: int, timeout_s: float = 2.0) -> None:
    deadline = time.monotonic() + timeout_s
    while len(lab.call_events) < count:
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"timed out waiting for {count} light service calls; saw {len(lab.call_events)}"
            )
        await asyncio.sleep(0.001)


async def set_motion_off_at(hass: HomeAssistant, t0_ns: int, delay_ms: float) -> None:
    await sleep_until_ns(t0_ns + int(delay_ms * 1_000_000.0))
    hass.states.async_set(MOTION_ENTITY, "off")


async def make_hass(
    *,
    blueprint_source: Path,
    turn_on_delay_ms: float,
    native_automation: bool,
) -> tuple[HomeAssistant, LightLab, tempfile.TemporaryDirectory[str]]:
    temp = tempfile.TemporaryDirectory(prefix="agentmark-natural-motion-")
    hass = HomeAssistant(temp.name)
    loader.async_setup(hass)
    hass.config_entries = config_entries.ConfigEntries(hass, {})
    await hass.config_entries.async_initialize()
    dr.async_setup(hass)
    await asyncio.gather(dr.async_load(hass), er.async_load(hass))
    await trigger_helper.async_setup(hass)
    hass.set_state(CoreState.running)

    hass.states.async_set(MOTION_ENTITY, "off")
    hass.states.async_set(LIGHT_ENTITY, "off")

    lab = LightLab(hass, turn_on_delay_ms=turn_on_delay_ms)
    lab.install()

    if native_automation:
        destination = (
            Path(temp.name)
            / "blueprints"
            / "automation"
            / "agentmark"
            / "motion_light.yaml"
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
                            "motion_entity": MOTION_ENTITY,
                            "light_target": {"entity_id": LIGHT_ENTITY},
                            "no_motion_wait": BLUEPRINT_DELAY_S,
                        },
                    }
                }
            },
        )
        if not ok:
            raise RuntimeError("native Home Assistant automation setup returned false")
        await hass.async_block_till_done()

    return hass, lab, temp


async def cleanup_hass(hass: HomeAssistant, lab: LightLab, temp: tempfile.TemporaryDirectory[str]) -> None:
    lab.close()
    try:
        await hass.async_stop()
    finally:
        temp.cleanup()


def summarize_run(
    *,
    label: str,
    t0_ns: int,
    lab: LightLab,
    feedback_delay_ms: float,
) -> dict[str, Any]:
    calls = lab.relative_calls(t0_ns)
    states = lab.relative_states(t0_ns)
    completions = lab.relative_completions(t0_ns)
    by_service = Counter(str(row["service"]) for row in calls)
    off_calls = [row for row in calls if row["service"] == "turn_off"]
    on_calls = [row for row in calls if row["service"] == "turn_on"]
    if len(on_calls) != 1 or len(off_calls) != 1:
        raise AssertionError(
            f"{label}: expected exactly one turn_on/turn_off, got {dict(by_service)}"
        )

    off = off_calls[0]
    verdict = support_verdict(off.get("motion_state_at_issue"))
    return {
        "label": label,
        "feedback_delay_ms": feedback_delay_ms,
        "turn_on_issue_ms": float(on_calls[0]["t_ms"]),
        "turn_off_issue_ms": float(off["t_ms"]),
        "turn_off_motion_state": off.get("motion_state_at_issue"),
        "support": verdict,
        "call_counts": dict(sorted(by_service.items())),
        "raw_call_events": calls,
        "raw_state_events": states,
        "raw_completions": completions,
    }


async def run_native(
    *,
    blueprint_source: Path,
    feedback_delay_ms: float,
    turn_on_delay_ms: float,
    label: str,
) -> dict[str, Any]:
    hass, lab, temp = await make_hass(
        blueprint_source=blueprint_source,
        turn_on_delay_ms=turn_on_delay_ms,
        native_automation=True,
    )
    try:
        t0_ns = now_ns()
        feedback_task = asyncio.create_task(
            set_motion_off_at(hass, t0_ns, feedback_delay_ms)
        )
        hass.states.async_set(MOTION_ENTITY, "on")
        await wait_for_call_count(lab, 2)
        await feedback_task
        await hass.async_block_till_done()
        return summarize_run(
            label=label,
            t0_ns=t0_ns,
            lab=lab,
            feedback_delay_ms=feedback_delay_ms,
        )
    finally:
        await cleanup_hass(hass, lab, temp)


async def run_replay(
    *,
    blueprint_source: Path,
    mode: str,
    source: dict[str, Any],
    feedback_delay_ms: float,
    label: str,
) -> dict[str, Any]:
    if mode not in {"R0", "R1"}:
        raise ValueError(mode)
    hass, lab, temp = await make_hass(
        blueprint_source=blueprint_source,
        turn_on_delay_ms=TARGET_ON_DELAY_MS,
        native_automation=False,
    )
    try:
        t0_ns = now_ns()
        feedback_task = asyncio.create_task(
            set_motion_off_at(hass, t0_ns, feedback_delay_ms)
        )
        hass.states.async_set(MOTION_ENTITY, "on")

        source_on_issue_ms = float(source["turn_on_issue_ms"])
        source_off_issue_ms = float(source["turn_off_issue_ms"])
        source_completions = [
            row
            for row in source["raw_completions"]
            if row["service"] == "turn_on"
        ]
        if len(source_completions) != 1:
            raise AssertionError("source must have one turn_on completion")
        source_on_complete_ms = float(source_completions[0]["t_ms"])
        source_think_ms = source_off_issue_ms - source_on_complete_ms
        if source_think_ms < 0:
            raise AssertionError("source post-completion interval is negative")

        await sleep_until_ns(t0_ns + int(source_on_issue_ms * 1_000_000.0))

        if mode == "R0":
            on_task = asyncio.create_task(
                hass.services.async_call(
                    "light",
                    "turn_on",
                    {"entity_id": LIGHT_ENTITY},
                    blocking=True,
                )
            )
            await sleep_until_ns(t0_ns + int(source_off_issue_ms * 1_000_000.0))
            await hass.services.async_call(
                "light",
                "turn_off",
                {"entity_id": LIGHT_ENTITY},
                blocking=True,
            )
            await on_task
        else:
            await hass.services.async_call(
                "light",
                "turn_on",
                {"entity_id": LIGHT_ENTITY},
                blocking=True,
            )
            await asyncio.sleep(source_think_ms / 1000.0)
            await hass.services.async_call(
                "light",
                "turn_off",
                {"entity_id": LIGHT_ENTITY},
                blocking=True,
            )

        await feedback_task
        await hass.async_block_till_done()
        result = summarize_run(
            label=label,
            t0_ns=t0_ns,
            lab=lab,
            feedback_delay_ms=feedback_delay_ms,
        )
        result["source_post_completion_interval_ms"] = source_think_ms
        return result
    finally:
        await cleanup_hass(hass, lab, temp)


def run_passes_counts(row: dict[str, Any]) -> bool:
    return row["call_counts"] == {"turn_off": 1, "turn_on": 1}


def support_failure(row: dict[str, Any]) -> bool:
    return bool(row["support"]["support_failure"])


async def experiment(args: argparse.Namespace) -> dict[str, Any]:
    blueprint_source = Path(args.blueprint)
    blueprint_payload = blueprint_source.read_bytes()
    blueprint_sha = hashlib.sha256(blueprint_payload).hexdigest()
    if blueprint_sha != EXPECTED_BLUEPRINT_SHA256:
        raise AssertionError(
            f"external blueprint sha mismatch: {blueprint_sha} != {EXPECTED_BLUEPRINT_SHA256}"
        )

    source = await run_native(
        blueprint_source=blueprint_source,
        feedback_delay_ms=SOURCE_FEEDBACK_MS,
        turn_on_delay_ms=SOURCE_ON_DELAY_MS,
        label="source_native",
    )
    source_valid = (
        run_passes_counts(source)
        and source["turn_off_motion_state"] == "off"
        and float(source["turn_off_issue_ms"]) < 130.0
        and not support_failure(source)
    )
    if not source_valid:
        raise AssertionError("source trace failed frozen source qualification")

    decisive: dict[str, list[dict[str, Any]]] = {"R0": [], "R1": [], "R2": []}
    controls: dict[str, list[dict[str, Any]]] = {"R0": [], "R1": [], "R2": []}

    for trial in range(args.trials):
        decisive["R0"].append(
            await run_replay(
                blueprint_source=blueprint_source,
                mode="R0",
                source=source,
                feedback_delay_ms=TARGET_FEEDBACK_MS,
                label=f"target_t{trial}_R0",
            )
        )
        decisive["R1"].append(
            await run_replay(
                blueprint_source=blueprint_source,
                mode="R1",
                source=source,
                feedback_delay_ms=TARGET_FEEDBACK_MS,
                label=f"target_t{trial}_R1",
            )
        )
        decisive["R2"].append(
            await run_native(
                blueprint_source=blueprint_source,
                feedback_delay_ms=TARGET_FEEDBACK_MS,
                turn_on_delay_ms=TARGET_ON_DELAY_MS,
                label=f"target_t{trial}_R2_native",
            )
        )

    for mode in ("R0", "R1", "R2"):
        for trial in range(args.trials):
            if mode == "R2":
                controls[mode].append(
                    await run_native(
                        blueprint_source=blueprint_source,
                        feedback_delay_ms=SOURCE_FEEDBACK_MS,
                        turn_on_delay_ms=TARGET_ON_DELAY_MS,
                        label=f"noshift_t{trial}_{mode}_native",
                    )
                )
            else:
                controls[mode].append(
                    await run_replay(
                        blueprint_source=blueprint_source,
                        mode=mode,
                        source=source,
                        feedback_delay_ms=SOURCE_FEEDBACK_MS,
                        label=f"noshift_t{trial}_{mode}",
                    )
                )

    source_off = float(source["turn_off_issue_ms"])
    r0_off = [float(row["turn_off_issue_ms"]) for row in decisive["R0"]]
    r1_off = [float(row["turn_off_issue_ms"]) for row in decisive["R1"]]
    r2_off = [float(row["turn_off_issue_ms"]) for row in decisive["R2"]]

    gates = {
        "external_source_hash_exact": blueprint_sha == EXPECTED_BLUEPRINT_SHA256,
        "ha_version_exact": HA_VERSION == "2026.9.0",
        "source_valid": source_valid,
        "all_decisive_native_counts_exact": all(
            run_passes_counts(row)
            for mode in decisive.values()
            for row in mode
        ),
        "r0_support_failure_all": all(support_failure(row) for row in decisive["R0"]),
        "r1_support_failure_all": all(support_failure(row) for row in decisive["R1"]),
        "r2_support_preserved_all": all(not support_failure(row) for row in decisive["R2"]),
        "r0_turnoff_while_motion_all": all(
            row["turn_off_motion_state"] == "on" for row in decisive["R0"]
        ),
        "r1_turnoff_while_motion_all": all(
            row["turn_off_motion_state"] == "on" for row in decisive["R1"]
        ),
        "r2_turnoff_after_nomotion_all": all(
            row["turn_off_motion_state"] == "off" for row in decisive["R2"]
        ),
        "r1_timing_shift_material": (
            statistics.fmean(r1_off) - statistics.fmean(r0_off) >= 20.0
        ),
        "r2_semantic_shift_material": (
            statistics.fmean(r2_off) - source_off >= 80.0
        ),
        "noshift_counts_exact": all(
            run_passes_counts(row)
            for mode in controls.values()
            for row in mode
        ),
        "noshift_support_preserved": all(
            not support_failure(row)
            for mode in controls.values()
            for row in mode
        ),
        "noshift_turnoff_after_nomotion": all(
            row["turn_off_motion_state"] == "off"
            for mode in controls.values()
            for row in mode
        ),
    }
    gates["promoted"] = all(gates.values())

    result = {
        "schema": "agentmark.natural_controller.motion_light.v1",
        "replica": args.replica,
        "decision": "PROMOTED" if gates["promoted"] else "NOT_PROMOTED",
        "environment": {"home_assistant_core_version": HA_VERSION},
        "external_controller": {
            "repository": "home-assistant/core",
            "commit": "0cb25fe4727b5466743285f048eb6aa75fd02bbb",
            "path": "homeassistant/components/automation/blueprints/motion_light.yaml",
            "sha256": blueprint_sha,
            "source_edited": False,
            "blueprint_inputs": {
                "motion_entity": MOTION_ENTITY,
                "light_target": {"entity_id": LIGHT_ENTITY},
                "no_motion_wait_seconds": BLUEPRINT_DELAY_S,
            },
        },
        "frozen_protocol": {
            "source_feedback_ms": SOURCE_FEEDBACK_MS,
            "target_feedback_ms": TARGET_FEEDBACK_MS,
            "source_turn_on_completion_delay_ms": SOURCE_ON_DELAY_MS,
            "target_turn_on_completion_delay_ms": TARGET_ON_DELAY_MS,
            "turn_off_completion_delay_ms": OFF_DELAY_MS,
            "blueprint_post_feedback_delay_s": BLUEPRINT_DELAY_S,
            "trials": args.trials,
        },
        "source": source,
        "decisive": decisive,
        "no_feedback_shift_control": controls,
        "aggregate": {
            "source_turn_off_issue_ms": source_off,
            "R0_turn_off_mean_ms": statistics.fmean(r0_off),
            "R1_turn_off_mean_ms": statistics.fmean(r1_off),
            "R2_turn_off_mean_ms": statistics.fmean(r2_off),
            "R1_minus_R0_mean_ms": statistics.fmean(r1_off) - statistics.fmean(r0_off),
            "R2_minus_source_mean_ms": statistics.fmean(r2_off) - source_off,
            "R0_support_failure_rate": sum(support_failure(r) for r in decisive["R0"]) / args.trials,
            "R1_support_failure_rate": sum(support_failure(r) for r in decisive["R1"]) / args.trials,
            "R2_support_failure_rate": sum(support_failure(r) for r in decisive["R2"]) / args.trials,
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
                "aggregate": result["aggregate"],
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
