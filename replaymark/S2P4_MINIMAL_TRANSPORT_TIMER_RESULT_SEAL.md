# Gate S2-P4 — Minimal Transport-Timer Result Seal

Status: **FROZEN COMPLETE SCIENTIFIC CHARACTERIZATION.**

This seal preserves the first complete P4 execution exactly as observed. It does not repair Q1/Q2, relabel the preregistered P4 classifier, or authorize target execution.

## Authority

- P4 protocol: `d482d03816e603544c4cd131ff3add0a078cd788`
- P4 execution: `cad74a2405ad21805c550812114639217b2d7c9d`
- execution tree: `347eb2dec0ea1c8751a61b933420b0991c01e5a7`
- workflow run: `34165476263`
- workflow job: `101875541960`
- artifact: `10034020334`
- artifact SHA-256: `e0f363b847e380b016e2481384d8b8426bdb83a79841a1f909c2ea2df09d4085`

## Preregistered result

The exact frozen aggregate classifier returned:

```text
AMBIGUOUS
```

That classification is immutable.

All `1,728` self-echo rows completed with the device service absent, target absent, ACT2 absent, and socket options unmodified.

Aggregate metrics:

| Metric | p50 ms | p95 ms | p99 ms | max ms | fraction 35–45 ms |
|---|---:|---:|---:|---:|---:|
| self-echo receive | 1.858344 | 4.976739 | 42.072170 | 44.782376 | 4.2245% |
| PUBACK | 2.111777 | 41.249002 | 42.242965 | 45.073332 | 5.2662% |

The existing socket `TCP_NODELAY` value was `0` in all three rounds.

## Descriptive audit — not a classifier rewrite

The frozen per-cell `TcpExtDelayedACKs` deltas were:

```text
0, 1, 5, 1, 6, 0, 6, 1, 0
```

After the preregistered classification was already fixed, a descriptive cell-level audit found correlation of approximately `0.9230` between that counter delta and the number of PUBACK observations in `[35,45] ms`, and approximately `0.8813` for self-echo observations in the same window. This is triangulation, not causal identification.

The per-wave pattern is also descriptive only: wave 16 was mostly clean, wave 8 showed a sparse ~42-ms tail, and wave 4 showed a much stronger ~42-ms cluster. The aggregate preregistered result remains **AMBIGUOUS** regardless of these subgroups.

## What P4 establishes and does not establish

P4 establishes that **device logic is not necessary for a ~40-ms-scale timing tail to appear**: the device was removed entirely and the single-client broker self-echo still exhibited ~42-ms aggregate p99 latency.

P4 does **not** establish that delayed ACK, Nagle, Linux, Mosquitto, Paho, or any single transport mechanism is the cause. No socket option or kernel parameter was changed.

Most importantly, P4 exposes a category mistake in the failed source qualification design. The old `p99 <= 80 ms` condition was an engineering slack proxy introduced to keep source completion comfortably away from the inherited `100 ms` semantic evidence boundary. It is **not itself a ReplayMark semantic requirement**. The semantic requirement is that the evidence required by the frozen observation contract be complete by the actual boundary.

Therefore the next scientifically defensible move is not more wave hunting and not a transport-debugging detour. It is a new prospective protocol generation that qualifies the source at the **actual frozen semantic boundary** while preserving p50/p95/p99 only as descriptive system measurements.

## Anti-repair

- Q1 and Q2 failures remain authoritative.
- P4 remains `AMBIGUOUS`; it cannot be relabeled from subgroup analysis.
- P4 cannot produce W* or D*.
- P4 cannot authorize target execution.
- No 80-ms threshold is retroactively changed inside Q2.
- Any continuation must be a new protocol generation.

Next gate: `S2P5_BOUNDARY_COMPLETE_SOURCE_QUALIFICATION_PROTOCOL`.
