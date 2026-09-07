# ReplayMark E3b R1 non-interfering shadow hook

## Frozen objective

This increment attaches the already-closed ReplayMark runtime certificate chain to the real E3b `R1_timing` path while preserving the historical R1 implementation and its externally visible workload.

The permitted new behavior is only:

```text
frozen R1 execution
  + passive runtime capture
  -> post-execution RealizedObservation
  -> post-execution RealizedHistoricalAction
  -> same-task proof
  -> existing shadow semantic bridge
  -> certificate
```

There is still no execution policy, blocking, fallback, regeneration, or R2 substitution.

## Authority preservation

`agentmark_e3b_lab/e3_mqtt/app/ladder.py` remains byte-immutable. This matters twice:

1. it is the historical R1 implementation under test; and
2. its Git blob SHA is already embedded in the frozen E3b historical-action realizer as source authority.

The hook therefore does not add parameters, branches, callbacks, or certificate calls to `target_task`, `cond`, or `pub`.

## Why an external capture scope is necessary

The R1 observation boundary is based on the task-local value:

```text
t0 = time.monotonic_ns()
verify_deadline = t0 + verify_ms
```

It is not equivalent to reconstructing the deadline from the later ACT1 publish timestamp. Near a boundary, replacing `t0` with a publish timestamp could change the evidence token.

The shadow capture scope temporarily replaces only module references used by the frozen code:

- a transparent `time` proxy records the exact value returned to the original `t0` assignment;
- a wrapped first `sleep_until` arms that one capture after the scheduled offer sleep;
- a transparent MQTT client proxy timestamps and records the exact arguments supplied to the real `Client.publish` call, then delegates that call exactly once.

The original source file is unchanged.

## Hot-path separation

No ReplayMark semantic computation runs while R1 tasks are executing.

The sequence is:

```text
install capture-only wrappers
run existing ladder.cond(..., "R1_timing", ...)
restore original time / sleep / target_task / MQTT client objects
only then snapshot already-received Harness events
only then realize / correlate / certify
```

The only execution-time hook work is capture bookkeeping. Certificate construction, compiled-contract lookup, adjudication, and R* are outside the network workload interval.

## Observation snapshot rule

After `cond()` returns, the original R1 path has already waited for the task's stage-2 completion. The Paho callback thread is serial, so all callbacks whose runner-local receive timestamp is at or before the earlier verify deadline have already been committed to `Harness.state_events`.

The raw realization snapshot is therefore closed exactly at the frozen verify deadline and contains every Harness state event for that stage-1 device with:

```text
recv_mono_ns <= verify_deadline_mono_ns
```

Events use runner-local `time.monotonic_ns()` receive timestamps; device-container timestamps are never compared across clock domains.

## Historical-action capture rule

The MQTT proxy observes the actual arguments supplied to Paho. It does not trust caller semantic labels. The action realizer still independently validates:

- exact stage-2 topic role and task identity;
- exact UTF-8 payload `{"on": true}`;
- QoS 1;
- retain false;
- properties absent.

The proxy timestamp is taken immediately before delegating the actual Paho publish invocation.

## Runtime contract context binding

The frozen AgentMark kernel is adapted through the existing read-only `target_model_from_agentmark_kernel` path. The runtime claim is the existing operation projection at H=0.

Because the full adapted target also contains later controller states (`verified`, `done`), bare runtime feedback tokens are admitted only for the `after_act1` decision boundary. Other target states receive namespaced forward-evidence tokens. Thus:

```text
confirmed_by_deadline
not_visible_by_deadline
```

cannot accidentally denote a later controller state.

This is evidence-context binding, not a reimplementation of target semantics.

## Non-interference promotion gate

A real Eclipse Mosquitto 2.1.2 gate runs paired baseline and shadow R1 arms with alternating order and equal-length task prefixes. For every pair it requires exact equality of:

```text
legacy stable result fields
broker PUBLISH messages received
broker PUBLISH bytes received
Harness state-event count
```

and requires both arms to retain the original R1 workload of exactly four broker-level publishes per task (two command publishes plus two resulting device-state publishes).

The shadow arm must additionally produce exactly one chained ReplayMark certificate per R1 task and exactly two captured command invocations per task.

Under the deliberately shifted E3b target used by this gate, every R1 certificate is expected to be:

```text
observation = not_visible_by_deadline
historical action = ACT2
semantic verdict = INVALID
R* = DO_NOT_REUSE
```

This expected result is not used to alter execution.

## Timing is intentionally not promoted yet

The gate records baseline/shadow p99 and ACT2 timing differences for visibility, but timing is not yet an acceptance threshold. This increment proves semantic/workload non-interference first. Certification latency and hot-path optimization remain the later Constant-Cost Runtime Gate.

## Intentionally still open

```text
execution/fallback policy          NOT_IMPLEMENTED
selective-reuse intervention       NOT_IMPLEMENTED
constant-cost runtime optimization NOT_IMPLEMENTED
latency p50/p95/p99 promotion      NOT_IMPLEMENTED
Better Thermostat/HA realization   NOT_IMPLEMENTED
```
