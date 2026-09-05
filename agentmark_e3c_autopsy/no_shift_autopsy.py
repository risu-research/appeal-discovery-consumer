from __future__ import annotations

import argparse
import asyncio
import gc
import importlib.util
import json
from pathlib import Path
import sys
import time
from typing import Any


def ns_ms(ns: int) -> float:
    return ns / 1_000_000.0


def load_module(path: str):
    spec = importlib.util.spec_from_file_location("agentmark_e3c_base", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


async def run(args: argparse.Namespace) -> dict[str, Any]:
    mod = load_module(args.base_script)
    from homeassistant.const import EVENT_CALL_SERVICE, EVENT_STATE_CHANGED
    from homeassistant.core import StateMachine, callback

    telemetry: dict[str, Any] = {
        "schema": "agentmark.e3c.no_shift_autopsy.telemetry.v1",
        "replica": args.replica,
        "heartbeat_interval_ms": args.heartbeat_ms,
        "heartbeat_report_threshold_ms": args.heartbeat_report_ms,
        "gc_events": [],
        "heartbeat_stalls": [],
        "call_service": [],
        "state_set": [],
        "event_callbacks": [],
        "dual_observations": [],
    }

    stop_heartbeat = asyncio.Event()

    def gc_callback(phase: str, info: dict[str, Any]) -> None:
        telemetry["gc_events"].append(
            {
                "phase": phase,
                "generation": int(info.get("generation", -1)),
                "collected": int(info.get("collected", 0)),
                "uncollectable": int(info.get("uncollectable", 0)),
                "perf_ns": time.perf_counter_ns(),
                "wall_ns": time.time_ns(),
                "thread_cpu_ns": time.thread_time_ns(),
            }
        )

    async def heartbeat() -> None:
        interval_s = args.heartbeat_ms / 1000.0
        threshold_ns = int(args.heartbeat_report_ms * 1_000_000.0)
        last_perf = time.perf_counter_ns()
        last_cpu = time.thread_time_ns()
        while not stop_heartbeat.is_set():
            await asyncio.sleep(interval_s)
            now_perf = time.perf_counter_ns()
            now_cpu = time.thread_time_ns()
            elapsed = now_perf - last_perf
            cpu = now_cpu - last_cpu
            lag = max(0, elapsed - int(args.heartbeat_ms * 1_000_000.0))
            if lag >= threshold_ns:
                telemetry["heartbeat_stalls"].append(
                    {
                        "start_perf_ns": last_perf,
                        "end_perf_ns": now_perf,
                        "elapsed_ms": ns_ms(elapsed),
                        "lag_ms": ns_ms(lag),
                        "thread_cpu_ms": ns_ms(cpu),
                        "cpu_fraction_of_elapsed": 0.0 if elapsed <= 0 else cpu / elapsed,
                    }
                )
            last_perf = now_perf
            last_cpu = now_cpu

    original_wait_for_on_until = mod.wait_for_on_until

    async def dual_wait_for_on_until(hass, entity_id: str, deadline_ns: int):
        # Register a HA-native callback observer first, then run the frozen
        # observer unchanged. This is diagnostic A/B instrumentation: the
        # base result still uses the original observer's return value.
        start_perf = time.perf_counter_ns()
        state = hass.states.get(entity_id)
        native_fut = asyncio.get_running_loop().create_future()
        native_event_meta: dict[str, Any] = {}

        @callback
        def native_listener(event):
            if event.data.get("entity_id") != entity_id:
                return
            new_state = event.data.get("new_state")
            if new_state is not None and new_state.state == "on" and not native_fut.done():
                native_event_meta["event_fire_wall_ns"] = int(event.time_fired_timestamp * 1_000_000_000)
                native_event_meta["callback_perf_ns"] = time.perf_counter_ns()
                native_fut.set_result(native_event_meta["callback_perf_ns"])

        if state is not None and state.state == "on":
            native_fut.set_result(time.perf_counter_ns())
            native_unsub = None
        else:
            native_unsub = hass.bus.async_listen(EVENT_STATE_CHANGED, native_listener)
            state = hass.states.get(entity_id)
            if state is not None and state.state == "on" and not native_fut.done():
                native_fut.set_result(time.perf_counter_ns())

        try:
            frozen_visible, frozen_ns = await original_wait_for_on_until(hass, entity_id, deadline_ns)
            if native_fut.done():
                native_visible = True
                native_ns = native_fut.result()
            else:
                remaining = max(0.0, (deadline_ns - time.perf_counter_ns()) / 1_000_000_000.0)
                if remaining <= 0:
                    native_visible, native_ns = False, None
                else:
                    try:
                        native_ns = await asyncio.wait_for(asyncio.shield(native_fut), timeout=remaining)
                        native_visible = True
                    except TimeoutError:
                        native_visible, native_ns = False, None
            telemetry["dual_observations"].append({
                "entity_id": entity_id,
                "start_perf_ns": start_perf,
                "deadline_ns": deadline_ns,
                "frozen_visible": bool(frozen_visible),
                "frozen_callback_perf_ns": frozen_ns,
                "native_callback_visible": bool(native_visible),
                "native_callback_perf_ns": native_ns,
                "native_event_fire_wall_ns": native_event_meta.get("event_fire_wall_ns"),
            })
            return frozen_visible, frozen_ns
        finally:
            if native_unsub is not None:
                native_unsub()

    mod.wait_for_on_until = dual_wait_for_on_until

    original_call_service = mod.call_service

    async def traced_call_service(hass, service, data, *, blocking, context=None, issued=None):
        enter_perf = time.perf_counter_ns()
        enter_wall = time.time_ns()
        try:
            issue_ns, complete_ns = await original_call_service(
                hass,
                service,
                data,
                blocking=blocking,
                context=context,
                issued=issued,
            )
            return issue_ns, complete_ns
        finally:
            exit_perf = time.perf_counter_ns()
            telemetry["call_service"].append(
                {
                    "run_id": str(data.get("run_id")),
                    "task_id": str(data.get("task_id")),
                    "service": str(service),
                    "enter_perf_ns": enter_perf,
                    "enter_wall_ns": enter_wall,
                    "issue_perf_ns": locals().get("issue_ns"),
                    "complete_perf_ns": locals().get("complete_ns"),
                    "exit_perf_ns": exit_perf,
                    "blocking": bool(blocking),
                }
            )

    mod.call_service = traced_call_service

    original_state_set = StateMachine.async_set

    def traced_state_set(
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
        before_perf = time.perf_counter_ns()
        before_wall = time.time_ns()
        try:
            return original_state_set(
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
                telemetry["state_set"].append(
                    {
                        "run_id": str(attrs.get("agentmark_run")),
                        "task_id": str(attrs.get("agentmark_task")),
                        "cause": attrs.get("cause"),
                        "entity_id": str(entity_id),
                        "context_id": None if context is None else str(context.id),
                        "before_perf_ns": before_perf,
                        "after_perf_ns": time.perf_counter_ns(),
                        "before_wall_ns": before_wall,
                        "after_wall_ns": time.time_ns(),
                    }
                )

    StateMachine.async_set = traced_state_set

    original_install = mod.HALab.install

    def traced_install(self) -> None:
        original_install(self)

        def record_event(event, kind: str) -> None:
            if kind == "call_service":
                data = event.data
                if data.get("domain") != mod.DOMAIN:
                    return
                sd = dict(data.get("service_data") or {})
                run_id = str(sd.get("run_id"))
                task_id = str(sd.get("task_id"))
                service = str(data.get("service"))
            else:
                entity_id = event.data.get("entity_id")
                if not isinstance(entity_id, str) or not entity_id.startswith(("binary_sensor.agentmark_", "sensor.agentmark_")):
                    return
                ns = event.data.get("new_state")
                attrs = {} if ns is None else dict(ns.attributes)
                run_id = str(attrs.get("agentmark_run"))
                task_id = str(attrs.get("agentmark_task"))
                service = str(attrs.get("cause"))
            cb_wall = time.time_ns()
            telemetry["event_callbacks"].append(
                {
                    "kind": kind,
                    "run_id": run_id,
                    "task_id": task_id,
                    "service_or_cause": service,
                    "context_id": str(event.context.id),
                    "event_fire_wall_ns": int(event.time_fired_timestamp * 1_000_000_000),
                    "callback_wall_ns": cb_wall,
                    "callback_perf_ns": time.perf_counter_ns(),
                    "dispatch_lag_ms": ns_ms(cb_wall - int(event.time_fired_timestamp * 1_000_000_000)),
                }
            )

        @callback
        def forensic_call(event):
            record_event(event, "call_service")

        @callback
        def forensic_state(event):
            record_event(event, "state_changed")

        self._unsubs.append(self.hass.bus.async_listen(EVENT_CALL_SERVICE, forensic_call))
        self._unsubs.append(self.hass.bus.async_listen(EVENT_STATE_CHANGED, forensic_state))

    mod.HALab.install = traced_install

    gc.callbacks.append(gc_callback)
    hb = asyncio.create_task(heartbeat())
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
    finally:
        stop_heartbeat.set()
        try:
            await asyncio.wait_for(hb, timeout=1.0)
        except Exception:
            hb.cancel()
        try:
            gc.callbacks.remove(gc_callback)
        except ValueError:
            pass
        StateMachine.async_set = original_state_set
        mod.call_service = original_call_service
        mod.HALab.install = original_install
        mod.wait_for_on_until = original_wait_for_on_until

    calls = {
        (x["run_id"], x["task_id"], x["service"]): x
        for x in telemetry["call_service"]
        if x.get("issue_perf_ns") is not None
    }
    sets = {
        (x["run_id"], x["task_id"], x["cause"]): x
        for x in telemetry["state_set"]
    }
    callbacks = {
        (x["run_id"], x["task_id"], x["service_or_cause"]): x
        for x in telemetry["event_callbacks"]
        if x["kind"] == "state_changed"
    }

    dual_by_entity = {x["entity_id"]: x for x in telemetry["dual_observations"]}

    causal_rows = []
    for mode, rows in result["raw_replay_rows"]["controls"]["no_feedback_shift"].items():
        run_id = f"control_noshift_{mode.lower()}"
        for row in rows:
            task_id = row["task_id"]
            c = calls[(run_id, task_id, mod.ACT1)]
            s = sets[(run_id, task_id, "act1_visible")]
            ev = callbacks[(run_id, task_id, "act1_visible")]
            issue = int(c["issue_perf_ns"])
            state_set_ms = ns_ms(int(s["before_perf_ns"]) - issue)
            service_complete_ms = ns_ms(int(c["complete_perf_ns"]) - issue)
            callback_ms = ns_ms(int(ev["callback_perf_ns"]) - issue)
            miss = row["feedback_at_deadline"] == "MISS"
            entity_id = f"binary_sensor.agentmark_{task_id}"
            dual = dual_by_entity.get(entity_id, {})
            native_visible = dual.get("native_callback_visible")
            if not miss:
                cause = "VISIBLE"
            elif native_visible is True:
                cause = "FROZEN_EXECUTOR_OBSERVER_LATE_NATIVE_CALLBACK_VISIBLE"
            elif state_set_ms > args.verify_ms:
                cause = "STATE_SET_AFTER_DEADLINE"
            elif callback_ms > args.verify_ms:
                cause = "EVENT_DISPATCH_AFTER_DEADLINE_EVEN_NATIVE_CALLBACK"
            else:
                cause = "MONITOR_INCONSISTENCY"
            causal_rows.append(
                {
                    "mode": mode,
                    "task_index": row["task_index"],
                    "task_id": task_id,
                    "wave": int(row["task_index"]) // args.wave_size,
                    "feedback": row["feedback_at_deadline"],
                    "cause_class": cause,
                    "state_set_ms": state_set_ms,
                    "service_complete_ms": service_complete_ms,
                    "callback_ms": callback_ms,
                    "callback_dispatch_lag_ms_from_event_timestamp": float(ev["dispatch_lag_ms"]),
                    "native_callback_visible_by_deadline": native_visible,
                    "native_callback_ms_from_monitor_start": None if dual.get("native_callback_perf_ns") is None else ns_ms(int(dual["native_callback_perf_ns"]) - int(dual["start_perf_ns"])),
                    "act2_issue_ms": row["act2_issue_ms"],
                    "source_act2_issue_ms": row["source_act2_issue_ms"],
                }
            )

    miss_rows = [r for r in causal_rows if r["feedback"] == "MISS"]
    cause_counts: dict[str, int] = {}
    for r in miss_rows:
        cause_counts[r["cause_class"]] = cause_counts.get(r["cause_class"], 0) + 1

    result_out = {
        "schema": "agentmark.e3c.no_shift_autopsy.v1",
        "replica": args.replica,
        "base_decision": result["decision"],
        "base_promotion_gates": result["promotion_gates"],
        "frozen_protocol": result["frozen_protocol"],
        "no_shift_summary": result["controls"]["no_feedback_shift"],
        "causal_summary": {
            "misses": len(miss_rows),
            "cause_counts": dict(sorted(cause_counts.items())),
            "heartbeat_stalls_ge_threshold": len(telemetry["heartbeat_stalls"]),
            "gc_events": len(telemetry["gc_events"]),
        },
        "causal_rows": causal_rows,
        "telemetry": telemetry,
        "base_result": result,
    }
    return result_out


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
    p.add_argument("--heartbeat-ms", type=float, default=5.0)
    p.add_argument("--heartbeat-report-ms", type=float, default=8.0)
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
        "causal_summary": result["causal_summary"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
