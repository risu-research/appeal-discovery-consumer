from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import time
from typing import Any


def ns_ms(ns: int) -> float:
    return ns / 1_000_000.0


def load_module(path: str):
    spec = importlib.util.spec_from_file_location("agentmark_e3c_base_v2", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


async def run(args: argparse.Namespace) -> dict[str, Any]:
    mod = load_module(args.base_script)
    from homeassistant.core import HassJobType, StateMachine, callback
    from homeassistant.helpers.event import async_track_state_change_event

    observations: list[dict[str, Any]] = []
    state_sets: list[dict[str, Any]] = []
    original_wait = mod.wait_for_on_until
    original_set = StateMachine.async_set

    # Minimal differential observer: one keyed Home Assistant callback per entity.
    # It does NOT add global EVENT_STATE_CHANGED listeners and therefore avoids
    # the O(N^2) fanout pathology under investigation.
    async def differential_wait(hass, entity_id: str, deadline_ns: int):
        record: dict[str, Any] = {
            "entity_id": entity_id,
            "registered_perf_ns": time.perf_counter_ns(),
            "deadline_ns": int(deadline_ns),
            "indexed_callback_perf_ns": None,
            "indexed_event_fire_wall_ns": None,
            "indexed_event_context_id": None,
            "frozen_visible": None,
            "frozen_event_perf_ns": None,
        }
        observations.append(record)
        remove_holder: list[Any] = [None]

        @callback
        def indexed_listener(event) -> None:
            new_state = event.data.get("new_state")
            if new_state is None or new_state.state != "on":
                return
            if record["indexed_callback_perf_ns"] is not None:
                return
            record["indexed_callback_perf_ns"] = time.perf_counter_ns()
            record["indexed_event_fire_wall_ns"] = int(event.time_fired_timestamp * 1_000_000_000)
            record["indexed_event_context_id"] = str(event.context.id)
            if remove_holder[0] is not None:
                remove_holder[0]()
                remove_holder[0] = None

        # The official HA helper indexes by entity id and avoids global-listener
        # scanning/job creation. Force Callback job type explicitly.
        remove_holder[0] = async_track_state_change_event(
            hass,
            entity_id,
            indexed_listener,
            job_type=HassJobType.Callback,
        )
        state = hass.states.get(entity_id)
        if state is not None and state.state == "on":
            record["indexed_callback_perf_ns"] = time.perf_counter_ns()
            remove_holder[0]()
            remove_holder[0] = None

        try:
            frozen_visible, frozen_ns = await original_wait(hass, entity_id, deadline_ns)
            record["frozen_visible"] = bool(frozen_visible)
            record["frozen_event_perf_ns"] = frozen_ns
            return frozen_visible, frozen_ns
        finally:
            # Do not remove an unresolved indexed listener here. It self-removes
            # on the eventual ACT1 state event, allowing us to distinguish
            # before-deadline from after-deadline delivery without delaying the
            # frozen replay path.
            if record["indexed_callback_perf_ns"] is not None and remove_holder[0] is not None:
                remove_holder[0]()
                remove_holder[0] = None

    mod.wait_for_on_until = differential_wait

    def traced_set(
        self,
        entity_id: str,
        new_state: str,
        attributes=None,
        force_update: bool = False,
        context=None,
        state_info=None,
        timestamp=None,
    ) -> None:
        attrs = attributes or {}
        owned = str(entity_id).startswith(("binary_sensor.agentmark_", "sensor.agentmark_"))
        before = time.perf_counter_ns()
        try:
            return original_set(
                self,
                entity_id,
                new_state,
                attributes,
                force_update,
                context,
                state_info,
                timestamp,
            )
        finally:
            if owned:
                state_sets.append({
                    "run_id": str(attrs.get("agentmark_run")),
                    "task_id": str(attrs.get("agentmark_task")),
                    "cause": attrs.get("cause"),
                    "entity_id": str(entity_id),
                    "context_id": None if context is None else str(context.id),
                    "before_perf_ns": before,
                    "after_perf_ns": time.perf_counter_ns(),
                })

    StateMachine.async_set = traced_set
    try:
        exp_args = argparse.Namespace(
            tasks=args.tasks,
            trials=args.trials,
            wave_size=args.wave_size,
            wave_period_ms=args.wave_period_ms,
            source_delay_ms=args.source_delay_ms,
            target_delay_ms=args.target_delay_ms,
            verify_ms=args.verify_ms,
            replica=args.replica,
            out="unused.json",
        )
        result = await mod.experiment(exp_args)
        # All modes use HA's own drain. Give indexed self-removing listeners one
        # final tracked-job drain without introducing any fixed sleep.
        await asyncio.sleep(0)
    finally:
        StateMachine.async_set = original_set
        mod.wait_for_on_until = original_wait

    obs_by_entity: dict[str, list[dict[str, Any]]] = {}
    for x in observations:
        obs_by_entity.setdefault(x["entity_id"], []).append(x)

    sets = {
        (x["run_id"], x["task_id"], x["cause"]): x
        for x in state_sets
    }

    # Each no-shift entity id is unique to its mode/run, so match by exact id.
    causal_rows: list[dict[str, Any]] = []
    for mode, rows in result["raw_replay_rows"]["controls"]["no_feedback_shift"].items():
        run_id = f"control_noshift_{mode.lower()}"
        for row in rows:
            task_id = str(row["task_id"])
            entity_id = f"binary_sensor.agentmark_{task_id}"
            candidates = obs_by_entity.get(entity_id, [])
            if len(candidates) != 1:
                raise AssertionError(f"expected one observation for {entity_id}, got {len(candidates)}")
            o = candidates[0]
            deadline = int(o["deadline_ns"])
            indexed_ns = o["indexed_callback_perf_ns"]
            indexed_by_deadline = indexed_ns is not None and int(indexed_ns) <= deadline
            s = sets.get((run_id, task_id, "act1_visible"))
            if s is None:
                raise AssertionError(f"missing ACT1 state-set record for {run_id}/{task_id}")
            state_set_by_deadline = int(s["before_perf_ns"]) <= deadline
            frozen_miss = row["feedback_at_deadline"] == "MISS"

            if not frozen_miss:
                cause = "VISIBLE"
            elif indexed_by_deadline:
                cause = "FROZEN_GLOBAL_EXECUTOR_OBSERVER_ARTIFACT"
            elif state_set_by_deadline:
                cause = "EVENT_LOOP_OR_DISPATCH_LATE_UNDER_FROZEN_OBSERVER_LOAD"
            else:
                cause = "STATE_SET_LATE_UNDER_FROZEN_OBSERVER_LOAD"

            causal_rows.append({
                "mode": mode,
                "task_index": int(row["task_index"]),
                "task_id": task_id,
                "wave": int(row["task_index"]) // args.wave_size,
                "frozen_feedback": row["feedback_at_deadline"],
                "cause_class": cause,
                "deadline_ns": deadline,
                "indexed_callback_perf_ns": indexed_ns,
                "indexed_callback_by_deadline": bool(indexed_by_deadline),
                "indexed_callback_ms_from_registration": None if indexed_ns is None else ns_ms(int(indexed_ns) - int(o["registered_perf_ns"])),
                "state_set_before_perf_ns": int(s["before_perf_ns"]),
                "state_set_by_deadline": bool(state_set_by_deadline),
                "state_set_ms_before_deadline": ns_ms(deadline - int(s["before_perf_ns"])),
                "frozen_visible": o["frozen_visible"],
                "frozen_event_perf_ns": o["frozen_event_perf_ns"],
                "act1_complete_ms": float(row["act1_complete_ms"]),
                "act2_issue_ms": float(row["act2_issue_ms"]),
            })

    misses = [x for x in causal_rows if x["frozen_feedback"] == "MISS"]
    counts: dict[str, int] = {}
    for x in misses:
        counts[x["cause_class"]] = counts.get(x["cause_class"], 0) + 1

    summary_by_mode: dict[str, Any] = {}
    for mode in ("R0", "R1", "R2"):
        subset = [x for x in causal_rows if x["mode"] == mode]
        mm = [x for x in subset if x["frozen_feedback"] == "MISS"]
        summary_by_mode[mode] = {
            "tasks": len(subset),
            "frozen_misses": len(mm),
            "frozen_miss_rate": len(mm) / len(subset),
            "misses_with_indexed_callback_by_deadline": sum(x["indexed_callback_by_deadline"] for x in mm),
            "misses_with_state_set_by_deadline": sum(x["state_set_by_deadline"] for x in mm),
        }

    return {
        "schema": "agentmark.e3c.no_shift_autopsy.v2",
        "replica": args.replica,
        "method": {
            "shadow_observer": "homeassistant.helpers.event.async_track_state_change_event",
            "shadow_job_type": "HassJobType.Callback",
            "strict_deadline": "indexed_callback_perf_ns <= absolute deadline_ns",
            "frozen_observer_return_value_preserved": True,
        },
        "base_decision": result["decision"],
        "base_promotion_gates": result["promotion_gates"],
        "summary_by_mode": summary_by_mode,
        "miss_cause_counts": dict(sorted(counts.items())),
        "causal_rows": causal_rows,
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--base-script", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--replica", type=int, required=True)
    p.add_argument("--tasks", type=int, default=128)
    p.add_argument("--trials", type=int, default=6)
    p.add_argument("--wave-size", type=int, default=32)
    p.add_argument("--wave-period-ms", type=float, default=300.0)
    p.add_argument("--source-delay-ms", type=float, default=35.0)
    p.add_argument("--target-delay-ms", type=float, default=180.0)
    p.add_argument("--verify-ms", type=float, default=100.0)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    result = asyncio.run(run(args))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "replica": result["replica"],
        "base_decision": result["base_decision"],
        "summary_by_mode": result["summary_by_mode"],
        "miss_cause_counts": result["miss_cause_counts"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
