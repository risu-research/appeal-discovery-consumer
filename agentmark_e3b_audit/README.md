# E3b 80 ms Near-Threshold Replicated Causal Audit

This audit is deliberately isolated from the promoted E3b code and results. It does **not** alter the decisive ladder, safety certificate, or safety-boundary artifacts.

## Frozen question

The prior boundary sweep observed a one-run discrepancy at 80 ms: the controller-neutral prefix probe missed the 100 ms decision deadline more often than the live R1/R2 conditions. This audit asks whether that gap is:

1. transient runner/MQTT scheduling variance;
2. a measurement/control-flow artifact; or
3. a real workload -> substrate feedback effect within this harness.

The audit does not presuppose endogeneity and does not open E5 unless the effect survives the falsification gates below.

## Four conditions

- `P_prefix`: ACT1 only, legacy controller-neutral prefix measurement.
- `H_shadow`: same wait/classification control path as R1 but ACT2 is suppressed. MQTT workload is therefore the same as `P_prefix`.
- `R1_timing`: live timing-feedback replay with ACT2 after current completion.
- `R2_semantic`: semantic replay, inserting VERIFY when the 100 ms decision deadline is missed.

`P_prefix` vs `H_shadow` diagnoses runner/control-flow measurement effects. `H_shadow` vs R1/R2 is the workload contrast.

## Replication and randomization

- four independent GitHub-hosted Ubuntu runners;
- Eclipse Mosquitto `2.1.2-alpine` and Paho MQTT `2.1.0`;
- fixed 100 ms decision deadline, never recalibrated from target outcomes;
- target delays fixed in advance at 80 ms and 95 ms;
- 8 repeated blocks per delay and runner;
- 128 tasks per condition, wave size 32, 300 ms between waves;
- Williams-square condition order to balance position and first-order carryover;
- exact broker-native PUBLISH conservation required in every condition.

The source world is rechecked at 0 ms only as a validity condition; it may not move the frozen 100 ms boundary.

## No-overlap causal control

Each runner additionally executes a fixed 80 ms control with wave size 1, 20 tasks, and 300 ms between tasks. At this spacing, a task's first feedback and its downstream R1/R2 work should complete before the next task is offered. A peer-workload endogeneity explanation therefore predicts attenuation in this control.

## Precommitted decision rule

The practical effect threshold is 5 percentage points (`epsilon = 0.05`). The aggregate analysis uses paired block differences, a hierarchical bootstrap across independent runners and within-runner blocks, and a two-sided sign test.

- If `P_prefix - H_shadow` is not stable within 5 pp, classify the discrepancy as a measurement/control-flow confound.
- If `H_shadow` vs R1/R2 has a >=5 pp concurrent effect, its 95% hierarchical bootstrap CI excludes zero, at least 3/4 runners agree in direction, and the corresponding no-overlap effect is <5 pp, classify **concurrent workload endogeneity as supported in this harness**.
- If the live-vs-shadow concurrent effect does not survive, classify the old discrepancy as **not replicated**.
- Otherwise return **unresolved**, not a positive claim.

This rule is frozen before observing the audit result.
