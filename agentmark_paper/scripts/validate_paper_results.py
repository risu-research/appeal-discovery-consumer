#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
from paper_results_lib import ValidationError, build_manifest, canonical_json, load_json, manifest_sha256, validate_metric_types

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = ap.parse_args()
    try:
        expected = build_manifest(args.paper_root)
        validate_metric_types(expected)
        path = args.paper_root / "PAPER_RESULTS_MANIFEST.json"
        if not path.is_file():
            raise ValidationError("missing PAPER_RESULTS_MANIFEST.json")
        committed = load_json(path)
        validate_metric_types(committed)
        if canonical_json(committed) != canonical_json(expected):
            raise ValidationError("committed manifest differs from evidence-derived manifest")
        print("PASS: evidence hashes, source schemas, canonical provenance, semantic invariants,")
        print("      exact/measured type separation, exclusions, and committed manifest all validate")
        print(f"MANIFEST_SHA256={manifest_sha256(expected)}")
        print(f"EVIDENCE_TREE_SHA256={expected['evidence_tree_sha256']}")
        return 0
    except ValidationError as exc:
        print(f"FAIL: {exc}")
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
