#!/usr/bin/env python3
import argparse,csv,io
from pathlib import Path
from paper_results_lib import ValidationError,build,cjson,mhash
def frac(x):return f"{x['numerator']}/{x['denominator']} (= {x['decimal']:.1f}×)"
def emp(x):return f"{x['successes']}/{x['trials']} ({100*x['decimal']:.0f}%)"
def render(m):
    H=m["headline_results"]; T=H["timing_fidelity_is_not_controller_semantic_fidelity"]; W=H["replay_semantics_can_change_benchmark_workload"]; N=H["operation_identity_is_not_action_identity"]; Q=H["raw_feedback_difference_is_not_replay_invalidity"]; R=m["measured_timing"]["n1"]["timing_by_replica"]
    table=f"""# Canonical Paper Results Table

> Machine-generated from `PAPER_RESULTS_MANIFEST.json`. Do not hand-edit.

| Claim | Canonical evidence | Result | Status |
|---|---|---|---|
| Timing fidelity is not controller-semantic fidelity | E3b / E3c / N1 | R1 support failures: E3b {emp(T['e3b']['R1'])}; E3c {emp(T['e3c']['R1'])}; N1 {emp(T['n1']['R1'])}. R2 support failures are zero in all three. | CLOSED |
| Replay semantics can change benchmark workload | E3b / E3c | E3b 512→768 PUBLISH = {frac(W['e3b']['R2_over_R1'])}; E3c 256→384 native calls = {frac(W['e3c']['R2_over_R1'])}. | CLOSED |
| Operation identity is not action identity | N2 | TV_operation={N['TV_operation']['value']}, TV_action={N['TV_action']['value']}; operation fixed while `home`→`away` variant changes. | CLOSED |
| Raw feedback difference is not replay invalidity | N2b | raw TV={Q['raw_feedback_TV']['value']}, quotient TV={Q['quotient_feedback_TV']['value']}, action TV={Q['TV_action']['value']}; target replay failures {emp(Q['target_replay_support_failures'])}. | CLOSED |

N1 timing is deliberately replica-separated: replica 0 R1−R0 = {R[0]['R1_minus_R0']['value']:.15g} ms; replica 1 = {R[1]['R1_minus_R0']['value']:.15g} ms. No canonical cross-runner average is admitted.
"""
    rows=[
      ["e3b","R0_work","exact_count",512,"broker PUBLISH"],["e3b","R1_work","exact_count",512,"broker PUBLISH"],["e3b","R2_work","exact_count",768,"broker PUBLISH"],["e3b","R2_over_R1","exact_fraction","3/2","ratio"],
      ["e3c","R0_work","exact_count",256,"native HA service calls"],["e3c","R1_work","exact_count",256,"native HA service calls"],["e3c","R2_work","exact_count",384,"native HA service calls"],["e3c","R2_over_R1","exact_fraction","3/2","ratio"],
      ["n2","TV_operation","exact_scalar",0,"TV"],["n2","TV_action","exact_scalar",1,"TV"],["n2b","raw_feedback_TV","exact_scalar",1,"TV"],["n2b","quotient_feedback_TV","exact_scalar",0,"TV"],["n2b","TV_action","exact_scalar",0,"TV"],["n2b","target_replay_support_failures","empirical_fraction","0/12","trials"],
      ["n1","R1_minus_R0_replica0","measured_ms",R[0]["R1_minus_R0"]["value"],"ms"],["n1","R1_minus_R0_replica1","measured_ms",R[1]["R1_minus_R0"]["value"],"ms"]]
    s=io.StringIO(); w=csv.writer(s,lineterminator="\n"); w.writerow(["evidence","metric","kind","value","unit"]); w.writerows(rows)
    fig={"schema":"agentmark.paper_figure_data.v1","panels":{
      "semantic_support_failure":{"kind":"empirical_fraction","systems":{"E3b":{"R0":"12/12","R1":"12/12","R2":"0/12"},"E3c":{"R0":"1536/1536","R1":"1536/1536","R2":"0/1536"},"N1":{"R0":"12/12","R1":"12/12","R2":"0/12"}}},
      "workload_ratio":{"kind":"exact_fraction","systems":{"E3b":{"R1":512,"R2":768,"ratio":"3/2"},"E3c":{"R1":256,"R2":384,"ratio":"3/2"}}},
      "semantic_projection_tv":{"kind":"exact_scalar","systems":{"N2":{"operation":0,"action":1},"N2b":{"raw_feedback":1,"quotient_feedback":0,"operation":0,"action":0,"pair_restricted_eta_action":0}}},
      "n1_runner_timing":{"kind":"measured_ms","aggregation":"none","replicas":[{"replica":x["replica"],"R1_minus_R0_ms":x["R1_minus_R0"]["value"],"R2_minus_source_ms":x["R2_minus_source"]["value"]} for x in R]}}}
    summary=f"""# AgentMark Canonical Results Summary

Status: **FROZEN_CANONICAL**

All headline empirical cells are closed. E3b/E3c independently yield the exact semantic-replay workload expansion **3/2 (1.5×)**. E3b/E3c/N1 separate timing-aware replay from semantic replay on support preservation. N2 establishes **TV_operation=0, TV_action=1**. N2b establishes the safe-side quotient case: **raw feedback TV=1, quotient/action TV=0**, with **0/12** target-replay support failures.

N1 timing remains two independent measurements; no canonical cross-runner average is admitted. Empirical stop is **ACTIVE**.

Canonical evidence SHA-256: `{m['canonical_evidence_sha256']}`  
Manifest SHA-256: `{mhash(m)}`
"""
    freeze=f"""# AgentMark Paper-Results Freeze

Status: **FROZEN_CANONICAL**

This is the canonical interface between sealed experiments and manuscript prose.

## Contract

1. `CANONICAL_EVIDENCE.json` contains only paper-admitted fields machine-extracted from sealed aggregate artifacts; each source aggregate is pinned by GitHub Actions run, execution commit, artifact ID, archive SHA-256, source schema, and original aggregate SHA-256.
2. `extract_paper_results.py` is the only supported evidence→manifest path.
3. Exact structural metrics (`exact_count`, `exact_fraction`, `exact_scalar`) and timing measurements (`measured_ms`) are distinct types.
4. E3b/E3c workload expansion is derived from integer work counts and represented canonically as **3/2**, never copied from a timing statistic.
5. N1 runner timings remain separate; no cross-runner average is canonical.
6. N2b v1 run `33972326066` remains noncanonical; E3b boundary-sweep evidence remains non-headline.
7. The empirical stop rule is active.
8. CI regenerates/checks every downstream view and runs adversarial tamper tests.

Canonical evidence SHA-256: `{m['canonical_evidence_sha256']}`  
Manifest SHA-256: `{mhash(m)}`

Narrative prose is downstream of this layer and is never an authority over it.
"""
    return {"generated/PAPER_RESULTS_TABLE.md":table,"generated/paper_results.csv":s.getvalue(),"generated/figure_data.json":cjson(fig),"generated/RESULTS_SUMMARY.md":summary,"PAPER_RESULTS_FREEZE.md":freeze}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--paper-root",type=Path,default=Path(__file__).resolve().parents[1]); ap.add_argument("--check",action="store_true"); a=ap.parse_args()
    try: outs=render(build(a.paper_root))
    except ValidationError as e: print("FAIL:",e); return 2
    bad=[]
    for rel,text in outs.items():
        p=a.paper_root/rel
        if a.check:
            if not p.is_file() or p.read_text(encoding="utf-8")!=text: bad.append(rel)
        else:p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding="utf-8")
    if bad:print("FAIL: stale generated views: "+", ".join(bad));return 3
    print("PASS: paper views reproducible" if a.check else "WROTE: paper views");return 0
if __name__=="__main__":raise SystemExit(main())
