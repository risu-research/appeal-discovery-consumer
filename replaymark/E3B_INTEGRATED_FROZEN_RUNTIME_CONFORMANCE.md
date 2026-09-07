# ReplayMark E3b Integrated Frozen Runtime Conformance

## Status

This increment closes the first **task-by-task integrated runtime conformance**
boundary above the already frozen E3b R1 non-interfering shadow hook.

The question is no longer whether each component passes in isolation. The gate
asks whether one concrete live R1 task preserves a single, content-addressed
identity and semantic meaning through the complete chain:

```text
live R1 runtime facts
  -> raw observation/action records
  -> observation realization
  -> historical-action realization
  -> same-task correlation
  -> frozen ExplicitCompiledContract
  -> three-valued adjudication
  -> R*
  -> chained E3b runtime certificate
```

No execution/fallback policy is added.

## Independent literal oracle

The integrated comparison uses
`replaymark_oracle/e3b_integrated_runtime_oracle.py`.

That module imports no ReplayMark production module, AgentMark module, Paho MQTT
module, `ladder`, or experiment harness. It independently restates only the
frozen E3b literal definition:

- exact observation schema and closed monotonic boundary;
- exact event predicate and inclusive deadline;
- exact `a` observation / `b` action task identity;
- exact ACT2 topic, payload, QoS, retain and properties;
- same prefix/task and same monotonic clock;
- stage-2 cannot precede stage-1;
- at the frozen H=0 operation claim:
  - `confirmed_by_deadline + ACT2 -> VALID / REUSE`
  - `not_visible_by_deadline + ACT2 -> INVALID / DO_NOT_REUSE`.

The static oracle gate rejects any production import.

## Per-task conformance row

Every live task receives a row containing:

1. independent literal expectation;
2. raw observation SHA-256;
3. raw historical-action SHA-256;
4. realized observation fingerprint;
5. realized historical-action fingerprint;
6. same-task correlation fingerprint;
7. generic runtime semantic-certificate fingerprint;
8. chained E3b certificate fingerprint;
9. exact verdict and reuse disposition;
10. a fixed boolean conformance vector.

The conformance vector checks all seams, including:

- literal token equality;
- literal action coordinate equality;
- exact task prefix/id/role binding;
- observation and action raw-digest provenance;
- realizer semantic-digest authority;
- correlator semantic-digest authority;
- bridge semantic-digest authority;
- correlation binding to exact realized fingerprints;
- exact raw timestamp binding;
- same clock domain end to end;
- exact concrete target/QoS/retain;
- semantic certificate binding to the correlated pair;
- contract and claim fingerprints end to end;
- byte equality between the bridge's embedded adjudication/R* outputs and direct
  calls to the frozen `ExplicitCompiledContract`;
- exact H=0 `operation=ACT2` projection.

A row is PASS only if every fixed check is true.

## Matrix content address

Rows are sorted by live trial and canonical task id. Every row is content
addressed. The gate then seals an integrated matrix manifest containing:

- frozen ladder authority;
- contract/claim fingerprints;
- observation realizer semantic digest;
- action realizer semantic digest;
- correlator semantic digest;
- bridge semantic digest;
- the ordered list of row SHA-256 values.

The manifest SHA-256 is the run's **integrated conformance matrix identity**.

It is intentionally run-specific because real runtime timestamps and provenance
are included. It is not claimed to be stable across executions.

## Live substrate

The gate first re-runs the already frozen R1 baseline-vs-shadow non-interference
experiment on real Eclipse Mosquitto 2.1.2.

It then runs a separate integrated-conformance workload using the same frozen
`ladder.py` and production shadow hook. For every integrated trial:

- one shadow material/certificate must exist per task;
- exactly two application command publishes are captured per task;
- broker PUBLISH workload must remain exactly `4 * tasks`;
- exactly two state events must exist per task;
- every task row must pass the complete conformance vector.

Raw `$SYS` publish-byte equality remains diagnostic only, per the previously
frozen R1 shadow-hook gate. The integrated gate does not silently promote that
known-unsound aggregate oracle.

## Falsification seam tests

The integrated live artifact also runs explicit post-execution mutations:

1. cross-task observation/action substitution:
   - independent oracle rejects;
   - production correlator rejects;
2. consequential ACT2 payload mutation:
   - independent oracle rejects;
   - production realization rejects before semantics;
3. detaching a semantic certificate from its original same-task proof:
   - chained certificate validation rejects;
4. adding one synthetic positive event inside the frozen observation boundary:
   - independent oracle flips to `VALID / REUSE`;
   - production chain independently flips to `VALID / REUSE`.

These mutations are verification-only. They do not alter live execution.

## Frozen non-goals

This increment still does **not** implement:

```text
execute / block / fallback / regenerate
selective-reuse intervention
runtime policy
latency promotion threshold
backend optimization
```

The next scientific boundary after this gate is runtime cost characterization:
measure certification latency/throughput first, and optimize only if the measured
profile demonstrates a real bottleneck.
