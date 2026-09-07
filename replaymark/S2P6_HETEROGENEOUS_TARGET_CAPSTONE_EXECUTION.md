# Gate S2-P6 — First-Complete Heterogeneous-Target Capstone Execution Charter

Status at this commit: **EXECUTION CHARTER FROZEN; LIVE OUTCOME UNKNOWN.**

This execution is the first permitted live exposure of the P6 heterogeneous target frozen at protocol authority `4a458f2f5cc9163c6046cc6d20b3626cecfc4a81`.

## Execution authority

- exact parent: P6 protocol `4a458f2f5cc9163c6046cc6d20b3626cecfc4a81`
- one immutable heterogeneous target process for the full six-trial run
- original frozen `device.py` remains unchanged and is not started
- live runner receives the frozen policy schedule but no target-class schedule or independent oracle
- target receives no policy, certificate, oracle, ReplayMark verdict, or mutable control-plane input
- no target probe is permitted before the first complete capstone

## Causal ordering

For each trial, all 192 A-side observation snapshots close and freeze before any historical ACT2 candidate is dispatched. The A-side quiescence barrier completes before B-side certification/dispatch. The target process is stopped after the live report is complete and before the independent literal oracle evaluates the result.

## Historical action

Every B-side candidate uses the frozen ACT2 decision content bound by the P6 historical template. The current pre-send monotonic timestamp is runtime realization provenance; it is not a replacement decision.

## Scientific authority

If the live runner produces the complete six-trial, 1,152-row report, that **first complete report is authoritative whether PASS or FAIL**. Later exact reruns are replication only and cannot replace it. An implementation/preflight failure before a complete live report is development history, not a scientific target result.

The independent verifier determines semantic safety from the frozen literal oracle over actual raw observation/action material. Hidden target class is only a causal sanity check and is not semantic truth.

Fallback, regeneration, and automatic retry remain **ABSENT**. No latency-speedup or broker exactly-once claim is made.
