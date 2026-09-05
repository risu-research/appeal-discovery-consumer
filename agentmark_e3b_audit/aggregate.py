from __future__ import annotations

import argparse
import glob
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path

CONDITIONS = ("P_prefix", "H_shadow", "R1_timing", "R2_semantic")
EPSILON = 0.05


def quantile(xs, q):
    if not xs:
        return None
    ys = sorted(float(x) for x in xs)
    pos = (len(ys) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    return ys[lo] if lo == hi else ys[lo] * (hi - pos) + ys[hi] * (pos - lo)


def exact_sign_p(diffs):
    pos = sum(d > 0 for d in diffs)
    neg = sum(d < 0 for d in diffs)
    n = pos + neg
    if n == 0:
        return 1.0
    k = min(pos, neg)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def hierarchical_bootstrap_ci(rows, a, b, *, draws=20000, seed=20260904):
    by_replica = defaultdict(list)
    for r in rows:
        by_replica[int(r["replica"])].append(r["rates"][a] - r["rates"][b])
    reps = sorted(by_replica)
    rng = random.Random(seed + sum(ord(c) for c in a + b))
    vals = []
    for _ in range(draws):
        chosen_reps = [rng.choice(reps) for _ in reps]
        sample = []
        for rep in chosen_reps:
            ds = by_replica[rep]
            sample.extend(rng.choice(ds) for _ in ds)
        vals.append(statistics.mean(sample))
    return [quantile(vals, 0.025), quantile(vals, 0.975)]


def paired_summary(rows, a, b):
    diffs = [r["rates"][a] - r["rates"][b] for r in rows]
    by_rep = defaultdict(list)
    for r, d in zip(rows, diffs):
        by_rep[int(r["replica"])].append(d)
    rep_means = {str(k): statistics.mean(v) for k, v in sorted(by_rep.items())}
    ci = hierarchical_bootstrap_ci(rows, a, b)
    return {
        "contrast": f"{a} - {b}",
        "blocks": len(diffs),
        "mean_difference": statistics.mean(diffs),
        "median_difference": statistics.median(diffs),
        "ci95_hierarchical_bootstrap": ci,
        "positive_blocks": sum(d > 0 for d in diffs),
        "negative_blocks": sum(d < 0 for d in diffs),
        "zero_blocks": sum(d == 0 for d in diffs),
        "exact_two_sided_sign_p": exact_sign_p(diffs),
        "replica_mean_differences": rep_means,
        "replicas_same_nonzero_direction": (
            sum(v > 0 for v in rep_means.values()) >= max(1, len(rep_means) - 1)
            or sum(v < 0 for v in rep_means.values()) >= max(1, len(rep_means) - 1)
        ),
    }


def ci_excludes_zero(summary):
    lo, hi = summary["ci95_hierarchical_bootstrap"]
    return lo > 0 or hi < 0


def concurrent_effect(summary):
    return (
        abs(summary["mean_difference"]) >= EPSILON
        and ci_excludes_zero(summary)
        and summary["replicas_same_nonzero_direction"]
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--inputs", required=True, help="glob for replica JSON files")
    p.add_argument("--out", required=True)
    a = p.parse_args()
    files = sorted(glob.glob(a.inputs))
    if len(files) < 4:
        raise RuntimeError(f"expected >=4 independent replicas, found {len(files)}")
    reports = [json.loads(Path(f).read_text()) for f in files]
    if not all(r.get("replica_pass") for r in reports):
        raise RuntimeError("one or more replica validity gates failed")

    rows_by_delay = defaultdict(list)
    for r in reports:
        rep = int(r["replica"])
        for b in r["main_blocks"]:
            rows_by_delay[int(b["delay_ms"])].append({
                "replica": rep,
                "block": int(b["block"]),
                "rates": {c: float(b["conditions"][c]["miss_rate"]) for c in CONDITIONS},
            })

    delays = {}
    for delay, rows in sorted(rows_by_delay.items()):
        delays[str(delay)] = {
            "blocks": len(rows),
            "condition_mean_miss_rates": {
                c: statistics.mean(r["rates"][c] for r in rows) for c in CONDITIONS
            },
            "P_minus_H": paired_summary(rows, "P_prefix", "H_shadow"),
            "R1_minus_H": paired_summary(rows, "R1_timing", "H_shadow"),
            "R2_minus_H": paired_summary(rows, "R2_semantic", "H_shadow"),
            "R2_minus_R1": paired_summary(rows, "R2_semantic", "R1_timing"),
            "P_minus_R1": paired_summary(rows, "P_prefix", "R1_timing"),
            "P_minus_R2": paired_summary(rows, "P_prefix", "R2_semantic"),
        }

    serial_rows = []
    for r in reports:
        s = r["serial_no_overlap_control"]
        serial_rows.append({
            "replica": int(r["replica"]),
            "rates": {c: float(s["conditions"][c]["miss_rate"]) for c in CONDITIONS},
        })
    serial = {
        "replicas": len(serial_rows),
        "condition_mean_miss_rates": {
            c: statistics.mean(r["rates"][c] for r in serial_rows) for c in CONDITIONS
        },
        "per_replica": serial_rows,
        "mean_differences": {
            "P_minus_H": statistics.mean(r["rates"]["P_prefix"] - r["rates"]["H_shadow"] for r in serial_rows),
            "R1_minus_H": statistics.mean(r["rates"]["R1_timing"] - r["rates"]["H_shadow"] for r in serial_rows),
            "R2_minus_H": statistics.mean(r["rates"]["R2_semantic"] - r["rates"]["H_shadow"] for r in serial_rows),
        },
    }

    d80 = delays["80"]
    measurement_stable = (
        abs(d80["P_minus_H"]["mean_difference"]) < EPSILON
        and not ci_excludes_zero(d80["P_minus_H"])
    )
    r1_effect = concurrent_effect(d80["R1_minus_H"])
    r2_effect = concurrent_effect(d80["R2_minus_H"])
    serial_r1_small = abs(serial["mean_differences"]["R1_minus_H"]) < EPSILON
    serial_r2_small = abs(serial["mean_differences"]["R2_minus_H"]) < EPSILON

    if not measurement_stable:
        verdict = "MEASUREMENT_OR_CONTROL_FLOW_CONFOUND"
    elif (r1_effect or r2_effect) and ((not r1_effect or serial_r1_small) and (not r2_effect or serial_r2_small)):
        verdict = "CONCURRENT_WORKLOAD_ENDOGENEITY_SUPPORTED_IN_HARNESS"
    elif not r1_effect and not r2_effect:
        verdict = "LEGACY_DISCREPANCY_NOT_REPLICATED"
    else:
        verdict = "UNRESOLVED_EFFECT_NOT_SPECIFIC_TO_CONCURRENT_WORKLOAD"

    report = {
        "schema": "agentmark.e3b.near_threshold_causal_audit.aggregate.v1",
        "audit": "E3b 80ms near-threshold replicated causal audit",
        "replicas": len(reports),
        "replica_ids": sorted(int(r["replica"]) for r in reports),
        "precommitted_effect_size_epsilon": EPSILON,
        "delays": delays,
        "serial_no_overlap_control_80ms": serial,
        "decision": {
            "measurement_path_stable_P_vs_H": measurement_stable,
            "concurrent_R1_vs_H_effect": r1_effect,
            "concurrent_R2_vs_H_effect": r2_effect,
            "serial_R1_vs_H_below_epsilon": serial_r1_small,
            "serial_R2_vs_H_below_epsilon": serial_r2_small,
            "verdict": verdict,
        },
        "validity": {
            "all_replica_gates_pass": all(r["replica_pass"] for r in reports),
            "all_brokers_mosquitto_2_1_2": all("mosquitto version 2.1.2" in (r.get("broker_version_sys") or "").lower() for r in reports),
            "all_sources_clean_at_frozen_100ms": all(r["source_cleanliness"]["controller_valid_at_fixed_verify"] for r in reports),
        },
        "input_files": [Path(f).name for f in files],
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"verdict": verdict, "decision": report["decision"], "miss80": d80["condition_mean_miss_rates"], "serial80": serial["condition_mean_miss_rates"]}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
