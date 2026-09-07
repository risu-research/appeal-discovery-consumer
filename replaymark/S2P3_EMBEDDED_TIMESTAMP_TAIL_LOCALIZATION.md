# Gate S2-P3 — Embedded-Timestamp Causal Tail Localization Protocol

Status: **FROZEN BEFORE ANY P3 SOURCE EXECUTION.**

P3 does not retry Q2, relax the 80-ms threshold, insert a smaller wave, compute a new
`W*`, derive `D*`, or inspect the shifted target. The Q2 scientific failure remains
immutable.

## Why P3 exists

Q2 established that the predeclared source loads `{16,8,4}` do not satisfy the
frozen 80-ms p99 qualification, and that smaller wave size does not monotonically
remove the completion tail. Before adding more load candidates or deeper tracing,
P3 asks a simpler causal-boundary question:

> Does the source completion tail occur before the frozen device publishes its state,
> or after that publication on the observation-return path?

The frozen device already emits `ts_mono_ns` inside every state payload. P3 uses that
existing timestamp rather than changing the device, broker, QoS, or semantic runtime.

## Immutable authorities

- Q2 failure seal: `0b24288d85958fd7b4f3dcd418fd7dda85bd4efc`
- Q2 execution: `79577a00e78aa61a5d92c6d608a9f64601bdb1d9`
- Q2 run: `34158327040`
- Q2 artifact: `10031766440`
- Q2 artifact SHA-256: `159abbf5e99ecd8ec4e051824cfb63fd59918ac539009821447d89e616377cdd`
- P2 protocol: `22ec2da2e62c1fa7e9d1a5e02ff676188d90ab5e`
- frozen device blob: `27240e65cb8e1a7d788cc5dea8484cbad8ec6653`
- frozen experiment harness blob: `a5c7483b198bc03f251d31b75750c27fad1f2d29`

## Source-only design

P3 repeats the exact Q2 candidate waves and cyclic order only for characterization:

```text
round 0: 16, 8, 4
round 1:  8, 4,16
round 2:  4,16, 8
```

Every cell contains 192 source ACT1 tasks. All nine cells must run: 1,728 rows total.
State delay remains 0 ms, verify boundary 100 ms, wave period 300 ms, task timeout
1000 ms. There is no ACT2 candidate, ReplayMark execution decision, fallback,
regeneration, or shifted-target path.

## Existing timestamp as the first discriminator

For every task P3 records:

```text
offer
task start
ACT1 publish call
ACT1 PUBACK observed by runner
device state publish     <- frozen payload ts_mono_ns
runner state receive
```

The primary additive decomposition is:

```text
end-to-end completion
=
publish-call overhead
+
forward + device
+
post-device observation
```

`PUBACK` latency is reported separately because it is not an additive serial component
of the state-observation path.

The runner receive timestamp remains the semantic observation boundary. Device-side
time is used only to localize where elapsed time accumulated.

## Clock-domain qualification

Cross-process subtraction is forbidden unless the run establishes the clock boundary.

The artifact must capture `/proc/self/ns/time` and `/proc/self/timens_offsets` for the
runner and the frozen device. Both monotonic offsets must be zero. Every row must also
satisfy:

```text
device_state_publish_mono_ns <= state_on_recv_mono_ns
```

If any clock check fails, the result is `CLOCK_DOMAIN_INVALID` and P3 makes no
cross-process segment attribution.

## Frozen reporting

P3 reports p50/p95/p99/max for every segment per cell, per wave pooled, and globally.
For each cell it also defines the tail as rows at or above the empirical p95
end-to-end completion boundary and reports the device-side and post-device fractions
of total completion.

A diagnostic classification is frozen before execution:

- `POST_DEVICE_DOMINANT` iff clock qualification passes, pooled post-device p99 is at
  least 4x pooled forward+device p99, and the pooled top-tail median post-device
  fraction is at least 0.75.
- `PRE_DEVICE_DOMINANT` is the symmetric rule.
- `MIXED_OR_UNLOCALIZED` otherwise.
- `CLOCK_DOMAIN_INVALID` if clock qualification fails.

This classification is diagnostic, not a promotion threshold.

## Anti-repair lock

P3 cannot:

- rehabilitate Q2;
- select a new `W*`;
- derive `D*`;
- relax the 80-ms Q2 threshold;
- add wave 2, wave 1, or any other candidate;
- change MQTT QoS, broker version, or frozen device code;
- inspect a shifted target;
- branch on target outcomes.

The first complete P3 execution is authoritative. Later exact repeats are replication
only.

## Strategic use

If P3 localizes the tail post-device, the next defensible move is not another smaller
load. It is a new prospective boundary-aligned calibration design that treats
source-device feasibility and observer-arrival variability as distinct quantities.
If P3 localizes pre-device, the next work stays on source offered-load/forward-path
feasibility. If it remains mixed, one additional minimal discriminator may be frozen.

P3 itself changes no ReplayMark theorem or runtime semantics.
