from __future__ import annotations

"""Gate S2-Q source-only calibration.

This runner is intentionally incapable of executing the shifted target capstone.
It runs only ACT1 source tasks at state delay 0, records the first matching A-side
state completion for every task, and derives the one protocol-defined D* preview.
The independent verifier recomputes every statistic and D* from raw integer
timestamps before the calibration may be promoted.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import math
from pathlib import Path
import statistics
import time
import uuid

from experiment import Harness


SCHEMA = "replaymark.s2q-source-only-calibration.v1"


def _sleep_until(deadline_ns: int) -> None:
    while True:
        remaining = deadline_ns - time.monotonic_ns()
        if remaining <= 0:
            return
        time.sleep(remaining / 1e9)


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ys = sorted(values)
    pos = (len(ys) - 1) * q / 100.0
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return ys[lo]
    return ys[lo] * (hi - pos) + ys[hi] * (pos - lo)


def _publish_act1(harness: Harness, device: str) -> int:
    stamp = time.monotonic_ns()
    info = harness.client.publish(
        f"agentmark/{device}/command",
        '{"on": true}',
        qos=1,
        retain=False,
        properties=None,
    )
    info.wait_for_publish(timeout=5)
    return stamp


def _run_task(
    harness: Harness,
    *,
    replicate: int,
    task_id: int,
    prefix: str,
    offer_ns: int,
    verify_ms: float,
    task_timeout_ms: int,
) -> dict[str, object]:
    _sleep_until(offer_ns)
    t0_ns = time.monotonic_ns()
    device = f"{prefix}-{task_id}-a"
    publish_ns = _publish_act1(harness, device)
    verify_deadline_ns = t0_ns + int(verify_ms * 1e6)
    timeout_deadline_ns = t0_ns + int(task_timeout_ms * 1e6)

    by_deadline = harness.wait_state_on_until(
        device,
        verify_deadline_ns,
        after_ns=publish_ns,
    )
    eventual = by_deadline
    if eventual is None:
        eventual = harness.wait_state_on_until(
            device,
            timeout_deadline_ns,
            after_ns=publish_ns,
        )

    recv_ns = None if eventual is None else int(eventual["recv_mono_ns"])
    completion_ms = None if recv_ns is None else (recv_ns - t0_ns) / 1e6
    visible = by_deadline is not None

    return {
        "replicate": replicate,
        "task_id": task_id,
        "device": device,
        "state_delay_ms": 0,
        "t0_mono_ns": t0_ns,
        "act1_publish_mono_ns": publish_ns,
        "verify_deadline_mono_ns": verify_deadline_ns,
        "task_timeout_deadline_mono_ns": timeout_deadline_ns,
        "state_on_recv_mono_ns": recv_ns,
        "completion_offset_ms": completion_ms,
        "visible_by_verify_deadline": visible,
        "completed_by_task_timeout": eventual is not None,
        "event_on": None if eventual is None else bool(eventual.get("on")),
        "event_device": None if eventual is None else str(eventual.get("device")),
        "event_cause": None if eventual is None else str(eventual.get("cause")),
    }


def _run_replicate(
    harness: Harness,
    *,
    replicate: int,
    tasks: int,
    wave_size: int,
    wave_period_ms: float,
    verify_ms: float,
    task_timeout_ms: int,
) -> dict[str, object]:
    prefix = f"s2q-source-r{replicate}-{uuid.uuid4().hex[:10]}"
    base_ns = time.monotonic_ns() + 100_000_000
    rows: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=tasks) as pool:
        futures = [
            pool.submit(
                _run_task,
                harness,
                replicate=replicate,
                task_id=task_id,
                prefix=prefix,
                offer_ns=base_ns
                + (task_id // wave_size) * int(wave_period_ms * 1e6),
                verify_ms=verify_ms,
                task_timeout_ms=task_timeout_ms,
            )
            for task_id in range(tasks)
        ]
        for future in as_completed(futures):
            rows.append(future.result())
    rows.sort(key=lambda row: int(row["task_id"]))
    return {
        "replicate": replicate,
        "prefix": prefix,
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--broker", default="mosquitto")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--tasks", type=int, default=192)
    parser.add_argument("--wave-size", type=int, default=32)
    parser.add_argument("--wave-period-ms", type=float, default=300.0)
    parser.add_argument("--verify-ms", type=float, default=100.0)
    parser.add_argument("--task-timeout-ms", type=int, default=1000)
    parser.add_argument(
        "--out",
        default="/results/replaymark_s2q_source_calibration.json",
    )
    args = parser.parse_args()

    harness = Harness(args.broker, args.port)
    replicates: list[dict[str, object]] = []
    try:
        broker_version = harness.broker_version()
        harness.set_state_delay(0)
        for replicate in range(args.replicates):
            replicates.append(
                _run_replicate(
                    harness,
                    replicate=replicate,
                    tasks=args.tasks,
                    wave_size=args.wave_size,
                    wave_period_ms=args.wave_period_ms,
                    verify_ms=args.verify_ms,
                    task_timeout_ms=args.task_timeout_ms,
                )
            )
            time.sleep(0.05)
    finally:
        harness.close()

    rows = [row for rep in replicates for row in rep["rows"]]
    offsets = [
        float(row["completion_offset_ms"])
        for row in rows
        if row["completion_offset_ms"] is not None
    ]
    all_complete = len(offsets) == args.replicates * args.tasks
    all_visible = all(bool(row["visible_by_verify_deadline"]) for row in rows)
    median_ms = statistics.median(offsets) if offsets else None
    p99_ms = _percentile(offsets, 99.0)
    d_star_ms = None
    if all_complete and median_ms is not None:
        d_star_ms = math.floor((args.verify_ms - median_ms) + 0.5)

    report = {
        "schema": SCHEMA,
        "broker": broker_version,
        "source_only": True,
        "shifted_target_executed": False,
        "act2_candidate_constructed": False,
        "state_delay_ms": 0,
        "parameters": {
            "replicates": args.replicates,
            "tasks_per_replicate": args.tasks,
            "wave_size": args.wave_size,
            "wave_period_ms": args.wave_period_ms,
            "verify_ms": args.verify_ms,
            "task_timeout_ms": args.task_timeout_ms,
        },
        "replicates": replicates,
        "runner_derived_preview": {
            "row_count": len(rows),
            "completion_count": len(offsets),
            "all_tasks_complete": all_complete,
            "all_source_state_visible_by_verify_deadline": all_visible,
            "pooled_median_source_completion_ms": median_ms,
            "pooled_completion_p99_ms": p99_ms,
            "D_star_ms": d_star_ms,
        },
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["runner_derived_preview"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
