# ReplayMark E3b R1 non-interfering shadow hook

## Status and objective

This increment attaches the already-closed ReplayMark runtime certificate chain to the real E3b `R1_timing` path without changing the frozen R1 implementation or giving ReplayMark any execution authority.

The only admitted new behavior is:

```text
frozen R1 execution
  + passive capture
  -> post-execution RealizedObservation
  -> post-execution RealizedHistoricalAction
  -> same-task proof
  -> existing shadow semantic bridge
  -> chained ReplayMark certificate
```

There is still no blocking, fallback, regeneration, R2 substitution, or other execution policy.

## Frozen-source preservation

`agentmark_e3b_lab/e3_mqtt/app/ladder.py` is byte-immutable. Its Git blob SHA remains:

```text
fcc1768544714f1b11a497a856f8e18d4d2f07dd
```

This is mandatory because the file is both the historical R1 implementation under test and an authority already embedded in the frozen E3b historical-action realizer.

The gate also rechecks the frozen `device.py`, `experiment.py`, and `ladder_v2.py` blob identities before any live experiment.

## Exact boundary capture without modifying R1

The R1 evidence deadline is defined from the original task-local value:

```text
t0 = time.monotonic_ns()
verify_deadline = t0 + verify_ms
```

It is not reconstructed from the later ACT1 publish timestamp. Near the boundary those are not equivalent.

A temporary capture scope therefore wraps only module references used by the frozen code:

1. a transparent `time` proxy records the exact value returned to the original `t0` assignment;
2. a transparent MQTT client proxy timestamps and records the exact arguments presented to the real Paho `Client.publish`, then delegates the invocation exactly once.

No frozen source file is edited.

## Hot-path separation

ReplayMark semantic computation never runs concurrently with the R1 network workload.

```text
install capture-only wrappers
run existing ladder.cond(..., "R1_timing", ...)
restore original time / sleep / target_task / MQTT client objects
only then snapshot already-received Harness events
only then realize / correlate / certify
```

Thus the task hot path pays only capture bookkeeping. Contract lookup, adjudication, R*, certificate construction, and serialization occur after `cond()` has completed.

## Observation realization source

After `cond()` returns, R1 has already waited for stage-2 completion. Harness has therefore committed the earlier runner-local state callbacks needed for the verify boundary.

For each task the raw observation is closed exactly at the original verify deadline and contains every stage-1 Harness state event satisfying:

```text
recv_mono_ns <= verify_deadline_mono_ns
```

Only runner-local `time.monotonic_ns()` receive timestamps are compared. Device-container timestamps are never mixed into that clock domain.

## Historical-action realization source

The MQTT proxy observes the actual application call material passed to Paho. The frozen realizer still independently requires:

```text
stage-2 topic role and task identity exact
payload UTF-8 exactly {"on": true}
QoS = 1
retain = false
properties = none
```

The proxy timestamp is taken immediately before delegating the real publish call.

## Runtime contract context binding

The frozen AgentMark kernel is lifted through the existing read-only compatibility adapter. The runtime claim is the existing operation projection at H=0.

Bare runtime evidence tokens are admitted only for the `after_act1` decision boundary. Later controller states (`verified`, `done`) receive namespaced forward-evidence tokens, preventing a runtime feedback token from silently denoting a different controller context.

This is evidence-context binding, not a new target semantics implementation.

## Non-interference promotion contract

The live gate uses real Eclipse Mosquitto 2.1.2 and alternating paired baseline/shadow R1 arms. For each pair it requires all of the following:

```text
legacy stable R1 result fields are exactly equal
broker PUBLISH message count is exactly the original workload
actual shadow ACT1/ACT2 Paho call material equals the literal frozen R1 template
normalized device-state event semantics are exactly equal
state-event count is exactly equal
one chained ReplayMark certificate exists per R1 task
no extra command publish exists
```

The command-wire comparison covers every captured ACT1 and ACT2 call and compares exact topic, UTF-8 payload, QoS, retain, and properties against the literal output dictated by the byte-frozen `ladder.py` authority.

Timestamp-bearing device events are compared after removing only run-local timestamps. Task id, stage role, device identity suffix, `on`, and `cause` remain in the equality relation.

## Why `$SYS/broker/publish/bytes/received` is diagnostic-only

The first live attempt deliberately treated cross-run equality of Mosquitto's `$SYS/broker/publish/bytes/received` as a promotion invariant. That gate rejected a run even though:

```text
PUBLISH count              baseline = shadow = 256
state events               baseline = shadow = 128
legacy stable R1 outputs   exactly equal
shadow certificates        64 / 64 correct
```

The byte counter differed because it is an asynchronously sampled aggregate and includes timestamp-bearing device-state payloads whose raw decimal timestamp bytes naturally differ across separate executions. Exact equality of that aggregate is therefore not a sound oracle for whether the shadow hook changed application-controlled wire material.

The corrected gate does not weaken the requirement. It replaces the false aggregate oracle with a stricter causal one:

```text
actual application-controlled Paho command call material
    == literal byte-frozen R1 command template
```

while retaining exact broker publish-count and event-semantic conservation. The raw `$SYS` byte counter is still recorded for diagnosis but cannot promote or fail the increment.

## Expected shadow verdict in the shifted target world

The live gate deliberately uses the target delay that makes the original R1 timing-only replay semantically unsafe. Every shadow task is therefore expected to certify, without altering execution:

```text
observation       = not_visible_by_deadline
historical action = ACT2
verdict           = INVALID
R*                = DO_NOT_REUSE
```

Any other result fails the gate.

## Timing is intentionally not promoted here

Baseline/shadow p99 and ACT2 timing differences are recorded for visibility only. This increment closes semantic/wire/event/workload non-interference first. Formal certification-latency p50/p95/p99 thresholds belong to the later Constant-Cost Runtime Gate.

## Intentionally still open

```text
execution/fallback policy          NOT_IMPLEMENTED
selective-reuse intervention       NOT_IMPLEMENTED
constant-cost runtime optimization NOT_IMPLEMENTED
latency p50/p95/p99 promotion      NOT_IMPLEMENTED
Better Thermostat/HA realization   NOT_IMPLEMENTED
```
