# Gate S2-P — Pre-Frozen Mixed Selective-Reuse Capstone Protocol

Status: **FROZEN BEFORE SOURCE CALIBRATION AND BEFORE ANY SHIFTED-target outcome.**

Authority inherited from Gate S1:

- S1 certified execution admission: `c93c8574eb62cb4dcde94890fdfc8f939b41e00a`
- S0 current-runtime seal: `8716db916c49578ee69930b973a44f892f975307`
- S0 optimization authority: `25d317392b9ce6aaaedc190ef6aff8bc38d555b5`

This gate adds **no experiment runner, no target execution, no semantic theorem,
no fallback, no regeneration, and no runtime optimization**. Its purpose is to
commit the project to the capstone design before data can influence the design.

## Scientific question

Gate S1 proved that a validated runtime certificate can prospectively open or
close the exact E3b ACT2 application sink. S2 asks the stronger systems question:

> Under one fixed target configuration and one shared historical-action class,
> can ReplayMark retain exactly the historical decisions independently supported
> by current evidence, while an Always-Admit policy executes unsafe decisions and
> an Always-Block policy discards safe decisions?

The capstone is not a latency contest and is not a new semantic theorem. It is
the first direct systems realization of the fixed-evidence maximal safe-reuse
boundary.

## Why protocol freeze comes before calibration

A mixed workload is unusually vulnerable to threshold cherry-picking. Choosing a
target delay after inspecting target outcomes would make the centerpiece result
scientifically weak even if the final figure looked excellent.

Therefore S2 is split into four irreversible stages:

1. **S2-P** — freeze this protocol with no calibration and no shifted target run.
2. **S2-Q** — perform source-only calibration at state delay 0 and seal exactly
   one derived `D_star`.
3. **S2-E** — execute the first complete mixed target capstone at exactly that
   sealed `D_star`.
4. **S2-F** — audit the completed execution for leakage, post-hoc exclusion, and
   policy-dependent evidence or candidate construction.

A qualification failure is a scientific result. It is not permission to move
the target delay until the desired mixture appears.

## Source-only calibration

The verify boundary is inherited and frozen at **100 ms**.

S2-Q uses three source-only replicates, each with:

- 192 ACT1-only tasks;
- wave size 32;
- wave period 300 ms;
- source state delay 0 ms;
- task timeout 1000 ms.

No ACT2 candidate is constructed and no shifted target arm is run.

For every source task:

```text
completion_offset = state_on_recv_mono_ns - task_t0_ns
```

The 576 offsets are pooled. Source qualification requires every task to complete,
every state to be visible by the 100-ms verify boundary, and pooled p99 <= 80 ms.

The only legal mixed-stress delay is then:

```text
D_star_ms =
    floor((100 ms - pooled_median_source_completion_ms) + 0.5)
```

That is nearest-integer-millisecond rounding for a positive value. `D_star` must
be at least 1 ms and strictly below 100 ms.

S2-Q seals the exact raw source rows, the pooled statistics, and `D_star` before
any shifted target outcome may be generated. There is no second formula and no
target-informed retuning.

## One fixed target, not task-specific labels

S2-E uses the exact same sealed `D_star` for every target task in every policy.
The experiment may not alternate task-specific delays, expose a delay label to
ReplayMark, or adapt the delay after observing outcomes.

The target workload consists of six fresh trials of 192 tasks each:

- 1152 total target tasks;
- wave size 32;
- wave period 300 ms;
- verify boundary 100 ms;
- task timeout 1000 ms.

The intended mixture must arise from the real runtime under one fixed target
configuration, not from hand-labeled safe and unsafe task classes.

## Freeze evidence before any policy can perturb it

The three policies share one target workload. To prevent policy side effects from
changing later evidence, every trial is split into two causal phases.

### Phase A — evidence materialization

All 192 tasks issue ACT1 only. Every observation snapshot is closed at the same
100-ms decision boundary and frozen. No ACT2 candidate is dispatched.

After every snapshot is frozen, the runner waits for A-side quiescence. Late A
events may be observed for quiescence but may never rewrite an already-closed
snapshot.

Only after this barrier may Phase B begin.

### Phase B — prospective candidate and dispatch

Tasks are processed in ascending task id. For each task, the exact frozen ACT2
candidate is constructed immediately before certification/dispatch:

- payload exact UTF-8 `{"on": true}`;
- QoS 1;
- retain false;
- properties null;
- canonical E3b stage-2 topic.

The same candidate constructor is used for every policy.

A ReplayMark certificate is computed for every task so that the semantic
bookkeeping path is common, but **Always-Admit and Always-Block are forbidden to
consult the certificate outcome when choosing their action**.

No fallback, regeneration, or automatic retry exists in S2.

## Outcome-blind policy assignment

Policy assignment is fixed by this protocol before S2-Q.

Policies:

- `ALWAYS_ADMIT`
- `ALWAYS_BLOCK`
- `REPLAYMARK`

Tasks are assigned in balanced blocks of three. Every block contains exactly one
task from each policy. The permutation is selected from six permutations by:

```text
SHA256(
  "replaymark.s2.policy-assignment.v1|s1=c93c8574...|trial=<t>|block=<b>"
)

selector = big-endian uint64(first 8 digest bytes) mod 6
```

Each trial therefore has exactly 64 tasks per policy and 64 blocks. Across six
trials each policy receives 384 tasks.

The complete 1152-row assignment schedule is committed by SHA-256:

`ec91b78a6720ef9b4e83da12f9b8cf37c1d05028bb6ebaf0e4c6a274ff372d1e`

The assignment cannot depend on target observation, semantic verdict, certificate,
or independent oracle.

## Controlled baselines

The capstone uses three deliberately narrow policies.

### Always-Admit

Execute the exact ACT2 candidate once for every assigned task. Certificate
content is ignored for the decision.

### Always-Block

Execute zero ACT2 candidates for every assigned task. Certificate content is
ignored for the decision.

### ReplayMark

Dispatch only through the frozen S1 certified execution gate. No alternate action
surface exists.

The paper must not call this global Pareto optimality over regeneration,
acquisition, or other costs. The formal claim remains the fixed-evidence
maximal sound reuse result.

## Independent evaluation occurs after execution

The live dispatch path is not allowed to import or consult the independent oracle.

After all dispatch is complete and the live harness is closed, a separate
evaluation step applies the frozen production-independent E3b literal oracle to
the recorded raw observation/action material.

For each task:

```text
oracle_safe =
    oracle verdict == VALID
    and oracle reuse disposition == REUSE

unsafe_execution = executed and not oracle_safe
safe_retention    = executed and oracle_safe
unnecessary_block = not executed and oracle_safe
sound_block       = not executed and not oracle_safe
```

This prevents the evaluation label from becoming an execution input.

## Qualification

A capstone run may be promoted only if the fixed target naturally yields an
informative mixture:

- all 1152 rows are present;
- no task is excluded post hoc;
- every trial contains at least one oracle-safe and one oracle-unsafe task;
- pooled safe fraction is within [0.20, 0.80];
- each policy's 384-task aggregate contains at least 64 safe and 64 unsafe tasks.

If this qualification fails, the result is preserved as a null/negative S2
result. `D_star`, verify boundary, workload shape, policy schedule, thresholds,
and task selection may not be changed to rescue the experiment.

## Promotion

For the independently labeled assigned tasks:

### ReplayMark

```text
executed task set == oracle-safe task set
unsafe executions == 0
unnecessary blocks == 0
safe-retention rate == 1
unsafe-execution rate == 0
```

Exact set equality is required. One misclassified task fails the gate.

### Always-Admit

```text
executed task set == all assigned tasks
safe-retention rate == 1
unsafe-execution rate == 1
unsafe executions > 0
```

### Always-Block

```text
executed task set == empty set
safe-retention rate == 0
unsafe-execution rate == 0
unnecessary blocks > 0
```

At the application boundary every executed candidate must have exactly one
delegate invocation. An executed candidate must yield at least one matching
B-side state effect; a blocked candidate must yield zero matching B-side effects.
No broker-delivery exactly-once claim is made.

There is no latency or speedup promotion threshold.

## First-complete-run authority

S2-Q's first complete source-only calibration artifact becomes the sole `D_star`
authority.

After a separate S2-E execution charter is frozen, the **first complete live S2-E
report** is authoritative. A complete qualification failure cannot be replaced by
a more favorable rerun.

An infrastructure retry is allowed only before a complete report exists and only
with the exact same commit, protocol, and already-sealed `D_star`. Later exact
runs are replications and never replace the first complete result.

## Prohibited repairs

The following are protocol violations:

- changing `D_star` after any shifted-target outcome;
- changing the 100-ms verify boundary;
- task-specific or policy-specific target delay;
- assigning policy from evidence, verdict, or oracle;
- policy dispatch before all trial observations are frozen;
- letting B-side policy traffic alter any frozen A-side evidence;
- baseline use of certificate content for its decision;
- live use of the independent oracle;
- post-hoc task/trial removal;
- relabeling runtime/realization failure as semantic `UNRESOLVED`;
- adding fallback, regeneration, or automatic retry;
- reopening runtime micro-optimization because the capstone is aesthetically slow.

## What S2 does not claim

S2 does not establish caller-owned fallback quality, regeneration policy,
cross-process exactly-once behavior, broker exactly-once delivery, global Pareto
optimality, target-wide generalization, a new theorem, or a minimal subset of raw
input variables.

If S2 promotes, the next systems gate is caller-owned native fallback and
deployment-answer restoration. Until then, the only new scientific question is
whether ReplayMark realizes the already-proved selective-reuse boundary as an
observable live-system advantage.
