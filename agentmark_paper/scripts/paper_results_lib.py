#!/usr/bin/env python3
"""Deterministic, fail-closed paper-results extraction for AgentMark.

This module is intentionally stdlib-only. Canonical paper numbers are derived
from sealed aggregate JSON capsules plus immutable GitHub Actions provenance.
Narrative memory is never an input.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

EXPECTED = ("e3b", "e3c", "n1", "n2", "n2b")

# Immutable upstream identity lock. These values were cross-checked against
# GitHub Actions run metadata and server-reported artifact digests before freeze.
CANONICAL_SOURCE_LOCK = {
    "e3b": {
        "run_id": 33935626964,
        "workflow": "AgentMark E3b Mosquitto Promotion",
        "branch": "agentmark-e3b-lab",
        "execution_commit": "5f5eb578f2d47de8e8ac53c1dacee917c49cd9dd",
        "artifact_id": 9960088059,
        "artifact_name": "agentmark-e3b-decisive-v2",
        "artifact_archive_sha256": "829e05748ae38c76f880ab57538112a980c1da3d3ebedd4b84c1e6409093eb95",
        "primary_sha256": "46d0ef0c82cf1fd40c3746cffb667d101d32a5431e7b52f99a9fa7fecf323b12",
        "source_schema": "agentmark.e3b.r0_r1_r2_certificate.v2",
        "evidence_id": "E3b",
        "role": "headline_positive_witness",
        "primary_source_filename": "e3b_r0_r1_r2_certificate.json",
    },
    "e3c": {
        "run_id": 33942887473,
        "workflow": "AgentMark E3c Home Assistant Ecological Replication",
        "branch": "agentmark-e3c-home-assistant",
        "execution_commit": "02028046d3f3d4fc32ed44b15c4b986e9df3545a",
        "artifact_id": 9962430737,
        "artifact_name": "agentmark-e3c-home-assistant-replicated",
        "artifact_archive_sha256": "7ef5140a6dcdaee508154d49071aa15733da95b7507ead7d8d63afc963a12cb3",
        "primary_sha256": "9e1e91d4e7733880da8236b3a4afb3647f8aa9582fe8f7d6d2a8ec44f038653b",
        "source_schema": "agentmark.e3c.home_assistant.replicated_aggregate.v1",
        "evidence_id": "E3c",
        "role": "headline_ecological_replication",
        "primary_source_filename": "e3c_home_assistant_replicated.json",
    },
    "n1": {
        "run_id": 33946985750,
        "workflow": "AgentMark N1 Official HA Motion-Light",
        "branch": "agentmark-theory-lock",
        "execution_commit": "5b2ba2aa35bf0bd00715b6b9475b44d9695c3c8f",
        "artifact_id": 9963663630,
        "artifact_name": "agentmark-n1-official-motion-light-replicated",
        "artifact_archive_sha256": "14dfde9ff11865a548984ec4858429258d2d4fc1b7584c41d96a251530eb3f27",
        "primary_sha256": "4812816bd830b5e71d89843f8510c44f93c37a89b054ae8ef7a9358e90ec00f7",
        "source_schema": "agentmark.natural_controller.motion_light.replicated.v1",
        "evidence_id": "N1",
        "role": "headline_external_official_controller",
        "primary_source_filename": "N1_MOTION_LIGHT_REPLICATED.json",
    },
    "n2": {
        "run_id": 33965918153,
        "workflow": "AgentMark N2 Better Thermostat Action Identity",
        "branch": "agentmark-theory-lock",
        "execution_commit": "4264c43d013178c8babedf772b1c06c5ddbe73cb",
        "artifact_id": 9969439579,
        "artifact_name": "agentmark-n2-better-thermostat-v4-replicated",
        "artifact_archive_sha256": "76bd2850156040139aabd935ccab44f01fb27344770c2f04a055fed81ee901b7",
        "primary_sha256": "df389a937832374008e459afd2a0454e632675a713b0a3b2b7d1b9258894d446",
        "source_schema": "agentmark.natural_controller.better_thermostat.replicated.v4",
        "evidence_id": "N2",
        "role": "headline_action_identity_counterexample",
        "primary_source_filename": "N2_BETTER_THERMOSTAT_REPLICATED.json",
    },
    "n2b": {
        "run_id": 33972619262,
        "workflow": "AgentMark N2b Decision Equivalence v2",
        "branch": "agentmark-n2b-decision-equivalence",
        "execution_commit": "9ec25a1cc2a16bff893d7ff5ffc9271bf6e059f6",
        "artifact_id": 9971397583,
        "artifact_name": "agentmark-n2b-decision-equivalence-v2-replicated",
        "artifact_archive_sha256": "4d75b17e6bd0bd9ba41cb574f9bca022364c312c09b215b74a36a92fda5861db",
        "primary_sha256": "93975a490a6af4e48e35152a77129430df0b0f7883015fc2ce72bd0d6fdffe75",
        "source_schema": "agentmark.n2b.replicated_aggregate.v2",
        "evidence_id": "N2b",
        "role": "headline_safe_side_decision_equivalence",
        "primary_source_filename": "N2B_DECISION_EQUIVALENCE_V2_REPLICATED.json",
    },
}

CANONICAL_REPLICA_ARTIFACTS = {
    "e3c": [
        {"replica": 0, "artifact_id": 9962428621, "sha256": "9c12212d1239a68235763e9c0e7a295e16d34fef653ab19f4329854b92a61262"},
        {"replica": 1, "artifact_id": 9962428209, "sha256": "ebc0b0a6fa306608776b32905c1744cdb1456640f1f69e824c18c1dffe2c762d"},
    ],
    "n1": [
        {"replica": 0, "artifact_id": 9963661146, "sha256": "b444792e46d8fa76b7a6829fa6de526948ddcc61d17710e5b0bfdb48b27042d4"},
        {"replica": 1, "artifact_id": 9963660995, "sha256": "1e6fe88ddc380329897ab9441c1974ce0174bfd35198e3ceadddfa37b8999fc1"},
    ],
    "n2": [
        {"replica": 0, "artifact_id": 9969436636, "sha256": "765bc094b51173341ddd1af7539b46e6714d92f66c0ccb30267f6ada813f388e"},
        {"replica": 1, "artifact_id": 9969435125, "sha256": "632eaae611e2bc1d96340eaa6ff19f4ab980aebffe65e0d8ed30e7f2256dd046"},
    ],
    "n2b": [
        {"replica": 0, "artifact_id": 9971395032, "sha256": "e7282f932832ac241dfd98ea60ee6a70157d74773e9c385917e37dc2388ba6a5"},
        {"replica": 1, "artifact_id": 9971395797, "sha256": "3be804d49d91cc4d1a9a03281495b90c6136df4ad773a51bfa8c3f2f6029649e"},
    ],
}


class ValidationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValidationError(f"cannot parse JSON {path}: {exc}") from exc


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def exact_count(value: int, unit: str) -> Dict[str, Any]:
    require(isinstance(value, int) and not isinstance(value, bool), f"exact count must be int: {value!r}")
    return {"kind": "exact_count", "value": value, "unit": unit}


def exact_fraction(numerator: int, denominator: int, label: str) -> Dict[str, Any]:
    require(isinstance(numerator, int) and not isinstance(numerator, bool) and isinstance(denominator, int) and not isinstance(denominator, bool), "fraction inputs must be integers")
    require(denominator != 0, "fraction denominator must be nonzero")
    f = Fraction(numerator, denominator)
    return {
        "kind": "exact_fraction",
        "label": label,
        "numerator": f.numerator,
        "denominator": f.denominator,
        "decimal": float(f),
    }


def exact_scalar(value: int, label: str) -> Dict[str, Any]:
    require(isinstance(value, int) and not isinstance(value, bool) and value in (0, 1), f"expected exact 0/1 scalar for {label}, got {value!r}")
    return {"kind": "exact_scalar", "label": label, "value": value}


def empirical_fraction(successes: int, trials: int, label: str) -> Dict[str, Any]:
    require(isinstance(successes, int) and isinstance(trials, int), "empirical fraction must use integers")
    require(0 <= successes <= trials and trials > 0, f"invalid empirical fraction {successes}/{trials}")
    f = Fraction(successes, trials)
    return {
        "kind": "empirical_fraction",
        "label": label,
        "successes": successes,
        "trials": trials,
        "decimal": float(f),
    }


def measured_ms(value: float, label: str, replica: int | None = None) -> Dict[str, Any]:
    require(isinstance(value, (int, float)) and not isinstance(value, bool), f"measured ms must be numeric: {value!r}")
    out: Dict[str, Any] = {"kind": "measured_ms", "label": label, "value": float(value), "unit": "ms"}
    if replica is not None:
        out["replica"] = replica
    return out


def primary_bytes(evidence_dir: Path, key: str) -> bytes:
    """Return exact logical primary.json bytes from plain or lossless gzip storage."""
    plain = evidence_dir / "primary.json"
    packed = evidence_dir / "primary.json.gz"
    require(plain.is_file() or packed.is_file(), f"{key}: missing primary evidence")
    plain_bytes = plain.read_bytes() if plain.is_file() else None
    packed_bytes = None
    if packed.is_file():
        try:
            packed_bytes = gzip.decompress(packed.read_bytes())
        except Exception as exc:
            raise ValidationError(f"{key}: cannot decompress primary.json.gz: {exc}") from exc
    if plain_bytes is not None and packed_bytes is not None:
        require(plain_bytes == packed_bytes, f"{key}: plain/compressed primary representations disagree")
    return plain_bytes if plain_bytes is not None else packed_bytes  # type: ignore[return-value]


def evidence_tree_sha256(paper_root: Path) -> Tuple[str, list[dict[str, str]]]:
    """Hash logical evidence, independent of lossless physical storage encoding."""
    entries: list[dict[str, str]] = []
    governance_path = paper_root / "evidence" / "GOVERNANCE.json"
    require(governance_path.is_file(), "missing governance evidence")
    entries.append({
        "path": "evidence/GOVERNANCE.json",
        "sha256": sha256_file(governance_path),
    })
    for key in EXPECTED:
        d = paper_root / "evidence" / key
        prov_path = d / "PROVENANCE.json"
        require(prov_path.is_file(), f"{key}: missing provenance")
        entries.append({
            "path": f"evidence/{key}/PROVENANCE.json",
            "sha256": sha256_file(prov_path),
        })
        entries.append({
            "path": f"evidence/{key}/primary.json",
            "sha256": sha256_bytes(primary_bytes(d, key)),
        })
    entries.sort(key=lambda x: x["path"])
    payload = "".join(f"{x['sha256']}  {x['path']}\n" for x in entries).encode("utf-8")
    return sha256_bytes(payload), entries


def load_and_validate_sources(paper_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    sources: dict[str, Any] = {}
    for key in EXPECTED:
        d = paper_root / "evidence" / key
        prov_path = d / "PROVENANCE.json"
        require(prov_path.is_file(), f"missing provenance: {prov_path}")
        raw_primary = primary_bytes(d, key)
        try:
            primary = json.loads(raw_primary.decode("utf-8"))
        except Exception as exc:
            raise ValidationError(f"cannot parse logical primary evidence for {key}: {exc}") from exc
        prov = load_json(prov_path)
        require(prov.get("schema") == "agentmark.paper_evidence_provenance.v1", f"{key}: bad provenance schema")
        require(prov.get("canonical") is True, f"{key}: evidence is not canonical")
        require(prov.get("primary_filename") == "primary.json", f"{key}: primary filename drift")
        actual_hash = sha256_bytes(raw_primary)
        require(actual_hash == prov.get("primary_sha256"), f"{key}: primary SHA-256 mismatch")
        require(primary.get("schema") == prov.get("source_schema"), f"{key}: source schema mismatch")
        lock = CANONICAL_SOURCE_LOCK[key]
        for field, expected in lock.items():
            require(prov.get(field) == expected, f"{key}: canonical provenance drift for {field}")
        if key in CANONICAL_REPLICA_ARTIFACTS:
            require(prov.get("replica_artifacts") == CANONICAL_REPLICA_ARTIFACTS[key],
                    f"{key}: replica artifact provenance drift")
        if key == "n1":
            require(prov.get("noncanonical_history") == [{
                "run_id": 33945478968,
                "workflow": "AgentMark N1 Official HA Motion-Light",
                "execution_commit": "657db9b5bf048b47529c5f4c7adbe1569ca6ab27",
                "conclusion": "failure",
                "reason": "initial workflow execution failed; no canonical result",
            }], "N1 noncanonical history drift")
        sources[key] = {"primary": primary, "provenance": prov}
    governance = load_json(paper_root / "evidence" / "GOVERNANCE.json")
    require(governance.get("schema") == "agentmark.paper_results_governance.v1", "bad governance schema")
    require(governance.get("empirical_stop_active") is True, "empirical stop must remain active")
    excluded = governance.get("excluded_evidence", [])
    v1 = [x for x in excluded if x.get("id") == "N2b-v1"]
    require(len(v1) == 1 and v1[0] == {
        "id": "N2b-v1",
        "run_id": 33972326066,
        "workflow": "AgentMark N2b Natural Decision Equivalence",
        "execution_commit": "e2bb6c8e90295c448a4679ae4a342d791542c5ce",
        "conclusion": "failure",
        "canonical": False,
        "reason": "superseded invalid measurement contract; failed before a valid N2b result",
    }, "N2b v1 must remain exactly pinned and explicitly noncanonical")
    boundary = [x for x in excluded if x.get("id") == "E3b-safety-boundary"]
    require(len(boundary) == 1 and boundary[0] == {
        "id": "E3b-safety-boundary",
        "run_id": 33935626964,
        "artifact_id": 9960095929,
        "artifact_name": "agentmark-e3b-safety-boundary",
        "artifact_archive_sha256": "214a25bc666336d86d0e59f2031713b6d79d3cdd9704b8e6f9b75da03bfef257",
        "canonical_headline": False,
        "reason": "falsification/exploratory boundary evidence; not a headline result source",
    }, "E3b safety-boundary artifact must remain exactly pinned and non-headline")
    return sources, governance

def _int_from_exact_float(value: Any, context: str) -> int:
    require(isinstance(value, (int, float)) and not isinstance(value, bool), f"{context}: expected numeric")
    iv = int(value)
    require(float(iv) == float(value), f"{context}: expected integer-valued number, got {value}")
    return iv


def _e3b(p: dict[str, Any]) -> dict[str, Any]:
    require(p.get("schema") == "agentmark.e3b.r0_r1_r2_certificate.v2", "E3b schema drift")
    require(p.get("promotion_pass") is True, "E3b promotion no longer passes")
    rows = p.get("broker_publish_conservation", [])
    grouped: dict[str, list[int]] = {"R0_rigid": [], "R1_timing": [], "R2_semantic": []}
    for row in rows:
        mode = row.get("mode")
        require(mode in grouped, f"E3b unexpected broker mode {mode!r}")
        require(row.get("exact") is True and float(row.get("error", 1)) == 0.0, "E3b broker conservation not exact")
        observed = _int_from_exact_float(row.get("observed"), f"E3b {mode} observed")
        expected = _int_from_exact_float(row.get("expected"), f"E3b {mode} expected")
        require(observed == expected, f"E3b {mode} observed != expected")
        grouped[mode].append(observed)
    for mode, vals in grouped.items():
        require(len(vals) == 12, f"E3b {mode}: expected 12 decisive trials, got {len(vals)}")
        require(len(set(vals)) == 1, f"E3b {mode}: work count varies across trials")
    r0, r1, r2 = (grouped["R0_rigid"][0], grouped["R1_timing"][0], grouped["R2_semantic"][0])
    require((r0, r1, r2) == (512, 512, 768), f"E3b canonical work counts drifted: {(r0,r1,r2)}")
    a = p["aggregate"]
    require(a["r0_violation"] == 1.0 and a["r1_violation"] == 1.0 and a["r2_violation"] == 0.0,
            "E3b semantic-support rates drifted")
    require(a["r2_verify_fraction"] == 1.0, "E3b R2 VERIFY fraction drifted")
    cert = p.get("replay_safety_certificate", {})
    require(cert.get("classification") == "CERTIFIED_UNSAFE", "E3b safety certificate drifted")
    return {
        "work_per_trial": {
            "R0": exact_count(r0, "broker PUBLISH"),
            "R1": exact_count(r1, "broker PUBLISH"),
            "R2": exact_count(r2, "broker PUBLISH"),
        },
        "R2_over_R1_workload": exact_fraction(r2, r1, "native broker-PUBLISH workload ratio"),
        "semantic_support_failure": {
            "R0": empirical_fraction(12, 12, "support-violating trials"),
            "R1": empirical_fraction(12, 12, "support-violating trials"),
            "R2": empirical_fraction(0, 12, "support-violating trials"),
        },
        "R2_verify": empirical_fraction(12, 12, "VERIFY trials"),
        "replay_safety_certificate": {
            "classification": "CERTIFIED_UNSAFE",
            "policy_feedback_sensitivity_eta": exact_scalar(_int_from_exact_float(cert["policy_feedback_sensitivity_eta"], "E3b eta"), "eta"),
            "epsilon": cert["epsilon"],
            "confidence": cert["confidence"],
        },
        "timing": {
            "R1_shift_vs_R0": measured_ms(a["r1_timing_shift_ms"], "aggregate R1 timing shift vs R0"),
            "R0_p99": measured_ms(a["r0_p99"], "R0 p99"),
            "R1_p99": measured_ms(a["r1_p99"], "R1 p99"),
            "R2_p99": measured_ms(a["r2_p99"], "R2 p99"),
        },
    }


def _e3c(p: dict[str, Any]) -> dict[str, Any]:
    require(p.get("schema") == "agentmark.e3c.home_assistant.replicated_aggregate.v1", "E3c schema drift")
    require(p.get("decision") == "PROMOTED_REPLICATED" and p.get("replicas") == 2, "E3c promotion/replicas drift")
    vals = p.get("validation_artifacts", [])
    require(len(vals) == 2 and all(v.get("pass") is True for v in vals), "E3c validations must both pass")
    w = p["exact_native_work_per_trial"]
    r0 = _int_from_exact_float(w["R0"], "E3c R0 native work")
    r1 = _int_from_exact_float(w["R1"], "E3c R1 native work")
    r2 = _int_from_exact_float(w["R2"], "E3c R2 native work")
    require((r0, r1, r2) == (256, 256, 384), f"E3c canonical work counts drifted: {(r0,r1,r2)}")
    a = p["aggregate"]
    require(a["R0"]["support_violation_rate"] == 1.0, "E3c R0 support rate drift")
    require(a["R1"]["support_violation_rate"] == 1.0, "E3c R1 support rate drift")
    require(a["R2"]["support_violation_rate"] == 0.0 and a["R2"]["verify_fraction"] == 1.0, "E3c R2 semantics drift")
    p99 = p["source_completion_p99_ms_by_replica"]
    require(isinstance(p99, list) and len(p99) == 2, "E3c p99 must remain replica-separated")
    return {
        "work_per_trial": {
            "R0": exact_count(r0, "native Home Assistant service calls"),
            "R1": exact_count(r1, "native Home Assistant service calls"),
            "R2": exact_count(r2, "native Home Assistant service calls"),
        },
        "R2_over_R1_workload": exact_fraction(r2, r1, "native Home Assistant workload ratio"),
        "semantic_support_failure": {
            "R0": empirical_fraction(_int_from_exact_float(a["R0"]["n"], "E3c R0 n"), _int_from_exact_float(a["R0"]["n"], "E3c R0 n"), "support-violating rows"),
            "R1": empirical_fraction(_int_from_exact_float(a["R1"]["n"], "E3c R1 n"), _int_from_exact_float(a["R1"]["n"], "E3c R1 n"), "support-violating rows"),
            "R2": empirical_fraction(0, _int_from_exact_float(a["R2"]["n"], "E3c R2 n"), "support-violating rows"),
        },
        "R2_verify": empirical_fraction(_int_from_exact_float(a["R2"]["n"], "E3c R2 n"), _int_from_exact_float(a["R2"]["n"], "E3c R2 n"), "VERIFY rows"),
        "timing": {
            "source_completion_p99_by_replica": [
                measured_ms(p99[0], "source completion p99", 0),
                measured_ms(p99[1], "source completion p99", 1),
            ],
            "R1_mean_act2_shift_vs_source": measured_ms(a["R1"]["mean_act2_shift_vs_source_ms"], "R1 mean act2 shift vs source"),
            "R2_mean_act2_shift_vs_source": measured_ms(a["R2"]["mean_act2_shift_vs_source_ms"], "R2 mean act2 shift vs source"),
        },
        "claim_boundary": p["claim_boundary"],
    }


def _n1(p: dict[str, Any]) -> dict[str, Any]:
    require(p.get("schema") == "agentmark.natural_controller.motion_light.replicated.v1", "N1 schema drift")
    require(p.get("decision") == "PROMOTED_REPLICATED", "N1 decision drift")
    require(p.get("independent_validations_passed") == 2 and p.get("replicas") == [0, 1], "N1 replication drift")
    tc = p["trial_counts"]
    require(tc["per_mode_per_replica"] == 6 and tc["per_mode_total"] == 12, "N1 trial count drift")
    summaries = p["runner_summaries"]
    require([x["replica"] for x in summaries] == [0, 1], "N1 runner ordering/identity drift")
    timings = []
    for s in summaries:
        r = s["replica"]
        prod = s["producer_aggregate"]
        val = s["validation_recomputed"]
        for key in ("R1_minus_R0_mean_ms", "R2_minus_source_mean_ms"):
            require(prod[key] == val[key], f"N1 replica {r}: producer/validator timing disagreement for {key}")
        require(prod["R0_support_failure_rate"] == 1.0 and prod["R1_support_failure_rate"] == 1.0
                and prod["R2_support_failure_rate"] == 0.0, f"N1 replica {r}: support rates drift")
        timings.append({
            "replica": r,
            "R1_minus_R0": measured_ms(prod["R1_minus_R0_mean_ms"], "R1 minus R0 mean", r),
            "R2_minus_source": measured_ms(prod["R2_minus_source_mean_ms"], "R2 minus source mean", r),
        })
    require(timings[0]["R1_minus_R0"]["value"] == 35.24896700000001, "N1 replica 0 canonical timing drift")
    require(timings[1]["R1_minus_R0"]["value"] == 35.178532166666656, "N1 replica 1 canonical timing drift")
    ext = p["external_controller"]
    require(ext["repository"] == "home-assistant/core" and ext["source_edited"] is False, "N1 external source drift")
    return {
        "semantic_support_failure": {
            "R0": empirical_fraction(12, 12, "support-violating trials"),
            "R1": empirical_fraction(12, 12, "support-violating trials"),
            "R2": empirical_fraction(0, 12, "support-violating trials"),
        },
        "timing_by_replica": timings,
        "independent_validations": exact_count(2, "validators passed"),
        "external_controller": ext,
    }


def _n2(p: dict[str, Any]) -> dict[str, Any]:
    require(p.get("schema") == "agentmark.natural_controller.better_thermostat.replicated.v4", "N2 schema drift")
    require(p.get("decision") == "PROMOTED_REPLICATED", "N2 decision drift")
    require(p.get("independent_validations_passed") == 2 and p.get("replicas") == [0, 1], "N2 replication drift")
    rec = p["recomputed_across_replicas"]
    require(rec["TV_operation"] == 0.0 and rec["TV_action"] == 1.0, "N2 TV headline drift")
    require(rec["TV_operation_each_runner"] == [0.0, 0.0] and rec["TV_action_each_runner"] == [1.0, 1.0],
            "N2 runner TVs drift")
    srcs, tgts = rec["source_identities"], rec["target_identities"]
    require(len(srcs) == 2 and srcs[0] == srcs[1], "N2 source identity does not replicate")
    require(len(tgts) == 2 and tgts[0] == tgts[1], "N2 target identity does not replicate")
    require(srcs[0]["operation"] == tgts[0]["operation"] == "climate.set_preset_mode", "N2 operation identity drift")
    require(srcs[0]["variant"] == '{"preset_mode":"home"}', "N2 source action variant drift")
    require(tgts[0]["variant"] == '{"preset_mode":"away"}', "N2 target action variant drift")
    validations = p["runner_validations"]
    require(len(validations) == 2, "N2 requires two runner validations")
    require(all(v["observer_ordering_diagnostics"]["used_for_promotion"] is False for v in validations),
            "N2 observer-ordering diagnostics must remain non-promotional")
    return {
        "TV_operation": exact_scalar(0, "operation-level total variation"),
        "TV_action": exact_scalar(1, "action-level total variation"),
        "source_action": srcs[0],
        "target_action": tgts[0],
        "independent_validations": exact_count(2, "validators passed"),
        "claim_boundary": p["claim_boundary"],
        "diagnostic_exclusion": "observer_ordering_diagnostics.used_for_promotion=false in both replicas",
    }


def _n2b(p: dict[str, Any]) -> dict[str, Any]:
    require(p.get("schema") == "agentmark.n2b.replicated_aggregate.v2", "N2b schema drift")
    require(p.get("decision") == "PROMOTED_REPLICATED" and p.get("replicas") == [0, 1], "N2b promotion/replicas drift")
    theory = p["theory"]
    require(theory["raw_feedback_tv"] == 1.0, "N2b raw feedback TV drift")
    require(theory["quotient_feedback_tv"] == 0.0, "N2b quotient TV drift")
    require(theory["TV_operation"] == 0.0 and theory["TV_action"] == 0.0, "N2b workload TVs drift")
    require(theory["pair_restricted_eta_action"] == 0.0 and theory["unsupported_feedback"] == [], "N2b eta/support drift")
    vals = p["replica_validations"]
    require(len(vals) == 2 and [x["replica"] for x in vals] == [0, 1], "N2b validation replicas drift")
    require(all(x["verdict"] == "PASS" and x["producer_consistent_with_independent_validation"] is True for x in vals),
            "N2b independent validation failed")
    require(all(all(x["checks"].values()) for x in vals), "N2b validator check false")
    counts = p["counts"]
    expected = {"source_native":12, "target_native":12, "target_replay":12, "no_shift_replay":12,
                "target_replay_action_support_failures":0, "control_replay_action_support_failures":0}
    require(all(counts.get(k) == v for k,v in expected.items()), f"N2b counts drifted: {counts}")
    require(p["measurement_contract"]["v1_failure_run"] == 33972326066, "N2b v1 failure provenance drift")
    return {
        "raw_feedback_TV": exact_scalar(1, "raw feedback total variation"),
        "quotient_feedback_TV": exact_scalar(0, "decision-quotient feedback total variation"),
        "TV_operation": exact_scalar(0, "operation-level total variation"),
        "TV_action": exact_scalar(0, "action-level total variation"),
        "pair_restricted_eta_action": exact_scalar(0, "pair-restricted action sensitivity eta"),
        "target_replay_support_failures": empirical_fraction(0, 12, "action-support failures"),
        "control_replay_support_failures": empirical_fraction(0, 12, "action-support failures"),
        "independent_validations": exact_count(2, "validators passed"),
        "decision_equivalence_class": theory["action_feedback_classes"],
    }


def build_manifest(paper_root: Path) -> dict[str, Any]:
    sources, governance = load_and_validate_sources(paper_root)
    e3b = _e3b(sources["e3b"]["primary"])
    e3c = _e3c(sources["e3c"]["primary"])
    n1 = _n1(sources["n1"]["primary"])
    n2 = _n2(sources["n2"]["primary"])
    n2b = _n2b(sources["n2b"]["primary"])
    tree_hash, file_hashes = evidence_tree_sha256(paper_root)

    evidence = {}
    for key in EXPECTED:
        prov = sources[key]["provenance"]
        evidence[key] = {
            "canonical": True,
            "role": prov["role"],
            "run_id": prov["run_id"],
            "workflow": prov["workflow"],
            "branch": prov["branch"],
            "execution_commit": prov["execution_commit"],
            "artifact_id": prov["artifact_id"],
            "artifact_name": prov["artifact_name"],
            "artifact_archive_sha256": prov["artifact_archive_sha256"],
            "primary_sha256": prov["primary_sha256"],
            "source_schema": prov["source_schema"],
        }

    return {
        "schema": "agentmark.paper_results_manifest.v1",
        "status": "FROZEN_CANONICAL",
        "generation_policy": {
            "machine_owned": True,
            "source": "sealed evidence capsules only",
            "narrative_memory_is_authoritative": False,
            "exact_vs_measured_type_separation": True,
        },
        "evidence_tree_sha256": tree_hash,
        "canonical_provenance_lock_sha256": sha256_bytes(canonical_json(CANONICAL_SOURCE_LOCK).encode("utf-8")),
        "evidence_file_hashes": file_hashes,
        "evidence": evidence,
        "headline_results": {
            "timing_fidelity_is_not_controller_semantic_fidelity": {
                "state": "CLOSED",
                "evidence": ["e3b", "e3c", "n1"],
                "e3b": {"semantic_support_failure": e3b["semantic_support_failure"], "R2_verify": e3b["R2_verify"]},
                "e3c": {"semantic_support_failure": e3c["semantic_support_failure"], "R2_verify": e3c["R2_verify"]},
                "n1": {"semantic_support_failure": n1["semantic_support_failure"]},
            },
            "replay_semantics_can_change_benchmark_workload": {
                "state": "CLOSED",
                "evidence": ["e3b", "e3c"],
                "e3b": {"work_per_trial": e3b["work_per_trial"], "R2_over_R1": e3b["R2_over_R1_workload"]},
                "e3c": {"work_per_trial": e3c["work_per_trial"], "R2_over_R1": e3c["R2_over_R1_workload"]},
            },
            "operation_identity_is_not_action_identity": {
                "state": "CLOSED",
                "evidence": ["n2"],
                "TV_operation": n2["TV_operation"],
                "TV_action": n2["TV_action"],
                "source_action": n2["source_action"],
                "target_action": n2["target_action"],
            },
            "raw_feedback_difference_is_not_replay_invalidity": {
                "state": "CLOSED",
                "evidence": ["n2b"],
                "raw_feedback_TV": n2b["raw_feedback_TV"],
                "quotient_feedback_TV": n2b["quotient_feedback_TV"],
                "TV_operation": n2b["TV_operation"],
                "TV_action": n2b["TV_action"],
                "pair_restricted_eta_action": n2b["pair_restricted_eta_action"],
                "target_replay_support_failures": n2b["target_replay_support_failures"],
            },
        },
        "measured_timing": {
            "e3b": e3b["timing"],
            "e3c": e3c["timing"],
            "n1": {
                "policy": "replica values remain separate; no canonical cross-runner average",
                "timing_by_replica": n1["timing_by_replica"],
            },
        },
        "validation_summary": {
            "n1": n1["independent_validations"],
            "n2": n2["independent_validations"],
            "n2b": n2b["independent_validations"],
        },
        "claim_boundaries": {
            "e3c": e3c["claim_boundary"],
            "n2": n2["claim_boundary"],
            "n2b": "pair-restricted eta=0 is not a claim that the full Better Thermostat controller is feedback-insensitive.",
        },
        "governance": {
            "empirical_stop_active": True,
            "empirical_stop_source": governance["empirical_stop_source"],
            "excluded_evidence": governance["excluded_evidence"],
            "authoritative_rule": governance["authoritative_rule"],
        },
    }


def validate_metric_types(manifest: dict[str, Any]) -> None:
    exact_area = manifest["headline_results"]["replay_semantics_can_change_benchmark_workload"]
    for eid in ("e3b", "e3c"):
        ratio = exact_area[eid]["R2_over_R1"]
        require(ratio.get("kind") == "exact_fraction", f"{eid}: workload ratio must be exact_fraction")
        require((ratio.get("numerator"), ratio.get("denominator")) == (3, 2), f"{eid}: workload ratio must be exactly 3/2")
        require(ratio.get("decimal") == 1.5, f"{eid}: derived decimal must be 1.5")
        for mode in ("R0", "R1", "R2"):
            require(exact_area[eid]["work_per_trial"][mode].get("kind") == "exact_count",
                    f"{eid}: workload counts must be exact_count")
    # measured timing must never leak into the exact workload subtree.
    def walk(obj: Any) -> Iterable[dict[str, Any]]:
        if isinstance(obj, dict):
            if "kind" in obj:
                yield obj
            for v in obj.values():
                yield from walk(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from walk(v)
    require(all(m.get("kind") != "measured_ms" for m in walk(exact_area)),
            "measured_ms leaked into exact workload results")
    n1timing = manifest["measured_timing"]["n1"]
    require(set(n1timing) == {"policy", "timing_by_replica"},
            "N1 timing subtree may contain only policy and per-replica measurements")
    require(n1timing["policy"] == "replica values remain separate; no canonical cross-runner average",
            "N1 timing aggregation policy drift")
    rows = n1timing["timing_by_replica"]
    require(isinstance(rows, list) and len(rows) == 2, "N1 timing must contain exactly two replica rows")
    require([r["replica"] for r in rows] == [0, 1], "N1 timing must retain replicas 0 and 1 separately")
    require(all(set(r) == {"replica", "R1_minus_R0", "R2_minus_source"} for r in rows),
            "N1 timing rows contain unexpected aggregation fields")
    for r in rows:
        require(r["R1_minus_R0"]["kind"] == "measured_ms" and r["R2_minus_source"]["kind"] == "measured_ms",
                "N1 timing metrics must be typed measured_ms")


def manifest_sha256(manifest: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json(manifest).encode("utf-8"))
