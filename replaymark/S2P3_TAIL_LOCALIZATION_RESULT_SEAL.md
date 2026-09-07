# Gate S2-P3 — First-Complete Tail Localization Result Seal

Status: **FROZEN FIRST-COMPLETE P3 PASS.**

P3 was introduced after the complete Q2 source-envelope failure to answer one small
causal-boundary question without changing the frozen device, broker, QoS, ReplayMark
semantics, Q2 threshold, or target environment:

> Did the observed source completion tail accumulate predominantly before the frozen
> device published its state, or after device publication on the return observation
> path?

## Authority

- protocol: `496ceaead74df882e91b6c86670cc62329e6b88e`
- first execution: `8378113f4392a69c282f402fe3ef4fd0c93738f3`
- execution tree: `6170edc3ef0253730d9244107d9b25dd848a5260`
- workflow run: `34159820966`
- job: `101859086158`
- artifact: `10032248216`
- artifact ZIP SHA-256: `44e1320f22aac6e152030c582b6fa2dee3411d8d6803e78c1fb363f7d15fcf4f`
- Q2 failure seal remains: `0b24288d85958fd7b4f3dcd418fd7dda85bd4efc`

The workflow completed all three source-only rounds, independent timestamp
reconstruction, clock-domain checks, seal generation, artifact upload, cleanup, and
scientific-validity enforcement successfully.

## Scientific validity

```text
rows                         1728
unique devices               1728
clock domain valid           true
max additive error           1.42e-14 ms
shifted target executed      false
W*                            null
D*                            null
Q2 rehabilitated             false
scientific verdict           PASS
classification               MIXED_OR_UNLOCALIZED
```

The classification is not a failure. P3 preregistered it as one scientifically valid
outcome if neither side met the frozen 4x/75% dominance rule.

## Pooled decomposition

| Segment | p50 ms | p95 ms | p99 ms | max ms |
|---|---:|---:|---:|---:|
| end-to-end completion | 5.553 | 45.247 | 83.471 | 123.402 |
| forward + device | 1.020 | 41.372 | 82.566 | 83.160 |
| post-device observation | 3.056 | 41.546 | 42.083 | 81.789 |
| PUBACK latency | 1.710 | 41.674 | 42.579 | 43.913 |
| scheduler start lateness | — | — | 0.754 | 1.140 |

The pooled top-tail median decomposition was approximately 85.6% forward+device and
14.4% post-device. However, this pooled summary hides strong wave dependence.

## Wave-specific localization

### Wave 16

- 576/576 visible by 100 ms;
- end-to-end p99: 85.061 ms;
- forward+device p99: 82.829 ms;
- post-device p99: 41.994 ms;
- PUBACK p99: 42.557 ms;
- top-tail median: 94.6% forward+device, 5.4% post-device.

The observed tail is strongly forward/pre-device biased in this condition.

### Wave 8

- 570/576 visible by 100 ms;
- end-to-end p99: 93.325 ms;
- forward+device p99: 82.565 ms;
- post-device p99: 42.064 ms;
- PUBACK p99: 43.081 ms;
- top-tail median: 66.6% forward+device, 33.4% post-device.

This condition is mixed and forward-biased.

### Wave 4

- 576/576 visible by 100 ms;
- end-to-end p99: 53.186 ms;
- forward+device p99: 41.485 ms;
- post-device p99: 42.201 ms;
- PUBACK p99: 42.203 ms;
- top-tail median: 1.7% forward+device, 98.3% post-device.

The observed tail is strongly post-device biased in this condition.

## What P3 establishes

P3 rules out two overly simple explanations for the Q2 behavior:

1. the tail is not merely task-offer scheduler lateness; scheduler p99 remained below
   1 ms in the pooled run;
2. the tail is not confined to a single side of the device-state publication boundary.

It also exposes an approximately 40–42 ms scale in post-device observation and PUBACK
latencies, while some forward+device p99 values reach approximately 82–83 ms. This is
a useful structural clue, not a causal attribution.

## What P3 does not establish

P3 does **not** establish TCP/Nagle, delayed ACK, MQTT, kernel, broker, or device
causation. It does not permit Q2 threshold relaxation, a new `W*`, `D*`, target probe,
fallback, or regeneration. Q2 remains failed exactly as sealed.

## Strategic consequence

The next scientifically economical question is not "which smaller wave should we
try?" and not "what full-stack tracer should we install?". The evidence supports a
minimal source-only path discriminator that asks whether the recurring ~40-ms scale
survives when the device state mutation is removed, and whether it survives when the
device itself is removed.

A prospective three-path discriminator is therefore the leading next design:

1. command -> device state (existing path);
2. query -> device state (same device and return path, no state mutation);
3. broker/client QoS1 loopback (no device).

That experiment should be frozen before execution and should diagnose path location
without changing TCP settings or retroactively repairing Q2.
