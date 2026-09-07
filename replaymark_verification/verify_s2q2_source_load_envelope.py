from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "replaymark" / "S2P2_SOURCE_QUALIFIED_LOAD_ENVELOPE.json"
RUNNER = ROOT / "agentmark_e3b_lab" / "e3_mqtt" / "app" / "replaymark_s2q2_source_load_envelope.py"
WORKFLOW = ROOT / ".github" / "workflows" / "replaymark-runtime-gate-s2q2-source-load-envelope.yml"

P2_HEAD = "22ec2da2e62c1fa7e9d1a5e02ff676188d90ab5e"
P2_PROTOCOL_BLOB = "c7e3103adfe2a3803e506e7c20674ad32edb058f"
P2_VERIFIER_BLOB = "0e3ad3a771dcef0445232308f69c933dffe61c67"
Q1_HEAD = "2a7e994810ae9c88d626d50fea1b06a7eb3550b5"
S0_OPTIMIZATION_AUTHORITY = "25d317392b9ce6aaaedc190ef6aff8bc38d555b5"
EXPECTED_SCREENING_SCHEDULE_SHA256 = "7850522b51e6f62130685835fb487bfe94cca9e122a79e11f64d5232bbf648d7"

EXPECTED_INCREMENT = {
    ".github/workflows/replaymark-runtime-gate-s2q2-source-load-envelope.yml",
    "agentmark_e3b_lab/e3_mqtt/app/replaymark_s2q2_source_load_envelope.py",
    "replaymark/S2Q2_SOURCE_LOAD_ENVELOPE_AND_HOLDOUT.md",
    "replaymark_verification/verify_s2q2_source_load_envelope.py",
}
P2_AUTHORITY_FILES = {
    ".github/workflows/replaymark-runtime-gate-s2p2-source-qualified-load-envelope-protocol.yml",
    "replaymark/S2P2_SOURCE_QUALIFIED_LOAD_ENVELOPE.json",
    "replaymark/S2P2_SOURCE_QUALIFIED_LOAD_ENVELOPE.md",
    "replaymark_verification/verify_s2p2_source_qualified_load_envelope.py",
}
Q1_AUTHORITY_FILES = {
    ".github/workflows/replaymark-runtime-gate-s2q-source-calibration.yml",
    "agentmark_e3b_lab/e3_mqtt/app/replaymark_s2q_source_calibration.py",
    "replaymark/S2Q_SOURCE_ONLY_CALIBRATION.md",
    "replaymark_verification/verify_s2q_source_calibration.py",
}
SCREENING_ORDERS = ((16, 8, 4), (8, 4, 16), (4, 16, 8))
ELIGIBLE_WAVES = (16, 8, 4)
TASKS = 192
WAVE_PERIOD_MS = 300.0
VERIFY_MS = 100.0
TASK_TIMEOUT_MS = 1000
SELECTION_SEAL_SCHEMA = "replaymark.s2q2-screening-selection-seal.v1"


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


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


def _float_equal(a: object, b: float | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    try:
        return abs(float(a) - float(b)) <= 1e-12
    except (TypeError, ValueError):
        return False


def _preflight() -> dict[str, object]:
    parent = _git("rev-parse", "HEAD^")
    if parent != P2_HEAD:
        raise SystemExit(f"S2-Q2 must be exact child of P2: {parent} != {P2_HEAD}")

    changed = set(_git("diff", "--name-only", P2_HEAD, "HEAD").splitlines())
    if changed != EXPECTED_INCREMENT:
        raise SystemExit(
            "undeclared S2-Q2 increment: "
            f"missing={sorted(EXPECTED_INCREMENT - changed)} "
            f"extra={sorted(changed - EXPECTED_INCREMENT)}"
        )

    protocol_blob = _git("rev-parse", f"HEAD:{PROTOCOL.relative_to(ROOT)}")
    if protocol_blob != P2_PROTOCOL_BLOB:
        raise SystemExit("P2 protocol blob drift")
    p2_verifier_blob = _git(
        "rev-parse",
        "HEAD:replaymark_verification/verify_s2p2_source_qualified_load_envelope.py",
    )
    if p2_verifier_blob != P2_VERIFIER_BLOB:
        raise SystemExit("P2 verifier blob drift")

    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    if protocol["status"] != "FROZEN_AFTER_Q1_SOURCE_ONLY_FAILURE_BEFORE_ANY_SHIFTED_TARGET_OUTCOME":
        raise SystemExit("P2 prospective status drift")
    if protocol["next_gate"] != "S2Q2_SOURCE_LOAD_ENVELOPE_SCREEN_HOLDOUT_AND_DSTAR_SEAL":
        raise SystemExit("P2 next-gate authority drift")
    if protocol["authorities"]["s2q_v1_failed_head"] != Q1_HEAD:
        raise SystemExit("Q1 failed authority drift")

    authority_matches = 0
    for path in sorted(P2_AUTHORITY_FILES | Q1_AUTHORITY_FILES):
        if _git("rev-parse", f"HEAD:{path}") != _git("rev-parse", f"{P2_HEAD}:{path}"):
            raise SystemExit(f"frozen P2/Q1 authority file drift: {path}")
        authority_matches += 1

    s0_manifest = json.loads(
        (ROOT / "replaymark" / "CURRENT_RUNTIME_SEAL.json").read_text(encoding="utf-8")
    )
    if s0_manifest["authority"]["commit"] != S0_OPTIMIZATION_AUTHORITY:
        raise SystemExit("S0 optimization authority drift")
    if s0_manifest["optimization_policy"]["state"] != "FROZEN":
        raise SystemExit("runtime micro-optimization freeze reopened")
    s0_matches = 0
    for rows in s0_manifest["frozen_blobs"].values():
        for path, expected in rows.items():
            if _git("rev-parse", f"HEAD:{path}") != expected:
                raise SystemExit(f"S0 frozen blob drift: {path}")
            s0_matches += 1

    source = RUNNER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports: list[str] = []
    state_delay_literals: list[object] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "set_state_delay"
        ):
            if len(node.args) != 1 or not isinstance(node.args[0], ast.Constant):
                raise SystemExit("S2-Q2 set_state_delay must use one literal argument")
            state_delay_literals.append(node.args[0].value)

    forbidden_imports = [
        name
        for name in imports
        if name == "replaymark"
        or name.startswith("replaymark.")
        or name == "replaymark_oracle"
        or name.startswith("replaymark_oracle.")
    ]
    if forbidden_imports:
        raise SystemExit(f"source-only Q2 runner imports semantic/oracle code: {forbidden_imports}")
    if state_delay_literals != [0, 0]:
        raise SystemExit(
            f"screening and holdout must each set literal delay zero once: {state_delay_literals}"
        )
    for forbidden in ("-b/command", "certify_reuse(", "adjudicate(", "execute_admitted"):
        if forbidden in source:
            raise SystemExit(f"source-only Q2 runner contains forbidden target/semantic token: {forbidden}")
    if "--wave-size" in source:
        raise SystemExit("holdout runner must not accept a caller-supplied W*")

    workflow = WORKFLOW.read_text(encoding="utf-8")
    if workflow.count("--mode screening-round") != 3:
        raise SystemExit("workflow must execute exactly three screening rounds")
    if workflow.count("--mode holdout") != 3:
        raise SystemExit("workflow must admit exactly three possible holdout replicates")
    for index in range(3):
        if workflow.count(f"--round-index {index}") != 1:
            raise SystemExit(f"screening round {index} invocation drift")
        if workflow.count(f"--holdout-replicate {index}") != 1:
            raise SystemExit(f"holdout replicate {index} invocation drift")
    if workflow.count("docker compose down -v --remove-orphans") < 6:
        raise SystemExit("workflow must restart broker/device for each screening round and holdout replicate")
    if workflow.count("docker compose up -d --build mosquitto device") != 6:
        raise SystemExit("workflow broker/device restart count drift")
    if workflow.count("if: steps.select.outputs.w_star != ''") != 3:
        raise SystemExit("holdout steps are not gated on successful W* selection")
    if workflow.count("--selection-seal /results/q2_screening_selection_seal.json") != 3:
        raise SystemExit("holdout does not consume the exact machine selection seal")
    for forbidden in ("replaymark_s2_admission_live", "set_state_delay(", "-b/command"):
        if forbidden in workflow:
            raise SystemExit(f"Q2 workflow contains target execution token: {forbidden}")

    return {
        "exact_p2_parent": True,
        "declared_files_only": True,
        "p2_protocol_blob": protocol_blob,
        "frozen_p2_q1_authority_files": authority_matches,
        "s0_frozen_blob_matches": s0_matches,
        "runtime_micro_optimization": "FROZEN",
        "runner_semantic_oracle_imports": 0,
        "runner_state_delay_literals": state_delay_literals,
        "caller_supplied_holdout_W_star": False,
        "screening_round_restarts": 3,
        "holdout_replicate_restarts": 3,
        "shifted_target_code_path_added": False,
    }


def _validate_cell(
    cell: object,
    *,
    phase: str,
    replicate: int,
    round_index: int | None,
    position: int | None,
    wave_size: int,
) -> dict[str, object]:
    checks: list[bool] = []
    rows_out: list[dict[str, object]] = []
    prefix = None
    if not isinstance(cell, dict):
        return {
            "valid": False,
            "rows": [],
            "prefix": None,
            "completion_offsets_ms": [],
            "start_lateness_ms": [],
            "p99_ms": None,
            "preview_exact": False,
        }

    prefix = cell.get("prefix")
    rows = cell.get("rows")
    header_ok = (
        cell.get("phase") == phase
        and cell.get("replicate") == replicate
        and cell.get("round_index") == round_index
        and cell.get("position") == position
        and cell.get("wave_size") == wave_size
        and isinstance(prefix, str)
        and isinstance(rows, list)
        and len(rows) == TASKS
    )
    checks.append(header_ok)

    offsets: list[float] = []
    lateness: list[float] = []
    if isinstance(rows, list) and isinstance(prefix, str):
        base_offer_ns = None
        for task_id, row in enumerate(rows):
            if not isinstance(row, dict):
                checks.append(False)
                continue
            rows_out.append(row)
            try:
                offer = int(row["offer_mono_ns"])
                t0 = int(row["task_start_mono_ns"])
                publish = int(row["act1_publish_mono_ns"])
                verify_deadline = int(row["verify_deadline_mono_ns"])
                timeout_deadline = int(row["task_timeout_deadline_mono_ns"])
                recv_raw = row["state_on_recv_mono_ns"]
                recv = None if recv_raw is None else int(recv_raw)
                completion_raw = row["completion_offset_ms"]
                lateness_raw = row["start_lateness_ms"]
                if base_offer_ns is None:
                    base_offer_ns = offer
                expected_offer = base_offer_ns + (
                    task_id // wave_size
                ) * int(WAVE_PERIOD_MS * 1e6)
                expected_completion = None if recv is None else (recv - t0) / 1e6
                expected_lateness = (t0 - offer) / 1e6
                visible_expected = recv is not None and publish <= recv <= verify_deadline
                complete_expected = recv is not None and publish <= recv <= timeout_deadline
                row_ok = (
                    row.get("phase") == phase
                    and row.get("replicate") == replicate
                    and row.get("round_index") == round_index
                    and row.get("position") == position
                    and row.get("wave_size") == wave_size
                    and row.get("task_id") == task_id
                    and row.get("device") == f"{prefix}-{task_id}-a"
                    and row.get("state_delay_ms") == 0
                    and offer == expected_offer
                    and t0 >= offer
                    and publish >= t0
                    and verify_deadline == t0 + int(VERIFY_MS * 1e6)
                    and timeout_deadline == t0 + int(TASK_TIMEOUT_MS * 1e6)
                    and _float_equal(completion_raw, expected_completion)
                    and _float_equal(lateness_raw, expected_lateness)
                    and row.get("visible_by_verify_deadline") is visible_expected
                    and row.get("completed_by_task_timeout") is complete_expected
                )
                if recv is None:
                    row_ok = row_ok and (
                        row.get("event_on") is None
                        and row.get("event_device") is None
                        and row.get("event_cause") is None
                    )
                else:
                    row_ok = row_ok and (
                        row.get("event_on") is True
                        and row.get("event_device") == f"{prefix}-{task_id}-a"
                        and row.get("event_cause") == "command"
                    )
                    offsets.append(float(expected_completion))
                lateness.append(float(expected_lateness))
                checks.append(row_ok)
            except (KeyError, TypeError, ValueError):
                checks.append(False)

    preview = cell.get("runner_descriptive_preview")
    p99_ms = _percentile(offsets, 99.0)
    preview_exact = False
    if isinstance(preview, dict):
        preview_exact = (
            preview.get("row_count") == len(rows_out)
            and preview.get("completion_count") == len(offsets)
            and preview.get("visible_by_verify_deadline")
            == sum(bool(row.get("visible_by_verify_deadline")) for row in rows_out)
            and _float_equal(
                preview.get("completion_median_ms"),
                statistics.median(offsets) if offsets else None,
            )
            and _float_equal(preview.get("completion_p99_ms"), p99_ms)
            and _float_equal(
                preview.get("start_lateness_p99_ms"),
                _percentile(lateness, 99.0),
            )
        )
    checks.append(preview_exact)

    return {
        "valid": bool(checks) and all(checks),
        "rows": rows_out,
        "prefix": prefix,
        "completion_offsets_ms": offsets,
        "start_lateness_ms": lateness,
        "p99_ms": p99_ms,
        "preview_exact": preview_exact,
    }


def _screening_files(screening_dir: Path) -> list[Path]:
    return [screening_dir / f"q2_screen_round_{i}.json" for i in range(3)]


def _screening_recompute(screening_dir: Path) -> dict[str, object]:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    screening = protocol["load_envelope_screening"]
    files = _screening_files(screening_dir)
    if not all(path.is_file() for path in files):
        missing = [str(path) for path in files if not path.is_file()]
        raise SystemExit(f"incomplete screening result set: {missing}")

    candidate_cells: dict[int, list[dict[str, object]]] = {wave: [] for wave in ELIGIBLE_WAVES}
    round_reports: list[dict[str, object]] = []
    prefixes: list[str] = []
    result_hashes: dict[str, str] = {}
    structural_round_checks: list[bool] = []

    for round_index, path in enumerate(files):
        result = json.loads(path.read_text(encoding="utf-8"))
        result_hashes[f"round_{round_index}"] = _sha256(path)
        expected_order = list(SCREENING_ORDERS[round_index])
        structural = (
            result.get("schema") == "replaymark.s2q2-source-screening-round.v1"
            and result.get("source_only") is True
            and result.get("shifted_target_executed") is False
            and result.get("act2_candidate_constructed") is False
            and result.get("broker") == "mosquitto version 2.1.2"
            and result.get("state_delay_ms") == 0
            and result.get("round_index") == round_index
            and result.get("frozen_order") == expected_order
            and result.get("parameters")
            == {
                "tasks_per_cell": TASKS,
                "wave_period_ms": WAVE_PERIOD_MS,
                "verify_ms": VERIFY_MS,
                "task_timeout_ms": TASK_TIMEOUT_MS,
                "quiescence_seconds_between_cells": 0.5,
            }
        )
        cells = result.get("cells")
        if not isinstance(cells, list) or len(cells) != 3:
            structural = False
            cells = []

        cell_summaries: list[dict[str, object]] = []
        for position, wave_size in enumerate(expected_order):
            cell = cells[position] if position < len(cells) else None
            validation = _validate_cell(
                cell,
                phase="screening",
                replicate=round_index,
                round_index=round_index,
                position=position,
                wave_size=wave_size,
            )
            structural = structural and bool(validation["valid"])
            if isinstance(validation["prefix"], str):
                prefixes.append(str(validation["prefix"]))
            candidate_cells[wave_size].append(validation)
            cell_summaries.append(
                {
                    "position": position,
                    "wave_size": wave_size,
                    "rows": len(validation["rows"]),
                    "p99_ms": validation["p99_ms"],
                    "structurally_valid": validation["valid"],
                    "start_lateness_p99_ms": _percentile(
                        list(validation["start_lateness_ms"]), 99.0
                    ),
                }
            )
        structural_round_checks.append(structural)
        round_reports.append(
            {
                "round_index": round_index,
                "structurally_valid": structural,
                "cells": cell_summaries,
            }
        )

    candidate_stats: dict[str, dict[str, object]] = {}
    passing: list[int] = []
    for wave_size in ELIGIBLE_WAVES:
        validations = candidate_cells[wave_size]
        rows = [row for v in validations for row in v["rows"]]
        offsets = [x for v in validations for x in v["completion_offsets_ms"]]
        per_rep_p99 = [v["p99_ms"] for v in validations]
        all_structural = len(validations) == 3 and all(bool(v["valid"]) for v in validations)
        all_complete = (
            len(rows) == 576
            and len(offsets) == 576
            and all(row.get("completed_by_task_timeout") is True for row in rows)
        )
        all_visible = (
            len(rows) == 576
            and all(row.get("visible_by_verify_deadline") is True for row in rows)
        )
        each_p99_ok = (
            len(per_rep_p99) == 3
            and all(
                value is not None
                and float(value)
                <= float(screening["qualification_per_candidate"]["each_replicate_p99_ms_max"])
                for value in per_rep_p99
            )
        )
        pooled_p99 = _percentile(offsets, 99.0)
        pooled_p99_ok = (
            pooled_p99 is not None
            and pooled_p99
            <= float(screening["qualification_per_candidate"]["pooled_p99_ms_max"])
        )
        qualifies = (
            all_structural
            and len(rows) == 576
            and all_complete
            and all_visible
            and each_p99_ok
            and pooled_p99_ok
        )
        if qualifies:
            passing.append(wave_size)
        candidate_stats[str(wave_size)] = {
            "rows": len(rows),
            "all_rows_structurally_valid": all_structural,
            "all_tasks_complete_by_timeout": all_complete,
            "all_tasks_visible_by_verify_deadline": all_visible,
            "replicate_p99_ms": per_rep_p99,
            "each_replicate_p99_at_most_80": each_p99_ok,
            "pooled_median_ms": statistics.median(offsets) if offsets else None,
            "pooled_p99_ms": pooled_p99,
            "pooled_p99_at_most_80": pooled_p99_ok,
            "qualifies": qualifies,
        }

    all_prefixes_fresh = len(prefixes) == 9 and len(set(prefixes)) == 9
    all_rounds_structural = len(structural_round_checks) == 3 and all(structural_round_checks)
    w_star = (
        max(passing)
        if passing and all_rounds_structural and all_prefixes_fresh
        else None
    )
    screening_verdict = "PASS" if w_star is not None else "FAIL"

    return {
        "round_reports": round_reports,
        "screening_result_sha256s": result_hashes,
        "screening_source_rows": sum(
            int(candidate_stats[str(wave)]["rows"]) for wave in ELIGIBLE_WAVES
        ),
        "all_rounds_structurally_valid": all_rounds_structural,
        "all_candidate_namespaces_fresh": all_prefixes_fresh,
        "candidate_stats": candidate_stats,
        "W_star_screen": w_star,
        "screening_verdict": screening_verdict,
        "prefixes": prefixes,
    }


def _expected_selection_seal(screening: dict[str, object]) -> dict[str, object]:
    return {
        "schema": SELECTION_SEAL_SCHEMA,
        "q2_execution_head": _git("rev-parse", "HEAD"),
        "p2_head": P2_HEAD,
        "p2_protocol_sha256": _sha256(PROTOCOL),
        "screening_schedule_sha256": EXPECTED_SCREENING_SCHEDULE_SHA256,
        "screening_result_sha256s": screening["screening_result_sha256s"],
        "screening_source_rows": screening["screening_source_rows"],
        "all_rounds_structurally_valid": screening["all_rounds_structurally_valid"],
        "all_candidate_namespaces_fresh": screening["all_candidate_namespaces_fresh"],
        "candidate_stats": screening["candidate_stats"],
        "W_star_screen": screening["W_star_screen"],
        "screening_verdict": screening["screening_verdict"],
        "source_only": True,
        "shifted_target_executed": False,
        "act2_candidate_constructed": False,
        "selection_data_source": "only the 1728 frozen screening rows",
        "target_outcomes_visible": False,
    }


def _write_selection_phase(
    screening_dir: Path,
    selection_seal_out: Path,
) -> dict[str, object]:
    screening = _screening_recompute(screening_dir)
    seal = _expected_selection_seal(screening)
    selection_seal_out.parent.mkdir(parents=True, exist_ok=True)
    selection_seal_out.write_text(
        json.dumps(seal, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "phase": "SCREENING_SELECTION",
        "screening": {
            key: value
            for key, value in screening.items()
            if key != "prefixes"
        },
        "selection_seal_sha256": _sha256(selection_seal_out),
        "verdict": screening["screening_verdict"],
        "holdout_permitted": screening["screening_verdict"] == "PASS",
        "target_execution_permitted": False,
    }


def _holdout_files(holdout_dir: Path) -> list[Path]:
    return [holdout_dir / f"q2_holdout_{i}.json" for i in range(3)]


def _final_verify(
    screening_dir: Path,
    selection_seal_path: Path,
    holdout_dir: Path,
) -> dict[str, object]:
    screening = _screening_recompute(screening_dir)
    expected_seal = _expected_selection_seal(screening)
    if not selection_seal_path.is_file():
        raise SystemExit("screening selection seal missing")
    actual_seal = json.loads(selection_seal_path.read_text(encoding="utf-8"))
    selection_seal_exact = actual_seal == expected_seal
    selection_seal_sha = _sha256(selection_seal_path)

    if screening["screening_verdict"] != "PASS":
        unexpected_holdout = any(path.is_file() for path in _holdout_files(holdout_dir))
        return {
            "phase": "FINAL",
            "screening": {
                key: value for key, value in screening.items() if key != "prefixes"
            },
            "selection_seal_exact": selection_seal_exact,
            "selection_seal_sha256": selection_seal_sha,
            "holdout": {
                "executed": unexpected_holdout,
                "permitted": False,
                "unexpected_holdout_after_screening_failure": unexpected_holdout,
            },
            "W_star_screen": screening["W_star_screen"],
            "D_star_ms": None,
            "screening_rows_used_in_D_star_estimate": 0,
            "holdout_rows_used_in_D_star_estimate": 0,
            "shifted_target_executed": False,
            "act2_candidate_constructed": False,
            "scientific_verdict": "FAIL",
            "verdict": "FAIL",
        }

    w_star = int(screening["W_star_screen"])
    files = _holdout_files(holdout_dir)
    files_complete = all(path.is_file() for path in files)
    holdout_validations: list[dict[str, object]] = []
    holdout_hashes: dict[str, str] = {}
    prefixes: list[str] = []
    structural_reports: list[bool] = []

    if files_complete:
        for replicate, path in enumerate(files):
            result = json.loads(path.read_text(encoding="utf-8"))
            holdout_hashes[f"replicate_{replicate}"] = _sha256(path)
            structural = (
                result.get("schema") == "replaymark.s2q2-source-holdout-replicate.v1"
                and result.get("source_only") is True
                and result.get("shifted_target_executed") is False
                and result.get("act2_candidate_constructed") is False
                and result.get("broker") == "mosquitto version 2.1.2"
                and result.get("state_delay_ms") == 0
                and result.get("holdout_replicate") == replicate
                and result.get("selected_wave_size") == w_star
                and result.get("selection_seal_sha256") == selection_seal_sha
                and result.get("parameters")
                == {
                    "tasks": TASKS,
                    "wave_period_ms": WAVE_PERIOD_MS,
                    "verify_ms": VERIFY_MS,
                    "task_timeout_ms": TASK_TIMEOUT_MS,
                }
            )
            validation = _validate_cell(
                result.get("cell"),
                phase="holdout",
                replicate=replicate,
                round_index=None,
                position=None,
                wave_size=w_star,
            )
            structural = structural and bool(validation["valid"])
            structural_reports.append(structural)
            holdout_validations.append(validation)
            if isinstance(validation["prefix"], str):
                prefixes.append(str(validation["prefix"]))

    rows = [row for v in holdout_validations for row in v["rows"]]
    offsets = [x for v in holdout_validations for x in v["completion_offsets_ms"]]
    per_rep_p99 = [v["p99_ms"] for v in holdout_validations]
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    holdout_q = protocol["fresh_holdout_confirmation"]["qualification"]

    namespaces_fresh = (
        len(prefixes) == 3
        and len(set(prefixes)) == 3
        and set(prefixes).isdisjoint(set(screening["prefixes"]))
    )
    all_structural = (
        files_complete
        and len(structural_reports) == 3
        and all(structural_reports)
        and namespaces_fresh
        and selection_seal_exact
    )
    all_complete = (
        len(rows) == 576
        and len(offsets) == 576
        and all(row.get("completed_by_task_timeout") is True for row in rows)
    )
    all_visible = (
        len(rows) == 576
        and all(row.get("visible_by_verify_deadline") is True for row in rows)
    )
    each_p99_ok = (
        len(per_rep_p99) == 3
        and all(
            value is not None
            and float(value) <= float(holdout_q["each_replicate_p99_ms_max"])
            for value in per_rep_p99
        )
    )
    pooled_p99 = _percentile(offsets, 99.0)
    pooled_p99_ok = (
        pooled_p99 is not None
        and pooled_p99 <= float(holdout_q["pooled_p99_ms_max"])
    )
    holdout_qualification_pass = (
        all_structural
        and len(rows) == 576
        and all_complete
        and all_visible
        and each_p99_ok
        and pooled_p99_ok
    )

    holdout_median = statistics.median(offsets) if offsets else None
    d_star_ms = None
    if holdout_qualification_pass and holdout_median is not None:
        d_star_ms = math.floor((VERIFY_MS - holdout_median) + 0.5)

    dstar_bounds_ok = (
        d_star_ms is not None
        and d_star_ms >= int(protocol["dstar_seal"]["must_satisfy_min_ms"])
        and d_star_ms < int(protocol["dstar_seal"]["must_satisfy_max_exclusive_ms"])
    )
    final_pass = (
        screening["screening_verdict"] == "PASS"
        and selection_seal_exact
        and holdout_qualification_pass
        and dstar_bounds_ok
    )

    return {
        "phase": "FINAL",
        "screening": {
            key: value for key, value in screening.items() if key != "prefixes"
        },
        "selection_seal_exact": selection_seal_exact,
        "selection_seal_sha256": selection_seal_sha,
        "holdout": {
            "executed": files_complete,
            "files_complete": files_complete,
            "result_sha256s": holdout_hashes,
            "rows": len(rows),
            "all_rows_structurally_valid": all_structural,
            "fresh_namespaces_disjoint_from_screening": namespaces_fresh,
            "all_tasks_complete_by_timeout": all_complete,
            "all_tasks_visible_by_verify_deadline": all_visible,
            "replicate_p99_ms": per_rep_p99,
            "each_replicate_p99_at_most_80": each_p99_ok,
            "pooled_median_ms": holdout_median,
            "pooled_p99_ms": pooled_p99,
            "pooled_p99_at_most_80": pooled_p99_ok,
            "qualification_pass": holdout_qualification_pass,
        },
        "W_star_screen": w_star,
        "D_star_ms": d_star_ms,
        "D_star_computed_only_after_holdout_pass": d_star_ms is None
        or holdout_qualification_pass,
        "D_star_bounds_ok": dstar_bounds_ok,
        "screening_rows_used_in_D_star_estimate": 0,
        "holdout_rows_used_in_D_star_estimate": 576
        if holdout_qualification_pass
        else 0,
        "shifted_target_executed": False,
        "act2_candidate_constructed": False,
        "target_outcomes_visible": False,
        "fallback": "ABSENT",
        "regeneration": "ABSENT",
        "scientific_verdict": "PASS" if final_pass else "FAIL",
        "verdict": "PASS" if final_pass else "FAIL",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--screening-dir")
    parser.add_argument("--selection-seal-out")
    parser.add_argument("--selection-seal")
    parser.add_argument("--holdout-dir")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    preflight = _preflight()
    report: dict[str, object] = {
        "schema": "replaymark.s2q2-source-load-envelope-verification.v1",
        "preflight": preflight,
        "p2_protocol_sha256": _sha256(PROTOCOL),
    }

    if args.preflight_only:
        report["phase"] = "PREFLIGHT"
        report["verdict"] = "PASS"
    elif args.selection_seal_out:
        if not args.screening_dir:
            raise SystemExit("--screening-dir required for selection phase")
        report.update(
            _write_selection_phase(
                Path(args.screening_dir),
                Path(args.selection_seal_out),
            )
        )
    else:
        if not args.screening_dir or not args.selection_seal or not args.holdout_dir:
            raise SystemExit(
                "--screening-dir, --selection-seal, and --holdout-dir required for final verification"
            )
        report.update(
            _final_verify(
                Path(args.screening_dir),
                Path(args.selection_seal),
                Path(args.holdout_dir),
            )
        )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
