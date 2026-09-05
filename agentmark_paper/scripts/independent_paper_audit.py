#!/usr/bin/env python3
"""Independent second implementation of the AgentMark paper-result audit.

Intentionally does not import paper_results_lib. It independently checks the
canonical evidence identities and the critical paper-facing invariants so that
a shared extractor bug cannot silently bless the freeze.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

EXPECTED = {
    "e3b": {
        "run_id": 33935626964,
        "execution_commit": "5f5eb578f2d47de8e8ac53c1dacee917c49cd9dd",
        "artifact_id": 9960088059,
        "artifact_archive_sha256": "829e05748ae38c76f880ab57538112a980c1da3d3ebedd4b84c1e6409093eb95",
        "primary_sha256": "46d0ef0c82cf1fd40c3746cffb667d101d32a5431e7b52f99a9fa7fecf323b12",
        "schema": "agentmark.e3b.r0_r1_r2_certificate.v2",
    },
    "e3c": {
        "run_id": 33942887473,
        "execution_commit": "02028046d3f3d4fc32ed44b15c4b986e9df3545a",
        "artifact_id": 9962430737,
        "artifact_archive_sha256": "7ef5140a6dcdaee508154d49071aa15733da95b7507ead7d8d63afc963a12cb3",
        "primary_sha256": "9e1e91d4e7733880da8236b3a4afb3647f8aa9582fe8f7d6d2a8ec44f038653b",
        "schema": "agentmark.e3c.home_assistant.replicated_aggregate.v1",
    },
    "n1": {
        "run_id": 33946985750,
        "execution_commit": "5b2ba2aa35bf0bd00715b6b9475b44d9695c3c8f",
        "artifact_id": 9963663630,
        "artifact_archive_sha256": "14dfde9ff11865a548984ec4858429258d2d4fc1b7584c41d96a251530eb3f27",
        "primary_sha256": "4812816bd830b5e71d89843f8510c44f93c37a89b054ae8ef7a9358e90ec00f7",
        "schema": "agentmark.natural_controller.motion_light.replicated.v1",
    },
    "n2": {
        "run_id": 33965918153,
        "execution_commit": "4264c43d013178c8babedf772b1c06c5ddbe73cb",
        "artifact_id": 9969439579,
        "artifact_archive_sha256": "76bd2850156040139aabd935ccab44f01fb27344770c2f04a055fed81ee901b7",
        "primary_sha256": "df389a937832374008e459afd2a0454e632675a713b0a3b2b7d1b9258894d446",
        "schema": "agentmark.natural_controller.better_thermostat.replicated.v4",
    },
    "n2b": {
        "run_id": 33972619262,
        "execution_commit": "9ec25a1cc2a16bff893d7ff5ffc9271bf6e059f6",
        "artifact_id": 9971397583,
        "artifact_archive_sha256": "4d75b17e6bd0bd9ba41cb574f9bca022364c312c09b215b74a36a92fda5861db",
        "primary_sha256": "93975a490a6af4e48e35152a77129430df0b0f7883015fc2ce72bd0d6fdffe75",
        "schema": "agentmark.n2b.replicated_aggregate.v2",
    },
}


def die(msg: str) -> None:
    raise RuntimeError(msg)


def need(cond: bool, msg: str) -> None:
    if not cond:
        die(msg)


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def primary_raw(evidence_dir: Path, key: str) -> bytes:
    plain = evidence_dir / "primary.json"
    packed = evidence_dir / "primary.json.gz"
    need(plain.is_file() or packed.is_file(), f"{key}: missing evidence")
    a = plain.read_bytes() if plain.is_file() else None
    b = gzip.decompress(packed.read_bytes()) if packed.is_file() else None
    if a is not None and b is not None:
        need(a == b, f"{key}: storage representations disagree")
    return a if a is not None else b  # type: ignore[return-value]


def exact_int(value: Any, label: str) -> int:
    need(isinstance(value, (int, float)) and not isinstance(value, bool), f"{label}: numeric required")
    iv = int(value)
    need(float(iv) == float(value), f"{label}: integer-valued number required")
    return iv


def audit(root: Path) -> None:
    evidence: dict[str, dict[str, Any]] = {}
    for key, exp in EXPECTED.items():
        ed = root / "evidence" / key
        pp = ed / "PROVENANCE.json"
        need(pp.is_file(), f"{key}: missing provenance")
        raw = primary_raw(ed, key)
        p, prov = json.loads(raw.decode("utf-8")), load(pp)
        need(hashlib.sha256(raw).hexdigest() == exp["primary_sha256"], f"{key}: frozen primary digest mismatch")
        need(p.get("schema") == exp["schema"], f"{key}: source schema mismatch")
        for field in ("run_id", "execution_commit", "artifact_id", "artifact_archive_sha256"):
            need(prov.get(field) == exp[field], f"{key}: upstream identity mismatch for {field}")
        need(prov.get("primary_sha256") == exp["primary_sha256"], f"{key}: provenance primary digest mismatch")
        need(prov.get("canonical") is True, f"{key}: not canonical")
        evidence[key] = p

    e3b = evidence["e3b"]
    need(e3b.get("promotion_pass") is True, "E3b: promotion failed")
    groups = {"R0_rigid": [], "R1_timing": [], "R2_semantic": []}
    for row in e3b.get("broker_publish_conservation", []):
        mode = row.get("mode")
        need(mode in groups, f"E3b: unexpected mode {mode!r}")
        observed = exact_int(row.get("observed"), f"E3b {mode} observed")
        expected = exact_int(row.get("expected"), f"E3b {mode} expected")
        need(row.get("exact") is True and observed == expected and float(row.get("error")) == 0.0,
             f"E3b {mode}: conservation failure")
        groups[mode].append(observed)
    need(all(len(v) == 12 and len(set(v)) == 1 for v in groups.values()), "E3b: trial/work-count replication drift")
    need((groups["R0_rigid"][0], groups["R1_timing"][0], groups["R2_semantic"][0]) == (512, 512, 768),
         "E3b: exact workload drift")
    a = e3b["aggregate"]
    need((a["r0_violation"], a["r1_violation"], a["r2_violation"], a["r2_verify_fraction"]) == (1.0, 1.0, 0.0, 1.0),
         "E3b: semantic result drift")

    e3c = evidence["e3c"]
    need(e3c.get("decision") == "PROMOTED_REPLICATED" and e3c.get("replicas") == 2, "E3c: replication drift")
    w = e3c["exact_native_work_per_trial"]
    need(tuple(exact_int(w[k], f"E3c {k} work") for k in ("R0", "R1", "R2")) == (256, 256, 384),
         "E3c: exact workload drift")
    a = e3c["aggregate"]
    need(a["R0"]["support_violation_rate"] == 1.0 and a["R1"]["support_violation_rate"] == 1.0,
         "E3c: R0/R1 support result drift")
    need(a["R2"]["support_violation_rate"] == 0.0 and a["R2"]["verify_fraction"] == 1.0,
         "E3c: R2 semantic result drift")
    need(len(e3c.get("validation_artifacts", [])) == 2 and all(v.get("pass") is True for v in e3c["validation_artifacts"]),
         "E3c: validation drift")

    n1 = evidence["n1"]
    need(n1.get("decision") == "PROMOTED_REPLICATED" and n1.get("replicas") == [0, 1], "N1: replication drift")
    need(n1.get("independent_validations_passed") == 2, "N1: validator drift")
    need(n1.get("trial_counts") == {"per_mode_per_replica": 6, "per_mode_total": 12}, "N1: trial-count drift")
    summaries = n1["runner_summaries"]
    need([x["replica"] for x in summaries] == [0, 1], "N1: runner identity drift")
    for x in summaries:
        prod, val = x["producer_aggregate"], x["validation_recomputed"]
        need(prod["R0_support_failure_rate"] == 1.0 and prod["R1_support_failure_rate"] == 1.0 and prod["R2_support_failure_rate"] == 0.0,
             "N1: support result drift")
        need(prod["R1_minus_R0_mean_ms"] == val["R1_minus_R0_mean_ms"], "N1: R1 timing producer/validator mismatch")
        need(prod["R2_minus_source_mean_ms"] == val["R2_minus_source_mean_ms"], "N1: R2 timing producer/validator mismatch")
    need([summaries[0]["producer_aggregate"]["R1_minus_R0_mean_ms"], summaries[1]["producer_aggregate"]["R1_minus_R0_mean_ms"]]
         == [35.24896700000001, 35.178532166666656], "N1: frozen runner timings drift")
    need(n1["external_controller"]["repository"] == "home-assistant/core" and n1["external_controller"]["source_edited"] is False,
         "N1: official-controller provenance drift")

    n2 = evidence["n2"]
    need(n2.get("decision") == "PROMOTED_REPLICATED" and n2.get("replicas") == [0, 1] and n2.get("independent_validations_passed") == 2,
         "N2: replication drift")
    r = n2["recomputed_across_replicas"]
    need(r["TV_operation"] == 0.0 and r["TV_action"] == 1.0, "N2: projection TV drift")
    need(r["TV_operation_each_runner"] == [0.0, 0.0] and r["TV_action_each_runner"] == [1.0, 1.0], "N2: runner TV drift")
    src, tgt = r["source_identities"], r["target_identities"]
    need(len(src) == len(tgt) == 2 and src[0] == src[1] and tgt[0] == tgt[1], "N2: action identity replication drift")
    need(src[0]["operation"] == tgt[0]["operation"] == "climate.set_preset_mode", "N2: operation drift")
    need(src[0]["variant"] == '{"preset_mode":"home"}' and tgt[0]["variant"] == '{"preset_mode":"away"}', "N2: action variant drift")

    n2b = evidence["n2b"]
    need(n2b.get("decision") == "PROMOTED_REPLICATED" and n2b.get("replicas") == [0, 1], "N2b: replication drift")
    t = n2b["theory"]
    need((t["raw_feedback_tv"], t["quotient_feedback_tv"], t["TV_operation"], t["TV_action"], t["pair_restricted_eta_action"])
         == (1.0, 0.0, 0.0, 0.0, 0.0), "N2b: decision-equivalence result drift")
    counts = n2b["counts"]
    need({k: counts[k] for k in ("source_native", "target_native", "target_replay", "no_shift_replay",
                                  "target_replay_action_support_failures", "control_replay_action_support_failures")}
         == {"source_native": 12, "target_native": 12, "target_replay": 12, "no_shift_replay": 12,
             "target_replay_action_support_failures": 0, "control_replay_action_support_failures": 0}, "N2b: count/result drift")
    need(n2b["measurement_contract"]["v1_failure_run"] == 33972326066, "N2b: v1 exclusion provenance drift")
    need(len(n2b["replica_validations"]) == 2 and all(v["verdict"] == "PASS" for v in n2b["replica_validations"]),
         "N2b: independent validation drift")

    m = load(root / "PAPER_RESULTS_MANIFEST.json")
    need(m.get("status") == "FROZEN_CANONICAL", "manifest: freeze status drift")
    hr = m["headline_results"]
    need(hr["replay_semantics_can_change_benchmark_workload"]["e3b"]["R2_over_R1"]["numerator"] == 3 and
         hr["replay_semantics_can_change_benchmark_workload"]["e3b"]["R2_over_R1"]["denominator"] == 2, "manifest: E3b ratio drift")
    need(hr["replay_semantics_can_change_benchmark_workload"]["e3c"]["R2_over_R1"]["numerator"] == 3 and
         hr["replay_semantics_can_change_benchmark_workload"]["e3c"]["R2_over_R1"]["denominator"] == 2, "manifest: E3c ratio drift")
    need(hr["operation_identity_is_not_action_identity"]["TV_operation"]["value"] == 0 and
         hr["operation_identity_is_not_action_identity"]["TV_action"]["value"] == 1, "manifest: N2 TV drift")
    safe = hr["raw_feedback_difference_is_not_replay_invalidity"]
    need((safe["raw_feedback_TV"]["value"], safe["quotient_feedback_TV"]["value"], safe["TV_action"]["value"])
         == (1, 0, 0), "manifest: N2b safe-side result drift")
    need(m["governance"]["empirical_stop_active"] is True, "manifest: empirical stop disabled")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = ap.parse_args()
    try:
        audit(args.paper_root)
        print("PASS: independent paper audit reproduces canonical identities and critical results")
        return 0
    except Exception as exc:
        print(f"FAIL: independent audit: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
