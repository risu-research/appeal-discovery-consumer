from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

PARENT = "b1841de01e1343e14eb9563eef97877a3fbba83c"
BASE_PROTOCOL_COMMIT = "40bd3e994dd83f7554fb1d05f192707ca9bf996c"
BASE_PROTOCOL_BLOB = "ba83cdf78e9109ab0c7dcfe1d04bb11dd89880c5"
CLARIFICATION_BLOB = "d4fc55e81c6fa2310c539e94de4b352c1e6fb5b9"
SEED = "fd5b25ae05235eb460f426c716e1835783ced32e00ae81c7b67f24d09b83d596"
PROFILES = ("BARRIER_IMMEDIATE", "BARRIER_JITTERED")
GAPS = (0, 125, 250, 500)
REPLICAS = ("A", "B")
BATCHES = (192, 196, 200, 204, 208)
TRIALS = range(6)
NS_PER_MS = 1_000_000
CHANGED = {
    ".github/workflows/replaymark-runtime-gate-s3c2-schedule-conformance.yml",
    "agentmark_e3b_lab/e3_mqtt/app/s3c2_schedule.py",
    "replaymark_verification/verify_s3c2_schedule_conformance.py",
}
FROZEN_BLOBS = {
    "replaymark/S3C2_BARRIER_SCHEDULE_INVARIANCE_PROTOCOL.json": BASE_PROTOCOL_BLOB,
    "replaymark/S3C2_BARRIER_SCHEDULE_INVARIANCE_PROTOCOL_CLARIFICATION_V1.json": CLARIFICATION_BLOB,
    "replaymark/S3C1_FIRST_COMPLETE_V3_AUTHORITY_DIAGNOSIS.json": "703a6305660a9d25ef9a8a0b9a7d818cf05fe28a",
    "agentmark_e3b_lab/e3_mqtt/app/replaymark_s3c1_paired_deployment.py": "8d68a9680fcd49597fb1255392fb17b3cf4c834e",
    "replaymark_verification/verify_s3c1_paired_deployment.py": "8c5e66213e9ec6cb7f7e01731ab2273c2f3bc0a5",
    "agentmark_e3b_lab/e3_mqtt/app/s3c1_direct_native.py": "22456d02b5b3a3b2258b2bc1893ae45a221873f7",
    "agentmark_e3b_lab/e3_mqtt/app/s3c1_paired_heterogeneous_device.py": "0042bfeb1c570e8de3b61973336187d9a46d58aa",
    "replaymark/runtime_e3b_execution_gate.py": "22748a5aa820e83e4700a339e8af297cdd9f9143",
    "replaymark/runtime_e3b_action.py": "d5d483751eb06fd8b00f7bb2eff613a20f0f796c",
    "replaymark/runtime_e3b_observation.py": "de6cdc8ccdbb9b189e238cc5dbad173060fe17ab",
    "replaymark/runtime_e3b_correlation.py": "bbdc243eccf29c0a26b92bc78c0acdb96222da8e",
    "replaymark/runtime_e3b_bridge.py": "5c2b13f35edcae9ce42fa062f51f1b6ce46747bf",
    "agentmark_e3b_lab/e3_mqtt/mosquitto/mosquitto.conf": "0b68187c4590e780409048ea8c9e3144d34ccaa6",
}


def g(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def fail(message: str) -> None:
    raise AssertionError(message)


def independent_gap_permutation(replica: str, n: int, trial: int) -> tuple[int, ...]:
    cell_key = f"{SEED}|{replica}|{n}|{trial}"
    pairs = []
    for gap in GAPS:
        canonical = str(gap)
        preimage = f"{cell_key}|gap|{canonical}".encode("utf-8")
        pairs.append((hashlib.sha256(preimage).hexdigest(), gap))
    pairs.sort(key=lambda row: (row[0], row[1]))
    return tuple(gap for _digest, gap in pairs)


def independent_profile_order(replica: str, n: int, trial: int) -> tuple[str, str]:
    preimage = f"{SEED}|order|{replica}|{n}|{trial}".encode("utf-8")
    digest = hashlib.sha256(preimage).digest()
    if (digest[-1] & 1) == 0:
        return ("BARRIER_IMMEDIATE", "BARRIER_JITTERED")
    return ("BARRIER_JITTERED", "BARRIER_IMMEDIATE")


def load_schedule(path: Path):
    spec = importlib.util.spec_from_file_location("s3c2_schedule_under_test", path)
    if spec is None or spec.loader is None:
        fail("cannot load schedule module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            out.add(node.module or "")
    return out


def expect_raises(callable_obj, *args) -> None:
    try:
        callable_obj(*args)
    except Exception:
        return
    fail("expected fail-closed exception")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    checks: dict[str, bool] = {}
    details: dict[str, object] = {}

    checks["exact_parent"] = g("rev-parse", "HEAD^") == PARENT
    checks["protocol_parent"] = g("rev-parse", "HEAD^^") == BASE_PROTOCOL_COMMIT
    changed = set(filter(None, g("diff", "--name-only", "HEAD^", "HEAD").splitlines()))
    checks["exact_changed_set"] = changed == CHANGED

    blob_mismatches = {}
    for path, expected in FROZEN_BLOBS.items():
        actual = g("rev-parse", f"HEAD:{path}")
        if actual != expected:
            blob_mismatches[path] = {"expected": expected, "actual": actual}
    checks["frozen_blobs_exact"] = not blob_mismatches
    details["blob_mismatches"] = blob_mismatches

    protocol = json.loads(Path("replaymark/S3C2_BARRIER_SCHEDULE_INVARIANCE_PROTOCOL.json").read_text(encoding="utf-8"))
    clarification = json.loads(Path("replaymark/S3C2_BARRIER_SCHEDULE_INVARIANCE_PROTOCOL_CLARIFICATION_V1.json").read_text(encoding="utf-8"))
    checks["protocol_identity"] = (
        protocol["schema"] == "replaymark.s3c2-barrier-schedule-invariance-protocol.v1"
        and protocol["status"] == "FROZEN_POST_S3C1_FAILURE_BEFORE_IMPLEMENTATION_OR_NEW_LIVE_TARGET_EXPOSURE"
        and protocol["unchanged_matrix"]["physical_cells_total"] == 120
        and protocol["schedule_factor"]["profiles"]["BARRIER_JITTERED"]["gap_set_ms"] == [0.0, 125.0, 250.0, 500.0]
        and protocol["schedule_factor"]["profiles"]["BARRIER_JITTERED"]["schedule_seed_sha256"] == SEED
        and protocol["why_this_is_a_distinct_gate"]["s3c1_verdict"] == "FAIL"
        and protocol["why_this_is_a_distinct_gate"]["s3c1_promotion"] == "NOT_PROMOTED"
    )
    checks["clarification_identity"] = (
        clarification["schema"] == "replaymark.s3c2-barrier-schedule-invariance-protocol-clarification.v1"
        and clarification["base_protocol"]["commit"] == BASE_PROTOCOL_COMMIT
        and clarification["base_protocol"]["blob"] == BASE_PROTOCOL_BLOB
        and clarification["canonical_schedule_constants"]["seed_ascii"] == SEED
        and clarification["canonical_schedule_constants"]["gap_set_ms_integer"] == list(GAPS)
        and clarification["profile_order_function"]["mapping"]["0"] == ["BARRIER_IMMEDIATE", "BARRIER_JITTERED"]
        and clarification["profile_order_function"]["mapping"]["1"] == ["BARRIER_JITTERED", "BARRIER_IMMEDIATE"]
    )

    schedule_path = Path("agentmark_e3b_lab/e3_mqtt/app/s3c2_schedule.py")
    imports = imported_modules(schedule_path)
    checks["schedule_import_boundary"] = imports <= {"__future__", "hashlib"}
    details["schedule_imports"] = sorted(imports)
    text = schedule_path.read_text(encoding="utf-8")
    checks["schedule_no_replaymark_dependency"] = (
        "import replaymark" not in text
        and "from replaymark" not in text
        and "verify_s3c" not in text
        and "replaymark_s3c1_paired_deployment" not in text
    )

    s = load_schedule(schedule_path)
    checks["constant_identity"] = (
        s.SEED_ASCII == SEED
        and tuple(s.PROFILES) == PROFILES
        and tuple(s.GAP_SET_MS) == GAPS
        and tuple(s.REPLICAS) == REPLICAS
        and tuple(s.BATCH_SIZES) == BATCHES
        and tuple(s.TRIALS) == tuple(TRIALS)
        and s.NS_PER_MS == NS_PER_MS
    )

    order_counts = {PROFILES: 0, tuple(reversed(PROFILES)): 0}
    all_observed_gaps: set[int] = set()
    schedule_cells = 0
    exact_rows = 0
    for replica in REPLICAS:
        for n in BATCHES:
            for trial in TRIALS:
                schedule_cells += 1
                oracle_order = independent_profile_order(replica, n, trial)
                implementation_order = tuple(s.profile_order(replica, n, trial))
                if implementation_order != oracle_order:
                    fail(f"profile order mismatch: {replica=} {n=} {trial=}")
                order_counts[oracle_order] += 1

                oracle_perm = independent_gap_permutation(replica, n, trial)
                implementation_perm = tuple(s.jitter_gap_permutation(replica, n, trial))
                if implementation_perm != oracle_perm:
                    fail(f"gap permutation mismatch: {replica=} {n=} {trial=}")
                if set(implementation_perm) != set(GAPS) or len(implementation_perm) != 4:
                    fail("jitter permutation is not exact frozen gap set")

                waves = (n + 3) // 4
                for wave_index in range(waves - 1):
                    expected = oracle_perm[wave_index % 4]
                    got = s.requested_gap_ms("BARRIER_JITTERED", replica, n, trial, wave_index)
                    if got != expected:
                        fail("jitter requested gap mismatch")
                    if s.requested_gap_ms("BARRIER_IMMEDIATE", replica, n, trial, wave_index) != 0:
                        fail("immediate profile requested nonzero gap")
                    all_observed_gaps.add(got)
                    exact_rows += 1

    checks["all_60_source_cells_covered"] = schedule_cells == 60
    checks["both_profile_orders_present"] = all(value > 0 for value in order_counts.values())
    checks["all_four_jitter_gaps_present"] = all_observed_gaps == set(GAPS)
    checks["all_schedule_rows_match_oracle"] = exact_rows == sum(((n + 3) // 4 - 1) for _replica in REPLICAS for n in BATCHES for _trial in TRIALS)
    details["profile_order_counts"] = {
        "IMMEDIATE_FIRST": order_counts[PROFILES],
        "JITTERED_FIRST": order_counts[tuple(reversed(PROFILES))],
    }
    details["schedule_transition_rows_checked"] = exact_rows

    q = 1_000_000_000
    checks["immediate_before_quiescence_fails"] = s.transition_disposition("BARRIER_IMMEDIATE", "A", 192, 0, 0, q, q - 1) == "BEFORE_QUIESCENCE"
    checks["immediate_exact_boundary_admissible"] = s.transition_disposition("BARRIER_IMMEDIATE", "A", 192, 0, 0, q, q) == "ADMISSIBLE"

    jitter_boundary_checks = 0
    for wave_index in range(4):
        gap = s.requested_gap_ms("BARRIER_JITTERED", "A", 192, 0, wave_index)
        eligible = q + gap * NS_PER_MS
        if s.next_wave_eligible_ns("BARRIER_JITTERED", "A", 192, 0, wave_index, q) != eligible:
            fail("eligible timestamp mismatch")
        if gap > 0:
            if s.transition_disposition("BARRIER_JITTERED", "A", 192, 0, wave_index, q, eligible - 1) != "BEFORE_REQUIRED_GAP":
                fail("jitter one-ns-early transition did not fail closed")
        if s.transition_disposition("BARRIER_JITTERED", "A", 192, 0, wave_index, q, eligible) != "ADMISSIBLE":
            fail("jitter exact eligibility boundary not admissible")
        jitter_boundary_checks += 1
    checks["jitter_boundaries_fail_closed"] = jitter_boundary_checks == 4

    checks["observed_gap_preserves_negative_violation"] = s.post_barrier_observed_gap_ns(q, q - 1) == -1
    checks["host_lateness_clamped_only_at_zero"] = (
        s.host_start_lateness_after_eligibility_ns(q, q - 1) == 0
        and s.host_start_lateness_after_eligibility_ns(q, q + 7) == 7
    )
    checks["counterfactual_strict_boundary"] = (
        s.counterfactual_s3c1_500ms_overrun(q, q + 500_000_000) is False
        and s.counterfactual_s3c1_500ms_overrun(q, q + 500_000_001) is True
    )

    expect_raises(s.profile_order, "C", 192, 0)
    expect_raises(s.profile_order, "A", 193, 0)
    expect_raises(s.profile_order, "A", 192, 6)
    expect_raises(s.requested_gap_ms, "UNKNOWN", "A", 192, 0, 0)
    expect_raises(s.requested_gap_ms, "BARRIER_IMMEDIATE", "A", 192, 0, -1)
    expect_raises(s.next_wave_eligible_ns, "BARRIER_IMMEDIATE", "A", 192, 0, 0, True)
    expect_raises(s.counterfactual_s3c1_500ms_overrun, q, q - 1)
    checks["invalid_inputs_fail_closed"] = True

    verdict = "PASS" if all(checks.values()) else "FAIL"
    report = {
        "schema": "replaymark.s3c2-schedule-implementation-conformance.v1",
        "verdict": verdict,
        "parent": PARENT,
        "base_protocol_commit": BASE_PROTOCOL_COMMIT,
        "checks": checks,
        "details": details,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if verdict != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
