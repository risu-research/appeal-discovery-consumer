#!/usr/bin/env python3
from __future__ import annotations
import gzip
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
PAPER_ROOT = HERE.parents[1]
VALIDATOR = PAPER_ROOT / "scripts" / "validate_paper_results.py"
EXTRACTOR = PAPER_ROOT / "scripts" / "extract_paper_results.py"
GENERATOR = PAPER_ROOT / "scripts" / "generate_paper_views.py"

def run(script: Path, root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), "--paper-root", str(root), *extra],
        text=True, capture_output=True, check=False,
    )

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

class PaperResultsFreezeTests(unittest.TestCase):
    def temp_copy(self):
        td = tempfile.TemporaryDirectory()
        dst = Path(td.name) / "agentmark_paper"
        shutil.copytree(PAPER_ROOT, dst)
        return td, dst

    def test_baseline_closure_validates(self):
        cp = run(VALIDATOR, PAPER_ROOT)
        self.assertEqual(cp.returncode, 0, cp.stdout + cp.stderr)
        self.assertEqual(run(EXTRACTOR, PAPER_ROOT, "--check").returncode, 0)
        self.assertEqual(run(GENERATOR, PAPER_ROOT, "--check").returncode, 0)

    def test_lossless_gzip_storage_is_representation_invariant(self):
        td, dst = self.temp_copy()
        try:
            p = dst / "evidence/e3b/primary.json"
            packed = dst / "evidence/e3b/primary.json.gz"
            raw = p.read_bytes() if p.is_file() else gzip.decompress(packed.read_bytes())
            packed.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))
            if p.is_file():
                p.unlink()
            cp = run(VALIDATOR, dst)
            self.assertEqual(cp.returncode, 0, cp.stdout + cp.stderr)
            self.assertEqual(run(EXTRACTOR, dst, "--check").returncode, 0)
            self.assertEqual(run(GENERATOR, dst, "--check").returncode, 0)
        finally:
            td.cleanup()

    def test_byte_tamper_is_rejected_by_provenance_hash(self):
        td, dst = self.temp_copy()
        try:
            p = dst / "evidence/e3c/primary.json"
            obj = json.loads(p.read_text())
            obj["exact_native_work_per_trial"]["R2"] = 383
            p.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
            cp = run(VALIDATOR, dst)
            self.assertNotEqual(cp.returncode, 0)
            self.assertIn("SHA-256 mismatch", cp.stdout)
        finally:
            td.cleanup()

    def test_semantic_tamper_is_rejected_even_if_attacker_rehashes_capsule(self):
        td, dst = self.temp_copy()
        try:
            p = dst / "evidence/e3b/primary.json"
            packed = dst / "evidence/e3b/primary.json.gz"
            if not p.is_file():
                p.write_bytes(gzip.decompress(packed.read_bytes()))
                packed.unlink()
            obj = json.loads(p.read_text())
            target = next(r for r in obj["broker_publish_conservation"]
                          if r["mode"] == "R2_semantic" and r["trial"] == 0)
            target["observed"] = 767.0
            target["expected"] = 767.0
            p.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
            provp = dst / "evidence/e3b/PROVENANCE.json"
            prov = json.loads(provp.read_text())
            prov["primary_sha256"] = sha(p)
            provp.write_text(json.dumps(prov, indent=2, sort_keys=True) + "\n")
            cp = run(VALIDATOR, dst)
            self.assertNotEqual(cp.returncode, 0)
            self.assertTrue("canonical provenance drift" in cp.stdout or "work count varies" in cp.stdout or "canonical work counts drifted" in cp.stdout, cp.stdout)
        finally:
            td.cleanup()

    def test_workload_timing_type_confusion_is_rejected(self):
        td, dst = self.temp_copy()
        try:
            p = dst / "PAPER_RESULTS_MANIFEST.json"
            obj = json.loads(p.read_text())
            metric = obj["headline_results"]["replay_semantics_can_change_benchmark_workload"]["e3b"]["R2_over_R1"]
            metric.clear()
            metric.update({"kind":"measured_ms","label":"wrong timing substitution","value":145.8477432721354,"unit":"ms"})
            p.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
            cp = run(VALIDATOR, dst)
            self.assertNotEqual(cp.returncode, 0)
        finally:
            td.cleanup()

    def test_n1_cross_runner_average_is_not_admitted(self):
        td, dst = self.temp_copy()
        try:
            p = dst / "PAPER_RESULTS_MANIFEST.json"
            obj = json.loads(p.read_text())
            n1 = obj["measured_timing"]["n1"]
            n1["timing_by_replica"] = [{
                "replica":"average",
                "R1_minus_R0":{"kind":"measured_ms","label":"forbidden average","value":35.21374958333333,"unit":"ms"},
                "R2_minus_source":{"kind":"measured_ms","label":"forbidden average","value":119.56934391666667,"unit":"ms"},
            }]
            p.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
            cp = run(VALIDATOR, dst)
            self.assertNotEqual(cp.returncode, 0)
        finally:
            td.cleanup()

    def test_noncanonical_n2b_v1_cannot_be_promoted(self):
        td, dst = self.temp_copy()
        try:
            p = dst / "evidence/GOVERNANCE.json"
            obj = json.loads(p.read_text())
            v1 = next(x for x in obj["excluded_evidence"] if x["id"] == "N2b-v1")
            v1["canonical"] = True
            p.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
            cp = run(VALIDATOR, dst)
            self.assertNotEqual(cp.returncode, 0)
            self.assertIn("N2b v1 must remain exactly pinned and explicitly noncanonical", cp.stdout)
        finally:
            td.cleanup()

    def test_provenance_role_relabel_is_rejected(self):
        td, dst = self.temp_copy()
        try:
            p = dst / "evidence/n2b/PROVENANCE.json"
            obj = json.loads(p.read_text())
            obj["role"] = "headline_positive_witness"
            p.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
            cp = run(VALIDATOR, dst)
            self.assertNotEqual(cp.returncode, 0)
            self.assertIn("canonical provenance drift for role", cp.stdout)
        finally:
            td.cleanup()

    def test_provenance_repoint_is_rejected_even_if_self_consistent(self):
        td, dst = self.temp_copy()
        try:
            p = dst / "evidence/n1/PROVENANCE.json"
            obj = json.loads(p.read_text())
            obj["artifact_id"] = 123456789
            p.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
            cp = run(VALIDATOR, dst)
            self.assertNotEqual(cp.returncode, 0)
            self.assertIn("canonical provenance drift", cp.stdout)
        finally:
            td.cleanup()

    def test_e3c_fractional_exact_work_is_rejected_even_if_rehashed(self):
        td, dst = self.temp_copy()
        try:
            p = dst / "evidence/e3c/primary.json"
            obj = json.loads(p.read_text())
            obj["exact_native_work_per_trial"]["R2"] = 384.5
            p.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
            provp = dst / "evidence/e3c/PROVENANCE.json"
            prov = json.loads(provp.read_text())
            prov["primary_sha256"] = sha(p)
            provp.write_text(json.dumps(prov, indent=2, sort_keys=True) + "\n")
            cp = run(VALIDATOR, dst)
            self.assertNotEqual(cp.returncode, 0)
            # Either immutable provenance lock or strict integer semantics must reject it.
            self.assertTrue("canonical provenance drift" in cp.stdout or "expected integer-valued" in cp.stdout, cp.stdout)
        finally:
            td.cleanup()

    def test_n1_timing_subtree_rejects_extra_aggregate_field(self):
        td, dst = self.temp_copy()
        try:
            p = dst / "PAPER_RESULTS_MANIFEST.json"
            obj = json.loads(p.read_text())
            obj["measured_timing"]["n1"]["cross_runner_average_ms"] = 35.21
            p.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")
            cp = run(VALIDATOR, dst)
            self.assertNotEqual(cp.returncode, 0)
        finally:
            td.cleanup()

if __name__ == "__main__":
    unittest.main()
