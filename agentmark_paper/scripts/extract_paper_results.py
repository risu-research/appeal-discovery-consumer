#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
from paper_results_lib import ValidationError, build_manifest, canonical_json

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paper-root", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    out = args.paper_root / "PAPER_RESULTS_MANIFEST.json"
    try:
        text = canonical_json(build_manifest(args.paper_root))
    except ValidationError as exc:
        print(f"FAIL: {exc}")
        return 2
    if args.check:
        if not out.is_file() or out.read_text(encoding="utf-8") != text:
            print("FAIL: PAPER_RESULTS_MANIFEST.json is stale or missing")
            return 3
        print("PASS: canonical manifest is byte-for-byte reproducible")
        return 0
    out.write_text(text, encoding="utf-8")
    print(f"WROTE: {out}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
