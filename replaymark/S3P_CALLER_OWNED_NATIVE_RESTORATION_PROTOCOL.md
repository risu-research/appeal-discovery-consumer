# Gate S3-P — Caller-Owned Native Restoration Protocol

Status: **FROZEN BEFORE ANY S3 LIVE EXECUTION.**

S2 is closed. ReplayMark has already shown that, in one prospectively frozen heterogeneous target, it executes exactly the historical decisions independently supported by current evidence while Always-Admit executes unsafe history and Always-Block discards safe history. S3 asks the next deployment-level question without changing the ReplayMark theorem or moving fallback inside ReplayMark:

> When certified historical reuse is blocked, can the **caller** restore the task through the target's existing native path, while ReplayMark still preserves every historical decision that remains supportable?

## Why this is the next gate instead of Q4

Q1/Q2/Q3 were attempts to calibrate hosted transport timing so that a single delay boundary would naturally generate a mixed semantic workload. That experimental strategy failed prospectively and was retired by the successful P6 macro-pivot. P6 explicitly removed the W*/D* dependency and created the mixed workload through one immutable heterogeneous target whose class labels remained hidden from ReplayMark.

Therefore there is no scientific obligation called “Q4” left to satisfy. Re-running source calibration would reintroduce a mechanism that the evidence has already shown to be unnecessary. Future external transfer or replication may deserve its own gate, but it must not be a repair of the retired Q lineage.

## Exact authority

- S2-F complete result seal: `313d24099546eb672eeabb5d449a476b261087be`
- P6 protocol: `4a458f2f5cc9163c6046cc6d20b3626cecfc4a81`
- P6 first-complete execution: `e5e992b0a31c952017ee4209be2c0585a6cab500`
- P6 result seal: `60c444f32f98c9ee9ef42c8b06395ebf4ed9a902`
- S2-F corrected audit: `91f217c2db79f84b269e4a350d86bcc82d302ac5`

Frozen production/runtime blobs are inherited unchanged. In particular the certified execution gate remains the no-fallback gate: it may execute an admitted historical ACT2 or block it, but it never chooses the native path.

## Reuse the exact P6 target and assignment structure

S3 adds **no new target randomization** and does not retune target behavior.

The exact P6 heterogeneous target blob is reused:

```text
5b57bc44e91dc38e44eaafc760286fa4b616ff9c
```

The P6 target-class schedule and delays remain unchanged:

```text
REFERENCE -> command-state delay 0 ms
SHIFTED   -> command-state delay 180 ms
```

The target class is not semantic truth and is not visible to ReplayMark or the caller policy. Independent evidence remains the semantic authority.

The task-policy partition is also inherited from P6. S3 performs only this fixed bijective relabeling:

```text
P6 ALWAYS_ADMIT  -> S3 ALWAYS_REUSE
P6 ALWAYS_BLOCK  -> S3 ALWAYS_NATIVE
P6 REPLAYMARK    -> S3 REPLAYMARK_NATIVE
```

Thus no new policy seed is introduced. Every policy still receives exactly 32 REFERENCE + 32 SHIFTED tasks in every trial. Under the canonical S3 schedule-record serialization, the joint 1,152-row policy x target-class schedule SHA-256 is:

```text
27503b245e2d978f1884f717248d32336602c3f1c8e22ee379ba4442fcbcc047
```

## Three caller policies

### ALWAYS_REUSE

The caller executes the exact historical ACT2 candidate regardless of its certificate.

Expected role in the experiment:

```text
historical reuse = all 384 assigned tasks
native path      = 0
```

It must execute at least one independently unsafe historical decision or the capstone is not qualified.

### ALWAYS_NATIVE

The caller never executes the historical candidate. For every assigned task it invokes the existing target-native recovery path.

Expected role:

```text
historical reuse = 0
native path      = all 384 assigned tasks
```

This is the conservative restoration baseline. It should restore all tasks without unsafe historical execution, but it necessarily discards some history that the independent oracle says remained reusable.

### REPLAYMARK_NATIVE

ReplayMark retains its frozen no-fallback semantics. The caller first obtains the validated admission from the exact existing execution gate.

```text
ADMIT_REUSE -> exact historical ACT2 once; caller native path not entered
BLOCK_REUSE -> zero historical ACT2; control returns to caller; caller native path entered
```

Promotion requires exact set equality:

```text
historical reuse set == independent-oracle safe set
caller native set     == independent-oracle unsafe set
```

There may be no unsafe historical execution and no unnecessary native recovery.

## Caller-owned native path

The P6 target already exposes the relevant native mechanism. Its command path retains the frozen 0/180-ms heterogeneous delay, while its `query` path immediately publishes the current state. S3 uses that existing path rather than inventing a ReplayMark fallback.

For one native task the caller must perform exactly:

```text
1. historical ACT2 is not published
2. QUERY same-task role A
3. receive a fresh on=true state confirmation caused by that query
4. only after that confirmation, generate a fresh ACT2
5. publish fresh ACT2 to same-task role B
6. observe the matching B-side command effect by the native task timeout
```

The fresh ACT2 may be wire-identical to the historical ACT2. Its meaning is different because its provenance is different: it is generated **after current-state confirmation**. It must be recorded through a caller-native provenance channel and must never be submitted back to ReplayMark as historical material.

## Critical failure separation

S3 may not silently reinterpret non-semantic failures:

- realization/correlation/certificate validation failure is **not** `BLOCK_REUSE`;
- such a pipeline failure does not enter the experimental caller-native path;
- native query timeout is a `NATIVE_FAILURE`, not semantic `UNRESOLVED`;
- native fresh-ACT2 publish/effect failure is a `NATIVE_FAILURE`, not a change to ReplayMark's verdict;
- execution-gate sink failure remains an execution failure and does not trigger automatic native recovery in this protocol.

This keeps the theorem boundary intact.

## Phase discipline

For each of 6 trials x 192 tasks:

1. use the same source workload parameters as P6: wave size 32, wave period 300 ms, evidence boundary 100 ms;
2. publish ACT1 and close complete observation snapshots exactly as in P6;
3. freeze all 192 observations;
4. wait for the same A-side quiescence barrier;
5. instantiate the same exact historical ACT2 candidate and certify every task through the unchanged runtime chain;
6. only after all evidence is frozen may any policy-dependent historical or native traffic occur;
7. execute the assigned caller policy;
8. close all historical/native B-side effect windows;
9. close the live harness;
10. only then run the independent oracle and promotion verifier.

A native query or fresh ACT2 may never affect another task's already-frozen semantic evidence.

## Separate provenance channels

Because a fresh native ACT2 can have the same MQTT topic/payload/QoS/retain/properties as the historical candidate, S3 must not infer provenance from wire bytes alone.

The prospective runner must use disjoint application-level recording channels for:

- `HISTORICAL_ACT2` dispatches;
- `NATIVE_QUERY_A` dispatches;
- `NATIVE_FRESH_ACT2` dispatches.

The verifier must bind each native fresh ACT2 to the exact preceding same-task query confirmation and prove that no historical dispatch occurred on that native task. Foreign or duplicate calls fail closed.

## Promotion criteria

The first complete S3 live report is authoritative. No speed threshold participates in promotion.

Structural requirements:

- 1,152/1,152 rows complete;
- 384 tasks assigned to each caller policy;
- exactly 32 REFERENCE + 32 SHIFTED tasks per policy per trial;
- every trial contains both independent-oracle safe and unsafe history;
- hidden target class absent from live policy input;
- production ReplayMark and execution-gate blobs unchanged;
- all observations frozen before any policy-dependent traffic.

Outcome requirements:

**ALWAYS_REUSE**

```text
historical_reuse_count = 384
native_path_count      = 0
unsafe_historical_execution_count > 0
```

**ALWAYS_NATIVE**

```text
historical_reuse_count = 0
native_path_count      = 384
restored_task_count    = 384
unsafe_historical_execution_count = 0
unnecessary_native_path_count > 0
```

**REPLAYMARK_NATIVE**

```text
historical_reuse_set = independent-oracle safe set
native_path_set      = independent-oracle unsafe set
unsafe historical executions = 0
unnecessary native recoveries = 0
restored_task_count = 384
```

For every native task, the verifier must independently establish:

```text
QUERY_A publish
  < same-task query-caused current-state confirmation
  < NATIVE_FRESH_ACT2 generation/publish
  < matching B-side command effect deadline
```

## Metrics

Primary claims are semantic and work-conservation claims, not latency claims:

- unsafe historical executions;
- safe history retained;
- unnecessary native recoveries;
- native recovery count;
- total caller application publishes;
- query count;
- restored task count.

Latency and broker counters may be recorded descriptively but cannot determine promotion unless a separate future protocol preregisters such a claim.

## Anti-repair

- Q1/Q2/Q3 remain immutable failures; no Q4 is admitted;
- no W*, D*, source-load search, or target-delay search;
- exact P6 target bytes and class schedule are reused;
- exact P6 task partition is reused by fixed policy relabeling;
- no target probe before the first complete S3 execution;
- no task deletion or post-hoc policy reassignment;
- no native-path substitution inside ReplayMark;
- no fallback/regeneration change to `execution_admission.py` or `runtime_e3b_execution_gate.py`;
- first complete S3 result is not replaceable by a later favorable rerun.

This protocol is intentionally narrower than “ReplayMark has a fallback.” The stronger and cleaner claim is: **ReplayMark certifies the maximal safe historical subset; the caller remains free to recover the complementary set through its own native semantics.**
