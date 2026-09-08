# Gate S3-C1 — Paired Four-Arm Deployment Closure Protocol

Status: **FROZEN BEFORE IMPLEMENTATION OR ANY NEW QUEUE OUTCOME.**

Exact parent: `94584db84bebd73e664f19f0fe2d3b9f5998c813` (the frozen S3-C0 PASS seal).

## 1. Scientific endpoint

S3-C1 asks one deployment question:

> **On one prospectively frozen heterogeneous target workload, does ReplayMark-Native reach exactly the same persistent-queue deployment conclusion as an independent direct target controller while preserving every historical ACT2 that current evidence certifies safe?**

The endpoint is deliberately not a previously observed number. In particular, the old homogeneous `166` boundary is not inherited. S3-C0 established that the mixed workload composes as `4N + 2U`, where `U` is the number of tasks whose actual frozen evidence requires the native query branch.

## 2. Why four arms, not two

Every paired cell executes four isolated persistent-queue arms over the same logical task population and the same target-class assignment.

| Arm | Scientific role | Frozen work law |
|---|---|---:|
| `ALWAYS_REUSE` | optimistic negative control | `4N` |
| `DIRECT_NATIVE` | **deployment truth** | `4N + 2U` |
| `REPLAYMARK_NATIVE` | **system under test** | `4N + 2U` |
| `ALWAYS_NATIVE` | pessimistic rerun-all control; **not truth** | `6N` |

`DIRECT_NATIVE` is intentionally independent: it may not import ReplayMark production code, the S3 runner, certificates, or the historical ACT2 template. It acts only on its own frozen evidence. If the task is `confirmed_by_deadline`, it issues a fresh ACT2 without a query. If it is `not_visible_by_deadline`, it issues QUERY(A), waits for current-state confirmation, then generates a fresh ACT2.

`REPLAYMARK_NATIVE` uses the already-frozen ReplayMark chain unchanged. A certified safe historical ACT2 is admitted once; a blocked historical ACT2 is not executed and the caller owns QUERY/current-confirmation/fresh-ACT2 recovery.

`ALWAYS_REUSE` executes the historical ACT2 for every task without consulting evidence. `ALWAYS_NATIVE` queries every task and is a rerun-all stress/control arm. Neither baseline is allowed to masquerade as native truth.

The resulting falsification geometry is intentionally two-sided. If the theory-to-deployment bridge is real, blind reuse can be too optimistic, rerun-all can be too pessimistic, and selective ReplayMark can sit exactly on the independent native endpoint.

## 3. Queue endpoint frozen unchanged

The deployment endpoint is the already-promoted Mosquitto persistent QoS-1 count endpoint:

- Eclipse Mosquitto `2.1.2`, image `eclipse-mosquitto:2.1.2-alpine`;
- image digest `sha256:6f8d8a947c506f8a2290ec65cd4bd2bc7cb4d43fb5f6271f861cb013e2ef9797`;
- documented default `max_queued_messages = 1000`;
- documented default `max_queued_bytes = 0`;
- canonical broker config SHA-256 `886f26936b560ebfbf584744c8c4f5f2dd3eeeba946313ad1d2f7f8848bf0858`;
- no explicit `max_queued_messages`, `max_queued_bytes`, `max_inflight_messages`, or `queue_qos0_messages`;
- measured terminal roles exactly `command`, `query`, `state`, all QoS 1.

Each arm has a distinct persistent client and a prospectively derived explicit set of device filters. A broad subscription that can mix another arm into that queue is forbidden. Every paired cell starts from a fresh broker and empty session state.

For every arm independently, the frozen count endpoint is

```text
delivered = min(generated, 1000)
lost      = max(generated - 1000, 0)
```

This is a count/deployment endpoint only. S3-C1 makes no sequence-equivalence claim.

## 4. Target and observation discipline

The target remains the E3b command/query/state mechanism: REFERENCE devices publish command-caused state at 0 ms; SHIFTED devices at 180 ms; QUERY publishes current state immediately. The decision boundary is exactly 100 ms, task timeout 1000 ms, and the post-confirmation gap is 20 ms.

S3-C1 uses a new additive lab-only target realization only because the deployment ladder extends past the old P6 fixed 192-task range. The only admitted semantic generalization is support for the frozen S3-C1 `(batch, trial, task)` schedule. It must otherwise preserve the frozen P6 command/query/state semantics and immutable 0/180-ms per-device delay. It may receive no policy, certificate, ReplayMark, oracle, or adaptive input.

Logical wave size is **4**. Since each logical task has four twins, this is 16 physical twins per wave. Wave period is **500 ms**.

A hard paired observation barrier applies to every wave:

1. every arm publishes ACT1 for every logical task in the wave;
2. all four-arm 100-ms observation snapshots close immutably;
3. only after all snapshots close may any arm issue QUERY or ACT2;
4. all post-decision consequences quiesce before the next wave.

Late events cannot rewrite a snapshot. An evidence mismatch never removes a task or shortens the workload; it is preserved as a gate failure.

## 5. Prospectively frozen heterogeneous schedule

The five tested batch sizes are

```text
192, 196, 200, 204, 208
```

with six trials on each of two independent hosted replicas (`A`, `B`).

For every `(batch_size, trial)`, task IDs are SHA-256 ranked by

```text
replaymark.s3c1.paired-target-class.v1|c0=94584db84bebd73e664f19f0fe2d3b9f5998c813|batch=<N>|trial=<trial>|task=<task_id>
```

using the fixed seed

```text
replaymark.s3c1.paired-target-class.v1|c0=94584db84bebd73e664f19f0fe2d3b9f5998c813
```

The lowest `N/2` ranks are SHIFTED and the remainder REFERENCE. The same class applies to all four twins of one logical task. Arm/policy identity is absent from the class function.

The canonical 6,000-row schedule per replica has SHA-256

```text
3330c82c66cd344e01b48ac16e96e5fb4b4cb3a6b55ea880fe6285621e039af8
```

The class is a controlled causal input, **not semantic truth**. Semantic truth is recomputed from each arm's frozen raw observation snapshot.

## 6. Stress ladder derivation without recycling `166`

C0 proved the task endpoint is 4 messages on the no-query branch and 6 on the query branch. Under an exactly balanced *nominal* target mix, the mean is therefore 5 messages/task. With the externally fixed stock queue `Q=1000`,

```text
1000 / 5 = 200
```

is a **prospective stress center**, not a claimed capacity boundary.

We freeze symmetric robust offsets `[-8,-4,0,+4,+8]`, producing the five batches above. Their nominal counts are:

| N | Always-Reuse | Direct/RM nominal | Always-Native |
|---:|---:|---:|---:|
| 192 | 768 | 960 | 1152 |
| 196 | 784 | 980 | 1176 |
| 200 | 800 | 1000 | 1200 |
| 204 | 816 | 1020 | 1224 |
| 208 | 832 | 1040 | 1248 |

These numbers do **not** determine the scientific outcome. The validator uses the observed evidence-derived `U` for every cell. No old numeric boundary is imported.

Total first-complete design:

```text
2 replicas × 5 batches × 6 trials = 60 paired cells
12,000 logical task rows
48,000 arm-task executions
```

All 60 cells are mandatory; there is no early stopping.

## 7. Independent oracle path

Live dispatch cannot import or query the independent validator.

After a cell has completed all four arms, the live harness is closed and all four persistent queues are drained. Only then does a separate validator run. It imports neither ReplayMark production code nor the live runner and does not trust runner summary fields.

Its authoritative inputs are raw frozen observation snapshots, raw application publish provenance, an independent online role-event ledger, raw persistent-collector deliveries, exact broker config bytes, and exact Git/blob identities.

For each task it independently derives the evidence token using the frozen inclusive 100-ms boundary. `U` is then the number of `not_visible_by_deadline` tasks in the `DIRECT_NATIVE` arm. `REPLAYMARK_NATIVE` must have the same evidence token **task by task**. A mismatch is a scientific gate failure; it cannot be dropped, repaired, relabeled, or averaged away.

## 8. Exact promotion contract

Every structural, pairing, conservation, primary, and negative-control condition below is required.

- Complete 60-cell matrix; four complete arms per cell; no task exclusions; exact target schedule; exact broker image/version/config; all frozen ReplayMark runtime blobs unchanged.
- Direct/RM evidence equality task-by-task in every cell.
- Raw role laws exactly: Reuse=`(2N,0,2N)`; Direct=`(2N,U,2N+U)`; ReplayMark=`(2N,U,2N+U)`; Rerun-all=`(2N,N,3N)`.
- Every arm/cell obeys the exact stock-queue delivery law; persistent session is present; duplicate delivered count is zero.
- Direct and ReplayMark generated vectors, delivered/lost counts, and LOSSLESS/LOSSY classification are exactly equal in **every cell**.
- ReplayMark historical-reuse set equals the independent safe-evidence set; caller-native set equals the independent unsafe-evidence set; unsafe historical execution is zero; unnecessary native recovery is zero; every certified-safe historical ACT2 is retained.
- In **each replica**, at least one canonical cell must show `ALWAYS_REUSE=LOSSLESS` while Direct/RM are LOSSY, and at least one must show `ALWAYS_NATIVE=LOSSY` while Direct/RM are LOSSLESS.

As a secondary descriptive endpoint only, the validator may report the **robust tested lossless frontier**: the maximum tested `N` for which every canonical cell at that `N` is lossless. Direct and ReplayMark frontiers must agree. This is not a global capacity theorem.

## 9. First-complete authority and no repair

The first complete 60-cell matrix plus its independent validator certificate is the sole scientific authority for this protocol generation.

A later exact repetition is replication only. After any outcome is visible there is no same-generation:

- batch substitution,
- deadline/delay/wave retuning,
- queue retuning,
- failed-cell deletion,
- task exclusion,
- retry-based replacement of the first complete result, or
- reclassification of a scientific mismatch as success.

Implementation failure and scientific failure remain distinct and are both preserved.

## 10. Interpretation boundary

If every frozen criterion passes, the permitted claim is:

> **On the frozen paired heterogeneous Mosquitto workload, ReplayMark-Native reaches the same persistent-queue deployment classification as an independent direct target controller while retaining every historical ACT2 certified safe; blind reuse can be optimistically wrong and rerun-all can be pessimistically wrong.**

S3-C1 does not claim a universal Mosquitto capacity, the old 166 boundary, sequence equivalence, latency speedup, broker exactly-once delivery, cross-process exactly-once execution, prevalence across deployments, hidden-class semantic truth, or arbitrary-metric compositionality.

This commit is protocol-only. It adds no runner, target implementation, result file, or target/queue execution permission.
