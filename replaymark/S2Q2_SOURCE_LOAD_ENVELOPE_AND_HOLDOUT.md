# Gate S2-Q2 — Source Load-Envelope Screening, Fresh Holdout, and D* Seal

Status target: **execute the P2 source-only load-envelope protocol exactly once,
select the largest independently feasible predeclared load from all screening
evidence, confirm that load on fresh holdout evidence, and derive D* only after
the holdout passes. No shifted target may exist anywhere in this gate.**

Frozen parent:

- P2 authority: `22ec2da2e62c1fa7e9d1a5e02ff676188d90ab5e`
- P2 protocol blob: `c7e3103adfe2a3803e506e7c20674ad32edb058f`
- Q1 failed authority remains `2a7e994810ae9c88d626d50fea1b06a7eb3550b5`
- wave 32 remains permanently ineligible for this S2 capstone.
- S0 runtime micro-optimization remains frozen.

## Scientific boundary

Q2 is source-only. It cannot:

- construct or publish ACT2;
- execute a shifted target;
- import ReplayMark semantic or oracle modules in the live runner;
- choose a load from target outcomes;
- accept a human-supplied W* on the holdout path;
- compute D* from screening rows;
- fall back to a smaller load after holdout failure;
- alter the P2 candidate set, qualification thresholds, ordering design, or D*
  formula.

The first complete Q2 report is authoritative. A complete scientific failure is
preserved. Only an infrastructure failure before a complete report may be retried
on the exact same commit and parameters.

## Phase A — all-candidate source screening

The exact eligible set remains:

```text
16, 8, 4
```

All candidates run. There is no early stop. Three fresh broker/device rounds use
the frozen cyclic Latin-square order:

```text
round 0: 16 -> 8 -> 4
round 1:  8 -> 4 -> 16
round 2:  4 ->16 -> 8
```

Each candidate therefore has exactly three source-only replicates and 576 rows.
Each screening round starts from a fresh Mosquitto/device restart. Candidate cells
inside a round use fresh task namespaces and a fixed quiescence drain between
cells. The runner records the intended offer timestamp as well as actual task
start, so scheduler start lateness is observable rather than silently folded into
the workload definition. Start lateness is descriptive only and introduces no new
post-P2 threshold.

For each candidate, the independent verifier recomputes from raw integer
timestamps:

- exact 576-row presence;
- exact task/wave schedule geometry;
- task completion and 100-ms visibility;
- each replicate p99;
- pooled median and p99;
- runner preview consistency;
- namespace uniqueness.

The P2 qualification remains unchanged: every task must complete and be visible,
each replicate p99 must be at most 80 ms, and pooled p99 must be at most 80 ms.

Only after all nine cells exist does the independent verifier compute:

```text
W_star_screen =
    maximum numeric wave in {16,8,4}
    whose complete frozen qualification passes
```

If no candidate passes, Q2 fails and no holdout is permitted.

## Machine-bound screening selection seal

The live runner never selects W*. After all three screening rounds, the independent
verifier writes a screening-selection seal containing:

- exact Q2 execution commit;
- exact P2 authority and protocol hash;
- all three raw screening result SHA-256 digests;
- candidate statistics and qualification bits;
- exact `W_star_screen`;
- explicit source-only / no-target flags.

The holdout runner does **not** expose a `--wave-size` argument. It must consume
this exact selection seal and obtains W* only from the sealed verifier output.
Every holdout result records the selection-seal SHA-256, so a foreign or edited
selection is detectable.

## Phase B — fresh source-only holdout

Only a PASS screening seal admits holdout.

The selected W* receives exactly three fresh holdout replicates, each under a
fresh Mosquitto/device restart and a fresh task namespace:

```text
3 replicates x 192 tasks = 576 holdout rows
```

The screening rows are not reused. Holdout qualification repeats the frozen P2
requirements:

- exact 576-row presence;
- all rows structurally valid;
- every task complete by timeout;
- every task visible by 100 ms;
- each replicate p99 <= 80 ms;
- pooled p99 <= 80 ms;
- all holdout namespaces fresh and disjoint from screening;
- all holdout reports bound to the exact screening-selection seal.

If any holdout requirement fails, the gate fails. Q2 does not try another load.

## Phase C — D* derivation

D* is not even computed unless the full holdout qualification passes.

Only the 576 fresh holdout completion offsets are then used:

```text
D_star_ms =
    floor((100.0 - pooled_median_holdout_completion_ms) + 0.5)
```

and the frozen admissibility rule remains:

```text
1 <= D_star_ms < 100
```

The final verifier explicitly reports:

```text
screening_rows_used_in_D_star_estimate = 0
holdout_rows_used_in_D_star_estimate   = 576
```

A scientific holdout failure therefore has `D_star_ms = null`; a favorable delay
is never derived from failed or selected-on screening evidence.

## Evidence preservation

The workflow uploads the Q2 artifact before enforcing the scientific verdict.
The artifact includes raw screening rounds, the screening verification and
selection seal, any admitted holdout replicates, final independent verification,
gate status, exact source/protocol files, commit metadata, and SHA-256 manifests.

No target outcome is available in Q2. A successful Q2 closes only the source load
and D* selection problem. The inherited S2 target policy schedule, evidence-before-
dispatch barrier, independent post-execution oracle, and exact-set ReplayMark
promotion rule remain downstream and unchanged.
