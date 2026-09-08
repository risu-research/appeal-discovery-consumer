# Gate S3-C0 — Claim-to-Queue Composition Closure

Status: **PROSPECTIVE / NO LIVE QUEUE EXECUTION.**

S3-C0 is a proof-and-refinement gate between the already frozen S3 selective-retention result and any later deployment-level Mosquitto queue experiment. It does not run the target, inspect a new queue outcome, choose a capacity boundary, or modify ReplayMark semantics.

## 1. Why this gate exists

S3 established an action-level result:

- certified-safe historical decisions are actually reused;
- the unsupported complement is blocked and routed through a caller-owned current-state query and fresh ACT2;
- ReplayMark-Native's historical set exactly equals the independent safe set;
- ReplayMark-Native's caller-native set exactly equals the independent unsafe set; and
- all assigned tasks are restored.

The older E3b deployment experiment established a different endpoint: the number of QoS-1 task-namespace messages retained by a persistent offline Mosquitto subscriber under the documented default queue-count policy.

A semantic action result does **not** automatically imply a queue-capacity result. S3-C0 therefore asks whether the S3 execution paths refine that exact downstream endpoint task-by-task before any new deployment experiment is allowed.

This gate is deliberately motivated by the earlier failed Better-Thermostat downstream attempt: an upstream semantic difference is not assumed to survive an endpoint unless the endpoint projection is closed explicitly.

## 2. Frozen authorities

### S3

- S3-P protocol: `75d5d4379fdda221c0b9661f799d7779d6bba9f2`
- first-complete S3 execution: `8333e8808d5a950effd8a4e552718be3324909d3`
- S3 result seal / required parent of this gate: `cf1f09398ad6148dfa1907dd2a02bdc443308ab7`
- S3 artifact: `10035602271`
- S3 artifact ZIP SHA-256: `31bd3972787ee09e0e2c366a46d2fc8f9cc1049d5d33668bb8b253901f5af2db`

### Promoted documented-default queue result

- frozen protocol: `b8ae9503cbb32a260c32284f0aba0e679480050d`
- authoritative execution: `23b7c85bca6cb85fde9f4361a0f9664d21c8ae8d`
- promoted result: `ac20890bb4aa926e439802510de3723b74591c94`
- workflow run: `34002935533`
- artifact: `9980049060`
- artifact ZIP SHA-256: `9f8f78ddd0d80e3cf27f34a1625ed172553690342a31baee788f2764cd2f1dee`

The verifier pins the exact source blobs from both histories rather than copying their semantics into a new experimental runner.

## 3. Exact queue endpoint being composed

The legacy persistent subscriber subscribed to the task namespace and counted QoS-1 messages whose terminal role was exactly:

```text
command
query
state
```

The deployment endpoint is therefore the **count projection**

```text
Q(trace) = number of task-namespace QoS-1 PUBLISHes
           with terminal role in {command, query, state}.
```

A batch is lossless when the persistent offline subscriber later recovers every message in that projection.

This endpoint is intentionally **not** full trace equivalence. For the promoted documented-default capacity claim, message order and payload identity beyond task role/QoS are not the scientific endpoint. This matters because a caller-native query may occur at a different wall-clock phase than the old direct-native query while still inducing the same queue-count contribution.

Control-plane messages outside the task namespace are excluded. A task-local `QUERY_A` and its query-caused `state` are **inside** the endpoint; they are not silently discarded as instrumentation.

## 4. The critical native-reference distinction

S3's `ALWAYS_NATIVE` arm is a deliberately conservative rerun-all baseline. It performs the caller-owned query-confirmation path for every assigned task.

It is **not** the deployment ground truth.

The deployment reference is the direct target controller under the same decision evidence:

```text
confirmed_by_deadline:
    ACT1 -> state -> ACT2

not_visible_by_deadline:
    ACT1 -> QUERY_A -> current-state confirmation -> ACT2
```

Thus direct target-native execution queries only when the deadline evidence requires the query branch.

This distinction is frozen before S3-C1. Any later deployment comparison that substitutes S3 `ALWAYS_NATIVE` for the direct target controller fails the gate.

## 5. Concrete taskwise refinement

The frozen device semantics produce one task-local QoS-1 state publication for each command and one immediate task-local QoS-1 state publication for each query.

S3 freezes all A-side observations and waits for A-side quiescence before phase-B historical/native dispatch. Therefore the initial ACT1 command and its command-caused A-state are already part of every completed task's downstream work before selective dispatch.

### Evidence is `confirmed_by_deadline`

Direct target-native:

```text
ACT1 command          1
A command-state       1
ACT2 command          1
B command-state       1
-----------------------
total                 4
```

ReplayMark-Native certifies the historical ACT2, yielding exactly the same endpoint vector:

```text
(command, query, state) = (2, 0, 2), total = 4.
```

### Evidence is `not_visible_by_deadline`

Direct target-native:

```text
ACT1 command          1
A command-state       1
QUERY_A               1
A query-state         1
ACT2 command          1
B command-state       1
-----------------------
total                 6
```

ReplayMark blocks historical ACT2, then the caller performs `QUERY_A -> query-caused current-state confirmation -> fresh ACT2`. Its endpoint vector is therefore exactly:

```text
(command, query, state) = (2, 1, 3), total = 6.
```

The composition claim is only this frozen endpoint refinement. It is not a theorem that arbitrary ReplayMark contracts preserve arbitrary downstream metrics.

## 6. Aggregate law

Let:

- `N` = number of tasks in a batch;
- `U` = number of tasks whose **actual frozen decision evidence** takes the direct-native query branch.

Then both independent direct target-native execution and ReplayMark-Native induce

```text
M(N,U) = 4N + 2U
```

counted QoS-1 task messages.

The S3-C1 deployment oracle must compute this from raw task evidence/events without reading the caller policy label or hidden `REFERENCE/SHIFTED` target class.

Taskwise equality then gives aggregate equality by addition:

```text
M_ReplayMark-Native(N,U) = M_Direct-Native(N,U).
```

This is the exact composition bridge S3-C0 is meant to close.

## 7. Why 166 is deliberately **not** inherited

The old 166-task boundary was mechanically derived in a homogeneous changed target where **every task** took the six-message native branch:

```text
U = N
M(N,N) = 6N
floor(1000 / 6) = 166.
```

The frozen S3 heterogeneous workload intentionally contains both evidence-safe and evidence-unsafe tasks. Its native work is therefore `4N + 2U`, not `6N` in general.

Consequently:

> **S3-C0 must PASS only while refusing to inherit 166 as the new target boundary.**

Hard-coding `166` into S3-C1 is forbidden. The stronger deployment question is whether ReplayMark-Native reaches the **same queue conclusion as an independently executed direct target-native controller under the same fresh workload**, while preserving every historical decision certified safe.

If a future homogeneous all-query workload is separately frozen, `166` may again be derived from its own workload law. It is not imported into the heterogeneous capstone by nostalgia for the old headline.

## 8. S3-C1 admission requirements

S3-C1 is admitted only if this gate passes. A later protocol must then satisfy all of the following before seeing a new queue outcome:

1. direct target-native is an implementation independent from ReplayMark and from S3 `ALWAYS_NATIVE`;
2. ReplayMark-Native uses the frozen S3 certification/admission semantics unchanged;
3. both conditions receive the same prospectively frozen workload construction and queue policy;
4. the persistent subscriber counts the exact endpoint above, including task-local query traffic;
5. an independent post-run oracle reconstructs task evidence and expected work without policy or hidden-class labels;
6. no fixed numeric boundary is selected from a prior heterogeneous outcome;
7. first-complete deployment evidence is authoritative whether PASS or FAIL; and
8. if composition or runtime conservation fails, the result is preserved rather than repaired into a favorable deployment story.

## 9. Promotion and stop rule

S3-C0 PASS requires:

- exact S3 result-seal parent;
- exact current and legacy source blobs;
- exact legacy endpoint-role extraction;
- taskwise `4/6` refinement equality;
- policy-label-free aggregate law;
- explicit refusal to inherit the legacy 166 boundary; and
- zero live queue/target execution in this gate.

If any requirement fails, **S3-C1 is blocked**. No deployment experiment may be used to reverse-engineer a replacement composition rule.

## 10. Interpretation boundary

S3-C0 proves a concrete refinement for one frozen E3b/Mosquitto endpoint. It does not promote:

- arbitrary metric compositionality;
- sequence equivalence;
- payload equivalence beyond the declared queue projection;
- a 166-task heterogeneous boundary;
- S3 `ALWAYS_NATIVE` as target-native truth;
- a new latency claim;
- cross-process exactly-once; or
- broker-delivery exactly-once.

The desired scientific outcome of S3-C0 is not a dramatic number. It is a clean right to ask the deployment experiment at all.
