from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import math
import os
from pathlib import Path
import statistics
import time
import uuid

from experiment import Harness

SCHEMA = "replaymark.s2p3-embedded-timestamp-tail-round.v1"
SCHEDULE = (
    (16, 8, 4),
    (8, 4, 16),
    (4, 16, 8),
)
TASKS = 192
WAVE_PERIOD_MS = 300.0
VERIFY_MS = 100.0
TASK_TIMEOUT_MS = 1000
QUIESCENCE_SECONDS = 0.5


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ys = sorted(values)
    pos = (len(ys) - 1) * q / 100.0
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return ys[lo]
    return ys[lo] * (hi - pos) + ys[hi] * (pos - lo)


def time_namespace_info() -> dict[str, object]:
    link = os.readlink("/proc/self/ns/time")
    offsets = Path("/proc/self/timens_offsets").read_text(encoding="utf-8")
    return {"ns_time_link": link, "timens_offsets": offsets}


def sleep_until(deadline_ns: int) -> None:
    while True:
        remaining = deadline_ns - time.monotonic_ns()
        if remaining <= 0:
            return
        time.sleep(remaining / 1e9)


def publish_act1(harness: Harness, device: str) -> tuple[int, int]:
    call_ns = time.monotonic_ns()
    info = harness.client.publish(
        f"agentmark/{device}/command",
        '{"on": true}',
        qos=1,
        retain=False,
        properties=None,
    )
    info.wait_for_publish(timeout=5)
    puback_ns = time.monotonic_ns()
    return call_ns, puback_ns


def run_task(
    harness: Harness,
    *,
    round_index: int,
    position: int,
    wave_size: int,
    task_id: int,
    prefix: str,
    offer_ns: int,
) -> dict[str, object]:
    sleep_until(offer_ns)
    start_ns = time.monotonic_ns()
    device = f"{prefix}-{task_id}-a"
    publish_call_ns, puback_ns = publish_act1(harness, device)
    verify_deadline_ns = start_ns + int(VERIFY_MS * 1e6)
    timeout_deadline_ns = start_ns + int(TASK_TIMEOUT_MS * 1e6)

    by_deadline = harness.wait_state_on_until(
        device, verify_deadline_ns, after_ns=publish_call_ns
    )
    eventual = by_deadline
    if eventual is None:
        eventual = harness.wait_state_on_until(
            device, timeout_deadline_ns, after_ns=publish_call_ns
        )

    recv_ns = None if eventual is None else int(eventual["recv_mono_ns"])
    device_publish_ns = (
        None if eventual is None or eventual.get("ts_mono_ns") is None
        else int(eventual["ts_mono_ns"])
    )

    def ms(delta: int | None) -> float | None:
        return None if delta is None else delta / 1e6

    end_to_end = None if recv_ns is None else recv_ns - start_ns
    forward_device = (
        None if device_publish_ns is None else device_publish_ns - publish_call_ns
    )
    post_device = (
        None if recv_ns is None or device_publish_ns is None
        else recv_ns - device_publish_ns
    )
    publish_overhead = publish_call_ns - start_ns

    return {
        "round_index": round_index,
        "position": position,
        "wave_size": wave_size,
        "task_id": task_id,
        "device": device,
        "state_delay_ms": 0,
        "offer_mono_ns": offer_ns,
        "task_start_mono_ns": start_ns,
        "act1_publish_call_mono_ns": publish_call_ns,
        "act1_puback_mono_ns": puback_ns,
        "verify_deadline_mono_ns": verify_deadline_ns,
        "task_timeout_deadline_mono_ns": timeout_deadline_ns,
        "device_state_publish_mono_ns": device_publish_ns,
        "state_on_recv_mono_ns": recv_ns,
        "visible_by_verify_deadline": by_deadline is not None,
        "completed_by_task_timeout": eventual is not None,
        "event_on": None if eventual is None else bool(eventual.get("on")),
        "event_device": None if eventual is None else str(eventual.get("device")),
        "event_cause": None if eventual is None else str(eventual.get("cause")),
        "scheduler_start_lateness_ms": ms(start_ns - offer_ns),
        "publish_call_overhead_ms": ms(publish_overhead),
        "forward_plus_device_ms": ms(forward_device),
        "post_device_observation_ms": ms(post_device),
        "end_to_end_completion_ms": ms(end_to_end),
        "puback_latency_ms": ms(puback_ns - publish_call_ns),
    }


def run_cell(
    harness: Harness,
    *,
    round_index: int,
    position: int,
    wave_size: int,
) -> dict[str, object]:
    prefix = f"s2p3-r{round_index}-p{position}-w{wave_size}-{uuid.uuid4().hex[:12]}"
    base_ns = time.monotonic_ns() + 100_000_000
    rows: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=TASKS) as pool:
        futures = [
            pool.submit(
                run_task,
                harness,
                round_index=round_index,
                position=position,
                wave_size=wave_size,
                task_id=task_id,
                prefix=prefix,
                offer_ns=base_ns
                + (task_id // wave_size) * int(WAVE_PERIOD_MS * 1e6),
            )
            for task_id in range(TASKS)
        ]
        for future in as_completed(futures):
            rows.append(future.result())
    rows.sort(key=lambda row: int(row["task_id"]))

    preview = {}
    for field in [
        "scheduler_start_lateness_ms",
        "publish_call_overhead_ms",
        "forward_plus_device_ms",
        "post_device_observation_ms",
        "end_to_end_completion_ms",
        "puback_latency_ms",
    ]:
        values = [float(r[field]) for r in rows if r[field] is not None]
        preview[field] = {
            "p50": statistics.median(values) if values else None,
            "p95": percentile(values, 95),
            "p99": percentile(values, 99),
            "max": max(values) if values else None,
        }
    return {
        "round_index": round_index,
        "position": position,
        "wave_size": wave_size,
        "prefix": prefix,
        "rows": rows,
        "runner_descriptive_preview": preview,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--broker", default="mosquitto")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--round-index", type=int, required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    round_index = int(args.round_index)
    if round_index not in range(3):
        raise SystemExit("round index must be 0,1,2")

    harness = Harness(args.broker, args.port)
    try:
        broker = harness.broker_version()
        harness.set_state_delay(0)
        cells = []
        for position, wave in enumerate(SCHEDULE[round_index]):
            cells.append(
                run_cell(
                    harness,
                    round_index=round_index,
                    position=position,
                    wave_size=wave,
                )
            )
            if position < 2:
                time.sleep(QUIESCENCE_SECONDS)
    finally:
        harness.close()

    report = {
        "schema": SCHEMA,
        "source_only": True,
        "shifted_target_executed": False,
        "act2_candidate_constructed": False,
        "state_delay_ms": 0,
        "broker": broker,
        "round_index": round_index,
        "frozen_order": list(SCHEDULE[round_index]),
        "runner_time_namespace": time_namespace_info(),
        "parameters": {
            "tasks_per_cell": TASKS,
            "wave_period_ms": WAVE_PERIOD_MS,
            "verify_ms": VERIFY_MS,
            "task_timeout_ms": TASK_TIMEOUT_MS,
            "quiescence_seconds_between_cells": QUIESCENCE_SECONDS,
        },
        "cells": cells,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
