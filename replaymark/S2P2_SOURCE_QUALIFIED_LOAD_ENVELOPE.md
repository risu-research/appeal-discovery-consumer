# Gate S2-P2 — Source-Qualified Load-Envelope Protocol

Status: **FROZEN AFTER THE FIRST COMPLETE S2-Q SOURCE-ONLY FAILURE AND BEFORE ANY SHIFTED-TARGET OUTCOME.**

This is a new protocol generation, not a repair or replacement of the failed S2-Q result.

## Immutable failure anchor

The first complete S2-Q run remains authoritative:

- execution commit: `2a7e994810ae9c88d626d50fea1b06a7eb3550b5`
- workflow run: `34156280604`
- artifact: `10031102728`
- artifact SHA-256: `1e70174e401bf3147b0ef66586b978d500f409e0d0534b15a7cfea392eba1975`
- raw source-result SHA-256: `393231030149423cf2137bf4f998f4a6809b777241741664dc08972adc1a225e`
- wave size: `32`
- source rows: `576/576`
- pooled median completion: `12.5464795 ms`
- pooled p99 completion: `128.36104425 ms`
- visible by 100 ms: `560/576`
- scientific verdict: **FAIL**
- shifted target executed: **NO**
- ACT2 candidate constructed: **NO**

Wave size 32 is permanently ineligible for this S2 capstone. A later favorable replication cannot rehabilitate it.

## Why P2 exists

S2-P v1 fixed wave size 32 before data. The first source-only calibration showed that this offered burst load does not satisfy the preregistered clean-source envelope on the authoritative run. The correct response is not to retry until a favorable result appears and not to inspect the target. P2 defines, prospectively, a target-blind load-selection rule using only lower source loads.

The design deliberately separates **load selection** from **D* estimation**. Screening data may select the load but may not estimate D*. A fresh holdout source sample must both confirm the selected load and provide the only data used to derive D*.

## Screening envelope

Wave 32 is excluded. The only eligible candidates are the fixed geometric backoff:

```text
16, 8, 4
```

No intermediate or smaller candidate may be inserted after seeing results.

Every candidate is run in every screening round, regardless of earlier results. There is no early stop. The three rounds use the cyclic Latin-square order:

```text
round 0: 16, 8, 4
round 1:  8, 4,16
round 2:  4,16, 8
```

The canonical 9-cell schedule SHA-256 is:

`7850522b51e6f62130685835fb487bfe94cca9e122a79e11f64d5232bbf648d7`

Each candidate therefore receives three source-only replicates of 192 ACT1 tasks, 576 rows total. All source parameters remain:

- state delay 0 ms;
- verify boundary 100 ms;
- wave period 300 ms;
- task timeout 1000 ms;
- no ACT2 candidate;
- no ReplayMark execution decision;
- no shifted target.

A candidate is feasible only if **every** frozen condition passes:

- all 576 rows present;
- all tasks complete by timeout;
- every task is visible by the 100-ms verify boundary;
- p99 <= 80 ms in each of the three replicates;
- pooled p99 <= 80 ms;
- no task exclusion.

The screening selection is deterministic:

```text
W*_screen =
    maximum numeric eligible wave size
    whose complete qualification passes.
```

If no candidate passes, the gate fails before any target execution.

## Fresh holdout confirmation

Screening does not authorize S2-E.

If screening selects `W*_screen`, a fresh source-only holdout runs exactly three new 192-task replicates at that one wave size. The holdout uses fresh task namespaces and fresh broker/device lifecycle per replicate. It must pass the same strict source qualification.

If the holdout fails, P2/Q2 fails. The implementation may **not** fall back to the next lower screened wave in the same protocol generation.

This prevents selection-data overfitting and prevents holdout-driven adaptive backoff.

## D* from holdout only

Only after the holdout passes may D* be computed, using only the 576 fresh holdout completion offsets:

```text
D*_ms =
    floor((100.0 - pooled_median_holdout_completion_ms) + 0.5)
```

with `1 <= D* < 100`.

Screening rows may not be pooled into the D* estimate. There is no alternate formula and no target-informed retuning.

## What P2 supersedes

Everything in S2-P v1 remains frozen except the three specific assumptions that the failed source calibration invalidated:

1. fixed source wave size 32;
2. fixed target wave size 32;
3. use of one source sample both to qualify the load and estimate D*.

If P2/Q2 promotes, S2-E inherits the original six trials, 192 tasks/trial, 100-ms evidence boundary, 300-ms wave period, exact policy-assignment schedule, policy semantics, evidence-before-dispatch barrier, independent oracle, promotion criteria, and no-fallback/no-regeneration boundary. The target uses exactly the sealed `W*` and `D*`.

## Anti-fishing rules

- Q1 FAIL remains authoritative.
- Wave 32 cannot be retried for promotion.
- Candidate set, order, and qualification thresholds freeze here.
- All screening candidates must run.
- Holdout failure cannot trigger same-generation fallback.
- The target cannot run until both W* and D* are sealed.
- Target outcomes can never influence W* or D*.
- The first complete Q2 report is authoritative.
- Later exact repeats are replication only.

## Non-claims

P2 does not claim that wave 32 is universally infeasible, that W* is a global throughput optimum, that D* is optimal for producing a target mixture, or that a mixed target outcome is guaranteed. It adds no semantic theorem, fallback, regeneration, or runtime optimization.

## Next gate

`S2Q2_SOURCE_LOAD_ENVELOPE_SCREEN_HOLDOUT_AND_DSTAR_SEAL`

That gate may execute source-only evidence. Shifted-target execution remains forbidden until Q2 succeeds and seals both W* and D*.
