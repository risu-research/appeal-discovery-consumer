from __future__ import annotations

"""Verify Gate S0 as a pure current-runtime authority seal."""

import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "replaymark" / "CURRENT_RUNTIME_SEAL.json"

AUTHORITY_COMMIT = "25d317392b9ce6aaaedc190ef6aff8bc38d555b5"
AUTHORITY_TREE = "7f8349a10d884a212c3f7143dbd56e2b8cc13718"
AUTHORITY_PARENT = "a1445ce1b03aa75b95b97f518f1d79227f2206f9"
EXPECTED_CHANGED = {
    ".github/workflows/replaymark-runtime-gate-s0-current-seal.yml",
    "replaymark/CURRENT_RUNTIME_SEAL.json",
    "replaymark/CURRENT_RUNTIME_SEAL.md",
    "replaymark_verification/verify_current_runtime_seal.py",
}


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _flatten_blob_map(manifest: dict[str, object]) -> dict[str, str]:
    out: dict[str, str] = {}
    groups = manifest["frozen_blobs"]
    assert isinstance(groups, dict)
    for group_name, group in groups.items():
        assert isinstance(group_name, str)
        assert isinstance(group, dict)
        for path, sha in group.items():
            assert isinstance(path, str) and isinstance(sha, str)
            if path in out:
                raise AssertionError(f"duplicate frozen path: {path}")
            out[path] = sha
    return out


def verify() -> dict[str, object]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["schema"] == "replaymark.gate-s0-current-runtime-seal.v1"
    assert manifest["gate"] == "S0_CURRENT_RUNTIME_SEAL"

    authority = manifest["authority"]
    assert authority["commit"] == AUTHORITY_COMMIT
    assert authority["tree"] == AUTHORITY_TREE
    assert authority["parent"] == AUTHORITY_PARENT
    assert authority["workflow_run"] == 34144836504
    assert authority["workflow_conclusion"] == "success"
    assert authority["artifact"] == {
        "id": 10027299146,
        "name": "replaymark-runtime-e3b-same-object-binding-fast-path",
        "sha256": "c75868eefed78f80f8a13483020b79938d852c5e0083be029e425956e57a5625",
        "size_bytes": 94787,
    }

    head_parent = _git("rev-parse", "HEAD^")
    if head_parent != AUTHORITY_COMMIT:
        raise AssertionError(f"S0 must be exact child of authority: {head_parent} != {AUTHORITY_COMMIT}")
    parent_tree = _git("rev-parse", "HEAD^1^{tree}")
    if parent_tree != AUTHORITY_TREE:
        raise AssertionError(f"authority tree drift: {parent_tree} != {AUTHORITY_TREE}")
    authority_parent = _git("rev-parse", "HEAD^^")
    if authority_parent != AUTHORITY_PARENT:
        raise AssertionError(f"authority parent drift: {authority_parent} != {AUTHORITY_PARENT}")

    changed = set(_git("diff", "--name-only", "HEAD^", "HEAD").splitlines())
    if changed != EXPECTED_CHANGED:
        raise AssertionError(f"S0 increment drift: {sorted(changed)} != {sorted(EXPECTED_CHANGED)}")

    frozen = _flatten_blob_map(manifest)
    parent_matches = 0
    head_matches = 0
    for path, want in frozen.items():
        got_parent = _git("rev-parse", f"HEAD^:{path}")
        got_head = _git("rev-parse", f"HEAD:{path}")
        if got_parent != want:
            raise AssertionError(f"authority frozen blob mismatch {path}: {got_parent} != {want}")
        if got_head != want:
            raise AssertionError(f"S0 mutated frozen blob {path}: {got_head} != {want}")
        parent_matches += 1
        head_matches += 1

    closed = manifest["closed"]
    required_closed = {
        "semantic_core": "CLOSED",
        "explicit_compiled_contract": "CLOSED",
        "e3b_observation_realization": "PASS",
        "e3b_historical_action_realization": "PASS",
        "e3b_same_task_correlation": "PASS",
        "e3b_shadow_runtime_bridge": "PASS",
        "r1_noninterfering_shadow": "PASS",
        "integrated_frozen_runtime_conformance": "PASS",
        "runtime_cost_characterization": "PASS",
        "verified_contract_identity_reuse": "PASS",
        "same_object_certificate_binding": "PASS",
    }
    if closed != required_closed:
        raise AssertionError("closed-status manifest drift")

    assert manifest["not_implemented"] == {
        "execution_policy": "NOT_IMPLEMENTED",
        "selective_reuse_intervention": "NOT_IMPLEMENTED",
        "caller_owned_fallback": "NOT_IMPLEMENTED",
    }

    opt = manifest["optimization_policy"]
    assert opt["state"] == "FROZEN"
    assert "selective-reuse capstone" in opt["rule"]
    assert "material runtime bottleneck" in opt["reopen_only_if"]
    assert opt["forbidden_as_reopen_basis"] == [
        "aesthetic cleanup",
        "speculative speedup",
        "microbenchmark-only improvement without capstone relevance",
        "new semantic claim",
    ]

    boundary = manifest["scientific_boundary"]
    assert boundary["rstar_is"] == "maximally permissive fixed-evidence support-sound binary reuse rule"
    assert boundary["rstar_is_not"] == "fallback or regeneration policy"
    assert boundary["realization_failure_is_not"] == "semantic UNRESOLVED"
    assert boundary["runtime_seal_adds_semantics"] is False
    assert boundary["runtime_seal_adds_execution"] is False

    return {
        "schema": "replaymark.gate-s0-current-runtime-seal.verification.v1",
        "authority_commit": AUTHORITY_COMMIT,
        "authority_tree": AUTHORITY_TREE,
        "seal_head": _git("rev-parse", "HEAD"),
        "changed_files": sorted(changed),
        "frozen_blob_count": len(frozen),
        "authority_blob_matches": parent_matches,
        "seal_head_blob_matches": head_matches,
        "optimization_state": "FROZEN",
        "execution_policy": "NOT_IMPLEMENTED",
        "selective_reuse_intervention": "NOT_IMPLEMENTED",
        "verdict": "PASS",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out")
    args = parser.parse_args()
    report = verify()
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
