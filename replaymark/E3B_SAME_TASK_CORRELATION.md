# ReplayMark E3b same-task correlation freeze

## Status

This increment closes exactly one runtime-composition seam after the independently frozen E3b observation and historical-action realizers:

```text
raw stage-1 observation
  -> existing RealizedObservation

raw stage-2 candidate publish
  -> existing RealizedHistoricalAction

both realized values
  -> E3bTaskCorrelationProof
```

It does **not** call `ExplicitCompiledContract`, adjudicate a claim, call `certify_reuse()`, construct a `RuntimeReuseCertificate`, alter R0/R1/R2 execution, block a publish, or select fallback/regeneration.

## Why this gate exists

An individually valid stage-1 observation from task X and an individually valid stage-2 ACT2 candidate from task Y are not a valid ReplayMark runtime input pair. Co-location in one Python call, temporal proximity, or a caller-supplied `same_task=True` flag is not evidence of correlation.

The E3b harness already gives us a stronger native identity relation. Stage-1 and stage-2 devices are created as:

```text
<prefix>-<task-id>-a
<prefix>-<task-id>-b
```

This gate makes that relation explicit and content-addressed before any semantic contract is allowed to consume the pair.

## Frozen correlation rule

The production correlator must first invoke the already-frozen individual realizers. Individual realization failure propagates unchanged and stops the chain.

After both succeed, the correlator independently parses the runtime identities and requires:

```text
observation role = a
action role      = b
observation prefix == action prefix
observation task-id == action task-id
task-id is canonical ASCII decimal
observation clock domain == action clock domain
action publish timestamp >= stage-1 command publish timestamp
```

Temporal proximity is never used as task identity. The timestamp rule is only a conservative causal-order sanity check after exact identity has already matched.

## Why `RealizedObservation` is not widened

`RealizedObservation` deliberately contains the evidence token and observation boundary, not E3b-specific task identity. Mutating that generic theorem-boundary value now would couple a substrate-specific naming scheme to the portable semantic core.

Instead this increment adds an E3b-specific `E3bTaskCorrelationProof` outside the generic semantic types, exactly at the concrete composition seam.

## Provenance binding

A successful proof binds:

- the correlator semantic digest;
- canonical task prefix/id and required a->b roles;
- shared monotonic clock domain;
- stage-1 command timestamp, observation boundary, and stage-2 publish timestamp;
- exact `RealizedObservation` fingerprint;
- exact `RealizedHistoricalAction` fingerprint;
- exact canonical raw-record digests.

Changing the action publish timestamp does not change task identity, but it does change the action realization fingerprint and therefore changes the correlation proof fingerprint.

## Failure semantics

Pairwise failures are **not** ReplayMark Verdicts and are **not** semantic `UNRESOLVED`.

The new E3b-specific failure classes are:

```text
MALFORMED_IDENTITY
ROLE_MISMATCH
TASK_MISMATCH
CLOCK_DOMAIN_MISMATCH
TEMPORAL_INCONSISTENCY
INTERNAL_INCONSISTENCY
```

No generic `RealizationStage` or Verdict enum is widened for this increment.

## Independent oracle wall

The gate compares production correlation against a separately written literal regex-based oracle for the new pairwise relation. The observation and action realizers retain their own pre-existing independent differential gates.

## Next boundary, intentionally still open

Only after this gate is frozen may the next increment do:

```text
E3bCorrelatedRuntimePair
  -> existing ExplicitCompiledContract.adjudicate(...)
  -> existing ExplicitCompiledContract.certify_reuse(...)
  -> RuntimeReuseCertificate
```

That future bridge must remain shadow-only and must not duplicate support, adjudication, or R* logic.
