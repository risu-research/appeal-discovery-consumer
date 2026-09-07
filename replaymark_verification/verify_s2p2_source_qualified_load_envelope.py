from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "replaymark" / "S2P2_SOURCE_QUALIFIED_LOAD_ENVELOPE.json"

Q1_HEAD = "2a7e994810ae9c88d626d50fea1b06a7eb3550b5"
S2P_V1_HEAD = "ce92490e546e25cae980b7c84806ff655f2c947d"
S1_HEAD = "c93c8574eb62cb4dcde94890fdfc8f939b41e00a"
S0_HEAD = "8716db916c49578ee69930b973a44f892f975307"
S0_OPTIMIZATION_AUTHORITY = "25d317392b9ce6aaaedc190ef6aff8bc38d555b5"
S2P_V1_PROTOCOL_BLOB = "0a2160ed7fa7e50ba5641fa251b334e9e0cb7beb"
EXPECTED_SCREENING_SCHEDULE_SHA256 = "7850522b51e6f62130685835fb487bfe94cca9e122a79e11f64d5232bbf648d7"
EXPECTED_INCREMENT = {
    ".github/workflows/replaymark-runtime-gate-s2p2-source-qualified-load-envelope-protocol.yml",
    "replaymark/S2P2_SOURCE_QUALIFIED_LOAD_ENVELOPE.json",
    "replaymark/S2P2_SOURCE_QUALIFIED_LOAD_ENVELOPE.md",
    "replaymark_verification/verify_s2p2_source_qualified_load_envelope.py",
}
Q1_INCREMENT = {
    ".github/workflows/replaymark-runtime-gate-s2q-source-calibration.yml",
    "agentmark_e3b_lab/e3_mqtt/app/replaymark_s2q_source_calibration.py",
    "replaymark/S2Q_SOURCE_ONLY_CALIBRATION.md",
    "replaymark_verification/verify_s2q_source_calibration.py",
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def verify_git_boundary(protocol: dict[str, object]) -> dict[str, object]:
    parent = git("rev-parse", "HEAD^")
    if parent != Q1_HEAD:
        raise AssertionError(f"P2 must be exact child of failed Q1 authority: {parent} != {Q1_HEAD}")

    changed = set(git("diff", "--name-only", Q1_HEAD, "HEAD").splitlines())
    if changed != EXPECTED_INCREMENT:
        raise AssertionError(
            "undeclared P2 increment: "
            f"missing={sorted(EXPECTED_INCREMENT - changed)} "
            f"extra={sorted(changed - EXPECTED_INCREMENT)}"
        )

    p1_blob = git("rev-parse", "HEAD:replaymark/S2_MIXED_CAPSTONE_PROTOCOL.json")
    if p1_blob != S2P_V1_PROTOCOL_BLOB:
        raise AssertionError("S2-P v1 protocol blob drift")

    q1_matches = 0
    for path in sorted(Q1_INCREMENT):
        now = git("rev-parse", f"HEAD:{path}")
        old = git("rev-parse", f"{Q1_HEAD}:{path}")
        if now != old:
            raise AssertionError(f"Q1 authority file drift: {path}")
        q1_matches += 1

    seal = json.loads(
        (ROOT / "replaymark" / "CURRENT_RUNTIME_SEAL.json").read_text(encoding="utf-8")
    )
    if seal["authority"]["commit"] != S0_OPTIMIZATION_AUTHORITY:
        raise AssertionError("S0 optimization authority drift")
    if seal["optimization_policy"]["state"] != "FROZEN":
        raise AssertionError("runtime micro-optimization freeze reopened")

    frozen_matches = 0
    for rows in seal["frozen_blobs"].values():
        for path, expected in rows.items():
            actual = git("rev-parse", f"HEAD:{path}")
            if actual != expected:
                raise AssertionError(f"S0 frozen blob drift: {path}")
            frozen_matches += 1

    authorities = protocol["authorities"]
    exact = {
        "s0_optimization_authority": S0_OPTIMIZATION_AUTHORITY,
        "s0_runtime_seal_head": S0_HEAD,
        "s1_execution_admission_head": S1_HEAD,
        "s2p_v1_protocol_head": S2P_V1_HEAD,
        "s2q_v1_failed_head": Q1_HEAD,
        "s2q_v1_workflow_run": 34156280604,
        "s2q_v1_source_result_sha256": "393231030149423cf2137bf4f998f4a6809b777241741664dc08972adc1a225e",
    }
    for key, expected in exact.items():
        if authorities[key] != expected:
            raise AssertionError(f"authority drift {key}: {authorities[key]} != {expected}")
    artifact = authorities["s2q_v1_artifact"]
    if artifact != {
        "id": 10031102728,
        "sha256": "1e70174e401bf3147b0ef66586b978d500f409e0d0534b15a7cfea392eba1975",
    }:
        raise AssertionError("Q1 artifact authority drift")

    return {
        "exact_failed_q1_parent": True,
        "declared_files_only": True,
        "s0_frozen_blob_matches": frozen_matches,
        "q1_authority_files_unchanged": q1_matches,
        "runtime_micro_optimization": "FROZEN",
    }


def verify_q1_failure_anchor(protocol: dict[str, object]) -> dict[str, object]:
    q1 = protocol["q1_failure_anchor"]
    expected = {
        "wave_size": 32,
        "source_rows": 576,
        "pooled_median_source_completion_ms": 12.5464795,
        "pooled_completion_p99_ms": 128.36104425,
        "visible_by_100ms": 560,
        "not_visible_by_100ms": 16,
        "scientific_verdict": "FAIL",
        "shifted_target_executed": False,
        "act2_candidate_constructed": False,
        "permanently_ineligible_for_this_s2_capstone": True,
        "later_replication_may_not_rehabilitate_wave_32": True,
    }
    if q1 != expected:
        raise AssertionError(f"Q1 failure anchor drift: {q1}")
    return {
        "q1_scientific_verdict": "FAIL",
        "wave_32_permanently_ineligible": True,
        "target_outcomes_seen": False,
    }


def verify_screening(protocol: dict[str, object]) -> dict[str, object]:
    screening = protocol["load_envelope_screening"]
    if screening["eligible_wave_sizes_descending"] != [16, 8, 4]:
        raise AssertionError("eligible wave set drift")
    if screening["wave_32_is_not_a_candidate"] is not True:
        raise AssertionError("failed wave 32 became eligible")
    if screening["all_candidates_are_run_regardless_of_earlier_candidate_results"] is not True:
        raise AssertionError("screening permits adaptive early stop")
    if screening["no_early_stop"] is not True:
        raise AssertionError("screening early stop not forbidden")
    if screening["state_delay_ms"] != 0 or screening["verify_ms"] != 100.0:
        raise AssertionError("source-only timing boundary drift")
    if screening["wave_period_ms"] != 300.0 or screening["task_timeout_ms"] != 1000:
        raise AssertionError("screening workload timing drift")
    if screening["tasks_per_candidate_replicate"] != 192:
        raise AssertionError("screening task count drift")
    if screening["screening_rounds"] != 3 or screening["replicates_per_candidate"] != 3:
        raise AssertionError("screening replication plan drift")
    if screening["rows_per_candidate"] != 576 or screening["total_screening_rows"] != 1728:
        raise AssertionError("screening row count drift")

    expected_orders = [[16, 8, 4], [8, 4, 16], [4, 16, 8]]
    actual_orders = [row["ordered_wave_sizes"] for row in screening["screening_schedule"]]
    if actual_orders != expected_orders:
        raise AssertionError("screening Latin-square order drift")

    rows = []
    position_counts = {16: Counter(), 8: Counter(), 4: Counter()}
    for round_idx, order in enumerate(actual_orders):
        for position, wave in enumerate(order):
            rows.append({"round": round_idx, "position": position, "wave_size": wave})
            position_counts[wave][position] += 1
    digest = sha256_bytes(canonical_json_bytes(rows))
    if digest != EXPECTED_SCREENING_SCHEDULE_SHA256:
        raise AssertionError("screening schedule implementation digest drift")
    if digest != screening["screening_schedule_sha256"]:
        raise AssertionError("screening schedule declared digest drift")
    for wave in [16, 8, 4]:
        if position_counts[wave] != Counter({0: 1, 1: 1, 2: 1}):
            raise AssertionError(f"candidate {wave} is not balanced across positions")

    q = screening["qualification_per_candidate"]
    required_true = [
        "all_576_rows_present",
        "all_tasks_complete_by_timeout",
        "all_tasks_visible_by_verify_deadline",
        "no_task_exclusion",
    ]
    if not all(q[key] is True for key in required_true):
        raise AssertionError("screening qualification weakened")
    if q["each_replicate_p99_ms_max"] != 80.0 or q["pooled_p99_ms_max"] != 80.0:
        raise AssertionError("screening p99 bound drift")
    if "maximum numeric eligible wave size" not in screening["selection_rule"]:
        raise AssertionError("W* selection rule drift")

    return {
        "eligible_wave_sizes": [16, 8, 4],
        "screening_rows": 1728,
        "schedule_sha256": digest,
        "latin_square_position_balance": True,
        "all_candidates_required": True,
    }


def verify_holdout_and_dstar(protocol: dict[str, object]) -> dict[str, object]:
    holdout = protocol["fresh_holdout_confirmation"]
    if holdout["runs_only_if_screening_selects_W_star"] is not True:
        raise AssertionError("holdout may run without screened W*")
    if holdout["wave_size"] != "exact W_star_screen":
        raise AssertionError("holdout wave can differ from screened W*")
    if holdout["replicates"] != 3 or holdout["tasks_per_replicate"] != 192:
        raise AssertionError("holdout sample plan drift")
    if holdout["total_holdout_rows"] != 576:
        raise AssertionError("holdout row count drift")
    if holdout["state_delay_ms"] != 0 or holdout["verify_ms"] != 100.0:
        raise AssertionError("holdout source boundary drift")
    hq = holdout["qualification"]
    if not all(
        hq[key] is True
        for key in [
            "all_576_rows_present",
            "all_tasks_complete_by_timeout",
            "all_tasks_visible_by_verify_deadline",
            "no_task_exclusion",
        ]
    ):
        raise AssertionError("holdout qualification weakened")
    if hq["each_replicate_p99_ms_max"] != 80.0 or hq["pooled_p99_ms_max"] != 80.0:
        raise AssertionError("holdout p99 bound drift")
    if "do not fall back" not in holdout["failure_rule"].lower():
        raise AssertionError("holdout failure can adaptively choose a lower W*")
    if holdout["selection_data_not_reused_for_D_star"] is not True:
        raise AssertionError("screening selection data can leak into D* estimate")

    dstar = protocol["dstar_seal"]
    if dstar["computed_only_after_holdout_passes"] is not True:
        raise AssertionError("D* can be computed before holdout qualification")
    if dstar["data_source"] != "only the 576 fresh holdout completion offsets at W_star_screen":
        raise AssertionError("D* data source drift")
    if dstar["definition"] != "D_star_ms = floor((100.0 - pooled_median_holdout_completion_ms) + 0.5)":
        raise AssertionError("D* formula drift")
    if dstar["must_satisfy_min_ms"] != 1 or dstar["must_satisfy_max_exclusive_ms"] != 100:
        raise AssertionError("D* admissibility drift")
    for key in [
        "computed_once",
        "sealed_before_any_shifted_target_outcome",
        "alternate_formula_forbidden",
        "retune_after_target_outcome_forbidden",
        "screening_rows_may_not_be_pooled_into_D_star_estimate",
    ]:
        if dstar[key] is not True:
            raise AssertionError(f"D* anti-fishing rule disabled: {key}")

    return {
        "holdout_rows": 576,
        "load_selection_data_separated_from_dstar_estimation": True,
        "same_generation_holdout_fallback_forbidden": True,
        "dstar_target_blind": True,
    }


def verify_inheritance_and_boundary(protocol: dict[str, object]) -> dict[str, object]:
    if protocol["schema"] != "replaymark.s2p2-source-qualified-load-envelope-protocol.v1":
        raise AssertionError("foreign P2 protocol schema")
    if protocol["gate"] != "S2P2_SOURCE_QUALIFIED_LOAD_ENVELOPE_PROTOCOL":
        raise AssertionError("wrong P2 gate")
    if protocol["status"] != "FROZEN_AFTER_Q1_SOURCE_ONLY_FAILURE_BEFORE_ANY_SHIFTED_TARGET_OUTCOME":
        raise AssertionError("P2 is not prospectively frozen")

    boundary = protocol["p2_boundary"]
    for key in [
        "source_screening_executed",
        "source_holdout_executed",
        "selected_W_star_available",
        "sealed_D_star_available",
        "shifted_target_execution_permitted",
        "target_outcome_visibility_permitted",
        "fallback_or_regeneration",
        "runtime_micro_optimization",
        "new_semantic_theorem",
    ]:
        if boundary[key] is not False:
            raise AssertionError(f"P2 protocol-only boundary unexpectedly enables {key}")
    if boundary["protocol_only_increment"] is not True:
        raise AssertionError("P2 is not protocol-only")

    inherited = protocol["supersession_scope"]
    if inherited["inherits_s2p_v1_policy_assignment_schedule_sha256"] != "ec91b78a6720ef9b4e83da12f9b8cf37c1d05028bb6ebaf0e4c6a274ff372d1e":
        raise AssertionError("policy schedule inheritance drift")
    if inherited["inherits_s2p_v1_target_tasks_per_trial"] != 192 or inherited["inherits_s2p_v1_target_trials"] != 6:
        raise AssertionError("target sample plan drift")
    if inherited["inherits_s2p_v1_verify_ms"] != 100.0 or inherited["inherits_s2p_v1_wave_period_ms"] != 300.0:
        raise AssertionError("target evidence timing drift")
    for key in [
        "inherits_s2p_v1_policy_semantics_unchanged",
        "inherits_s2p_v1_evidence_before_dispatch_barrier_unchanged",
        "inherits_s2p_v1_independent_oracle_unchanged",
        "inherits_s2p_v1_promotion_criteria_unchanged",
        "inherits_s2p_v1_no_fallback_no_regeneration",
    ]:
        if inherited[key] is not True:
            raise AssertionError(f"unexpected S2-P v1 semantic/evaluation drift: {key}")
    if inherited["supersedes_only"] != [
        "fixed wave_size=32 source calibration",
        "fixed wave_size=32 target workload",
        "same-data source load qualification and D_star estimation",
    ]:
        raise AssertionError("P2 supersession scope expanded")

    anti = protocol["anti_fishing_rules"]
    if not all(value is True for value in anti.values()):
        raise AssertionError("one or more anti-fishing rules disabled")

    if protocol["next_gate"] != "S2Q2_SOURCE_LOAD_ENVELOPE_SCREEN_HOLDOUT_AND_DSTAR_SEAL":
        raise AssertionError("wrong next gate")

    return {
        "protocol_only": True,
        "target_execution_permitted": False,
        "target_outcomes_visible": False,
        "p1_policy_and_oracle_semantics_inherited": True,
        "supersession_scope_bounded": True,
    }


def verify_no_result_bearing_increment() -> dict[str, object]:
    for path in EXPECTED_INCREMENT:
        if path.endswith(("_result.json", "_results.json", "_live.py", "_experiment.py", "_runner.py")):
            raise AssertionError(f"result-bearing or execution file in P2: {path}")
    workflow = (
        ROOT
        / ".github"
        / "workflows"
        / "replaymark-runtime-gate-s2p2-source-qualified-load-envelope-protocol.yml"
    ).read_text(encoding="utf-8").lower()
    forbidden = [
        "docker compose",
        "runner_shadow",
        "set_state_delay(",
        "replaymark_s2q_source_calibration.py",
        "mosquitto_sub",
    ]
    for token in forbidden:
        if token in workflow:
            raise AssertionError(f"P2 workflow contains runtime execution token: {token}")
    return {
        "experiment_runner_added": False,
        "source_screening_executed": False,
        "source_holdout_executed": False,
        "shifted_target_executed": False,
        "result_files_added": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    report = {
        "schema": "replaymark.s2p2-source-qualified-load-envelope-freeze-gate.v1",
        "verdict": "PASS",
        "protocol_sha256": sha256_bytes(PROTOCOL_PATH.read_bytes()),
        "git_boundary": verify_git_boundary(protocol),
        "q1_failure_anchor": verify_q1_failure_anchor(protocol),
        "screening": verify_screening(protocol),
        "holdout_and_dstar": verify_holdout_and_dstar(protocol),
        "inheritance_and_boundary": verify_inheritance_and_boundary(protocol),
        "no_result_bearing_increment": verify_no_result_bearing_increment(),
        "next_gate": "S2Q2_SOURCE_LOAD_ENVELOPE_SCREEN_HOLDOUT_AND_DSTAR_SEAL",
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
