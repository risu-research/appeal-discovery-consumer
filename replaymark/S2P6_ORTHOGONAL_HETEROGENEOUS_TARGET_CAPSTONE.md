# Gate S2-P6 — Orthogonal Heterogeneous-Target Selective-Reuse Capstone Protocol

Status: **FROZEN BEFORE ANY HETEROGENEOUS TARGET EXECUTION.**

P6 is a deliberate macro-pivot after the complete, preserved Q1/Q2/Q3 source-calibration failures. It does **not** repair those failures. It removes the unnecessary dependency on hosted transport jitter as the mechanism that creates a mixed semantic workload.

## Scientific question

Under one immutable heterogeneous target configuration, can ReplayMark execute exactly the historical ACT2 decisions independently supported by current evidence, while:

- **Always-Admit** retains all historical decisions but executes unsupported history,
- **Always-Block** executes no unsupported history but discards supported history, and
- **ReplayMark** retains exactly the independently supported historical subset?

The target-class label is never a ReplayMark input and is not itself semantic truth. Semantic truth remains the independent literal oracle over the actual frozen observation and exact ACT2 candidate.

## Authority

- Q3 complete scientific-failure seal: `ef370c38e6be82df340838be9db394559367c53e`
- S1 certified execution-admission authority: `c93c8574eb62cb4dcde94890fdfc8f939b41e00a`
- frozen observation realizer blob: `de6cdc8ccdbb9b189e238cc5dbad173060fe17ab`
- frozen action realizer blob: `d5d483751eb06fd8b00f7bb2eff613a20f0f796c`
- frozen same-task correlation blob: `bbdc243eccf29c0a26b92bc78c0acdb96222da8e`
- frozen S1 execution gate blob: `22748a5aa820e83e4700a339e8af297cdd9f9143`
- frozen E3b device reference blob: `27240e65cb8e1a7d788cc5dea8484cbad8ec6653`
- frozen R1/source ladder blob: `fcc1768544714f1b11a497a856f8e18d4d2f07dd`

## Why this is stronger than another Q4 calibration

Q1/Q2/Q3 already falsified the plan of obtaining a reviewer-resistant mixed workload by tuning source-load and a single delay boundary on a hosted MQTT path. P3 and P4 showed that roughly 40-ms transport/timer structure can survive even when device semantics are removed.

P6 therefore stops asking the transport stack to generate the semantic mixture for us.

Instead, one fixed target contains both reference-compatible and shifted target units. Their placement is frozen before execution, independent of policy, certificate, oracle, and outcome. ReplayMark does not receive the placement map.

## Exact orthogonal design

There are 6 trials, 64 blocks per trial, and 3 tasks per block.

The existing frozen S2 policy schedule is inherited unchanged:

- one `ALWAYS_ADMIT` task,
- one `ALWAYS_BLOCK` task,
- one `REPLAYMARK` task,

in every 3-task block.

Target class is assigned at the **block** level. For each trial, blocks 0..63 are SHA-256 ranked under the frozen P6 class seed. The lowest 32 are `REFERENCE`; the highest 32 are `SHIFTED`.

Therefore, without inspecting a single runtime outcome, every policy receives exactly:

```text
32 REFERENCE + 32 SHIFTED tasks per trial
```

The joint 1,152-row policy × target-class schedule SHA-256 is:

```text
f94fafcf932baa74f37979485af1d1f494ecde7ad0491ad35d6536478496a750
```

The target-class block map SHA-256 is:

```text
27c137dc2573a040596be5fbec3eedc4edad3e020e73d586660c1043880502e7
```

## One immutable target configuration

The additive lab-only heterogeneous target must preserve the frozen `device.py` command/query/state wire semantics. The only allowed semantic delta is replacing the single global `state_delay_ms` scalar with an immutable per-device delay chosen from the frozen block schedule:

- `REFERENCE`: 0 ms
- `SHIFTED`: 180 ms

The same class applies to both role `a` and role `b` for a task.

The target receives no policy, certificate, oracle, or ReplayMark verdict. It emits no target-class label on the state wire. There is no control-plane mutation during the run.

This is one pre-installed heterogeneous target, not task-by-task adaptive retuning.

## Historical ACT2 meaning

P6 reuses the frozen E3b historical ACT2 decision content:

```text
operation       ACT2
target role     stage2
topic role      agentmark/<prefix>-<task-id>-b/command
payload         {"on": true}
QoS             1
retain          false
properties      null
```

The current `publish_mono_ns` is the already-frozen pre-send realization provenance needed to bind the historical decision to the current same task. It is not a rewrite of the historical decision content.

Historical template SHA-256:

```text
e86d5f42a09b8257185b6e3608ac83c0ac41deeba7890b914c22b0441a8b8888
```

## Execution order

For each trial:

1. publish ACT1 for all 192 tasks under the frozen offer schedule;
2. close every complete observation snapshot at/after its 100-ms evidence deadline;
3. freeze all 192 snapshots;
4. wait for the A-side quiescence barrier;
5. instantiate the exact historical ACT2 candidate for each task;
6. certify every candidate through the unchanged runtime chain;
7. dispatch by the assigned policy;
8. close the live harness;
9. only then run the independent oracle.

No ACT2 may affect another task's observation evidence.

## Promotion

P6 does **not** require the hidden `REFERENCE` class to be semantically safe task-by-task. Hosted transport noise may still make some reference tasks unsafe. The independent oracle is the authority.

ReplayMark promotes only if:

```text
executed_task_set == independent_oracle_safe_task_set
unsafe_execution_count == 0
unnecessary_block_count == 0
```

Always-Admit must execute at least one oracle-unsafe historical decision. Always-Block must unnecessarily block at least one oracle-safe historical decision.

Each policy must receive at least 64 oracle-safe and at least 64 oracle-unsafe tasks in aggregate, and every trial must contain both.

## Anti-leakage

- target class is not a ReplayMark input;
- target class is not present in the raw observation/action record;
- production ReplayMark imports no target schedule;
- policy assignment is independent of target class;
- target class is independent of policy;
- live policy path imports no independent oracle;
- all observations freeze before any policy dispatch.

## Anti-repair

- Q1, Q2, and Q3 remain failed;
- P6 has no `D*`;
- P6 has no source calibration;
- no heterogeneous-target probe is allowed before the first complete capstone;
- 0/180-ms class delays are immutable after this freeze;
- the class schedule is immutable after this freeze;
- the 100-ms semantic evidence boundary is unchanged;
- the first complete P6 report is authoritative;
- later exact executions are replication only.

Fallback, regeneration, and automatic retry remain **ABSENT**.
