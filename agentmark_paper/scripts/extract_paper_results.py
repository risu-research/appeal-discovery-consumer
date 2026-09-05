#!/usr/bin/env python3
import argparse
from pathlib import Path
from paper_results_lib import ValidationError, build, cjson
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--paper-root",type=Path,default=Path(__file__).resolve().parents[1]); ap.add_argument("--check",action="store_true"); a=ap.parse_args()
    try: text=cjson(build(a.paper_root))
    except ValidationError as e: print("FAIL:",e); return 2
    p=a.paper_root/"PAPER_RESULTS_MANIFEST.json"
    if a.check:
        if not p.is_file() or p.read_text(encoding="utf-8")!=text: print("FAIL: canonical manifest stale/missing"); return 3
        print("PASS: canonical manifest byte-for-byte reproducible"); return 0
    p.write_text(text,encoding="utf-8"); print("WROTE:",p); return 0
if __name__=="__main__": raise SystemExit(main())
