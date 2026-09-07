# Gate S1 — Certified Execution Admission, No Fallback

Status target: **one narrow execution boundary only**.

Frozen base:

- S0 seal: `8716db916c49578ee69930b973a44f892f975307`
- S0 optimization authority: `25d317392b9ce6aaaedc190ef6aff8bc38d555b5`
- semantic core, realizers, same-task correlation, runtime bridge, R1 shadow,
  integrated conformance, and current runtime cost remain byte-identical.
- runtime micro-optimization remains frozen.

## Question

S0 established that a live runtime chain can produce an auditable certificate
whose R* result is either `REUSE` or `DO_NOT_REUSE`. S1 asks the first execution
question:

> Can the validated certificate itself be made the only authority that opens the
> historical-reuse action sink?

The S1 policy is intentionally minimal:

```text
validated VALID + REUSE             -> ADMIT_REUSE
validated INVALID + DO_NOT_REUSE    -> BLOCK_REUSE
validated UNRESOLVED + DO_NOT_REUSE -> BLOCK_REUSE
```

`BLOCK_REUSE` does **not** mean regenerate, retry, verify again, abort, or choose
another action. Those choices remain absent.

## Why the boundary is prospective

The earlier R1 shadow hook was deliberately non-interfering: it allowed the
frozen action to execute and certified the run afterward. That is scientifically
correct for shadow conformance, but it cannot itself enforce selective execution.

S1 therefore moves the action capture to its already-frozen semantic meaning:
the resolved E3b `Client.publish` candidate **at the pre-send boundary**. The raw
candidate contains the exact topic, payload, QoS, retain flag, properties, clock
domain, and candidate invocation timestamp. Nothing has been sent merely because
this candidate record exists.

A complete decision-boundary observation is closed first. The candidate action
and observation are then:

1. realized by the frozen realizers;
2. same-task correlated by the frozen correlator;
3. certified through the frozen `ExplicitCompiledContract` bridge;
4. independently reconstructed again by the execution gate;
5. byte-compared to the presented chained certificate;
6. mapped to `ADMIT_REUSE` or `BLOCK_REUSE`;
7. consumed exactly once within the gate instance; and
8. only if admitted, delegated once to the concrete MQTT publish sink.

This avoids the circular mistake of executing first and claiming the result was
prospectively gated afterward.

## Two-layer design

### 1. Generic admission policy

`replaymark/execution_admission.py`

This module accepts an **already validated** `RuntimeReuseCertificate` and adds no
semantic reasoning. It only maps frozen R* entitlement to execution admission.
It does not import or call the adjudicator, compiler, support envelope, evidence
compiler, MQTT, fallback, or regeneration logic.

The three-valued semantic reason remains embedded in the admission record. Thus
`INVALID` and `UNRESOLVED` both block reuse, but remain distinguishable.

### 2. E3b validating execution gate

`replaymark/runtime_e3b_execution_gate.py`

The safe dispatch path never trusts a caller-supplied verdict, reuse flag,
same-task flag, or alternate action. It receives:

```text
ExplicitCompiledContract
raw observation
raw pre-send action candidate
presented chained certificate
```

It recomputes the pair and chained certificate through the frozen components and
requires exact canonical-byte equality with the presented certificate.

Only the recomputed, validated action candidate can reach the sink. There is no
topic/payload/QoS/retain/properties override parameter in the dispatch API.

## Fail-closed behavior

The following do not execute historical reuse:

- valid certificate with `INVALID`;
- valid certificate with `UNRESOLVED`;
- certificate/raw-material mismatch;
- foreign contract;
- realization or same-task-correlation failure;
- duplicate consumption of the same admission;
- any malformed action candidate.

A sink failure after admission is also terminal in S1. The admission is marked
consumed **before** the external delegate call. S1 does not automatically retry,
regenerate, or select another action after an ambiguous side effect.

## Single-use scope

S1 enforces at-most-once application dispatch for one admission **within one gate
instance/process**, including concurrent duplicate callers.

S1 deliberately does **not** claim durable cross-process exactly-once execution.
MQTT QoS behavior, process crashes, broker retries, and persistent idempotency are
different problems. A later capstone may add a durable deduplication mechanism if
the target system actually requires it; S1 will not manufacture that claim.

## Live Mosquitto falsification

The live gate runs a dedicated prospective admission harness, not the frozen R1
performance experiment.

For each task it closes the observation at the verify deadline, constructs the
exact stage-2 pre-send candidate, produces the chained certificate, then lets the
S1 gate independently revalidate it before any stage-2 delegate call.

Two real-broker arms are required:

### Positive arm

- state delay: below the verify boundary;
- evidence: `confirmed_by_deadline`;
- semantic verdict: `VALID`;
- R*: `REUSE`;
- S1: `ADMIT_REUSE`;
- exact gate-owned stage-2 publish delegates: one per task;
- observable stage-2 state effects: one per task.

### Negative arm

- state delay: beyond the verify boundary;
- evidence: `not_visible_by_deadline`;
- semantic verdict: `INVALID`;
- R*: `DO_NOT_REUSE`;
- S1: `BLOCK_REUSE`;
- gate-owned stage-2 publish delegates: zero;
- observable stage-2 state effects: zero.

The negative arm is the critical causal check: the same candidate action exists
and is certifiable as a candidate, but the sink remains closed.

## Non-goals

S1 does not claim:

- a complete selective-reuse capstone;
- latency improvement;
- fallback quality;
- regeneration policy;
- evidence refinement policy;
- durable exactly-once behavior;
- broker-delivery exactly-once behavior;
- target-wide generalization beyond the admitted E3b boundary;
- any new semantic theorem.

The S0 optimization freeze remains in force.

## Promotion rule

Gate S1 closes only if all of the following pass on the exact S1 commit:

- S0 is the exact parent;
- every S0 frozen blob is unchanged;
- only the declared additive S1 files exist in the increment;
- generic mapping matches an independent literal oracle;
- VALID dispatches exactly once;
- INVALID dispatches zero times;
- UNRESOLVED dispatches zero times;
- mismatched/foreign certificates fail before the sink;
- concurrent duplicate admission causes exactly one application delegate call;
- sink failure is not automatically retried;
- the dispatch API exposes no fallback or action-override surface;
- the live positive Mosquitto arm admits and produces the expected stage-2 effect;
- the live negative Mosquitto arm blocks with zero stage-2 delegate/effect;
- no S0 runtime optimization is introduced.

Only then may the project move from **certified shadow judgment** to a
**certified execution-admission primitive**.
