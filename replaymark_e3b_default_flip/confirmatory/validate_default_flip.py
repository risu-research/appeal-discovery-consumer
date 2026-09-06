from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path


BATCHES = (166, 167, 250, 251)
REPLICAS = ("A", "B")
MODES = ("R1_TIMING", "TARGET_NATIVE", "R2_SEMANTIC")
EXPECTED_GENERATED_PER_TASK = {
    "R1_TIMING": 4,
    "TARGET_NATIVE": 6,
    "R2_SEMANTIC": 6,
}
EXPECTED_VIOLATION = {
    "R1_TIMING": 1.0,
    "TARGET_NATIVE": 0.0,
    "R2_SEMANTIC": 0.0,
}
FORBIDDEN_QUEUE_DIRECTIVES = {
    "max_queued_messages",
    "max_queued_bytes",
    "max_inflight_messages",
    "queue_qos0_messages",
}
Q = 1000


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_directives(path: Path) -> tuple[list[str], list[str]]:
    text = path.read_text()
    directives = []
    forbidden = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name = stripped.split(None, 1)[0]
        directives.append(name)
        if name in FORBIDDEN_QUEUE_DIRECTIVES:
            forbidden.append(name)
    return directives, sorted(set(forbidden))


def expected(mode: str, n: int) -> tuple[int, int, int]:
    generated = EXPECTED_GENERATED_PER_TASK[mode] * n
    delivered = min(generated, Q)
    loss = generated - delivered
    return generated, delivered, loss


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input-dir", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    root = Path(args.input_dir)
    json_paths = sorted(root.rglob("default_flip_*_n*.json"))
    config_paths = sorted(root.rglob("mosquitto_default_queue_*_n*.conf"))

    errors: list[str] = []
    reports: dict[tuple[str, int], dict] = {}
    configs: dict[tuple[str, int], Path] = {}
    input_hashes: dict[str, str] = {}

    for path in json_paths:
        d = json.loads(path.read_text())
        if d.get("schema") != "replaymark.e3b.documented_default_capacity_flip.raw.v1":
            errors.append(f"wrong schema: {path}")
            continue
        key = (str(d.get("replica")), int(d.get("batch_size")))
        if key in reports:
            errors.append(f"duplicate raw report {key}")
            continue
        reports[key] = d
        input_hashes[path.name] = sha256(path)

    for path in config_paths:
        stem = path.stem
        # mosquitto_default_queue_A_n166
        parts = stem.split("_")
        try:
            replica = parts[-2]
            n = int(parts[-1][1:])
        except Exception:
            errors.append(f"cannot parse config identity: {path.name}")
            continue
        key = (replica, n)
        if key in configs:
            errors.append(f"duplicate config {key}")
            continue
        configs[key] = path
        input_hashes[path.name] = sha256(path)

    expected_keys = {(r, n) for r in REPLICAS for n in BATCHES}
    if set(reports) != expected_keys:
        errors.append(
            f"raw coverage mismatch missing={sorted(expected_keys-set(reports))} extra={sorted(set(reports)-expected_keys)}"
        )
    if set(configs) != expected_keys:
        errors.append(
            f"config coverage mismatch missing={sorted(expected_keys-set(configs))} extra={sorted(set(configs)-expected_keys)}"
        )

    digests = {d.get("broker_image_digest") for d in reports.values()}
    versions = {d.get("broker_version_sys") for d in reports.values()}
    git_shas = {d.get("git_sha") for d in reports.values()}
    if len(digests) != 1 or None in digests:
        errors.append(f"broker digest mismatch: {sorted(map(str, digests))}")
    if versions != {"mosquitto version 2.1.2"}:
        errors.append(f"broker version mismatch: {sorted(map(str, versions))}")
    if len(git_shas) != 1 or None in git_shas:
        errors.append(f"git sha mismatch: {sorted(map(str, git_shas))}")

    per_batch = defaultdict(
        lambda: defaultdict(lambda: {"cells": 0, "generated": 0, "delivered": 0, "loss": 0})
    )
    measured_cells = 0
    task_executions = 0

    for key in sorted(expected_keys):
        report = reports.get(key)
        config = configs.get(key)
        if report is None or config is None:
            continue
        replica, n = key

        directives, forbidden = parse_directives(config)
        config_hash = sha256(config)
        if forbidden:
            errors.append(f"{key}: forbidden queue directives {forbidden}")
        att = report.get("config_attestation", {})
        if att.get("sha256") != config_hash:
            errors.append(f"{key}: config hash mismatch raw={att.get('sha256')} actual={config_hash}")
        if att.get("forbidden_queue_directives_found") != []:
            errors.append(f"{key}: runner reported forbidden queue directive")
        if att.get("default_queue_policy_attested") is not True:
            errors.append(f"{key}: runner config attestation false")
        if report.get("documented_default_max_queued_messages") != 1000:
            errors.append(f"{key}: default queue count field not 1000")
        if report.get("queue_capacity_explicitly_overridden") is not False:
            errors.append(f"{key}: report says queue capacity overridden")
        if report.get("implementation_pass") is not True:
            errors.append(f"{key}: implementation gate failed")

        params = report.get("parameters", {})
        frozen = {
            "tasks": n,
            "trials": 6,
            "wave_size": 32,
            "wave_period_ms": 300,
            "verify_ms": 100,
            "target_delay_ms": 150,
            "post_completion_gap_ms": 20.0,
            "task_timeout_ms": 1200,
            "drain_quiet_barrier_s": 0.75,
        }
        for name, value in frozen.items():
            if params.get(name) != value:
                errors.append(f"{key}: parameter {name}={params.get(name)!r}, expected {value!r}")

        trials = report.get("trials", [])
        if len(trials) != 6:
            errors.append(f"{key}: trial count {len(trials)} != 6")
        trial_ids = set()
        for tr in trials:
            tid = tr.get("trial")
            if tid in trial_ids:
                errors.append(f"{key}: duplicate trial id {tid}")
            trial_ids.add(tid)
            conditions = tr.get("conditions", {})
            if set(conditions) != set(MODES):
                errors.append(f"{key} trial {tid}: mode coverage {sorted(conditions)}")
                continue

            native = conditions["TARGET_NATIVE"]
            r2 = conditions["R2_SEMANTIC"]
            for field in (
                "generated_qos1",
                "delivered_qos1",
                "loss",
                "lossless",
                "verify_count",
                "support_violation_fraction",
            ):
                if native.get(field) != r2.get(field):
                    errors.append(
                        f"{key} trial {tid}: native/R2 disagreement {field}: {native.get(field)} vs {r2.get(field)}"
                    )

            for mode in MODES:
                row = conditions[mode]
                generated, delivered, loss = expected(mode, n)
                expected_verify = 0 if mode == "R1_TIMING" else n
                checks = {
                    "runner_implementation_pass": row.get("implementation_pass") is True,
                    "generated_exact": row.get("generated_qos1") == generated,
                    "observer_exact": row.get("generated_observer_count") == generated,
                    "delivered_exact": row.get("delivered_qos1") == delivered,
                    "loss_exact": row.get("loss") == loss,
                    "lossless_exact": row.get("lossless") is (loss == 0),
                    "tasks_complete": row.get("success_rate") == 1.0,
                    "support_boundary": row.get("support_violation_fraction") == EXPECTED_VIOLATION[mode],
                    "verify_exact": row.get("verify_count") == expected_verify,
                    "session_present": row.get("collector_session_present") is True,
                    "no_collector_duplicates": row.get("collector_duplicate_deliveries") == 0,
                }
                for name, ok in checks.items():
                    if not ok:
                        errors.append(f"{key} trial {tid} {mode}: {name} failed")
                agg = per_batch[n][mode]
                agg["cells"] += 1
                agg["generated"] += int(row.get("generated_qos1", 0))
                agg["delivered"] += int(row.get("delivered_qos1", 0))
                agg["loss"] += int(row.get("loss", 0))
                measured_cells += 1
                task_executions += n

    primary_checks = {
        "r1_n250_lossless_all": per_batch[250]["R1_TIMING"]["cells"] == 12
        and per_batch[250]["R1_TIMING"]["loss"] == 0,
        "native_n250_loses_exactly_6000": per_batch[250]["TARGET_NATIVE"]["cells"] == 12
        and per_batch[250]["TARGET_NATIVE"]["loss"] == 500 * 12,
        "r2_n250_loses_exactly_6000": per_batch[250]["R2_SEMANTIC"]["cells"] == 12
        and per_batch[250]["R2_SEMANTIC"]["loss"] == 500 * 12,
        "native_n250_loss_fraction_one_third": per_batch[250]["TARGET_NATIVE"]["generated"] == 1500 * 12
        and per_batch[250]["TARGET_NATIVE"]["loss"] * 3
        == per_batch[250]["TARGET_NATIVE"]["generated"],
    }
    boundary_checks = {
        "r1_n250_lossless": per_batch[250]["R1_TIMING"]["loss"] == 0,
        "r1_n251_loses_four_per_trial": per_batch[251]["R1_TIMING"]["loss"] == 4 * 12,
        "native_n166_lossless": per_batch[166]["TARGET_NATIVE"]["loss"] == 0,
        "native_n167_loses_two_per_trial": per_batch[167]["TARGET_NATIVE"]["loss"] == 2 * 12,
        "r2_n166_lossless": per_batch[166]["R2_SEMANTIC"]["loss"] == 0,
        "r2_n167_loses_two_per_trial": per_batch[167]["R2_SEMANTIC"]["loss"] == 2 * 12,
    }
    for name, ok in {**primary_checks, **boundary_checks}.items():
        if not ok:
            errors.append(f"certificate check failed: {name}")

    normalized = {
        str(n): {mode: dict(per_batch[n][mode]) for mode in MODES}
        for n in BATCHES
    }
    certificate = {
        "schema": "replaymark.e3b.documented_default_capacity_flip.certificate.v1",
        "status": "CONFIRMATORY_CERTIFICATE",
        "protocol": "replaymark_e3b_default_flip/DEFAULT_FLIP_PROTOCOL.md",
        "input_sha256": dict(sorted(input_hashes.items())),
        "git_sha": next(iter(git_shas)) if len(git_shas) == 1 else None,
        "broker_version_sys": next(iter(versions)) if len(versions) == 1 else None,
        "broker_image_digest": next(iter(digests)) if len(digests) == 1 else None,
        "documented_default_max_queued_messages": 1000,
        "coverage": {
            "replicas": list(REPLICAS),
            "batch_sizes": list(BATCHES),
            "trials_per_replica_batch": 6,
            "conditions_per_trial": 3,
            "measured_condition_executions": measured_cells,
            "task_executions": task_executions,
        },
        "per_batch": normalized,
        "primary_checks": primary_checks,
        "boundary_checks": boundary_checks,
        "downstream_conclusion": {
            "r1_maximum_lossless_batch_tasks": 250,
            "target_native_maximum_lossless_batch_tasks": 166,
            "r2_maximum_lossless_batch_tasks": 166,
            "r1_overstates_safe_batch_by_tasks": 84,
            "native_loss_fraction_at_r1_selected_n250": 1 / 3,
            "n250_r1_classification": "LOSSLESS",
            "n250_target_native_classification": "LOSSY",
            "n250_r2_classification": "LOSSY",
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
