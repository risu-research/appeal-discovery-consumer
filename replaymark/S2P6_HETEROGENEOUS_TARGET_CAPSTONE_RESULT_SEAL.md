# Gate S2-P6 — First-Complete Heterogeneous-Target Capstone Result Seal

Status: **FROZEN FIRST-COMPLETE PASS.**

This seal records the first complete live exposure of the prospectively frozen P6 heterogeneous target. The result is authoritative and is not replaceable by a later favorable rerun.

## Authority

- P6 protocol: `4a458f2f5cc9163c6046cc6d20b3626cecfc4a81`
- execution authority: `e5e992b0a31c952017ee4209be2c0585a6cab500`
- execution tree: `a88776698d85015e0897d1d95dc87edb87aee6e3`
- workflow run: `34168034341`
- workflow job: `101882862715`
- artifact: `10034798750`
- artifact SHA-256: `1319c41908d511ca9e8976973801350aab593199038b82752d8e4e7c78d0ecdb`
- artifact size: 624,939 bytes

The earlier commit `2536b5e3d28c32a48db58478f729d5d211e66250` / run `34167976472` failed at preflight because the verifier invocation lacked the repository import root. No broker target or live capstone executed in that run; it remains development history and is not a scientific target result.

## First-complete result

| Policy | Assigned | Oracle-safe | Oracle-unsafe | Executed |
|---|---:|---:|---:|---:|
| Always-Admit | 384 | 186 | 198 | 384 |
| Always-Block | 384 | 191 | 193 | 0 |
| ReplayMark | 384 | 188 | 196 | **188** |

ReplayMark's executed task set was **exactly equal** to its independently computed oracle-safe task set:

```text
safe assigned       = 188
safe executed       = 188
unsafe assigned     = 196
unsafe executed     = 0
unnecessary blocks  = 0
```

Therefore, in this first complete run:

```text
ReplayMark safe retention rate      = 100%
ReplayMark unsafe execution rate    = 0%
```

Always-Admit retained all 186 safe decisions assigned to it but also executed all 198 unsafe historical decisions. Always-Block executed no unsafe history but discarded all 191 safe decisions assigned to it.

## Hidden target class sanity check

The hidden class schedule was not used as semantic truth. Independent evaluation produced:

```text
REFERENCE: 565 safe, 11 unsafe
SHIFTED:     0 safe, 576 unsafe
```

The 11 unsafe REFERENCE tasks are important: they demonstrate why target class was correctly treated only as a causal sanity check. ReplayMark did not receive that label and followed actual runtime evidence instead.

## Falsification checks already passed in the first verifier

- 1,152/1,152 rows present;
- inherited policy schedule exact;
- 32 REFERENCE + 32 SHIFTED tasks per policy per trial;
- all six trials contain oracle-safe and oracle-unsafe decisions;
- production certificate vs independent literal oracle mismatches: 0;
- target-class leakage rows: 0;
- application effect mismatches: 0;
- exact historical ACT2 action calls match executed rows;
- ReplayMark gate consumed exactly 384 admissions;
- original frozen device not started;
- one immutable heterogeneous target process used;
- live runner was target-class blind and oracle-blind;
- fallback, regeneration, and automatic retry absent.

## Claims intentionally not made

This result does not claim hidden target class equals semantic truth task-by-task, cross-process exactly-once, broker-delivery exactly-once, fallback quality, regeneration quality, or a latency speedup.

The next gate is **S2-F — Heterogeneous-Target Falsification Audit**. It must attack this result rather than add a new favorable execution.
