from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path


QUEUE_LIMITS = (511, 512, 767, 768)
REPLICAS = ("A", "B")
MODES = ("R1_TIMING", "TARGET_NATIVE", "R2_SEMANTIC")
EXPECTED_GENERATED = {
    "R1_TIMING": 512,
    "TARGET_NATIVE": 768,
    "R2_SEMANTIC": 768,
}
EXPECTED_VIOLATION = {
    "R1_TIMING": 1.0,
    "TARGET_NATIVE": 0.0,
    "R2_SEMANTIC": 0.0,
}
EXPECTED_VERIFY = {
    "R1_TIMING": 0,
    "TARGET_NATIVE": 128,
    "R2_SEMANTIC": 128,
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def expected_loss(queue_limit: int, mode: str) -> int:
    return max(EXPECTED_GENERATED[mode] - queue_limit, 0)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input-dir", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    root = Path(args.input_dir)
    paths = sorted(root.rglob("confirmatory_*_q*.json"))
    errors: list[str] = []
    reports: dict[tuple[str, int], dict] = {}
    hashes: dict[str, str] = {}

    for path in paths:
        try:
            d = json.loads(path.read_text())
        except Exception as e:
            errors.append(f"cannot parse {path}: {e}")
            continue
        if d.get("schema") != "replaymark.e3b.downstream.queue_confirmatory_raw.v1":
            errors.append(f"wrong schema {path}: {d.get('schema')}")
            continue
        key = (d.get("replica"), int(d.get("queue_limit")))
        if key in reports:
            errors.append(f"duplicate raw report for {key}")
            continue
        reports[key] = d
        hashes[path.name] = sha256(path)

    expected_keys = {(r, q) for r in REPLICAS for q in QUEUE_LIMITS}
    actual_keys = set(reports)
    if actual_keys != expected_keys:
        errors.append(
            f"coverage mismatch missing={sorted(expected_keys-actual_keys)} extra={sorted(actual_keys-expected_keys)}"
        )

    digests = {d.get("broker_image_digest") for d in reports.values()}
    versions = {d.get("broker_version_sys") for d in reports.values()}
    git_shas = {d.get("git_sha") for d in reports.values()}
    if len(digests) != 1 or None in digests:
        errors.append(f"broker digest mismatch: {sorted(map(str, digests))}")
    if versions != {"mosquitto version 2.1.2"}:
        errors.append(f"broker version mismatch: {sorted(map(str, versions))}")
    if len(git_shas) != 1 or None in git_shas:
        errors.append(f"raw artifacts do not share one git sha: {sorted(map(str, git_shas))}")

    all_cells = []
    per_queue = defaultdict(lambda: defaultdict(lambda: {"generated": 0, "delivered": 0, "loss": 0, "cells": 0}))

    for key in sorted(expected_keys):
        d = reports.get(key)
        if d is None:
            continue
        replica, q = key
        if d.get("status") != "CONFIRMATORY_RAW":
            errors.append(f"{key}: wrong status {d.get('status')}")
        if d.get("implementation_pass") is not True:
            errors.append(f"{key}: implementation gate failed")
        params = d.get("parameters", {})
        frozen_params = {
            "tasks": 128,
            "trials": 6,
            "wave_size": 32,
            "wave_period_ms": 300,
            "verify_ms": 100,
            "target_delay_ms": 150,
            "post_completion_gap_ms": 20.0,
            "task_timeout_ms": 1200,
            "max_queued_messages": q,
            "max_queued_bytes": 0,
            "max_inflight_messages": 20,
            "queue_qos0_messages": False,
            "drain_quiet_barrier_s": 0.75,
        }
        for name, expected in frozen_params.items():
            if params.get(name) != expected:
                errors.append(f"{key}: parameter {name}={params.get(name)!r}, expected {expected!r}")

        trials = d.get("trials", [])
        if len(trials) != 6:
            errors.append(f"{key}: trial count {len(trials)} != 6")
        seen_trial_ids = set()
        for tr in trials:
            tid = tr.get("trial")
            if tid in seen_trial_ids:
                errors.append(f"{key}: duplicate trial id {tid}")
            seen_trial_ids.add(tid)
            conditions = tr.get("conditions", {})
            if set(conditions) != set(MODES):
                errors.append(f"{key} trial {tid}: mode coverage {sorted(conditions)}")
                continue

            native = conditions["TARGET_NATIVE"]
            r2 = conditions["R2_SEMANTIC"]
            for field in ("generated_qos1", "delivered_qos1", "loss", "lossless", "verify_count"):
                if native.get(field) != r2.get(field):
                    errors.append(
                        f"{key} trial {tid}: native/R2 disagreement {field}: {native.get(field)} vs {r2.get(field)}"
                    )

            for mode in MODES:
                row = conditions[mode]
                generated = EXPECTED_GENERATED[mode]
                loss = expected_loss(q, mode)
                delivered = generated - loss
                lossless = loss == 0
                checks = {
                    "runner_implementation_pass": row.get("implementation_pass") is True,
                    "generated_exact": row.get("generated_qos1") == generated,
                    "observer_exact": row.get("generated_observer_count") == generated,
                    "delivered_exact": row.get("delivered_qos1") == delivered,
                    "loss_exact": row.get("loss") == loss,
                    "lossless_exact": row.get("lossless") is lossless,
                    "tasks_complete": row.get("success_rate") == 1.0,
                    "support_boundary": row.get("support_violation_fraction") == EXPECTED_VIOLATION[mode],
                    "verify_exact": row.get("verify_count") == EXPECTED_VERIFY[mode],
                    "session_present": row.get("collector_session_present") is True,
                    "no_collector_duplicates": row.get("collector_duplicate_deliveries") == 0,
                }
                for check, ok in checks.items():
                    if not ok:
                        errors.append(f"{key} trial {tid} {mode}: {check} failed")
                all_cells.append(
                    {
                        "replica": replica,
                        "queue_limit": q,
                        "trial": tid,
                        "mode": mode,
                        "generated": row.get("generated_qos1"),
                        "delivered": row.get("delivered_qos1"),
                        "loss": row.get("loss"),
                    }
                )
                agg = per_queue[q][mode]
                agg["generated"] += int(row.get("generated_qos1", 0))
                agg["delivered"] += int(row.get("delivered_qos1", 0))
                agg["loss"] += int(row.get("loss", 0))
                agg["cells"] += 1

    # Primary q=512 conclusion disagreement, across 2 replicas x 6 trials = 12 cells/mode.
    q512 = per_queue[512]
    primary_checks = {
        "r1_q512_lossless_all": q512["R1_TIMING"]["cells"] == 12 and q512["R1_TIMING"]["loss"] == 0,
        "native_q512_loses_exactly_3072": q512["TARGET_NATIVE"]["cells"] == 12 and q512["TARGET_NATIVE"]["loss"] == 256 * 12,
        "r2_q512_loses_exactly_3072": q512["R2_SEMANTIC"]["cells"] == 12 and q512["R2_SEMANTIC"]["loss"] == 256 * 12,
        "native_q512_loss_fraction_one_third": q512["TARGET_NATIVE"]["generated"] == 768 * 12 and q512["TARGET_NATIVE"]["loss"] * 3 == q512["TARGET_NATIVE"]["generated"],
    }

    boundary_checks = {
        "r1_q511_loses_one_per_trial": per_queue[511]["R1_TIMING"]["loss"] == 1 * 12,
        "r1_q512_lossless": per_queue[512]["R1_TIMING"]["loss"] == 0,
        "native_q767_loses_one_per_trial": per_queue[767]["TARGET_NATIVE"]["loss"] == 1 * 12,
        "native_q768_lossless": per_queue[768]["TARGET_NATIVE"]["loss"] == 0,
        "r2_q767_loses_one_per_trial": per_queue[767]["R2_SEMANTIC"]["loss"] == 1 * 12,
        "r2_q768_lossless": per_queue[768]["R2_SEMANTIC"]["loss"] == 0,
    }

    for name, ok in {**primary_checks, **boundary_checks}.items():
        if not ok:
            errors.append(f"certificate check failed: {name}")

    normalized_per_queue = {
        str(q): {mode: dict(per_queue[q][mode]) for mode in MODES}
        for q in QUEUE_LIMITS
    }
    certificate = {
        "schema": "replaymark.e3b.downstream.queue_confirmatory_certificate.v1",
        "status": "CONFIRMATORY_CERTIFICATE",
        "protocol": "replaymark_e3b_downstream/CONFIRMATORY_PROTOCOL.md",
        "input_files": sorted(hashes),
        "input_sha256": dict(sorted(hashes.items())),
        "git_sha": next(iter(git_shas)) if len(git_shas) == 1 else None,
        "broker_version_sys": next(iter(versions)) if len(versions) == 1 else None,
        "broker_image_digest": next(iter(digests)) if len(digests) == 1 else None,
        "coverage": {
            "replicas": list(REPLICAS),
            "queue_limits": list(QUEUE_LIMITS),
            "trials_per_replica_queue": 6,
            "conditions_per_trial": 3,
            "measured_condition_executions": len(all_cells),
            "task_executions": len(all_cells) * 128,
        },
        "per_queue": normalized_per_queue,
        "primary_checks": primary_checks,
        "boundary_checks": boundary_checks,
        "downstream_conclusion": {
            "r1_minimum_lossless_queue_messages": 512,
            "target_native_minimum_lossless_queue_messages": 768,
            "r2_minimum_lossless_queue_messages": 768,
            "target_native_over_r1_requirement_ratio": 1.5,
            "r1_underprovision_fraction_of_native_requirement": 1 / 3,
            "native_loss_fraction_at_r1_selected_q512": 1 / 3,
            "q512_r1_classification": "LOSSLESS",
            "q512_target_native_classification": "LOSSY",
            "q512_r2_classification": "LOSSY",
        },
        "errors": errors,
        "confirmation_pass": len(errors) == 0,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(certificate, indent=2, sort_keys=True) + "\n")
    print(json.dumps(certificate, indent=2, sort_keys=True))
    if errors:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
