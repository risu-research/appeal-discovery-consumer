# ReplayMark runtime realization boundary — freeze + E3b observation realization

## Status

This increment freezes the boundary between raw runtime artifacts and the
already-packaged ReplayMark semantic contract, and implements **only the E3b
observation side** of that boundary.

It does not realize historical actions, invoke `CompiledContract`, execute or
block an action, choose target-native fallback, refine evidence, retry, or alter
the existing E3b R0/R1/R2 harness.

Concrete semantic-package authority before this increment:

`replaymark-concrete-contract-packaging@4c3680d0c9dea2be5fb88109afea1f7f7d0045af`

## 1. Why this boundary exists

The proved semantic contract accepts an already-canonical pair `(e, z)`:

- `e`: retained-evidence token;
- `z`: historical action coordinates, projected by the contract's `ClaimSpec`.

A live replay system instead produces events, timestamps, topics, payloads, API
calls, and other concrete runtime objects. A perfectly correct theorem can still
produce the wrong real-system conclusion if those raw objects are incorrectly
mapped into `(e, z)`.

Therefore realization is a separate correctness boundary rather than an
extension of VALID/INVALID/UNRESOLVED semantics.

## 2. Frozen runtime value types

`replaymark.runtime_realization` freezes:

- `RealizedObservation`;
- `RealizedHistoricalAction`;
- `RealizationProvenance`;
- `RealizationFailure` / `RealizationError`;
- `RuntimeReuseCertificate`.

These are runtime-boundary values, not new package-root semantic types. The
existing six-type `replaymark.__all__` semantic boundary is unchanged.

## 3. Realization provenance

Every successful realization carries:

```text
stage
realizer_id
realizer_semantic_digest
source_schema
raw_record_digest
```

`realizer_semantic_digest` content-addresses the interpretation rule.
`raw_record_digest` content-addresses the canonical runtime record admitted by
that rule.

This separates the provenance questions:

> Which interpretation semantics were used?

and:

> Which exact runtime record was interpreted?

## 4. Realization failure is not semantic UNRESOLVED

The runtime boundary has structured failure classes including malformed input,
missing required fields, duplicate input, clock-domain mismatch,
out-of-boundary data, ambiguous realization, and unknown semantic values.

They are not ReplayMark verdicts.

```text
REALIZATION FAILURE != UNRESOLVED
```

`UNRESOLVED` means an admitted evidence token is semantically underdetermined by
the compiled model. A realization failure means there is no admitted semantic
input yet; a correct bridge must not call the semantic contract after such a
failure.

## 5. `RuntimeReuseCertificate` freeze

`RuntimeReuseCertificate` is the future audit chain joining:

```text
RealizedObservation
RealizedHistoricalAction
exact CompiledContract identity
Adjudication
RStarDecision
```

The value validates token, claim, adjudication, R*, depth, support/evidence
authority, and action-projection consistency. It contains no `execute`,
`fallback`, `regenerate`, `abort`, or retry field.

This increment freezes the type but does not construct it from live E3b data,
because historical-action realization is deliberately still absent.

## 6. E3b source authority and the completeness problem

The frozen E3b harness stores received state events and, for one device, searches
for an event satisfying:

```text
after_ns <= recv_mono_ns <= deadline_ns
and bool(event["on"])
```

The deadline and lower bound are inclusive. Older retained events remain in the
harness but do not match; later events do not change the already-closed boundary.

A first draft of this increment considered accepting a caller-prefiltered list of
"matching" events. That design was rejected before freeze: omission of one
matching event would recreate the same completeness class of error that
compiler-owned Omega inversion was introduced to eliminate.

The production realizer therefore accepts a **complete state-event snapshot** and
performs the E3b match predicate itself.

## 7. Complete raw observation record

The source schema is:

```text
schema
clock_domain
expected_device
command_publish_mono_ns
verify_deadline_mono_ns
closed_at_mono_ns
events:
    event_id
    device
    on
    recv_mono_ns
    clock_domain
```

The record means:

> this is the complete admitted event snapshot available through
> `closed_at_mono_ns` for this realization boundary.

The snapshot must satisfy:

```text
closed_at_mono_ns >= verify_deadline_mono_ns
```

Otherwise absence cannot safely mean "not visible by deadline" and realization
fails closed.

This increment does not yet implement the live snapshot-capture adapter. The
truthfulness and completeness of that future capture is an explicit remaining
trust obligation, not hidden inside the semantic theorem.

## 8. Exact E3b matching rule

The realizer itself selects events satisfying all three conditions:

```text
event.device == expected_device
event.on is True
command_publish_mono_ns <= event.recv_mono_ns <= verify_deadline_mono_ns
```

The source schema deliberately requires `on` to be an actual boolean rather than
inheriting arbitrary Python truthiness. This is a conservative runtime typing
boundary for the E3b state body.

The result is:

```text
zero matching events
    -> not_visible_by_deadline

exactly one matching event
    -> confirmed_by_deadline

more than one distinct matching event
    -> AMBIGUOUS_REALIZATION
```

The realized object preserves:

- the exact evidence token;
- named monotonic clock domain;
- `boundary_timestamp_ns = verify_deadline_mono_ns`; and
- the receive timestamp of the matching event when confirmed.

## 9. Absence versus missing or incomplete data

Three cases are intentionally different.

**Complete snapshot, zero matching events:** legitimate negative evidence,
`not_visible_by_deadline`.

**Missing `events` field:** malformed input.

**Snapshot closed before the verify deadline:** insufficiently complete input and
`OUT_OF_BOUNDARY`.

ReplayMark therefore never turns missing or not-yet-closed data into negative
evidence.

## 10. Historical and future events are retained but not reinterpreted

An event before `command_publish_mono_ns` may be present in the complete retained
snapshot. It is history and is ignored by the decision predicate.

An event after `verify_deadline_mono_ns` but at or before `closed_at_mono_ns` may
also be present if the snapshot was taken later. It is ignored and cannot relabel
the closed decision.

An event timestamp later than the declared `closed_at_mono_ns` contradicts the
snapshot boundary and fails closed.

This distinction matches the frozen harness more faithfully than requiring a
caller to strip every nonmatching event before realization.

## 11. One monotonic clock domain only

Every timestamp in one record must belong to the same named monotonic clock
domain. ReplayMark does not infer offsets, translate wall time, or perform
approximate cross-clock conversion.

A cross-domain event fails with `CLOCK_DOMAIN_MISMATCH`.

## 12. Duplicate and repeated matching events

`event_id` is a record-local identity for one captured receive occurrence.
Duplicate IDs fail as `DUPLICATE_INPUT`.

Multiple distinct events that all satisfy the exact E3b matching predicate fail
as `AMBIGUOUS_REALIZATION`. The first realizer does not guess whether such data
represents retransmission, duplication, or a meaningful second state event.

Unrelated-device, `on=False`, pre-command, and post-deadline events may coexist in
the complete snapshot and do not count as matches.

## 13. Strict source shape

The production parser rejects missing or unknown top-level/event fields, foreign
schemas, noncanonical identifiers, nonboolean `on`, booleans/floats/negative
values where integer nanoseconds are required, non-sequence event containers,
a deadline not strictly after command publication, insufficient snapshot
closure, cross-clock data, duplicate IDs, and events after the declared closure.

Shape failures become structured `RealizationError`; no ordinary parser exception
is converted into an evidence token.

## 14. Content-addressed interpretation rule

The E3b realization rule has a canonical record containing its source schema,
complete-snapshot requirement, exact device/state/time predicate, inclusive
deadline, clock-domain rule, event-cardinality semantics, and
absence-versus-missing semantics.

Its SHA-256 is stored in every successful `RealizationProvenance`.

A changed raw timestamp changes the raw-record digest. A changed interpretation
rule changes the realizer semantic digest.

## 15. Independent literal oracle

Verification uses:

`replaymark_oracle/e3b_observation_oracle.py`

The oracle imports neither `replaymark.runtime_e3b_observation` nor
`replaymark.runtime_realization`. It works directly over plain mappings and
literally evaluates the complete-snapshot rule.

Production and oracle are compared across systematic deadline, closure,
timestamp, clock-domain, device, boolean-state, event-cardinality, and malformed
shape cases.

## 16. Existing E3b experiment remains frozen

This increment does not edit historical `ladder.py` or `experiment.py`.

No R1 decision changes. No historical ACT2 is blocked. No fallback is selected.
The existing R0/R1/R2 scientific evidence therefore remains untouched while its
observation boundary is independently restated and executable.

## 17. Remaining trust boundaries

This increment still does not prove:

- that a future live capture adapter truthfully reports `closed_at_mono_ns`;
- that the live capture includes every relevant E3b state-event occurrence;
- that this observation realizer is admitted for a particular compiled evidence
  semantics artifact in a live bridge;
- historical concrete-action realization;
- raw MQTT command/payload -> `ProjectedAction` correctness;
- runtime `CompiledContract` invocation;
- shadow-mode insertion;
- execution intervention or fallback correctness.

The `realizer_semantic_digest` makes future admission binding auditable, but the
binding itself is intentionally not invented in this observation-only step.

## 18. Next admissible boundary

After this gate passes, the next atomic step is:

```text
raw historical E3b ACT2
    -> RealizedHistoricalAction
```

That step must freeze the concrete MQTT action identity and compare production
canonicalization to an independent literal oracle.

Only after both observation and action realization are closed should a shadow
runtime bridge call the already-frozen `CompiledContract` and construct
`RuntimeReuseCertificate`.
