# ReplayMark External Retention-Transfer Gate — Frozen Protocol

**Status:** protocol freeze before decisive scripted audit  
**Branch:** `replaymark-external-retention-transfer-final`  
**Base theory head:** `5a75e3b99d7602d3506555fda12192d8903a7eb8`  
**Purpose:** test whether ReplayMark's retention boundary transfers to independently authored, current trace-replay systems without changing ReplayMark's definitions or silently broadening their claims.

## 1. Scientific posture

Exploratory reconnaissance identified two strong external candidates and several negative/irrelevant cases. This file freezes the decisive source audit **after candidate discovery but before the scripted adjudication is executed**. Candidate selection is therefore exploratory; the invariants, claim profiles, verdict rules, and promotion criteria below are frozen before the mechanical result.

This gate is adversarial in both directions:

- it must detect a retained claim-relevant decision when the external artifact actually has one;
- it must **not** call a fixed-workload serving benchmark invalid merely because its historical structure is retained;
- uncertainty must remain `UNRESOLVED`, not be promoted to `INVALID`;
- a source-level transfer result is not a target-native runtime divergence result.

The intended contribution, if the gate passes, is claim-sensitive transfer: the same replay artifact can legitimately support a fixed historical workload claim while failing to license a stronger target-native agent-path claim.

## 2. External systems and immutable pins

### Candidate A — NVIDIA TensorRT-LLM Scaffolding trace replay (primary)

Repository: `NVIDIA/TensorRT-LLM`  
Pinned commit: `26092ade9de608a71695bfc5800c956b8658ee98`

Pinned files:

1. `tensorrt_llm/scaffolding/trace_replay/replay.py`  
   Git blob SHA: `8561acd566853d9582093aa67af3c468ff87d3da`
2. `examples/scaffolding/trace_replay/trace_example/matplotlib__matplotlib-23412/matplotlib__matplotlib-23412.trace.json`  
   Git blob SHA: `b072d91ba795936957c1d6318f0b0c5e82ea9901`
3. `examples/scaffolding/trace_replay/README.md`  
   Git blob SHA: `fcf57ede2452aeee8294fa8990c0976ed3509061`
4. `docs/source/blogs/tech_blog/blog27_Evaluating_Agentic_Serving_with_Trace_Replay_and_Job_Level_Metrics.md`  
   Git blob SHA: `9b6a6321f24fb777994c032f9fd96458ea366329`

### Candidate B — AIPerf / InferenceX AgentX Weka replay (independent transfer replication)

Repository: `ai-dynamo/aiperf`  
Pinned commit: `13ae4f6b6b5363007ad52ee2470c3b49c9403b34`

Pinned files:

1. `docs/tutorials/weka-trace.md`  
   Git blob SHA: `8e84b82264750e729ca41a9cdab6c3e237fc6eed`
2. `docs/tutorials/agentx-mvp.md`  
   Git blob SHA: `2a8210ecd31f95c699e53c43f104b620a7c18c80`
3. `src/aiperf/dataset/loader/weka_trace.py`  
   Git blob SHA: `6aa56f42fe83fa443263f0abc6dff0aa6732e245`

The audit must recompute each Git blob SHA from downloaded bytes and fail closed on any mismatch.

## 3. Claim profiles

The external replay systems are not assigned one universal verdict. ReplayMark adjudicates a **claim**.

### C_fixed — fixed historical serving-workload claim

The benchmark endpoint is performance of a serving system under the recorded structural workload: recorded request/branch topology, token budgets, and tool-delay structure are part of the exogenous benchmark workload.

For this claim, a historical tool name or branch topology need not represent what the target model's live agent would choose. Retention is intentional workload construction. ReplayMark therefore does **not** infer invalidity merely from semantic retention.

Canonical output label for this gate:

`LICENSED_AS_FIXED_WORKLOAD_OBJECT`

This label means only that the retention finding does not contradict this fixed-workload claim. It is not a blanket certification of every metric or implementation detail of the external benchmark.

### C_native — target-native reactive agent-path claim

The benchmark endpoint is the workload/path a live agent using the replay target model/controller would itself generate on the target execution.

For this claim, tool selection, branch/fan-out decisions, and subsequent claim-relevant path choices are consequential actions. A retained historical decision may be reused only if target evidence certifies support.

At the first retained decision, use the conservative action projection appropriate to the artifact, e.g.

`phi_native(a) = (decision_kind, resolved_tool_or_branch_class)`.

The decisive source audit asks whether the replay artifact itself establishes that a fresh target decision supports the historical action it subsequently schedules.

## 4. Frozen predictions — Candidate A

The scripted audit must test all of the following.

### A1 — fresh target generation occurs

For assistant-message events, the replay implementation constructs a generation task and invokes the configured replay worker/backend. The source audit must locate this target generation path mechanically.

### A2 — historical consequential actions are independently replayed

Historical `tool_call` events are separate trace events. Their replay handler uses recorded timing and does not execute or regenerate the external tool decision from fresh target semantics.

### A3 — no semantic guard links fresh target output to the retained tool event

The assistant replay path must not use the historical `event.tool_calls` field to test whether the fresh target output selected the same historical tool before the later trace `tool_call` event is dispatched. The trace-routing path must schedule non-structural events from `trace.events` independently of such a support check.

This is a **source invariant**, not an inference from comments.

### A4 — a shipped, independently authored trace contains the retained-decision pattern

The pinned shipped trace must contain at least one assistant message with a non-empty historical `tool_calls` list and at least one historical `tool_call` event. The audit must report exact counts and the first witness pair/event sequence.

### A5 — claim-sensitive ReplayMark adjudication

If A1–A4 hold:

- `C_fixed` => `LICENSED_AS_FIXED_WORKLOAD_OBJECT` with respect to this retention question.
- `C_native` => `UNRESOLVED` from the replay artifact alone unless additional evidence proves target support or exclusion.

Reason: the replay artifact establishes that a fresh target generation occurred and that a historical decision was retained, but absent semantic linkage the evidence does not establish that the target-native agent supports that retained action. ReplayMark must not infer structural exclusion from absence of a check.

### A6 — INVALID requires stronger evidence

`INVALID` is forbidden at source-audit stage. It may be promoted only if a separately frozen target-native comparator or structural target model proves the retained historical action is outside possible target support.

## 5. Frozen predictions — Candidate B

The independent replication tests whether the same retention boundary appears in a different replay implementation.

### B1 — target model rewriting

The pinned AIPerf documentation/source must establish that recorded trace model names can be rewritten to configured served model(s); the target model need not match the model that generated the recorded trace.

### B2 — recorded DAG/subagent topology is retained

The pinned documentation/source must establish that recorded subagent/fan-out structure is reconstructed into root/child conversations and SPAWN/SPAWN_JOIN dependencies rather than regenerated by the newly configured target model.

### B3 — claim-sensitive adjudication

If B1–B2 hold:

- a fixed historical traffic/serving claim is not rejected by ReplayMark merely for retaining the topology;
- a stronger claim that this different target model's live agent would itself choose the same subagent topology is `UNRESOLVED` without target-decision evidence.

No `INVALID` claim is licensed by this source-only replication.

## 6. Negative controls / exclusions

Exploratory reconnaissance found examples where ReplayMark should not manufacture a gate:

- **Co-zyBench:** current simulated building/occupant state is consumed and HVAC setpoints are recomputed during EnergyPlus callbacks. This is a regeneration-style negative control, not a positive retention witness.
- replay systems whose explicit scientific object is the recorded trajectory itself remain legitimate for that fixed-trajectory claim unless a stronger target-native claim is asserted.

These cases are not included in the decisive positive source gate and must not be reclassified to improve apparent prevalence.

## 7. Mechanical audit requirements

The audit program must be deterministic, dependency-light, and fail closed.

For Candidate A it must:

1. verify pinned Git blob identities from raw bytes;
2. parse `replay.py` with Python `ast`;
3. locate `QueueExecutor._handle_tool_call`, `QueueExecutor._handle_message`, and `ReplayEngine.launch_trace`;
4. prove source invariants A1–A3 with AST/source-segment predicates rather than comments alone;
5. parse the shipped JSON trace and compute A4 counts/witnesses;
6. inspect pinned README/blog text only for declared benchmark intent/claim context, never to substitute for code invariants.

For Candidate B it must:

1. verify pinned Git blob identities;
2. test exact, predeclared documentation/source markers for model rewriting and topology reconstruction;
3. inspect the loader source for reconstructed child conversations and SPAWN/SPAWN_JOIN semantics;
4. report B1–B3 separately from Candidate A.

The program must emit:

- `EXTERNAL_RETENTION_TRANSFER_RESULTS.json`
- `EXTERNAL_RETENTION_TRANSFER_REPORT.md`

Every individual predicate must be recorded with PASS/FAIL and supporting source location or source fragment hash where feasible.

## 8. Promotion gates

### G0 — integrity
All pinned upstream identities match. Otherwise `FAIL_INTEGRITY` and stop.

### G1 — NVIDIA source-transfer gate
A1–A4 all PASS. Then `NVIDIA_SOURCE_TRANSFER=PASS` and claim verdicts are emitted exactly as frozen above.

### G2 — AIPerf independent-transfer gate
B1–B2 PASS. Then `AIPERF_SOURCE_TRANSFER=PASS` and claim verdicts are emitted exactly as frozen above.

### G3 — external retention-transfer promotion
G1 and G2 both PASS. Then the result may support the bounded claim:

> Two independently authored, current agent-serving trace-replay implementations retain historical agent structure while allowing a different/fresh target model to serve the replay. ReplayMark does not reject their fixed-workload serving claims; it identifies that the same replay evidence alone does not license the stronger claim that the target model's live agent would generate the retained path.

This is an **external claim-boundary transfer**, not an empirical target-native mismatch.

### G4 — quantum-jump INVALID promotion
Not satisfied by source audit. Requires a new preregistered comparator showing a retained historical action is outside target possible support in an external target-native execution.

### G5 — strongest downstream promotion
Not satisfied by source audit. Requires G4 plus a changed external benchmark conclusion (ranking, capacity, success/failure, or another predeclared consequential endpoint).

## 9. Anti-overclaim license

Even if G3 passes, the manuscript must not say:

- TensorRT-LLM trace replay is invalid;
- AgentX is invalid;
- the target model definitely would choose a different tool/path;
- fixed-traffic serving measurements are unsound merely because topology is retained.

The strongest source-audit wording licensed by G3 is:

> ReplayMark distinguishes workload replay from target-native path replay. In two independent agent-serving trace replayers, historical structure is intentionally retained while the serving target may differ from the trace-generating model. That is legitimate for a fixed-workload serving claim; without evidence linking fresh target decisions to the retained structure, the stronger target-native agent-path claim remains unresolved.

## 10. Stop rule

After the decisive scripted audit:

- if G3 fails, do not rescue the result by weakening predicates post hoc;
- if G3 passes but G4 is infeasible without reconstructing private/missing trace semantics or introducing an artificial mock, freeze the source-transfer result and return to manuscript polish;
- pursue G4 only if a natural, reproducible target-native comparator can be constructed without changing the external benchmark's task semantics.
