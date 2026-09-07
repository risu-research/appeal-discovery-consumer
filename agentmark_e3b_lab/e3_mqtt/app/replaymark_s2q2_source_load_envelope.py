from __future__ import annotations

"""ReplayMark Gate S2-Q2 source-only load-envelope execution.

This runner is intentionally incapable of executing ACT2 or a shifted target.
It performs either one frozen screening round or one fresh holdout replicate.
W* is never accepted as a caller-supplied number for holdout: the holdout path
must consume the independent screening-selection seal produced after all three
screening rounds.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import math
from pathlib import Path
import statistics
import time
import uuid

from experiment import Harness


SCREENING_SCHEMA = "replaymark.s2q2-source-screening-round.v1"
HOLDOUT_SCHEMA = "replaymark.s2q2-source-holdout-replicate.v1"
SELECTION_SEAL_SCHEMA = "replaymark.s2q2-screening-selection-seal.v1"

SCREENING_SCHEDULE = (
    (16, 8, 4),
    (8, 4, 16),
    (4, 16, 8),
)
TASKS = 192
WAVE_PERIOD_MS = 300.0
VERIFY_MS = 100.0
TASK_TIMEOUT_MS = 1000
QUIESCENCE_SECONDS = 0.5


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    phase: str,
    replicate: int,
    round_index: int | None,
    position: int | None,
    wave_size: int,
    task_id: int,
    prefix: str,
    offer_ns: int,
) -> dict[str, object]:
    _sleep_until(offer_ns)
    t0_ns = time.monotonic_ns()
    device = f"{prefix}-{task_id}-a"
    publish_ns = _publish_act1(harness, device)
    verify_deadline_ns = t0_ns + int(VERIFY_MS * 1e6)
    timeout_deadline_ns = t0_ns + int(TASK_TIMEOUT_MS * 1e6)

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
    start_lateness_ms = (t0_ns - offer_ns) / 1e6
    visible = by_deadline is not None

    return {
        "phase": phase,
        "replicate": replicate,
        "round_index": round_index,
        "position": position,
        "wave_size": wave_size,
        "task_id": task_id,
        "device": device,
        "state_delay_ms": 0,
        "offer_mono_ns": offer_ns,
        "task_start_mono_ns": t0_ns,
        "start_lateness_ms": start_lateness_ms,
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


def _run_cell(
    harness: Harness,
    *,
    phase: str,
    replicate: int,
    round_index: int | None,
    position: int | None,
    wave_size: int,
) -> dict[str, object]:
    prefix = (
        f"s2q2-{phase}-r{replicate}-w{wave_size}-"
        f"{uuid.uuid4().hex[:12]}"
    )
    base_ns = time.monotonic_ns() + 100_000_000
    rows: list[dict[str, object]] = []

    with ThreadPoolExecutor(max_workers=TASKS) as pool:
        futures = [
            pool.submit(
                _run_task,
                harness,
                phase=phase,
                replicate=replicate,
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
    offsets = [
        float(row["completion_offset_ms"])
        for row in rows
        if row["completion_offset_ms"] is not None
    ]
    lateness = [float(row["start_lateness_ms"]) for row in rows]
    return {
        "phase": phase,
        "replicate": replicate,
        "round_index": round_index,
        "position": position,
        "wave_size": wave_size,
        "prefix": prefix,
        "rows": rows,
        "runner_descriptive_preview": {
            "row_count": len(rows),
            "completion_count": len(offsets),
            "visible_by_verify_deadline": sum(
                bool(row["visible_by_verify_deadline"]) for row in rows
            ),
            "completion_median_ms": statistics.median(offsets) if offsets else None,
            "completion_p99_ms": _percentile(offsets, 99.0),
            "start_lateness_p99_ms": _percentile(lateness, 99.0),
        },
    }


def _run_screening_round(args: argparse.Namespace) -> dict[str, object]:
    round_index = int(args.round_index)
    if round_index not in range(len(SCREENING_SCHEDULE)):
        raise SystemExit("screening round index must be 0, 1, or 2")

    harness = Harness(args.broker, args.port)
    cells: list[dict[str, object]] = []
    try:
        broker_version = harness.broker_version()
        harness.set_state_delay(0)
        for position, wave_size in enumerate(SCREENING_SCHEDULE[round_index]):
            cells.append(
                _run_cell(
                    harness,
                    phase="screening",
                    replicate=round_index,
                    round_index=round_index,
                    position=position,
                    wave_size=wave_size,
                )
            )
            if position + 1 < len(SCREENING_SCHEDULE[round_index]):
                time.sleep(QUIESCENCE_SECONDS)
    finally:
        harness.close()

    return {
        "schema": SCREENING_SCHEMA,
        "source_only": True,
        "shifted_target_executed": False,
        "act2_candidate_constructed": False,
        "broker": broker_version,
        "state_delay_ms": 0,
        "round_index": round_index,
        "frozen_order": list(SCREENING_SCHEDULE[round_index]),
        "parameters": {
            "tasks_per_cell": TASKS,
            "wave_period_ms": WAVE_PERIOD_MS,
            "verify_ms": VERIFY_MS,
            "task_timeout_ms": TASK_TIMEOUT_MS,
            "quiescence_seconds_between_cells": QUIESCENCE_SECONDS,
        },
        "cells": cells,
    }


def _run_holdout(args: argparse.Namespace) -> dict[str, object]:
    replicate = int(args.holdout_replicate)
    if replicate not in range(3):
        raise SystemExit("holdout replicate must be 0, 1, or 2")

    seal_path = Path(args.selection_seal)
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    if seal.get("schema") != SELECTION_SEAL_SCHEMA:
        raise SystemExit("foreign screening selection seal")
    if seal.get("screening_verdict") != "PASS":
        raise SystemExit("holdout forbidden without PASS screening selection seal")
    wave_size = seal.get("W_star_screen")
    if wave_size not in (16, 8, 4):
        raise SystemExit("screening selection seal contains ineligible W*")

    harness = Harness(args.broker, args.port)
    try:
        broker_version = harness.broker_version()
        harness.set_state_delay(0)
        cell = _run_cell(
            harness,
            phase="holdout",
            replicate=replicate,
            round_index=None,
            position=None,
            wave_size=int(wave_size),
        )
    finally:
        harness.close()

    return {
        "schema": HOLDOUT_SCHEMA,
        "source_only": True,
        "shifted_target_executed": False,
        "act2_candidate_constructed": False,
        "broker": broker_version,
        "state_delay_ms": 0,
        "holdout_replicate": replicate,
        "selected_wave_size": int(wave_size),
        "selection_seal_sha256": _sha256(seal_path),
        "parameters": {
            "tasks": TASKS,
            "wave_period_ms": WAVE_PERIOD_MS,
            "verify_ms": VERIFY_MS,
            "task_timeout_ms": TASK_TIMEOUT_MS,
        },
        "cell": cell,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--broker", default="mosquitto")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument(
        "--mode",
        required=True,
        choices=("screening-round", "holdout"),
    )
    parser.add_argument("--round-index", type=int)
    parser.add_argument("--holdout-replicate", type=int)
    parser.add_argument("--selection-seal")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    if args.mode == "screening-round":
        if args.round_index is None:
            raise SystemExit("--round-index is required for screening-round")
        if args.selection_seal is not None or args.holdout_replicate is not None:
            raise SystemExit("screening-round cannot accept holdout arguments")
        report = _run_screening_round(args)
    else:
        if args.holdout_replicate is None or args.selection_seal is None:
            raise SystemExit(
                "--holdout-replicate and --selection-seal are required for holdout"
            )
        if args.round_index is not None:
            raise SystemExit("holdout cannot accept --round-index")
        report = _run_holdout(args)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "schema": report["schema"],
                "mode": args.mode,
                "out": str(out),
                "source_only": True,
                "shifted_target_executed": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
