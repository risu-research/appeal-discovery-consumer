from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import time
import uuid
from pathlib import Path

from experiment import Harness, _sys_delta, percentile
from ladder import offers, pub, sleep_until, source_task

PUB = "$SYS/broker/publish/messages/received"
CONDITIONS = ("P_prefix", "H_shadow", "R1_timing", "R2_semantic")
WILLIAMS = (
    ("P_prefix", "H_shadow", "R2_semantic", "R1_timing"),
    ("H_shadow", "R1_timing", "P_prefix", "R2_semantic"),
    ("R1_timing", "R2_semantic", "H_shadow", "P_prefix"),
    ("R2_semantic", "P_prefix", "R1_timing", "H_shadow"),
)


def wait_event_until(h: Harness, device: str, deadline_ns: int, *, after_ns: int, cause: str | None = None):
    """Wait for one matching state event, optionally filtering by device-side cause."""
    with h.cv:
        while True:
            candidates = [
                e
                for e in h.state_events.get(device, [])
                if after_ns <= e["recv_mono_ns"] <= deadline_ns
                and bool(e.get("on"))
                and (cause is None or e.get("cause") == cause)
            ]
            if candidates:
                return min(candidates, key=lambda e: e["recv_mono_ns"])
            remaining_ns = deadline_ns - time.monotonic_ns()
            if remaining_ns <= 0:
                return None
            h.cv.wait(remaining_ns / 1e9)


def pct(xs, q):
    ys = [float(x) for x in xs if x is not None]
    return percentile(ys, q) if ys else None


def mean(xs):
    ys = [float(x) for x in xs if x is not None]
    return statistics.mean(ys) if ys else None


def audit_task(h: Harness, condition: str, i: int, prefix: str, offer_ns: int,
               verify_ms: float, gap_ms: float, timeout_ms: int, wave_size: int):
    sleep_until(offer_ns)
    t0 = time.monotonic_ns()
    a = f"{prefix}-{i}-a"
    b = f"{prefix}-{i}-b"
    td = t0 + int(timeout_ms * 1e6)
    vd = t0 + int(verify_ms * 1e6)
    ops = []

    a1 = pub(h, f"agentmark/{a}/command", {"on": True})
    ops.append("ACT1")
    first_command = None
    resolved = None
    miss = False
    a2 = None

    if condition == "P_prefix":
        first_command = wait_event_until(h, a, vd, after_ns=a1, cause="command")
        if first_command is None:
            miss = True
            first_command = wait_event_until(h, a, td, after_ns=a1, cause="command")
        resolved = first_command

    elif condition == "H_shadow":
        # Same wait/classification path as R1, but deliberately suppress ACT2.
        first_command = wait_event_until(h, a, td, after_ns=a1, cause="command")
        miss = first_command is None or first_command["recv_mono_ns"] > vd
        resolved = first_command
        if resolved is not None:
            sleep_until(resolved["recv_mono_ns"] + int(gap_ms * 1e6))

    elif condition == "R1_timing":
        first_command = wait_event_until(h, a, td, after_ns=a1, cause="command")
        miss = first_command is None or first_command["recv_mono_ns"] > vd
        resolved = first_command
        if resolved is not None:
            sleep_until(resolved["recv_mono_ns"] + int(gap_ms * 1e6))
            a2 = pub(h, f"agentmark/{b}/command", {"on": True})
            ops.append("ACT2")
            wait_event_until(h, b, td, after_ns=a2, cause="command")

    elif condition == "R2_semantic":
        first_command = wait_event_until(h, a, vd, after_ns=a1, cause="command")
        miss = first_command is None
        resolved = first_command
        if miss:
            q = pub(h, f"agentmark/{a}/query", {})
            ops.append("VERIFY")
            # Preserve decisive R2 semantics: VERIFY may resolve through either
            # the delayed command state or the immediate query state.
            resolved = h.wait_state_on_until(a, td, after_ns=q)
            # Recover command-caused timing separately for causal analysis.
            if first_command is None:
                first_command = wait_event_until(h, a, td, after_ns=a1, cause="command")
        if resolved is not None:
            sleep_until(resolved["recv_mono_ns"] + int(gap_ms * 1e6))
            a2 = pub(h, f"agentmark/{b}/command", {"on": True})
            ops.append("ACT2")
            wait_event_until(h, b, td, after_ns=a2, cause="command")
    else:
        raise ValueError(condition)

    first_ns = first_command["recv_mono_ns"] if first_command is not None else None
    first_from_t0 = (first_ns - t0) / 1e6 if first_ns is not None else None
    first_from_pub = (first_ns - a1) / 1e6 if first_ns is not None else None
    return {
        "task_id": i,
        "wave": i // wave_size,
        "condition": condition,
        "success": resolved is not None,
        "decision_miss": bool(miss),
        "verify_count": ops.count("VERIFY"),
        "ops": ops,
        "offer_lag_ms": (t0 - offer_ns) / 1e6,
        "act1_publish_offset_ms": (a1 - t0) / 1e6,
        "first_command_from_t0_ms": first_from_t0,
        "first_command_from_publish_ms": first_from_pub,
        "first_command_deadline_margin_ms": (verify_ms - first_from_t0) if first_from_t0 is not None else None,
        "act2_offset_ms": (a2 - t0) / 1e6 if a2 is not None else None,
    }


def summarize_rows(rows):
    n = len(rows)
    misses = sum(int(r["decision_miss"]) for r in rows)
    first = [r["first_command_from_t0_ms"] for r in rows if r["first_command_from_t0_ms"] is not None]
    pubfirst = [r["first_command_from_publish_ms"] for r in rows if r["first_command_from_publish_ms"] is not None]
    offerlags = [r["offer_lag_ms"] for r in rows]
    by_wave = {}
    for r in rows:
        w = str(r["wave"])
        z = by_wave.setdefault(w, {"tasks": 0, "misses": 0, "latencies_ms": []})
        z["tasks"] += 1
        z["misses"] += int(r["decision_miss"])
        if r["first_command_from_t0_ms"] is not None:
            z["latencies_ms"].append(r["first_command_from_t0_ms"])
    wave_summary = {
        w: {
            "tasks": z["tasks"],
            "misses": z["misses"],
            "miss_rate": z["misses"] / z["tasks"],
            "first_command_p50_ms": pct(z["latencies_ms"], 50),
            "first_command_p99_ms": pct(z["latencies_ms"], 99),
        }
        for w, z in sorted(by_wave.items(), key=lambda kv: int(kv[0]))
    }
    return {
        "tasks": n,
        "success_rate": sum(int(r["success"]) for r in rows) / n,
        "misses": misses,
        "miss_rate": misses / n,
        "verify_count": sum(int(r["verify_count"]) for r in rows),
        "first_command_mean_ms": mean(first),
        "first_command_p50_ms": pct(first, 50),
        "first_command_p95_ms": pct(first, 95),
        "first_command_p99_ms": pct(first, 99),
        "first_command_from_publish_mean_ms": mean(pubfirst),
        "offer_lag_p99_ms": pct(offerlags, 99),
        "wave_summary": wave_summary,
    }


def expected_publish(condition: str, n: int, miss_count: int):
    if condition in ("P_prefix", "H_shadow"):
        return 2 * n
    if condition == "R1_timing":
        return 4 * n
    if condition == "R2_semantic":
        return 4 * n + 2 * miss_count
    raise ValueError(condition)


def run_condition(h: Harness, condition: str, delay_ms: int, *, tasks: int, wave_size: int,
                  wave_period_ms: int, verify_ms: float, gap_ms: float, timeout_ms: int,
                  tag: str):
    h.set_state_delay(delay_ms)
    before = h.fresh_sys_snapshot()
    prefix = f"ca-{tag}-{condition}-{uuid.uuid4().hex[:5]}"
    rows = offers(
        tasks,
        wave_size,
        wave_period_ms,
        lambda i, o: audit_task(h, condition, i, prefix, o, verify_ms, gap_ms, timeout_ms, wave_size),
    )
    # Drain late scheduled publishes before the fresh counter barrier.
    time.sleep(max(delay_ms, int(verify_ms)) / 1000.0 + 0.08)
    after = h.fresh_sys_snapshot()
    sys_delta = _sys_delta(before, after)
    summary = summarize_rows(rows)
    observed = float(sys_delta.get(PUB, float("nan")))
    expected = float(expected_publish(condition, tasks, summary["misses"]))
    summary.update({
        "condition": condition,
        "delay_ms": delay_ms,
        "sys": sys_delta,
        "publish_conservation": {
            "expected": expected,
            "observed": observed,
            "error": observed - expected if math.isfinite(observed) else None,
            "exact": math.isfinite(observed) and observed == expected,
        },
        "rows": rows,
    })
    return summary


def block_order(replica: int, delay_index: int, block: int):
    # Williams square balances treatment position and first-order carryover.
    return list(WILLIAMS[(block + replica + 2 * delay_index) % len(WILLIAMS)])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--broker", default=os.getenv("BROKER_HOST", "mosquitto"))
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--replica", type=int, required=True)
    p.add_argument("--verify-ms", type=float, default=100.0)
    p.add_argument("--delays-ms", default="80,95")
    p.add_argument("--blocks", type=int, default=8)
    p.add_argument("--tasks", type=int, default=128)
    p.add_argument("--wave-size", type=int, default=32)
    p.add_argument("--wave-period-ms", type=int, default=300)
    p.add_argument("--gap-ms", type=float, default=20.0)
    p.add_argument("--timeout-ms", type=int, default=1200)
    p.add_argument("--serial-tasks", type=int, default=20)
    p.add_argument("--serial-period-ms", type=int, default=300)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    delays = [int(x) for x in a.delays_ms.split(",") if x.strip()]
    if a.tasks % a.wave_size:
        raise ValueError("tasks must be divisible by wave size")
    if 80 not in delays:
        raise ValueError("80ms must remain in the audit")

    h = Harness(a.broker, a.port)
    try:
        version = h.broker_version()
        # Fixed 100ms decision boundary is preregistered from the promoted E3b run.
        # Source is checked only for continued cleanliness; it cannot move the boundary.
        h.set_state_delay(0)
        src = offers(
            a.tasks,
            a.wave_size,
            a.wave_period_ms,
            lambda i, o: source_task(h, i, f"audit-source-r{a.replica}-{uuid.uuid4().hex[:5]}", o, a.gap_ms, a.timeout_ms),
        )
        source_first = [float(x["first_completion_offset_ms"]) for x in src]
        source = {
            "tasks": len(src),
            "first_completion_p99_ms": pct(source_first, 99),
            "first_completion_max_ms": max(source_first),
            "controller_valid_at_fixed_verify": all(x <= a.verify_ms for x in source_first),
        }

        blocks = []
        for di, delay in enumerate(delays):
            for b in range(a.blocks):
                order = block_order(a.replica, di, b)
                row = {"delay_ms": delay, "block": b, "order": order, "conditions": {}}
                for condition in order:
                    row["conditions"][condition] = run_condition(
                        h,
                        condition,
                        delay,
                        tasks=a.tasks,
                        wave_size=a.wave_size,
                        wave_period_ms=a.wave_period_ms,
                        verify_ms=a.verify_ms,
                        gap_ms=a.gap_ms,
                        timeout_ms=a.timeout_ms,
                        tag=f"r{a.replica}-d{delay}-b{b}",
                    )
                blocks.append(row)

        # No-overlap causal control: one task per 300ms wave at 80ms delay means
        # downstream traffic completes before the next task is offered.
        serial_order = list(WILLIAMS[a.replica % len(WILLIAMS)])
        serial = {"delay_ms": 80, "order": serial_order, "conditions": {}}
        for condition in serial_order:
            serial["conditions"][condition] = run_condition(
                h,
                condition,
                80,
                tasks=a.serial_tasks,
                wave_size=1,
                wave_period_ms=a.serial_period_ms,
                verify_ms=a.verify_ms,
                gap_ms=a.gap_ms,
                timeout_ms=a.timeout_ms,
                tag=f"serial-r{a.replica}",
            )
    finally:
        h.close()

    checks = {
        "broker_is_mosquitto_2_1_2": bool(version and "mosquitto version 2.1.2" in version.lower()),
        "source_clean_at_frozen_100ms": source["controller_valid_at_fixed_verify"],
        "all_main_publish_conservation_exact": all(
            c["publish_conservation"]["exact"] for b in blocks for c in b["conditions"].values()
        ),
        "all_serial_publish_conservation_exact": all(
            c["publish_conservation"]["exact"] for c in serial["conditions"].values()
        ),
        "all_conditions_successful": all(
            c["success_rate"] == 1.0 for b in blocks for c in b["conditions"].values()
        ) and all(c["success_rate"] == 1.0 for c in serial["conditions"].values()),
    }
    report = {
        "schema": "agentmark.e3b.near_threshold_causal_audit.replica.v1",
        "audit": "E3b 80ms near-threshold replicated causal audit",
        "replica": a.replica,
        "broker_version_sys": version,
        "preregistered_hypotheses": {
            "H_noise": "legacy prefix/live discrepancy disappears under balanced repeated blocks and independent runners",
            "H_measurement": "P_prefix differs from H_shadow despite identical MQTT workload, implicating runner/control-flow measurement",
            "H_endogeneity": "H_shadow vs live differs at concurrency 32, is stable across runners, and attenuates under no-overlap wave_size=1 control",
        },
        "parameters": {**vars(a), "delays_ms_parsed": delays},
        "source_cleanliness": source,
        "main_blocks": blocks,
        "serial_no_overlap_control": serial,
        "checks": checks,
        "replica_pass": all(checks.values()),
    }
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    compact = {
        "replica": a.replica,
        "pass": report["replica_pass"],
        "source": source,
        "miss_rates": [
            {
                "delay": b["delay_ms"],
                "block": b["block"],
                **{k: v["miss_rate"] for k, v in b["conditions"].items()},
            }
            for b in blocks
        ],
        "serial_80": {k: v["miss_rate"] for k, v in serial["conditions"].items()},
    }
    print(json.dumps(compact, indent=2, sort_keys=True))
    if not report["replica_pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
