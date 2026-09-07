# Gate S2-P5 — Boundary-Complete Source Qualification Protocol

Status: **FROZEN AFTER P4 AND BEFORE FRESH P5 SOURCE EXECUTION OR ANY SHIFTED TARGET OUTCOME.**

P5 is a new protocol generation. It does not convert Q1 or Q2 into successes. Their preregistered failures remain immutable.

## Why this generation exists

Q1/Q2 used an engineering slack condition, `source completion p99 <= 80 ms`, in addition to the inherited `100 ms` evidence deadline. P3/P4 showed substantial ~40-ms transport/runtime timing structure, including a device-free one-client broker self-echo path. P4 did not identify a unique cause and remains preregistered `AMBIGUOUS`.

The decisive reason for P5 is therefore not a causal transport claim. It is the frozen ReplayMark observation semantics themselves: the E3b realizer requires a **complete snapshot closed at or after the verify deadline** and asks whether the matching state event arrived inside the inclusive `[command_publish, verify_deadline]` interval. It does not require a 20-ms slack margin or any percentile threshold.

P5 prospectively realigns source qualification with that actual semantic boundary.

## Measurement primitive is frozen

P5 does not introduce a new source runner. It reuses exact blob

`c263486aaf2d7dde05dd557e22a2324024c7575e`

at

`agentmark_e3b_lab/e3_mqtt/app/replaymark_s2q2_source_load_envelope.py`.

Thus the source traffic generator, MQTT client behavior, timestamps, candidate set, round order, task counts, deadline, timeout, and fresh namespaces remain the same. Only the **prospectively declared scientific qualification rule** changes.

## Screening

Candidates remain exactly `{16, 8, 4}` and all run under the same cyclic Latin-square schedule:

```text
round 0: 16, 8, 4
round 1:  8, 4,16
round 2:  4,16, 8
```

Each candidate receives 3 × 192 = 576 fresh source-only ACT1 tasks. State delay is 0 ms, verify deadline is 100 ms, task timeout is 1000 ms, wave period is 300 ms, and no ACT2 or target path exists.

A candidate qualifies iff:

1. all 576 expected rows are present;
2. every row is structurally valid source-only evidence;
3. every task completes by timeout;
4. every required source state observation is visible by the frozen 100-ms verify deadline;
5. no task is excluded.

`p50`, `p95`, `p99`, maximum completion, and scheduling lateness remain fully reported but **cannot affect promotion**.

The deterministic selection is:

```text
W*_screen = max { w in {16,8,4} : w satisfies all boundary-completeness conditions }
```

If no candidate qualifies, P5/Q3 fails before target execution.

## Fresh holdout

A selected W* is not enough. Three fresh 192-task source replicates run at exactly W*, each with fresh namespace and fresh broker/device lifecycle. The same boundary-completeness rule applies. A holdout failure ends this protocol generation; there is no same-generation fallback to a smaller wave.

## D* seal

Only after the fresh holdout passes is D* computed, and only from those 576 holdout completion offsets:

```text
D*_ms = floor((100.0 - pooled_median_holdout_completion_ms) + 0.5)
```

with `1 <= D* < 100`.

Screening rows cannot enter this estimate. No target outcome can influence W* or D*.

## What changes and what does not

P5 changes one scientific qualification predicate in a new prospective generation: the old non-semantic `p99 <= 80 ms` slack proxy no longer gates source promotion.

It does **not** change:

- the 100-ms semantic evidence deadline;
- the observation realizer or any semantic theorem;
- the source measurement runner;
- the candidate set or schedule;
- S1 execution admission;
- the later S2 target policy assignment schedule;
- no-fallback/no-regeneration boundaries;
- Q1/Q2/P3/P4 historical results.

The old 80-ms p99 values remain important descriptive systems evidence; they are simply no longer confused with the semantic evidence requirement.

## Anti-fishing

All candidates must run. Source data must be fresh. Selection and holdout are separated. Holdout cannot adaptively fall back. The target remains forbidden until W* and D* are sealed. A later result cannot retroactively alter this protocol.

Next gate: `S2Q3_BOUNDARY_COMPLETE_SOURCE_SCREEN_HOLDOUT_AND_DSTAR_SEAL`.
