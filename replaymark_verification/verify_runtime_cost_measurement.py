from __future__ import annotations

"""Self-gate for measurement mechanics used by Runtime Cost Characterization."""

import argparse
import ast
import json
from pathlib import Path

from runtime_cost_measurement import (
    linear_fit,
    percentile,
    run_interleaved,
    summarize_ns,
    summary_is_ordered,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    args = parser.parse_args()

    if percentile([10.0, 20.0, 30.0, 40.0], 50) != 25.0:
        raise AssertionError("median interpolation is incorrect")
    if percentile([10.0, 20.0, 30.0, 40.0], 95) != 38.5:
        raise AssertionError("p95 interpolation is incorrect")

    summary = summarize_ns([1.0, 2.0, 3.0, 4.0, 5.0])
    if not summary_is_ordered(summary):
        raise AssertionError("summary percentile ordering failed")
    if summary["samples"] != 5:
        raise AssertionError("summary sample count failed")

    fit = linear_fit([(1.0, 7.0), (2.0, 12.0), (3.0, 17.0), (4.0, 22.0)])
    if abs(fit["slope_ns_per_task"] - 5.0) > 1e-12:
        raise AssertionError("linear-fit slope failed")
    if abs(fit["intercept_ns"] - 2.0) > 1e-12 or abs(fit["r2"] - 1.0) > 1e-12:
        raise AssertionError("linear-fit intercept/R2 failed")

    calls = {"a": 0, "b": 0}
    def a(index: int) -> int:
        calls["a"] += 1
        return index + 1
    def b(index: int) -> int:
        calls["b"] += 1
        return index + 2

    measured = run_interleaved(
        {"a": a, "b": b},
        case_count=4,
        rounds=20,
        inner=2,
        warmup_rounds=2,
        seed=7,
    )
    expected_calls = (2 + 20) * 2
    if calls != {"a": expected_calls, "b": expected_calls}:
        raise AssertionError(f"interleaved call accounting failed: {calls}")
    if not all(summary_is_ordered(value) for value in measured.values()):
        raise AssertionError("interleaved summaries are malformed")

    source = Path(__file__).with_name("runtime_cost_measurement.py")
    tree = ast.parse(source.read_text(encoding="utf-8"))
    forbidden = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = [alias.name.split(".", 1)[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            roots = [(node.module or "").split(".", 1)[0]]
        else:
            continue
        forbidden.extend(
            root for root in roots
            if root in {"replaymark", "agentmark", "paho"}
        )
    if forbidden:
        raise AssertionError(f"measurement helper imports production semantics: {forbidden}")

    result = {
        "schema": "replaymark.runtime-cost-measurement-self-gate.v1",
        "percentile_reference": True,
        "linear_fit_reference": True,
        "interleaved_call_accounting": True,
        "measurement_helper_production_imports": 0,
        "verdict": "PASS",
    }
    text = json.dumps(result, indent=2, sort_keys=True)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
