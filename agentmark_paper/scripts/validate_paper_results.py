#!/usr/bin/env python3
import argparse
from pathlib import Path
from paper_results_lib import ValidationError, build, cjson, readj, typecheck, mhash
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--paper-root",type=Path,default=Path(__file__).resolve().parents[1]); a=ap.parse_args()
    try:
        expected=build(a.paper_root); typecheck(expected)
        p=a.paper_root/"PAPER_RESULTS_MANIFEST.json"
        if not p.is_file(): raise ValidationError("missing PAPER_RESULTS_MANIFEST.json")
        got=readj(p); typecheck(got)
        if cjson(got)!=cjson(expected): raise ValidationError("committed manifest differs from evidence-derived manifest")
        print("PASS: provenance, capsule semantics, type separation, exclusions, and manifest validate")
        print("CANONICAL_EVIDENCE_SHA256="+expected["canonical_evidence_sha256"])
        print("MANIFEST_SHA256="+mhash(expected)); return 0
    except ValidationError as e: print("FAIL:",e); return 2
if __name__=="__main__": raise SystemExit(main())
