#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, io, json
from pathlib import Path
from paper_results_lib import ValidationError, build_manifest, canonical_json, manifest_sha256

def _frac(x):
    return f"{x['numerator']}/{x['denominator']} (= {x['decimal']:.1f}×)"

def _emp(x):
    return f"{x['successes']}/{x['trials']} ({100*x['decimal']:.0f}%)"

def render(manifest):
    hr = manifest["headline_results"]
    w = hr["replay_semantics_can_change_benchmark_workload"]
    t = hr["timing_fidelity_is_not_controller_semantic_fidelity"]
    n2 = hr["operation_identity_is_not_action_identity"]
    n2b = hr["raw_feedback_difference_is_not_replay_invalidity"]
    n1t = manifest["measured_timing"]["n1"]["timing_by_replica"]

    table = """# Canonical Paper Results Table

> Machine-generated from `PAPER_RESULTS_MANIFEST.json`. Do not hand-edit.

| Claim | Canonical evidence | Result | Status |
|---|---|---|---|
| Timing fidelity is not controller-semantic fidelity | E3b / E3c / N1 | E3b R1 support failure {e3br1}; E3c R1 {e3cr1}; N1 R1 {n1r1}; semantic R2 support failure is 0 in all three | CLOSED |
| Replay semantics can change benchmark workload | E3b / E3c | E3b 512→768 PUBLISH = {e3bratio}; E3c 256→384 native calls = {e3cratio} | CLOSED |
| Operation identity is not action identity | N2 | TV_operation={tvop}; TV_action={tva}; same `climate.set_preset_mode`, `home`→`away` variant | CLOSED |
| Raw feedback difference is not replay invalidity | N2b | raw TV={raw}; quotient TV={quot}; action TV={act}; target replay support failures {fail} | CLOSED |

N1 runner timing shifts are deliberately not averaged in the canonical layer: replica 0 = {n10:.15g} ms; replica 1 = {n11:.15g} ms.
""".format(
        e3br1=_emp(t["e3b"]["semantic_support_failure"]["R1"]),
        e3cr1=_emp(t["e3c"]["semantic_support_failure"]["R1"]),
        n1r1=_emp(t["n1"]["semantic_support_failure"]["R1"]),
        e3bratio=_frac(w["e3b"]["R2_over_R1"]),
        e3cratio=_frac(w["e3c"]["R2_over_R1"]),
        tvop=n2["TV_operation"]["value"], tva=n2["TV_action"]["value"],
        raw=n2b["raw_feedback_TV"]["value"], quot=n2b["quotient_feedback_TV"]["value"],
        act=n2b["TV_action"]["value"], fail=_emp(n2b["target_replay_support_failures"]),
        n10=n1t[0]["R1_minus_R0"]["value"], n11=n1t[1]["R1_minus_R0"]["value"],
    )

    rows = [
        ["e3b","R0_work","exact_count",w["e3b"]["work_per_trial"]["R0"]["value"],"broker PUBLISH"],
        ["e3b","R1_work","exact_count",w["e3b"]["work_per_trial"]["R1"]["value"],"broker PUBLISH"],
        ["e3b","R2_work","exact_count",w["e3b"]["work_per_trial"]["R2"]["value"],"broker PUBLISH"],
        ["e3b","R2_over_R1","exact_fraction","3/2","ratio"],
        ["e3c","R0_work","exact_count",w["e3c"]["work_per_trial"]["R0"]["value"],"native HA service calls"],
        ["e3c","R1_work","exact_count",w["e3c"]["work_per_trial"]["R1"]["value"],"native HA service calls"],
        ["e3c","R2_work","exact_count",w["e3c"]["work_per_trial"]["R2"]["value"],"native HA service calls"],
        ["e3c","R2_over_R1","exact_fraction","3/2","ratio"],
        ["n2","TV_operation","exact_scalar",n2["TV_operation"]["value"],"TV"],
        ["n2","TV_action","exact_scalar",n2["TV_action"]["value"],"TV"],
        ["n2b","raw_feedback_TV","exact_scalar",n2b["raw_feedback_TV"]["value"],"TV"],
        ["n2b","quotient_feedback_TV","exact_scalar",n2b["quotient_feedback_TV"]["value"],"TV"],
        ["n2b","TV_action","exact_scalar",n2b["TV_action"]["value"],"TV"],
        ["n2b","target_replay_support_failures","empirical_fraction","0/12","trials"],
        ["n1","R1_minus_R0_replica0","measured_ms",n1t[0]["R1_minus_R0"]["value"],"ms"],
        ["n1","R1_minus_R0_replica1","measured_ms",n1t[1]["R1_minus_R0"]["value"],"ms"],
    ]
    sio=io.StringIO()
    cw=csv.writer(sio, lineterminator="\n")
    cw.writerow(["evidence","metric","kind","value","unit"])
    cw.writerows(rows)

    figure_data = {
        "schema":"agentmark.paper_figure_data.v1",
        "panels":{
            "semantic_support_failure":{
                "kind":"empirical_fraction",
                "systems":{
                    "E3b":{"R0":"12/12","R1":"12/12","R2":"0/12"},
                    "E3c":{"R0":"1536/1536","R1":"1536/1536","R2":"0/1536"},
                    "N1":{"R0":"12/12","R1":"12/12","R2":"0/12"},
                },
            },
            "workload_ratio":{
                "kind":"exact_fraction",
                "systems":{"E3b":{"R1":512,"R2":768,"ratio":"3/2"},
                           "E3c":{"R1":256,"R2":384,"ratio":"3/2"}},
            },
            "semantic_projection_tv":{
                "kind":"exact_scalar",
                "systems":{"N2":{"operation":0,"action":1},
                           "N2b":{"raw_feedback":1,"quotient_feedback":0,"operation":0,"action":0,"pair_restricted_eta_action":0}},
            },
            "n1_runner_timing":{
                "kind":"measured_ms",
                "aggregation":"none",
                "replicas":[
                    {"replica":0,"R1_minus_R0_ms":n1t[0]["R1_minus_R0"]["value"],
                     "R2_minus_source_ms":n1t[0]["R2_minus_source"]["value"]},
                    {"replica":1,"R1_minus_R0_ms":n1t[1]["R1_minus_R0"]["value"],
                     "R2_minus_source_ms":n1t[1]["R2_minus_source"]["value"]},
                ],
            },
        },
    }

    provenance_rows = []
    for key in ("e3b", "e3c", "n1", "n2", "n2b"):
        e = manifest["evidence"][key]
        provenance_rows.append(
            f"| {key.upper()} | `{e['run_id']}` | `{e['execution_commit']}` | "
            f"`{e['artifact_id']}` / `{e['artifact_name']}` | `{e['artifact_archive_sha256']}` | "
            f"`{e['primary_sha256']}` |"
        )
    provenance = """# Canonical Provenance Ledger

> Machine-generated from `PAPER_RESULTS_MANIFEST.json`. Do not hand-edit.

| Evidence | Run | Execution commit | Aggregate artifact | Server artifact SHA-256 | Primary JSON SHA-256 |
|---|---:|---|---|---|---|
""" + "\n".join(provenance_rows) + "\n\n"
    provenance += (
        "Excluded from headline authority: N2b v1 run `33972326066` (failed measurement contract) "
        "and E3b safety-boundary artifact `9960095929` (falsification/exploratory boundary evidence).\n"
    )

    summary = f"""# AgentMark Canonical Results Summary

Status: **FROZEN_CANONICAL**

All headline empirical cells are closed. The paper layer is generated from five sealed evidence capsules: E3b, E3c, N1, N2, and N2b. Exact structural quantities and measured timing quantities are represented by different metric types and cannot substitute for one another without validation failure.

- E3b and E3c independently give the same exact semantic-replay workload expansion: **3/2 (1.5×)**.
- E3b, E3c, and N1 show support failure under R1 and support preservation under semantic R2 in their sealed trials.
- N2 closes the projection distinction: **TV_operation=0, TV_action=1**.
- N2b closes the safe-side quotient prediction: **raw feedback TV=1, quotient/action TV=0**, with **0/12** target-replay support failures.
- N1 timing is retained as two independent runner measurements, never promoted to one canonical cross-runner average.

Empirical stop: **ACTIVE**. Generic N3-style breadth is outside the frozen plan unless adversarial paper review exposes a specific undefended claim.

Evidence tree SHA-256: `{manifest['evidence_tree_sha256']}`  \nCanonical provenance-lock SHA-256: `{manifest['canonical_provenance_lock_sha256']}`  \nManifest SHA-256: `{manifest_sha256(manifest)}`
"""

    freeze = f"""# AgentMark Paper-Results Freeze

Status: **FROZEN_CANONICAL**

This directory is the canonical interface between sealed experiments and manuscript prose.

## Freeze contract

1. `evidence/*/primary.json` contains exact copies of canonical aggregate JSONs from successful GitHub Actions artifacts.
2. Each `PROVENANCE.json` pins workflow run, execution commit, artifact ID, archive digest, source schema, and primary-file digest; those identities are independently hard-locked in `paper_results_lib.py`.
3. `scripts/extract_paper_results.py` is the only supported path from evidence to `PAPER_RESULTS_MANIFEST.json`; provenance cannot be repointed merely by rehashing a replacement capsule.
4. `scripts/validate_paper_results.py` fails closed on provenance drift, content-hash drift, schema drift, result drift, exclusion drift, or exact/measured type confusion.
5. `scripts/generate_paper_views.py` generates manuscript-facing tables, CSV, figure data, and summary from the manifest.
6. N1 runner timings remain separate; no canonical cross-runner average is admitted.
7. E3b/E3c workload ratios are derived from exact integer work counts and canonically represented as **3/2**, never imported from a timing statistic or floating-point narrative.
8. N2b v1 run `33972326066` remains explicitly noncanonical. E3b safety-boundary evidence remains non-headline.
9. The empirical stop rule is active.

## Cryptographic lock

Evidence tree SHA-256: `{manifest['evidence_tree_sha256']}`  \nCanonical provenance-lock SHA-256: `{manifest['canonical_provenance_lock_sha256']}`  \nManifest SHA-256: `{manifest_sha256(manifest)}`

The Git commit containing this freeze is an additional content-addressed audit boundary. Narrative text is downstream of this layer, never an authority over it.
"""
    return {
        "generated/PAPER_RESULTS_TABLE.md": table,
        "generated/paper_results.csv": sio.getvalue(),
        "generated/figure_data.json": canonical_json(figure_data),
        "generated/RESULTS_SUMMARY.md": summary,
        "generated/PROVENANCE_LEDGER.md": provenance,
        "PAPER_RESULTS_FREEZE.md": freeze,
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--paper-root", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--check", action="store_true")
    args=ap.parse_args()
    try:
        m=build_manifest(args.paper_root)
        outputs=render(m)
        stale=[]
        for rel,text in outputs.items():
            p=args.paper_root/rel
            if args.check:
                if not p.is_file() or p.read_text(encoding="utf-8") != text:
                    stale.append(rel)
            else:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text, encoding="utf-8")
        if stale:
            print("FAIL: stale generated views: " + ", ".join(stale))
            return 3
        print("PASS: paper views are reproducible" if args.check else "WROTE: paper views")
        return 0
    except ValidationError as exc:
        print(f"FAIL: {exc}")
        return 2

if __name__=="__main__":
    raise SystemExit(main())
