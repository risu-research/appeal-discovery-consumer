from __future__ import annotations

"""Measurement-only helpers for ReplayMark runtime cost characterization.

This module contains no ReplayMark semantics. It provides deterministic
interleaved timing, percentile summaries, and simple linear scaling summaries.
"""

from collections.abc import Callable, Mapping
import gc
import math
import random
import statistics
import time
from typing import Any


def percentile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    if not 0.0 <= q <= 100.0:
        raise ValueError("q must be in [0, 100]")
    xs = sorted(float(value) for value in values)
    pos = (len(xs) - 1) * q / 100.0
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return xs[lo]
    return xs[lo] * (hi - pos) + xs[hi] * (pos - lo)


def summarize_ns(values: list[float]) -> dict[str, float | int]:
    if not values:
        raise ValueError("summary requires at least one sample")
    xs = [float(value) for value in values]
    med = statistics.median(xs)
    mad = statistics.median(abs(value - med) for value in xs)
    mean = statistics.fmean(xs)
    stdev = statistics.pstdev(xs) if len(xs) > 1 else 0.0
    return {
        "samples": len(xs),
        "min_ns": min(xs),
        "p50_ns": percentile(xs, 50),
        "p95_ns": percentile(xs, 95),
        "p99_ns": percentile(xs, 99),
        "max_ns": max(xs),
        "mean_ns": mean,
        "stdev_ns": stdev,
        "mad_ns": mad,
        "p50_us": percentile(xs, 50) / 1000.0,
        "p95_us": percentile(xs, 95) / 1000.0,
        "p99_us": percentile(xs, 99) / 1000.0,
    }


def timer_probe(samples: int = 4096) -> dict[str, float | int]:
    if samples < 32:
        raise ValueError("timer probe requires at least 32 samples")
    deltas: list[float] = []
    for _ in range(samples):
        start = time.perf_counter_ns()
        end = time.perf_counter_ns()
        deltas.append(float(end - start))
    return summarize_ns(deltas)


def run_interleaved(
    stage_functions: Mapping[str, Callable[[int], Any]],
    *,
    case_count: int,
    rounds: int,
    inner: int,
    warmup_rounds: int = 16,
    seed: int = 20260907,
) -> dict[str, dict[str, float | int]]:
    """Measure stages in deterministic randomized order.

    Each timing sample is an average over ``inner`` calls so timer overhead is
    amortized. Stage order is shuffled each round to reduce monotonic thermal or
    scheduler drift. Case indices rotate deterministically across the corpus.
    """

    if not stage_functions:
        raise ValueError("at least one stage is required")
    if case_count < 1 or rounds < 20 or inner < 1 or warmup_rounds < 1:
        raise ValueError("invalid benchmark dimensions")

    names = tuple(stage_functions)
    rng = random.Random(seed)
    sink: Any = None

    for warmup in range(warmup_rounds):
        order = list(names)
        rng.shuffle(order)
        for name in order:
            fn = stage_functions[name]
            for offset in range(inner):
                sink = fn((warmup * inner + offset) % case_count)

    samples: dict[str, list[float]] = {name: [] for name in names}
    gc_was_enabled = gc.isenabled()
    gc.disable()
    try:
        for round_index in range(rounds):
            order = list(names)
            rng.shuffle(order)
            base = round_index * inner
            for name in order:
                fn = stage_functions[name]
                start = time.perf_counter_ns()
                for offset in range(inner):
                    sink = fn((base + offset) % case_count)
                elapsed = time.perf_counter_ns() - start
                samples[name].append(float(elapsed) / inner)
    finally:
        if gc_was_enabled:
            gc.enable()

    if sink is None:
        raise AssertionError("benchmark stage results were not evaluated")
    return {name: summarize_ns(values) for name, values in samples.items()}


def linear_fit(points: list[tuple[float, float]]) -> dict[str, float]:
    """Ordinary least-squares y = intercept + slope*x with R^2."""

    if len(points) < 2:
        raise ValueError("linear fit requires at least two points")
    xs = [float(x) for x, _ in points]
    ys = [float(y) for _, y in points]
    x_mean = statistics.fmean(xs)
    y_mean = statistics.fmean(ys)
    denom = sum((x - x_mean) ** 2 for x in xs)
    if denom == 0:
        raise ValueError("linear fit x values must vary")
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denom
    intercept = y_mean - slope * x_mean
    fitted = [intercept + slope * x for x in xs]
    ss_res = sum((y - yhat) ** 2 for y, yhat in zip(ys, fitted))
    ss_tot = sum((y - y_mean) ** 2 for y in ys)
    r2 = 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot
    return {"slope_ns_per_task": slope, "intercept_ns": intercept, "r2": r2}


def summary_is_ordered(summary: Mapping[str, float | int]) -> bool:
    return (
        float(summary["min_ns"])
        <= float(summary["p50_ns"])
        <= float(summary["p95_ns"])
        <= float(summary["p99_ns"])
        <= float(summary["max_ns"])
    )


__all__ = (
    "linear_fit",
    "percentile",
    "run_interleaved",
    "summarize_ns",
    "summary_is_ordered",
    "timer_probe",
)
